"""Tests for the occupation index and program/occupation join."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from camino.build import (
    MATCH_EXACT,
    RELATED_SOURCE_ONET,
    RELATED_SOURCE_SOC_SIBLINGS,
    EnrichmentCoverage,
    aggregate_match_coverage,
    area_coverage,
    detailed_soc_codes,
    enrichment_coverage,
    fetch_enrichment,
    index_occupations,
    match_occupations,
    peer_medians,
    program_payload,
    search_entry,
    unmapped_cities,
)
from camino.sources.careeronestop import TOKEN_ENV, USER_ID_ENV, OccupationEnrichment, Skill
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
        import httpx

        monkeypatch.setenv(USER_ID_ENV, "user")
        monkeypatch.setenv(TOKEN_ENV, "token")
        (tmp_path / "29-1141.00.json").write_text(json.dumps(CACHED_RESPONSE), encoding="utf-8")

        def explode(*args: object, **kwargs: object) -> None:
            raise AssertionError("hit the network despite a warm cache")

        monkeypatch.setattr(httpx.Client, "get", explode)
        found = fetch_enrichment(["29-1141"], cache_dir=tmp_path)
        assert set(found) == {"29-1141"}
        assert found["29-1141"].description == "Assess patient health problems and needs."


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

    def _entry(self, region: dict | None, city: str | None = "Fresno") -> dict:
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
