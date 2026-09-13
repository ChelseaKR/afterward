"""Tests for the Projections Central adapter (D9), against recorded live responses.

The property defended hardest here is the one whose failure is invisible on a page: a
figure that is real, plausible, and about the wrong population. The national row sits in
the same array as the states; the openings column is an annual average where this
pipeline's records carry a ten-year total; and an unusable query parameter answers 404 in
exactly the words a state with no data gets. Each of those publishes a believable number,
so each of them has a test that names it.

The recordings in ``tests/fixtures/projections-central`` are verbatim. Expectations are
derived from them where they can be, so a re-recording moves the expectations by being
read rather than by being edited.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from afterward.sources import projections_central
from afterward.sources.dol_etp import FetchError
from afterward.sources.projections_central import (
    ACCEPTED_PAGE_SIZES,
    CONTRADICTORY_ZERO,
    NATIONAL_STFIPS,
    PAGE_SIZE,
    ProjectionsCentralError,
    fetch_state_projections,
    fetch_state_rows,
    is_detailed_soc,
    parse_rows,
)

RECORDED = Path(__file__).parent / "fixtures" / "projections-central"
NEVADA = "32"


def recorded(name: str) -> dict[str, Any]:
    return dict(json.loads((RECORDED / name).read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def nevada_rows() -> list[dict[str, Any]]:
    return list(recorded("nv-longterm-2026-09-11.json")["rows"])


@pytest.fixture(scope="module")
def all_states_rows() -> list[dict[str, Any]]:
    return list(recorded("all-states-29-1141-2026-09-11.json")["rows"])


class TestTheNationalRow:
    """The one row in this source that would publish a wrong population's real number."""

    def test_the_recorded_all_states_response_really_does_carry_it(
        self, all_states_rows: list[dict[str, Any]]
    ) -> None:
        """The premise, asserted against the recording rather than asserted in prose.

        Without this the three tests below could all pass over a fixture that no longer
        contains the thing they exist to refuse.
        """
        national = [row for row in all_states_rows if row["STFIPS"] == NATIONAL_STFIPS]
        assert len(national) == 1
        assert national[0]["Area"] == " United States"
        assert all_states_rows.index(national[0]) == 0
        # Filed among the states, not appended after them: the row after it is a state.
        assert all_states_rows[1]["Area"] == "Alabama"
        assert all_states_rows[1]["STFIPS"] == "1"
        # And the recording says how much of the response it is. Eight rows are kept and
        # the served pager is not; see fixtures/projections-central/RECORDED.md.
        recording = recorded("all-states-29-1141-2026-09-11.json")
        assert recording["pager"]["total_items"] == 55
        assert len(all_states_rows) == 8

    def test_it_is_refused_by_name_rather_than_filtered_out(
        self, all_states_rows: list[dict[str, Any]]
    ) -> None:
        """Refused, not dropped. A filter would let a wrong request succeed quietly."""
        with pytest.raises(ProjectionsCentralError, match="United States"):
            parse_rows(all_states_rows, state_fips=NEVADA)

    def test_a_row_for_another_state_refuses_the_whole_read(
        self, all_states_rows: list[dict[str, Any]]
    ) -> None:
        states_only = [row for row in all_states_rows if row["STFIPS"] != NATIONAL_STFIPS]
        with pytest.raises(ProjectionsCentralError, match="was requested"):
            parse_rows(states_only, state_fips=NEVADA)

    def test_asking_for_the_national_code_is_refused_before_any_request(self) -> None:
        with pytest.raises(ProjectionsCentralError, match="not a state"):
            fetch_state_projections(NATIONAL_STFIPS)

    def test_the_nevada_recording_carries_no_national_row(
        self, nevada_rows: list[dict[str, Any]]
    ) -> None:
        """Which is the reason the per-state endpoint is the one this adapter asks."""
        assert {row["STFIPS"] for row in nevada_rows} == {NEVADA}
        assert {row["Area"] for row in nevada_rows} == {"Nevada"}


class TestWhatTheSourceDoesNotPublish:
    def test_no_wage_column_exists_in_the_recorded_response(
        self, nevada_rows: list[dict[str, Any]]
    ) -> None:
        columns = {key for row in nevada_rows for key in row}
        assert columns == {
            "Area",
            "Title",
            "Base",
            "Projected",
            "Change",
            "PercentChange",
            "AvgAnnualOpenings",
            "STFIPS",
            "StateURL",
            "OccCode",
            "BaseYear",
            "ProjYear",
        }
        assert not [name for name in columns if "wage" in name.casefold()]

    def test_the_annual_openings_average_never_becomes_a_ten_year_total(
        self, nevada_rows: list[dict[str, Any]]
    ) -> None:
        """The units trap, and the reason ``total_job_openings`` is null for this source.

        EDD's ``Total Job Openings`` is a ten-year total; this source's
        ``AvgAnnualOpenings`` is one year. Across the 56 occupations in the committed
        California fixture the ratio is 10.0. Writing one into the other's field would
        understate openings tenfold behind a number nothing on the page could contradict.
        """
        read = parse_rows(nevada_rows, state_fips=NEVADA)
        assert [row.total_job_openings for row in read.rows] == [None] * len(read.rows)
        # And the figure really was there to be mistaken: this is not a null because the
        # source sent nothing.
        assert sum(1 for row in nevada_rows if row["AvgAnnualOpenings"]) > 500

    def test_every_measure_this_source_lacks_is_null_on_every_row(
        self, nevada_rows: list[dict[str, Any]]
    ) -> None:
        read = parse_rows(nevada_rows, state_fips=NEVADA)
        for row in read.rows:
            assert row.median_annual_wage is None
            assert row.median_hourly_wage is None
            assert row.entry_level_education is None
            assert row.work_experience is None
            assert row.job_training is None
            assert row.area_type is None
            assert row.soc_level is None

    def test_every_row_is_its_state_so_no_area_definition_can_be_read_from_it(
        self, nevada_rows: list[dict[str, Any]]
    ) -> None:
        from afterward.sources.edd_lmi import area_definitions

        read = parse_rows(nevada_rows, state_fips=NEVADA)
        assert all(row.is_statewide for row in read.rows)
        assert area_definitions(read.rows) == []


class TestTheDetailedOccupationRule:
    @pytest.mark.parametrize(
        ("code", "detailed"),
        [
            ("29-1141", True),  # detailed
            ("11-1011", True),
            ("00-0000", False),  # major group total
            ("11-0000", False),  # major group
            ("13-1000", False),  # minor group
            ("13-1020", False),  # broad occupation -- the level the old EDD bug let through
            ("29-2010", False),
            ("", False),
            (None, False),
            ("29-114", False),
            ("29-1141.00", False),
        ],
    )
    def test_the_level_is_read_off_the_whole_code(self, code: str | None, detailed: bool) -> None:
        assert is_detailed_soc(code) is detailed

    def test_the_recording_splits_the_way_the_rule_says(
        self, nevada_rows: list[dict[str, Any]]
    ) -> None:
        """Counted from the file. 649 detailed, 7 broad, one major-group total."""
        codes = [row["OccCode"] for row in nevada_rows]
        detailed = [code for code in codes if is_detailed_soc(code)]
        aggregates = [code for code in codes if not is_detailed_soc(code)]
        assert len(codes) == 657
        assert len(detailed) == 649
        assert sorted(aggregates) == [
            "00-0000",
            "13-1020",
            "13-2020",
            "29-2010",
            "31-1120",
            "39-7010",
            "47-4090",
            "51-2090",
        ]


class TestContradictoryZero:
    def test_the_recorded_row_that_contradicts_itself_is_refused_and_named(
        self, nevada_rows: list[dict[str, Any]]
    ) -> None:
        read = parse_rows(nevada_rows, state_fips=NEVADA)
        assert [row.soc_code for row in read.refused] == ["45-4029"]
        assert read.refused[0].reason == CONTRADICTORY_ZERO
        assert "45-4029" not in {row.soc_code for row in read.rows}
        assert read.published_rows == 657
        assert len(read.rows) == 656

    def test_the_premise_holds_in_the_recording(self, nevada_rows: list[dict[str, Any]]) -> None:
        row = next(row for row in nevada_rows if row["OccCode"] == "45-4029")
        assert row["Base"] == "0"
        assert row["PercentChange"] == "25"

    def test_a_genuine_zero_change_is_not_a_contradiction(self) -> None:
        """An occupation that really is not moving keeps its row."""
        read = parse_rows(
            [
                {
                    "Area": "Nevada",
                    "Title": "Somebody",
                    "Base": "0",
                    "Projected": "0",
                    "Change": "0",
                    "PercentChange": "0",
                    "AvgAnnualOpenings": "0",
                    "STFIPS": NEVADA,
                    "OccCode": "29-1141",
                    "BaseYear": "2024",
                    "ProjYear": "2034",
                }
            ],
            state_fips=NEVADA,
        )
        assert read.refused == ()
        assert len(read.rows) == 1


class TestPagination:
    """A dropped page is a set of occupations that silently publish no projection."""

    @staticmethod
    def _serving(rows: list[dict[str, Any]], *, total_items: int | None = None) -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            page = int(request.url.params.get("page", 0))
            size = int(request.url.params["items_per_page"])
            start = page * size
            return httpx.Response(
                200,
                json={
                    "rows": rows[start : start + size],
                    "pager": {
                        "current_page": page,
                        "total_items": len(rows) if total_items is None else total_items,
                        "total_pages": -(-len(rows) // size),
                        "items_per_page": size,
                    },
                },
            )

        return httpx.Client(transport=httpx.MockTransport(handler))

    def test_every_page_is_collected(self, nevada_rows: list[dict[str, Any]]) -> None:
        with self._serving(nevada_rows) as client:
            collected = fetch_state_rows(NEVADA, client=client)
        assert len(collected) == 657
        assert [row["OccCode"] for row in collected] == [row["OccCode"] for row in nevada_rows]

    def test_it_takes_more_than_one_page_to_do_it(self, nevada_rows: list[dict[str, Any]]) -> None:
        """Otherwise the loop above would be untested on the state it was measured on."""
        assert len(nevada_rows) > PAGE_SIZE

    def test_a_short_read_is_refused_rather_than_published(
        self, nevada_rows: list[dict[str, Any]]
    ) -> None:
        with (
            self._serving(nevada_rows[:120], total_items=657) as client,
            pytest.raises(ProjectionsCentralError, match="657 rows and 120 arrived"),
        ):
            fetch_state_rows(NEVADA, client=client)

    def test_the_page_size_is_one_the_service_accepts(self) -> None:
        """Measured 2026-09-11: any other value answers 404 "No results found.", which is
        also what a state with nothing published gets."""
        assert PAGE_SIZE in ACCEPTED_PAGE_SIZES

    def test_only_accepted_parameters_are_ever_sent(
        self, nevada_rows: list[dict[str, Any]]
    ) -> None:
        sent: list[httpx.URL] = []

        def handler(request: httpx.Request) -> httpx.Response:
            sent.append(request.url)
            return httpx.Response(
                200,
                json={
                    "rows": nevada_rows[:1],
                    "pager": {
                        "current_page": 0,
                        "total_items": 1,
                        "total_pages": 1,
                        "items_per_page": PAGE_SIZE,
                    },
                },
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            fetch_state_rows(NEVADA, client=client)
        assert len(sent) == 1
        assert set(sent[0].params) == {"page", "items_per_page"}
        assert int(sent[0].params["items_per_page"]) in ACCEPTED_PAGE_SIZES

    def test_a_404_is_raised_rather_than_read_as_a_state_with_no_projections(self) -> None:
        """The measured ambiguity: the service answers 404 "No results found." both to a
        state code it holds nothing for and to a query parameter it does not accept."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, text="No results found.")

        with (
            httpx.Client(transport=httpx.MockTransport(handler)) as client,
            pytest.raises(FetchError),
        ):
            fetch_state_rows(NEVADA, client=client)

    def test_a_body_that_is_not_the_expected_object_is_refused(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[{"Area": "Nevada"}])

        with (
            httpx.Client(transport=httpx.MockTransport(handler)) as client,
            pytest.raises(ProjectionsCentralError, match="not the object"),
        ):
            fetch_state_rows(NEVADA, client=client)

    def test_a_pager_that_never_ends_is_stopped_rather_than_followed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "rows": [],
                    "pager": {
                        "current_page": 0,
                        "total_items": 10**9,
                        "total_pages": 10**6,
                        "items_per_page": PAGE_SIZE,
                    },
                },
            )

        with (
            httpx.Client(transport=httpx.MockTransport(handler)) as client,
            pytest.raises(ProjectionsCentralError, match="past the"),
        ):
            fetch_state_rows(NEVADA, client=client)


class TestParsedValues:
    def test_the_period_comes_from_the_row_and_not_from_a_date_range_endpoint(
        self, nevada_rows: list[dict[str, Any]]
    ) -> None:
        read = parse_rows(nevada_rows, state_fips=NEVADA)
        assert {row.period for row in read.rows} == {"2024-2034"}

    def test_a_declining_occupation_keeps_its_negative_change(
        self, nevada_rows: list[dict[str, Any]]
    ) -> None:
        read = parse_rows(nevada_rows, state_fips=NEVADA)
        declining = [row for row in read.rows if (row.numeric_change or 0) < 0]
        assert declining, "the recording is expected to contain declining occupations"

    def test_an_unreadable_figure_is_null_rather_than_zero(self) -> None:
        read = parse_rows(
            [
                {
                    "Area": "Nevada",
                    "Title": "Somebody",
                    "Base": "N/A",
                    "Projected": "",
                    "Change": "10",
                    "PercentChange": "1",
                    "AvgAnnualOpenings": "5",
                    "STFIPS": NEVADA,
                    "OccCode": "29-1141",
                    "BaseYear": "2024",
                    "ProjYear": "2034",
                }
            ],
            state_fips=NEVADA,
        )
        assert read.rows[0].base_employment is None
        assert read.rows[0].projected_employment is None


def _live_rows() -> Iterator[dict[str, Any]]:  # pragma: no cover - documentation only
    """How the recordings were made. Not called by any test; see fixtures/RECORDED.md."""
    yield from projections_central.fetch_state_rows(NEVADA)
