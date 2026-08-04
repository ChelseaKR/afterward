"""Tests for the DOL ETP client.

The suppression-sentinel behaviour is the highest-stakes logic in this codebase: showing a
suppressed cell as 0% would misrepresent a real training provider's performance.
"""

from __future__ import annotations

import pytest

from camino.sources.dol_etp import (
    Program,
    clean_measure,
    clean_url,
    parse_program,
    parse_state_benchmark,
)


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

    def test_total_cost_with_a_suppressed_component_is_marked_incomplete(self) -> None:
        """The sum is a floor, not a total, and callers must be able to tell."""
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
        assert program.cost_is_complete is False

    def test_total_cost_with_every_component_reported_is_complete(self) -> None:
        program = parse_program(
            {
                "_source": {
                    "field_uuid": "u",
                    "field_non_wioa_tuition_cost": 5568,
                    "field_non_wioa_supplies_cost": 2450,
                }
            }
        )
        assert program.total_cost == 8018.0
        assert program.cost_is_complete is True

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


class TestStateBenchmark:
    """The statewide aggregate gives a bare program rate something to be read against."""

    def _source(self, **overrides: object) -> dict[str, object]:
        return {
            "field_c_completed_percent": 0.71,
            "field_c_q2_employment_percent": 0.27,
            "field_c_median_earnings": 16978.95,
            "field_c_cred_attainment_percent": 0.37,
            "field_c_total_exited": 664260,
            "field_c_total_completed": 469808,
            **overrides,
        }

    def test_parses_the_published_measures(self) -> None:
        benchmark = parse_state_benchmark("CA", self._source())
        assert benchmark.completion_rate == 0.71
        assert benchmark.q2_employment_rate == 0.27
        assert benchmark.median_earnings == 16978.95
        assert benchmark.total_exited == 664260

    def test_suppressed_state_measures_stay_none(self) -> None:
        benchmark = parse_state_benchmark("CA", self._source(field_c_median_earnings=-1))
        assert benchmark.median_earnings is None

    def test_missing_fields_do_not_raise(self) -> None:
        benchmark = parse_state_benchmark("CA", {})
        assert benchmark.state == "CA"
        assert benchmark.completion_rate is None

    def test_as_dict_uses_the_same_keys_as_program_outcomes(self) -> None:
        """The UI compares these side by side, so the names must line up."""
        payload = parse_state_benchmark("CA", self._source()).as_dict()
        assert payload["employment_rate_q2"] == 0.27
        assert payload["median_earnings"] == 16978.95
        assert payload["state"] == "CA"


class TestCleanUrl:
    """`field_program_url` is free text from third parties and lands in an href."""

    def test_keeps_absolute_http_urls(self) -> None:
        assert clean_url("https://example.org/program") == "https://example.org/program"
        assert clean_url("http://example.org") == "http://example.org"

    def test_repairs_a_bare_domain(self) -> None:
        # Unambiguous, and discarding it would lose a working provider link.
        assert clean_url("www.amanet.org") == "https://www.amanet.org"
        assert clean_url("www.example.com/path/") == "https://www.example.com/path/"

    def test_repairs_a_protocol_relative_url(self) -> None:
        assert clean_url("//example.org/x") == "https://example.org/x"

    def test_drops_text_that_is_not_a_url(self) -> None:
        # Five California records hold a course title where a URL belongs. Rendered raw,
        # these made "Provider's website" navigate to a path inside this site.
        assert clean_url("Data Science Career Track") is None
        assert clean_url("Supply Management") is None

    def test_drops_dangerous_schemes(self) -> None:
        # React does not block javascript: in an href, so this is a script-injection sink.
        for hostile in (
            "javascript:alert(1)",
            "JavaScript:alert(1)",
            "data:text/html;base64,PHNjcmlwdD4=",
            "vbscript:msgbox(1)",
            "file:///etc/passwd",
        ):
            assert clean_url(hostile) is None, hostile

    def test_drops_empty_and_null(self) -> None:
        assert clean_url(None) is None
        assert clean_url("   ") is None
