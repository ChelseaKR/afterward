"""Every figure the README states about the corpus, checked against the artifact it describes.

The README is a published page. It carried a claim that the pipeline joins "each" of the
3,266 programs to California's ten-year projection while the committed coverage statement
said 3,250 of them, which is the exact error this project exists to argue against: an
absence rendered as though it were a value. Correcting the sentence alone would only reset
the clock, because nothing would have failed when the next snapshot moved the number.

So the numbers in the prose are pinned to the two statements that are committed beside the
export and are computed from it rather than typed: ``web/public/ctdl/ctdl-coverage.json``
and ``web/public/ctdl/ctdl-validation.json``. Both hold full-corpus figures, unlike
``web/public/data/coverage.json``, which is a 60-program fixture on a fixture build and is
not committed at all.

Each claim is located by a regex anchored on enough surrounding words to identify the
sentence. A rewrite that drops the sentence fails here rather than passing quietly, which
is deliberate: the figures are the reason the sentence is in the README, so a sentence that
no longer states them has to be re-derived rather than silently un-gated.

What this does not check: that the committed statements match a fresh build. That is
``make ctdl-export`` and ``scripts/ci_artifact_check.py``'s job. This checks only that the
prose agrees with the artifact as committed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"
COVERAGE = REPO_ROOT / "web" / "public" / "ctdl" / "ctdl-coverage.json"
VALIDATION = REPO_ROOT / "web" / "public" / "ctdl" / "ctdl-validation.json"


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        loaded: dict[str, Any] = json.load(handle)
    return loaded


def _readme() -> str:
    # Newlines folded to spaces: these sentences wrap, and where they wrap is not a fact
    # about the corpus. Everything else, including the thousands separators, is matched
    # exactly as published.
    return re.sub(r"\s+", " ", README.read_text(encoding="utf-8"))


def _stated(pattern: str) -> int:
    """The one number the README states at ``pattern``, which must match exactly once."""
    matches = re.findall(pattern, _readme())
    assert matches, f"README no longer states this figure; pattern found nothing: {pattern}"
    assert len(matches) == 1, f"pattern is ambiguous, matched {len(matches)} times: {pattern}"
    return int(matches[0].replace(",", ""))


def _unprojected(key: str) -> int:
    counts: dict[str, Any] = _load(COVERAGE)["not_projected"]["source_fields"][key]
    return int(counts["reported_in_source"])


def _programs() -> int:
    return int(_load(COVERAGE)["source_programs"])


class TestTheProjectionJoin:
    """The claim this file was written for."""

    def test_the_lede_states_how_many_programs_there_are(self) -> None:
        assert _stated(r"([\d,]+) California training programs,") == _programs()

    def test_the_lede_states_how_many_are_joined_to_a_projection(self) -> None:
        stated = _stated(r"([\d,]+) of them joined to the state's own ten-year")
        assert stated == _unprojected("occupation_projections")

    def test_the_lede_states_how_many_are_not(self) -> None:
        stated = _stated(
            r"California publishes no projection for the occupation the other ([\d,]+)"
        )
        assert stated == _programs() - _unprojected("occupation_projections")

    def test_the_body_states_the_join_the_same_way_the_lede_does(self) -> None:
        joined = _stated(r"([\d,]+) of the [\d,]+ get one")
        total = _stated(r"[\d,]+ of the ([\d,]+) get one")
        assert joined == _unprojected("occupation_projections")
        assert total == _programs()

    def test_the_body_states_how_many_are_not(self) -> None:
        stated = _stated(r"state publishes no projection for the occupation the other ([\d,]+)")
        assert stated == _programs() - _unprojected("occupation_projections")

    def test_a_program_without_a_projection_is_not_hidden_by_the_wording(self) -> None:
        """No quantifier may re-assert the claim that was wrong.

        "each one" and "every one" over the program corpus is the sentence this file
        replaced. The projection is joined to 3,250 of 3,266, so a universal is false and
        must not come back through a rewrite.
        """
        text = _readme()
        for quantifier in (
            "joins each one to",
            "joined to the state's own ten-year projection for the occupation each",
        ):
            assert quantifier not in text, f"README re-asserts a universal join: {quantifier!r}"


class TestOutcomeCoverage:
    def test_the_headline_counts_programs_reporting_no_measure(self) -> None:
        """1,209 is the complement of the DataSetProfile count.

        ``dataset_profile`` returns a profile for a program with at least one reported
        measure and ``None`` when every measure is suppressed, so the entity count is
        exactly "programs reporting at least one measure".
        """
        stated = _stated(r"publish no outcome data at all . ([\d,]+) of [\d,]+")
        profiles = int(_load(COVERAGE)["entities"]["qdata:DataSetProfile"])
        assert stated == _programs() - profiles

    def test_the_headline_counts_programs_reporting_at_least_one(self) -> None:
        stated = _stated(r"while the other ([\d,]+) report at least one measure")
        assert stated == int(_load(COVERAGE)["entities"]["qdata:DataSetProfile"])

    def test_the_headline_is_still_more_than_a_third(self) -> None:
        """The README says "More than a third" in bold. If a refresh moves it under a
        third, the word is wrong even though every digit beside it is right."""
        profiles = int(_load(COVERAGE)["entities"]["qdata:DataSetProfile"])
        silent = _programs() - profiles
        assert "**More than a third**" in _readme()
        assert silent * 3 > _programs()

    def test_the_silent_programs_that_filed_no_cohort_count(self) -> None:
        """The count of programs filing none of the four cohort fields.

        The sentence also asserts these all sit inside the 1,209, which holds only if no
        program reports a measure without a cohort count. That relation is not checked
        here; the count is.
        """
        stated = _stated(r"([\d,]+) of the [\d,]+ silent programs filed no cohort")
        assert stated == _programs() - _unprojected("outcome_measures")

    def test_the_competency_based_programs(self) -> None:
        stated = _stated(r"([\d,]+) of California's [\d,]+ programs say that")
        length: dict[str, Any] = _load(COVERAGE)["not_projected"]["source_fields"]["program_length"]
        assert stated == int(length["source_fields"]["length.competency_based"])


TABLE_ROWS: tuple[tuple[str, str], ...] = (
    ("The CIP code for the field of study", "instructional_program_code"),
    ("Online, in person, or both", "program_format"),
    ("How long the program takes", "program_length"),
    ("Where the program is offered", "program_location"),
    ("What kind of provider it is", "provider_category"),
    ("What it costs a student funded under WIOA", "wioa_funded_cost"),
    ("The state's ten-year outlook for the occupation", "occupation_projections"),
    ("Four of the nine reported outcome measures", "outcome_measures"),
)
"""Each row of the "What it does not carry" table, and the coverage key it reports.

The label-to-key mapping is written here because a table row is prose and the key is not.
The numbers are not written here: they are read from the coverage statement.
"""


class TestWhatItDoesNotCarryTable:
    def test_the_table_has_a_row_for_every_dropped_field(self) -> None:
        keys = set(_load(COVERAGE)["not_projected"]["source_fields"])
        assert {key for _, key in TABLE_ROWS} == keys

    def test_the_prose_counts_the_rows(self) -> None:
        assert "eight things" in _readme()
        assert len(TABLE_ROWS) == 8

    @pytest.mark.parametrize(("label", "key"), TABLE_ROWS, ids=[k for _, k in TABLE_ROWS])
    def test_the_row_states_the_counted_figure(self, label: str, key: str) -> None:
        stated = _stated(rf"\| {re.escape(label)} \| ([\d,]+) \|")
        assert stated == _unprojected(key)


class TestValidatorFindings:
    def test_the_entity_count_the_warning_fired_on(self) -> None:
        stated = _stated(r"no errors, and one warning, ([\d,]+) times")
        validation = _load(VALIDATION)
        assert stated == int(validation["findings"]["WARNING"])
        assert stated == int(validation["entities_validated"])

    def test_no_errors_means_no_errors(self) -> None:
        validation = _load(VALIDATION)
        assert int(validation["findings"]["ERROR"]) == 0
        assert len(validation["codes"]) == 1, "README says one warning code; there are more"

    def test_the_scope_the_result_holds_over(self) -> None:
        scope = _load(VALIDATION)["validator_scope"]
        judged_classes = _stated(r"judge ([\d,]+) of the [\d,]+ classes")
        total_classes = _stated(r"judge [\d,]+ of the ([\d,]+) classes")
        judged_props = _stated(r"and ([\d,]+) of the [\d,]+ properties this")
        total_props = _stated(r"and [\d,]+ of the ([\d,]+) properties this")
        assert judged_classes == int(scope["classes_in_validator_schema"])
        assert total_classes == int(scope["classes_emitted"])
        assert judged_props == int(scope["properties_in_validator_schema"])
        assert total_props == int(scope["properties_emitted"])

    def test_the_scope_the_result_does_not_hold_over(self) -> None:
        scope = _load(VALIDATION)["validator_scope"]
        assert "the three classes and seven properties it could not" in _readme()
        assert len(scope["classes_not_in_validator_schema"]) == 3
        assert len(scope["properties_not_in_validator_schema"]) == 7


class TestTheSnapshotDate:
    def test_the_readme_names_the_snapshot_both_statements_were_taken_from(self) -> None:
        coverage_date = str(_load(COVERAGE)["snapshot_date"])
        assert str(_load(VALIDATION)["snapshot_date"]) == coverage_date
        assert f"on the {coverage_date} snapshot" in _readme()
