"""A flat CSV of the emitted dataset, in which no blank ever carries a meaning.

The site's dataset is sharded JSON, which is right for a page that loads one program and wrong
for the reader most likely to check this project's figures: a journalist or a researcher with a
spreadsheet. This module writes that dataset as one table, beside a Frictionless Table Schema
generated from the same column definitions in the same pass, so the two cannot drift.

It writes a Frictionless **Data Package** around the pair: ``datapackage.json``, plus the three
emitted JSON files copied in beside the table, so every path in the descriptor resolves inside
the directory a reader downloaded. A descriptor that named ``programs.json`` and left it in the
site's public directory would resolve for whoever built it and for nobody else -- a broken
package that reads as a complete one. :func:`data_package_problems` reads the written
descriptor back against the files on disk and is what the export refuses on.

The whole design is one rule. **Every measure carries a state word beside it, and the state word
is never blank.** A value cell is empty only where the state cell says why it is empty. An empty
cell on its own means nothing, and a reader who does not know that is one `fillna(0)` away from
publishing that a training programme placed nobody in work.

The state vocabulary is three words, and the missing fourth is the interesting one.

``reported``
    A number the source filed, present in the value column beside it.

``not_reported``
    No number. This is the ETP scorecard's ``-1`` and its empty string, which
    :func:`afterward.sources.dol_etp.clean_measure` maps to ``None``.

``competency_based``
    Only on ``length_weeks`` and ``length_hours``, and only from ``length.competency_based``.
    The ETP data dictionary attaches ``-1`` to those two elements and to no others with a
    different meaning: the programme advances on demonstrated competency, so it has no fixed
    length. That is a positive fact about the programme, not missing data, and reporting it as
    missing would report a deliberate design decision as a gap.

**There is deliberately no ``suppressed``**, and issue #110 asked for one. The reason is that this
dataset cannot honestly produce it. WIOA does suppress small-cohort cells, and that suppression is
the reason a great many of these measures are absent -- but the ETP scorecard serves a suppressed
cell and an unreported cell as the same ``-1``, and its own data dictionary describes the sentinel
as "not reported or suppressed" without distinguishing them. By the time a measure reaches the
emitted record, the cause is gone. Writing ``suppressed`` into a cell whose cause is unknown would
be this project's own headline failure mode wearing its opposite face: not an absence published as
a number, but an absence published as a specific, defensible-sounding cause nobody measured.
``not_reported`` is what the dataset knows, so ``not_reported`` is what it says. If the source ever
separates the two, the vocabulary can grow; guessing now would put a claim in a CSV that no line
of this codebase could defend.

Determinism: rows are sorted by ``uuid``, so the same snapshot produces byte-identical output
whatever order the build emitted in.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

__all__ = [
    "COLUMNS",
    "DATA_PACKAGE_FILENAME",
    "JSON_RESOURCES",
    "SCHEMA_FILENAME",
    "STATES",
    "TABLE_FILENAME",
    "Column",
    "ExportReport",
    "data_package_problems",
    "export_csv",
    "state_column_problems",
    "to_csv",
    "to_data_package",
    "to_table_schema",
]

TABLE_FILENAME: Final = "programs.csv"
SCHEMA_FILENAME: Final = "programs.schema.json"
DATA_PACKAGE_FILENAME: Final = "datapackage.json"

STATE_SUFFIX: Final = "_state"

REPORTED: Final = "reported"
NOT_REPORTED: Final = "not_reported"
COMPETENCY_BASED: Final = "competency_based"

STATES: Final[tuple[str, ...]] = (REPORTED, NOT_REPORTED, COMPETENCY_BASED)
"""Every word a state column may carry. A reader may check against this and find no sixth."""

FieldKind = Literal["string", "number", "integer", "boolean"]


@dataclass(frozen=True, slots=True)
class Column:
    """One column of the flat table, and how to get its value out of a program record."""

    name: str
    kind: FieldKind
    description: str
    path: tuple[str, ...]
    """Dotted path into the program record, as a tuple of keys."""

    measured: bool = False
    """Whether this column carries a measure, and therefore gets a state column beside it.

    A measure is a number the source may or may not have filed. Identity, location and the
    provider's own text are not measures: a blank provider city is a blank provider city, and
    inventing a state word for it would say that somebody declined to report it.
    """


def _identity(name: str, kind: FieldKind, description: str, *path: str) -> Column:
    return Column(name=name, kind=kind, description=description, path=path)


def _measure(name: str, kind: FieldKind, description: str, *path: str) -> Column:
    return Column(name=name, kind=kind, description=description, path=path, measured=True)


# The table, in column order. Identity first, then the provider's own description of the
# programme, then the three families a reader compares on: cost, length, outcomes. Everything
# derived rather than filed -- the occupation join, the link verdict -- comes last, so that a
# reader scrolling right meets this project's own work only after the source's.
COLUMNS: Final[tuple[Column, ...]] = (
    _identity("uuid", "string", "Stable record id, as filed by the ETP scorecard.", "uuid"),
    _identity("provider_name", "string", "Training provider, as filed.", "provider_name"),
    _identity("program_name", "string", "Programme title, as filed.", "program_name"),
    _identity("entity_type", "string", "Provider's own entity type, as filed.", "entity_type"),
    _identity("cip_code", "string", "CIP code the provider filed for this programme.", "cip_code"),
    _identity(
        "program_format",
        "string",
        "The provider's own sentence about delivery mode, quoted rather than categorised.",
        "program_format",
    ),
    _identity("program_url", "string", "Programme page as filed by the provider.", "program_url"),
    _identity("city", "string", "Programme city.", "location", "city"),
    _identity("state", "string", "Programme state.", "location", "state"),
    _identity("zip", "string", "Programme postal code.", "location", "zip"),
    _identity(
        "area_name",
        "string",
        "EDD projection area this programme was placed in, or empty if it was placed in none.",
        "region",
        "area_name",
    ),
    _identity(
        "area_matched_on",
        "string",
        "How the area was decided. Empty where no area was matched.",
        "region",
        "matched_on",
    ),
    _measure("cost_tuition", "number", "Tuition in dollars, as filed.", "cost", "tuition"),
    _measure("cost_supplies", "number", "Supplies in dollars, as filed.", "cost", "supplies"),
    _measure(
        "cost_total_out_of_pocket",
        "number",
        (
            "Total out-of-pocket cost in dollars. Read this with cost_total_is_complete: where "
            "that is false a component was not reported, so the total is a floor and not a price."
        ),
        "cost",
        "total_out_of_pocket",
    ),
    _identity(
        "cost_total_is_complete",
        "boolean",
        (
            "Whether every component of the total was reported. False makes the total a floor. "
            "Not a measure: it is this project's statement about the cost figures, always known."
        ),
        "cost",
        "total_is_complete",
    ),
    _measure(
        "cost_wioa_funded",
        "number",
        "Cost covered by WIOA funding, in dollars, as filed.",
        "cost",
        "wioa_funded_cost",
    ),
    _measure(
        "length_weeks",
        "number",
        (
            "Programme length in weeks. State competency_based means the programme advances on "
            "demonstrated competency and has no fixed length; it is not missing data."
        ),
        "length",
        "weeks",
    ),
    _measure(
        "length_hours",
        "number",
        "Programme length in instructional hours. See length_weeks on competency_based.",
        "length",
        "hours",
    ),
    _identity(
        "outcomes_reported",
        "boolean",
        (
            "Whether the source filed any outcome data for this programme at all. Where false, "
            "every outcome measure below states not_reported."
        ),
        "outcomes",
        "reported",
    ),
    _measure("total_served", "number", "Participants served.", "outcomes", "total_served"),
    _measure("total_exited", "number", "Participants who exited.", "outcomes", "total_exited"),
    _measure(
        "total_completed", "number", "Participants who completed.", "outcomes", "total_completed"
    ),
    _measure(
        "completion_rate",
        "number",
        "Completion rate, 0 to 1 as filed.",
        "outcomes",
        "completion_rate",
    ),
    _measure(
        "credentials_earned",
        "number",
        "Credentials earned by participants.",
        "outcomes",
        "credentials_earned",
    ),
    _measure(
        "median_earnings",
        "number",
        "Median quarterly earnings after exit, in dollars, as filed.",
        "outcomes",
        "median_earnings",
    ),
    _measure(
        "employment_rate_q2",
        "number",
        "Employment rate in the second quarter after exit, 0 to 1 as filed.",
        "outcomes",
        "employment_rate_q2",
    ),
    _measure(
        "employed_q2",
        "number",
        "Participants employed in the second quarter after exit.",
        "outcomes",
        "employed_q2",
    ),
    _measure(
        "employed_q4",
        "number",
        "Participants employed in the fourth quarter after exit.",
        "outcomes",
        "employed_q4",
    ),
    _identity(
        "soc_codes",
        "string",
        "SOC codes the provider filed, space separated. Empty where the provider filed none.",
        "soc_codes",
    ),
    _identity(
        "occupation_match_kind",
        "string",
        (
            "How this project joined the programme to an occupation, for the first occupation "
            "listed. Empty where no occupation was joined. This project's work, not the source's."
        ),
        "occupations",
        "0",
        "match",
        "kind",
    ),
    _identity(
        "occupation_soc_code",
        "string",
        "SOC code of the first joined occupation. Empty where none was joined.",
        "occupations",
        "0",
        "soc_code",
    ),
    _identity(
        "occupation_title",
        "string",
        "EDD title of the first joined occupation. Empty where none was joined.",
        "occupations",
        "0",
        "title",
    ),
    _identity(
        "provider_link_verdict",
        "string",
        (
            "What this project's link checker found at the filed URL. Empty where no verdict "
            "was reached, which is not the same as a working link."
        ),
        "provider_link",
        "verdict",
    ),
)

_MEASURES: Final[tuple[Column, ...]] = tuple(c for c in COLUMNS if c.measured)
_LENGTH_MEASURES: Final[frozenset[str]] = frozenset({"length_weeks", "length_hours"})


def header() -> list[str]:
    """Column names in order, each measure immediately followed by its state column."""
    names: list[str] = []
    for column in COLUMNS:
        names.append(column.name)
        if column.measured:
            names.append(column.name + STATE_SUFFIX)
    return names


def _at(record: Mapping[str, Any], path: Sequence[str]) -> object:
    """Follow a dotted path, returning ``None`` rather than raising on any break in it.

    A numeric segment indexes a list. A missing key, a short list or a null on the way down all
    return ``None``, which the caller renders as an absence with a state word beside it -- never
    as a zero, and never as a crash that would lose the other 3,000 rows.
    """
    current: object = record
    for key in path:
        if key.isdigit():
            if not isinstance(current, list) or len(current) <= int(key):
                return None
            current = current[int(key)]
            continue
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _render(value: object) -> str:
    """One cell, with no coercion that could invent a number.

    ``None`` becomes the empty string and nothing else does. Booleans are written as ``true`` and
    ``false`` rather than Python's capitalised forms, so the file reads the same as the JSON it
    came from.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (list, tuple)):
        return " ".join(str(item) for item in value)
    return str(value)


def state_of(record: Mapping[str, Any], column: Column) -> str:
    """The state word for one measure in one record. Never empty, and never guessed.

    ``competency_based`` reaches only the two length columns, and only from the record's own
    ``length.competency_based`` flag. Everything else absent is ``not_reported``: see the module
    docstring on why ``suppressed`` is not a word this dataset may write.
    """
    if column.name in _LENGTH_MEASURES:
        length = record.get("length")
        if isinstance(length, Mapping) and length.get("competency_based") is True:
            return COMPETENCY_BASED
    return REPORTED if _at(record, column.path) is not None else NOT_REPORTED


def _row(record: Mapping[str, Any]) -> dict[str, str]:
    row: dict[str, str] = {}
    for column in COLUMNS:
        value = _at(record, column.path)
        row[column.name] = _render(value)
        if column.measured:
            state = state_of(record, column)
            row[column.name + STATE_SUFFIX] = state
            if state != REPORTED:
                # A competency-based programme may still carry a length the source filed by
                # accident; the state is the claim, so the value column is cleared to agree
                # with it rather than leaving two cells that say different things.
                row[column.name] = ""
    return row


def to_csv(programs: Sequence[Mapping[str, Any]]) -> str:
    """The flat table for these programs, sorted by ``uuid`` so the bytes are reproducible."""
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=header(), lineterminator="\n")
    writer.writeheader()
    for record in sorted(programs, key=lambda p: str(p.get("uuid", ""))):
        writer.writerow(_row(record))
    return buffer.getvalue()


def to_table_schema(snapshot_date: str, *, path: str = TABLE_FILENAME) -> dict[str, Any]:
    """A Frictionless Table Schema for exactly the columns :func:`to_csv` writes.

    Generated from :data:`COLUMNS` in the same pass as the table, so a column cannot appear in
    one and not the other. Every state column is constrained to :data:`STATES`, which is how a
    validator, rather than a reader's goodwill, enforces that there is no sixth word.
    """
    fields: list[dict[str, Any]] = []
    for column in COLUMNS:
        fields.append(
            {
                "name": column.name,
                "type": column.kind,
                "description": column.description,
            }
        )
        if column.measured:
            fields.append(
                {
                    "name": column.name + STATE_SUFFIX,
                    "type": "string",
                    "description": (
                        f"How {column.name} is present or absent. Never empty. A blank "
                        f"{column.name} is explained here and nowhere else."
                    ),
                    "constraints": {"required": True, "enum": list(STATES)},
                }
            )
    return {
        "$schema": "https://datapackage.org/profiles/2.0/tableschema.json",
        "name": "programs",
        "title": f"California ETPL programs, snapshot {snapshot_date}",
        "description": (
            "One row per state-listed training programme. Every measure carries a state word "
            "beside it and the state word is never empty; a value cell is empty only where the "
            "state cell says why. The vocabulary is reported, not_reported and competency_based. "
            "There is no 'suppressed': the ETP scorecard serves a suppressed cell and an "
            "unreported cell as the same -1, so the cause is not in this data and this file does "
            "not invent one."
        ),
        "path": path,
        "profile": "tabular-data-resource",
        "fields": fields,
        "missingValues": [""],
    }


#: The emitted JSON files a data package copies beside the table, with the sentence each
#: gets in the descriptor. The site serves these; a reader who wants the joins rather than
#: the flat table needs them, and a descriptor that names a file it did not bring is a
#: descriptor whose paths do not resolve.
JSON_RESOURCES: Final[tuple[tuple[str, str], ...]] = (
    (
        "programs.json",
        (
            "Every programme as the site serves it, with the nested cost, length, outcome and "
            "occupation-join objects the flat table flattens away."
        ),
    ),
    (
        "occupations.json",
        (
            "Every occupation the programmes above feed, with its wages, its ten-year "
            "projection and the SOC vintage each figure was published under."
        ),
    ),
    (
        "coverage.json",
        (
            "This snapshot's account of itself: how many programmes reported each measure, how "
            "many were placed in a region and by which rule, and what was left unplaced. Read "
            "this before quoting any figure from the other two."
        ),
    ),
)


def to_data_package(
    snapshot_date: str, *, resources: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """A Frictionless Data Package descriptor for one snapshot's published files.

    ``resources`` is the measured half — one mapping per file, carrying at least ``name``,
    ``path``, ``bytes`` and ``hash``. It is passed in rather than read here so that the
    descriptor is a pure function of its inputs and the writer is the only thing that
    touches a filesystem: a descriptor that measured the files itself could not be tested
    against a file set it did not create.

    No clock is consulted. ``version`` is the snapshot date, which is the identity that
    matters for this dataset — the same snapshot must produce byte-identical output, so a
    ``created`` timestamp would make every export differ from the last for no reason a
    reader could use. That is also why the releases are date-tagged rather than semver
    (``docs/adr/0001-release-and-versioning-na.md``).
    """
    return {
        "$schema": "https://datapackage.org/profiles/2.0/datapackage.json",
        "name": f"afterward-california-training-programs-{snapshot_date}",
        "title": f"Afterward: California training programmes, snapshot {snapshot_date}",
        "description": (
            "Every California training programme reported under WIOA, its outcomes as the "
            "state filed them, and the occupations it leads to. Absence is never a number "
            "here: an outcome the source did not file is absent in the value column and "
            "explained in the state column beside it, and coverage.json states how much of "
            "each measure is present. A blank is not a zero."
        ),
        "version": snapshot_date,
        "homepage": "https://afterward.chelseakr.com",
        "licenses": [
            {
                "name": "Apache-2.0",
                "path": "https://www.apache.org/licenses/LICENSE-2.0",
                "title": (
                    "Apache License 2.0 — covers the joins, derivations and column "
                    "definitions this project contributes."
                ),
            }
        ],
        "sources": [
            {
                "title": (
                    "U.S. Department of Labor, Training Provider Results (ETP scorecard) — "
                    "the programmes, their costs, lengths and outcome measures"
                ),
                "path": "https://www.trainingproviderresults.gov/",
            },
            {
                "title": (
                    "California EDD Labor Market Information Division — the ten-year "
                    "occupational projections and the projection areas"
                ),
                "path": "https://labormarketinfo.edd.ca.gov/",
            },
            {
                "title": (
                    "U.S. Bureau of Labor Statistics, Occupational Employment and Wage Statistics"
                ),
                "path": "https://www.bls.gov/oes/",
            },
            {
                "title": (
                    "O*NET — occupation titles, including the Spanish titles from Mi Proximo Paso"
                ),
                "path": "https://www.onetcenter.org/",
            },
        ],
        "contributors": [{"title": "Afterward contributors", "role": "author"}],
        "keywords": [
            "california",
            "workforce",
            "wioa",
            "training-programs",
            "labor-market",
            "open-data",
        ],
        # Both sentences a reader needs before quoting anything out of this package, in the
        # package itself rather than only in a README they may never have downloaded. The
        # reporting-obligation record they point at is PROVENANCE.md I7-I11.
        "citation": [
            {
                "text": (
                    "Kelly-Reif, C. Afterward: California training programs, their reported "
                    f"outcomes, and where they lead. Snapshot {snapshot_date}. "
                    "https://github.com/ChelseaKR/afterward"
                ),
                "path": "https://github.com/ChelseaKR/afterward/blob/main/CITATION.cff",
            }
        ],
        "afterward:provenance": {
            "path": "https://github.com/ChelseaKR/afterward/blob/main/PROVENANCE.md",
            "sourceData": (
                "Source data is U.S. Government work (public domain) and California open "
                "data; per-source terms are recorded in PROVENANCE.md."
            ),
            "reportingObligations": (
                "Which providers must report performance, and which are exempt, is recorded "
                "in PROVENANCE.md I7-I11 with the primary texts: 20 CFR 677.230, 680.450, "
                "680.470 and 680.490; WIOA sec. 116(d)(4) and 116(d)(6)(C); the ETP Data "
                "Dictionary v4.0; and California EDD directive WSD25-02. Registered "
                "apprenticeship is the only category exempt from ETP performance reporting. "
                "A community college's blank row is not an exemption being used."
            ),
            "suppression": (
                "WIOA suppresses small-cohort cells, and the ETP scorecard serves a "
                "suppressed cell and an unreported cell as the same -1. By the time a "
                "measure reaches this package the cause is gone, so the state vocabulary "
                "carries no 'suppressed' word: naming one would be a claim nothing here "
                "measured. WIOA sec. 116(d)(6)(C) states a standard, not a numeric "
                "threshold, and no minimum cell size is published, so none is stated."
            ),
        },
        "resources": list(resources),
    }


def data_package_problems(descriptor: Mapping[str, Any], root: Path) -> list[str]:
    """Read a written descriptor back and report every resource it cannot account for.

    Deliberately reads the files from disk rather than the values the writer held in
    memory. A check that re-derives its expectation from the function that produced the
    answer compares a value to itself; this asks what a downloader would find.
    """
    problems: list[str] = []
    resources = descriptor.get("resources")
    if not isinstance(resources, list) or not resources:
        return ["the descriptor declares no resources, so it describes nothing"]
    for resource in resources:
        name = resource.get("name", "<unnamed>")
        path = resource.get("path")
        if not isinstance(path, str):
            problems.append(f"{name}: no path")
            continue
        target = root / path
        if not target.is_file():
            problems.append(f"{name}: declares {path!r}, which is not in the package")
            continue
        payload = target.read_bytes()
        if resource.get("bytes") != len(payload):
            problems.append(
                f"{name}: declares {resource.get('bytes')} bytes, {path!r} is {len(payload)}"
            )
        expected = f"sha256:{hashlib.sha256(payload).hexdigest()}"
        if resource.get("hash") != expected:
            problems.append(f"{name}: declared hash does not match {path!r}")
    return problems


def _resource(path: Path, *, name: str, description: str, **extra: Any) -> dict[str, Any]:
    """One descriptor entry, measured from the bytes actually written."""
    payload = path.read_bytes()
    entry: dict[str, Any] = {
        "name": name,
        "path": path.name,
        "description": description,
        "bytes": len(payload),
        "hash": f"sha256:{hashlib.sha256(payload).hexdigest()}",
    }
    entry.update(extra)
    return entry


def state_column_problems(text: str) -> list[str]:
    """Read a rendered table back and report every way it breaks the one rule.

    Deliberately parses the CSV text rather than inspecting the records it came from. A check
    that re-derives its expectation from the same function that produced the answer compares a
    value to itself and cannot fail; this reads the bytes a downloader would read.
    """
    problems: list[str] = []
    reader = csv.DictReader(io.StringIO(text))
    names = reader.fieldnames or []
    expected = header()
    if names != expected:
        return [f"header is {names}, expected {expected}"]

    state_names = [c.name + STATE_SUFFIX for c in _MEASURES]
    for line, row in enumerate(reader, start=2):
        for column in _MEASURES:
            state = row[column.name + STATE_SUFFIX]
            value = row[column.name]
            if state == "":
                problems.append(f"row {line}: {column.name + STATE_SUFFIX} is empty")
            elif state not in STATES:
                problems.append(f"row {line}: {column.name + STATE_SUFFIX} is {state!r}")
            elif state == REPORTED and value == "":
                problems.append(f"row {line}: {column.name} is blank but states {REPORTED}")
            elif state != REPORTED and value != "":
                problems.append(f"row {line}: {column.name} carries {value!r} but states {state}")
            if state == COMPETENCY_BASED and column.name not in _LENGTH_MEASURES:
                problems.append(
                    f"row {line}: {column.name} states {COMPETENCY_BASED}, which belongs only to "
                    "the two length columns"
                )
    if not state_names:  # pragma: no cover - a table with no measures has no rule to break
        problems.append("the table declares no measure columns, so its one rule checks nothing")
    return problems


def check_states(text: str) -> None:
    """Raise if a rendered table breaks the one rule this module exists to keep."""
    problems = state_column_problems(text)
    if problems:
        shown = "\n  ".join(problems[:20])
        raise ValueError(
            f"the exported table breaks its own absence rule ({len(problems)} problems):\n  {shown}"
        )


@dataclass(frozen=True, slots=True)
class ExportReport:
    """What one export wrote, for the command line to print."""

    snapshot_date: str
    rows: int
    columns: int
    measures: int
    table_path: Path
    schema_path: Path
    package_path: Path
    resources: tuple[str, ...]
    """Every file the descriptor declares, in descriptor order."""

    states: Mapping[str, int]
    """How many cells reached each state word, across every measure column."""


def export_csv(dataset_dir: Path, output_dir: Path) -> ExportReport:
    """Write the flat table, its Table Schema, and a Data Package around both.

    Reads the same ``programs.json`` the site serves, so the export cannot disagree with the
    site about what the data says. The rule is checked against the rendered bytes before
    anything is written: a failed check leaves no partial file to mistake for a good one.

    ``output_dir`` ends up a **complete** Frictionless Data Package: the table, its schema,
    the three emitted JSON files copied in beside it, and ``datapackage.json`` declaring
    every one with its size and sha256. The copies are the point. A descriptor that named
    ``programs.json`` while leaving it in ``web/public/data`` would have a path that
    resolves for whoever built it and for nobody who downloaded it, which is a broken
    package that reads as a complete one.

    Nothing is written into ``dataset_dir``: the bytes the site serves are untouched, and
    the descriptor is written last, after every file it measures exists.
    """
    missing = [name for name, _ in JSON_RESOURCES if not (dataset_dir / name).is_file()]
    if missing:
        raise ValueError(
            f"{dataset_dir} is missing {', '.join(missing)}, so a complete data package "
            "cannot be written from it. Run `make data` (or `make data-offline`) first."
        )

    dataset = json.loads((dataset_dir / "programs.json").read_text(encoding="utf-8"))
    coverage = json.loads((dataset_dir / "coverage.json").read_text(encoding="utf-8"))
    programs: list[dict[str, Any]] = dataset["programs"]
    snapshot_date = str(coverage["snapshot_date"])

    text = to_csv(programs)
    check_states(text)
    schema = to_table_schema(snapshot_date)

    output_dir.mkdir(parents=True, exist_ok=True)
    table_path = output_dir / TABLE_FILENAME
    schema_path = output_dir / SCHEMA_FILENAME
    table_path.write_text(text, encoding="utf-8", newline="")
    schema_path.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    resources = [
        _resource(
            table_path,
            name="programs",
            description=(
                "One row per programme. Every measure carries a state word beside it and the "
                "state word is never blank: a value cell is empty only where the state cell "
                "says why."
            ),
            profile="tabular-data-resource",
            mediatype="text/csv",
            encoding="utf-8",
            # `to_csv` passes `lineterminator="\n"` explicitly, against csv's `\r\n`
            # default, so the descriptor has to say so or a strict reader parses a
            # trailing `\r` into the last column of every row.
            dialect={"delimiter": ",", "lineTerminator": "\n", "header": True},
            schema=schema,
        )
    ]
    for filename, description in JSON_RESOURCES:
        copied = output_dir / filename
        shutil.copyfile(dataset_dir / filename, copied)
        resources.append(
            _resource(
                copied,
                name=filename.removesuffix(".json") + "-json",
                description=description,
                mediatype="application/json",
                encoding="utf-8",
            )
        )

    package = to_data_package(snapshot_date, resources=resources)
    package_path = output_dir / DATA_PACKAGE_FILENAME
    package_path.write_text(
        json.dumps(package, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    # Read the descriptor back off disk rather than checking the dict still in hand: the
    # claim is about the package a reader downloads, and a truncated or unreadable
    # `datapackage.json` is invisible to the variable it was serialized from.
    #
    # This cannot catch a *missing* resource, and that is worth saying rather than implying:
    # `_resource` measures each file's bytes to build its entry, so a file the writer did
    # not bring raises there first, before any entry naming it exists. Measured -- deleting
    # the `copyfile` above fails at `_resource` with `FileNotFoundError`, not here. The
    # guard against that is the up-front refusal at the top of this function.
    written = json.loads(package_path.read_text(encoding="utf-8"))
    problems = data_package_problems(written, output_dir)
    if problems:  # pragma: no cover - reachable only by a failed write, not by a bad build
        raise ValueError(
            "the data package does not describe what was written:\n  " + "\n  ".join(problems)
        )

    counts = dict.fromkeys(STATES, 0)
    for record in programs:
        for column in _MEASURES:
            counts[state_of(record, column)] += 1

    return ExportReport(
        snapshot_date=snapshot_date,
        rows=len(programs),
        columns=len(header()),
        measures=len(_MEASURES),
        table_path=table_path,
        schema_path=schema_path,
        package_path=package_path,
        resources=tuple(str(entry["path"]) for entry in resources),
        states=counts,
    )
