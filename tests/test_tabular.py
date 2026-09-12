"""The flat CSV export, and the one rule it exists to keep.

The rule is that no blank ever carries a meaning: every measure has a state word beside it, the
state word is never empty, and a value cell is empty only where the state cell says why. Almost
every assertion below is a form of "the state agrees with the value", and so is the result of an
export that did nothing at all. So the sabotage cases here introduce a fault, read the rendered
file back to prove the fault is in it, and only then assert what changed. A control that silently
fails to apply reads as a pass.

The other thing held here is the absent fourth state. Issue #110 asked for `suppressed` and this
export does not write it, because the ETP scorecard serves a suppressed cell and an unreported
cell as the same `-1` and the cause is gone before the record is emitted. Naming it would be an
absence published as a specific cause nobody measured, which is the project's own headline defect
wearing its opposite face. `TestTheAbsentFourthState` is where that decision is pinned so it
cannot be undone by accident.
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from afterward import tabular
from afterward.cli import app

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "fixtures" / "data"


@pytest.fixture(scope="module")
def programs() -> list[dict[str, Any]]:
    document = json.loads((FIXTURE_DIR / "programs.json").read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = document["programs"]
    return records


@pytest.fixture(scope="module")
def table(programs: list[dict[str, Any]]) -> str:
    return tabular.to_csv(programs)


@pytest.fixture(scope="module")
def rows(table: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(table)))


def _record(uuid: str, **overrides: Any) -> dict[str, Any]:
    """A minimal program record, with the three families every measure lives in."""
    base: dict[str, Any] = {
        "uuid": uuid,
        "provider_name": "A Provider",
        "program_name": "A Program",
        "location": {"city": "Fresno", "state": "CA", "zip": "93701"},
        "cost": {
            "tuition": 100.0,
            "supplies": 0.0,
            "total_out_of_pocket": 100.0,
            "total_is_complete": True,
            "wioa_funded_cost": 0.0,
        },
        "length": {"weeks": 12.0, "hours": 400.0, "competency_based": False},
        "outcomes": {
            "total_served": 10.0,
            "total_exited": 9.0,
            "total_completed": 8.0,
            "completion_rate": 0.8,
            "credentials_earned": 8.0,
            "median_earnings": 9000.0,
            "employment_rate_q2": 0.7,
            "employed_q2": 7.0,
            "employed_q4": 6.0,
            "reported": True,
        },
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = {**base[key], **value}
        else:
            base[key] = value
    return base


def _minimal_dataset(source: Path, *, records: list[dict[str, Any]] | None = None) -> Path:
    """A dataset directory carrying every file a complete data package declares.

    `occupations.json` is here because the export copies it into the package rather than
    naming it and leaving it behind: a descriptor whose paths resolve only on the machine
    that built it is a broken package that reads as a complete one.
    """
    source.mkdir(parents=True, exist_ok=True)
    (source / "programs.json").write_text(
        json.dumps({"programs": records if records is not None else [_record("a")]}),
        encoding="utf-8",
    )
    (source / "occupations.json").write_text(json.dumps({"occupations": []}), encoding="utf-8")
    (source / "coverage.json").write_text(
        json.dumps({"snapshot_date": "2026-08-07"}), encoding="utf-8"
    )
    return source


class TestTheOneRule:
    """No blank carries a meaning, over the committed fixture."""

    def test_the_fixture_exports_with_no_problems(self, table: str) -> None:
        assert tabular.state_column_problems(table) == []

    def test_no_state_cell_is_ever_empty(self, rows: list[dict[str, str]]) -> None:
        empty = [
            (row["uuid"], name)
            for row in rows
            for name, value in row.items()
            if name.endswith("_state") and value == ""
        ]

        assert empty == []

    def test_every_state_cell_carries_one_of_the_three_words(
        self, rows: list[dict[str, str]]
    ) -> None:
        seen = {value for row in rows for name, value in row.items() if name.endswith("_state")}

        assert seen <= set(tabular.STATES)
        assert seen == set(tabular.STATES), "the fixture should exercise all three states"

    def test_a_blank_value_always_has_a_state_that_explains_it(
        self, rows: list[dict[str, str]]
    ) -> None:
        for row in rows:
            for column in (c for c in tabular.COLUMNS if c.measured):
                if row[column.name] == "":
                    assert row[column.name + "_state"] != tabular.REPORTED

    def test_a_reported_state_always_has_a_value(self, rows: list[dict[str, str]]) -> None:
        for row in rows:
            for column in (c for c in tabular.COLUMNS if c.measured):
                if row[column.name + "_state"] == tabular.REPORTED:
                    assert row[column.name] != ""

    def test_the_fixture_actually_contains_the_absences_this_is_testing(
        self, rows: list[dict[str, str]]
    ) -> None:
        """Otherwise every assertion above passes over a table with nothing absent in it."""
        not_reported = sum(
            1
            for row in rows
            for name, value in row.items()
            if name.endswith("_state") and value == tabular.NOT_REPORTED
        )

        assert not_reported > 50, "the fixture no longer carries enough absences to test on"


class TestTheAbsentFourthState:
    """`suppressed` is not a word this dataset may write, and this is where that is pinned."""

    def test_the_vocabulary_is_three_words(self) -> None:
        assert tabular.STATES == ("reported", "not_reported", "competency_based")

    def test_suppressed_is_not_among_them(self) -> None:
        assert "suppressed" not in tabular.STATES

    def test_the_schema_says_why_rather_than_leaving_it_unexplained(self) -> None:
        """A reader meeting three words where the issue promised four is owed the reason."""
        description = tabular.to_table_schema("2026-08-07")["description"]

        assert "suppressed" in description
        assert "-1" in description

    def test_the_source_module_still_conflates_the_two_causes(self) -> None:
        """The premise of the decision, checked against the code it rests on.

        If `clean_measure` ever learns to tell a suppressed cell from an unreported one, this
        fails, and the vocabulary should grow a fourth word. Until then it must not.
        """
        from afterward.sources import dol_etp

        assert dol_etp.clean_measure(-1) is None
        assert dol_etp.clean_measure("") is None
        assert dol_etp.clean_measure(None) is None
        assert dol_etp.clean_measure(0) == 0.0


class TestCompetencyBased:
    """The `-1` that means a fact rather than a gap, on the two columns it belongs to."""

    def test_a_competency_based_program_states_it_on_both_length_columns(self) -> None:
        record = _record("a", length={"weeks": None, "hours": None, "competency_based": True})

        (row,) = list(csv.DictReader(io.StringIO(tabular.to_csv([record]))))

        assert row["length_weeks_state"] == tabular.COMPETENCY_BASED
        assert row["length_hours_state"] == tabular.COMPETENCY_BASED
        assert row["length_weeks"] == ""
        assert row["length_hours"] == ""

    def test_it_never_reaches_a_column_that_is_not_a_length(self) -> None:
        record = _record(
            "a",
            length={"weeks": None, "hours": None, "competency_based": True},
            outcomes={"median_earnings": None},
        )

        (row,) = list(csv.DictReader(io.StringIO(tabular.to_csv([record]))))

        assert row["median_earnings_state"] == tabular.NOT_REPORTED

    def test_a_length_missing_from_a_non_competency_program_is_not_reported(self) -> None:
        record = _record("a", length={"weeks": None, "hours": 400.0, "competency_based": False})

        (row,) = list(csv.DictReader(io.StringIO(tabular.to_csv([record]))))

        assert row["length_weeks_state"] == tabular.NOT_REPORTED
        assert row["length_hours_state"] == tabular.REPORTED
        assert row["length_hours"] == "400"

    def test_a_record_predating_the_flag_is_not_reported_rather_than_competency_based(
        self,
    ) -> None:
        """`build.py` warns that older records carry no `competency_based` key at all.

        Reading a missing flag as competency-based would claim a design decision the provider
        never filed; reading it as `not_reported` claims only that no length is present.
        """
        record = _record("a")
        del record["length"]["competency_based"]
        record["length"]["weeks"] = None
        record["length"]["hours"] = None

        (row,) = list(csv.DictReader(io.StringIO(tabular.to_csv([record]))))

        assert row["length_weeks_state"] == tabular.NOT_REPORTED

    def test_a_competency_based_length_that_still_carries_a_number_is_cleared(self) -> None:
        """Two cells that disagree is worse than one that is empty. The state is the claim."""
        record = _record("a", length={"weeks": 12.0, "hours": 400.0, "competency_based": True})

        (row,) = list(csv.DictReader(io.StringIO(tabular.to_csv([record]))))

        assert row["length_weeks"] == ""
        assert row["length_weeks_state"] == tabular.COMPETENCY_BASED
        assert tabular.state_column_problems(tabular.to_csv([record])) == []


class TestZeroIsNotAnAbsence:
    """The defect running the other way: a real zero must survive as a zero."""

    def test_a_zero_measure_states_reported(self) -> None:
        record = _record(
            "a", outcomes={"employed_q2": 0.0, "completion_rate": 0.0}, cost={"tuition": 0.0}
        )

        (row,) = list(csv.DictReader(io.StringIO(tabular.to_csv([record]))))

        assert row["employed_q2"] == "0"
        assert row["employed_q2_state"] == tabular.REPORTED
        assert row["completion_rate"] == "0"
        assert row["completion_rate_state"] == tabular.REPORTED
        assert row["cost_tuition"] == "0"
        assert row["cost_tuition_state"] == tabular.REPORTED

    def test_a_false_boolean_is_written_as_false_and_not_as_a_blank(self) -> None:
        record = _record("a", cost={"total_is_complete": False}, outcomes={"reported": False})

        (row,) = list(csv.DictReader(io.StringIO(tabular.to_csv([record]))))

        assert row["cost_total_is_complete"] == "false"
        assert row["outcomes_reported"] == "false"


class TestTheTableSchema:
    """Generated from the same column definitions as the table, so it cannot drift."""

    def test_every_schema_field_is_a_csv_column_and_the_reverse(self, table: str) -> None:
        schema = tabular.to_table_schema("2026-08-07")
        declared = [field["name"] for field in schema["fields"]]
        written = (table.split("\n")[0]).split(",")

        assert declared == written

    def test_every_state_field_is_constrained_to_the_three_words(self) -> None:
        schema = tabular.to_table_schema("2026-08-07")
        states = [f for f in schema["fields"] if f["name"].endswith("_state")]

        assert len(states) == len([c for c in tabular.COLUMNS if c.measured])
        for field in states:
            assert field["constraints"]["enum"] == list(tabular.STATES)
            assert field["constraints"]["required"] is True

    def test_every_field_carries_a_description(self) -> None:
        for field in tabular.to_table_schema("2026-08-07")["fields"]:
            assert field["description"].strip()

    def test_the_empty_string_is_the_only_declared_missing_value(self) -> None:
        """A schema declaring `0` or `-1` as a missing value would undo the whole design."""
        assert tabular.to_table_schema("2026-08-07")["missingValues"] == [""]

    def test_the_snapshot_date_travels_in_the_title(self) -> None:
        assert "2026-08-07" in tabular.to_table_schema("2026-08-07")["title"]


class TestDeterminism:
    def test_the_same_programs_produce_the_same_bytes(self, programs: list[dict[str, Any]]) -> None:
        assert tabular.to_csv(programs) == tabular.to_csv(programs)

    def test_the_emitted_order_does_not_change_the_bytes(
        self, programs: list[dict[str, Any]]
    ) -> None:
        assert tabular.to_csv(programs) == tabular.to_csv(list(reversed(programs)))

    def test_rows_come_out_sorted_by_uuid(self, rows: list[dict[str, str]]) -> None:
        uuids = [row["uuid"] for row in rows]

        assert uuids == sorted(uuids)


class TestMissingPiecesOfARecord:
    """A break in the path is an absence, never a crash and never a zero."""

    @pytest.mark.parametrize("section", ["cost", "length", "outcomes", "location"])
    def test_a_whole_missing_section_becomes_absences(self, section: str) -> None:
        record = _record("a")
        del record[section]

        text = tabular.to_csv([record])

        assert tabular.state_column_problems(text) == []

    def test_a_null_section_becomes_absences(self) -> None:
        record = _record("a", outcomes=None)

        text = tabular.to_csv([record])
        (row,) = list(csv.DictReader(io.StringIO(text)))

        assert row["median_earnings_state"] == tabular.NOT_REPORTED
        assert row["median_earnings"] == ""

    def test_an_empty_occupations_list_leaves_the_join_columns_blank(self) -> None:
        record = _record("a", occupations=[])

        (row,) = list(csv.DictReader(io.StringIO(tabular.to_csv([record]))))

        assert row["occupation_soc_code"] == ""
        assert row["occupation_match_kind"] == ""

    def test_soc_codes_are_written_space_separated(self) -> None:
        record = _record("a", soc_codes=["29-2052", "31-9097"])

        (row,) = list(csv.DictReader(io.StringIO(tabular.to_csv([record]))))

        assert row["soc_codes"] == "29-2052 31-9097"


class TestTheProblemReaderCanActuallyFail:
    """The checker reads the rendered bytes, so a sabotage in the bytes must reach it.

    Each case mutates the rendered table, asserts the mutation is present in the text, and only
    then asserts that the checker sees it. `state_column_problems` re-deriving its expectation
    from `to_csv` would compare a value to itself and could never fail; these prove it does not.
    """

    def test_an_emptied_state_cell_is_reported(self) -> None:
        record = _record("a")
        text = tabular.to_csv([record])
        header, first, _ = text.split("\n")
        index = header.split(",").index("median_earnings_state")
        cells = first.split(",")
        assert cells[index] == "reported"
        cells[index] = ""
        sabotaged = "\n".join([header, ",".join(cells), ""])
        # Same number of cells, one of them emptied: the shape is intact and only the state
        # is gone, so a problem reported here is the emptiness and not a shifted row.
        assert len(sabotaged.split("\n")[1].split(",")) == len(first.split(","))
        assert sabotaged.split("\n")[1].split(",")[index] == ""

        problems = tabular.state_column_problems(sabotaged)

        assert problems == ["row 2: median_earnings_state is empty"]

    def test_a_fourth_state_word_is_reported(self, table: str) -> None:
        sabotaged = table.replace(",not_reported,", ",suppressed,", 1)
        assert ",suppressed," in sabotaged

        problems = tabular.state_column_problems(sabotaged)

        assert any("'suppressed'" in p for p in problems)

    def test_a_value_filled_in_beside_a_not_reported_state_is_caught(self) -> None:
        record = _record("a", outcomes={"median_earnings": None})
        text = tabular.to_csv([record])
        header = text.split("\n")[0].split(",")
        index = header.index("median_earnings")
        cells = text.split("\n")[1].split(",")
        assert cells[index] == ""
        cells[index] = "0"
        sabotaged = "\n".join([text.split("\n")[0], ",".join(cells), ""])
        assert ",0,not_reported," in sabotaged

        problems = tabular.state_column_problems(sabotaged)

        assert any("carries '0'" in p and "not_reported" in p for p in problems)

    def test_a_blanked_value_beside_a_reported_state_is_caught(self) -> None:
        record = _record("a")
        text = tabular.to_csv([record])
        header = text.split("\n")[0].split(",")
        index = header.index("median_earnings")
        cells = text.split("\n")[1].split(",")
        assert cells[index] == "9000"
        cells[index] = ""
        sabotaged = "\n".join([text.split("\n")[0], ",".join(cells), ""])
        assert ",,reported," in sabotaged

        problems = tabular.state_column_problems(sabotaged)

        assert any("blank but states reported" in p for p in problems)

    def test_a_changed_header_is_reported_before_anything_else(self, table: str) -> None:
        sabotaged = table.replace("median_earnings_state", "median_earnings_status", 1)
        assert "median_earnings_status" in sabotaged

        problems = tabular.state_column_problems(sabotaged)

        assert len(problems) == 1
        assert problems[0].startswith("header is")

    def test_the_checker_says_nothing_about_the_untouched_table(self, table: str) -> None:
        assert tabular.state_column_problems(table) == []


class TestTheExportRefusesRatherThanWritingAPartialFile:
    """The guard runs before anything is written, as `export_ctdl`'s guards do."""

    def test_a_broken_rule_leaves_no_file_behind(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source = _minimal_dataset(tmp_path / "data")
        out = tmp_path / "out"

        good = tabular.to_csv([_record("a")])
        broken = good.replace(",reported,", ",,", 1)
        # Prove the sabotage is a sabotage before relying on the refusal it should cause.
        assert broken != good
        assert tabular.state_column_problems(broken) != []
        monkeypatch.setattr(tabular, "to_csv", lambda programs: broken)

        with pytest.raises(ValueError, match="breaks its own absence rule"):
            tabular.export_csv(source, out)

        assert not (out / tabular.TABLE_FILENAME).exists()
        assert not (out / tabular.SCHEMA_FILENAME).exists()

    def test_without_the_sabotage_the_same_export_succeeds(self, tmp_path: Path) -> None:
        """The control's control: the refusal above is caused by the fault, not by the setup."""
        source = _minimal_dataset(tmp_path / "data")
        out = tmp_path / "out"

        report = tabular.export_csv(source, out)

        assert report.rows == 1
        assert (out / tabular.TABLE_FILENAME).exists()


class TestTheCommandLine:
    def test_it_writes_the_table_and_the_schema(self, tmp_path: Path) -> None:
        result = CliRunner().invoke(
            app,
            [
                "export-csv",
                "--dataset-dir",
                str(FIXTURE_DIR),
                "--output-dir",
                str(tmp_path),
            ],
        )

        assert result.exit_code == 0, result.output
        table = (tmp_path / tabular.TABLE_FILENAME).read_text(encoding="utf-8")
        schema = json.loads((tmp_path / tabular.SCHEMA_FILENAME).read_text(encoding="utf-8"))
        assert tabular.state_column_problems(table) == []
        assert [f["name"] for f in schema["fields"]] == table.split("\n")[0].split(",")

    def test_it_prints_the_state_counts_rather_than_only_a_row_count(self, tmp_path: Path) -> None:
        """A row count is the number that looks fine when every cell is absent."""
        result = CliRunner().invoke(
            app,
            ["export-csv", "--dataset-dir", str(FIXTURE_DIR), "--output-dir", str(tmp_path)],
        )

        for state in tabular.STATES:
            assert state in result.output

    def test_the_report_counts_agree_with_the_file_it_wrote(self, tmp_path: Path) -> None:
        report = tabular.export_csv(FIXTURE_DIR, tmp_path)
        table = (tmp_path / tabular.TABLE_FILENAME).read_text(encoding="utf-8")
        rows = list(csv.DictReader(io.StringIO(table)))

        counted = {state: 0 for state in tabular.STATES}
        for row in rows:
            for name, value in row.items():
                if name.endswith("_state"):
                    counted[value] += 1

        assert report.rows == len(rows)
        assert dict(report.states) == counted
        assert report.columns == len(table.split("\n")[0].split(","))


class TestTheMakefileTargetIsTheOneDescribed:
    """`csv-export` must not write into the directory the site serves."""

    def test_it_writes_to_dist_and_not_to_the_dataset_directory(self) -> None:
        makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
        start = makefile.index("\ncsv-export:")
        recipe = makefile[start:].split("\n\n")[0]

        assert "--output-dir $(DIST_DIR)/csv" in recipe
        assert "--dataset-dir $(DATASET_DIR)" in recipe
        assert "> $(DATASET_DIR)" not in recipe

    def test_the_target_is_declared_phony(self) -> None:
        makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
        phony = makefile.split(".PHONY:")[1].split("\n\n")[0]

        assert "csv-export" in phony


class TestTheDataPackage:
    """The descriptor has to describe the directory a reader downloaded, not the one it was built in.

    Every assertion here reads files off disk rather than the values the writer held in
    memory. A check that re-derives its expectation from the function that produced the
    answer compares a value to itself and cannot fail — the same reason
    `state_column_problems` parses the rendered CSV instead of inspecting the records.
    """

    @pytest.fixture
    def package_dir(self, tmp_path: Path) -> Path:
        tabular.export_csv(FIXTURE_DIR, tmp_path)
        return tmp_path

    def test_every_declared_resource_is_in_the_package(self, package_dir: Path) -> None:
        descriptor = json.loads(
            (package_dir / tabular.DATA_PACKAGE_FILENAME).read_text(encoding="utf-8")
        )

        assert tabular.data_package_problems(descriptor, package_dir) == []

    def test_it_declares_the_table_and_all_three_emitted_json_files(
        self, package_dir: Path
    ) -> None:
        """A package holding only the CSV would send a reader back to the sharded JSON."""
        descriptor = json.loads(
            (package_dir / tabular.DATA_PACKAGE_FILENAME).read_text(encoding="utf-8")
        )

        declared = [resource["path"] for resource in descriptor["resources"]]
        assert declared == [tabular.TABLE_FILENAME, *(name for name, _ in tabular.JSON_RESOURCES)]

    def test_the_json_resources_are_copies_of_the_dataset_byte_for_byte(
        self, package_dir: Path
    ) -> None:
        for name, _description in tabular.JSON_RESOURCES:
            assert (package_dir / name).read_bytes() == (FIXTURE_DIR / name).read_bytes()

    def test_the_table_resource_carries_the_same_schema_that_was_written_beside_it(
        self, package_dir: Path
    ) -> None:
        """Two copies of a schema that can disagree are worse than one."""
        descriptor = json.loads(
            (package_dir / tabular.DATA_PACKAGE_FILENAME).read_text(encoding="utf-8")
        )
        beside = json.loads((package_dir / tabular.SCHEMA_FILENAME).read_text(encoding="utf-8"))

        assert descriptor["resources"][0]["schema"] == beside

    def test_the_declared_dialect_is_the_one_the_writer_uses(self, package_dir: Path) -> None:
        """`to_csv` overrides csv's `\\r\\n` default; a reader told otherwise parses a stray CR."""
        descriptor = json.loads(
            (package_dir / tabular.DATA_PACKAGE_FILENAME).read_text(encoding="utf-8")
        )
        table = (package_dir / tabular.TABLE_FILENAME).read_bytes().decode("utf-8")

        terminator = descriptor["resources"][0]["dialect"]["lineTerminator"]
        assert terminator == "\n"
        assert table.endswith(terminator)
        assert "\r" not in table

    def test_the_version_is_the_snapshot_the_dataset_declares(self, package_dir: Path) -> None:
        descriptor = json.loads(
            (package_dir / tabular.DATA_PACKAGE_FILENAME).read_text(encoding="utf-8")
        )
        coverage = json.loads((FIXTURE_DIR / "coverage.json").read_text(encoding="utf-8"))

        assert descriptor["version"] == coverage["snapshot_date"]

    def test_the_same_snapshot_writes_the_same_descriptor(self, tmp_path: Path) -> None:
        """No clock is consulted, so two exports of one snapshot are byte-identical."""
        first, second = tmp_path / "one", tmp_path / "two"
        tabular.export_csv(FIXTURE_DIR, first)
        tabular.export_csv(FIXTURE_DIR, second)

        assert (first / tabular.DATA_PACKAGE_FILENAME).read_bytes() == (
            second / tabular.DATA_PACKAGE_FILENAME
        ).read_bytes()

    def test_it_names_the_reporting_obligations_and_the_absent_suppressed_state(
        self, package_dir: Path
    ) -> None:
        """The two sentences a reader needs before quoting a blank, inside the package.

        A README they may never have downloaded is not where the caveat belongs: the
        scorecard serves a suppressed cell and an unreported cell as the same `-1`, and a
        reader who does not know that will read `not_reported` as "nobody was suppressed".
        """
        descriptor = json.loads(
            (package_dir / tabular.DATA_PACKAGE_FILENAME).read_text(encoding="utf-8")
        )
        provenance = descriptor["afterward:provenance"]

        assert "PROVENANCE.md I7-I11" in provenance["reportingObligations"]
        assert "apprenticeship" in provenance["reportingObligations"].lower()
        assert "no 'suppressed' word" in provenance["suppression"]
        assert descriptor["citation"][0]["text"].endswith("https://github.com/ChelseaKR/afterward")

    def test_a_resource_the_package_does_not_hold_is_a_problem_not_a_pass(
        self, package_dir: Path
    ) -> None:
        """The control for the checker: it must fail on a descriptor whose path is a lie."""
        descriptor = json.loads(
            (package_dir / tabular.DATA_PACKAGE_FILENAME).read_text(encoding="utf-8")
        )
        (package_dir / "occupations.json").unlink()

        problems = tabular.data_package_problems(descriptor, package_dir)

        assert [p for p in problems if "occupations.json" in p], problems

    def test_a_resource_whose_bytes_changed_is_a_problem(self, package_dir: Path) -> None:
        """A hash nothing compares is a hash nobody can trust."""
        descriptor = json.loads(
            (package_dir / tabular.DATA_PACKAGE_FILENAME).read_text(encoding="utf-8")
        )
        table = package_dir / tabular.TABLE_FILENAME
        table.write_bytes(table.read_bytes() + b"x")

        problems = tabular.data_package_problems(descriptor, package_dir)

        assert any("hash" in p for p in problems), problems

    def test_an_empty_resource_list_is_refused_rather_than_read_as_clean(self) -> None:
        """`all([])` over no resources is the shape this project keeps finding."""
        assert tabular.data_package_problems({"resources": []}, Path(".")) != []
        assert tabular.data_package_problems({}, Path(".")) != []

    def test_a_dataset_missing_a_declared_file_is_refused_before_anything_is_written(
        self, tmp_path: Path
    ) -> None:
        source = _minimal_dataset(tmp_path / "data")
        (source / "occupations.json").unlink()
        out = tmp_path / "out"

        with pytest.raises(ValueError, match=re.escape("occupations.json")):
            tabular.export_csv(source, out)

        assert not (out / tabular.DATA_PACKAGE_FILENAME).exists()

    def test_the_report_names_every_file_the_descriptor_declares(self, tmp_path: Path) -> None:
        report = tabular.export_csv(FIXTURE_DIR, tmp_path)
        descriptor = json.loads(
            (tmp_path / tabular.DATA_PACKAGE_FILENAME).read_text(encoding="utf-8")
        )

        assert list(report.resources) == [r["path"] for r in descriptor["resources"]]


class TestTheChecksumsCoverWhatWasWritten:
    """SHA256SUMS is derived from the descriptor, so a new resource cannot be left out."""

    def test_the_recipe_reads_the_resource_list_rather_than_naming_files(self) -> None:
        makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
        recipe = makefile[makefile.index("\ncsv-export:") :].split("\n\n")[0]

        assert 'json.load(open("datapackage.json"))["resources"]' in recipe
        assert "SHA256SUMS" in recipe
        # The two files that are *not* resources still have to be named, because a
        # descriptor cannot list itself.
        assert "programs.schema.json datapackage.json > SHA256SUMS" in recipe
