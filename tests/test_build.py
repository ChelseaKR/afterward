"""Tests for the occupation index and program/occupation join."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

import httpx
import pytest

from afterward.build import (
    MATCH_EXACT,
    PEER_MEASURES,
    RELATED_SOURCE_ONET,
    RELATED_SOURCE_SOC_SIBLINGS,
    SITE_COVERAGE_KEYS,
    EnrichmentCoverage,
    LinkCheckRun,
    _attach_local_help,
    aggregate_match_coverage,
    area_coverage,
    build_offline,
    check_coverage_counts,
    check_coverage_shape,
    check_outcome_integrity,
    check_provider_links,
    cohort_integrity_coverage,
    coverage_count_problems,
    coverage_shape_problems,
    detailed_soc_codes,
    enrichment_coverage,
    fetch_enrichment,
    fetch_job_centers,
    index_occupations,
    load_link_checks,
    local_help_block,
    local_help_coverage,
    local_help_document,
    match_occupations,
    outcome_integrity_problems,
    peer_medians,
    program_payload,
    provider_link_coverage,
    provider_link_pages,
    search_entry,
    unmapped_cities,
)
from afterward.sources import link_check
from afterward.sources.careeronestop import TOKEN_ENV, USER_ID_ENV, OccupationEnrichment, Skill
from afterward.sources.dol_etp import CohortFiling, cohort_integrity, parse_program
from afterward.sources.edd_lmi import area_definitions, parse_projections, principal_city_areas
from afterward.sources.link_check import (
    LABEL_PROGRAM_PAGE,
    LABEL_PROVIDER_HOME,
    NOTICE_UNREACHABLE,
    SUBSTITUTION_FRONT_PAGE,
    SUBSTITUTION_HTTPS,
    VERDICT_BY_REASON,
    LinkCheck,
    Reason,
    checks_document,
)
from afterward.sources.local_help import COMPREHENSIVE, WHO_DECIDES, AmericanJobCenter

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "data"

PROJECTION_CSV = """Area Type,Area Name,Period,SOC Level,Standard Occupational Classification (SOC),Occupational Title,Base Year Employment Estimate,Projected Year Employment Estimate,Numeric Change,Percentage Change,Exits,Transfers,Total Job Openings,Median Hourly Wage,Median Annual Wage,Entry Level Education,Work Experience,Job Training
State,California,2024-2034,1,00-0000,"Total, All Occupations",100,110,10,10.0,5,5,20,25.00,52000,N/A,N/A,N/A
State,California,2024-2034,4,15-1252,Software Developers,1000,1200,200,20.0,50,80,330,68.50,142480,Bachelor's degree,None,None
Metropolitan Area,Fresno MSA,2024-2034,4,15-1252,Software Developers,50,60,10,20.0,3,5,18,45.00,93600,Bachelor's degree,None,None
"""


CLEAN_COHORT = {
    "attributable": True,
    "internally_consistent": True,
    "shared_with_sibling_programs": None,
    "exited_exceeds_served": False,
    "completed_exceeds_served": False,
    "oversized_for_one_program": False,
}
"""What :func:`afterward.sources.dol_etp.cohort_integrity` writes on a record with nothing wrong.

Spelled out rather than generated, so a change to the emitted shape has to be made twice --
once in the pipeline and once here, deliberately.
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


class TestAggregateOccupationMatch:
    """Programs EDD publishes only inside a larger occupation, and the credential hazard.

    EDD marks every one of these aggregates as SOC level 4, its most detailed level, because
    there is no California estimate below them to publish. The fixture is faithful to that.
    """

    CSV = """Area Type,Area Name,Period,SOC Level,Standard Occupational Classification (SOC),Occupational Title,Base Year Employment Estimate,Projected Year Employment Estimate,Numeric Change,Percentage Change,Exits,Transfers,Total Job Openings,Median Hourly Wage,Median Annual Wage,Entry Level Education,Work Experience,Job Training
State,California,2024-2034,4,15-1252,Software Developers,1000,1200,200,20.0,50,80,330,68.50,142480,Bachelor's degree,None,None
State,California,2024-2034,4,31-1120,Home Health and Personal Care Aides,900,990,90,10.0,40,60,190,20.00,41600,High school diploma or equivalent,None,None
State,California,2024-2034,4,21-1018,"Substance Abuse, Behavioral Disorder, and Mental Health Counselors",500,550,50,10.0,20,30,100,30.00,62400,Master's degree,None,None
State,California,2024-2034,4,29-2010,Clinical Laboratory Technologists and Technicians,400,440,40,10.0,15,25,80,40.00,83200,Bachelor's degree,None,None
State,California,2024-2034,4,47-4090,Miscellaneous Construction and Related Workers,300,330,30,10.0,10,20,60,25.00,52000,N/A,None,None
"""

    def _occupations(self) -> dict:
        return index_occupations(list(parse_projections(self.CSV)))

    def _payload(self, *socs: str) -> dict:
        source = {"field_uuid": "u1"}
        for index, soc in enumerate(socs, start=1):
            source[f"field_program_soc_occ_{index}"] = soc.replace("-", "") + "00"
        return program_payload(parse_program({"_source": source}), self._occupations())

    def test_a_detailed_code_edd_hides_inside_a_broad_group_still_matches(self) -> None:
        # 31-1121 Home Health Aides has no California estimate of its own; without this the
        # program shows no occupation panel at all.
        occupations = self._payload("31-1121")["occupations"]
        assert [o["soc_code"] for o in occupations] == ["31-1120"]

    def test_a_broad_group_match_says_it_is_a_broad_group(self) -> None:
        match = self._payload("31-1121")["occupations"][0]["match"]
        assert match["kind"] == "soc_broad_group"
        assert match["program_soc_codes"] == ["31-1121"]

    def test_a_hybrid_match_says_it_is_a_hybrid(self) -> None:
        match = self._payload("21-1011")["occupations"][0]["match"]
        assert match["kind"] == "bls_hybrid_occupation"

    def test_an_exact_match_is_labelled_exact_and_keeps_its_education(self) -> None:
        occupation = self._payload("15-1252")["occupations"][0]
        assert occupation["match"]["kind"] == MATCH_EXACT
        assert occupation["match"]["entry_level_education_withheld"] is False
        assert occupation["entry_level_education"] == "Bachelor's degree"

    def test_a_masters_from_the_other_half_of_a_hybrid_is_not_shown(self) -> None:
        """The whole reason this was not wired in sooner.

        21-1018's "Master's degree" comes from its mental-health-counselor half. Attached to
        a community-college substance-use-counseling certificate it tells someone their
        credential does not qualify them for the job it does qualify them for.
        """
        occupation = self._payload("21-1011")["occupations"][0]
        assert occupation["entry_level_education"] is None
        assert occupation["match"]["entry_level_education_withheld"] is True

    def test_a_bachelors_from_the_technologist_half_is_not_shown_to_a_technician(self) -> None:
        occupation = self._payload("29-2012")["occupations"][0]
        assert occupation["entry_level_education"] is None
        assert occupation["match"]["entry_level_education_withheld"] is True

    def test_education_is_withheld_even_where_the_aggregate_happens_to_agree(self) -> None:
        # 31-1120's "High school diploma or equivalent" is very likely right for a home
        # health aide certificate. Keeping it anyway would mean deciding case by case which
        # aggregate's credential fits, which is the similarity judgement the mapping module
        # refuses to make, in a place nobody could audit it.
        occupation = self._payload("31-1121")["occupations"][0]
        assert occupation["entry_level_education"] is None
        assert occupation["match"]["entry_level_education_withheld"] is True

    def test_the_other_figures_survive_the_aggregate_match(self) -> None:
        # A median wage over a wider population is still an estimate of a population this
        # trainee is in, and it is the only one California publishes for them.
        occupation = self._payload("31-1121")["occupations"][0]
        assert occupation["median_annual_wage"] == 41600.0
        assert occupation["total_job_openings"] == 190.0
        assert occupation["percent_change"] == 10.0
        assert occupation["title"] == "Home Health and Personal Care Aides"

    def test_a_missing_education_is_not_reported_as_withheld(self) -> None:
        # Two absences that would otherwise render as the same null: EDD published no
        # credential for 47-4090, so there was nothing for this pipeline to decline.
        occupation = self._payload("47-4099")["occupations"][0]
        assert occupation["entry_level_education"] is None
        assert occupation["match"]["entry_level_education_withheld"] is False

    def test_two_codes_collapsing_onto_one_aggregate_yield_one_row(self) -> None:
        payload = self._payload("31-1121", "31-1122")
        assert [o["soc_code"] for o in payload["occupations"]] == ["31-1120"]
        assert payload["occupations"][0]["match"]["program_soc_codes"] == ["31-1121", "31-1122"]

    def test_an_already_matched_program_keeps_its_exact_row_and_gains_the_aggregate(self) -> None:
        # The 74-program case: the exact match was never at risk, and the added row is
        # labelled so the page can tell the reader which is which.
        payload = self._payload("15-1252", "29-2012")
        assert [o["soc_code"] for o in payload["occupations"]] == ["15-1252", "29-2010"]
        assert [o["match"]["kind"] for o in payload["occupations"]] == [
            MATCH_EXACT,
            "soc_broad_group",
        ]
        assert payload["occupations"][0]["entry_level_education"] == "Bachelor's degree"
        assert payload["occupations"][1]["entry_level_education"] is None

    def test_an_unresolvable_code_is_still_dropped_rather_than_guessed_at(self) -> None:
        # 19-3094 Political Scientists: no published parent, and the residual sibling
        # 19-3099 is by definition the social scientists who are not political scientists.
        assert self._payload("19-3094")["occupations"] == []

    def test_every_occupation_row_carries_a_match_block(self) -> None:
        # A consumer must never have to guess, so the key is present on exact matches too.
        payload = self._payload("15-1252", "21-1011", "47-4099")
        for occupation in payload["occupations"]:
            assert set(occupation["match"]) == {
                "kind",
                "program_soc_codes",
                "entry_level_education_withheld",
            }

    def test_the_feed_order_is_preserved(self) -> None:
        payload = self._payload("21-1011", "15-1252")
        assert [o["soc_code"] for o in payload["occupations"]] == ["21-1018", "15-1252"]


class TestMatchKindResolution:
    """``match_occupations`` on its own, including cases the live snapshot does not have."""

    def _published(self) -> dict:
        return {"15-1252": {}, "31-1120": {}, "31-1121": {}, "21-1018": {}}

    def test_a_code_published_under_its_own_name_is_exact_even_if_it_has_a_parent(self) -> None:
        # 31-1121 is a member of 31-1120 in the table, but this snapshot publishes it
        # directly, so resolving it to its parent would discard detail EDD does have.
        matches = match_occupations(["31-1121"], self._published())
        assert [(m.soc_code, m.kind) for m in matches] == [("31-1121", MATCH_EXACT)]

    def test_an_exact_match_wins_over_an_aggregate_reaching_the_same_occupation(self) -> None:
        # DOL naming the published code itself is a stronger claim than one derived here.
        published = {"31-1120": {}, "15-1252": {}}
        matches = match_occupations(["31-1122", "31-1120"], published)
        assert len(matches) == 1
        assert matches[0].kind == MATCH_EXACT
        assert matches[0].program_soc_codes == ("31-1122", "31-1120")

    def test_is_aggregate_is_the_complement_of_exact(self) -> None:
        published = {"21-1018": {}, "15-1252": {}}
        matches = match_occupations(["15-1252", "21-1014"], published)
        assert [m.is_aggregate for m in matches] == [False, True]

    def test_a_target_the_snapshot_does_not_publish_is_not_invented(self) -> None:
        # The mapping table is checked against the live snapshot at call time, not trusted.
        assert match_occupations(["21-1014"], {"15-1252": {}}) == []

    def test_a_malformed_code_is_dropped_rather_than_raising(self) -> None:
        matches = match_occupations(["not-a-soc", "15-1252"], self._published())
        assert [m.soc_code for m in matches] == ["15-1252"]


class TestAggregateMatchCoverage:
    """The aggregate half of the join is published, not folded into the headline."""

    def _payload(self, *kinds: tuple[str, bool]) -> dict:
        return {
            "occupations": [
                {"match": {"kind": kind, "entry_level_education_withheld": withheld}}
                for kind, withheld in kinds
            ]
        }

    def test_counts_programs_rows_and_withheld_credentials(self) -> None:
        report = aggregate_match_coverage(
            [
                self._payload((MATCH_EXACT, False)),
                self._payload(("soc_broad_group", True)),
                self._payload((MATCH_EXACT, False), ("bls_hybrid_occupation", True)),
                self._payload(("soc_broad_group", False)),
                self._payload(),
            ]
        )
        assert report.programs == 3
        assert report.occupation_matches == 3
        assert report.programs_with_education_withheld == 2

    def test_separates_programs_recovered_from_programs_that_merely_gained_a_row(self) -> None:
        # Only the first would show no occupation at all without the aggregation.
        report = aggregate_match_coverage(
            [
                self._payload(("soc_broad_group", True)),
                self._payload((MATCH_EXACT, False), ("soc_broad_group", True)),
            ]
        )
        assert report.programs == 2
        assert report.recovered_programs == 1

    def test_a_build_with_no_aggregate_matches_reports_zeros(self) -> None:
        report = aggregate_match_coverage([self._payload((MATCH_EXACT, False))])
        assert report.programs == 0
        assert report.recovered_programs == 0
        assert report.occupation_matches == 0
        assert report.programs_with_education_withheld == 0


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

    def test_says_the_list_came_from_the_classification(self) -> None:
        # Without O*NET this is a claim about filing, not about the work, and the record has
        # to say so rather than let the page imply the stronger one.
        assert self._occupations()["29-1141"]["related_source"] == RELATED_SOURCE_SOC_SIBLINGS

    def test_an_occupation_with_no_answer_names_no_source(self) -> None:
        occupation = self._occupations()["15-1252"]
        assert occupation["related"] == []
        assert occupation["related_source"] is None


ENRICHED_RN = OccupationEnrichment(
    soc_code="29-1141",
    onet_code="29-1141.00",
    description="Assess patient health problems and needs.",
    skills=(
        Skill(name="Critical Thinking", importance=4.0),
        Skill(name="Unrated", importance=None),
    ),
    # 29-2052 is projected by EDD in the fixture below; 31-9091 is not.
    related=(("29-2052", "Pharmacy Techs"), ("31-9091", "Dental Assistants")),
    bright_outlook="Rapid Growth; Numerous Job Openings",
)


class TestEnrichmentFields:
    """CareerOneStop fields reach the record without inventing anything."""

    def _occupations(self, enrichment: dict | None = None) -> dict:
        rows = list(parse_projections(TestRelatedOccupations.CSV))
        return index_occupations(rows, enrichment=enrichment)

    def test_attaches_the_description_and_bright_outlook(self) -> None:
        occupation = self._occupations({"29-1141": ENRICHED_RN})["29-1141"]
        assert occupation["description"] == "Assess patient health problems and needs."
        assert occupation["bright_outlook"] == "Rapid Growth; Numerous Job Openings"

    def test_an_unrated_skill_importance_stays_null(self) -> None:
        skills = self._occupations({"29-1141": ENRICHED_RN})["29-1141"]["skills"]
        assert skills == [
            {"name": "Critical Thinking", "importance": 4.0},
            {"name": "Unrated", "importance": None},
        ]

    def test_drops_related_occupations_edd_does_not_publish(self) -> None:
        # 31-9091 has no California projection, so it has no page, no wage and no openings.
        related_onet = self._occupations({"29-1141": ENRICHED_RN})["29-1141"]["related_onet"]
        assert related_onet == [{"soc_code": "29-2052", "title": "Pharmacy Techs"}]

    def test_an_unenriched_occupation_carries_empty_fields_not_missing_ones(self) -> None:
        occupation = self._occupations({"29-1141": ENRICHED_RN})["29-2061"]
        assert occupation["description"] is None
        assert occupation["bright_outlook"] is None
        assert occupation["skills"] == []
        assert occupation["related_onet"] == []

    def test_a_build_with_no_enrichment_still_writes_every_key(self) -> None:
        occupation = self._occupations()["29-1141"]
        assert occupation["description"] is None
        assert occupation["skills"] == []
        assert occupation["related_onet"] == []
        assert occupation["bright_outlook"] is None


class TestRelatedSource:
    """One source per occupation, named in the record. Never a blend of the two."""

    def _occupations(self, enrichment: dict) -> dict:
        rows = list(parse_projections(TestRelatedOccupations.CSV))
        return index_occupations(rows, enrichment=enrichment)

    def test_prefers_onet_over_the_soc_siblings(self) -> None:
        occupation = self._occupations({"29-1141": ENRICHED_RN})["29-1141"]
        assert occupation["related_source"] == RELATED_SOURCE_ONET
        assert [r["soc_code"] for r in occupation["related"]] == ["29-2052"]

    def test_does_not_pad_an_onet_list_with_siblings(self) -> None:
        # 29-2061 is a sibling with three times the openings of the one O*NET named. Adding
        # it would leave the page unable to say what either row means.
        occupation = self._occupations({"29-1141": ENRICHED_RN})["29-1141"]
        assert "29-2061" not in {r["soc_code"] for r in occupation["related"]}

    def test_falls_back_to_siblings_for_an_unenriched_occupation(self) -> None:
        occupation = self._occupations({"29-1141": ENRICHED_RN})["29-2052"]
        assert occupation["related_source"] == RELATED_SOURCE_SOC_SIBLINGS
        assert [r["soc_code"] for r in occupation["related"]] == ["29-1141", "29-2061"]

    def test_falls_back_when_nothing_onet_named_is_published_here(self) -> None:
        stranded = OccupationEnrichment(
            soc_code="29-1141",
            onet_code="29-1141.00",
            description="Assess patient health problems and needs.",
            skills=(),
            related=(("31-9091", "Dental Assistants"),),
            bright_outlook=None,
        )
        occupation = self._occupations({"29-1141": stranded})["29-1141"]
        assert occupation["related_onet"] == []
        assert occupation["related_source"] == RELATED_SOURCE_SOC_SIBLINGS
        assert {r["soc_code"] for r in occupation["related"]} == {"29-2061", "29-2052"}

    def test_onet_can_relate_across_major_groups_where_the_hierarchy_cannot(self) -> None:
        # The point of preferring O*NET: 15-1252 has no SOC siblings here at all, and the
        # classification therefore has nothing to say about work that resembles it.
        crossing = OccupationEnrichment(
            soc_code="15-1252",
            onet_code="15-1252.00",
            description=None,
            skills=(),
            related=(("29-1141", "Registered Nurses"),),
            bright_outlook=None,
        )
        occupation = self._occupations({"15-1252": crossing})["15-1252"]
        assert occupation["related_source"] == RELATED_SOURCE_ONET
        assert [r["soc_code"] for r in occupation["related"]] == ["29-1141"]

    def test_related_rows_carry_this_datasets_own_figures_and_title(self) -> None:
        # The link text has to match the heading of the page it opens, so EDD's title wins
        # over O*NET's wording for the same occupation.
        row = self._occupations({"29-1141": ENRICHED_RN})["29-1141"]["related"][0]
        assert row == {
            "soc_code": "29-2052",
            "title": "Pharmacy Technicians",
            "median_annual_wage": 52000.0,
            "total_job_openings": 100.0,
            "percent_change": 5.0,
        }

    def test_never_relates_an_occupation_to_itself(self) -> None:
        looping = OccupationEnrichment(
            soc_code="29-1141",
            onet_code="29-1141.00",
            description=None,
            skills=(),
            # A specialisation collapses onto the occupation it specialises.
            related=(("29-1141", "Registered Nurses"), ("29-2061", "Licensed Practical Nurses")),
            bright_outlook=None,
        )
        occupation = self._occupations({"29-1141": looping})["29-1141"]
        assert [r["soc_code"] for r in occupation["related"]] == ["29-2061"]


class TestEnrichmentCoverage:
    """The counts published in coverage.json come from the records, not from the fetch."""

    def _report(self, enrichment: dict) -> EnrichmentCoverage:
        rows = list(parse_projections(TestRelatedOccupations.CSV))
        return enrichment_coverage(index_occupations(rows, enrichment=enrichment))

    def test_counts_descriptions_and_related_sources(self) -> None:
        report = self._report({"29-1141": ENRICHED_RN})
        assert report.occupations == 4
        assert report.enriched == 1
        assert report.with_description == 1
        assert report.with_skills == 1
        assert report.with_bright_outlook == 1
        assert report.related_from_onet == 1
        # 29-2061 and 29-2052 still have each other and the RN row.
        assert report.related_from_soc_siblings == 2
        # 15-1252 is alone in its major group and O*NET named nothing for it.
        assert report.without_related == 1

    def test_a_build_without_credentials_reports_zeros_not_an_absence(self) -> None:
        report = self._report({})
        assert report.enriched == 0
        assert report.with_description == 0
        assert report.related_from_onet == 0
        assert report.related_from_soc_siblings == 3
        assert report.without_related == 1


class TestDetailedSocCodes:
    def test_lists_only_the_occupations_that_will_be_published(self) -> None:
        rows = list(parse_projections(TestRegionalProjectionOnPrograms.CSV))
        # Statewide detailed rows only: the Fresno rows repeat SOCs already listed, and a
        # rollup like 00-0000 is not an occupation anyone can train for.
        assert detailed_soc_codes(rows) == ["15-1252", "29-1141", "15-1211"]

    def test_excludes_summary_rows(self) -> None:
        assert "00-0000" not in detailed_soc_codes(parse_projections(PROJECTION_CSV))


CACHED_RESPONSE = {
    "OccupationDetail": [
        {
            "OnetCode": "29-1141.00",
            "OnetDescription": "Assess patient health problems and needs.",
            "SkillsDataList": [{"ElementName": "Critical Thinking", "DataValue": "4"}],
            "RelatedOnetTitles": {"29-2061.00": "Licensed Practical Nurses"},
        }
    ]
}


class TestFetchEnrichment:
    """CI has no credentials, and a warm cache must not touch the network."""

    def test_without_credentials_returns_nothing_and_asks_nobody(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(USER_ID_ENV, raising=False)
        monkeypatch.delenv(TOKEN_ENV, raising=False)

        import httpx

        def explode(*args: object, **kwargs: object) -> None:
            raise AssertionError("attempted a request without credentials")

        monkeypatch.setattr(httpx.Client, "get", explode)
        assert fetch_enrichment(["29-1141", "15-1252"]) == {}

    def test_a_warm_cache_is_served_without_a_request(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """...but only an entry that answers the request actually being made.

        The response shape follows the query parameters, so an entry fetched before the
        client asked for tasks, alternate titles and education is not a smaller version of
        today's answer, it is that answer with fields missing. Serving it would put "this
        occupation reports no tasks" on a page when the truth is that nobody asked, so
        widening the parameter set has to cost a refetch rather than pass silently.
        """
        import httpx

        from afterward.sources.careeronestop import REQUEST_PARAMS, cache_envelope

        monkeypatch.setenv(USER_ID_ENV, "user")
        monkeypatch.setenv(TOKEN_ENV, "token")
        entry = tmp_path / "29-1141.00.json"

        def explode(*args: object, **kwargs: object) -> None:
            raise AssertionError("hit the network despite a warm cache")

        monkeypatch.setattr(httpx.Client, "get", explode)

        entry.write_text(
            json.dumps(cache_envelope(CACHED_RESPONSE, onet_code="29-1141.00", state="CA")),
            encoding="utf-8",
        )
        found = fetch_enrichment(["29-1141"], cache_dir=tmp_path)
        assert set(found) == {"29-1141"}
        assert found["29-1141"].description == "Assess patient health problems and needs."

        # The same response, recorded as having been fetched without tasks. Reaching the
        # network is the assertion here: it is what a stale entry must cost.
        narrow = cache_envelope(CACHED_RESPONSE, onet_code="29-1141.00", state="CA")
        narrow["request"]["params"] = {**REQUEST_PARAMS, "tasks": "false"}
        entry.write_text(json.dumps(narrow), encoding="utf-8")
        with pytest.raises(AssertionError, match="hit the network"):
            fetch_enrichment(["29-1141"], cache_dir=tmp_path)


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


class TestSearchEntryArea:
    """The search index must be able to filter by area without inventing one."""

    def _entry(
        self, region: dict | None, city: str | None = "Fresno", cohort: dict | None = None
    ) -> dict:
        program = {
            "uuid": "u1",
            "program_name": "Software Development",
            "provider_name": "Fresno City College",
            "location": {"city": city},
            "region": region,
            "cost": {"total_out_of_pocket": None, "total_is_complete": True},
            "length": {"weeks": None},
            "soc_codes": [],
            "occupations": [],
            "outcomes": {
                "completion_rate": None,
                "employment_rate_q2": None,
                "median_earnings": None,
                "reported": False,
                "cohort": cohort or CLEAN_COHORT,
            },
        }
        return search_entry(program)

    def test_a_placed_program_carries_its_areas_short_name(self) -> None:
        entry = self._entry(
            {
                "area_name": "Fresno MSA (Fresno and Madera Counties)",
                "area_short_name": "Fresno MSA",
                "area_type": "Metropolitan Area",
                "matched_on": "principal_city",
            }
        )
        # The short name only: the county gloss in area_name is a fetch away on the program
        # page and would cost payload on every row for a filter that never reads it.
        assert entry["a"] == "Fresno MSA"

    def test_an_unplaced_program_carries_null_not_a_bucket(self) -> None:
        # Clovis is minutes from Fresno and in Fresno County. EDD does not name it, so the
        # index says so rather than filing it under the area a reader would assume.
        entry = self._entry(None, city="Clovis")
        assert entry["a"] is None
        assert entry["c"] == "Clovis"

    def test_the_key_is_always_written(self) -> None:
        # So a consumer can tell an unplaced program from an index built before this field.
        assert "a" in self._entry(None)


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
                    "cohort": CLEAN_COHORT,
                }
            }
            for v in values
        ]

    def _unattributable(self, value: float) -> dict:
        return {
            "outcomes": {
                "completion_rate": value,
                "employment_rate_q2": value,
                "median_earnings": value,
                "cohort": dict(CLEAN_COHORT, attributable=False),
            }
        }

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

    def test_a_cohort_we_will_not_attribute_does_not_vote(self) -> None:
        """One institution-level filing stamped on ten programs must not move the yardstick.

        Left in, it would be counted once per row it was copied onto, so the median every
        other program is judged against would be partly a single provider's paperwork.
        """
        result = peer_medians(
            [*self._payloads(0.4, 0.5, 0.6), *(self._unattributable(0.9) for _ in range(10))]
        )
        assert result["completion_rate"]["median"] == 0.5
        assert result["completion_rate"]["reporting"] == 3

    def test_the_exclusions_are_published_rather_than_hidden(self) -> None:
        result = peer_medians([*self._payloads(0.5), self._unattributable(0.9)])
        assert result["employment_rate_q2"]["excluded_not_attributable"] == 1

    def test_nothing_is_excluded_when_every_cohort_is_this_programs_own(self) -> None:
        result = peer_medians(self._payloads(0.5, None))
        assert result["median_earnings"]["excluded_not_attributable"] == 0


class TestCoverageShape:
    """A key missing from coverage.json deletes a comparison without deleting anything visible.

    That already happened once: a snapshot built before `state_benchmark` existed removed every
    statewide comparison from all 2,057 outcome pages, and the only symptom was three fewer
    lines. These tests are the guard that turns it into a failed build.
    """

    def _document(self, **overrides: object) -> dict:
        document = {key: 1 for key in SITE_COVERAGE_KEYS}
        document["snapshot_date"] = "2026-08-04"
        document["state_benchmark"] = {"state": "CA"}
        document["peer_medians"] = {
            measure: {"median": 0.5, "reporting": 3} for measure in PEER_MEASURES
        }
        return document | overrides

    def test_a_complete_document_passes(self) -> None:
        assert coverage_shape_problems(self._document()) == []
        check_coverage_shape(self._document())

    def test_an_absent_key_is_reported(self) -> None:
        document = self._document()
        del document["peer_medians"]
        assert coverage_shape_problems(document) == ["peer_medians: absent"]

    def test_a_null_where_the_site_expects_a_number_is_reported(self) -> None:
        # Not "we counted nothing" — a build that failed to count, rendered as a blank.
        assert coverage_shape_problems(self._document(total_programs=None)) == [
            "total_programs: null"
        ]

    def test_a_null_state_benchmark_is_allowed(self) -> None:
        """DOL publishing no statewide row is a finding, and the site types it nullable."""
        assert coverage_shape_problems(self._document(state_benchmark=None)) == []

    def test_a_peer_median_missing_one_measure_is_reported(self) -> None:
        # The measure with no median silently loses its comparison and keeps the other two,
        # which is the hardest version of this to notice.
        document = self._document(peer_medians={"completion_rate": {"median": 0.5, "reporting": 3}})
        assert coverage_shape_problems(document) == [
            "peer_medians.employment_rate_q2: absent",
            "peer_medians.median_earnings: absent",
        ]

    def test_every_shortfall_is_listed_not_just_the_first(self) -> None:
        document = self._document()
        del document["distinct_providers"]
        del document["outcome_coverage_pct"]
        assert coverage_shape_problems(document) == [
            "distinct_providers: absent",
            "outcome_coverage_pct: absent",
        ]

    def test_the_build_refuses_rather_than_filling_in_a_default(self) -> None:
        """A default invented here would publish a number the build did not compute."""
        document = self._document()
        del document["state_benchmark"]
        with pytest.raises(ValueError, match="state_benchmark: absent"):
            check_coverage_shape(document)

    def test_an_offline_build_emits_a_document_the_site_can_read(self, tmp_path: Path) -> None:
        """The fixture path copies its coverage block through, so it is checked end to end."""
        build_offline(FIXTURE_DIR, output_dir=tmp_path)
        emitted = json.loads((tmp_path / "coverage.json").read_text(encoding="utf-8"))
        assert coverage_shape_problems(emitted) == []


_MEASURES = ("median_earnings", "employment_rate_q2", "completion_rate")
"""The three headline measures `programs_with_any_outcome` is a count of."""


def _outcomes(**overrides: object) -> dict:
    """One emitted outcomes block, reporting all three headline measures."""
    return {
        "total_served": 20.0,
        "total_exited": 18.0,
        "total_completed": 15.0,
        "completion_rate": 0.83,
        "credentials_earned": 12.0,
        "median_earnings": 9500.0,
        "employment_rate_q2": 0.72,
        "employed_q2": 13.0,
        "employed_q4": 12.0,
        "reported": True,
    } | overrides


def _outcome_payload(uuid: str = "p1", **overrides: object) -> dict:
    return {"uuid": uuid, "outcomes": _outcomes(**overrides)}


def _no_outcome_payload(uuid: str = "p2") -> dict:
    """A program whose three headline measures were all withheld or never filed."""
    return _outcome_payload(uuid, reported=False, **dict.fromkeys(_MEASURES))


class TestCoverageCounts:
    """A coverage figure that does not describe the dataset published beside it.

    `check_coverage_shape` asks whether the numbers are there. These ask whether they are true
    of the programs being written out in the same breath, which is the question that survives
    the figures being quoted somewhere nobody can check them against the data.
    """

    def _document(self, payloads: list[dict], **overrides: object) -> dict:
        total = len(payloads)
        with_any = sum(
            1 for p in payloads if any(p["outcomes"][measure] is not None for measure in _MEASURES)
        )
        document = {
            "total_programs": total,
            "programs_with_any_outcome": with_any,
            "programs_with_median_earnings": sum(
                1 for p in payloads if p["outcomes"]["median_earnings"] is not None
            ),
            "programs_with_employment_rate": sum(
                1 for p in payloads if p["outcomes"]["employment_rate_q2"] is not None
            ),
            "programs_with_completion_rate": sum(
                1 for p in payloads if p["outcomes"]["completion_rate"] is not None
            ),
            "outcome_coverage_pct": round(100.0 * with_any / total, 1) if total else 0.0,
        }
        return document | overrides

    def test_a_document_that_matches_its_payloads_passes(self) -> None:
        payloads = [_outcome_payload("a"), _outcome_payload("b")]
        assert coverage_count_problems(self._document(payloads), payloads) == []
        check_coverage_counts(self._document(payloads), payloads)

    def test_a_stale_total_is_caught(self) -> None:
        """The fixture path carries this key through untouched; this is what notices."""
        payloads = [_outcome_payload("a")]
        problems = coverage_count_problems(self._document(payloads, total_programs=3266), payloads)
        assert problems == ["total_programs: says 3266, emitted programs give 1"]

    def test_a_stale_outcome_count_is_caught(self) -> None:
        payloads = [_outcome_payload("a"), _outcome_payload("b", median_earnings=None)]
        problems = coverage_count_problems(
            self._document(payloads, programs_with_median_earnings=2), payloads
        )
        assert problems == ["programs_with_median_earnings: says 2, emitted programs give 1"]

    def test_a_percentage_that_disagrees_with_its_own_counts_is_caught(self) -> None:
        """The number in the footer of every page, checked against the programs behind it."""
        payloads = [_outcome_payload("a"), _no_outcome_payload("b")]
        problems = coverage_count_problems(
            self._document(payloads, outcome_coverage_pct=63.0), payloads
        )
        assert problems == ["outcome_coverage_pct: says 63.0, 1 of 2 emitted programs give 50.0"]

    def test_a_program_reporting_nothing_is_counted_as_such(self) -> None:
        payloads = [_outcome_payload("a"), _no_outcome_payload("b")]
        assert coverage_count_problems(self._document(payloads), payloads) == []

    def test_every_disagreement_is_listed_not_just_the_first(self) -> None:
        payloads = [_outcome_payload("a")]
        problems = coverage_count_problems(
            self._document(payloads, total_programs=9, programs_with_completion_rate=9), payloads
        )
        assert problems == [
            "total_programs: says 9, emitted programs give 1",
            "programs_with_completion_rate: says 9, emitted programs give 1",
        ]

    def test_the_build_refuses_rather_than_correcting_the_number(self) -> None:
        payloads = [_outcome_payload("a")]
        with pytest.raises(ValueError, match="total_programs: says 3266"):
            check_coverage_counts(self._document(payloads, total_programs=3266), payloads)

    def test_an_empty_dataset_does_not_divide_by_zero(self) -> None:
        assert coverage_count_problems(self._document([]), []) == []

    def test_an_offline_build_publishes_counts_its_own_programs_support(
        self, tmp_path: Path
    ) -> None:
        """End to end on the path that carries the fixture's arithmetic through."""
        build_offline(FIXTURE_DIR, output_dir=tmp_path)
        emitted = json.loads((tmp_path / "coverage.json").read_text(encoding="utf-8"))
        payloads = json.loads((tmp_path / "programs.json").read_text(encoding="utf-8"))["programs"]
        assert coverage_count_problems(emitted, payloads) == []


class TestOutcomeIntegrity:
    """A number on the page that nobody measured.

    `-1` is how the ETP scorecard says "withheld". It is mapped to None where it enters, and
    these are the check at the end that publishes, because that is where it would be read as a
    finding about a real school rather than as a sentinel.
    """

    def test_a_clean_record_passes(self) -> None:
        assert outcome_integrity_problems([_outcome_payload()]) == []
        check_outcome_integrity([_outcome_payload()])

    def test_a_record_reporting_nothing_passes(self) -> None:
        assert outcome_integrity_problems([_no_outcome_payload("p1")]) == []

    def test_the_suppression_sentinel_reaching_output_is_caught(self) -> None:
        problems = outcome_integrity_problems([_outcome_payload(median_earnings=-1)])
        assert problems == ["p1.median_earnings: the -1 sentinel reached output"]

    def test_a_rate_above_one_is_caught(self) -> None:
        problems = outcome_integrity_problems([_outcome_payload(completion_rate=1.4)])
        assert problems == ["p1.completion_rate: 1.4 is not a proportion"]

    def test_a_negative_headcount_is_caught(self) -> None:
        problems = outcome_integrity_problems([_outcome_payload(employed_q2=-4.0)])
        assert problems == ["p1.employed_q2: -4.0 is a negative headcount"]

    def test_a_genuine_zero_is_not_a_problem(self) -> None:
        """A reported zero is a fact about a real cohort, and is not a suppressed cell."""
        assert (
            outcome_integrity_problems([_outcome_payload(employment_rate_q2=0.0, employed_q2=0.0)])
            == []
        )

    def test_a_reported_flag_that_hides_published_measures_is_caught(self) -> None:
        """False over three real numbers renders a "not reported" notice over reported data."""
        problems = outcome_integrity_problems([_outcome_payload(reported=False)])
        assert problems == ["p1.reported: says False, which its own measures contradict"]

    def test_a_reported_flag_claiming_measures_that_are_absent_is_caught(self) -> None:
        payload = _outcome_payload(**dict.fromkeys(_MEASURES))
        assert outcome_integrity_problems([payload]) == [
            "p1.reported: says True, which its own measures contradict"
        ]

    def test_the_build_refuses_rather_than_clamping(self) -> None:
        with pytest.raises(ValueError, match="sentinel reached output"):
            check_outcome_integrity([_outcome_payload(median_earnings=-1)])

    def test_the_message_names_the_program_and_caps_the_list(self) -> None:
        payloads = [_outcome_payload(f"p{i}", completion_rate=2.0) for i in range(14)]
        with pytest.raises(ValueError, match=r"and 4 more"):
            check_outcome_integrity(payloads)

    def test_an_offline_build_emits_no_unmeasured_outcome(self, tmp_path: Path) -> None:
        build_offline(FIXTURE_DIR, output_dir=tmp_path)
        payloads = json.loads((tmp_path / "programs.json").read_text(encoding="utf-8"))["programs"]
        assert outcome_integrity_problems(payloads) == []


class TestCohortLabellingOnProgramRecords:
    """The figures survive; the claim that they measure this program does not."""

    def _programs(self, *sources: dict) -> list:
        return [parse_program({"_source": s}) for s in sources]

    def _payloads(self, *sources: dict) -> list[dict]:
        programs = self._programs(*sources)
        verdicts = cohort_integrity([CohortFiling.of(p) for p in programs])
        return [
            program_payload(p, _occupations(), cohort=c)
            for p, c in zip(programs, verdicts, strict=True)
        ]

    def _desert(self, uuid: str, **extra: object) -> dict:
        return {
            "field_uuid": uuid,
            "field_etp": "COLLEGE OF THE DESERT",
            "field_c_total_served": 8692,
            "field_c_total_exited": 1837,
            "field_c_total_completed": 1618,
            "field_c_completed_percent": 0.88,
            "field_c_q2_employment_percent": 0.04,
            **extra,
        }

    def test_a_shared_cohort_keeps_every_figure_it_reported(self) -> None:
        """Marking, not deleting. The filings are real and a reader may want to see them.

        Nulling them would say "not reported", which is false, and is the single confusion
        this dataset exists to prevent.
        """
        outcomes = self._payloads(self._desert("a"), self._desert("b"))[0]["outcomes"]
        assert outcomes["total_served"] == 8692.0
        assert outcomes["employment_rate_q2"] == 0.04
        assert outcomes["reported"] is True

    def test_a_shared_cohort_says_it_is_not_this_programs(self) -> None:
        outcomes = self._payloads(self._desert("a"), self._desert("b"))[0]["outcomes"]
        assert outcomes["cohort"]["attributable"] is False
        assert outcomes["cohort"]["shared_with_sibling_programs"] == 1

    def test_an_ordinary_program_carries_the_block_saying_nothing_is_wrong(self) -> None:
        payload = self._payloads({"field_uuid": "u", "field_etp": "p"})[0]
        assert payload["outcomes"]["cohort"] == CLEAN_COHORT

    def test_a_record_built_alone_still_reports_its_own_contradiction(self) -> None:
        program = parse_program(
            {
                "_source": {
                    "field_uuid": "u",
                    "field_etp": "Lemoore College",
                    "field_c_total_served": 1796,
                    "field_c_total_exited": 5214,
                }
            }
        )
        cohort = program_payload(program, _occupations())["outcomes"]["cohort"]
        assert cohort["exited_exceeds_served"] is True
        assert cohort["internally_consistent"] is False

    def test_the_search_index_row_carries_the_same_verdict(self) -> None:
        payloads = self._payloads(self._desert("a"), self._desert("b"))
        entry = search_entry(payloads[0])
        assert entry["at"] is False
        # …and still carries the numbers, so a null in the index keeps meaning "not
        # reported" rather than "we declined to attribute this".
        assert entry["er"] == 0.04
        assert entry["r"] is True

    def test_a_clean_program_is_marked_comparable_in_the_index(self) -> None:
        entry = search_entry(self._payloads({"field_uuid": "u", "field_etp": "p"})[0])
        assert entry["at"] is True


class TestCohortIntegrityCoverage:
    """The scale of what was marked is published, not swallowed."""

    def _payloads(self, *cohorts: dict) -> list[dict]:
        return [
            {
                "provider_name": f"provider {index}",
                "outcomes": {
                    "total_served": 10.0,
                    "total_exited": 10.0,
                    "total_completed": 10.0,
                    "cohort": dict(CLEAN_COHORT, **cohort),
                },
            }
            for index, cohort in enumerate(cohorts)
        ]

    def test_counts_shared_cohorts_and_recovers_their_grouping(self) -> None:
        # One group of three and one of two: five programs, two groups, largest three.
        shared = [{"shared_with_sibling_programs": 2, "attributable": False}] * 3
        pair = [{"shared_with_sibling_programs": 1, "attributable": False}] * 2
        report = cohort_integrity_coverage(self._payloads(*shared, *pair, {}))
        assert report.shared_cohorts == 5
        assert report.shared_cohort_groups == 2
        assert report.largest_shared_cohort == 3

    def test_a_clean_build_reports_zeros_rather_than_an_absence(self) -> None:
        report = cohort_integrity_coverage(self._payloads({}, {}))
        assert report.shared_cohorts == 0
        assert report.shared_cohort_groups == 0
        assert report.largest_shared_cohort == 0
        assert report.not_attributable == 0

    def test_contradictions_are_counted_per_violation_and_as_a_union(self) -> None:
        report = cohort_integrity_coverage(
            self._payloads(
                {"exited_exceeds_served": True, "internally_consistent": False},
                {
                    "exited_exceeds_served": True,
                    "completed_exceeds_served": True,
                    "internally_consistent": False,
                },
                {},
            )
        )
        assert report.exited_exceeds_served == 2
        assert report.completed_exceeds_served == 1
        assert report.internally_contradictory == 2

    def test_oversized_rows_are_counted_with_the_providers_behind_them(self) -> None:
        payloads = self._payloads(
            {"oversized_for_one_program": True, "attributable": False},
            {"oversized_for_one_program": True, "attributable": False},
            {},
        )
        payloads[1]["provider_name"] = payloads[0]["provider_name"]
        report = cohort_integrity_coverage(payloads)
        assert report.oversized_for_one_program == 2
        assert report.oversized_providers == 1

    def test_the_union_is_published_because_the_overlap_is_invisible(self) -> None:
        report = cohort_integrity_coverage(
            self._payloads(
                {
                    "shared_with_sibling_programs": 1,
                    "oversized_for_one_program": True,
                    "attributable": False,
                },
                {"shared_with_sibling_programs": 1, "attributable": False},
                {},
            )
        )
        assert report.shared_cohorts == 2
        assert report.oversized_for_one_program == 1
        assert report.not_attributable == 2

    def test_silence_is_not_counted_as_a_cohort(self) -> None:
        payloads = self._payloads({}, {})
        for key in ("total_served", "total_exited", "total_completed"):
            payloads[0]["outcomes"][key] = None
        assert cohort_integrity_coverage(payloads).programs_with_cohort_counts == 1


# --------------------------------------------------------------------------------------
# Provider links
# --------------------------------------------------------------------------------------

GOOD = "https://a.edu/welding"
MISSING = "https://b.edu/programs/welding.aspx"
B_ROOT = "https://b.edu/"


def _check(url: str, reason: Reason, upgrade: str | None = None) -> LinkCheck:
    return LinkCheck(
        url=url,
        verdict=VERDICT_BY_REASON[reason],
        reason=reason,
        status_code=None,
        final_url=None,
        https_alternative=upgrade,
        detail=None,
        checked_at=datetime(2026, 8, 4, 9, 0, tzinfo=UTC),
        attempts=1,
    )


def _checks(*checks: LinkCheck) -> dict[str, LinkCheck]:
    return {check.url: check for check in checks}


def _with_url(uuid: str, url: str | None) -> dict:
    source: dict[str, object] = {"field_uuid": uuid, "field_etp": "Provider"}
    if url is not None:
        source["field_program_url"] = url
    return {"_source": source}


def _payload(url: str | None, checks: dict[str, LinkCheck] | None = None) -> dict:
    return program_payload(
        parse_program(_with_url("u", url)), _occupations(), link_checks=checks or {}
    )


class TestProviderLinkOnProgramRecords:
    """What a program record says about the link the site puts in front of a reader."""

    def test_a_build_with_no_link_data_publishes_the_link_exactly_as_filed(self) -> None:
        """The CI case, and the case before any of this existed. Unchecked is not dead."""
        link = _payload(GOOD)["provider_link"]
        assert link["href"] == GOOD
        assert link["linked"] is True
        assert link["label"] == LABEL_PROGRAM_PAGE

    def test_a_build_with_no_link_data_claims_nothing(self) -> None:
        link = _payload(GOOD)["provider_link"]
        assert link["verdict"] is None
        assert link["checked_on"] is None
        assert link["notice"] is None

    def test_the_block_is_always_written_so_a_gap_is_visible(self) -> None:
        """Absent would be indistinguishable from a dataset built before the field existed;
        the key is present and its verdict is null, which says "nobody looked"."""
        assert "provider_link" in _payload(GOOD)

    def test_a_program_with_no_website_has_no_link_block(self) -> None:
        """Null here is "this provider filed no URL", which is 1,430 of California's 3,266
        programs and has nothing to do with the check."""
        payload = _payload(None)
        assert payload["program_url"] is None
        assert payload["provider_link"] is None

    def test_a_dead_name_is_published_without_a_link(self) -> None:
        link = _payload(GOOD, _checks(_check(GOOD, "dns_failure")))["provider_link"]
        assert link["href"] is None
        assert link["linked"] is False
        assert link["notice"] == NOTICE_UNREACHABLE
        assert link["checked_on"] == "2026-08-04"

    def test_a_suppressed_link_still_carries_the_federal_records_url(self) -> None:
        payload = _payload(GOOD, _checks(_check(GOOD, "dns_failure")))
        assert payload["program_url"] == GOOD
        assert payload["provider_link"]["url"] == GOOD

    def test_a_404_with_a_working_front_page_is_sent_there_instead(self) -> None:
        checks = _checks(_check(MISSING, "not_found"), _check(B_ROOT, "ok"))
        link = _payload(MISSING, checks)["provider_link"]
        assert link["href"] == B_ROOT
        assert link["label"] == LABEL_PROVIDER_HOME
        assert link["substitution"] == SUBSTITUTION_FRONT_PAGE

    def test_a_verified_https_equivalent_is_swapped_in(self) -> None:
        insecure = "http://a.edu/welding"
        link = _payload(insecure, _checks(_check(insecure, "ok", upgrade=GOOD)))["provider_link"]
        assert link["href"] == GOOD
        assert link["substitution"] == SUBSTITUTION_HTTPS

    def test_the_records_own_url_is_never_rewritten(self) -> None:
        """`program_url` is the source's value. The decision sits beside it, not on top."""
        insecure = "http://a.edu/welding"
        payload = _payload(insecure, _checks(_check(insecure, "ok", upgrade=GOOD)))
        assert payload["program_url"] == insecure

    def test_a_link_we_could_not_judge_is_left_exactly_as_it_was(self) -> None:
        link = _payload(GOOD, _checks(_check(GOOD, "forbidden")))["provider_link"]
        assert link["href"] == GOOD
        assert link["linked"] is True
        assert link["notice"] is None


class TestProviderLinkPages:
    def test_counts_the_pages_behind_each_url(self) -> None:
        payloads = [{"program_url": GOOD}, {"program_url": GOOD}, {"program_url": MISSING}]
        assert provider_link_pages(payloads) == {GOOD: 2, MISSING: 1}

    def test_a_program_with_no_url_contributes_nothing(self) -> None:
        assert provider_link_pages([{"program_url": None}]) == {}


class TestLoadLinkChecks:
    def test_no_path_is_no_link_data(self) -> None:
        assert load_link_checks(None) == {}

    def test_an_absent_report_is_the_ordinary_case_not_an_error(self, tmp_path: Path) -> None:
        assert load_link_checks(tmp_path / "nothing-here.json") == {}

    def test_a_report_round_trips(self, tmp_path: Path) -> None:
        path = tmp_path / "link-checks.json"
        checks = _checks(_check(GOOD, "ok"))
        path.write_text(json.dumps(checks_document(checks)), encoding="utf-8")
        assert load_link_checks(path) == checks

    def test_a_report_that_cannot_be_read_is_raised_not_swallowed(self, tmp_path: Path) -> None:
        """Treating it as "nothing was checked" would republish links already established
        as broken, silently, because a file was malformed."""
        path = tmp_path / "link-checks.json"
        path.write_text('{"version": 99, "checks": []}', encoding="utf-8")
        with pytest.raises(ValueError, match="version"):
            load_link_checks(path)


class TestProviderLinkCoverage:
    def _payloads(self) -> list[dict]:
        checks = _checks(
            _check(GOOD, "ok"),
            _check(MISSING, "not_found"),
            _check(B_ROOT, "ok"),
            _check("http://c.edu", "ok", upgrade="https://c.edu/"),
            _check("https://d.edu/x", "dns_failure"),
            _check("https://e.edu/x", "forbidden"),
        )
        urls = [
            GOOD,
            GOOD,
            MISSING,
            "http://c.edu",
            "https://d.edu/x",
            "https://e.edu/x",
            "https://unchecked.edu/x",
            None,
        ]
        return [_payload(url, checks) for url in urls]

    def test_counts_the_programs_that_show_a_link_at_all(self) -> None:
        coverage = provider_link_coverage(self._payloads())
        assert coverage.programs_with_link == 7
        assert coverage.distinct_urls == 6

    def test_unchecked_is_its_own_number_and_never_folded_into_alive(self) -> None:
        coverage = provider_link_coverage(self._payloads())
        assert coverage.programs_unchecked == 1
        assert coverage.unchecked_urls == 1
        assert coverage.programs_alive == 3
        assert coverage.programs_checked == 6

    def test_counts_each_verdict_over_pages_rather_than_urls(self) -> None:
        """One dead domain on 126 pages is a 126-page problem."""
        coverage = provider_link_coverage(self._payloads())
        assert coverage.programs_dead == 2
        assert coverage.programs_indeterminate == 1

    def test_counts_what_the_reader_actually_gets(self) -> None:
        coverage = provider_link_coverage(self._payloads())
        assert coverage.programs_linked == 6
        assert coverage.programs_not_linked == 1
        assert coverage.programs_upgraded_to_https == 1
        assert coverage.programs_sent_to_front_page == 1
        assert coverage.programs_labelled_home_page == 1

    def test_publishes_when_the_observation_was_made(self) -> None:
        coverage = provider_link_coverage(self._payloads())
        assert coverage.earliest_check == "2026-08-04"
        assert coverage.latest_check == "2026-08-04"

    def test_a_build_with_no_link_data_reports_nothing_established(self) -> None:
        """Every count that would imply a finding is zero, and the dates are null: nothing
        was looked at, which is not the same as nothing being wrong."""
        coverage = provider_link_coverage([_payload(GOOD), _payload(None)])
        assert coverage.programs_with_link == 1
        assert coverage.programs_checked == 0
        assert coverage.programs_unchecked == 1
        assert coverage.programs_dead == 0
        assert coverage.programs_not_linked == 0
        assert coverage.earliest_check is None
        assert coverage.latest_check is None


class _Server:
    """A scripted site that counts every knock, so politeness stays measurable."""

    def __init__(self, routes: dict[str, int]) -> None:
        self.routes = routes
        self.requests: list[tuple[str, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append((request.method, str(request.url)))
        return httpx.Response(self.routes.get(str(request.url), 404))


class TestCheckProviderLinks:
    """The explicitly-invoked pass. It writes a report; it never touches the dataset."""

    ROUTES: ClassVar[dict[str, int]] = {GOOD: 200, MISSING: 404, B_ROOT: 200}

    def _dataset(self, tmp_path: Path) -> Path:
        dataset = tmp_path / "processed"
        dataset.mkdir(exist_ok=True)
        (dataset / "programs.json").write_text(
            json.dumps(
                {
                    "programs": [
                        {"program_url": GOOD},
                        {"program_url": GOOD},
                        {"program_url": MISSING},
                        {"program_url": None},
                    ]
                }
            ),
            encoding="utf-8",
        )
        return dataset

    def _run(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        cache_dir: Path | None = None,
    ) -> tuple[LinkCheckRun, _Server]:
        server = _Server(self.ROUTES)
        monkeypatch.setattr(
            link_check,
            "build_client",
            lambda *a, **k: httpx.Client(transport=httpx.MockTransport(server)),
        )
        run = check_provider_links(
            self._dataset(tmp_path),
            output_path=tmp_path / "link-checks.json",
            cache_dir=cache_dir,
            max_workers=2,
            sleep=lambda _: None,
        )
        return run, server

    def test_reports_urls_and_the_pages_that_depend_on_them(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        run, _ = self._run(tmp_path, monkeypatch)
        assert run.urls == 2
        assert run.pages == 3
        assert run.pages_by_verdict == {"alive": 2, "dead": 1}

    def test_the_front_page_of_a_404_is_read_but_not_counted_as_a_link(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """It is evidence about a substitution, not a link this dataset publishes. Counting
        it would inflate every figure in the report that motivated this work."""
        run, server = self._run(tmp_path, monkeypatch)
        assert run.front_pages_checked == 1
        assert run.by_verdict == {"alive": 1, "dead": 1}
        assert ("GET", B_ROOT) in server.requests

    def test_every_provider_is_knocked_on_once(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two dataset URLs and one front page, one GET each and nothing repeated.

        The pass used to spend a HEAD and then a confirming GET on anything negative. Asking
        the way a reader asks answers the same question in one request and makes the page's
        own title readable, so a provider is knocked on once per address per run.
        """
        _, server = self._run(tmp_path, monkeypatch)
        assert server.requests == [
            ("GET", GOOD),
            ("GET", MISSING),
            ("GET", B_ROOT),
        ]

    def test_the_report_drives_the_next_builds_decision(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._run(tmp_path, monkeypatch)
        checks = load_link_checks(tmp_path / "link-checks.json")
        link = _payload(MISSING, checks)["provider_link"]
        assert link["href"] == B_ROOT
        assert link["substitution"] == SUBSTITUTION_FRONT_PAGE

    def test_a_page_that_answers_200_and_says_it_is_missing_reaches_the_record(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The whole path, end to end, for the 23 pages that motivated the body read.

        Butte College served exactly this on 2026-08-05: HTTP 200, ``<title>404 Error</title>``,
        at a URL three program pages published as "Provider's website". Its front door is
        fine, so what the reader gets is a working link to it and a dated sentence saying
        why -- not a confident link into a "page not found" screen.
        """

        def site(request: httpx.Request) -> httpx.Response:
            if str(request.url) == B_ROOT:
                return httpx.Response(200, html="<title>Butte College</title>")
            return httpx.Response(200, html="<title>404 Error</title>")

        monkeypatch.setattr(
            link_check,
            "build_client",
            lambda *a, **k: httpx.Client(transport=httpx.MockTransport(site)),
        )
        check_provider_links(
            self._dataset(tmp_path),
            output_path=tmp_path / "link-checks.json",
            cache_dir=None,
            max_workers=2,
            sleep=lambda _: None,
        )
        checks = load_link_checks(tmp_path / "link-checks.json")
        link = _payload(MISSING, checks)["provider_link"]
        assert link["verdict"] == "dead"
        assert link["reason"] == "soft_not_found"
        assert link["href"] == B_ROOT
        assert link["substitution"] == SUBSTITUTION_FRONT_PAGE
        assert link["notice"] == "page_unreachable"
        assert link["url"] == MISSING, "the federal record's own value survives"

    def test_an_address_that_is_for_sale_reaches_the_record_unlinked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No front page is asked for and none is offered: the whole address is merchandise.

        The reader gets the URL as plain text and a sentence that does not pretend we failed
        to reach it, because we did not -- an advertisement answered.
        """

        def parked(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, html="<title>Example.com is for sale | HugeDomains</title>")

        monkeypatch.setattr(
            link_check,
            "build_client",
            lambda *a, **k: httpx.Client(transport=httpx.MockTransport(parked)),
        )
        run = check_provider_links(
            self._dataset(tmp_path),
            output_path=tmp_path / "link-checks.json",
            cache_dir=None,
            max_workers=2,
            sleep=lambda _: None,
        )
        assert run.front_pages_checked == 0
        link = _payload(MISSING, load_link_checks(tmp_path / "link-checks.json"))["provider_link"]
        assert link["linked"] is False
        assert link["href"] is None
        assert link["notice"] == "domain_for_sale"

    def test_a_warm_cache_asks_nobody_anything(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """1,000 providers should not be re-asked whether they exist on every re-run."""
        cache = tmp_path / "cache"
        self._run(tmp_path, monkeypatch, cache_dir=cache)
        _, second = self._run(tmp_path, monkeypatch, cache_dir=cache)
        assert second.requests == []

    def test_it_refuses_to_guess_at_a_dataset_that_is_not_there(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="afterward build"):
            check_provider_links(tmp_path / "nowhere", output_path=tmp_path / "out.json")


class TestOfflineBuildLinks:
    """The hermetic build. It has no network, so it establishes nothing about any link."""

    def test_every_link_is_published_as_filed(self, tmp_path: Path) -> None:
        build_offline(FIXTURE_DIR, output_dir=tmp_path)
        programs = json.loads((tmp_path / "programs.json").read_text(encoding="utf-8"))
        linked = [p for p in programs["programs"] if p["program_url"]]
        assert linked, "fixture has no provider links left to exercise this"
        for program in linked:
            assert program["provider_link"]["href"] == program["program_url"]
            assert program["provider_link"]["verdict"] is None
            assert program["provider_link"]["notice"] is None

    def test_the_coverage_block_says_nothing_was_established(self, tmp_path: Path) -> None:
        build_offline(FIXTURE_DIR, output_dir=tmp_path)
        coverage = json.loads((tmp_path / "coverage.json").read_text(encoding="utf-8"))
        links = coverage["provider_links"]
        assert links["programs_checked"] == 0
        assert links["programs_dead"] == 0
        assert links["programs_not_linked"] == 0
        assert links["earliest_check"] is None

    def test_a_report_is_used_when_one_is_handed_to_it(self, tmp_path: Path) -> None:
        """Offline means no network, not no knowledge: a report read from disk is fine."""
        programs = json.loads((FIXTURE_DIR / "programs.json").read_text(encoding="utf-8"))
        url = next(p["program_url"] for p in programs["programs"] if p["program_url"])
        report = tmp_path / "link-checks.json"
        report.write_text(
            json.dumps(checks_document(_checks(_check(url, "dns_failure")))), encoding="utf-8"
        )

        out = tmp_path / "out"
        build_offline(FIXTURE_DIR, output_dir=out, link_checks_path=report)
        built = json.loads((out / "programs.json").read_text(encoding="utf-8"))["programs"]
        suppressed = [p for p in built if p["program_url"] == url]
        assert suppressed
        for program in suppressed:
            assert program["provider_link"]["linked"] is False
            assert program["provider_link"]["notice"] == NOTICE_UNREACHABLE


# --------------------------------------------------------------------------------------
# The next step
#
# The one feature on this site whose failure mode is somebody losing a morning's pay. A
# person reads that a program was on California's Eligible Training Provider List, walks
# into an office expecting the training to be paid for, and is told no. These tests are
# about the two things that keep the distance between those sentences visible: a centre this
# build never looked for must never render as a centre that is not there, and the sentence
# saying who actually decides must not be separable from the steps it qualifies.
# --------------------------------------------------------------------------------------


def _center(
    center_id: str,
    lat: float | None,
    lon: float | None,
    *,
    comprehensive: bool = True,
    state: str | None = "CA",
) -> AmericanJobCenter:
    return AmericanJobCenter(
        center_id=center_id,
        name=f"{center_id} AJCC",
        address=("1 Main St",),
        city="Somewhere",
        state=state,
        postal_code="90000",
        phone="555-0100",
        email=None,
        website=None,
        hours="Mon-Fri 9-5",
        center_type=COMPREHENSIVE if comprehensive else "Affiliate Center",
        lat=lat,
        lon=lon,
        veterans_representative=None,
        temporarily_closed=None,
        closure_note=None,
        worker_services=(),
        youth_services=(),
        last_updated=None,
    )


SACRAMENTO = (38.5816, -121.4944)
CENTERS = (
    _center("near", 38.56, -121.47),
    _center("mid", 38.40, -121.30, comprehensive=False),
    _center("far", 38.35, -121.25),
    _center("hundreds-of-miles-away", 32.71, -117.16),
)


def _at(lat: float | None, lon: float | None) -> dict[str, Any]:
    return {"lat": lat, "lon": lon}


class TestLocalHelpOnProgramRecords:
    def test_publishes_the_nearest_centers_closest_first(self) -> None:
        block = local_help_block(_at(*SACRAMENTO), CENTERS)
        assert [row["id"] for row in block["centers"]] == ["near", "mid", "far"]
        assert block["centers"][0]["miles"] < block["centers"][1]["miles"]

    def test_publishes_ids_rather_than_copies_of_the_directory(self) -> None:
        """The same three offices are nearest to hundreds of programs.

        Copying the addresses into every record would put megabytes of duplicated text into a
        dataset meant to be served to phones. The directory is published once in coverage.json
        and these point into it.
        """
        row = local_help_block(_at(*SACRAMENTO), CENTERS)["centers"][0]
        assert set(row) == {"id", "miles"}

    def test_a_center_beyond_the_radius_is_not_offered(self) -> None:
        block = local_help_block(_at(*SACRAMENTO), CENTERS)
        assert "hundreds-of-miles-away" not in [row["id"] for row in block["centers"]]

    def test_no_center_nearby_is_an_empty_list_not_a_null(self) -> None:
        """The distinction the whole feature rests on.

        A null here means nothing was looked for, and a page renders it as "we have not
        established which offices are nearest". An empty list means the search ran and
        California has nothing within the radius -- true of 32 of its 3,266 programs, and a
        finding those pages state rather than swallow.
        """
        block = local_help_block(_at(41.75, -124.20), CENTERS)
        assert block["centers"] == []

    def test_no_directory_is_a_null_rather_than_an_empty_list(self) -> None:
        assert local_help_block(_at(*SACRAMENTO), None)["centers"] is None

    def test_a_program_with_no_coordinates_is_not_searched(self) -> None:
        # Not "there is nothing near it": there is nowhere to search from.
        assert local_help_block(_at(None, None), CENTERS)["centers"] is None
        assert local_help_block(_at(38.5, None), CENTERS)["centers"] is None

    def test_distance_is_rounded_to_a_tenth(self) -> None:
        # A great-circle distance offered to somebody deciding whether to travel. More
        # precision than this would be a claim about roads nothing here has measured.
        miles = local_help_block(_at(*SACRAMENTO), CENTERS)["centers"][0]["miles"]
        assert miles == round(miles, 1)

    def test_a_program_record_carries_the_block_even_with_no_centers(self) -> None:
        program = parse_program({"_source": {"field_uuid": "u1"}})
        payload = program_payload(program, _occupations())
        assert payload["local_help"]["centers"] is None
        assert payload["local_help"]["radius_miles"] > 0


class TestFetchJobCenters:
    def test_returns_none_without_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CI has none, and a build that dies for want of an office finder helps nobody."""
        monkeypatch.delenv(USER_ID_ENV, raising=False)
        monkeypatch.delenv(TOKEN_ENV, raising=False)
        assert fetch_job_centers("CA") is None

    def test_drops_centers_outside_the_state(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The nearest office to Blythe is in Arizona, and it cannot open a California account.

        Correct of the finder to return it, wrong of this dataset to attach it to a California
        program as the place to ask about California money.
        """
        monkeypatch.setattr(
            "afterward.build.local_help.fetch_centers",
            lambda *a, **k: (*CENTERS, _center("phoenix", 33.45, -112.07, state="AZ")),
        )
        found = fetch_job_centers("CA")
        assert found is not None
        assert "phoenix" not in [c.center_id for c in found]


class TestLocalHelpCoverage:
    def _payloads(self, centers: tuple[AmericanJobCenter, ...] | None) -> list[dict[str, Any]]:
        places = [
            ("Sacramento", *SACRAMENTO),
            ("Davis", 38.60, -121.50),
            ("Crescent City", 41.75, -124.20),
            ("Nowhere", None, None),
        ]
        payloads = [{"location": {"city": city, **_at(lat, lon)}} for city, lat, lon in places]
        _attach_local_help(payloads, centers)
        return payloads

    def test_counts_what_the_pages_actually_carry(self) -> None:
        coverage = local_help_coverage(self._payloads(CENTERS), CENTERS)
        assert coverage.centers_loaded == len(CENTERS)
        assert coverage.programs_searched == 3
        assert coverage.programs_with_a_center == 2
        assert coverage.programs_with_none_within_radius == 1
        assert coverage.programs_not_searched == 1

    def test_a_build_that_did_not_look_reports_null_rather_than_zero_centers(self) -> None:
        """`0` would say the directory answered and California has no job centres in it."""
        coverage = local_help_coverage(self._payloads(None), None)
        assert coverage.centers_loaded is None
        assert coverage.programs_searched == 0
        assert coverage.nearest_median_miles is None
        assert coverage.nearest_farthest_miles is None

    def test_counts_a_comprehensive_center_separately(self) -> None:
        # An affiliate site need not provide access to every partner program (20 CFR 678.310),
        # so "there is an office" and "there is an office that can do all of it" differ.
        coverage = local_help_coverage(self._payloads(CENTERS), CENTERS)
        assert coverage.programs_with_a_comprehensive_center == 2

    def test_the_document_always_carries_the_guidance(self) -> None:
        """Credentials decide whether we know where the offices are, not what the rules are."""
        payloads = self._payloads(None)
        document = local_help_document(local_help_coverage(payloads, None), None, payloads)
        assert document["centers"] is None
        assert document["cities"] is None
        assert document["guidance"]["steps"]
        assert document["guidance"]["who_decides"]

    def test_the_document_cannot_carry_steps_without_saying_who_decides(self) -> None:
        """The structural guarantee, checked at the point it reaches the dataset.

        `funding_guidance()` is the only way to obtain the steps and the disclaimer is a field
        of what it returns, so a pipeline cannot emit one without the other. This asserts the
        property survives serialisation, which is where it would otherwise be lost.
        """
        payloads = self._payloads(CENTERS)
        document = local_help_document(local_help_coverage(payloads, CENTERS), CENTERS, payloads)
        assert document["guidance"]["who_decides"] == WHO_DECIDES
        assert [s["id"] for s in document["guidance"]["steps"] if s["on_program_page"]]
        assert document["cities"]["places_located"] >= 1


class TestOfflineBuildLocalHelp:
    def test_no_page_claims_a_nearby_office(self, tmp_path: Path) -> None:
        build_offline(FIXTURE_DIR, output_dir=tmp_path)
        programs = json.loads((tmp_path / "programs.json").read_text(encoding="utf-8"))["programs"]
        assert programs
        for program in programs:
            assert program["local_help"]["centers"] is None

    def test_the_funding_guidance_still_ships(self, tmp_path: Path) -> None:
        """The route to funding does not depend on this machine reaching a list of offices."""
        build_offline(FIXTURE_DIR, output_dir=tmp_path)
        coverage = json.loads((tmp_path / "coverage.json").read_text(encoding="utf-8"))
        guidance = coverage["local_help"]["guidance"]
        assert guidance["who_decides"] == WHO_DECIDES
        assert guidance["questions"]
        assert guidance["finders"]
        assert coverage["local_help"]["centers_loaded"] is None
