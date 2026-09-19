"""Tests for the projection-source seam and for the declaration it writes.

What is under test here is mostly one sentence in ``coverage.json``. The occupation records
of a state whose source publishes no wage are, field for field, the records of a state whose
source withheld one -- so the declaration is the only thing that tells a reader which they
are holding, and a declaration nothing checks is decoration. Both directions of the check
are exercised: a measure declared absent that some record carries, and a measure declared
published that no record does.
"""

from __future__ import annotations

import csv
import hashlib
import json
from typing import Any

import pytest

from afterward.sources import projection_source, state_fips
from afterward.sources.projection_source import (
    EDD_MEASURES,
    PROJECTIONS_CENTRAL_MEASURES,
    EddProjections,
    ProjectionsCentralSource,
    PublishedMeasures,
    SourceRead,
    fixture_read,
    source_for,
    unpublished_measures_carrying_values,
)
from afterward.sources.state_fips import StateCodeError


def occupations(**overrides: Any) -> dict[str, dict[str, Any]]:
    """One occupation carrying every measure, before overrides."""
    row: dict[str, Any] = {
        "base_employment": 1000.0,
        "projected_employment": 1100.0,
        "numeric_change": 100.0,
        "percent_change": 10.0,
        "total_job_openings": 900.0,
        "median_annual_wage": 50000.0,
        "median_hourly_wage": 24.0,
        "entry_level_education": "Bachelor's degree",
        "work_experience": "None",
        "job_training": "None",
        "regions": [{"area_name": "Somewhere"}],
    }
    row.update(overrides)
    return {"29-1141": row}


class TestChoosingASource:
    def test_california_keeps_edd(self) -> None:
        source = source_for("CA")
        assert isinstance(source, EddProjections)
        assert source.source == "D2"
        assert source.publishes == EDD_MEASURES

    def test_every_other_state_reads_projections_central(self) -> None:
        source = source_for("nv")
        assert isinstance(source, ProjectionsCentralSource)
        assert source.state == "NV"
        assert source.source == "D9"
        assert source.publishes == PROJECTIONS_CENTRAL_MEASURES
        assert source.endpoint.endswith("/32")

    def test_a_code_that_is_not_a_state_is_refused_here_and_not_at_the_endpoint(self) -> None:
        """A bad code must not arrive as an unexplained 404: the endpoint answers 404 "No
        results found." to an unknown state and to an unusable parameter alike."""
        with pytest.raises(StateCodeError, match="XZ"):
            source_for("XZ")


class TestWhatTheDeclarationSays:
    def test_projections_central_names_the_seven_measures_it_does_not_publish(self) -> None:
        assert list(PROJECTIONS_CENTRAL_MEASURES.absent) == [
            "entry_level_education",
            "job_training",
            "median_annual_wage",
            "median_hourly_wage",
            "regions",
            "total_job_openings",
            "work_experience",
        ]

    def test_edd_publishes_every_measure_in_the_record(self) -> None:
        assert EDD_MEASURES.absent == ()

    def test_the_declaration_names_the_publisher_the_endpoint_and_the_period(self) -> None:
        read = SourceRead(
            state="NV",
            source="D9",
            publisher="Projections Central",
            endpoint="https://example.invalid/32",
            publishes=PROJECTIONS_CENTRAL_MEASURES,
            rows=(),
            rows_published=0,
        )
        block = read.declaration(occupations_indexed=0)
        assert block["state"] == "NV"
        assert block["source"] == "D9"
        assert block["endpoint"] == "https://example.invalid/32"
        assert block["figures_read_from"] == "source"
        assert block["measures_this_source_does_not_publish"] == list(
            PROJECTIONS_CENTRAL_MEASURES.absent
        )

    def test_a_fixture_build_reports_no_rows_rather_than_zero_rows(self) -> None:
        """Zero rows read would say the publisher served nothing, about a publisher nobody
        asked. The offline path reads a committed fixture and says so."""
        block = fixture_read(
            source_for("CA"), state="CA", periods=["2024-2034", "2024-2034"]
        ).declaration(occupations_indexed=56)
        assert block["figures_read_from"] == "committed_fixture"
        assert block["rows_published"] is None
        assert block["rows_read"] is None
        assert block["rows_refused"] is None
        assert block["period"] == "2024-2034"
        assert block["occupations_indexed"] == 56

    def test_two_periods_in_one_read_refuse_to_collapse_into_one(self) -> None:
        block = fixture_read(
            source_for("CA"), state="CA", periods=["2024-2034", "2022-2032"]
        ).declaration(occupations_indexed=2)
        assert block["period"] is None
        assert block["periods"] == ["2022-2032", "2024-2034"]


class TestTheDeclarationIsCheckedAgainstTheRecords:
    def test_a_matching_dataset_has_nothing_to_say(self) -> None:
        assert unpublished_measures_carrying_values(occupations(), EDD_MEASURES) == []

    def test_a_value_under_a_measure_the_source_does_not_publish_is_caught(self) -> None:
        """The shape that would attach California OEWS percentiles to another state."""
        problems = unpublished_measures_carrying_values(occupations(), PROJECTIONS_CENTRAL_MEASURES)
        assert any("median_annual_wage" in problem for problem in problems)
        assert any("regions" in problem for problem in problems)
        assert len(problems) == len(PROJECTIONS_CENTRAL_MEASURES.absent)

    def test_a_measure_declared_published_that_nothing_carries_is_caught(self) -> None:
        """The other direction: a column that arrived empty and nothing noticed."""
        problems = unpublished_measures_carrying_values(
            occupations(median_annual_wage=None), EDD_MEASURES
        )
        assert problems == [
            "0 of 1 occupations carry median_annual_wage, and the projection source "
            "declares it publishes median_annual_wage. An empty column read as every "
            "occupation withholding the measure is a build that measured nothing."
        ]

    def test_an_empty_region_list_counts_as_not_carried(self) -> None:
        problems = unpublished_measures_carrying_values(occupations(regions=[]), EDD_MEASURES)
        assert any("regions" in problem for problem in problems)

    def test_no_occupations_at_all_is_a_refusal_and_not_a_pass(self) -> None:
        """Every check below it is a count, and every count over nothing agrees."""
        problems = unpublished_measures_carrying_values({}, PROJECTIONS_CENTRAL_MEASURES)
        assert len(problems) == 1
        assert "no occupations" in problems[0]

    def test_a_projections_central_shaped_record_satisfies_its_own_declaration(self) -> None:
        read = occupations(
            total_job_openings=None,
            median_annual_wage=None,
            median_hourly_wage=None,
            entry_level_education=None,
            work_experience=None,
            job_training=None,
            regions=[],
        )
        assert unpublished_measures_carrying_values(read, PROJECTIONS_CENTRAL_MEASURES) == []


class TestTheMeasureTableCoversTheRecord:
    def test_every_flag_names_a_field_the_committed_fixture_carries(self) -> None:
        """A flag for a field the records do not have would check nothing, silently."""
        from pathlib import Path

        fixture = json.loads(Path("fixtures/data/occupations.json").read_text(encoding="utf-8"))[
            "occupations"
        ]
        keys = {key for row in fixture.values() for key in row}
        missing = sorted(set(PublishedMeasures.__dataclass_fields__) - keys)
        assert missing == []


class TestTheVendoredStateTable:
    def test_it_matches_the_digest_recorded_beside_it(self) -> None:
        digest = hashlib.sha256(state_fips.VENDORED_PATH.read_bytes()).hexdigest()
        assert digest == state_fips.provenance()["sha256"]

    def test_it_carries_the_rows_its_record_claims(self) -> None:
        rows = list(
            csv.DictReader(state_fips.VENDORED_PATH.read_text(encoding="utf-8").splitlines())
        )
        assert len(rows) == state_fips.provenance()["rows"]
        assert sorted(rows[0]) == ["state_fips", "usps"]

    def test_it_carries_no_state_names(self) -> None:
        """Nothing joins on a name, and the subset rule on the record says so."""
        text = state_fips.VENDORED_PATH.read_text(encoding="utf-8")
        assert "California" not in text
        assert "Nevada" not in text

    def test_the_codes_go_both_ways_without_collision(self) -> None:
        table = state_fips.by_usps()
        assert len(set(table.values())) == len(table)
        assert table["CA"] == "06"
        assert table["NV"] == "32"

    def test_an_unknown_code_raises_and_names_what_is_known(self) -> None:
        with pytest.raises(StateCodeError) as caught:
            state_fips.fips_for("ZZ")
        assert "CA" in str(caught.value)

    def test_the_table_is_not_a_claim_that_a_state_publishes_anything(self) -> None:
        """AS and UM have codes here and report no ETP programs. The ETP feed decides that,
        not this file -- see ``build.check_state_is_reported``."""
        assert "AS" in state_fips.by_usps()


def test_the_module_exposes_the_protocol_both_sources_satisfy() -> None:
    sources: list[projection_source.ProjectionSource] = [
        EddProjections(),
        ProjectionsCentralSource(state="NV"),
    ]
    assert [source.state for source in sources] == ["CA", "NV"]
