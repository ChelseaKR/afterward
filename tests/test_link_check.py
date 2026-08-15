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
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, get_args

import httpx
import pytest

from afterward.sources import link_check, link_review
from afterward.sources.dol_etp import USER_AGENT
from afterward.sources.link_check import (
    CACHE_TTL,
    CLASSIFIER_VERSION,
    DOCUMENT_VERSION,
    LABEL_PROGRAM_PAGE,
    LABEL_PROVIDER_HOME,
    MAX_ATTEMPTS,
    NOTICE_FOR_SALE,
    NOTICE_REDIRECT_UNCONFIRMED,
    NOTICE_REDIRECT_UNRELATED,
    NOTICE_UNREACHABLE,
    RETRYABLE_REASONS,
    SUBSTITUTION_FRONT_PAGE,
    SUBSTITUTION_HTTPS,
    VERDICT_BY_REASON,
    LinkCheck,
    LinkCheckCache,
    Reason,
    Verdict,
    build_client,
    check_url,
    check_urls,
    checks_document,
    checks_from_document,
    decide,
    front_page_candidates,
    front_page_for,
    https_variant,
    is_dead,
    site_root,
    summarise,
    upgrade_for,
    verdict_for,
)

PAGE = "https://example.edu/programs/welding"
ROOT = "https://example.edu/"
INSECURE = "http://example.edu/programs/welding"
OFFSITE = "https://somewhere-else.example/"
"""Where an off-site redirect landed. Which domain it is decides everything about the
decision and nothing about the check, so the tests that care name it."""
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
            # Only fill it in when the test has not deliberately set one, so a test can
            # model a failure that happened at a redirect target.
            if getattr(outcome, "_request", None) is None:
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


_SERVED: list[int] = []
"""Which chunks of a scripted body the checker actually pulled.

Politeness towards a small college is measured in what it was asked to send, so the tests
count that rather than trusting a comment about it.
"""


def _counted(*chunks: bytes) -> Iterator[bytes]:
    """A response body that records each chunk at the moment it is pulled."""
    for index, chunk in enumerate(chunks or (b"x" * 5_000_000,)):
        _SERVED.append(index)
        yield chunk


def _titled(title: str, *, padding: int = 0) -> str:
    """A page whose only relevant feature is what it calls itself."""
    return f"<!doctype html><html><head>{'<!--' + 'x' * padding + '-->' if padding else ''}<title>{title}</title></head><body><p>hello</p></body></html>"


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


def checked(
    url: str,
    reason: Reason,
    *,
    upgrade: str | None = None,
    final: str | None = None,
    when: datetime = NOW,
) -> LinkCheck:
    """A finished check, written by hand.

    The decision layer is a pure function of results, so its tests state the result they mean
    rather than staging an HTTP conversation that produces it.
    """
    return LinkCheck(
        url=url,
        verdict=VERDICT_BY_REASON[reason],
        reason=reason,
        status_code=None,
        final_url=final,
        https_alternative=upgrade,
        detail=None,
        checked_at=when,
        attempts=1,
    )


def results(*checks: LinkCheck) -> dict[str, LinkCheck]:
    return {check.url: check for check in checks}


class TestClassificationTable:
    """The reason -> verdict mapping is the whole argument, so it is checked as data."""

    def test_every_reason_has_a_verdict(self) -> None:
        assert set(get_args(Reason)) == set(VERDICT_BY_REASON)

    def test_no_verdict_means_unchecked(self) -> None:
        """Absence is not a value. A URL nobody read has no LinkCheck at all."""
        assert set(get_args(Verdict)) == {"alive", "dead", "indeterminate"}

    def test_only_conclusive_evidence_counts_as_dead(self) -> None:
        dead = {reason for reason, verdict in VERDICT_BY_REASON.items() if verdict == "dead"}
        assert dead == {
            "dns_failure",
            "not_found",
            "gone",
            "soft_not_found",
            "domain_for_sale",
        }

    def test_a_socket_that_would_not_open_is_not_evidence_about_a_provider(self) -> None:
        """Measured: every ``connection_failed`` in the real corpus was our end of the wire.

        ``http://www.ueicollege.com`` answered curl, netcat and httpx-given-the-IP on the
        same machine at the same moment, while httpx-given-the-name raised ENETUNREACH three
        times running. A name DNS has never heard of is evidence about a provider; a socket
        that would not open is evidence about a socket.
        """
        assert VERDICT_BY_REASON["connection_failed"] == "indeterminate"

    def test_a_refusal_is_never_dead(self) -> None:
        """403 and 405 mean "not for robots", which is not a claim about the page."""
        assert VERDICT_BY_REASON["forbidden"] == "indeterminate"
        assert VERDICT_BY_REASON["method_not_allowed"] == "indeterminate"

    def test_retryable_reasons_are_real_reasons(self) -> None:
        assert set(get_args(Reason)) >= RETRYABLE_REASONS

    def test_deterministic_failures_are_not_retried(self) -> None:
        assert "tls_failure" not in RETRYABLE_REASONS
        assert "too_many_redirects" not in RETRYABLE_REASONS


class TestHostResolution:
    """DNS is what separates "this provider's domain is gone" from "we could not connect"."""

    def test_a_missing_host_does_not_reach_the_resolver(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            link_check.socket,
            "getaddrinfo",
            lambda *a, **k: pytest.fail("looked up an empty host"),
        )
        assert link_check._host_resolves(None) is False
        assert link_check._host_resolves("") is False

    def test_a_name_the_resolver_rejects_does_not_resolve(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def refuse(*args: object, **kwargs: object) -> None:
            raise link_check.socket.gaierror(8, "nodename nor servname provided")

        monkeypatch.setattr(link_check.socket, "getaddrinfo", refuse)
        assert link_check._host_resolves("gone.example") is False

    def test_our_own_networking_failing_does_not_blame_the_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An OSError that is not a lookup failure is our problem, not theirs."""

        def broken(*args: object, **kwargs: object) -> None:
            raise OSError(65, "No route to host")

        monkeypatch.setattr(link_check.socket, "getaddrinfo", broken)
        assert link_check._host_resolves("real-school.example") is True

    def test_a_resolvable_name_resolves(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(link_check.socket, "getaddrinfo", lambda *a, **k: [object()])
        assert link_check._host_resolves("real-school.example") is True

    def test_a_urlless_comparison_is_not_the_same_site(self) -> None:
        assert link_check._same_site("https://a.edu/", "https://") is False


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
        assert handler.methods == ["GET"]

    def test_every_url_is_asked_the_way_a_reader_would_ask(self) -> None:
        """GET, and only GET, whatever the answer turns out to be.

        This module used to send HEAD first and confirm anything negative with a GET, because
        HEAD is the method servers implement worst -- the August 2026 audit measured 33 of 769
        live URLs whose HEAD disagreed with their GET, 8 of them answering HEAD with 404 for a
        page that GETs perfectly well. Asking once, with the method a browser uses, makes that
        whole class of disagreement unreachable rather than survivable, and it is what puts
        the page's own title within reach.
        """
        for outcome in (httpx.Response(200), httpx.Response(404), httpx.Response(403)):
            client, handler = replay(outcome)
            with client:
                check_url(PAGE, client=client, sleep=Clock(), now=at())
            assert handler.methods == ["GET"]

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
    def test_a_404_is_dead(self) -> None:
        client, handler = replay(httpx.Response(404))
        with client:
            check = check_url(PAGE, client=client, sleep=Clock(), now=at())
        assert (check.verdict, check.reason) == ("dead", "not_found")
        assert handler.methods == ["GET"]

    def test_a_410_is_dead(self) -> None:
        check = probe(httpx.Response(410))
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

    def test_a_name_that_does_not_resolve_is_asked_no_more_than_the_retry_budget(
        self, unresolvable: None
    ) -> None:
        """A resolver hiccup and a lapsed domain raise the same exception, so DNS is retried
        -- but only within the one budget, and never doubled by asking a second way."""
        client, handler = replay(*[httpx.ConnectError("no such host")] * MAX_ATTEMPTS)
        with client:
            check_url(PAGE, client=client, sleep=Clock(), now=at())
        assert handler.methods == ["GET"] * MAX_ATTEMPTS

    def test_a_redirect_to_a_dead_name_blames_the_dead_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The first host is alive and redirects to one that is not. Blame the second.

        ``https://www.sanjuan.edu/sunrisetc`` really does 301 to ``adulted.sanjuan.edu``,
        which does not resolve, and httpx reports the failing hop rather than the URL the
        request started from. Testing DNS on the starting URL would file a live school
        district's website as refusing connections.
        """
        asked: list[str | None] = []

        def resolves(host: str | None) -> bool:
            asked.append(host)
            return host != "adulted.example.edu"

        monkeypatch.setattr(link_check, "_host_resolves", resolves)
        failure = httpx.ConnectError("no such host")
        failure.request = httpx.Request("GET", "https://adulted.example.edu/")
        assert link_check._transport_reason(failure, PAGE) == "dns_failure"
        assert asked == ["adulted.example.edu"]

    def test_a_failure_with_no_request_attached_falls_back_to_the_url(
        self, unresolvable: None
    ) -> None:
        assert link_check._transport_reason(httpx.ConnectError("boom"), PAGE) == "dns_failure"

    def test_a_refused_connection_is_not_dead(self, resolving: None) -> None:
        """It resolves and would not talk. That is not the same finding as "it is gone"."""
        client, _ = replay(*[httpx.ConnectError("connection refused")] * (2 * MAX_ATTEMPTS))
        with client:
            check = check_url(PAGE, client=client, sleep=Clock(), now=at())
        assert (check.verdict, check.reason) == ("indeterminate", "connection_failed")


class TestConservatism:
    """Everything a host might do to a robot that is not evidence about the page."""

    def test_a_403_is_indeterminate(self) -> None:
        """The single most important false positive this checker has to avoid."""
        check = probe(httpx.Response(403))
        assert (check.verdict, check.reason) == ("indeterminate", "forbidden")

    def test_a_405_is_indeterminate(self) -> None:
        check = probe(httpx.Response(405))
        assert (check.verdict, check.reason) == ("indeterminate", "method_not_allowed")

    def test_a_persistent_500_is_broken_not_gone(self) -> None:
        check = probe(*[httpx.Response(500)] * MAX_ATTEMPTS)
        assert (check.verdict, check.reason) == ("indeterminate", "server_error")

    def test_a_cloudflare_525_is_indeterminate(self) -> None:
        client, _ = replay(httpx.Response(525))
        with client:
            check = check_url(PAGE, client=client, sleep=Clock(), now=at(), max_attempts=1)
        assert check.verdict == "indeterminate"

    def test_a_409_is_indeterminate(self) -> None:
        check = probe(httpx.Response(409))
        assert (check.verdict, check.reason) == ("indeterminate", "other_client_error")

    def test_a_451_is_indeterminate(self) -> None:
        check = probe(httpx.Response(451))
        assert check.verdict == "indeterminate"

    def test_a_timeout_means_slow_not_absent(self) -> None:
        client, _ = replay(*[httpx.ConnectTimeout("timed out")] * MAX_ATTEMPTS)
        with client:
            check = check_url(PAGE, client=client, sleep=Clock(), now=at())
        assert (check.verdict, check.reason) == ("indeterminate", "timeout")

    def test_a_bad_certificate_is_not_a_missing_page(self, resolving: None) -> None:
        """An expired cert is a broken door on a building that is still there."""
        failure = httpx.ConnectError("certificate verify failed")
        failure.__cause__ = ssl.SSLCertVerificationError("expired")
        client, handler = replay(failure)
        with client:
            check = check_url(PAGE, client=client, sleep=Clock(), now=at())
        assert (check.verdict, check.reason) == ("indeterminate", "tls_failure")
        # Deterministic: asked once, never retried.
        assert handler.methods == ["GET"]

    def test_a_server_that_hangs_up_is_present_not_absent(self, resolving: None) -> None:
        client, _ = replay(*[httpx.RemoteProtocolError("server disconnected")] * MAX_ATTEMPTS)
        with client:
            check = check_url(PAGE, client=client, sleep=Clock(), now=at())
        assert (check.verdict, check.reason) == ("indeterminate", "protocol_error")

    def test_a_redirect_loop_is_indeterminate(self, resolving: None) -> None:
        client, _ = replay(httpx.TooManyRedirects("loop"))
        with client:
            check = check_url(PAGE, client=client, sleep=Clock(), now=at())
        assert (check.verdict, check.reason) == ("indeterminate", "too_many_redirects")

    def test_a_host_still_rate_limiting_after_every_retry_is_indeterminate(self) -> None:
        """Being asked to slow down is not a statement about whether the page exists."""
        check = probe(*[httpx.Response(429)] * MAX_ATTEMPTS)
        assert (check.verdict, check.reason) == ("indeterminate", "rate_limited")


# ------------------------------------------------------------------------------------------
# What a 200 turns out to be
#
# Every title below was served by a real California provider with HTTP 200 on 2026-08-05, and
# every one of them sat behind a confident "Provider's website" link on a program page. They
# are quoted rather than invented because the pattern that matches them is only as good as the
# strings it was written against, and a fixture nobody measured is a guess with a test around
# it. 20 of the 767 live URLs in that corpus are in here; the other 747 must survive it
# untouched, which is what TestTitlesThatMeanNothing is for.
# ------------------------------------------------------------------------------------------

# Punctuation these providers actually served is escaped rather than typed: a curly
# apostrophe and an em dash are what separate a segment or sit inside one, and neither is
# distinguishable from its ASCII lookalike in a diff.
SOFT_404_TITLES = [
    "Not Found",  # springboard.com, 2 pages
    "404 - Elk Grove Unified School District",  # egace.egusd.net, 4 pages
    "404 Error",  # butte.edu, 3 pages
    "Page Not Found | Maiquela\u2019s Cosmetology Academy",  # maiquelascosmetology.net, 2 pages
]

FOR_SALE_TITLES = [
    "AselBeauty.com is for sale | HugeDomains",  # 2 pages
    "DronitEk.com is for sale | HugeDomains",  # 7 pages
    "intechcollege.com \u2014 Buy this expired domain | ED.com",  # 2 pages
    "catruckschool.com \u2014 Buy this expired domain | ED.com",  # 1 page
]

WORKING_TITLES = [
    "Medical Assistant Training | Bay Area Medical Academy",
    "Butte College",
    "Elk Grove Adult and Community Education - Home",
    "School of Career Education | Riverside County Office of Education",
    "Catalog",  # the elumenapp catalogue shell, ~50 pages of real course listings
    "Angeles University | Nursing & Business School in Los Angeles",
    "Truck Driving School in West Sacramento | 1 on 1 Truck Academy",
]


class TestWhatA200SaysItIs:
    """A 200 is a promise of a page, not a page.

    Measured on the August 2026 corpus: of the 767 provider URLs that answered 2xx, 20 were
    not pages at all -- 10 were the provider's own "page not found" screen served with HTTP
    200, and 10 were listings offering the address for sale. Between them they sat under 23
    program pages, each of which published "Provider's website" and sent a reader who was
    ready to enrol into a dead end that looked like a working link.
    """

    @pytest.mark.parametrize("title", SOFT_404_TITLES)
    def test_a_page_that_says_it_is_not_there_is_not_there(self, title: str) -> None:
        check = probe(httpx.Response(200, html=_titled(title)))
        assert (check.verdict, check.reason) == ("dead", "soft_not_found")

    @pytest.mark.parametrize("title", FOR_SALE_TITLES)
    def test_an_address_offered_for_sale_is_not_a_provider(self, title: str) -> None:
        check = probe(httpx.Response(200, html=_titled(title)))
        assert (check.verdict, check.reason) == ("dead", "domain_for_sale")

    def test_the_title_that_convicted_it_is_kept_as_the_evidence(self) -> None:
        """A verdict this consequential has to be arguable after the fact, not taken on
        trust, so the report records the sentence the page used about itself."""
        check = probe(httpx.Response(200, html=_titled("404 Error")))
        assert check.detail == "page title: 404 Error"
        assert check.status_code == 200, "the status line is still recorded as what it was"

    def test_what_the_page_says_outranks_where_it_landed(self) -> None:
        """Four of these were redirects to another domain, which this module used to call
        `redirected_offsite` and publish as a working link. The stronger finding wins."""
        check = probe(
            redirect("https://www.hugedomains.com/domain_profile.cfm?d=dronitek.com"),
            httpx.Response(200, html=_titled("DronitEk.com is for sale | HugeDomains")),
        )
        assert check.reason == "domain_for_sale"


class TestTitlesThatMeanNothing:
    """The other 747, and the ways a checker could wrongly convict one of them.

    A wrong `dead` hides a real school from someone trying to enrol, and nothing downstream
    can tell it apart from a true one. Every case here is a shape that appears in the real
    corpus and must survive untouched.
    """

    @pytest.mark.parametrize("title", WORKING_TITLES)
    def test_an_ordinary_provider_page_is_left_alone(self, title: str) -> None:
        check = probe(httpx.Response(200, html=_titled(title)))
        assert check.verdict == "alive"

    def test_a_page_that_merely_mentions_the_words_is_not_convicted(self) -> None:
        """The pattern is anchored to a whole title segment, not searched for inside one.

        A course about handling 404s, or a school whose page discusses what to do when a
        record is not found, says those words without being that page.
        """
        for title in (
            "Web Server Administration: 404 Handling | Example College",
            "What to do if your transcript is not found",
            "Lost and Found | Student Services",
            "Homes for sale: Real Estate Licensing Program",
        ):
            check = probe(httpx.Response(200, html=_titled(title)))
            assert check.verdict == "alive", title

    def test_a_page_with_no_title_is_not_judged(self) -> None:
        """16 URLs in the corpus answer with a SiteGround bot-check interstitial: a bare
        meta-refresh, no title, no text. They are byte-for-byte as empty as a parking stub,
        and the providers behind them are open. Emptiness is not evidence."""
        stub = '<html><head><meta http-equiv="refresh" content="0;/.well-known/sgcaptcha/"></head></html>'
        check = probe(httpx.Response(200, html=stub))
        assert check.verdict == "alive"

    def test_a_body_that_is_not_html_is_not_judged(self) -> None:
        """10 provider links in the corpus are PDFs. A PDF has no title element, and
        pattern-matching its bytes would be reading tea leaves."""
        check = probe(
            httpx.Response(
                200,
                headers={"content-type": "application/pdf"},
                content=b"%PDF-1.4 404 not found is for sale",
            )
        )
        assert check.verdict == "alive"

    def test_a_title_beyond_the_read_cap_fails_towards_alive(self) -> None:
        """32 of the corpus's 755 HTML responses push `</title>` past the cap, the furthest
        at 170 KB. Truncation can only cost a detection, never manufacture one -- a title
        nobody read is a title nobody matched."""
        check = probe(
            httpx.Response(
                200, html=_titled("404 Not Found", padding=link_check.BODY_READ_CAP + 1_000)
            )
        )
        assert check.verdict == "alive"

    def test_a_title_split_across_the_markup_is_still_read(self) -> None:
        """Entities and inline tags are how the page was written, not what it says."""
        check = probe(
            httpx.Response(200, html="<html><head><title>Page&nbsp;<b>Not Found</b></title></head>")
        )
        assert (check.verdict, check.reason) == ("dead", "soft_not_found")

    def test_a_body_that_stops_arriving_is_not_a_finding(self) -> None:
        """The status line already arrived and is the answer. A connection that dies while
        the page is still being read has told us nothing further, and must not be allowed to
        turn a page that answered into a page that did not."""

        def cut_off() -> Iterator[bytes]:
            yield b"<html><head><title>Welding Cer"
            raise httpx.ReadError("connection reset")

        check = probe(
            httpx.Response(200, headers={"content-type": "text/html"}, content=cut_off()),
            probe_https=False,
        )
        assert (check.verdict, check.reason) == ("alive", "ok")

    def test_only_a_2xx_body_is_read_for_a_title(self) -> None:
        """A 404 is already conclusive from its status line, and a 403's body is a bot wall
        rather than a page -- reading either could only muddle a settled answer."""
        check = probe(httpx.Response(403, html=_titled("404 Not Found")))
        assert (check.verdict, check.reason) == ("indeterminate", "forbidden")


class TestRetries:
    def test_a_transient_5xx_then_a_200_is_alive(self) -> None:
        clock = Clock()
        client, handler = replay(httpx.Response(503), httpx.Response(200))
        with client:
            check = check_url(PAGE, client=client, sleep=clock, now=at())
        assert check.verdict == "alive"
        assert check.attempts == 2
        assert clock.waits == [1.0]
        assert handler.methods == ["GET", "GET"]

    def test_backoff_is_bounded_and_exponential(self) -> None:
        clock = Clock()
        client, _ = replay(*[httpx.Response(503)] * MAX_ATTEMPTS)
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
        client, handler = replay(httpx.Response(503, headers={"Retry-After": "3600"}))
        with client:
            check = check_url(PAGE, client=client, sleep=clock, now=at())
        assert check.verdict == "indeterminate"
        assert handler.methods == ["GET"]
        assert 3600.0 not in clock.waits

    def test_a_404_is_never_retried(self) -> None:
        """A decision, not a hiccup. One request, and no more."""
        client, handler = replay(httpx.Response(404))
        with client:
            check_url(PAGE, client=client, sleep=Clock(), now=at())
        assert handler.methods == ["GET"]

    def test_a_403_is_never_retried(self) -> None:
        client, handler = replay(httpx.Response(403))
        with client:
            check_url(PAGE, client=client, sleep=Clock(), now=at())
        assert handler.methods == ["GET"]


class TestPoliteness:
    def test_a_pause_separates_a_url_from_the_https_probe_of_the_same_host(self) -> None:
        clock = Clock()
        client, _ = replay(httpx.Response(200), httpx.Response(200))
        with client:
            check_url(INSECURE, client=client, sleep=clock, now=at(), pause=2.5)
        assert 2.5 in clock.waits

    def test_only_a_page_that_answered_is_read_at_all(self) -> None:
        """A provider should not pay to serve a body that could not settle anything.

        A 404's body is not evidence -- the status line already said it -- and neither is a
        PDF's, which has no title to read. Both are closed unread. Only the 2xx HTML case is
        worth a provider's bandwidth, and even then only as far as ``</title>``.
        """
        for response in (
            httpx.Response(404, headers={"content-type": "text/html"}, content=_counted()),
            httpx.Response(200, headers={"content-type": "application/pdf"}, content=_counted()),
            httpx.Response(200, headers={"content-type": ""}, content=_counted()),
        ):
            _SERVED.clear()
            client, _ = replay(response)
            with client:
                check_url(PAGE, client=client, sleep=Clock(), now=at(), probe_https=False)
            assert _SERVED == []

    def test_a_page_is_read_only_as_far_as_its_title(self) -> None:
        """Measured median on the real corpus: 529 characters. The rest is never asked for."""
        _SERVED.clear()
        client, _ = replay(
            httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                content=_counted(
                    b"<html><head><title>Welding Certificate</title>", b"x" * 5_000_000
                ),
            )
        )
        with client:
            check = check_url(PAGE, client=client, sleep=Clock(), now=at(), probe_https=False)
        assert check.reason == "ok"
        assert _SERVED == [0], "read past </title> and made a provider serve the whole page"

    def test_the_request_budget_for_one_url_is_bounded(self) -> None:
        client, handler = replay(*[httpx.Response(503)] * MAX_ATTEMPTS)
        with client:
            check = check_url(PAGE, client=client, sleep=Clock(), now=at())
        assert len(handler.requests) == MAX_ATTEMPTS
        assert check.attempts == MAX_ATTEMPTS


class TestHttpsUpgrade:
    def test_an_http_url_answering_on_https_is_upgradeable(self) -> None:
        client, handler = replay(httpx.Response(200), httpx.Response(200))
        with client:
            check = check_url(INSECURE, client=client, sleep=Clock(), now=at())
        assert check.verdict == "alive"
        assert check.https_alternative == "https://example.edu/programs/welding"
        assert check.is_upgradeable is True
        assert handler.calls[1] == ("GET", "https://example.edu/programs/welding")

    def test_an_http_url_with_no_https_answer_offers_no_upgrade(self) -> None:
        client, _ = replay(httpx.Response(200), httpx.Response(404))
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
        client, _ = replay(httpx.Response(404), httpx.Response(200))
        with client:
            check = check_url(INSECURE, client=client, sleep=Clock(), now=at())
        assert check.verdict == "dead"
        assert check.https_alternative == "https://example.edu/programs/welding"

    def test_an_address_that_is_for_sale_is_not_probed_over_tls(self) -> None:
        """It is for sale on both schemes. Asking the parking host twice buys nothing."""
        client, handler = replay(httpx.Response(200, html=_titled("Example.com is for sale")))
        with client:
            check = check_url(INSECURE, client=client, sleep=Clock(), now=at())
        assert check.reason == "domain_for_sale"
        assert check.https_alternative is None
        assert all(url.startswith("http://") for _, url in handler.calls)

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

    def test_an_entry_from_an_older_classifier_is_re_read(self, tmp_path: Path) -> None:
        """The bug that kept a working detector from ever judging anything.

        The 2026-08-05 title detector changed what a 200 means, and every 200 in the cache was
        warm for thirty days, so a re-run handed back the verdicts it was written to replace.
        Ten "page not found" screens stayed published as working provider links. A cache entry
        now belongs to the classifier that wrote it.
        """
        cache = LinkCheckCache(tmp_path, now=at())
        path = cache.path_for(PAGE)
        assert path is not None
        stale = replace(checked(PAGE, "ok"), classifier_version=CLASSIFIER_VERSION - 1)
        path.write_text(json.dumps(stale.as_dict()), encoding="utf-8")
        assert cache.get(PAGE) is None

    def test_an_entry_written_before_the_classifier_was_versioned_is_re_read(
        self, tmp_path: Path
    ) -> None:
        """Older than every version there is, which is the only safe reading of a file that
        does not say."""
        cache = LinkCheckCache(tmp_path, now=at())
        path = cache.path_for(PAGE)
        assert path is not None
        payload = checked(PAGE, "ok").as_dict()
        del payload["classifier_version"]
        path.write_text(json.dumps(payload), encoding="utf-8")
        assert LinkCheck.from_dict(payload).classifier_version == 0
        assert cache.get(PAGE) is None

    def test_an_entry_from_this_classifier_is_still_served(self, tmp_path: Path) -> None:
        """The other half: a version bump costs one full re-read, not every read forever."""
        cache = LinkCheckCache(tmp_path, now=at())
        cache.put(checked(PAGE, "ok"))
        assert cache.get(PAGE) is not None

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

    def test_a_client_it_made_itself_is_closed_again(self, monkeypatch: pytest.MonkeyPatch) -> None:
        made: list[httpx.Client] = []

        def factory(*args: object, **kwargs: object) -> httpx.Client:
            client, _ = replay(httpx.Response(200))
            made.append(client)
            return client

        monkeypatch.setattr(link_check, "build_client", factory)
        results = check_urls(["https://a.edu/x"], sleep=Clock(), now=at(), max_workers=1)
        assert results["https://a.edu/x"].verdict == "alive"
        assert made[0].is_closed is True

    def test_nothing_to_check_is_not_an_error(self) -> None:
        """An empty corpus produces an empty mapping, not a mapping full of defaults."""
        assert check_urls([], sleep=Clock(), now=at()) == {}


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


class TestSiteRoot:
    def test_a_deep_path_has_a_front_page(self) -> None:
        assert site_root("https://example.edu/a/b/c.aspx?x=1") == "https://example.edu/"

    def test_a_front_page_has_no_front_page_of_its_own(self) -> None:
        """Nothing to offer instead: the URL that 404'd *is* the root."""
        assert site_root("https://example.edu/") is None
        assert site_root("https://example.edu") is None

    def test_a_query_string_alone_still_counts_as_a_page(self) -> None:
        assert site_root("https://example.edu/?course=welding") == "https://example.edu/"

    def test_the_scheme_is_left_alone(self) -> None:
        """Whether the front page is better over https is answered by asking, not assuming."""
        assert site_root("http://example.edu/programs") == "http://example.edu/"


class TestFrontPageCandidates:
    def test_a_404_earns_a_front_page_check(self) -> None:
        checks = results(checked(PAGE, "not_found"))
        assert front_page_candidates(checks) == [ROOT]

    def test_a_410_earns_one_too(self) -> None:
        assert front_page_candidates(results(checked(PAGE, "gone"))) == [ROOT]

    def test_a_name_that_does_not_resolve_earns_nothing(self) -> None:
        """The host does not exist, so neither does anything under it."""
        assert front_page_candidates(results(checked(PAGE, "dns_failure"))) == []

    def test_a_live_url_earns_nothing(self) -> None:
        assert front_page_candidates(results(checked(PAGE, "ok"))) == []

    def test_a_refusal_earns_nothing(self) -> None:
        """A 403 is not evidence the page is gone, so there is nothing to replace."""
        assert front_page_candidates(results(checked(PAGE, "forbidden"))) == []

    def test_one_host_with_many_dead_pages_is_asked_once(self) -> None:
        checks = results(
            checked("https://example.edu/a", "not_found"),
            checked("https://example.edu/b", "not_found"),
        )
        assert front_page_candidates(checks) == [ROOT]

    def test_a_front_page_already_checked_is_not_asked_again(self) -> None:
        checks = results(checked(PAGE, "not_found"), checked(ROOT, "ok"))
        assert front_page_candidates(checks) == []

    def test_a_dead_front_page_asks_for_nothing_further(self) -> None:
        assert front_page_candidates(results(checked(ROOT, "not_found"))) == []

    def test_a_soft_404_earns_a_front_page_check_like_any_other(self) -> None:
        """A page that says it is not there is a page that is not there, and the provider is
        plainly still answering -- all four soft-404 hosts in the corpus have a live root."""
        assert front_page_candidates(results(checked(PAGE, "soft_not_found"))) == [ROOT]

    def test_an_address_for_sale_earns_nothing(self) -> None:
        """Its front page is the same sales listing. Asking would spend a request on a
        foregone answer, for the same reason a name that does not resolve is not asked."""
        assert front_page_candidates(results(checked(PAGE, "domain_for_sale"))) == []


class TestDecideUnchecked:
    """The first case, and the one the whole design turns on."""

    def test_a_url_nobody_read_is_published_exactly_as_filed(self) -> None:
        decision = decide({}, PAGE)
        assert decision is not None
        assert decision.href == PAGE
        assert decision.linked is True
        assert decision.label == LABEL_PROGRAM_PAGE

    def test_a_url_nobody_read_carries_no_verdict_and_no_date(self) -> None:
        decision = decide({}, PAGE)
        assert decision is not None
        assert decision.verdict is None
        assert decision.reason is None
        assert decision.checked_on is None

    def test_a_url_nobody_read_is_never_annotated(self) -> None:
        """There is nothing to say about a page nobody looked at."""
        decision = decide({}, PAGE)
        assert decision is not None
        assert decision.notice is None
        assert decision.substitution is None

    def test_a_run_that_checked_other_urls_does_not_leak_onto_this_one(self) -> None:
        decision = decide(results(checked("https://other.edu/", "not_found")), PAGE)
        assert decision is not None
        assert decision.verdict is None
        assert decision.linked is True

    def test_a_program_with_no_url_has_no_decision_at_all(self) -> None:
        assert decide({}, None) is None
        assert decide(results(checked(PAGE, "ok")), None) is None


class TestDecideAlive:
    def test_a_working_page_is_linked_unchanged(self) -> None:
        decision = decide(results(checked(PAGE, "ok")), PAGE)
        assert decision is not None
        assert decision.href == PAGE
        assert decision.substitution is None
        assert decision.notice is None
        assert decision.label == LABEL_PROGRAM_PAGE

    def test_a_verified_https_equivalent_is_swapped_in(self) -> None:
        checks = results(checked(INSECURE, "ok", upgrade=PAGE))
        decision = decide(checks, INSECURE)
        assert decision is not None
        assert decision.href == PAGE
        assert decision.substitution == SUBSTITUTION_HTTPS
        # The record's own value is still published beside it.
        assert decision.url == INSECURE

    def test_an_upgrade_is_not_an_annotation(self) -> None:
        """A scheme change is a transport improvement, not a finding about the provider."""
        decision = decide(results(checked(INSECURE, "ok", upgrade=PAGE)), INSECURE)
        assert decision is not None
        assert decision.notice is None

    def test_a_page_that_lands_on_the_site_root_is_relabelled_not_suppressed(self) -> None:
        decision = decide(results(checked(PAGE, "redirected_to_site_root")), PAGE)
        assert decision is not None
        assert decision.linked is True
        assert decision.href == PAGE
        assert decision.label == LABEL_PROVIDER_HOME
        assert decision.notice is None


class TestDecideOffsiteRedirect:
    """A page answered from another domain, and who is at the other end decides everything.

    Until 2026-08-15 this class was published as an ordinary link on the reasoning that a
    catalogue vendor and a domain squatter are indistinguishable mechanically. They are --
    and the consequence was six California program pages offering a reader a link to
    ``giligiacollege.com``, ``eastvalleycollege.com`` and ``hollywoodculturalcollege.com``,
    which serve an Indonesian gambling site, an Indonesian lottery site and an unrelated
    Baltimore charity. Indistinguishable is a reason to withhold, not a reason to publish.
    """

    def test_an_offsite_redirect_nobody_resolved_is_not_linked(self) -> None:
        decision = decide(results(checked(PAGE, "redirected_offsite", final=OFFSITE)), PAGE)
        assert decision is not None
        assert decision.linked is False
        assert decision.href is None
        assert decision.notice == NOTICE_REDIRECT_UNCONFIRMED
        assert decision.redirect == "unresolved"

    def test_the_filed_url_survives_as_text_with_a_date(self) -> None:
        """The federal record's own value is never dropped, and a sentence about it is
        always dated: a reader may want the Internet Archive, and a verdict has a shelf
        life."""
        decision = decide(results(checked(PAGE, "redirected_offsite", final=OFFSITE)), PAGE)
        assert decision is not None
        assert decision.url == PAGE
        assert decision.checked_on == "2026-08-04"

    def test_a_confirmed_rebrand_is_published_exactly_as_it_was_before(self) -> None:
        decision = decide(
            results(checked(PAGE, "redirected_offsite", final=OFFSITE)),
            PAGE,
            redirect=link_review.RedirectVerdict("same_provider", "review", "checked by hand"),
        )
        assert decision is not None
        assert decision.linked is True
        assert decision.href == PAGE
        assert decision.label == LABEL_PROGRAM_PAGE
        assert decision.notice is None
        assert decision.redirect == "same_provider"

    def test_a_confirmed_rebrand_still_gets_its_https_upgrade(self) -> None:
        checks = results(checked(INSECURE, "redirected_offsite", final=OFFSITE, upgrade=PAGE))
        decision = decide(
            checks,
            INSECURE,
            redirect=link_review.RedirectVerdict("same_provider", "feed", "the feed files it"),
        )
        assert decision is not None
        assert decision.href == PAGE
        assert decision.substitution == SUBSTITUTION_HTTPS

    def test_a_reviewed_hijack_publishes_no_link_and_its_own_sentence(self) -> None:
        decision = decide(
            results(checked(PAGE, "redirected_offsite", final=OFFSITE)),
            PAGE,
            redirect=link_review.RedirectVerdict("unrelated", "review", "somebody else's site"),
        )
        assert decision is not None
        assert decision.linked is False
        assert decision.href is None
        assert decision.notice == NOTICE_REDIRECT_UNRELATED
        assert decision.notice != NOTICE_REDIRECT_UNCONFIRMED

    def test_an_address_advertised_for_sale_reuses_the_sentence_written_for_that(self) -> None:
        """A redirect to a marketplace listing is the same situation the title detector
        already has wording for, and one situation deserves one sentence."""
        decision = decide(
            results(checked(PAGE, "redirected_offsite", final=OFFSITE)),
            PAGE,
            redirect=link_review.RedirectVerdict("for_sale", "review", "a listing for it"),
        )
        assert decision is not None
        assert decision.linked is False
        assert decision.notice == NOTICE_FOR_SALE

    def test_only_a_confirmation_produces_a_link(self) -> None:
        """The property the whole class turns on, stated over every resolution there is."""
        for resolution in ("unresolved", "unrelated", "for_sale"):
            decision = decide(
                results(checked(PAGE, "redirected_offsite", final=OFFSITE)),
                PAGE,
                redirect=link_review.RedirectVerdict(resolution, "review", "why"),  # type: ignore[arg-type]
            )
            assert decision is not None
            assert decision.linked is False, resolution
            assert decision.href is None, resolution

    def test_the_reader_is_never_told_the_provider_is_gone(self) -> None:
        """``page_unreachable`` would be false here twice over: the address answered, and
        what answered is not evidence about a school."""
        for resolution in ("unresolved", "unrelated"):
            decision = decide(
                results(checked(PAGE, "redirected_offsite", final=OFFSITE)),
                PAGE,
                redirect=link_review.RedirectVerdict(resolution, "review", "why"),  # type: ignore[arg-type]
            )
            assert decision is not None
            assert decision.notice != NOTICE_UNREACHABLE

    def test_nothing_else_carries_a_redirect_resolution(self) -> None:
        """``redirect`` is null for every link that never left the site it named, so a
        consumer cannot read one class's field as another's."""
        for reason in ("ok", "redirected_to_site_root", "not_found", "forbidden"):
            decision = decide(results(checked(PAGE, reason)), PAGE)  # type: ignore[arg-type]
            assert decision is not None
            assert decision.redirect is None, reason
        assert decide({}, PAGE).redirect is None  # type: ignore[union-attr]


class TestDecideIndeterminate:
    """113 URLs on 163 pages that could not be judged. Nothing may happen to them."""

    @pytest.mark.parametrize(
        "reason",
        ["forbidden", "method_not_allowed", "rate_limited", "server_error", "timeout"],
    )
    def test_a_page_we_could_not_judge_renders_as_it_always_has(self, reason: Reason) -> None:
        decision = decide(results(checked(PAGE, reason)), PAGE)
        assert decision is not None
        assert decision.href == PAGE
        assert decision.linked is True
        assert decision.label == LABEL_PROGRAM_PAGE

    def test_a_page_we_could_not_judge_is_never_annotated(self) -> None:
        """Printing "we could not reach this" next to a working institution's WIOA figures
        on the strength of a bot filter is a false claim about a named organisation."""
        decision = decide(results(checked(PAGE, "forbidden")), PAGE)
        assert decision is not None
        assert decision.notice is None

    def test_a_bad_certificate_still_publishes_the_link(self) -> None:
        decision = decide(results(checked(PAGE, "tls_failure")), PAGE)
        assert decision is not None
        assert decision.linked is True
        assert decision.notice is None

    def test_the_verdict_is_still_recorded_even_though_nothing_changes(self) -> None:
        """The interface must not act on it; the dataset should still say what was seen."""
        decision = decide(results(checked(PAGE, "forbidden")), PAGE)
        assert decision is not None
        assert decision.verdict == "indeterminate"
        assert decision.reason == "forbidden"
        assert decision.checked_on == "2026-08-04"

    def test_not_even_the_scheme_changes(self) -> None:
        """An https equivalent is earned by an answer, and this URL gave us none to reason
        from -- so there is nothing to swap and no swap is made."""
        checks = results(checked(INSECURE, "forbidden", upgrade=PAGE))
        decision = decide(checks, INSECURE)
        assert decision is not None
        assert decision.href == INSECURE
        assert decision.substitution is None


class TestDecideDead:
    def test_a_name_that_does_not_resolve_publishes_no_link(self) -> None:
        decision = decide(results(checked(PAGE, "dns_failure")), PAGE)
        assert decision is not None
        assert decision.href is None
        assert decision.linked is False

    def test_a_suppressed_link_still_publishes_the_url_and_the_date(self) -> None:
        """Suppression alone would hide that the federal record contains a URL at all, and a
        reader may want to try the Internet Archive with it."""
        decision = decide(results(checked(PAGE, "dns_failure")), PAGE)
        assert decision is not None
        assert decision.url == PAGE
        assert decision.notice == NOTICE_UNREACHABLE
        assert decision.checked_on == "2026-08-04"

    def test_a_dead_name_is_never_sent_to_a_front_page(self) -> None:
        """Even with a live root on file: the host in the record does not exist, and
        inferring a provider's successor is a judgement about identity, not a measurement."""
        checks = results(checked(PAGE, "dns_failure"), checked(ROOT, "ok"))
        decision = decide(checks, PAGE)
        assert decision is not None
        assert decision.href is None
        assert decision.substitution is None

    def test_a_404_with_a_working_front_page_goes_to_the_front_page(self) -> None:
        checks = results(checked(PAGE, "not_found"), checked(ROOT, "ok"))
        decision = decide(checks, PAGE)
        assert decision is not None
        assert decision.href == ROOT
        assert decision.linked is True
        assert decision.substitution == SUBSTITUTION_FRONT_PAGE

    def test_a_substituted_link_says_so_rather_than_pretending(self) -> None:
        """The reader is being sent somewhere other than where the record pointed. Saying
        nothing would be a quieter lie, not an absence of one."""
        checks = results(checked(PAGE, "not_found"), checked(ROOT, "ok"))
        decision = decide(checks, PAGE)
        assert decision is not None
        assert decision.label == LABEL_PROVIDER_HOME
        assert decision.notice == NOTICE_UNREACHABLE
        assert decision.url == PAGE

    def test_a_front_page_upgrade_is_carried_through(self) -> None:
        checks = results(
            checked("http://example.edu/p", "not_found"),
            checked("http://example.edu/", "ok", upgrade=ROOT),
        )
        decision = decide(checks, "http://example.edu/p")
        assert decision is not None
        assert decision.href == ROOT

    def test_a_site_that_404s_its_own_front_page_offers_nothing(self) -> None:
        checks = results(checked(PAGE, "not_found"), checked(ROOT, "not_found"))
        decision = decide(checks, PAGE)
        assert decision is not None
        assert decision.href is None
        assert decision.linked is False

    def test_a_front_page_that_only_refused_us_is_not_a_destination(self) -> None:
        """Weaker evidence both ways: the 404 is less trustworthy and the root is unproven.
        Neither justifies sending a reader somewhere."""
        checks = results(checked(PAGE, "not_found"), checked(ROOT, "forbidden"))
        decision = decide(checks, PAGE)
        assert decision is not None
        assert decision.href is None

    def test_a_front_page_that_lands_on_another_domain_is_not_offered(self) -> None:
        """Measured on the real corpus, that is as likely to be a domain-sale page."""
        checks = results(checked(PAGE, "not_found"), checked(ROOT, "redirected_offsite"))
        decision = decide(checks, PAGE)
        assert decision is not None
        assert decision.href is None

    def test_a_front_page_nobody_checked_is_not_assumed_to_work(self) -> None:
        decision = decide(results(checked(PAGE, "not_found")), PAGE)
        assert decision is not None
        assert decision.href is None
        assert decision.substitution is None

    def test_a_dead_root_has_nothing_to_fall_back_to(self) -> None:
        decision = decide(results(checked(ROOT, "not_found")), ROOT)
        assert decision is not None
        assert decision.href is None
        assert decision.label == LABEL_PROGRAM_PAGE

    def test_the_wording_hook_is_an_observation_not_a_diagnosis(self) -> None:
        """Every notice this module emits is about our own reading, and none of them travels
        without the date that gives it a shelf life."""
        for reason in ("not_found", "dns_failure", "soft_not_found", "domain_for_sale"):
            decision = decide(results(checked(PAGE, reason)), PAGE)
            assert decision is not None
            assert decision.notice is not None
            assert decision.checked_on is not None

    def test_a_soft_404_is_treated_exactly_like_the_404_it_is(self) -> None:
        """The reader's situation is identical -- the filed page is not there and the school
        is -- so the treatment is too, down to the wording."""
        checks = results(checked(PAGE, "soft_not_found"), checked(ROOT, "ok"))
        decision = decide(checks, PAGE)
        assert decision is not None
        assert decision.href == ROOT
        assert decision.label == LABEL_PROVIDER_HOME
        assert decision.substitution == SUBSTITUTION_FRONT_PAGE
        assert decision.notice == NOTICE_UNREACHABLE

    def test_an_address_for_sale_publishes_no_link(self) -> None:
        checks = results(checked(PAGE, "domain_for_sale"))
        decision = decide(checks, PAGE)
        assert decision is not None
        assert decision.href is None
        assert decision.linked is False
        assert decision.url == PAGE, "the record's own value survives, for the archive"

    def test_an_address_for_sale_gets_its_own_sentence(self) -> None:
        """ "We could not reach this page" would be false -- we reached it perfectly well,
        and an advertisement answered -- and it would send a reader back to retry an address
        that is never coming back. What they need to know is to look the school up by name.
        """
        decision = decide(results(checked(PAGE, "domain_for_sale")), PAGE)
        assert decision is not None
        assert decision.notice == NOTICE_FOR_SALE

    def test_an_address_for_sale_is_never_sent_to_its_own_front_page(self) -> None:
        """Even with a root on file that answered: whatever is there is the same listing,
        and the corpus's parking hosts serve it at every path."""
        checks = results(checked(PAGE, "domain_for_sale"), checked(ROOT, "ok"))
        decision = decide(checks, PAGE)
        assert decision is not None
        assert decision.href is None
        assert decision.substitution is None


class TestFrontPageFor:
    def test_an_unchecked_url_has_no_front_page(self) -> None:
        assert front_page_for({}, PAGE) is None

    def test_a_url_that_is_not_dead_has_no_front_page(self) -> None:
        checks = results(checked(PAGE, "forbidden"), checked(ROOT, "ok"))
        assert front_page_for(checks, PAGE) is None

    def test_no_url_at_all_has_no_front_page(self) -> None:
        assert front_page_for(results(checked(PAGE, "not_found")), None) is None


class TestDecisionSerialisation:
    def test_every_field_the_interface_needs_is_published(self) -> None:
        decision = decide(results(checked(PAGE, "not_found"), checked(ROOT, "ok")), PAGE)
        assert decision is not None
        assert decision.as_dict() == {
            "url": PAGE,
            "href": ROOT,
            "linked": True,
            "label": LABEL_PROVIDER_HOME,
            "verdict": "dead",
            "reason": "not_found",
            "checked_on": "2026-08-04",
            "notice": NOTICE_UNREACHABLE,
            "substitution": SUBSTITUTION_FRONT_PAGE,
            "redirect": None,
        }

    def test_an_offsite_decision_publishes_what_was_established_about_it(self) -> None:
        """The field a packaging gate reads. Without it, a dataset built before any redirect
        was reviewed is byte-indistinguishable from one where every redirect was."""
        decision = decide(
            results(checked(PAGE, "redirected_offsite", final=OFFSITE)),
            PAGE,
            redirect=link_review.RedirectVerdict("unrelated", "review", "somebody else's"),
        )
        assert decision is not None
        assert decision.as_dict()["redirect"] == "unrelated"
        assert decision.as_dict()["linked"] is False

    def test_an_unchecked_decision_publishes_nulls_not_omissions(self) -> None:
        """A consumer must be able to tell "checked, nothing to say" from "never looked",
        which it cannot do if the keys are missing."""
        decision = decide({}, PAGE)
        assert decision is not None
        assert decision.as_dict() == {
            "url": PAGE,
            "href": PAGE,
            "linked": True,
            "label": LABEL_PROGRAM_PAGE,
            "verdict": None,
            "reason": None,
            "checked_on": None,
            "notice": None,
            "substitution": None,
            "redirect": None,
        }


class TestChecksDocument:
    def test_a_run_survives_a_round_trip(self) -> None:
        checks = results(
            checked(PAGE, "not_found"),
            checked(ROOT, "ok"),
            checked(INSECURE, "ok", upgrade=PAGE),
        )
        restored = checks_from_document(json.loads(json.dumps(checks_document(checks))))
        assert restored == checks

    def test_a_decision_is_the_same_either_side_of_the_file(self) -> None:
        checks = results(checked(PAGE, "not_found"), checked(ROOT, "ok"))
        restored = checks_from_document(checks_document(checks))
        assert decide(restored, PAGE) == decide(checks, PAGE)

    def test_an_empty_run_is_a_valid_document(self) -> None:
        assert checks_from_document(checks_document({})) == {}

    def test_a_document_from_another_shape_is_refused_rather_than_guessed_at(self) -> None:
        document = checks_document(results(checked(PAGE, "ok")))
        document["version"] = DOCUMENT_VERSION + 1
        with pytest.raises(ValueError, match="version"):
            checks_from_document(document)

    def test_a_versionless_document_is_refused(self) -> None:
        with pytest.raises(ValueError, match="version"):
            checks_from_document({"checks": []})

    def test_an_unknown_reason_is_refused_rather_than_trusted(self) -> None:
        """Unlike the cache, which shrugs: a report that cannot be read is an operator
        pointing a build at the wrong file, and reading it as "nothing was checked" would
        republish links this project had already established were broken."""
        document = checks_document(results(checked(PAGE, "not_found")))
        document["checks"][0]["reason"] = "vanished"
        with pytest.raises(ValueError, match="reason"):
            checks_from_document(document)

    def test_the_document_records_when_the_run_finished(self) -> None:
        document = checks_document({}, checked_at=NOW)
        assert document["checked_at"] == NOW.isoformat()

    def test_the_document_records_which_classifier_reached_its_verdicts(self) -> None:
        assert checks_document({})["classifier_version"] == CLASSIFIER_VERSION


class TestAReportOlderThanTheClassifier:
    """A report is still read; it is no longer read silently.

    The 2026-08-05 title detector spent ten days judging nothing, because the report every
    build read had been produced before it existed and nothing anywhere compared the two.
    """

    def test_an_older_verdict_is_named(self) -> None:
        checks = results(
            replace(checked(PAGE, "ok"), classifier_version=CLASSIFIER_VERSION - 1),
            checked(ROOT, "ok"),
        )
        assert link_check.unasked_by_the_current_classifier(checks) == [PAGE]

    def test_a_current_report_names_nobody(self) -> None:
        checks = results(checked(PAGE, "ok"), checked(ROOT, "ok"))
        assert link_check.unasked_by_the_current_classifier(checks) == []

    def test_an_older_verdict_is_still_a_verdict(self) -> None:
        """It is not discarded. Withholding every link over a version number would hide
        hundreds of working schools to fix a problem that is about ten of them."""
        checks = results(replace(checked(PAGE, "not_found"), classifier_version=1))
        decision = decide(checks, PAGE)
        assert decision is not None
        assert decision.verdict == "dead"
        assert decision.linked is False

    def test_a_report_from_an_older_classifier_still_loads(self) -> None:
        document = checks_document(results(checked(PAGE, "ok")))
        document["checks"][0]["classifier_version"] = 1
        restored = checks_from_document(document)
        assert restored[PAGE].classifier_version == 1
