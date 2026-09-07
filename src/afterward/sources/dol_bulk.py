"""Reader for DOL's bulk ETP export, read **beside** the search API and never instead of it.

Source D1B in PROVENANCE.md. The file is
``https://www.trainingproviderresults.gov/data/DownloadPrograms.xlsx`` -- the same U.S.
Government work as D1, public domain under 17 U.S.C. §105.

`PROVENANCE.md` "Notes on D1: the bulk export, evaluated 2026-08-07" settles, in the
negative, whether this file should *replace* the search API: it carries no ``field_uuid`` so
every program URL would break, it is an older vintage that suppresses more than the API
publishes, and it does not close the program-year gap. **Nothing here reopens that.** What
the same note leaves open is the one thing the bulk file has that the API does not:

    de129 -- the actual denominator of the published Q2 employment rate.

Issue #25 established that ``employed_q2`` is not the numerator of ``employment_rate_q2``:
the rate is DE123/DE129, and DE129 (exiters whose second quarter after exit had arrived) is
a differently-scoped cohort from DE121 (``total_exited``). DE129 is not on the search API,
so the site publishes a rate whose denominator it cannot show -- the one figure a reader
cannot check on a site whose whole argument is that a reader must be able to.

Three rules govern everything in this module, and they are the reason it is a separate
source rather than an enrichment of :mod:`afterward.sources.dol_etp`:

1. **A borrowed figure is never merged into a D1 figure.** It travels with this file's own
   vintage, in its own block, labelled with where it came from. A denominator from one
   vintage beside a rate from another is two facts, and the record says so or shows nothing.
2. **A denominator that cannot reconstruct its own program's published rate is not that
   program's denominator.** Where ``d123_total_employed_q2 / de129`` does not reproduce
   ``c_q2_employment_percent``, nothing is shown and the program is counted in its own
   bucket. Measured over the whole file on 2026-09-07: 1,782 of 1,782 California rows
   carrying all three reconstruct within 0.01.
3. **The three states stay distinguishable**: a denominator shown, a bulk row found whose
   arithmetic does not hold, and no bulk row at all. And above them a fourth, which is not
   one of the three: the export was not read. Absent is not zero.

**No dependency.** An ``.xlsx`` is a zip of XML, and this reads it with :mod:`zipfile` and
:mod:`xml.etree` alone rather than adding a spreadsheet library to a package whose entire
runtime is ``httpx`` and ``typer``. The reader is deliberately small and refuses anything it
does not understand; it is not a general-purpose Excel reader and does not pretend to be.
"""

from __future__ import annotations

import datetime as _datetime
import re
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any
from xml.etree import ElementTree  # nosec B405 - _open_member is the defusing; see PROLOGUE_BYTES

from afterward.sources.dol_etp import clean_cip_code, clean_text, normalise_provider

BULK_URL = "https://www.trainingproviderresults.gov/data/DownloadPrograms.xlsx"
"""Where the file comes from. Nothing in this module fetches it.

The build reads a copy an operator has already downloaded, for the same reason
`make data` is dispatch-only: the DOL endpoint answers a GitHub Actions runner with 403,
and a build that silently produced no denominators because a fetch failed would publish the
absence as a measurement.
"""

SOURCE_ID = "D1B"
SOURCE_LABEL = "DOL ETP bulk export (DownloadPrograms.xlsx)"

_SPREADSHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_RELS_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_DOC_RELS_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

#: The columns this module reads, by their exact header in the file. Verified against the
#: real export on 2026-09-07: 57 columns, 77,085 rows, 55 distinct `reportingstate` values.
#:
#: Named exhaustively and required, rather than probed for with aliases. A missing column is
#: refused by name -- see :func:`_column_index` -- because the alternative is a join on a
#: column that happens to be there, which would produce numbers rather than an error.
PROVIDER_COLUMN = "d101_eligible_training_provider"
PROGRAM_NAME_COLUMN = "d105_program_name"
CIP_COLUMN = "d110_cip_code"
ZIP_COLUMN = "zip"
STATE_COLUMN = "reportingstate"
EMPLOYED_Q2_COLUMN = "d123_total_employed_q2"
PUBLISHED_RATE_COLUMN = "c_q2_employment_percent"
DENOMINATOR_Q2_COLUMN = "de129"
DENOMINATOR_Q4_COLUMN = "de130"
DENOMINATOR_WIOA_Q2_COLUMN = "de170"
DENOMINATOR_WIOA_Q4_COLUMN = "de171"
LIST_DATE_COLUMN = "de172"

REQUIRED_COLUMNS: tuple[str, ...] = (
    PROVIDER_COLUMN,
    PROGRAM_NAME_COLUMN,
    CIP_COLUMN,
    ZIP_COLUMN,
    STATE_COLUMN,
    EMPLOYED_Q2_COLUMN,
    PUBLISHED_RATE_COLUMN,
    DENOMINATOR_Q2_COLUMN,
    DENOMINATOR_Q4_COLUMN,
    DENOMINATOR_WIOA_Q2_COLUMN,
    DENOMINATOR_WIOA_Q4_COLUMN,
    LIST_DATE_COLUMN,
)

SUPPRESSED = -1.0
"""The same sentinel D1 uses, and it means the same thing here: not reported or withheld."""

RECONSTRUCTION_TOLERANCE = 0.01
"""How close ``d123 / de129`` must come to the published rate to be that rate's denominator.

Not a fitted threshold. The published rate is a fraction rounded by DOL, so an exact match
is not available; 0.01 is one step of the rate's own precision. It is also the tolerance the
provenance assessment measured at, and at which every one of the 1,782 California rows
carrying all three figures reconstructs -- so it is not doing any work to make a weak claim
look strong. Loosening it would; that is why it is a literal here and not a parameter.
"""

#: Excel's serial-date epoch. `de172` is filed as a number, not a date string: the raw value
#: 45473 is 2024-06-30. Publishing 45473 as "the vintage" would be a number that looks like a
#: measurement and is not one, which is the error this whole project is written against.
_EXCEL_EPOCH = _datetime.date(1899, 12, 30)

_CELL_REFERENCE = re.compile(r"^([A-Z]+)")

_FLOAT_ARTEFACT_CIP = re.compile(r"^(\d{1,2})\.(\d{5,})$")
"""A CIP code that has been through a binary float and come back wider than CIP goes.

Measured on the real export: it files ``11.020099999999999`` for 11.0201 and
``52.020099999999999`` for 52.0201. CIP details are two or four digits and never more, so
five or more decimals cannot be a code -- they can only be the residue of a round-trip
through a double. This is the bulk file's own defect and is repaired here rather than in
:func:`afterward.sources.dol_etp.clean_cip_code`, which repairs D1's different one (lost
zeros) and must not start accepting widths CIP does not have.

It matters: without this, the four-key join found 635 shared keys where 2,018 more agreed on
provider and program name and disagreed only on a CIP that is the same code.
"""


def repair_float_cip(value: str | None) -> str | None:
    """Round a CIP that a float round-trip widened, and leave every other spelling alone."""
    text = clean_text(value)
    if text is None:
        return None
    if _FLOAT_ARTEFACT_CIP.match(text) is None:
        return text
    try:
        return f"{round(float(text), 4):.4f}"
    except ValueError:  # pragma: no cover - the pattern already proved it parses
        return text


MAX_MEMBER_BYTES = 512 * 1024 * 1024
"""Uncompressed cap on any one member this reader opens.

An ``.xlsx`` is a zip, and a zip's declared uncompressed size is what makes a decompression
bomb cheap to build and expensive to open. The real export's two large members are 132 MB
(``sheet1.xml``) and 42 MB (``sharedStrings.xml``) uncompressed, from a 36 MB download, so
this leaves headroom for several years of growth and still refuses a file whose members
claim a gigabyte.
"""


class BulkExportError(RuntimeError):
    """Raised when the bulk export cannot be read as the file this module expects."""


_DOCTYPE = re.compile(rb"<!DOCTYPE", re.IGNORECASE)
_ELEMENT_START = re.compile(rb"<[A-Za-z_]")
PROLOGUE_BYTES = 64 * 1024
"""How much of a member is read to prove it declares no DOCTYPE before parsing it.

A DOCTYPE is the only way an XML document can declare an entity, and it must appear before
the document element. Both classic attacks need one: a billion-laughs bomb needs an internal
entity, an XXE read needs an external one. Refusing the DOCTYPE outright refuses both, and it
does so the same way on every Python this package supports.

That guard is load-bearing rather than belt-and-braces. Measured on this tree's interpreter:
`xml.etree.ElementTree` *does* expand internal entities -- the four-level laugh below expands
to 300 characters, and a ten-level one to a gigabyte. Neither `defusedxml` nor an expat
handler is used instead: the first is a dependency this package does not otherwise need, and
the second is `XMLParser.parser`, which no longer exists on Python 3.14.

    <!DOCTYPE lolz [ <!ENTITY lol "lol"> <!ENTITY lol1 "&lol;&lol;..."> ]>

A spreadsheet part has no reason to carry a DOCTYPE, and the real export carries none in any
of its ten members.
"""


def _open_member(archive: zipfile.ZipFile, name: str) -> IO[bytes]:
    """Open one member, refusing an implausible size or any DOCTYPE, before parsing it."""
    try:
        info = archive.getinfo(name)
    except KeyError as error:
        raise BulkExportError(f"the bulk export has no member {name!r}") from error
    if info.file_size > MAX_MEMBER_BYTES:
        raise BulkExportError(
            f"{name} declares {info.file_size} uncompressed bytes, over the "
            f"{MAX_MEMBER_BYTES}-byte cap this reader will open"
        )
    handle = archive.open(name)
    try:
        prologue = handle.read(PROLOGUE_BYTES)
        if _DOCTYPE.search(prologue):
            raise BulkExportError(f"{name} declares a DOCTYPE; refusing to parse it")
        if _ELEMENT_START.search(prologue) is None:
            # The document element has not started within the window, so a DOCTYPE could
            # still be waiting past it. Refusing is the only honest answer: the alternative
            # is a scan that stops before the thing it is scanning for.
            raise BulkExportError(
                f"{name} has no document element in its first {PROLOGUE_BYTES} bytes"
            )
        handle.seek(0)
    except Exception:
        handle.close()
        raise
    return handle


def _column_number(reference: str) -> int:
    """Zero-based column index from an A1-style cell reference."""
    match = _CELL_REFERENCE.match(reference)
    if match is None:
        raise BulkExportError(f"unreadable cell reference {reference!r}")
    number = 0
    for character in match.group(1):
        number = number * 26 + (ord(character) - 64)
    return number - 1


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    """The workbook's shared-string table, or an empty one when it has none."""
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    strings: list[str] = []
    with _open_member(archive, "xl/sharedStrings.xml") as handle:
        for _event, element in ElementTree.iterparse(handle, events=("end",)):  # noqa: S314  # nosec B314 - _open_member refuses any member declaring a DOCTYPE
            if element.tag == f"{_SPREADSHEET_NS}si":
                strings.append(
                    "".join(node.text or "" for node in element.iter(f"{_SPREADSHEET_NS}t"))
                )
                element.clear()
    return strings


def _first_sheet_path(archive: zipfile.ZipFile) -> str:
    """The path of the workbook's first worksheet, resolved through its relationships.

    Resolved rather than assumed to be ``xl/worksheets/sheet1.xml``. The current file does
    put it there, and a reader that hard-codes the guess reports "no such member" when a
    future export does not -- which reads as a corrupt download rather than as a layout
    this reader does not handle.
    """
    with _open_member(archive, "xl/workbook.xml") as handle:
        workbook = ElementTree.parse(handle).getroot()  # noqa: S314  # nosec B314 - _open_member refuses any member declaring a DOCTYPE
    sheets = workbook.find(f"{_SPREADSHEET_NS}sheets")
    sheet = None if sheets is None else sheets.find(f"{_SPREADSHEET_NS}sheet")
    if sheet is None:
        raise BulkExportError("workbook declares no worksheet")
    relationship_id = sheet.get(f"{_DOC_RELS_NS}id")
    with _open_member(archive, "xl/_rels/workbook.xml.rels") as handle:
        relationships = ElementTree.parse(handle).getroot()  # noqa: S314  # nosec B314 - _open_member refuses any member declaring a DOCTYPE
    for relationship in relationships.iter(f"{_RELS_NS}Relationship"):
        if relationship.get("Id") == relationship_id:
            target = relationship.get("Target") or ""
            return target if target.startswith("xl/") else f"xl/{target.lstrip('/')}"
    raise BulkExportError(f"workbook relationship {relationship_id!r} names no worksheet")


def _cell_text(cell: ElementTree.Element, strings: Sequence[str]) -> str:
    kind = cell.get("t")
    if kind == "inlineStr":
        inline = cell.find(f"{_SPREADSHEET_NS}is")
        if inline is None:
            return ""
        return "".join(node.text or "" for node in inline.iter(f"{_SPREADSHEET_NS}t"))
    value = cell.find(f"{_SPREADSHEET_NS}v")
    if value is None or value.text is None:
        return ""
    if kind == "s":
        index = int(value.text)
        if not 0 <= index < len(strings):
            raise BulkExportError(f"shared-string index {index} is outside the table")
        return strings[index]
    return value.text


def _sheet_rows(archive: zipfile.ZipFile, strings: Sequence[str]) -> Iterator[dict[int, str]]:
    """Every row of the first worksheet, as {column index: text}.

    Streamed and cleared row by row. The real file is 36 MB compressed and 77,085 rows; a
    reader that materialised it would make the build's memory profile depend on how many
    states DOL happens to publish.
    """
    with _open_member(archive, _first_sheet_path(archive)) as handle:
        for _event, element in ElementTree.iterparse(handle, events=("end",)):  # noqa: S314  # nosec B314 - _open_member refuses any member declaring a DOCTYPE
            if element.tag != f"{_SPREADSHEET_NS}row":
                continue
            row: dict[int, str] = {}
            for position, cell in enumerate(element.findall(f"{_SPREADSHEET_NS}c")):
                reference = cell.get("r")
                index = _column_number(reference) if reference else position
                row[index] = _cell_text(cell, strings)
            yield row
            element.clear()


def _column_index(header: Mapping[int, str]) -> dict[str, int]:
    """Locate every required column, or refuse naming the ones that are missing."""
    found = {name.strip(): index for index, name in header.items() if name.strip()}
    missing = [name for name in REQUIRED_COLUMNS if name not in found]
    if missing:
        raise BulkExportError(
            "the bulk export is missing column(s) this reader requires: "
            + ", ".join(missing)
            + f". It carries {len(found)}: "
            + ", ".join(sorted(found))
        )
    return {name: found[name] for name in REQUIRED_COLUMNS}


def measure(value: str) -> float | None:
    """A bulk-file measure as a float, or ``None`` when withheld or unreported.

    The same rule as :func:`afterward.sources.dol_etp.clean_measure`, restated here over
    strings because that one takes the API's already-typed values. ``-1`` is the sentinel and
    is never a zero.
    """
    text = value.strip()
    if not text:
        return None
    try:
        numeric = float(text)
    except ValueError:
        return None
    return None if numeric == SUPPRESSED else numeric


def list_date(value: str) -> str | None:
    """`de172` as an ISO date, or ``None`` when absent or unreadable.

    The column is an Excel serial number. Returning the raw 45473 would publish a number that
    reads as data and means nothing, so an unconvertible value is an absence here rather than
    a figure a reader has to know to distrust.
    """
    text = value.strip()
    if not text:
        return None
    try:
        serial = int(float(text))
    except ValueError:
        return None
    if serial <= 0:
        return None
    try:
        return (_EXCEL_EPOCH + _datetime.timedelta(days=serial)).isoformat()
    except OverflowError:  # pragma: no cover - only reachable from an absurd serial
        return None


def join_key(
    provider_name: str | None,
    program_name: str | None,
    cip_code: str | None,
    zip_code: str | None,
) -> tuple[str, str, str, str] | None:
    """The four-key join the provenance assessment used, or ``None`` if a part is missing.

    Provider names go through :func:`afterward.sources.dol_etp.normalise_provider`, which
    folds case and internal whitespace and nothing else -- the same key the duplicate-cohort
    check uses, so two modules cannot disagree about whether two filings are one provider.
    CIP goes through :func:`afterward.sources.dol_etp.clean_cip_code`, which restores the
    zero padding a float round-trip strips, because both sides of this join have been through
    one and ``51.071`` and ``51.0710`` are the same code.

    A record missing any of the four is not keyed at all. Joining on three of four would pair
    two programs a provider genuinely files separately, and a denominator attached to the
    wrong program is worse than no denominator.
    """
    provider = normalise_provider(provider_name)
    program = normalise_provider(program_name)
    cip = clean_cip_code(cip_code)
    postal = clean_text(zip_code)
    if postal is not None:
        postal = postal.split("-", 1)[0].strip().zfill(5)
    if not provider or not program or not cip or not postal:
        return None
    return provider, program, cip, postal


def reconstructs(
    employed_q2: float | None,
    denominator: float | None,
    published_rate: float | None,
) -> bool:
    """Whether this row's own arithmetic reproduces its own published rate.

    All three must be present and the denominator positive. A zero denominator does not make
    a rate of zero; it makes the division undefined, and a row that carries one has not
    demonstrated anything about the figure sitting beside it.
    """
    if employed_q2 is None or denominator is None or published_rate is None:
        return False
    if denominator <= 0:
        return False
    return abs(employed_q2 / denominator - published_rate) <= RECONSTRUCTION_TOLERANCE


@dataclass(frozen=True)
class BulkRow:
    """One row of the bulk export, carrying only what D1 does not publish."""

    provider_name: str | None
    program_name: str | None
    cip_code: str | None
    zip_code: str | None
    state: str | None
    employed_q2: float | None
    published_rate: float | None
    denominator_q2: float | None
    denominator_q4: float | None
    denominator_wioa_q2: float | None
    denominator_wioa_q4: float | None
    added_to_state_list: str | None

    @property
    def key(self) -> tuple[str, str, str, str] | None:
        return join_key(self.provider_name, self.program_name, self.cip_code, self.zip_code)

    @property
    def reconstructs_published_rate(self) -> bool:
        return reconstructs(self.employed_q2, self.denominator_q2, self.published_rate)


@dataclass(frozen=True)
class BulkExport:
    """A read of the bulk export, restricted to one reporting state.

    ``by_key`` deliberately holds only keys that occur exactly once. A key the file
    republishes is ambiguous, and picking either row would attach one program's denominator
    to another's rate on the strength of an arbitrary choice. ``ambiguous_keys`` counts them
    so the number is published rather than lost.
    """

    path: str
    state: str
    rows_read: int
    rows_in_state: int
    by_key: Mapping[tuple[str, str, str, str], BulkRow]
    ambiguous_keys: int
    unkeyable_rows: int
    vintage: str | None
    """The newest ``de172`` in the selected state, as an ISO date.

    The file carries no program year, reporting period or cycle -- see PROVENANCE.md "Notes
    on D1: the feed carries no program year" -- so this is not the period the outcomes
    describe. It is the newest date on which any program in this state was added to the
    state's ETP list, which is the only date the file has. Every borrowed figure is labelled
    with it so a reader can see that the denominator and the rate beside it are not from the
    same read.
    """

    def get(self, key: tuple[str, str, str, str] | None) -> BulkRow | None:
        return None if key is None else self.by_key.get(key)


def parse_rows(archive: zipfile.ZipFile, *, state: str) -> tuple[list[BulkRow], int, int]:
    """Every row of the export for one reporting state, plus the totals it was drawn from."""
    strings = _shared_strings(archive)
    stream = _sheet_rows(archive, strings)
    try:
        header = next(stream)
    except StopIteration as error:
        raise BulkExportError("the bulk export has no header row") from error
    index = _column_index(header)
    wanted = state.strip().upper()
    rows: list[BulkRow] = []
    total = 0
    for raw in stream:
        total += 1

        def cell(name: str, raw: dict[int, str] = raw) -> str:
            return raw.get(index[name], "")

        if (cell(STATE_COLUMN) or "").strip().upper() != wanted:
            continue
        rows.append(
            BulkRow(
                provider_name=clean_text(cell(PROVIDER_COLUMN)),
                program_name=clean_text(cell(PROGRAM_NAME_COLUMN)),
                cip_code=repair_float_cip(cell(CIP_COLUMN)),
                zip_code=clean_text(cell(ZIP_COLUMN)),
                state=wanted,
                employed_q2=measure(cell(EMPLOYED_Q2_COLUMN)),
                published_rate=measure(cell(PUBLISHED_RATE_COLUMN)),
                denominator_q2=measure(cell(DENOMINATOR_Q2_COLUMN)),
                denominator_q4=measure(cell(DENOMINATOR_Q4_COLUMN)),
                denominator_wioa_q2=measure(cell(DENOMINATOR_WIOA_Q2_COLUMN)),
                denominator_wioa_q4=measure(cell(DENOMINATOR_WIOA_Q4_COLUMN)),
                added_to_state_list=list_date(cell(LIST_DATE_COLUMN)),
            )
        )
    return rows, total, len(rows)


def read_bulk_export(path: Path | str, *, state: str = "CA") -> BulkExport:
    """Read one state out of the bulk export, keyed for the four-key join.

    Raises :class:`BulkExportError` rather than returning an empty read for anything it
    cannot understand -- a wrong file, a missing column, an unreadable cell reference. An
    empty read and a refused one look identical in a coverage count, and only one of them
    means "this state has no rows".
    """
    location = Path(path)
    try:
        archive = zipfile.ZipFile(location)
    except (OSError, zipfile.BadZipFile) as error:
        raise BulkExportError(f"{location}: not a readable .xlsx: {error}") from error
    with archive:
        rows, total, in_state = parse_rows(archive, state=state)

    counted: dict[tuple[str, str, str, str], list[BulkRow]] = {}
    unkeyable = 0
    for row in rows:
        key = row.key
        if key is None:
            unkeyable += 1
            continue
        counted.setdefault(key, []).append(row)
    unique = {key: found[0] for key, found in counted.items() if len(found) == 1}
    ambiguous = sum(1 for found in counted.values() if len(found) > 1)
    dates = [row.added_to_state_list for row in rows if row.added_to_state_list]
    return BulkExport(
        path=str(location),
        state=state.strip().upper(),
        rows_read=total,
        rows_in_state=in_state,
        by_key=unique,
        ambiguous_keys=ambiguous,
        unkeyable_rows=unkeyable,
        vintage=max(dates) if dates else None,
    )


# What a program can be in once the export has been read, and the one thing above them that
# is not a state of the program at all. Spelled out as constants because the build's coverage
# counters and the site both read them, and a typo would silently make a bucket unreachable.
#
# The issue that asked for this named three states. Measuring the join against the real
# 3,266-program dataset produced five, and the two extra ones are the measurement rather than
# a design flourish -- see PROVENANCE.md "Notes on D1B".
STATE_SHOWN = "shown"
STATE_RATE_NOT_PUBLISHED = "rate_not_published"
STATE_BULK_FIGURES_SUPPRESSED = "bulk_figures_suppressed"
STATE_DOES_NOT_RECONSTRUCT = "bulk_row_does_not_reconstruct"
STATE_NO_BULK_ROW = "no_bulk_row"
STATE_NOT_READ = "bulk_export_not_read"

DENOMINATOR_STATES: tuple[str, ...] = (
    STATE_SHOWN,
    STATE_RATE_NOT_PUBLISHED,
    STATE_BULK_FIGURES_SUPPRESSED,
    STATE_DOES_NOT_RECONSTRUCT,
    STATE_NO_BULK_ROW,
)
"""Every state a program can be in when the export *was* read. `STATE_NOT_READ` is absent on
purpose: it is a fact about the build, and folding it in here would let a build that read no
file report programs in a bucket describing what it found in one."""


def _not_read() -> dict[str, Any]:
    return {
        "state": STATE_NOT_READ,
        "denominator": None,
        "source": None,
        "vintage": None,
        "reconstructed_rate": None,
        "reconstructs_its_own_published_rate": None,
    }


def denominator_block(
    export: BulkExport | None,
    *,
    provider_name: str | None,
    program_name: str | None,
    cip_code: str | None,
    zip_code: str | None,
    published_rate: float | None,
) -> dict[str, Any]:
    """What this build can honestly say about one program's employment denominator.

    ``export`` of ``None`` is the ordinary case -- CI has no copy of a 36 MB file the DOL
    endpoint will not serve a runner -- and produces ``bulk_export_not_read`` with a null
    denominator. That is a statement about this build, not about this program, and it is kept
    distinct from every state that is a statement about the program.

    ``published_rate`` is **D1's** rate for this program: the number the site actually shows.
    The reconstruction is against that and nothing else. The bulk file reproduces its *own*
    ``c_q2_employment_percent`` from ``d123 / de129`` on every California row that carries all
    three -- 1,782 of 1,782 on 2026-09-07 -- but that is a fact about the bulk file's internal
    consistency, not a licence to put its denominator under a different file's rate. Measured
    over the 3,266-program dataset: 839 programs have a bulk row whose arithmetic reproduces
    the bulk file's own older rate and not the rate this site publishes. Showing a denominator
    for those would put a 2024 cohort under a 2026 number.

    ``reconstructs_its_own_published_rate`` carries that distinction into the record, so a
    reader looking at a refused program can tell "the bulk file disagrees with itself" from
    "the bulk file and the API disagree with each other".
    """
    if export is None:
        return _not_read()
    row = export.get(join_key(provider_name, program_name, cip_code, zip_code))
    if row is None:
        return {
            "state": STATE_NO_BULK_ROW,
            "denominator": None,
            "source": SOURCE_ID,
            "vintage": export.vintage,
            "reconstructed_rate": None,
            "reconstructs_its_own_published_rate": None,
        }
    common: dict[str, Any] = {
        "denominator": None,
        "source": SOURCE_ID,
        "vintage": row.added_to_state_list or export.vintage,
        "reconstructed_rate": None,
        "reconstructs_its_own_published_rate": row.reconstructs_published_rate,
    }
    if published_rate is None:
        # Nothing on the page for a denominator to sit under. Not a failure of the bulk row,
        # and counting it as one would report the API's own suppression as this file's.
        return {**common, "state": STATE_RATE_NOT_PUBLISHED}
    if row.employed_q2 is None or row.denominator_q2 is None:
        return {**common, "state": STATE_BULK_FIGURES_SUPPRESSED}
    if not reconstructs(row.employed_q2, row.denominator_q2, published_rate):
        return {**common, "state": STATE_DOES_NOT_RECONSTRUCT}
    return {
        **common,
        "state": STATE_SHOWN,
        "denominator": row.denominator_q2,
        "reconstructed_rate": row.employed_q2 / row.denominator_q2,
    }
