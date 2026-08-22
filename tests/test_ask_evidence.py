"""The evidence pack says NOT REPORTED where the dataset says null, and only there.

The pack is what the model reads and what the verifier checks against. Two failures would
each defeat the whole design: a suppressed cell rendered as a number (the model would repeat
it), or a null that means something else -- no fixed length by design, no EDD area for this
city -- rendered as NOT REPORTED (the model would call a fact an absence).
"""

from __future__ import annotations

from typing import Any

from afterward.ask.dataset import Dataset, RegionHit
from afterward.ask.evidence import (
    PEERS_ID,
    EvidencePack,
    build_pack,
    occupation_record,
    peers_record,
    program_record,
)
from afterward.ask.query import StructuredQuery, execute


def _program(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "uuid": "u1",
        "provider_name": "Provider 9",
        "program_name": "Class A CDL 160 Hour",
        "program_format": "This program provides in-person instruction only.",
        "entity_type": "Public",
        "location": {"city": "Fresno"},
        "region": {"area_name": "Fresno MSA (Fresno and Madera Counties)"},
        "length": {"weeks": 4.0, "hours": 160.0, "competency_based": False},
        "cost": {
            "tuition": 3000.0,
            "supplies": None,
            "total_out_of_pocket": 3000.0,
            "total_is_complete": False,
        },
        "outcomes": {
            "total_served": 30.0,
            "total_exited": 20.0,
            "total_completed": 19.0,
            "credentials_earned": None,
            "completion_rate": 0.95,
            "employment_rate_q2": None,
            "median_earnings": None,
            "reported": True,
            "cohort": {"attributable": True},
        },
        "occupations": [{"soc_code": "53-3032", "match": {"kind": "exact"}}],
    }
    base.update(overrides)
    return base


def _occupation(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "soc_code": "53-3032",
        "title": "Heavy and Tractor-Trailer Truck Drivers",
        "period": "2024-2034",
        "median_annual_wage": 61548.0,
        "total_job_openings": 40000.0,
        "percent_change": 12.5,
        "entry_level_education": "Postsecondary nondegree award",
        "spanish": {"title": "Camioneros"},
        "regions": [
            {
                "area_name": "Fresno MSA (Fresno and Madera Counties)",
                "period": "2023-2033",
                "median_annual_wage": 52598.0,
                "total_job_openings": 11190.0,
                "percent_change": 12.5,
            }
        ],
        "related": [{"soc_code": "53-3033"}],
        "related_source": "onet",
    }
    base.update(overrides)
    return base


FRESNO = RegionHit("Fresno", "Fresno MSA (Fresno and Madera Counties)", "Fresno MSA", None, "area")


class TestProgramFacts:
    def test_suppressed_measures_are_null_and_marked(self) -> None:
        record = program_record(_program())
        assert record.id == "P:u1"
        employed = record.fact("outcomes.employment_rate_q2")
        assert employed is not None and employed.value is None and employed.suppressed
        assert "outcomes.median_earnings" in record.suppressed_fields()
        assert "outcomes.completion_rate" not in record.suppressed_fields()

    def test_reported_values_carry_kind_and_period(self) -> None:
        record = program_record(
            _program(outcomes={**_program()["outcomes"], "median_earnings": 9000.0})
        )
        earnings = record.fact("outcomes.median_earnings")
        assert earnings is not None and earnings.kind == "money" and earnings.period == "quarter"
        rate = record.fact("outcomes.completion_rate")
        assert rate is not None and rate.kind == "rate" and rate.value == 0.95

    def test_incomplete_total_is_noted_as_a_floor(self) -> None:
        record = program_record(_program())
        total = record.fact("cost.total_out_of_pocket")
        assert total is not None and total.note and "floor" in total.note
        assert record.fact("cost.supplies").suppressed  # type: ignore[union-attr]

    def test_competency_based_length_is_a_fact_not_a_suppression(self) -> None:
        record = program_record(
            _program(length={"weeks": None, "hours": None, "competency_based": True})
        )
        weeks = record.fact("length.weeks")
        assert weeks is not None and weeks.value is None and not weeks.suppressed
        assert weeks.note and "competency" in weeks.note
        assert "length.weeks" not in record.suppressed_fields()

    def test_unfiled_length_is_suppressed(self) -> None:
        record = program_record(
            _program(length={"weeks": None, "hours": None, "competency_based": False})
        )
        assert "length.weeks" in record.suppressed_fields()

    def test_no_region_is_not_not_reported(self) -> None:
        record = program_record(_program(region=None))
        area = record.fact("region.area_name")
        assert area is not None and area.value is None and not area.suppressed
        assert area.note and "statewide" in area.note

    def test_unattributable_cohort_is_flagged(self) -> None:
        record = program_record(
            _program(outcomes={**_program()["outcomes"], "cohort": {"attributable": False}})
        )
        own = record.fact("outcomes.cohort.attributable")
        assert own is not None and own.value is False and own.note

    def test_names_and_links_are_carried(self) -> None:
        record = program_record(_program())
        assert "Class A CDL 160 Hour" in record.names and "Provider 9" in record.names
        assert record.links == ["O:53-3032 (exact)"]


class TestOccupationFacts:
    def test_statewide_facts_and_annual_period(self) -> None:
        record = occupation_record(_occupation(), None)
        wage = record.fact("median_annual_wage")
        assert wage is not None and wage.period == "annual" and wage.value == 61548.0
        assert record.fact("region.median_annual_wage") is None
        assert record.links == ["O:53-3033 (related, onet)"]

    def test_regional_row_adds_its_own_period(self) -> None:
        record = occupation_record(_occupation(), FRESNO)
        assert record.fact("region.median_annual_wage").value == 52598.0  # type: ignore[union-attr]
        assert record.fact("region.period").value == "2023-2033"  # type: ignore[union-attr]

    def test_region_without_a_row_is_said(self) -> None:
        record = occupation_record(_occupation(regions=[]), FRESNO)
        missing = record.fact("region")
        assert missing is not None and missing.value is None and missing.note

    def test_city_only_region_adds_nothing_regional(self) -> None:
        city = RegionHit("Clovis", None, None, "Clovis", "city")
        record = occupation_record(_occupation(), city)
        assert record.fact("region") is None and record.fact("region.period") is None

    def test_unpublished_projection_is_suppressed(self) -> None:
        record = occupation_record(_occupation(median_annual_wage=None, percent_change=None), None)
        assert {"median_annual_wage", "percent_change"} <= set(record.suppressed_fields())


class TestPeers:
    def test_peers_record_carries_medians_and_counts(self) -> None:
        record = peers_record(
            {
                "completion_rate": {"median": 0.85, "reporting": 1951},
                "employment_rate_q2": {"median": None, "reporting": 0},
                "median_earnings": {"median": 10900.0, "reporting": 1339},
            }
        )
        assert record.id == PEERS_ID
        assert record.fact("completion_rate").value == 0.85  # type: ignore[union-attr]
        assert record.fact("completion_rate.reporting").value == 1951  # type: ignore[union-attr]
        assert record.fact("employment_rate_q2") is None
        assert record.fact("median_earnings").period == "quarter"  # type: ignore[union-attr]

    def test_empty_peers_are_left_out_of_the_pack(self) -> None:
        d = Dataset.from_documents(
            {"programs": [_program()]},
            {"occupations": {"53-3032": _occupation()}},
            {"snapshot_date": "x"},
        )
        result = execute(
            StructuredQuery(language="en", intent="find_programs", occupation_terms=["truck"]), d
        )
        pack = build_pack(result, d)
        assert PEERS_ID not in pack.records


class TestRendering:
    def test_render_says_not_reported_only_for_suppressed(self) -> None:
        pack = EvidencePack(language="en")
        pack.records["P:u1"] = program_record(
            _program(region=None, length={"weeks": None, "hours": None, "competency_based": True})
        )
        text = pack.render()
        assert "outcomes.employment_rate_q2: NOT REPORTED" in text
        assert "outcomes.median_earnings: NOT REPORTED" in text
        assert "[one quarter]" in text
        assert "length.weeks: none -- competency-based" in text
        assert "region.area_name: none -- the city is not one EDD" in text
        assert "outcomes.completion_rate: 0.95 (95%)" in text
        assert "outcomes.total_exited: 20" in text
        assert "cost.tuition: $3,000" in text

    def test_render_carries_notes_region_and_links(self) -> None:
        d = Dataset.from_documents(
            {"programs": [_program()]},
            {"occupations": {"53-3032": _occupation()}},
            {
                "snapshot_date": "x",
                "peer_medians": {"completion_rate": {"median": 0.85, "reporting": 10}},
            },
        )
        q = StructuredQuery(
            language="en",
            intent="find_programs",
            occupation_terms=["truck", "zzz"],
            region_terms=["Fresno"],
        )
        result = execute(q, d)
        pack = build_pack(result, d)
        text = pack.render()
        assert text.startswith("NOTES: ")
        assert "terms not in the occupation vocabulary: zzz" in text
        assert "REGION: Fresno MSA (Fresno and Madera Counties) (area)" in text
        assert "[PEERS] PEERS:" in text
        assert "linked: O:53-3032 (exact)" in text
        assert "region.period: 2023-2033" in text
        assert "[per year]" in text

    def test_empty_pack_says_so(self) -> None:
        assert "No records matched." in EvidencePack(language="es").render()

    def test_notes_count_exclusions_and_truncation(self) -> None:
        programs = [
            _program(
                uuid=f"u{i}",
                cost={
                    "tuition": None,
                    "supplies": None,
                    "total_out_of_pocket": None,
                    "total_is_complete": False,
                },
            )
            for i in range(10)
        ]
        d = Dataset.from_documents(
            {"programs": programs},
            {"occupations": {"53-3032": _occupation()}},
            {"snapshot_date": "x"},
        )
        result = execute(
            StructuredQuery(
                language="en", intent="find_programs", occupation_terms=["truck"], max_cost=10
            ),
            d,
        )
        assert "10 programs left out because cost not reported" in build_pack(result, d).notes
        result = execute(
            StructuredQuery(language="en", intent="find_programs", occupation_terms=["truck"]), d
        )
        assert any(
            "programs matched; the first 8 are listed" in n for n in build_pack(result, d).notes
        )
