"""What changes in a build when the state is not California.

Three things, and each of them is a place where a California artifact would otherwise be
served up as a second state's answer: the OEWS extract on disk, the placement rules that
restate EDD's own area titles, and the declaration in ``coverage.json`` that says which
publisher the occupation figures came from.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from afterward.build import (
    UNPLACED_CROSSWALK_NOT_READ,
    UNPLACED_SOURCE_PUBLISHES_NO_AREAS,
    WAGE_SPREAD_STATE,
    check_projection_source,
    check_state_is_reported,
    load_wage_regions,
    load_wage_spread,
    place_program,
)
from afterward.sources import dol_etp, projection_source
from afterward.sources.dol_etp import FetchError, Program, parse_program

REPORTED = {"CA": 3266, "NV": 1069, "WA": 4996}


def program(city: str | None = "Reno", zip_code: str | None = "89501") -> Program:
    """One program, built the way the feed delivers it rather than field by field."""
    return parse_program(
        {
            "_source": {
                "field_uuid": "u",
                "field_etp": "A provider",
                "field_state": "NV",
                "field_city": city,
                "field_zip": zip_code,
            }
        }
    )


class TestTheStateIsCheckedAgainstTheFeed:
    def test_a_reported_state_passes_and_is_normalised(self) -> None:
        assert check_state_is_reported("nv", reported=REPORTED) == "NV"

    def test_an_unreported_state_is_refused_with_the_list(self) -> None:
        """Without this, `--state XZ` is a successful fetch of nothing: the filter matches
        no documents and the build emits an empty dataset."""
        with pytest.raises(ValueError) as caught:
            check_state_is_reported("XZ", reported=REPORTED)
        message = str(caught.value)
        assert "XZ" in message
        assert "CA, NV, WA" in message

    def test_an_empty_aggregation_is_a_failed_read_and_not_an_empty_country(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"aggregations": {"states": {"buckets": []}}})

        with (
            httpx.Client(transport=httpx.MockTransport(handler)) as client,
            pytest.raises(FetchError, match="no states at all"),
        ):
            dol_etp.fetch_states(client=client)

    def test_the_aggregation_is_one_request_and_asks_for_no_documents(self) -> None:
        sent: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            sent.append(json.loads(request.url.params["source"]))
            return httpx.Response(
                200,
                json={"aggregations": {"states": {"buckets": [{"key": "nv", "doc_count": 1069}]}}},
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            assert dol_etp.fetch_states(client=client) == {"NV": 1069}
        assert len(sent) == 1
        assert sent[0]["size"] == 0
        assert sent[0]["aggs"]["states"]["terms"]["size"] >= 57


class TestTheCaliforniaWageExtractStaysInCalifornia:
    """D3 is California's OEWS panel and the file it leaves carries no state column."""

    @staticmethod
    def _extract(tmp_path: Path) -> Path:
        path = tmp_path / "oews-statewide.json"
        path.write_text(
            json.dumps(
                {
                    "occupations": {"29-1141": {"p50": 144197.0}},
                    "regions": {"29-1141": {"Fresno MSA": {"p50": 120000.0}}},
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_california_reads_it(self, tmp_path: Path) -> None:
        path = self._extract(tmp_path)
        assert load_wage_spread(path, state=WAGE_SPREAD_STATE) == {"29-1141": {"p50": 144197.0}}
        assert load_wage_regions(path, state=WAGE_SPREAD_STATE)

    def test_another_state_does_not_even_with_the_file_right_there(self, tmp_path: Path) -> None:
        """Attaching these to a Nevada occupation would be a correct measurement of the
        wrong population -- reached by a file left in the working directory."""
        path = self._extract(tmp_path)
        assert path.exists()
        assert load_wage_spread(path, state="NV") == {}
        assert load_wage_regions(path, state="NV") == {}


class TestPlacementWhenTheSourcePublishesNoAreas:
    def test_neither_rule_is_attempted_and_the_reason_says_why(self) -> None:
        area, matched_on, reason = place_program(
            program(), city_areas=None, counties=None, areas_published=False
        )
        assert (area, matched_on, reason) == (None, None, UNPLACED_SOURCE_PUBLISHES_NO_AREAS)

    def test_it_is_not_the_same_as_nobody_having_looked(self) -> None:
        """``crosswalk_not_read`` is a statement about the build. This is a statement about
        the publisher, and conflating them would read as a broken join."""
        _, _, reason = place_program(program(), city_areas=None, counties=None)
        assert reason == UNPLACED_CROSSWALK_NOT_READ
        assert UNPLACED_SOURCE_PUBLISHES_NO_AREAS != UNPLACED_CROSSWALK_NOT_READ

    def test_a_city_that_would_otherwise_match_still_does_not_place(self) -> None:
        """The flag short-circuits the city rule too, not only the county one."""
        from afterward.sources.edd_lmi import parse_area

        fresno = parse_area("Metropolitan Area", "Fresno MSA (Fresno and Madera Counties)")
        placed, _, _ = place_program(
            program(city="Fresno"), city_areas={"fresno": fresno}, counties=None
        )
        assert placed is not None
        unplaced, _, reason = place_program(
            program(city="Fresno"),
            city_areas={"fresno": fresno},
            counties=None,
            areas_published=False,
        )
        assert unplaced is None
        assert reason == UNPLACED_SOURCE_PUBLISHES_NO_AREAS


class TestTheCoverageDeclarationIsEnforced:
    @staticmethod
    def _coverage(measures: projection_source.PublishedMeasures) -> dict[str, Any]:
        return {
            "projection_source": projection_source.SourceRead(
                state="NV",
                source="D9",
                publisher="Projections Central",
                endpoint="https://example.invalid/32",
                publishes=measures,
                rows=(),
                rows_published=0,
            ).declaration(occupations_indexed=1)
        }

    @staticmethod
    def _occupations(**overrides: Any) -> dict[str, dict[str, Any]]:
        row: dict[str, Any] = {
            "base_employment": 1.0,
            "projected_employment": 2.0,
            "numeric_change": 1.0,
            "percent_change": 1.0,
            "total_job_openings": None,
            "median_annual_wage": None,
            "median_hourly_wage": None,
            "entry_level_education": None,
            "work_experience": None,
            "job_training": None,
            "regions": [],
        }
        row.update(overrides)
        return {"29-1141": row}

    def test_a_dataset_that_agrees_with_its_declaration_passes(self) -> None:
        check_projection_source(
            self._coverage(projection_source.PROJECTIONS_CENTRAL_MEASURES),
            self._occupations(),
        )

    def test_a_wage_that_appeared_from_somewhere_is_refused(self) -> None:
        with pytest.raises(ValueError, match="median_annual_wage"):
            check_projection_source(
                self._coverage(projection_source.PROJECTIONS_CENTRAL_MEASURES),
                self._occupations(median_annual_wage=52000.0),
            )

    def test_a_coverage_document_with_no_declaration_is_refused(self) -> None:
        with pytest.raises(ValueError, match="no projection_source block"):
            check_projection_source({}, self._occupations())

    def test_a_declaration_that_names_measures_this_code_does_not_know_is_refused(self) -> None:
        document = self._coverage(projection_source.PROJECTIONS_CENTRAL_MEASURES)
        document["projection_source"]["publishes"]["invented_measure"] = True
        with pytest.raises(ValueError, match="does not name the same"):
            check_projection_source(document, self._occupations())

    def test_a_declaration_that_is_not_a_table_is_refused(self) -> None:
        with pytest.raises(ValueError, match="not the measure-by-measure table"):
            check_projection_source({"projection_source": {"publishes": "all of them"}}, {})
