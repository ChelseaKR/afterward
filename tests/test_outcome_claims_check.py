"""Tests for the statement that says which employment figure is a rate, and for its gate.

Two fields ship side by side and are not a numerator and a denominator of each other (#25).
The finding was written down in `PROVENANCE.md` and in comments beside both fields, and
neither of those travels with the data. What is tested here is that the statement is measured
from the dataset rather than typed, that it reaches the artifact, and that a stale copy of it
cannot be packaged -- which is the failure mode this project has now met twice, in #28 and
#34, where the repository was right and the published file was old.
"""

from __future__ import annotations

import importlib.util
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, ClassVar

from afterward.build import employment_measure_coverage

SPEC = importlib.util.spec_from_file_location(
    "outcome_claims_check",
    Path(__file__).resolve().parent.parent / "scripts" / "outcome_claims_check.py",
)
assert SPEC and SPEC.loader
outcome_claims_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(outcome_claims_check)


def program(**outcomes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "total_exited": None,
        "total_completed": None,
        "completion_rate": None,
        "employed_q2": None,
        "employment_rate_q2": None,
    }
    return {"outcomes": {**base, **outcomes}}


class TestTheStatementIsMeasured:
    def test_names_the_rate_as_the_one_to_trust(self) -> None:
        block = employment_measure_coverage([program()])
        assert block.authoritative == "employment_rate_q2"
        assert block.derivable_from_published_counts is False

    def test_counts_a_pair_that_does_not_reconcile(self) -> None:
        # 27 of 38 exiters is 71%; the published rate is 84%. Both are real figures from one
        # Van Nuys program's record, over two different denominators.
        block = employment_measure_coverage(
            [program(total_exited=38, employed_q2=27, employment_rate_q2=0.84)]
        )
        assert block.programs_publishing_both == 1
        assert block.count_over_exited_differs_by_over_10_points == 1
        assert block.count_over_exited_within_a_rounding_step == 0

    def test_counts_a_pair_that_does_reconcile_rather_than_assuming_none_can(self) -> None:
        """The block must be able to report agreement. If a refresh upstream ever publishes
        the rate's own denominator, this says so on the next build with nobody watching."""
        block = employment_measure_coverage(
            [program(total_exited=50, employed_q2=25, employment_rate_q2=0.5)]
        )
        assert block.count_over_exited_within_a_rounding_step == 1
        assert block.count_over_exited_differs_by_over_10_points == 0

    def test_counts_the_impossible_rows(self) -> None:
        block = employment_measure_coverage(
            [program(total_exited=467, employed_q2=572, employment_rate_q2=0.9)]
        )
        assert block.count_exceeds_exited == 1

    def test_a_rounding_step_is_agreement_not_a_discrepancy(self) -> None:
        """The source publishes rates to two decimals. 33/67 is 0.4925, published as 0.49."""
        block = employment_measure_coverage(
            [program(total_exited=67, total_completed=33, completion_rate=0.49)]
        )
        assert block.completion_rate_checked == 1
        assert block.completion_rate_reconciles == 1

    def test_the_completion_control_can_fail(self) -> None:
        block = employment_measure_coverage(
            [program(total_exited=100, total_completed=90, completion_rate=0.2)]
        )
        assert block.completion_rate_checked == 1
        assert block.completion_rate_reconciles == 0

    def test_a_zero_exit_count_is_not_divided_by(self) -> None:
        block = employment_measure_coverage(
            [program(total_exited=0, employed_q2=0, employment_rate_q2=0.0)]
        )
        assert block.programs_publishing_both == 0

    def test_a_program_reporting_nothing_contributes_nothing(self) -> None:
        block = employment_measure_coverage([program()])
        assert block.programs_publishing_rate == 0
        assert block.programs_publishing_count == 0
        assert block.programs_publishing_both == 0

    def test_the_citation_names_the_element_that_settles_it(self) -> None:
        assert "DE129" in employment_measure_coverage([]).citation


def _dataset(tmp_path: Path, programs: list[dict[str, Any]], coverage: dict[str, Any]) -> Path:
    (tmp_path / "programs.json").write_text(
        json.dumps({"snapshot_date": "2026-08-07", "programs": programs}), encoding="utf-8"
    )
    (tmp_path / "coverage.json").write_text(json.dumps(coverage), encoding="utf-8")
    return tmp_path


class TestTheGate:
    PROGRAMS: ClassVar[list[dict[str, Any]]] = [
        program(total_exited=38, employed_q2=27, employment_rate_q2=0.84)
    ]

    def _statement(self, programs: list[dict[str, Any]]) -> dict[str, Any]:
        return asdict(employment_measure_coverage(programs))

    def test_a_dataset_publishing_the_count_without_the_statement_is_refused(
        self, tmp_path: Path
    ) -> None:
        """The shape of every dataset published before this change, including the one
        production is serving."""
        found = outcome_claims_check.problems(_dataset(tmp_path, self.PROGRAMS, {}))
        assert found
        assert "employed_q2" in found[0]

    def test_a_dataset_that_publishes_no_count_needs_no_statement(self, tmp_path: Path) -> None:
        """Nothing to explain, so nothing is demanded. A gate that fires where there is no
        defect teaches an operator to stop reading it."""
        quiet = [program(total_exited=38, employment_rate_q2=0.84)]
        assert outcome_claims_check.problems(_dataset(tmp_path, quiet, {})) == []

    def test_a_statement_carried_over_from_another_dataset_is_refused(self, tmp_path: Path) -> None:
        """The offline build copies coverage keys through wholesale, which is exactly how a
        statement comes to describe some other snapshot. A stale claim reading as a current
        one is worse than no claim."""
        stale = self._statement(self.PROGRAMS) | {"count_exceeds_exited": 65}
        found = outcome_claims_check.problems(
            _dataset(tmp_path, self.PROGRAMS, {"employment_measures": stale})
        )
        assert found
        assert any("count_exceeds_exited" in line for line in found)

    def test_a_statement_naming_the_wrong_field_as_authoritative_is_refused(
        self, tmp_path: Path
    ) -> None:
        wrong = self._statement(self.PROGRAMS) | {"authoritative": "employed_q2"}
        dataset = _dataset(tmp_path, self.PROGRAMS, {"employment_measures": wrong})
        assert outcome_claims_check.problems(dataset)

    def test_a_matching_statement_passes(self, tmp_path: Path) -> None:
        matching = {"employment_measures": self._statement(self.PROGRAMS)}
        assert outcome_claims_check.problems(_dataset(tmp_path, self.PROGRAMS, matching)) == []

    def test_the_gate_reports_success_only_after_reading_both_files(self, tmp_path: Path) -> None:
        assert outcome_claims_check.main([str(tmp_path)]) == 1
        matching = {"employment_measures": self._statement(self.PROGRAMS)}
        assert outcome_claims_check.main([str(_dataset(tmp_path, self.PROGRAMS, matching))]) == 0
