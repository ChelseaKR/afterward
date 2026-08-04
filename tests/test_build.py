"""Tests for the occupation index and program/occupation join."""

from __future__ import annotations

import pytest

from camino.build import (
    area_coverage,
    index_occupations,
    peer_medians,
    program_payload,
    unmapped_cities,
)
from camino.sources.dol_etp import parse_program
from camino.sources.edd_lmi import area_definitions, parse_projections, principal_city_areas

PROJECTION_CSV = """Area Type,Area Name,Period,SOC Level,Standard Occupational Classification (SOC),Occupational Title,Base Year Employment Estimate,Projected Year Employment Estimate,Numeric Change,Percentage Change,Exits,Transfers,Total Job Openings,Median Hourly Wage,Median Annual Wage,Entry Level Education,Work Experience,Job Training
State,California,2024-2034,1,00-0000,"Total, All Occupations",100,110,10,10.0,5,5,20,25.00,52000,N/A,N/A,N/A
State,California,2024-2034,4,15-1252,Software Developers,1000,1200,200,20.0,50,80,330,68.50,142480,Bachelor's degree,None,None
Metropolitan Area,Fresno MSA,2024-2034,4,15-1252,Software Developers,50,60,10,20.0,3,5,18,45.00,93600,Bachelor's degree,None,None
"""


def _occupations() -> dict:
    return index_occupations(list(parse_projections(PROJECTION_CSV)))


class TestOccupationIndex:
    def test_summary_soc_rows_are_excluded(self) -> None:
        """00-0000 style rollups are not real occupations and must not be joinable."""
        assert "00-0000" not in _occupations()

    def test_statewide_detailed_row_is_indexed(self) -> None:
        occupations = _occupations()
        assert occupations["15-1252"]["median_annual_wage"] == 142480.0
        assert occupations["15-1252"]["total_job_openings"] == 330.0

    def test_regional_rows_attach_to_their_occupation(self) -> None:
        regions = _occupations()["15-1252"]["regions"]
        assert [r["area_name"] for r in regions] == ["Fresno MSA"]
        assert regions[0]["median_annual_wage"] == 93600.0

    def test_na_values_parse_as_none(self) -> None:
        rows = list(parse_projections(PROJECTION_CSV))
        assert rows[0].entry_level_education is None


class TestProgramPayload:
    def test_program_joins_to_matching_occupation(self) -> None:
        program = parse_program(
            {
                "_source": {
                    "field_uuid": "u1",
                    "field_program_name": "Software Development",
                    "field_program_soc_occ_1": "15-125200",
                }
            }
        )
        payload = program_payload(program, _occupations())
        assert [o["soc_code"] for o in payload["occupations"]] == ["15-1252"]

    def test_unmatched_soc_yields_no_occupations(self) -> None:
        program = parse_program(
            {"_source": {"field_uuid": "u2", "field_program_soc_occ_1": "99-999900"}}
        )
        assert program_payload(program, _occupations())["occupations"] == []

    def test_suppressed_outcomes_serialise_as_null_not_zero(self) -> None:
        program = parse_program({"_source": {"field_uuid": "u3", "field_c_median_earnings": -1}})
        outcomes = program_payload(program, _occupations())["outcomes"]
        assert outcomes["median_earnings"] is None
        assert outcomes["reported"] is False


class TestProjectionHelpers:
    def test_detailed_occupation_detection(self) -> None:
        rows = list(parse_projections(PROJECTION_CSV))
        assert rows[0].is_detailed_occupation is False
        assert rows[1].is_detailed_occupation is True

    def test_statewide_detection(self) -> None:
        rows = list(parse_projections(PROJECTION_CSV))
        assert rows[1].is_statewide is True
        assert rows[2].is_statewide is False


class TestRelatedOccupations:
    """Siblings come from the SOC hierarchy, which is a weaker claim than skill similarity."""

    CSV = """Area Type,Area Name,Period,SOC Level,Standard Occupational Classification (SOC),Occupational Title,Base Year Employment Estimate,Projected Year Employment Estimate,Numeric Change,Percentage Change,Exits,Transfers,Total Job Openings,Median Hourly Wage,Median Annual Wage,Entry Level Education,Work Experience,Job Training
State,California,2024-2034,4,29-1141,Registered Nurses,100,110,10,10.0,5,5,900,60.00,124000,Bachelor's degree,None,None
State,California,2024-2034,4,29-2061,Licensed Practical Nurses,50,55,5,10.0,3,3,300,35.00,72000,Postsecondary non-degree award,None,None
State,California,2024-2034,4,29-2052,Pharmacy Technicians,40,42,2,5.0,2,2,100,25.00,52000,High school diploma or equivalent,None,None
State,California,2024-2034,4,15-1252,Software Developers,80,96,16,20.0,4,6,500,68.50,142480,Bachelor's degree,None,None
"""

    def _occupations(self) -> dict:
        return index_occupations(list(parse_projections(self.CSV)))

    def test_relates_occupations_sharing_a_major_group(self) -> None:
        related = self._occupations()["29-1141"]["related"]
        assert {r["soc_code"] for r in related} == {"29-2061", "29-2052"}

    def test_does_not_relate_across_major_groups(self) -> None:
        related = self._occupations()["15-1252"]["related"]
        assert related == []

    def test_ranks_siblings_by_projected_openings(self) -> None:
        related = self._occupations()["29-2052"]["related"]
        assert [r["soc_code"] for r in related] == ["29-1141", "29-2061"]

    def test_never_relates_an_occupation_to_itself(self) -> None:
        for soc_code, occupation in self._occupations().items():
            assert soc_code not in {r["soc_code"] for r in occupation["related"]}


class TestRegionalProjectionOnPrograms:
    """A program should be shown its own area's numbers, or none, never a neighbour's."""

    CSV = """Area Type,Area Name,Period,SOC Level,Standard Occupational Classification (SOC),Occupational Title,Base Year Employment Estimate,Projected Year Employment Estimate,Numeric Change,Percentage Change,Exits,Transfers,Total Job Openings,Median Hourly Wage,Median Annual Wage,Entry Level Education,Work Experience,Job Training
State,California,2024-2034,4,15-1252,Software Developers,1000,1200,200,20.0,50,80,330,68.50,142480,Bachelor's degree,None,None
Metropolitan Area,"Fresno MSA (Fresno and Madera Counties)",2024-2034,4,15-1252,Software Developers,50,60,10,20.0,3,5,18,45.00,93600,Bachelor's degree,None,None
State,California,2024-2034,4,29-1141,Registered Nurses,900,990,90,10.0,40,60,190,60.00,124800,Bachelor's degree,None,None
Metropolitan Area,"Fresno MSA (Fresno and Madera Counties)",2024-2034,4,29-1141,Registered Nurses,60,60,0,0.0,2,3,0,$0.00,$0,Bachelor's degree,None,None
State,California,2024-2034,4,15-1211,Computer Systems Analysts,300,330,30,10.0,10,20,60,55.00,114400,Bachelor's degree,None,None
"""

    FRESNO_MSA = "Fresno MSA (Fresno and Madera Counties)"

    def _rows(self) -> list:
        return list(parse_projections(self.CSV))

    def _city_areas(self) -> dict:
        return principal_city_areas(area_definitions(self._rows()))

    def _payload(self, city: str | None, *socs: str) -> dict:
        source = {"field_uuid": "u1", "field_city": city}
        for index, soc in enumerate(socs, start=1):
            source[f"field_program_soc_occ_{index}"] = soc.replace("-", "") + "00"
        program = parse_program({"_source": source})
        return program_payload(program, index_occupations(self._rows()), self._city_areas())

    def test_a_program_in_a_named_city_carries_its_area(self) -> None:
        region = self._payload("Fresno", "15-1252")["region"]
        assert region["area_name"] == self.FRESNO_MSA
        assert region["area_short_name"] == "Fresno MSA"
        assert region["area_type"] == "Metropolitan Area"
        assert region["matched_on"] == "principal_city"

    def test_the_occupation_carries_that_areas_wage_and_openings(self) -> None:
        occupation = self._payload("Fresno", "15-1252")["occupations"][0]
        assert occupation["region"]["area_name"] == self.FRESNO_MSA
        assert occupation["region"]["median_annual_wage"] == 93600.0
        assert occupation["region"]["median_hourly_wage"] == 45.0
        assert occupation["region"]["total_job_openings"] == 18.0
        assert occupation["region"]["percent_change"] == 20.0

    def test_the_statewide_figures_are_still_the_headline(self) -> None:
        # D4: graduates do not necessarily work where they trained, so statewide stays the
        # default and the regional row sits beside it rather than replacing it.
        occupation = self._payload("Fresno", "15-1252")["occupations"][0]
        assert occupation["median_annual_wage"] == 142480.0
        assert occupation["total_job_openings"] == 330.0

    def test_matching_ignores_case_and_stray_whitespace(self) -> None:
        assert self._payload("  fresno ", "15-1252")["region"]["area_name"] == self.FRESNO_MSA

    def test_an_unnamed_city_gets_no_region_rather_than_a_nearby_one(self) -> None:
        payload = self._payload("Pleasant Hill", "15-1252")
        assert payload["region"] is None
        assert payload["occupations"][0]["region"] is None

    def test_a_missing_city_gets_no_region(self) -> None:
        payload = self._payload(None, "15-1252")
        assert payload["region"] is None

    def test_a_build_without_an_area_index_emits_explicit_nulls(self) -> None:
        # The key is always present so a consumer can tell "no region" from "old format".
        program = parse_program({"_source": {"field_uuid": "u1", "field_city": "Fresno"}})
        payload = program_payload(program, index_occupations(self._rows()))
        assert payload["region"] is None

    def test_a_suppressed_regional_wage_stays_null_not_zero(self) -> None:
        """EDD writes $0 where it has no wage to publish. Nobody earns nothing."""
        occupation = self._payload("Fresno", "29-1141")["occupations"][0]
        assert occupation["region"]["median_annual_wage"] is None
        assert occupation["region"]["median_hourly_wage"] is None

    def test_a_genuine_zero_openings_survives_as_zero(self) -> None:
        # The counterpart to the test above: zero openings is a real, publishable fact and
        # must not be flattened into "not reported".
        occupation = self._payload("Fresno", "29-1141")["occupations"][0]
        assert occupation["region"]["total_job_openings"] == 0.0
        assert occupation["region"]["percent_change"] == 0.0

    def test_an_occupation_edd_does_not_publish_locally_gets_a_null_region(self) -> None:
        """Distinct from an unplaceable program: the area is known, the row is not there.

        A reader can tell the two apart because the program-level region is populated here
        and null there.
        """
        payload = self._payload("Fresno", "15-1211")
        assert payload["region"] is not None
        assert payload["occupations"][0]["region"] is None

    def test_regions_are_resolved_per_occupation_not_once_per_program(self) -> None:
        payload = self._payload("Fresno", "15-1252", "29-1141", "15-1211")
        assert [o["region"] is not None for o in payload["occupations"]] == [True, True, False]


class TestAreaCoverageReporting:
    """The refusals are published, not swallowed."""

    def _payloads(self) -> list[dict]:
        return [
            {
                "region": {"area_name": "Fresno MSA (Fresno and Madera Counties)"},
                "location": {"city": "Fresno"},
            },
            {"region": None, "location": {"city": "Pleasant Hill"}},
            {"region": None, "location": {"city": "Pleasant Hill"}},
            {"region": None, "location": {"city": "Ukiah"}},
            {"region": None, "location": {"city": None}},
        ]

    def _areas(self) -> list:
        return area_definitions(parse_projections(TestRegionalProjectionOnPrograms.CSV))

    def test_counts_programs_placed_in_each_area(self) -> None:
        rows = area_coverage(self._payloads(), self._areas())
        assert rows[0]["area_name"] == "Fresno MSA (Fresno and Madera Counties)"
        assert rows[0]["programs"] == 1

    def test_publishes_each_areas_composition_alongside_the_count(self) -> None:
        rows = area_coverage(self._payloads(), self._areas())
        assert rows[0]["counties"] == ["Fresno", "Madera"]
        assert rows[0]["principal_cities"] == ["Fresno"]

    def test_lists_declined_cities_worst_first(self) -> None:
        assert unmapped_cities(self._payloads()) == {"Pleasant Hill": 2, "Ukiah": 1}

    def test_a_program_with_no_city_is_not_invented_as_one(self) -> None:
        assert None not in unmapped_cities(self._payloads())


class TestPeerMedians:
    """The benchmark must be the same statistic as the thing it is compared against."""

    def _payloads(self, *values: float | None) -> list[dict]:
        return [
            {
                "outcomes": {
                    "completion_rate": v,
                    "employment_rate_q2": v,
                    "median_earnings": v,
                }
            }
            for v in values
        ]

    def test_median_of_an_odd_count(self) -> None:
        result = peer_medians(self._payloads(0.1, 0.9, 0.5))
        assert result["completion_rate"]["median"] == 0.5

    def test_median_of_an_even_count_averages_the_middle_two(self) -> None:
        result = peer_medians(self._payloads(0.2, 0.4, 0.6, 0.8))
        assert result["completion_rate"]["median"] == 0.5

    def test_unreported_values_are_excluded_not_counted_as_zero(self) -> None:
        # Treating nulls as 0 would drag every median toward the floor and make most
        # programs look above average for no reason.
        result = peer_medians(self._payloads(0.8, None, 0.9, None))
        assert result["completion_rate"]["median"] == pytest.approx(0.85)
        assert result["completion_rate"]["reporting"] == 2

    def test_reports_how_many_programs_the_median_rests_on(self) -> None:
        result = peer_medians(self._payloads(0.5, 0.6, 0.7))
        assert result["employment_rate_q2"]["reporting"] == 3

    def test_no_reporters_gives_no_median_rather_than_zero(self) -> None:
        result = peer_medians(self._payloads(None, None))
        assert result["median_earnings"]["median"] is None
        assert result["median_earnings"]["reporting"] == 0

    def test_a_reported_zero_counts_toward_the_median(self) -> None:
        result = peer_medians(self._payloads(0.0, 0.5, 1.0))
        assert result["completion_rate"]["median"] == 0.5
        assert result["completion_rate"]["reporting"] == 3
