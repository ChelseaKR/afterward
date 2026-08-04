"""Tests for the HTTP layer both source clients share.

Two things are defended here. First, that this project tells public endpoints the truth
about who is calling: these are taxpayer-funded services, and a spoofed browser User-Agent
would be a lie told to buy access. Second, that failure handling stays at a rate an API
operator would call polite -- bounded backoff for genuine hiccups, and no retry loop at all
against a refusal.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest

from camino.sources import dol_etp, edd_lmi
from camino.sources.dol_etp import (
    BACKOFF_CAP_SECONDS,
    MAX_ATTEMPTS,
    PAUSE_BETWEEN_PAGES,
    RETRY_AFTER_CAP_SECONDS,
    USER_AGENT,
    FetchError,
    build_client,
    get_with_retry,
)

URL = "https://cxsearch.dol.gov/etp/_search"


class Replayer:
    """Transport handler that replays canned outcomes and remembers what it was asked.

    Runs out deliberately: an unplanned extra request means the code under test retried
    something it should have left alone, and that should fail loudly.
    """

    def __init__(self, *outcomes: httpx.Response | Exception) -> None:
        self._outcomes = list(outcomes)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert self._outcomes, f"unexpected extra request to {request.url}"
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, httpx.RequestError):
            outcome.request = request
            raise outcome
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    @property
    def agents(self) -> list[str]:
        return [r.headers.get("User-Agent", "") for r in self.requests]


def replay(*outcomes: httpx.Response | Exception) -> tuple[httpx.Client, Replayer]:
    """A client with no default headers, so the retry layer must supply the identity."""
    handler = Replayer(*outcomes)
    return httpx.Client(transport=httpx.MockTransport(handler)), handler


class Clock:
    """Stand-in for ``time.sleep`` that records instead of waiting."""

    def __init__(self) -> None:
        self.waits: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


def hit(uuid: str, sort: int) -> dict[str, object]:
    return {"_id": uuid, "_source": {"field_uuid": uuid}, "sort": [sort]}


def search_response(*hits: dict[str, object]) -> httpx.Response:
    return httpx.Response(200, json={"hits": {"hits": list(hits)}})


class TestIdentity:
    """The User-Agent is a disclosure, not a disguise."""

    def test_names_the_project_and_where_to_complain(self) -> None:
        assert USER_AGENT.startswith("camino/")
        assert "https://github.com/ChelseaKR/camino" in USER_AGENT
        assert "non-commercial open-data client" in USER_AGENT

    def test_does_not_impersonate_a_browser(self) -> None:
        """Spoofing Chrome would work. That is exactly why it is not done."""
        lowered = USER_AGENT.lower()
        for disguise in ("mozilla", "chrome", "safari", "applewebkit", "gecko", "edg/", "opera"):
            assert disguise not in lowered

    def test_build_client_sets_it_as_a_default_header(self) -> None:
        with build_client() as client:
            assert client.headers["User-Agent"] == USER_AGENT

    def test_client_is_configured_to_follow_redirects(self) -> None:
        with build_client() as client:
            assert client.follow_redirects is True

    def test_sent_even_when_the_caller_supplies_a_bare_client(self) -> None:
        """Callers may pass their own client; they may not make this project anonymous."""
        client, handler = replay(httpx.Response(200, json={}))
        with client:
            get_with_retry(client, URL)
        assert handler.agents == [USER_AGENT]
        assert "python-httpx" not in handler.agents[0]


class TestTransientFailures:
    def test_retries_a_5xx_then_returns_the_success(self) -> None:
        client, handler = replay(
            httpx.Response(503),
            httpx.Response(502),
            httpx.Response(200, json={"ok": True}),
        )
        clock = Clock()
        with client:
            response = get_with_retry(client, URL, sleep=clock)
        assert response.json() == {"ok": True}
        assert len(handler.requests) == 3
        assert clock.waits == [1.0, 2.0]

    def test_retries_a_timeout(self) -> None:
        client, handler = replay(
            httpx.ConnectTimeout("read timed out"),
            httpx.Response(200, json={}),
        )
        clock = Clock()
        with client:
            get_with_retry(client, URL, sleep=clock)
        assert len(handler.requests) == 2

    def test_retries_a_connection_failure(self) -> None:
        client, handler = replay(httpx.ConnectError("refused"), httpx.Response(200, json={}))
        with client:
            get_with_retry(client, URL, sleep=Clock())
        assert len(handler.requests) == 2

    def test_retries_a_429(self) -> None:
        client, handler = replay(httpx.Response(429), httpx.Response(200, json={}))
        with client:
            get_with_retry(client, URL, sleep=Clock())
        assert len(handler.requests) == 2

    def test_backoff_grows_exponentially_and_is_capped(self) -> None:
        client, _ = replay(*[httpx.Response(503) for _ in range(8)])
        clock = Clock()
        with client, pytest.raises(FetchError):
            get_with_retry(client, URL, max_attempts=8, sleep=clock)
        assert clock.waits == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0]
        assert max(clock.waits) == BACKOFF_CAP_SECONDS

    def test_attempts_are_bounded(self) -> None:
        """Bounded means bounded: a sulking endpoint must not become an infinite loop."""
        client, handler = replay(*[httpx.Response(500) for _ in range(MAX_ATTEMPTS)])
        clock = Clock()
        with client, pytest.raises(FetchError) as caught:
            get_with_retry(client, URL, sleep=clock)
        assert len(handler.requests) == MAX_ATTEMPTS
        assert len(clock.waits) == MAX_ATTEMPTS - 1
        assert f"after {MAX_ATTEMPTS} attempts" in str(caught.value)
        assert "500" in str(caught.value)

    def test_exhausted_transport_error_keeps_the_original_cause(self) -> None:
        client, _ = replay(*[httpx.ConnectError("refused") for _ in range(MAX_ATTEMPTS)])
        with client, pytest.raises(FetchError) as caught:
            get_with_retry(client, URL, sleep=Clock())
        assert isinstance(caught.value.__cause__, httpx.ConnectError)


class TestRetryAfter:
    def test_numeric_retry_after_overrides_the_backoff(self) -> None:
        client, _ = replay(
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(200, json={}),
        )
        clock = Clock()
        with client:
            get_with_retry(client, URL, sleep=clock)
        assert clock.waits == [7.0]

    def test_http_date_retry_after_is_understood(self) -> None:
        when = datetime.now(UTC) + timedelta(seconds=30)
        client, _ = replay(
            httpx.Response(503, headers={"Retry-After": format_datetime(when, usegmt=True)}),
            httpx.Response(200, json={}),
        )
        clock = Clock()
        with client:
            get_with_retry(client, URL, sleep=clock)
        assert 20.0 <= clock.waits[0] <= 31.0

    def test_a_date_already_past_waits_zero_rather_than_negative(self) -> None:
        when = datetime.now(UTC) - timedelta(seconds=60)
        client, _ = replay(
            httpx.Response(503, headers={"Retry-After": format_datetime(when, usegmt=True)}),
            httpx.Response(200, json={}),
        )
        clock = Clock()
        with client:
            get_with_retry(client, URL, sleep=clock)
        assert clock.waits == [0.0]

    def test_unparseable_retry_after_falls_back_to_backoff(self) -> None:
        client, _ = replay(
            httpx.Response(503, headers={"Retry-After": "soon-ish"}),
            httpx.Response(200, json={}),
        )
        clock = Clock()
        with client:
            get_with_retry(client, URL, sleep=clock)
        assert clock.waits == [1.0]

    def test_an_hour_long_retry_after_stops_instead_of_holding_the_build(self) -> None:
        """Respecting a long Retry-After means leaving, not sleeping through it."""
        client, handler = replay(httpx.Response(503, headers={"Retry-After": "3600"}))
        clock = Clock()
        with client, pytest.raises(FetchError) as caught:
            get_with_retry(client, URL, sleep=clock)
        assert clock.waits == []
        assert len(handler.requests) == 1
        assert "3600s wait" in str(caught.value)
        assert RETRY_AFTER_CAP_SECONDS == 120.0


class TestRefusals:
    """A 403 or 404 is a decision. Retrying one is just knocking harder."""

    def test_403_is_not_retried(self) -> None:
        client, handler = replay(httpx.Response(403))
        clock = Clock()
        with client, pytest.raises(FetchError) as caught:
            get_with_retry(client, URL, sleep=clock)
        assert len(handler.requests) == 1
        assert clock.waits == []
        assert caught.value.status_code == 403

    def test_403_message_says_what_happened_and_what_to_do(self) -> None:
        client, _ = replay(httpx.Response(403))
        with client, pytest.raises(FetchError) as caught:
            get_with_retry(client, URL, sleep=Clock())
        message = str(caught.value)
        assert "cxsearch.dol.gov" in message
        assert "403 Forbidden" in message
        assert "refused" in message
        # The operational point: this is a CI/datacenter-IP symptom, with a way out.
        assert "CI" in message and "datacenter" in message
        assert "committed data snapshot" in message

    def test_404_is_not_retried(self) -> None:
        client, handler = replay(httpx.Response(404))
        with client, pytest.raises(FetchError) as caught:
            get_with_retry(client, URL, sleep=Clock())
        assert len(handler.requests) == 1
        assert caught.value.status_code == 404
        assert "Not retried" in str(caught.value)

    def test_401_is_not_retried(self) -> None:
        client, handler = replay(httpx.Response(401))
        with client, pytest.raises(FetchError):
            get_with_retry(client, URL, sleep=Clock())
        assert len(handler.requests) == 1

    def test_fetch_error_carries_the_url_it_failed_on(self) -> None:
        client, _ = replay(httpx.Response(403))
        with client, pytest.raises(FetchError) as caught:
            get_with_retry(client, URL, sleep=Clock())
        assert caught.value.url == URL


class TestDolClient:
    def test_benchmark_fetch_identifies_itself(self) -> None:
        source = {"field_c_completed_percent": 0.71, "field_c_median_earnings": -1}
        client, handler = replay(search_response({"_source": source}))
        with client:
            benchmark = dol_etp.fetch_state_benchmark("CA", client=client)
        assert benchmark is not None
        assert benchmark.completion_rate == 0.71
        # Unchanged by the transport work: -1 still means "not reported", never zero.
        assert benchmark.median_earnings is None
        assert handler.agents == [USER_AGENT]

    def test_benchmark_fetch_returns_none_when_nothing_is_published(self) -> None:
        client, _ = replay(search_response())
        with client:
            assert dol_etp.fetch_state_benchmark("CA", client=client) is None

    def test_program_fetch_surfaces_the_403_guidance(self) -> None:
        client, handler = replay(httpx.Response(403))
        with client, pytest.raises(FetchError) as caught:
            list(dol_etp.fetch_programs("CA", client=client))
        assert len(handler.requests) == 1
        assert "datacenter" in str(caught.value)

    def test_inter_page_throttle_is_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The pause between pages is a courtesy to a public service. It stays."""
        clock = Clock()
        monkeypatch.setattr(dol_etp.time, "sleep", clock)
        client, handler = replay(
            search_response(hit("u1", 1), hit("u2", 2)),
            search_response(hit("u3", 3)),
        )
        with client:
            programs = list(dol_etp.fetch_programs("CA", page_size=2, client=client))
        assert [p.uuid for p in programs] == ["u1", "u2", "u3"]
        assert len(handler.requests) == 2
        assert clock.waits == [PAUSE_BETWEEN_PAGES]
        assert PAUSE_BETWEEN_PAGES == 0.4
        assert handler.agents == [USER_AGENT, USER_AGENT]

    def test_pages_are_fetched_in_sequence_not_in_parallel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A generator that pulls one page at a time is the whole rate limit."""
        monkeypatch.setattr(dol_etp.time, "sleep", Clock())
        client, handler = replay(
            search_response(hit("u1", 1)),
            search_response(hit("u2", 2)),
        )
        with client:
            stream = dol_etp.fetch_programs("CA", page_size=1, client=client)
            next(stream)
            assert len(handler.requests) == 1
            next(stream)
            assert len(handler.requests) == 2


CKAN_PACKAGE = {
    "result": {
        "resources": [
            {"format": "PDF", "url": "https://data.ca.gov/dataset/x/notes.pdf"},
            {"format": "CSV", "url": "https://data.ca.gov/dataset/x/projections.csv"},
        ]
    }
}

PROJECTION_CSV = (
    "Area Type,Area Name,Period,SOC Level,"
    "Standard Occupational Classification (SOC),Occupational Title,Median Annual Wage\n"
    "State,California,2024-2034,4,15-1252,Software Developers,142480\n"
)


class TestEddClient:
    def test_ckan_lookup_identifies_itself(self) -> None:
        client, handler = replay(httpx.Response(200, json=CKAN_PACKAGE))
        with client:
            url = edd_lmi.resolve_resource_url("oews", client=client)
        assert url == "https://data.ca.gov/dataset/x/projections.csv"
        assert handler.agents == [USER_AGENT]

    def test_ckan_lookup_retries_a_transient_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        clock = Clock()
        monkeypatch.setattr(dol_etp.time, "sleep", clock)
        client, handler = replay(
            httpx.Response(502),
            httpx.Response(200, json=CKAN_PACKAGE),
        )
        with client:
            assert edd_lmi.resolve_resource_url("oews", client=client)
        assert len(handler.requests) == 2
        assert clock.waits == [1.0]

    def test_ckan_403_is_reported_not_hammered(self) -> None:
        client, handler = replay(httpx.Response(403))
        with client, pytest.raises(FetchError) as caught:
            edd_lmi.resolve_resource_url("oews", client=client)
        assert len(handler.requests) == 1
        assert "data.ca.gov" in str(caught.value)

    def test_projection_download_identifies_itself_on_both_hops(self) -> None:
        client, handler = replay(
            httpx.Response(200, json=CKAN_PACKAGE),
            httpx.Response(200, text=PROJECTION_CSV),
        )
        with client:
            rows = edd_lmi.fetch_projections(client=client)
        assert [r.soc_code for r in rows] == ["15-1252"]
        assert rows[0].median_annual_wage == 142480.0
        assert handler.agents == [USER_AGENT, USER_AGENT]
