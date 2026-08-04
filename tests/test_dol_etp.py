"""Tests for the DOL ETP client.

The suppression-sentinel behaviour is the highest-stakes logic in this codebase: showing a
suppressed cell as 0% would misrepresent a real training provider's performance.
"""

from __future__ import annotations

import pytest

from camino.sources.dol_etp import Program, clean_measure, parse_program


class TestCleanMeasure:
    @pytest.mark.parametrize("value", [-1, -1.0, "-1", "", None])
    def test_not_reported_becomes_none(self, value: object) -> None:
        assert clean_measure(value) is None

    def test_genuine_zero_is_preserved(self) -> None:
        """A reported 0% is a real finding and must survive."""
        assert clean_measure(0) == 0.0
        assert clean_measure("0") == 0.0

    def test_ordinary_values_pass_through(self) -> None:
        assert clean_measure(0.64) == 0.64
        assert clean_measure("10200.01") == 10200.01

    def test_unparseable_becomes_none(self) -> None:
        assert clean_measure("not a number") is None


class TestSocNormalisation:
    def _program(self, **soc: str) -> Program:
        return parse_program({"_id": "x", "_source": {"field_uuid": "u", **soc}})

    def test_eight_digit_codes_truncate_to_standard_six(self) -> None:
        program = self._program(field_program_soc_occ_1="15-125200")
        assert program.soc_codes == ("15-1252",)

    def test_multiple_codes_are_collected_in_order(self) -> None:
        program = self._program(
            field_program_soc_occ_1="15-125200",
            field_program_soc_occ_2="29-114100",
        )
        assert program.soc_codes == ("15-1252", "29-1141")

    def test_blank_and_duplicate_codes_are_dropped(self) -> None:
        program = self._program(
            field_program_soc_occ_1="15-125200",
            field_program_soc_occ_2="",
            field_program_soc_occ_3="15-125200",
        )
        assert program.soc_codes == ("15-1252",)

    def test_malformed_code_is_ignored(self) -> None:
        assert self._program(field_program_soc_occ_1="abc").soc_codes == ()


class TestProgramParsing:
    def test_suppressed_outcomes_do_not_count_as_reported(self) -> None:
        program = parse_program(
            {
                "_source": {
                    "field_uuid": "u",
                    "field_c_median_earnings": -1,
                    "field_c_q2_employment_percent": -1,
                    "field_c_completed_percent": -1,
                }
            }
        )
        assert program.has_outcomes is False
        assert program.median_earnings is None

    def test_any_reported_measure_counts_as_outcomes(self) -> None:
        program = parse_program(
            {"_source": {"field_uuid": "u", "field_c_median_earnings": 10200.0}}
        )
        assert program.has_outcomes is True

    def test_total_cost_sums_reported_components_only(self) -> None:
        program = parse_program(
            {
                "_source": {
                    "field_uuid": "u",
                    "field_non_wioa_tuition_cost": 5568,
                    "field_non_wioa_supplies_cost": -1,
                }
            }
        )
        assert program.total_cost == 5568.0

    def test_total_cost_is_none_when_nothing_reported(self) -> None:
        program = parse_program(
            {
                "_source": {
                    "field_uuid": "u",
                    "field_non_wioa_tuition_cost": -1,
                    "field_non_wioa_supplies_cost": "",
                }
            }
        )
        assert program.total_cost is None
