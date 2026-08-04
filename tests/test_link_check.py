"""Tests for the provider-link checker.

The property defended hardest here is the one whose failure is invisible: a live provider
must never be classified dead. A false "dead" hides a real school from someone trying to
enrol, and nothing downstream can tell it apart from a true one. So most of what follows is
about the *conservatism* of the classifier -- 403, 405, timeouts, 5xx and anything else that
merely proves a host dislikes robots stays ``indeterminate`` -- and about the invariant that
an unchecked URL is not a dead URL.
"""

from __future__ import annotations

import json
import ssl
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, get_args

import httpx
import pytest

from camino.sources import link_check
from camino.sources.dol_etp import USER_AGENT
from camino.sources.link_check import (
    CACHE_TTL,
    MAX_ATTEMPTS,
    RETRYABLE_REASONS,
    VERDICT_BY_REASON,
    LinkCheck,
    LinkCheckCache,
    Reason,
    Verdict,
    build_client,
    check_url,
    check_urls,
    https_variant,
    is_dead,
    summarise,
    upgrade_for,
    verdict_for,
)

PAGE = "https://example.edu/programs/welding"
ROOT = "https://example.edu/"
INSECURE = "http://example.edu/programs/welding"
NOW = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


def at(moment: datetime = NOW) -> Any:
    return lambda: moment


class Replayer:
    """Mock transport that replays scripted outcomes and remembers what it was asked.

    Runs out deliberately: an unplanned extra request means the checker knocked on a small
    college's door more often than the test allowed, and that should fail loudly.
    """

    def __init__(self, *outcomes: httpx.Response | Exception) -> None:
        self._outcomes = list(outcomes)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert self._outcomes, f"unexpected extra request: {request.method} {request.url}"
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, httpx.RequestError):
            outcome.request = request
            raise outcome
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    @property
    def calls(self) -> list[tuple[str, str]]:
        return [(r.method, str(r.url)) for r in self.requests]

    @property
    def methods(self) -> list[str]:
        return [r.method for r in self.requests]


def replay(*outcomes: httpx.Response | Exception) -> tuple[httpx.Client, Replayer]:
    """A client with no default headers, so the checker must supply its own identity."""
    handler = Replayer(*outcomes)
    return httpx.Client(transport=httpx.MockTransport(handler)), handler


class Clock:
    """Stand-in for ``time.sleep`` that records instead of waiting."""

    def __init__(self) -> None:
        self.waits: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


def redirect(location: str, status: int = 301) -> httpx.Response:
    return httpx.Response(status, headers={"Location": location})


@pytest.fixture
def resolving(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Every hostname resolves, so a connect failure is the server's, not DNS's."""
    monkeypatch.setattr(link_check, "_host_resolves", lambda host: True)
    yield


@pytest.fixture
def unresolvable(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(link_check, "_host_resolves", lambda host: False)
    yield


def probe(*outcomes: httpx.Response | Exception, url: str = PAGE, **kwargs: Any) -> LinkCheck:
    """Run one check against a scripted server, for tests that only assert the verdict."""
    client, _ = replay(*outcomes)
    kwargs.setdefault("sleep", Clock())
    with client:
        return check_url(url, client=client, now=at(), **kwargs)


class TestClassificationTable:
    """The reason -> verdict mapping is the whole argument, so it is checked as data."""

    def test_every_reason_has_a_verdict(self) -> None:
        assert set(get_args(Reason)) == set(VERDICT_BY_REASON)

    def test_no_verdict_means_unchecked(self) -> None:
        """Absence is not a value. A URL nobody read has no LinkCheck at all."""
        assert set(get_args(Verdict)) == {"alive", "dead", "indeterminate"}

    def test_only_conclusive_evidence_counts_as_dead(self) -> None:
        dead = {reason for reason, verdict in VERDICT_BY_REASON.items() if verdict == "dead"}
        assert dead == {"dns_failure", "connection_failed", "not_found", "gone"}

    def test_a_refusal_is_never_dead(self) -> None:
        """403 and 405 mean "not for robots", which is not a claim about the page."""
        assert VERDICT_BY_REASON["forbidden"] == "indeterminate"
        assert VERDICT_BY_REASON["method_not_allowed"] == "indeterminate"

    def test_retryable_reasons_are_real_reasons(self) -> None:
        assert set(get_args(Reason)) >= RETRYABLE_REASONS

    def test_deterministic_failures_are_not_retried(self) -> None:
        assert "tls_failure" not in RETRYABLE_REASONS
        assert "too_many_redirects" not in RETRYABLE_REASONS


class TestIdentity:
    """The User-Agent is a disclosure, not a disguise -- same rule as every other client."""

    def test_sends_the_project_user_agent(self) -> None:
        client, handler = replay(httpx.Response(200))
        with client:
            check_url(PAGE, client=client, sleep=Clock(), now=at())
        assert handler.requests[0].headers["User-Agent"] == USER_AGENT

    def test_does_not_impersonate_a_browser(self) -> None:
        lowered = link_check.REQUEST_HEADERS["User-Agent"].lower()
        for disguise in ("mozilla", "chrome", "safari", "applewebkit", "gecko", "edg/"):
            assert disguise not in lowered

    def test_build_client_identifies_itself_and_follows_redirects(self) -> None:
        with build_client() as client:
            assert client.headers["User-Agent"] == USER_AGENT
            assert client.follow_redirects is True


class TestAlive:
    def test_a_plain_200_needs_one_request(self) -> None:
        client, handler = replay(httpx.Response(200))
        with client:
            check = check_url(PAGE, client=client, sleep=Clock(), now=at())
        assert (check.verdict, check.reason) == ("alive", "ok")
        assert check.status_code == 200
        assert handler.methods == ["HEAD"]

    def test_head_is_tried_before_get(self) -> None:
        client, handler = replay(httpx.Response(200))
        with client:
            check_url(PAGE, client=client, sleep=Clock(), now=at())
        assert handler.methods == ["HEAD"]

    def test_a_redirect_chain_ending_at_a_page_is_alive(self) -> None:
        check = probe(
            redirect("https://www.example.edu/programs/welding"),
            httpx.Response(200),
        )
        assert check.verdict == "alive"
        assert check.reason == "ok"
        assert check.final_url == "https://www.example.edu/programs/welding"

    def test_a_deep_page_redirected_to_the_site_root_is_flagged_not_condemned(self) -> None:
        """The provider is fine; this record's page is not. Two different findings."""
        check = probe(redirect(ROOT), httpx.Response(200))
        assert check.verdict == "alive"
        assert check.reason == "redirected_to_site_root"

    def test_a_site_root_that_stays_at_the_root_is_ordinary(self) -> None:
        check = probe(httpx.Response(200), url=ROOT)
        assert check.reason == "ok"

    def test_a_redirect_to_another_domain_is_alive_but_noted(self) -> None:
        check = probe(redirect("https://catalog.hosted-cms.com/x"), httpx.Response(200))
        assert check.verdict == "alive"
        assert check.reason == "redirected_offsite"

    def test_www_is_the_same_site(self) -> None:
        check = probe(redirect("https://www.example.edu/programs/welding"), httpx.Response(200))
        assert check.reason == "ok"

    def test_a_subdomain_is_the_same_site(self) -> None:
        check = probe(redirect("https://apply.example.edu/welding"), httpx.Response(200))
        assert check.reason == "ok"


class TestDead:
    def test_a_404_confirmed_by_get_is_dead(self) -> None:
        client, handler = replay(httpx.Response(404), httpx.Response(404))
        with client:
            check = check_url(PAGE, client=client, sleep=Clock(), now=at())
        assert (check.verdict, check.reason) == ("dead", "not_found")
        assert handler.methods == ["HEAD", "GET"]

    def test_a_410_is_dead(self) -> None:
        check = probe(httpx.Response(410), httpx.Response(410))
        assert (check.verdict, check.reason) == ("dead", "gone")

    def test_a_host_that_does_not_resolve_is_dead(self, unresolvable: None) -> None:
        client, _ = replay(
            httpx.ConnectError("nodename nor servname provided"),
            httpx.ConnectError("nodename nor servname provided"),
            httpx.ConnectError("nodename nor servname provided"),
        )
        with client:
            check = check_url(PAGE, client=client, sleep=Clock(), now=at())
        assert (check.verdict, check.reason) == ("dead", "dns_failure")
        assert check.status_code is None
        assert check.final_url is None

    def test_a_name_that_does_not_resolve_is_not_asked_again_with_get(
        self, unresolvable: None
    ) -> None:
        """A GET cannot make DNS work. Asking anyway is noise, not diligence."""
        client, handler = replay(*[httpx.ConnectError("no such host")] * MAX_ATTEMPTS)
        with client:
            check_url(PAGE, client=client, sleep=Clock(), now=at())
        assert set(handler.methods) == {"HEAD"}

    def test_a_refused_connection_is_dead_but_named_separately(self, resolving: None) -> None:
        """It resolves and will not talk. Weaker evidence than DNS, so a distinct reason."""
        client, _ = replay(*[httpx.ConnectError("connection refused")] * (2 * MAX_ATTEMPTS))
        with client:
            check = check_url(PAGE, client=client, sleep=Clock(), now=at())
        assert (check.verdict, check.reason) == ("dead", "connection_failed")


class TestConservatism:
    """Everything a host might do to a robot that is not evidence about the page."""

    def test_a_403_on_both_methods_is_indeterminate(self) -> None:
        check = probe(httpx.Response(403), httpx.Response(403))
        assert (check.verdict, check.reason) == ("indeterminate", "forbidden")

    def test_a_403_on_head_but_a_200_on_get_is_alive(self) -> None:
        """The single most important false positive this checker has to avoid."""
        client, handler = replay(httpx.Response(403), httpx.Response(200))
        with client:
            check = check_url(PAGE, client=client, sleep=Clock(), now=at())
        assert check.verdict == "alive"
        assert handler.methods == ["HEAD", "GET"]

    def test_a_404_on_head_but_a_200_on_get_is_alive(self) -> None:
        """Some servers answer HEAD badly. A negative HEAD is never believed alone."""
        check = probe(httpx.Response(404), httpx.Response(200))
        assert check.verdict == "alive"

    def test_a_405_on_head_but_a_200_on_get_is_alive(self) -> None:
        check = probe(httpx.Response(405), httpx.Response(200))
        assert check.verdict == "alive"

    def test_a_405_on_both_is_indeterminate(self) -> None:
        check = probe(httpx.Response(405), httpx.Response(405))
        assert (check.verdict, check.reason) == ("indeterminate", "method_not_allowed")

    def test_a_persistent_500_is_broken_not_gone(self) -> None:
        check = probe(*[httpx.Response(500)] * (2 * MAX_ATTEMPTS))
        assert (check.verdict, check.reason) == ("indeterminate", "server_error")

    def test_a_cloudflare_525_is_indeterminate(self) -> None:
        client, _ = replay(httpx.Response(525), httpx.Response(525))
        with client:
            check = check_url(PAGE, client=client, sleep=Clock(), now=at(), max_attempts=1)
        assert check.verdict == "indeterminate"

    def test_a_409_is_indeterminate(self) -> None:
        check = probe(httpx.Response(409), httpx.Response(409))
        assert (check.verdict, check.reason) == ("indeterminate", "other_client_error")

    def test_a_451_is_indeterminate(self) -> None:
        check = probe(httpx.Response(451), httpx.Response(451))
        assert check.verdict == "indeterminate"

    def test_a_timeout_means_slow_not_absent(self) -> None:
        client, _ = replay(*[httpx.ConnectTimeout("timed out")] * (2 * MAX_ATTEMPTS))
        with client:
            check = check_url(PAGE, client=client, sleep=Clock(), now=at())
        assert (check.verdict, check.reason) == ("indeterminate", "timeout")

    def test_a_bad_certificate_is_not_a_missing_page(self, resolving: None) -> None:
        """An expired cert is a broken door on a building that is still there."""
        failure = httpx.ConnectError("certificate verify failed")
        failure.__cause__ = ssl.SSLCertVerificationError("expired")
        client, handler = replay(failure, failure)
        with client:
            check = check_url(PAGE, client=client, sleep=Clock(), now=at())
        assert (check.verdict, check.reason) == ("indeterminate", "tls_failure")
        # Deterministic: tried once per method, never retried.
        assert handler.methods == ["HEAD", "GET"]

    def test_a_server_that_hangs_up_is_present_not_absent(self, resolving: None) -> None:
        client, _ = replay(*[httpx.RemoteProtocolError("server disconnected")] * (2 * MAX_ATTEMPTS))
        with client:
            check = check_url(PAGE, client=client, sleep=Clock(), now=at())
        assert (check.verdict, check.reason) == ("indeterminate", "protocol_error")

    def test_a_redirect_loop_is_indeterminate(self, resolving: None) -> None:
        client, _ = replay(httpx.TooManyRedirects("loop"), httpx.TooManyRedirects("loop"))
        with client:
            check = check_url(PAGE, client=client, sleep=Clock(), now=at())
        assert (check.verdict, check.reason) == ("indeterminate", "too_many_redirects")

    def test_a_soft_404_served_as_200_is_reported_alive(self) -> None:
        """Documented limitation: this cannot be detected without reading the body."""
        check = probe(httpx.Response(200, text="Sorry, page not found"))
        assert check.verdict == "alive"


class TestRetries:
    def test_a_transient_5xx_then_a_200_is_alive(self) -> None:
        clock = Clock()
        client, handler = replay(httpx.Response(503), httpx.Response(200))
        with client:
            check = check_url(PAGE, client=client, sleep=clock, now=at())
        assert check.verdict == "alive"
        assert check.attempts == 2
        assert clock.waits == [1.0]
        assert handler.methods == ["HEAD", "HEAD"]

    def test_backoff_is_bounded_and_exponential(self) -> None:
        clock = Clock()
        client, _ = replay(*[httpx.Response(503)] * (2 * MAX_ATTEMPTS))
        with client:
            check_url(PAGE, client=client, sleep=clock, now=at())
        assert clock.waits[:2] == [1.0, 2.0]

    def test_retry_after_overrides_the_backoff(self) -> None:
        clock = Clock()
        client, _ = replay(
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(200),
        )
        with client:
            check = check_url(PAGE, client=client, sleep=clock, now=at())
        assert check.verdict == "alive"
        assert clock.waits == [7.0]

    def test_a_retry_after_longer_than_we_will_hold_stops_rather_than_waits(self) -> None:
        """Being asked to go away for an hour is answered by going away, not by waiting."""
        clock = Clock()
        client, handler = replay(
            httpx.Response(503, headers={"Retry-After": "3600"}),
            httpx.Response(503, headers={"Retry-After": "3600"}),
        )
        with client:
            check = check_url(PAGE, client=client, sleep=clock, now=at())
        assert check.verdict == "indeterminate"
        assert handler.methods == ["HEAD", "GET"]
        assert 3600.0 not in clock.waits

    def test_a_404_is_never_retried(self) -> None:
        """A decision, not a hiccup. One HEAD, one confirming GET, and no more."""
        client, handler = replay(httpx.Response(404), httpx.Response(404))
        with client:
            check_url(PAGE, client=client, sleep=Clock(), now=at())
        assert handler.methods == ["HEAD", "GET"]

    def test_a_403_is_never_retried(self) -> None:
        client, handler = replay(httpx.Response(403), httpx.Response(403))
        with client:
            check_url(PAGE, client=client, sleep=Clock(), now=at())
        assert handler.methods == ["HEAD", "GET"]


class TestPoliteness:
    def test_a_pause_separates_head_from_get_on_the_same_host(self) -> None:
        clock = Clock()
        client, _ = replay(httpx.Response(404), httpx.Response(404))
        with client:
            check_url(PAGE, client=client, sleep=clock, now=at(), pause=2.5)
        assert 2.5 in clock.waits

    def test_a_get_body_is_never_downloaded(self) -> None:
        """A provider should not pay to serve a page nobody reads."""
        served: list[int] = []

        def body() -> Iterator[bytes]:
            served.append(1)
            yield b"x" * 5_000_000

        client, _ = replay(httpx.Response(404), httpx.Response(404, content=body()))
        with client:
            check_url(PAGE, client=client, sleep=Clock(), now=at())
        assert served == []

    def test_the_request_budget_for_one_url_is_bounded(self) -> None:
        client, handler = replay(*[httpx.Response(503)] * (2 * MAX_ATTEMPTS))
        with client:
            check = check_url(PAGE, client=client, sleep=Clock(), now=at())
        assert len(handler.requests) == 2 * MAX_ATTEMPTS
        assert check.attempts == 2 * MAX_ATTEMPTS


class TestHttpsUpgrade:
    def test_an_http_url_answering_on_https_is_upgradeable(self) -> None:
        client, handler = replay(httpx.Response(200), httpx.Response(200))
        with client:
            check = check_url(INSECURE, client=client, sleep=Clock(), now=at())
        assert check.verdict == "alive"
        assert check.https_alternative == "https://example.edu/programs/welding"
        assert check.is_upgradeable is True
        assert handler.calls[1] == ("HEAD", "https://example.edu/programs/welding")

    def test_an_http_url_with_no_https_answer_offers_no_upgrade(self) -> None:
        client, _ = replay(httpx.Response(200), httpx.Response(404), httpx.Response(404))
        with client:
            check = check_url(INSECURE, client=client, sleep=Clock(), now=at())
        assert check.verdict == "alive"
        assert check.https_alternative is None

    def test_a_site_that_already_redirects_to_https_costs_no_extra_request(self) -> None:
        client, handler = replay(
            redirect("https://example.edu/programs/welding"),
            httpx.Response(200),
        )
        with client:
            check = check_url(INSECURE, client=client, sleep=Clock(), now=at())
        assert check.https_alternative == "https://example.edu/programs/welding"
        assert len(handler.requests) == 2

    def test_a_dead_http_url_that_lives_on_https_is_still_worth_upgrading(self) -> None:
        client, _ = replay(httpx.Response(404), httpx.Response(404), httpx.Response(200))
        with client:
            check = check_url(INSECURE, client=client, sleep=Clock(), now=at())
        assert check.verdict == "dead"
        assert check.https_alternative == "https://example.edu/programs/welding"

    def test_a_name_that_does_not_resolve_is_not_probed_over_tls(self, unresolvable: None) -> None:
        client, handler = replay(*[httpx.ConnectError("no such host")] * MAX_ATTEMPTS)
        with client:
            check = check_url(INSECURE, client=client, sleep=Clock(), now=at())
        assert check.https_alternative is None
        assert all(url.startswith("http://") for _, url in handler.calls)

    def test_an_https_answer_that_lands_on_another_domain_is_not_an_upgrade(self) -> None:
        client, _ = replay(
            httpx.Response(200),
            redirect("https://parked.example-registrar.com/"),
            httpx.Response(200),
        )
        with client:
            check = check_url(INSECURE, client=client, sleep=Clock(), now=at())
        assert check.https_alternative is None

    def test_an_https_url_is_never_probed_twice(self) -> None:
        client, handler = replay(httpx.Response(200))
        with client:
            check = check_url(PAGE, client=client, sleep=Clock(), now=at())
        assert check.https_alternative is None
        assert len(handler.requests) == 1

    def test_probing_can_be_switched_off(self) -> None:
        client, handler = replay(httpx.Response(200))
        with client:
            check_url(INSECURE, client=client, sleep=Clock(), now=at(), probe_https=False)
        assert len(handler.requests) == 1

    def test_https_variant_only_rewrites_http(self) -> None:
        assert https_variant("http://x.edu/a?b=1") == "https://x.edu/a?b=1"
        assert https_variant(PAGE) is None


class TestMalformedInput:
    """A URL this checker cannot read is a caller bug, not a dead link."""

    @pytest.mark.parametrize(
        "url", ["/programs/welding", "javascript:alert(1)", "mailto:a@b.edu", "ftp://x.edu/"]
    )
    def test_a_non_http_url_is_refused_rather_than_condemned(self, url: str) -> None:
        client, handler = replay()
        with client, pytest.raises(ValueError, match="absolute http"):
            check_url(url, client=client, sleep=Clock(), now=at())
        assert handler.requests == []


class TestCache:
    def test_a_warm_entry_is_reused_without_a_request(self, tmp_path: Path) -> None:
        cache = LinkCheckCache(tmp_path, now=at())
        client, handler = replay(httpx.Response(200))
        with client:
            first = check_url(PAGE, client=client, cache=cache, sleep=Clock(), now=at())
            second = check_url(PAGE, client=client, cache=cache, sleep=Clock(), now=at())
        assert first == second
        assert len(handler.requests) == 1

    def test_entries_survive_a_new_cache_object(self, tmp_path: Path) -> None:
        client, _ = replay(httpx.Response(200))
        with client:
            check_url(PAGE, client=client, cache=LinkCheckCache(tmp_path), sleep=Clock(), now=at())
        reopened = LinkCheckCache(tmp_path, now=at())
        cached = reopened.get(PAGE)
        assert cached is not None
        assert cached.verdict == "alive"

    def test_a_stale_dead_verdict_expires_sooner_than_a_live_one(self, tmp_path: Path) -> None:
        """Hiding a provider that has come back is the costlier mistake, so dead ages out."""
        assert CACHE_TTL["dead"] < CACHE_TTL["alive"]
        assert CACHE_TTL["indeterminate"] < CACHE_TTL["dead"]

    @pytest.mark.parametrize(
        ("verdict", "response"),
        [("alive", httpx.Response(200)), ("dead", httpx.Response(410))],
    )
    def test_an_expired_entry_is_re_checked(
        self, tmp_path: Path, verdict: Verdict, response: httpx.Response
    ) -> None:
        client, _ = replay(response, response, httpx.Response(200))
        cache = LinkCheckCache(tmp_path, now=at())
        with client:
            first = check_url(PAGE, client=client, cache=cache, sleep=Clock(), now=at())
            assert first.verdict == verdict
            later = LinkCheckCache(tmp_path, now=at(NOW + CACHE_TTL[verdict] + timedelta(days=1)))
            assert later.get(PAGE) is None

    def test_a_corrupt_entry_is_ignored_rather_than_fatal(self, tmp_path: Path) -> None:
        cache = LinkCheckCache(tmp_path, now=at())
        path = cache.path_for(PAGE)
        assert path is not None
        path.write_text("{not json", encoding="utf-8")
        assert cache.get(PAGE) is None

    def test_an_entry_for_a_different_url_is_ignored(self, tmp_path: Path) -> None:
        """Cheap insurance against a digest collision handing back the wrong verdict."""
        cache = LinkCheckCache(tmp_path, now=at())
        path = cache.path_for(PAGE)
        assert path is not None
        other = LinkCheck(
            url="https://elsewhere.edu/",
            verdict="dead",
            reason="not_found",
            status_code=404,
            final_url=None,
            https_alternative=None,
            detail=None,
            checked_at=NOW,
            attempts=1,
        )
        path.write_text(json.dumps(other.as_dict()), encoding="utf-8")
        assert cache.get(PAGE) is None

    def test_an_unknown_reason_is_ignored_rather_than_trusted(self, tmp_path: Path) -> None:
        cache = LinkCheckCache(tmp_path, now=at())
        path = cache.path_for(PAGE)
        assert path is not None
        path.write_text(
            json.dumps(
                {
                    "url": PAGE,
                    "verdict": "dead",
                    "reason": "vibes",
                    "status_code": None,
                    "final_url": None,
                    "https_alternative": None,
                    "detail": None,
                    "checked_at": NOW.isoformat(),
                    "attempts": 1,
                }
            ),
            encoding="utf-8",
        )
        assert cache.get(PAGE) is None

    def test_no_directory_means_no_caching_and_no_error(self) -> None:
        cache = LinkCheckCache(None)
        client, handler = replay(httpx.Response(200), httpx.Response(200))
        with client:
            check_url(PAGE, client=client, cache=cache, sleep=Clock(), now=at())
            check_url(PAGE, client=client, cache=cache, sleep=Clock(), now=at())
        assert len(handler.requests) == 2

    def test_a_round_trip_preserves_every_field(self) -> None:
        original = LinkCheck(
            url=INSECURE,
            verdict="alive",
            reason="redirected_to_site_root",
            status_code=200,
            final_url="http://example.edu/",
            https_alternative="https://example.edu/",
            detail=None,
            checked_at=NOW,
            attempts=3,
        )
        assert LinkCheck.from_dict(original.as_dict()) == original


class TestCheckUrls:
    def test_every_distinct_url_is_checked_once(self) -> None:
        urls = ["https://a.edu/x", "https://b.edu/y", "https://a.edu/x"]
        client, handler = replay(*[httpx.Response(200)] * 2)
        with client:
            results = check_urls(urls, client=client, sleep=Clock(), now=at(), max_workers=1)
        assert set(results) == {"https://a.edu/x", "https://b.edu/y"}
        assert len(handler.requests) == 2

    def test_requests_to_one_site_are_spaced(self) -> None:
        clock = Clock()
        client, _ = replay(httpx.Response(200), httpx.Response(200))
        with client:
            check_urls(
                ["https://a.edu/x", "https://a.edu/y"],
                client=client,
                sleep=clock,
                now=at(),
                max_workers=1,
                pause=1.5,
            )
        assert 1.5 in clock.waits

    def test_one_site_is_never_read_by_two_workers_at_once(self) -> None:
        """Concurrency is across providers, never within one."""
        seen: dict[str, set[int]] = {}
        lock = threading.Lock()

        def handler(request: httpx.Request) -> httpx.Response:
            host = str(request.url.host)
            with lock:
                seen.setdefault(host, set()).add(threading.get_ident())
            return httpx.Response(200)

        urls = [f"https://site{n}.edu/page{p}" for n in range(6) for p in range(4)]
        client = httpx.Client(transport=httpx.MockTransport(handler))
        with client:
            check_urls(urls, client=client, sleep=Clock(), now=at(), max_workers=4)
        assert all(len(threads) == 1 for threads in seen.values())

    def test_www_and_bare_host_share_one_worker(self) -> None:
        """Two names for one server must still be read one request at a time."""
        threads: set[int] = set()
        lock = threading.Lock()

        def handler(request: httpx.Request) -> httpx.Response:
            with lock:
                threads.add(threading.get_ident())
            return httpx.Response(200)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        with client:
            check_urls(
                ["https://example.edu/a", "https://www.example.edu/b"],
                client=client,
                sleep=Clock(),
                now=at(),
                max_workers=4,
            )
        assert len(threads) == 1

    def test_progress_is_reported_as_results_arrive(self) -> None:
        seen: list[str] = []
        client, _ = replay(httpx.Response(200), httpx.Response(200))
        with client:
            check_urls(
                ["https://a.edu/x", "https://b.edu/y"],
                client=client,
                sleep=Clock(),
                now=at(),
                max_workers=1,
                on_result=lambda check: seen.append(check.url),
            )
        assert sorted(seen) == ["https://a.edu/x", "https://b.edu/y"]

    def test_a_caller_supplied_client_is_left_open(self) -> None:
        client, _ = replay(httpx.Response(200))
        with client:
            check_urls(["https://a.edu/x"], client=client, sleep=Clock(), now=at(), max_workers=1)
            assert client.is_closed is False


class TestUncheckedIsNotDead:
    """The invariant. An absent result is a gap in knowledge, never a verdict."""

    def _checks(self) -> dict[str, LinkCheck]:
        client, _ = replay(httpx.Response(200))
        with client:
            return check_urls(
                ["https://a.edu/x"], client=client, sleep=Clock(), now=at(), max_workers=1
            )

    def test_an_unchecked_url_has_no_verdict(self) -> None:
        assert verdict_for(self._checks(), "https://never-looked.edu/") is None

    def test_an_unchecked_url_is_not_dead_and_is_not_alive(self) -> None:
        assert is_dead(self._checks(), "https://never-looked.edu/") is None

    def test_a_missing_url_is_not_a_verdict_either(self) -> None:
        """A program with no provider link has no link to be dead."""
        assert verdict_for(self._checks(), None) is None
        assert is_dead(self._checks(), None) is None
        assert upgrade_for(self._checks(), None) is None

    def test_a_checked_url_answers_true_or_false(self) -> None:
        checks = self._checks()
        assert is_dead(checks, "https://a.edu/x") is False
        assert verdict_for(checks, "https://a.edu/x") == "alive"

    def test_an_unchecked_url_offers_no_upgrade(self) -> None:
        assert upgrade_for(self._checks(), "https://never-looked.edu/") is None


class TestSummarise:
    def _checks(self) -> dict[str, LinkCheck]:
        def make(url: str, reason: Reason, upgrade: str | None = None) -> LinkCheck:
            return LinkCheck(
                url=url,
                verdict=VERDICT_BY_REASON[reason],
                reason=reason,
                status_code=None,
                final_url=None,
                https_alternative=upgrade,
                detail=None,
                checked_at=NOW,
                attempts=1,
            )

        return {
            "http://gone.edu": make("http://gone.edu", "dns_failure"),
            "https://missing.edu/p": make("https://missing.edu/p", "not_found"),
            "http://shy.edu": make("http://shy.edu", "forbidden", "https://shy.edu"),
            "https://fine.edu": make("https://fine.edu", "ok"),
        }

    def test_counts_urls_and_the_pages_that_depend_on_them(self) -> None:
        pages = {"http://gone.edu": 126, "https://missing.edu/p": 22}
        summary = summarise(self._checks(), pages_per_url=pages)
        assert summary.urls_checked == 4
        assert summary.by_verdict["dead"] == 2
        assert summary.pages_by_verdict["dead"] == 148
        assert summary.pages_affected == 150

    def test_a_url_with_no_page_count_still_counts_once(self) -> None:
        summary = summarise(self._checks())
        assert summary.pages_affected == 4

    def test_counts_upgradeable_urls(self) -> None:
        summary = summarise(self._checks(), pages_per_url={"http://shy.edu": 9})
        assert summary.upgradeable_urls == 1
        assert summary.upgradeable_pages == 9

    def test_reasons_are_kept_separate_within_a_verdict(self) -> None:
        summary = summarise(self._checks())
        assert summary.by_reason["dns_failure"] == 1
        assert summary.by_reason["not_found"] == 1

    def test_an_empty_run_summarises_to_nothing_rather_than_failing(self) -> None:
        summary = summarise({})
        assert summary.urls_checked == 0
        assert summary.by_verdict == {}
