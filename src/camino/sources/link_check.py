"""Check whether the provider website on a program record actually goes anywhere.

Every program in source D1 may carry a ``field_program_url``, which the site renders as
"Provider's website". That link is an assertion, and the feed does not maintain it: schools
close, adult-education domains lapse, and a catalogue page outlives its URL by years. When
the assertion is wrong the reader is sent nowhere useful by a page that promised otherwise.

This module answers one question per URL, and it answers it in three values, not two:

``alive``
    Something answered and there is a page there.
``dead``
    The host does not resolve, refuses a connection, or the server says the page is gone.
``indeterminate``
    We got *an* answer and it does not settle the question. A 403 or a 405 usually means the
    host dislikes automated requests, not that the page vanished; a timeout means slow, not
    absent; a persistent 5xx means broken, which is not the same claim as gone.

The third value is the whole point. Wrongly marking a real provider's live website as dead
is its own harm -- it hides a school from someone trying to enrol -- so anything short of
evidence lands in ``indeterminate`` and the caller must decide what to do with a URL that
could not be judged.

**Absence is not a verdict.** There is deliberately no ``Verdict`` member meaning "not
checked". A URL nobody checked simply has no :class:`LinkCheck`, and :func:`verdict_for` and
:func:`is_dead` return ``None`` for it rather than a default. An unchecked URL is not a dead
URL, and the types are not allowed to blur that.

What this cannot do: a soft 404 -- a "page not found" served with HTTP 200 -- is
indistinguishable from a real page without fetching and interpreting the body, so it is
reported ``alive`` here. One cheap relative of it *is* caught: a request for a deep path
that ends up redirected to the site root almost always means the specific page is gone even
though the provider is fine, and that is flagged as ``redirected_to_site_root``.

Manners, since every host here is a small college or an adult school rather than a CDN:
HEAD before GET, GET streamed so a provider is not billed for a body nobody reads, one
request at a time per site with a pause between them, bounded concurrency across sites,
retries only for what is plausibly transient, ``Retry-After`` honoured, and the honest
:data:`~camino.sources.dol_etp.USER_AGENT` this project uses everywhere else. No browser
impersonation: a host that wants to refuse this client is entitled to recognise it and do so,
which is exactly why a refusal is classified ``indeterminate`` instead of ``dead``.

Results are cached on disk by URL so a rebuild does not re-ask 1,000 providers whether they
still exist.
"""

from __future__ import annotations

import hashlib
import json
import socket
import ssl
import threading
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final, Literal

import httpx

from camino.sources.dol_etp import (
    BACKOFF_CAP_SECONDS,
    BACKOFF_INITIAL_SECONDS,
    BACKOFF_MULTIPLIER,
    RETRY_AFTER_CAP_SECONDS,
    RETRYABLE_STATUS,
    USER_AGENT,
    _retry_after_seconds,
)

# ``dol_etp`` declares itself the owner of this package's HTTP manners, so the retry timing
# and the Retry-After parsing are imported rather than restated. Importing the private
# parser is the lesser evil: a second copy of that header's two encodings is a second place
# to get it wrong.

REQUEST_TIMEOUT: Final = 25.0
"""Generous on purpose. A small college on shared hosting is slow, not gone."""

MAX_ATTEMPTS: Final = 3
"""Tries per method. Worst case for one URL is 3 HEADs then 3 GETs, spread over a few
seconds of backoff -- less than a reader hammering reload on a broken page."""

HTTPS_PROBE_ATTEMPTS: Final = 1
"""The https probe answers "is there a free upgrade?", not "is this record's link good", so
it gets one try. Missing an upgrade costs nothing; a second round of traffic does."""

MAX_WORKERS: Final = 8
"""Sites checked at once. Never two requests to the same site concurrently -- see
:func:`check_urls`, which hands each site to one worker as a unit."""

PAUSE_BETWEEN_SAME_HOST: Final = 1.0
"""Seconds between consecutive requests to one site, including HEAD then GET."""

REQUEST_HEADERS: Final[Mapping[str, str]] = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
}

Verdict = Literal["alive", "dead", "indeterminate"]
"""What the check established. Note what is missing: there is no "unchecked"."""

Reason = Literal[
    # alive
    "ok",
    "redirected_to_site_root",
    "redirected_offsite",
    # dead
    "dns_failure",
    "connection_failed",
    "not_found",
    "gone",
    # indeterminate
    "forbidden",
    "method_not_allowed",
    "rate_limited",
    "server_error",
    "other_client_error",
    "timeout",
    "tls_failure",
    "protocol_error",
    "too_many_redirects",
]
"""Why, in enough detail to argue with."""

VERDICT_BY_REASON: Final[Mapping[Reason, Verdict]] = {
    "ok": "alive",
    "redirected_to_site_root": "alive",
    "redirected_offsite": "alive",
    # Dead. Only two kinds of evidence qualify: the name does not exist or the connection is
    # refused, and the server itself says the page is not there. ``connection_failed`` is the
    # weaker of the two -- a firewall that drops this client would look identical -- so it
    # stays a separate reason that a caller can choose to treat differently.
    "dns_failure": "dead",
    "connection_failed": "dead",
    "not_found": "dead",
    "gone": "dead",
    # Indeterminate. Every one of these is a host that is plainly *there*.
    "forbidden": "indeterminate",
    "method_not_allowed": "indeterminate",
    "rate_limited": "indeterminate",
    "server_error": "indeterminate",
    "other_client_error": "indeterminate",
    "timeout": "indeterminate",
    "tls_failure": "indeterminate",
    "protocol_error": "indeterminate",
    "too_many_redirects": "indeterminate",
}

RETRYABLE_REASONS: Final[frozenset[str]] = frozenset(
    {"timeout", "connection_failed", "dns_failure", "protocol_error"}
)
"""Transport failures worth one more look. A resolver hiccup and a genuinely lapsed domain
are the same exception, and only time apart tells them apart, so DNS is retried too.
A TLS rejection and a redirect loop are deterministic and are not."""

CACHE_TTL: Final[Mapping[Verdict, timedelta]] = {
    "alive": timedelta(days=30),
    "dead": timedelta(days=7),
    "indeterminate": timedelta(days=1),
}
"""How long a verdict may be reused. The asymmetry is deliberate: acting on a stale ``dead``
means hiding a provider that has come back, which is worse than re-checking a live site, and
an ``indeterminate`` result is barely worth keeping at all."""

DEFAULT_CACHE_SUBDIR: Final = "link-cache"
"""Conventional name under ``data/raw/`` for :class:`LinkCheckCache`."""


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class LinkCheck:
    """What was established about one URL, and when.

    A ``LinkCheck`` only ever exists for a URL that was actually checked. Constructing one to
    stand for "we did not look" would be exactly the absence-as-value move this codebase
    refuses everywhere else.
    """

    url: str
    verdict: Verdict
    reason: Reason
    status_code: int | None
    """HTTP status of the final response, or ``None`` when no response was ever obtained."""
    final_url: str | None
    """Where the request ended up after redirects, or ``None`` if it never arrived."""
    https_alternative: str | None
    """An ``https`` URL observed to work, when :attr:`url` is ``http``. Never a guess: this
    is only ever a URL that answered."""
    detail: str | None
    checked_at: datetime
    attempts: int
    """HTTP requests spent on this URL, so politeness is auditable after the fact."""

    @property
    def is_upgradeable(self) -> bool:
        """True when this ``http`` URL has a verified ``https`` equivalent."""
        return self.https_alternative is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "verdict": self.verdict,
            "reason": self.reason,
            "status_code": self.status_code,
            "final_url": self.final_url,
            "https_alternative": self.https_alternative,
            "detail": self.detail,
            "checked_at": self.checked_at.isoformat(),
            "attempts": self.attempts,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> LinkCheck:
        """Rebuild from :meth:`as_dict`. Raises on anything it does not recognise."""
        reason = payload["reason"]
        if reason not in VERDICT_BY_REASON:
            raise ValueError(f"unknown reason {reason!r}")
        return cls(
            url=str(payload["url"]),
            verdict=VERDICT_BY_REASON[reason],
            reason=reason,
            status_code=payload["status_code"],
            final_url=payload["final_url"],
            https_alternative=payload["https_alternative"],
            detail=payload["detail"],
            checked_at=datetime.fromisoformat(payload["checked_at"]),
            attempts=int(payload["attempts"]),
        )


# --------------------------------------------------------------------------------------
# Reading a URL
# --------------------------------------------------------------------------------------


def _site_key(url: str | httpx.URL) -> str:
    """The site a URL belongs to, for pacing and for same-site comparisons."""
    host = (httpx.URL(url).host or "").lower()
    return host.removeprefix("www.")


def _same_site(left: str | httpx.URL, right: str | httpx.URL) -> bool:
    """True when two URLs are the same site or one is a subdomain of the other."""
    a, b = _site_key(left), _site_key(right)
    if not a or not b:
        return False
    return a == b or a.endswith(f".{b}") or b.endswith(f".{a}")


def _has_path(url: httpx.URL) -> bool:
    return bool(url.path.strip("/")) or bool(url.query)


def _host_resolves(host: str | None) -> bool:
    """Whether DNS knows this name at all.

    Used to split a connection failure into "the domain is gone" and "the domain is there and
    would not talk to us", which are different findings and deserve different reasons.
    """
    if not host:
        return False
    try:
        socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    except OSError:
        # Our own networking is unhappy. Not the provider's fault; do not blame them.
        return True
    return True


def _caused_by_ssl(exc: BaseException) -> bool:
    seen: BaseException | None = exc
    while seen is not None:
        if isinstance(seen, ssl.SSLError):
            return True
        seen = seen.__cause__ or seen.__context__
    return False


def _transport_reason(exc: httpx.HTTPError, url: str) -> Reason:
    """Classify a request that never produced a response."""
    if isinstance(exc, httpx.TooManyRedirects):
        return "too_many_redirects"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if _caused_by_ssl(exc):
        return "tls_failure"
    if isinstance(exc, httpx.RemoteProtocolError):
        # The host accepted a connection and then mishandled it. Present, not absent.
        return "protocol_error"
    if isinstance(exc, httpx.ConnectError) and not _host_resolves(httpx.URL(url).host):
        return "dns_failure"
    return "connection_failed"


def _reason_for_status(status: int) -> Reason:
    """Classify a response the server chose to send."""
    if status == httpx.codes.NOT_FOUND:
        return "not_found"
    if status == httpx.codes.GONE:
        return "gone"
    if status == httpx.codes.FORBIDDEN:
        return "forbidden"
    if status == httpx.codes.METHOD_NOT_ALLOWED:
        return "method_not_allowed"
    if status == httpx.codes.TOO_MANY_REQUESTS:
        return "rate_limited"
    if status >= httpx.codes.INTERNAL_SERVER_ERROR:
        return "server_error"
    return "other_client_error"


def _reason_for_success(requested: httpx.URL, final: httpx.URL) -> Reason:
    """Classify a 2xx, which is not automatically an unqualified "ok"."""
    if not _same_site(requested, final):
        return "redirected_offsite"
    if _has_path(requested) and not _has_path(final):
        # A named page that now lands on the front door. The provider is alive; the page
        # this record points at is almost certainly not.
        return "redirected_to_site_root"
    return "ok"


@dataclass(frozen=True)
class _Outcome:
    """One request sequence, reduced to plain data so no live response escapes."""

    status_code: int | None
    final_url: str | None
    transport_reason: Reason | None
    detail: str | None
    attempts: int

    @property
    def succeeded(self) -> bool:
        return self.status_code is not None and 200 <= self.status_code < 300


def _backoff_seconds(attempt: int) -> float:
    return min(BACKOFF_INITIAL_SECONDS * BACKOFF_MULTIPLIER ** (attempt - 1), BACKOFF_CAP_SECONDS)


def _retry_delay(response: httpx.Response, attempt: int) -> float | None:
    """Seconds to wait before retrying, or ``None`` to stop and report what we have.

    A host asking for longer than :data:`RETRY_AFTER_CAP_SECONDS` is asking to be left alone,
    and the honest answer to that is "we do not know", not "we waited it out".
    """
    requested = _retry_after_seconds(response)
    if requested is None:
        return _backoff_seconds(attempt)
    return None if requested > RETRY_AFTER_CAP_SECONDS else requested


def _read_status(
    client: httpx.Client, method: str, url: str, attempt: int
) -> tuple[_Outcome, float | None]:
    """One request, reduced to an outcome plus how long to wait before retrying it.

    The response is streamed and closed without its body being read: this only needs the
    status line and the final URL, and a provider should not pay to serve a page nobody
    looks at. ``Retry-After`` is read here, while the response is still in scope.
    """
    with client.stream(method, url, headers=REQUEST_HEADERS, follow_redirects=True) as response:
        status = response.status_code
        outcome = _Outcome(status, str(response.url), None, None, attempt)
        if status not in RETRYABLE_STATUS:
            return outcome, None
        wait = _retry_delay(response, attempt)
    if wait is None:
        return replace(outcome, detail="server asked for a longer wait than we will hold"), None
    return outcome, wait


def _request(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    max_attempts: int,
    sleep: Callable[[float], None],
) -> _Outcome:
    """Issue ``method`` against ``url``, retrying only what is plausibly transient."""
    reason: Reason = "connection_failed"
    detail: str | None = None
    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        try:
            outcome, wait = _read_status(client, method, url, attempt)
        except httpx.HTTPError as exc:
            reason = _transport_reason(exc, url)
            detail = f"{type(exc).__name__}: {exc}"[:200]
            if reason not in RETRYABLE_REASONS or attempt == max_attempts:
                break
            sleep(_backoff_seconds(attempt))
        else:
            if wait is None or attempt == max_attempts:
                return outcome
            sleep(wait)
    return _Outcome(None, None, reason, detail, attempt)


def _to_check(url: str, outcome: _Outcome, *, now: datetime, attempts_before: int = 0) -> LinkCheck:
    """Turn a finished request sequence into a verdict."""
    attempts = outcome.attempts + attempts_before
    if outcome.status_code is None:
        reason = outcome.transport_reason or "connection_failed"
        return LinkCheck(
            url=url,
            verdict=VERDICT_BY_REASON[reason],
            reason=reason,
            status_code=None,
            final_url=None,
            https_alternative=None,
            detail=outcome.detail,
            checked_at=now,
            attempts=attempts,
        )
    final = httpx.URL(outcome.final_url or url)
    reason = (
        _reason_for_success(httpx.URL(url), final)
        if outcome.succeeded
        else _reason_for_status(outcome.status_code)
    )
    return LinkCheck(
        url=url,
        verdict=VERDICT_BY_REASON[reason],
        reason=reason,
        status_code=outcome.status_code,
        final_url=str(final),
        https_alternative=None,
        detail=outcome.detail,
        checked_at=now,
        attempts=attempts,
    )


def _probe(
    url: str,
    *,
    client: httpx.Client,
    max_attempts: int,
    sleep: Callable[[float], None],
    pause: float,
    now: datetime,
) -> LinkCheck:
    """Read one URL: HEAD first, then GET for a second opinion on anything else.

    HEAD is the method servers implement worst -- plenty of hosts answer it 403, 405 or even
    404 for pages that GET perfectly well. Since a wrong "dead" is the expensive mistake
    here, nothing negative is believed until GET has said the same thing.
    """
    head = _request(client, "HEAD", url, max_attempts=max_attempts, sleep=sleep)
    if head.succeeded or head.transport_reason == "dns_failure":
        # A name that does not resolve will not resolve for GET either, and asking again
        # would be noise.
        return _to_check(url, head, now=now)
    sleep(pause)
    body = _request(client, "GET", url, max_attempts=max_attempts, sleep=sleep)
    return _to_check(url, body, now=now, attempts_before=head.attempts)


# --------------------------------------------------------------------------------------
# http -> https
# --------------------------------------------------------------------------------------


def https_variant(url: str) -> str | None:
    """The same URL over https, or ``None`` if it is not an http URL."""
    parsed = httpx.URL(url)
    if parsed.scheme != "http":
        return None
    return str(parsed.copy_with(scheme="https"))


def _upgrade(
    check: LinkCheck,
    *,
    client: httpx.Client,
    max_attempts: int,
    sleep: Callable[[float], None],
    pause: float,
    now: datetime,
) -> LinkCheck:
    """Attach a verified https equivalent to an http URL, when one exists.

    Two ways to earn it, and both require having seen the https URL answer. Either the http
    URL already redirected to https on the same site, which proves it without another
    request, or the https variant is asked directly.
    """
    candidate = https_variant(check.url)
    if candidate is None:
        return check
    if (
        check.verdict == "alive"
        and check.final_url is not None
        and httpx.URL(check.final_url).scheme == "https"
        and _same_site(check.url, check.final_url)
    ):
        return replace(check, https_alternative=check.final_url)
    if check.reason == "dns_failure":
        # The name does not exist. It does not exist over TLS either.
        return check
    sleep(pause)
    probed = _probe(
        candidate,
        client=client,
        max_attempts=min(max_attempts, HTTPS_PROBE_ATTEMPTS),
        sleep=sleep,
        pause=pause,
        now=now,
    )
    # Only a working answer *on the provider's own site* is an upgrade. An https URL that
    # lands somewhere else entirely is a different destination, not a safer one.
    offer = probed.verdict == "alive" and _same_site(check.url, probed.final_url or candidate)
    alternative = (probed.final_url or candidate) if offer else None
    return replace(check, https_alternative=alternative, attempts=check.attempts + probed.attempts)


# --------------------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------------------


class LinkCheckCache:
    """Verdicts kept on disk, keyed by URL, so a rebuild does not re-ask every provider.

    One file per URL rather than one file for all of them: the checker runs several sites at
    once, and independent files mean two workers never contend for the same write and a run
    interrupted halfway keeps everything it had already learned.

    A ``directory`` of ``None`` disables caching entirely, which is what tests and one-off
    runs want.
    """

    def __init__(
        self,
        directory: Path | None,
        *,
        ttl: Mapping[Verdict, timedelta] = CACHE_TTL,
        now: Callable[[], datetime] = _utcnow,
    ) -> None:
        self.directory = directory
        self._ttl = dict(ttl)
        self._now = now
        self._lock = threading.Lock()

    def path_for(self, url: str) -> Path | None:
        if self.directory is None:
            return None
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.directory / f"{digest}.json"

    def get(self, url: str) -> LinkCheck | None:
        """A usable cached verdict, or ``None`` -- which means "ask", never "dead"."""
        path = self.path_for(url)
        if path is None or not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            check = LinkCheck.from_dict(payload)
        except (OSError, ValueError, KeyError, TypeError):
            # A cache is a convenience. An unreadable one means re-check, not fail.
            return None
        if check.url != url:
            return None
        age = self._now() - check.checked_at
        return None if age > self._ttl.get(check.verdict, timedelta(0)) else check

    def put(self, check: LinkCheck) -> None:
        path = self.path_for(check.url)
        if path is None:
            return
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(check.as_dict(), indent=2), encoding="utf-8")


# --------------------------------------------------------------------------------------
# Public interface
# --------------------------------------------------------------------------------------


def build_client(
    timeout: float = REQUEST_TIMEOUT, *, max_workers: int = MAX_WORKERS
) -> httpx.Client:
    """A client that identifies itself honestly and holds no more sockets than it needs."""
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers=dict(REQUEST_HEADERS),
        limits=httpx.Limits(max_connections=max_workers, max_keepalive_connections=max_workers),
    )


def check_url(
    url: str,
    *,
    client: httpx.Client,
    cache: LinkCheckCache | None = None,
    max_attempts: int = MAX_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
    pause: float = PAUSE_BETWEEN_SAME_HOST,
    now: Callable[[], datetime] = _utcnow,
    probe_https: bool = True,
) -> LinkCheck:
    """Establish what, if anything, is at ``url``.

    Raises ``ValueError`` for anything that is not an absolute http(s) URL. Callers get their
    URLs from :func:`camino.sources.dol_etp.clean_url`, which already refuses everything
    else; a malformed string is a caller bug, not a dead link, and must not be recorded as
    one.
    """
    parsed = httpx.URL(url)
    if parsed.scheme not in ("http", "https") or not parsed.host:
        raise ValueError(f"not an absolute http(s) URL: {url!r}")

    cached = cache.get(url) if cache is not None else None
    if cached is not None:
        return cached

    moment = now()
    check = _probe(
        url, client=client, max_attempts=max_attempts, sleep=sleep, pause=pause, now=moment
    )
    if probe_https:
        check = _upgrade(
            check,
            client=client,
            max_attempts=max_attempts,
            sleep=sleep,
            pause=pause,
            now=moment,
        )
    if cache is not None:
        cache.put(check)
    return check


def check_urls(
    urls: Iterable[str],
    *,
    client: httpx.Client | None = None,
    cache: LinkCheckCache | None = None,
    max_workers: int = MAX_WORKERS,
    max_attempts: int = MAX_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
    pause: float = PAUSE_BETWEEN_SAME_HOST,
    now: Callable[[], datetime] = _utcnow,
    probe_https: bool = True,
    on_result: Callable[[LinkCheck], None] | None = None,
) -> dict[str, LinkCheck]:
    """Check every distinct URL in ``urls``, politely.

    URLs are grouped by site and each site is handed to a single worker as a unit, so the
    concurrency is across providers and never within one: a school with forty programs still
    sees one request at a time, spaced by ``pause``. Workers are capped at ``max_workers``.

    The returned mapping holds an entry only for URLs that were actually read. A URL absent
    from it was not checked, and callers must not read that absence as a verdict.
    """
    distinct = list(dict.fromkeys(urls))
    by_site: dict[str, list[str]] = defaultdict(list)
    for url in distinct:
        by_site[_site_key(url)].append(url)

    results: dict[str, LinkCheck] = {}
    lock = threading.Lock()
    owns_client = client is None
    http = client or build_client(max_workers=max_workers)

    def run_site(site_urls: list[str]) -> None:
        for index, url in enumerate(site_urls):
            if index:
                sleep(pause)
            check = check_url(
                url,
                client=http,
                cache=cache,
                max_attempts=max_attempts,
                sleep=sleep,
                pause=pause,
                now=now,
                probe_https=probe_https,
            )
            with lock:
                results[url] = check
                if on_result is not None:
                    on_result(check)

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            list(pool.map(run_site, by_site.values()))
    finally:
        if owns_client:
            http.close()
    return results


def verdict_for(checks: Mapping[str, LinkCheck], url: str | None) -> Verdict | None:
    """The verdict recorded for ``url``, or ``None`` when it was never checked.

    ``None`` here means "we do not know", and it is the only correct answer for an unchecked
    URL. Defaulting to ``"alive"`` would publish a link nobody vouched for; defaulting to
    ``"dead"`` would hide a provider nobody accused. Callers must handle the third case.
    """
    if url is None:
        return None
    check = checks.get(url)
    return None if check is None else check.verdict


def is_dead(checks: Mapping[str, LinkCheck], url: str | None) -> bool | None:
    """``True``/``False`` when ``url`` was checked, ``None`` when it was not."""
    verdict = verdict_for(checks, url)
    return None if verdict is None else verdict == "dead"


def upgrade_for(checks: Mapping[str, LinkCheck], url: str | None) -> str | None:
    """A verified https equivalent for ``url``, or ``None`` if there is none or it is
    unchecked."""
    if url is None:
        return None
    check = checks.get(url)
    return None if check is None else check.https_alternative


@dataclass(frozen=True)
class LinkCheckSummary:
    """Counts over a set of checks, optionally weighted by how many pages carry each URL."""

    urls_checked: int
    pages_affected: int
    by_verdict: Mapping[Verdict, int]
    by_reason: Mapping[Reason, int]
    pages_by_verdict: Mapping[Verdict, int]
    upgradeable_urls: int
    upgradeable_pages: int


def summarise(
    checks: Mapping[str, LinkCheck],
    *,
    pages_per_url: Mapping[str, int] | None = None,
) -> LinkCheckSummary:
    """Aggregate checks, counting URLs and the pages that depend on them.

    ``pages_per_url`` is how many program pages render each URL; a URL missing from it counts
    once, since a URL that was worth checking is on at least one page.
    """
    weights = pages_per_url or {}
    by_verdict: Counter[Verdict] = Counter()
    by_reason: Counter[Reason] = Counter()
    pages_by_verdict: Counter[Verdict] = Counter()
    upgradeable_urls = 0
    upgradeable_pages = 0
    total_pages = 0
    for url, check in checks.items():
        pages = weights.get(url, 1)
        total_pages += pages
        by_verdict[check.verdict] += 1
        by_reason[check.reason] += 1
        pages_by_verdict[check.verdict] += pages
        if check.is_upgradeable:
            upgradeable_urls += 1
            upgradeable_pages += pages
    return LinkCheckSummary(
        urls_checked=len(checks),
        pages_affected=total_pages,
        by_verdict=dict(by_verdict),
        by_reason=dict(by_reason),
        pages_by_verdict=dict(pages_by_verdict),
        upgradeable_urls=upgradeable_urls,
        upgradeable_pages=upgradeable_pages,
    )
