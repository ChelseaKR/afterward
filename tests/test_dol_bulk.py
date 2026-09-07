"""The bulk export is read beside the API, and every way it could mislead is refused.

The claim this module makes on a reader's behalf is narrow and easy to overstate:
``d123_total_employed_q2 / de129`` reproduces the bulk file's own published rate on every
California row that carries all three -- 1,782 of 1,782 measured on 2026-09-07. That is a
fact about the bulk file's internal consistency. It is **not** a licence to put that
denominator under the rate this site publishes, which comes from a different file on a
different vintage; measured against the 3,266-program dataset, 839 programs have a bulk row
whose arithmetic reproduces the bulk file's own older rate and not the site's.

So the tests below are mostly about refusals.

The XLSX fixtures are written here rather than committed. A 36 MB binary in the repository
would be unreadable in review, and a small hand-written one exercises the reader against
bytes a test can state in full -- including the shapes the real file does not have
(inline strings, a DOCTYPE, a missing column) and must still be refused correctly.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

import pytest

from afterward.build import (
    _attach_bulk_denominator,
    denominator_coverage,
    denominator_integrity_problems,
)
from afterward.sources import dol_bulk

HEADER = [
    "d101_eligible_training_provider",
    "d105_program_name",
    "d110_cip_code",
    "zip",
    "reportingstate",
    "d123_total_employed_q2",
    "c_q2_employment_percent",
    "de129",
    "de130",
    "de170",
    "de171",
    "de172",
]


def _column_name(index: int) -> str:
    name = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _sheet_xml(rows: list[list[str]], *, inline: bool = False) -> bytes:
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
        "<sheetData>",
    ]
    for row_number, row in enumerate(rows, start=1):
        parts.append(f'<row r="{row_number}">')
        for column, value in enumerate(row):
            reference = f"{_column_name(column)}{row_number}"
            if value == "":
                parts.append(f'<c r="{reference}"/>')
            elif inline:
                parts.append(f'<c r="{reference}" t="inlineStr"><is><t>{value}</t></is></c>')
            else:
                parts.append(f'<c r="{reference}" t="str"><v>{value}</v></c>')
        parts.append("</row>")
    parts.append("</sheetData></worksheet>")
    return "".join(parts).encode("utf-8")


def write_workbook(
    path: Path,
    rows: list[list[str]],
    *,
    inline: bool = False,
    sheet_target: str = "worksheets/sheet1.xml",
    doctype_in: str | None = None,
) -> Path:
    """A minimal but real ``.xlsx``: workbook, relationships, one sheet.

    ``sheet_target`` moves the worksheet so the relationship-resolving path is exercised
    rather than the ``xl/worksheets/sheet1.xml`` guess.
    """
    workbook = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Programs" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Id="rId1" Target="{sheet_target}"'
        ' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"'
        "/></Relationships>"
    )
    members = {
        "xl/workbook.xml": workbook.encode("utf-8"),
        "xl/_rels/workbook.xml.rels": rels.encode("utf-8"),
        f"xl/{sheet_target}": _sheet_xml(rows, inline=inline),
    }
    if doctype_in is not None:
        payload = members[doctype_in]
        members[doctype_in] = payload.replace(
            b"?>", b'?><!DOCTYPE lolz [ <!ENTITY lol "lol"> ]>', 1
        )
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return path


def row(
    provider: str = "Example College",
    program: str = "Welding Certificate",
    cip: str = "48.0508",
    postal: str = "90001",
    state: str = "CA",
    employed: str = "35",
    rate: str = "0.7",
    de129: str = "50",
    de172: str = "45473",
) -> list[str]:
    return [provider, program, cip, postal, state, employed, rate, de129, "-1", "-1", "-1", de172]


@pytest.fixture
def workbook(tmp_path: Path) -> Path:
    return write_workbook(tmp_path / "bulk.xlsx", [HEADER, row()])


def test_reads_one_state_and_keys_it_for_the_four_key_join(workbook: Path) -> None:
    export = dol_bulk.read_bulk_export(workbook)
    assert export.rows_read == 1
    assert export.rows_in_state == 1
    assert export.vintage == "2024-06-30"
    assert list(export.by_key) == [("example college", "welding certificate", "48.0508", "90001")]


def test_rows_from_other_states_are_not_read(tmp_path: Path) -> None:
    path = write_workbook(tmp_path / "bulk.xlsx", [HEADER, row(state="TX"), row(state="CA")])
    export = dol_bulk.read_bulk_export(path, state="CA")
    assert export.rows_read == 2
    assert export.rows_in_state == 1


def test_inline_strings_read_the_same_as_shared_ones(tmp_path: Path) -> None:
    """The real export uses a shared-string table; the format permits inline. Both are read."""
    path = write_workbook(tmp_path / "bulk.xlsx", [HEADER, row()], inline=True)
    assert list(dol_bulk.read_bulk_export(path).by_key) == [
        ("example college", "welding certificate", "48.0508", "90001")
    ]


def test_the_worksheet_is_found_through_its_relationship_not_by_guessing_the_path(
    tmp_path: Path,
) -> None:
    path = write_workbook(
        tmp_path / "bulk.xlsx", [HEADER, row()], sheet_target="worksheets/sheet42.xml"
    )
    assert dol_bulk.read_bulk_export(path).rows_in_state == 1


@pytest.mark.parametrize("member", ["xl/workbook.xml", "xl/worksheets/sheet1.xml"])
def test_a_member_declaring_a_doctype_is_refused(tmp_path: Path, member: str) -> None:
    """The one guard standing between this reader and a billion-laughs bomb.

    Measured on this interpreter: `xml.etree.ElementTree` expands internal entities, so a
    ten-level laugh in a spreadsheet part would be expanded before anything looked at a
    column. A DOCTYPE is the only way to declare one, and a spreadsheet part never has one.
    """
    path = write_workbook(tmp_path / "bulk.xlsx", [HEADER, row()], doctype_in=member)
    with pytest.raises(dol_bulk.BulkExportError, match="DOCTYPE"):
        dol_bulk.read_bulk_export(path)


def test_a_member_whose_declared_size_is_implausible_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_workbook(tmp_path / "bulk.xlsx", [HEADER, row()])
    monkeypatch.setattr(dol_bulk, "MAX_MEMBER_BYTES", 10)
    with pytest.raises(dol_bulk.BulkExportError, match="over the"):
        dol_bulk.read_bulk_export(path)


def test_a_member_with_no_document_element_in_its_prologue_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A scan that stops before what it scans for has not scanned.

    The DOCTYPE guard reads a bounded prologue. If the document element has not started
    inside it, a DOCTYPE could still be waiting past the window, so the read is refused
    rather than continued on an unproven assumption.
    """
    path = write_workbook(tmp_path / "bulk.xlsx", [HEADER, row()])
    monkeypatch.setattr(dol_bulk, "PROLOGUE_BYTES", 8)
    with pytest.raises(dol_bulk.BulkExportError, match="no document element"):
        dol_bulk.read_bulk_export(path)


def test_a_missing_column_is_refused_by_name_rather_than_joined_around(tmp_path: Path) -> None:
    header = [name for name in HEADER if name != "de129"]
    path = write_workbook(tmp_path / "bulk.xlsx", [header, row()[:4] + row()[5:]])
    with pytest.raises(dol_bulk.BulkExportError) as error:
        dol_bulk.read_bulk_export(path)
    assert "de129" in str(error.value)
    assert "d101_eligible_training_provider" in str(error.value)


def test_a_file_that_is_not_a_zip_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "bulk.xlsx"
    path.write_text("<html>403 Forbidden</html>", encoding="utf-8")
    with pytest.raises(dol_bulk.BulkExportError, match="not a readable"):
        dol_bulk.read_bulk_export(path)


def test_an_empty_workbook_is_refused_rather_than_read_as_no_rows(tmp_path: Path) -> None:
    path = write_workbook(tmp_path / "bulk.xlsx", [])
    with pytest.raises(dol_bulk.BulkExportError, match="no header row"):
        dol_bulk.read_bulk_export(path)


@pytest.mark.parametrize(
    ("filed", "expected"),
    [
        ("11.020099999999999", "11.0201"),
        ("52.020099999999999", "52.0201"),
        ("15.061299999999999", "15.0613"),
        ("48.0508", "48.0508"),
        ("15.0999", "15.0999"),
        ("46", "46"),
        ("12.05", "12.05"),
        ("", None),
    ],
)
def test_a_cip_widened_by_a_float_round_trip_is_repaired_and_nothing_else_is(
    filed: str, expected: str | None
) -> None:
    """Without this the four-key join found 635 shared keys instead of 2,578.

    A CIP detail is two or four digits and never more, so five or more decimals can only be
    the residue of a double. Every other width the file carries is left exactly as filed: a
    bare series and a four-digit family are widths CIP genuinely publishes, and padding them
    would swap a family for one particular member of it.
    """
    assert dol_bulk.repair_float_cip(filed) == expected


@pytest.mark.parametrize(
    ("filed", "expected"),
    [("45473", "2024-06-30"), ("44213", "2021-01-17"), ("", None), ("0", None), ("n/a", None)],
)
def test_de172_is_published_as_a_date_and_never_as_its_serial(
    filed: str, expected: str | None
) -> None:
    """45473 is not a measurement. It is 2024-06-30 written in Excel's counting."""
    assert dol_bulk.list_date(filed) == expected


@pytest.mark.parametrize(
    ("filed", "expected"),
    [("35", 35.0), ("0", 0.0), ("-1", None), ("", None), ("  ", None), ("n/a", None)],
)
def test_the_minus_one_sentinel_is_an_absence_and_a_zero_is_a_count(
    filed: str, expected: float | None
) -> None:
    assert dol_bulk.measure(filed) == expected


@pytest.mark.parametrize(
    ("provider", "program", "cip", "postal"),
    [
        (None, "Welding", "48.0508", "90001"),
        ("Example College", None, "48.0508", "90001"),
        ("Example College", "Welding", None, "90001"),
        ("Example College", "Welding", "48.0508", None),
    ],
)
def test_a_record_missing_any_part_of_the_key_is_not_keyed_at_all(
    provider: str | None, program: str | None, cip: str | None, postal: str | None
) -> None:
    """Joining on three of four would pair two programs a provider files separately."""
    assert dol_bulk.join_key(provider, program, cip, postal) is None


def test_the_key_folds_case_and_a_zip_plus_four(tmp_path: Path) -> None:
    assert dol_bulk.join_key(
        "EXAMPLE  COLLEGE", "Welding  Certificate", "48.0508", "90001-1234"
    ) == (
        "example college",
        "welding certificate",
        "48.0508",
        "90001",
    )


def test_a_republished_key_is_dropped_rather_than_picked_between(tmp_path: Path) -> None:
    """Attaching one program's denominator to another's rate is worse than showing none."""
    path = write_workbook(
        tmp_path / "bulk.xlsx", [HEADER, row(de129="50"), row(de129="80", employed="56")]
    )
    export = dol_bulk.read_bulk_export(path)
    assert export.by_key == {}
    assert export.ambiguous_keys == 1


def test_a_row_that_cannot_be_keyed_is_counted_and_not_silently_dropped(tmp_path: Path) -> None:
    path = write_workbook(tmp_path / "bulk.xlsx", [HEADER, row(postal="")])
    export = dol_bulk.read_bulk_export(path)
    assert export.by_key == {}
    assert export.unkeyable_rows == 1


@pytest.mark.parametrize(
    ("employed", "denominator", "published", "expected"),
    [
        (35.0, 50.0, 0.7, True),
        (35.0, 50.0, 0.705, True),
        (35.0, 50.0, 0.75, False),
        (35.0, 0.0, 0.7, False),
        (None, 50.0, 0.7, False),
        (35.0, None, 0.7, False),
        (35.0, 50.0, None, False),
    ],
)
def test_a_zero_denominator_does_not_make_a_rate_of_zero(
    employed: float | None, denominator: float | None, published: float | None, expected: bool
) -> None:
    assert dol_bulk.reconstructs(employed, denominator, published) is expected


def _block(export: dol_bulk.BulkExport | None, **overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "provider_name": "Example College",
        "program_name": "Welding Certificate",
        "cip_code": "48.0508",
        "zip_code": "90001",
        "published_rate": 0.7,
    }
    fields.update(overrides)
    return dol_bulk.denominator_block(export, **fields)


def test_a_build_that_read_no_export_says_so_rather_than_saying_no_denominator_exists() -> None:
    block = _block(None)
    assert block["state"] == dol_bulk.STATE_NOT_READ
    assert block["denominator"] is None
    assert block["vintage"] is None
    assert dol_bulk.STATE_NOT_READ not in dol_bulk.DENOMINATOR_STATES


def test_a_reconstructing_row_shows_its_denominator_with_its_own_vintage(workbook: Path) -> None:
    block = _block(dol_bulk.read_bulk_export(workbook))
    assert block["state"] == dol_bulk.STATE_SHOWN
    assert block["denominator"] == 50.0
    assert block["reconstructed_rate"] == pytest.approx(0.7)
    assert block["vintage"] == "2024-06-30"
    assert block["source"] == "D1B"


def test_a_row_that_reproduces_only_its_own_older_rate_shows_nothing(workbook: Path) -> None:
    """The 839. The bulk row's arithmetic is sound and describes a different read.

    Its own `c_q2_employment_percent` is 0.7 and reconstructs exactly; the rate this site
    publishes for the same program is 0.55. Showing 50 as the denominator of 0.55 would put a
    2024 cohort under a 2026 number, and the record says which of the two disagreements it
    met rather than reporting a bare failure.
    """
    block = _block(dol_bulk.read_bulk_export(workbook), published_rate=0.55)
    assert block["state"] == dol_bulk.STATE_DOES_NOT_RECONSTRUCT
    assert block["denominator"] is None
    assert block["reconstructs_its_own_published_rate"] is True


def test_a_row_whose_own_arithmetic_fails_is_distinguished_from_one_that_holds(
    tmp_path: Path,
) -> None:
    path = write_workbook(tmp_path / "bulk.xlsx", [HEADER, row(employed="35", de129="200")])
    block = _block(dol_bulk.read_bulk_export(path))
    assert block["state"] == dol_bulk.STATE_DOES_NOT_RECONSTRUCT
    assert block["reconstructs_its_own_published_rate"] is False


def test_a_program_the_api_publishes_no_rate_for_is_not_a_reconstruction_failure(
    workbook: Path,
) -> None:
    """Counting it as one would report the API's own suppression as the bulk file's."""
    block = _block(dol_bulk.read_bulk_export(workbook), published_rate=None)
    assert block["state"] == dol_bulk.STATE_RATE_NOT_PUBLISHED
    assert block["denominator"] is None


@pytest.mark.parametrize("suppressed", ["employed", "de129"])
def test_a_suppressed_bulk_figure_is_its_own_state(tmp_path: Path, suppressed: str) -> None:
    fields = {"employed": "35", "de129": "50"} | {suppressed: "-1"}
    path = write_workbook(
        tmp_path / "bulk.xlsx",
        [HEADER, row(employed=fields["employed"], de129=fields["de129"])],
    )
    block = _block(dol_bulk.read_bulk_export(path))
    assert block["state"] == dol_bulk.STATE_BULK_FIGURES_SUPPRESSED
    assert block["denominator"] is None


def test_a_program_with_no_bulk_row_says_so(workbook: Path) -> None:
    block = _block(dol_bulk.read_bulk_export(workbook), program_name="Something Else")
    assert block["state"] == dol_bulk.STATE_NO_BULK_ROW
    assert block["vintage"] == "2024-06-30"


def _payload(**outcomes: Any) -> dict[str, Any]:
    return {
        "uuid": "u1",
        "provider_name": "Example College",
        "program_name": "Welding Certificate",
        "cip_code": "48.0508",
        "location": {"zip": "90001"},
        "outcomes": {"employment_rate_q2": 0.7, **outcomes},
    }


def test_coverage_counts_are_null_not_zero_when_no_export_was_read() -> None:
    """The whole reason this is a block. Absent is not a measurement of nothing."""
    payloads = [_payload()]
    _attach_bulk_denominator(payloads, None)
    coverage = denominator_coverage(payloads, None)
    assert coverage.bulk_export_read is False
    assert coverage.programs_total == 1
    assert coverage.programs_with_denominator is None
    assert coverage.programs_with_no_bulk_row is None
    assert coverage.vintage is None


def test_coverage_counts_every_state_from_the_records_a_reader_will_meet(
    tmp_path: Path,
) -> None:
    path = write_workbook(
        tmp_path / "bulk.xlsx",
        [
            HEADER,
            row(),
            row(program="Suppressed Program", de129="-1"),
            row(program="Older Vintage"),
            row(program="No Rate"),
        ],
    )
    export = dol_bulk.read_bulk_export(path)
    payloads = [
        _payload(),
        {**_payload(), "uuid": "u2", "program_name": "Suppressed Program"},
        {
            **_payload(employment_rate_q2=0.55),
            "uuid": "u3",
            "program_name": "Older Vintage",
        },
        {
            **_payload(employment_rate_q2=None),
            "uuid": "u4",
            "program_name": "No Rate",
        },
        {**_payload(), "uuid": "u5", "program_name": "Absent From The Bulk File"},
    ]
    _attach_bulk_denominator(payloads, export)
    coverage = denominator_coverage(payloads, export)
    assert coverage.bulk_export_read is True
    assert coverage.programs_total == 5
    assert coverage.programs_with_denominator == 1
    assert coverage.programs_bulk_figures_suppressed == 1
    assert coverage.programs_bulk_row_does_not_reconstruct == 1
    assert coverage.programs_reconstructing_only_their_own_older_rate == 1
    assert coverage.programs_rate_not_published == 1
    assert coverage.programs_with_no_bulk_row == 1
    assert denominator_integrity_problems(payloads) == []


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda block: block.pop("state"), "is not a state"),
        (lambda block: block.__setitem__("state", "fine"), "is not a state"),
        (
            lambda block: block.__setitem__("state", dol_bulk.STATE_NO_BULK_ROW),
            "carries a denominator it did not show",
        ),
        (lambda block: block.__setitem__("denominator", 0), "must be a positive number"),
        (lambda block: block.__setitem__("reconstructed_rate", None), "must carry its"),
        (lambda block: block.__setitem__("vintage", None), "must name its vintage"),
    ],
)
def test_a_record_whose_denominator_says_more_than_the_build_knows_is_refused(
    workbook: Path, mutate: Any, message: str
) -> None:
    payloads = [_payload()]
    _attach_bulk_denominator(payloads, dol_bulk.read_bulk_export(workbook))
    assert payloads[0]["employment_denominator"]["state"] == dol_bulk.STATE_SHOWN
    mutate(payloads[0]["employment_denominator"])
    problems = denominator_integrity_problems(payloads)
    assert any(message in problem for problem in problems), problems


def test_a_record_with_no_denominator_block_at_all_is_refused() -> None:
    """Absent, a page cannot tell "this build did not look" from "this program has none"."""
    assert denominator_integrity_problems([_payload()]) == ["u1: employment_denominator is absent"]


def _shared_string_workbook(path: Path, rows: list[list[str]], *, shift: int = 0) -> Path:
    """A workbook whose cells point into a shared-string table, as the real export does.

    Every earlier fixture here writes literal cell values, which is a shape the format allows
    and the real file does not use. Without this, the path that actually reads DOL's 191,613
    shared strings was exercised by nothing.

    ``shift`` offsets every index so the out-of-range branch can be reached without hand-
    writing XML: the table is real and the references point past its end.
    """
    table: list[str] = []
    lookup: dict[str, int] = {}
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
        "<sheetData>",
    ]
    for row_number, values in enumerate(rows, start=1):
        parts.append(f'<row r="{row_number}">')
        for column, value in enumerate(values):
            if value not in lookup:
                lookup[value] = len(table)
                table.append(value)
            reference = f"{_column_name(column)}{row_number}"
            parts.append(f'<c r="{reference}" t="s"><v>{lookup[value] + shift}</v></c>')
        parts.append("</row>")
    parts.append("</sheetData></worksheet>")

    shared = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        + "".join(f"<si><t>{value}</t></si>" for value in table)
        + "</sst>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Programs" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Target="worksheets/sheet1.xml"'
        ' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"'
        "/></Relationships>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr("xl/sharedStrings.xml", shared)
        archive.writestr("xl/worksheets/sheet1.xml", "".join(parts))
    return path


def test_a_shared_string_table_is_read_the_way_the_real_export_writes_one(
    tmp_path: Path,
) -> None:
    path = _shared_string_workbook(tmp_path / "bulk.xlsx", [HEADER, row()])
    export = dol_bulk.read_bulk_export(path)
    assert list(export.by_key) == [("example college", "welding certificate", "48.0508", "90001")]
    assert export.by_key[next(iter(export.by_key))].denominator_q2 == 50.0


def test_a_shared_string_index_past_the_table_is_refused(tmp_path: Path) -> None:
    path = _shared_string_workbook(tmp_path / "bulk.xlsx", [HEADER, row()], shift=1000)
    with pytest.raises(dol_bulk.BulkExportError, match="outside the table"):
        dol_bulk.read_bulk_export(path)


def _bare_workbook(path: Path, workbook: str, rels: str) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr("xl/worksheets/sheet1.xml", _sheet_xml([HEADER, row()]))
    return path


def test_a_workbook_declaring_no_worksheet_is_refused(tmp_path: Path) -> None:
    path = _bare_workbook(
        tmp_path / "bulk.xlsx",
        '<?xml version="1.0"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheets/></workbook>",
        '<?xml version="1.0"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>',
    )
    with pytest.raises(dol_bulk.BulkExportError, match="declares no worksheet"):
        dol_bulk.read_bulk_export(path)


def test_a_sheet_whose_relationship_resolves_to_nothing_is_refused(tmp_path: Path) -> None:
    path = _bare_workbook(
        tmp_path / "bulk.xlsx",
        '<?xml version="1.0"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Programs" r:id="rId9"/></sheets></workbook>',
        '<?xml version="1.0"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>',
    )
    with pytest.raises(dol_bulk.BulkExportError, match="names no worksheet"):
        dol_bulk.read_bulk_export(path)


def test_a_workbook_missing_a_member_this_reader_opens_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "bulk.xlsx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", _sheet_xml([HEADER, row()]))
    with pytest.raises(dol_bulk.BulkExportError, match="has no member"):
        dol_bulk.read_bulk_export(path)
