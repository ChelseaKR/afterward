"""Tests for the occupation index and program/occupation join."""

from __future__ import annotations

from camino.build import index_occupations, program_payload
from camino.sources.dol_etp import parse_program
from camino.sources.edd_lmi import parse_projections

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
