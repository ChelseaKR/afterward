"""What changed between two datasets, and the three events this must never merge.

A programme that left the list, a programme that is still listed and stopped reporting a
measure, and a programme that was never listed are three different facts. The tests that matter
most here are the ones asserting they stay apart: `TestARemovedProgramIsNotNineAbsences` is the
whole reason the module exists.

The second thing held here is that an empty diff means "compared, and nothing moved" and never
"could not compare". Every unreadable input is asserted to refuse, because the alternative --
zero counts from having read nothing -- is a published statement that the refresh changed
nothing, on the strength of never having looked.

Sabotage cases follow this repository's control convention: the fault is introduced, the file is
read back to prove the fault is in it, and only then is the change asserted. A control that
silently fails to apply reads as a pass.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from afterward import diff
from afterward.cli import app

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "fixtures" / "data"


def _program(uuid: str, **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "uuid": uuid,
        "provider_name": "A Provider",
        "program_name": "A Program",
        "length": {"weeks": 12.0, "hours": 400.0, "competency_based": False},
        "cost": {
            "tuition": 100.0,
            "supplies": 0.0,
            "total_out_of_pocket": 100.0,
            "total_is_complete": True,
            "wioa_funded_cost": 0.0,
        },
        "outcomes": {measure: 5.0 for measure in diff.MEASURES} | {"reported": True},
        "occupations": [{"soc_code": "29-2052", "match": {"kind": "exact"}}],
        "provider_link": {"verdict": "alive"},
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = {**base[key], **value}
        else:
            base[key] = value
    return base


def _write(directory: Path, programs: list[dict[str, Any]], snapshot: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "programs.json").write_text(
        json.dumps({"snapshot_date": snapshot, "state": "CA", "programs": programs}),
        encoding="utf-8",
    )
    (directory / "coverage.json").write_text(
        json.dumps(
            {
                "snapshot_date": snapshot,
                "total_programs": len(programs),
                "distinct_occupations_matched": 1,
            }
        ),
        encoding="utf-8",
    )
    return directory


def _compare(tmp_path: Path, before: list[dict[str, Any]], after: list[dict[str, Any]]):  # type: ignore[no-untyped-def]
    a = _write(tmp_path / "a", before, "2026-08-01")
    b = _write(tmp_path / "b", after, "2026-09-01")
    return diff.compare(diff.load_dataset(a), diff.load_dataset(b))


class TestARemovedProgramIsNotNineAbsences:
    """The distinction the module exists for, asserted in both directions."""

    def test_a_removed_program_produces_one_event_and_no_measure_events(
        self, tmp_path: Path
    ) -> None:
        result = _compare(tmp_path, [_program("a")], [])

        assert [c.kind for c in result.changes] == ["program_removed", "provider_gone"]
        assert result.counts["by_kind"]["stopped_reporting"] == 0
        for measure in diff.MEASURES:
            assert result.counts["by_measure"][measure]["stopped_reporting"] == 0

    def test_a_program_that_stops_reporting_produces_a_measure_event_and_stays_listed(
        self, tmp_path: Path
    ) -> None:
        after = _program("a", outcomes={"median_earnings": None})

        result = _compare(tmp_path, [_program("a")], [after])

        assert [c.kind for c in result.changes] == ["stopped_reporting"]
        assert result.changes[0].subject == "median_earnings"
        assert result.counts["by_kind"]["program_removed"] == 0

    def test_an_added_program_produces_one_event_and_no_measure_events(
        self, tmp_path: Path
    ) -> None:
        """A programme never on the list did not start reporting; it started being listed."""
        result = _compare(tmp_path, [], [_program("a")])

        assert [c.kind for c in result.changes] == ["program_added", "provider_new"]
        assert result.counts["by_kind"]["started_reporting"] == 0

    def test_the_two_cases_are_distinguishable_from_the_counts_alone(self, tmp_path: Path) -> None:
        """The counts a summary is written from must carry the distinction, not only the events."""
        removed = _compare(tmp_path / "one", [_program("a")], [])
        stopped = _compare(
            tmp_path / "two", [_program("a")], [_program("a", outcomes={"median_earnings": None})]
        )

        assert removed.counts["by_kind"] != stopped.counts["by_kind"]
        assert removed.counts["by_kind"]["program_removed"] == 1
        assert stopped.counts["by_kind"]["program_removed"] == 0


class TestMeasureEvents:
    def test_a_measure_appearing_is_started_reporting(self, tmp_path: Path) -> None:
        result = _compare(
            tmp_path, [_program("a", outcomes={"employed_q4": None})], [_program("a")]
        )

        assert [(c.kind, c.subject) for c in result.changes] == [
            ("started_reporting", "employed_q4")
        ]
        assert result.changes[0].after == "5"

    def test_a_measure_changing_value_is_not_a_reporting_event(self, tmp_path: Path) -> None:
        """The state is what this tracks. 5 to 7 is not a reporting change; it is a new number."""
        result = _compare(
            tmp_path, [_program("a")], [_program("a", outcomes={"median_earnings": 7.0})]
        )

        assert result.total == 0

    def test_every_measure_is_tracked_and_counted_on_its_own(self, tmp_path: Path) -> None:
        after = _program("a", outcomes=dict.fromkeys(diff.MEASURES))

        result = _compare(tmp_path, [_program("a")], [after])

        assert result.counts["by_kind"]["stopped_reporting"] == len(diff.MEASURES)
        for measure in diff.MEASURES:
            assert result.counts["by_measure"][measure]["stopped_reporting"] == 1

    def test_the_measure_counts_are_never_rolled_into_one_number(self) -> None:
        """Nine measures moving once and one measure moving nine times differ; the payload says so."""
        assert set(diff.DatasetDiff("a", "b", 0, 0, 0, 0, ()).counts) == {"by_kind", "by_measure"}

    def test_a_record_with_no_outcomes_section_reads_as_not_reported_not_as_a_crash(
        self, tmp_path: Path
    ) -> None:
        after = _program("a")
        del after["outcomes"]

        result = _compare(tmp_path, [_program("a")], [after])

        assert result.counts["by_kind"]["stopped_reporting"] == len(diff.MEASURES)


class TestTheOtherEventKinds:
    def test_a_retitled_program_carries_both_titles(self, tmp_path: Path) -> None:
        result = _compare(
            tmp_path, [_program("a")], [_program("a", program_name="A Renamed Program")]
        )

        (change,) = result.changes
        assert change.kind == "program_retitled"
        assert change.before == "A Program"
        assert change.after == "A Renamed Program"

    def test_a_provider_with_no_programs_left_is_reported_gone(self, tmp_path: Path) -> None:
        before = [_program("a"), _program("b", provider_name="Other Provider")]

        result = _compare(tmp_path, before, [_program("a")])

        gone = [c for c in result.changes if c.kind == "provider_gone"]
        assert [c.subject for c in gone] == ["Other Provider"]

    def test_a_provider_that_still_has_a_program_is_not_reported_gone(self, tmp_path: Path) -> None:
        before = [_program("a"), _program("b")]

        result = _compare(tmp_path, before, [_program("a")])

        assert [c.kind for c in result.changes] == ["program_removed"]

    def test_a_length_change_names_the_field(self, tmp_path: Path) -> None:
        result = _compare(tmp_path, [_program("a")], [_program("a", length={"weeks": 20.0})])

        (change,) = result.changes
        assert (change.kind, change.subject, change.before, change.after) == (
            "length_changed",
            "weeks",
            "12",
            "20",
        )

    def test_a_program_becoming_competency_based_is_its_own_length_event(
        self, tmp_path: Path
    ) -> None:
        after = _program("a", length={"weeks": None, "hours": None, "competency_based": True})

        result = _compare(tmp_path, [_program("a")], [after])

        subjects = {c.subject for c in result.changes if c.kind == "length_changed"}
        assert subjects == {"weeks", "hours", "competency_based"}

    def test_a_cost_change_names_the_field(self, tmp_path: Path) -> None:
        result = _compare(tmp_path, [_program("a")], [_program("a", cost={"tuition": 200.0})])

        (change,) = result.changes
        assert (change.kind, change.subject) == ("cost_changed", "tuition")

    def test_an_occupation_match_kind_moving_is_reported(self, tmp_path: Path) -> None:
        after = _program("a", occupations=[{"soc_code": "29-2052", "match": {"kind": "broad"}}])

        result = _compare(tmp_path, [_program("a")], [after])

        (change,) = result.changes
        assert (change.kind, change.before, change.after) == (
            "occupation_match_changed",
            "exact",
            "broad",
        )

    def test_losing_the_occupation_join_entirely_is_reported_as_a_move_to_nothing(
        self, tmp_path: Path
    ) -> None:
        result = _compare(tmp_path, [_program("a")], [_program("a", occupations=[])])

        (change,) = result.changes
        assert (change.kind, change.before, change.after) == (
            "occupation_match_changed",
            "exact",
            "",
        )

    def test_a_link_verdict_moving_is_reported(self, tmp_path: Path) -> None:
        after = _program("a", provider_link={"verdict": "not_found"})

        result = _compare(tmp_path, [_program("a")], [after])

        (change,) = result.changes
        assert (change.kind, change.before, change.after) == (
            "link_verdict_changed",
            "alive",
            "not_found",
        )


class TestAnEmptyDiffMeansCompared:
    """Zero counts must be the result of looking, never the result of not looking."""

    @pytest.mark.parametrize("missing", ["programs.json", "coverage.json"])
    def test_a_missing_file_refuses_rather_than_reading_an_empty_dataset(
        self, tmp_path: Path, missing: str
    ) -> None:
        directory = _write(tmp_path / "a", [_program("a")], "2026-08-01")
        (directory / missing).unlink()
        # The sabotage, read back: the file really is gone before the refusal is believed.
        assert not (directory / missing).exists()

        with pytest.raises(diff.DatasetUnreadable, match="does not exist"):
            diff.load_dataset(directory)

    def test_a_missing_directory_refuses(self, tmp_path: Path) -> None:
        with pytest.raises(diff.DatasetUnreadable, match="does not exist"):
            diff.load_dataset(tmp_path / "nowhere")

    def test_invalid_json_refuses(self, tmp_path: Path) -> None:
        directory = _write(tmp_path / "a", [_program("a")], "2026-08-01")
        (directory / "programs.json").write_text("{not json", encoding="utf-8")
        assert "{not json" in (directory / "programs.json").read_text(encoding="utf-8")

        with pytest.raises(diff.DatasetUnreadable, match="invalid JSON"):
            diff.load_dataset(directory)

    def test_a_dataset_with_no_snapshot_date_refuses(self, tmp_path: Path) -> None:
        directory = _write(tmp_path / "a", [_program("a")], "2026-08-01")
        (directory / "coverage.json").write_text(json.dumps({}), encoding="utf-8")

        with pytest.raises(diff.DatasetUnreadable, match="states no snapshot_date"):
            diff.load_dataset(directory)

    def test_a_record_with_no_uuid_refuses(self, tmp_path: Path) -> None:
        """Without a uuid there is nothing to compare on, and a guessed key invents events."""
        record = _program("a")
        del record["uuid"]
        directory = _write(tmp_path / "a", [record], "2026-08-01")

        with pytest.raises(diff.DatasetUnreadable, match="no uuid"):
            diff.load_dataset(directory)

    def test_a_programs_document_with_no_list_refuses(self, tmp_path: Path) -> None:
        directory = _write(tmp_path / "a", [_program("a")], "2026-08-01")
        (directory / "programs.json").write_text(
            json.dumps({"snapshot_date": "x"}), encoding="utf-8"
        )

        with pytest.raises(diff.DatasetUnreadable, match="no 'programs' list"):
            diff.load_dataset(directory)

    def test_an_empty_diff_says_it_compared(self, tmp_path: Path) -> None:
        result = _compare(tmp_path, [_program("a")], [_program("a")])

        assert result.total == 0
        assert result.as_payload()["compared"] is True

    def test_the_summary_of_an_empty_diff_says_which_of_the_two_it_is(self, tmp_path: Path) -> None:
        result = _compare(tmp_path, [_program("a")], [_program("a")])

        summary = diff.to_markdown(result)

        assert "compared and nothing moved" in summary
        assert "never an empty diff" in summary

    def test_a_refusal_writes_nothing(self, tmp_path: Path) -> None:
        good = _write(tmp_path / "a", [_program("a")], "2026-08-01")
        out = tmp_path / "out"

        with pytest.raises(diff.DatasetUnreadable):
            diff.diff_datasets(good, tmp_path / "nowhere", out)

        assert not (out / diff.STATEMENT_FILENAME).exists()
        assert not (out / diff.SUMMARY_FILENAME).exists()


class TestTheCommittedFixture:
    """The issue's two done-when conditions, over the fixture the repository ships."""

    def test_identical_directories_produce_zero_counts_and_identical_bytes(
        self, tmp_path: Path
    ) -> None:
        out = tmp_path / "out"

        first = diff.diff_datasets(FIXTURE_DIR, FIXTURE_DIR, out)
        bytes_once = (out / diff.STATEMENT_FILENAME).read_text(encoding="utf-8")
        diff.diff_datasets(FIXTURE_DIR, FIXTURE_DIR, out)

        assert first.total == 0
        assert all(count == 0 for count in first.counts["by_kind"].values())
        assert (out / diff.STATEMENT_FILENAME).read_text(encoding="utf-8") == bytes_once

    def test_one_nulled_measure_yields_exactly_that_event_and_no_removal(
        self, tmp_path: Path
    ) -> None:
        later = tmp_path / "later"
        later.mkdir()
        document = json.loads((FIXTURE_DIR / "programs.json").read_text(encoding="utf-8"))
        target = next(
            p for p in document["programs"] if p["outcomes"].get("median_earnings") is not None
        )
        target["outcomes"]["median_earnings"] = None
        (later / "programs.json").write_text(json.dumps(document), encoding="utf-8")
        (later / "coverage.json").write_text(
            (FIXTURE_DIR / "coverage.json").read_text(encoding="utf-8"), encoding="utf-8"
        )
        # The sabotage, read back off disk before the result is believed.
        reread = json.loads((later / "programs.json").read_text(encoding="utf-8"))
        assert (
            next(p for p in reread["programs"] if p["uuid"] == target["uuid"])["outcomes"][
                "median_earnings"
            ]
            is None
        )

        result = diff.compare(diff.load_dataset(FIXTURE_DIR), diff.load_dataset(later))

        assert [(c.kind, c.subject, c.uuid) for c in result.changes] == [
            ("stopped_reporting", "median_earnings", target["uuid"])
        ]
        assert result.counts["by_kind"]["program_removed"] == 0

    def test_the_fixture_compared_with_itself_is_not_vacuous(self) -> None:
        """A comparison of two empty datasets would also produce zero counts."""
        dataset = diff.load_dataset(FIXTURE_DIR)

        assert dataset.total_programs == 60
        assert len(dataset.providers) > 1


class TestDeterminism:
    def test_the_statement_carries_no_wall_clock(self, tmp_path: Path) -> None:
        result = _compare(tmp_path, [_program("a")], [_program("a", program_name="B")])
        payload = json.dumps(result.as_payload())

        assert "generated" not in payload
        assert "2026-09-06" not in payload  # today; only the two snapshot dates may appear
        assert payload.count("2026-08-01") == 1
        assert payload.count("2026-09-01") == 1

    def test_event_order_does_not_depend_on_input_order(self, tmp_path: Path) -> None:
        before = [_program("a"), _program("b"), _program("c")]
        after = [_program("c"), _program("a", program_name="B")]

        one = _compare(tmp_path / "one", before, after)
        two = _compare(tmp_path / "two", list(reversed(before)), list(reversed(after)))

        assert one.as_payload() == two.as_payload()

    def test_events_are_grouped_by_kind_in_the_declared_order(self, tmp_path: Path) -> None:
        before = [_program("a"), _program("b")]
        after = [_program("a", program_name="B", outcomes={"median_earnings": None})]

        result = _compare(tmp_path, before, after)
        positions = [diff.KINDS.index(c.kind) for c in result.changes]

        assert positions == sorted(positions)


class TestTheSummaryIsWrittenFromTheStatement:
    def test_every_kind_appears_in_the_table_with_its_count(self, tmp_path: Path) -> None:
        result = _compare(tmp_path, [_program("a")], [_program("a", cost={"tuition": 9.0})])

        summary = diff.to_markdown(result)

        for kind in diff.KINDS:
            assert f"| {kind} | " in summary
        assert "| cost_changed | 1 |" in summary

    def test_every_measure_has_a_row_even_when_nothing_moved(self, tmp_path: Path) -> None:
        """A measure missing from the table would read as a measure with nothing to report."""
        result = _compare(tmp_path, [_program("a")], [_program("a")])

        summary = diff.to_markdown(result)

        for measure in diff.MEASURES:
            assert f"| {measure} | 0 | 0 |" in summary

    def test_the_summary_states_both_snapshot_dates_and_both_program_counts(
        self, tmp_path: Path
    ) -> None:
        result = _compare(tmp_path, [_program("a")], [_program("a"), _program("b")])

        summary = diff.to_markdown(result)

        assert "2026-08-01" in summary
        assert "2026-09-01" in summary
        assert "1 programmes on 2026-08-01, 2 on 2026-09-01" in summary

    def test_the_summary_says_a_removal_is_not_a_reporting_change(self, tmp_path: Path) -> None:
        result = _compare(tmp_path, [_program("a")], [])

        assert "it stopped being listed" in diff.to_markdown(result)


class TestTheSummaryCannotDisagreeWithTheStatement:
    """A summary recomputing its own numbers could disagree with the statement it summarises.

    Sabotage the counts the summary is written from, prove the sabotage is in the object, and
    assert the summary moved with it. If the summary recounted the changes independently it would
    print the old number and this would fail -- which is what makes it a real check rather than a
    restatement.
    """

    def test_the_table_follows_the_counts_it_is_given(self, tmp_path: Path) -> None:
        real = _compare(tmp_path, [_program("a")], [_program("a", cost={"tuition": 9.0})])
        assert "| cost_changed | 1 |" in diff.to_markdown(real)

        doubled = diff.DatasetDiff(
            earlier=real.earlier,
            later=real.later,
            earlier_programs=real.earlier_programs,
            later_programs=real.later_programs,
            earlier_occupations=real.earlier_occupations,
            later_occupations=real.later_occupations,
            changes=real.changes + real.changes,
        )
        assert doubled.counts["by_kind"]["cost_changed"] == 2

        assert "| cost_changed | 2 |" in diff.to_markdown(doubled)


class TestTheCommandLine:
    def test_it_writes_both_files_and_exits_zero(self, tmp_path: Path) -> None:
        a = _write(tmp_path / "a", [_program("a")], "2026-08-01")
        b = _write(tmp_path / "b", [_program("a", cost={"tuition": 9.0})], "2026-09-01")
        out = tmp_path / "out"

        result = CliRunner().invoke(app, ["diff", str(a), str(b), "--output-dir", str(out)])

        assert result.exit_code == 0, result.output
        payload = json.loads((out / diff.STATEMENT_FILENAME).read_text(encoding="utf-8"))
        assert payload["counts"]["by_kind"]["cost_changed"] == 1
        assert (
            (out / diff.SUMMARY_FILENAME).read_text(encoding="utf-8").startswith("# What changed")
        )

    def test_an_unreadable_dataset_exits_two_and_writes_nothing(self, tmp_path: Path) -> None:
        a = _write(tmp_path / "a", [_program("a")], "2026-08-01")
        out = tmp_path / "out"

        result = CliRunner().invoke(
            app, ["diff", str(a), str(tmp_path / "nowhere"), "--output-dir", str(out)]
        )

        assert result.exit_code == 2
        assert not out.exists()

    def test_an_empty_diff_says_so_rather_than_printing_nothing(self, tmp_path: Path) -> None:
        a = _write(tmp_path / "a", [_program("a")], "2026-08-01")
        b = _write(tmp_path / "b", [_program("a")], "2026-09-01")

        result = CliRunner().invoke(
            app, ["diff", str(a), str(b), "--output-dir", str(tmp_path / "out")]
        )

        assert result.exit_code == 0
        assert "compared and nothing moved" in result.output

    def test_it_prints_the_measure_moves_that_happened(self, tmp_path: Path) -> None:
        a = _write(tmp_path / "a", [_program("a")], "2026-08-01")
        b = _write(
            tmp_path / "b", [_program("a", outcomes={"median_earnings": None})], "2026-09-01"
        )

        result = CliRunner().invoke(
            app, ["diff", str(a), str(b), "--output-dir", str(tmp_path / "out")]
        )

        assert "median_earnings" in result.output
        assert "stopped" in result.output


class TestTheMakefileTarget:
    def test_dataset_diff_is_declared_and_writes_to_dist(self) -> None:
        makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
        recipe = makefile[makefile.index("\ndataset-diff:") :].split("\n\n")[0]

        assert "$(DIST_DIR)/diff" in recipe
        assert "> $(DATASET_DIR)" not in recipe
        assert "dataset-diff" in makefile.split(".PHONY:")[1].split("\n\n")[0]
