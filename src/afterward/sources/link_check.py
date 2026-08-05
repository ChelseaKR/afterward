"""Check whether the provider website on a program record actually goes anywhere.

Every program in source D1 may carry a ``field_program_url``, which the site renders as
"Provider's website". That link is an assertion, and the feed does not maintain it: schools
close, adult-education domains lapse, and a catalogue page outlives its URL by years. When
the assertion is wrong the reader is sent nowhere useful by a page that promised otherwise.

This module answers one question per URL, and it answers it in three values, not two:

``alive``
    Something answered and there is a page there.
``dead``
    DNS does not know the host at all, or the server itself says the page is not there.
``indeterminate``
    Something happened and it does not settle the question. A 403 or a 405 usually means the
    host dislikes automated requests, not that the page vanished; a timeout means slow, not
    absent; a persistent 5xx means broken, which is not the same claim as gone; and a failure
    to connect to a name that *does* resolve may just as easily be this end of the wire.

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
:data:`~afterward.sources.dol_etp.USER_AGENT` this project uses everywhere else. No browser
impersonation: a host that wants to refuse this client is entitled to recognise it and do so,
which is exactly why a refusal is classified ``indeterminate`` instead of ``dead``.

Results are cached on disk by URL so a rebuild does not re-ask 1,000 providers whether they
still exist.

Reading a URL is only half of it. :func:`decide` turns one check into the decision an
interface needs -- link this, link that instead, or link nothing and say why -- so that the
rule lives in one tested place instead of being reinvented by whatever renders the page.
Its first case is the unchecked one, and it reproduces exactly what was published before any
of this existed.
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

from afterward.sources.dol_etp import (
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
    # Dead. Two kinds of evidence qualify, and only two: the name does not exist anywhere in
    # DNS, or the server itself states the page is not there.
    "dns_failure": "dead",
    "not_found": "dead",
    "gone": "dead",
    # Indeterminate. Every one of these is a host that is plainly *there*, or a failure this
    # client cannot prove belongs to the provider rather than to itself.
    "connection_failed": "indeterminate",
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


def _failing_url(exc: httpx.HTTPError, url: str) -> httpx.URL:
    """Where the failure actually happened, which need not be where the request started.

    ``https://www.sanjuan.edu/sunrisetc`` redirects to ``https://adulted.sanjuan.edu``, and it
    is the *second* name that does not resolve. Blaming the first would report a live host as
    refusing connections, so the failing request's own URL wins when the exception carries it.
    """
    try:
        return exc.request.url
    except RuntimeError:
        return httpx.URL(url)


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
    if isinstance(exc, httpx.ConnectError) and not _host_resolves(_failing_url(exc, url).host):
        return "dns_failure"
    # Resolves, would not connect. Deliberately *not* "dead": measured against the real
    # corpus, every URL that landed here turned out to be reachable by other clients on the
    # same machine at the same moment, and the failure was ours. A name that DNS has never
    # heard of is evidence about a provider; a socket that would not open is evidence about
    # a socket.
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
    URLs from :func:`afterward.sources.dol_etp.clean_url`, which already refuses everything
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


# --------------------------------------------------------------------------------------
# The provider's front page
# --------------------------------------------------------------------------------------

FRONT_PAGE_REASONS: Final[frozenset[str]] = frozenset({"not_found", "gone"})
"""The dead reasons for which a front page is worth asking about.

A 404 is the server saying *this page* is not there while plainly still being there itself,
so the provider's own front door is a real alternative destination. ``dns_failure`` is not in
this set: the name does not exist, so neither does anything under it, and there is nothing to
offer instead.
"""

FRONT_PAGE_ACCEPTED_REASONS: Final[frozenset[str]] = frozenset({"ok", "redirected_to_site_root"})
"""Front-page results good enough to send a reader to.

``redirected_offsite`` is excluded on purpose. Measured on the real corpus, a root that lands
on another domain is as likely to be ``hugedomains.com`` as a legitimate rebrand, and no
mechanical rule tells them apart -- so a reader is better served by no link than by one this
project cannot vouch for.
"""


def site_root(url: str) -> str | None:
    """The provider's front page for ``url``, or ``None`` when ``url`` *is* the front page.

    Same scheme as the record's own URL, deliberately: whether the front page is better over
    https is a question :func:`check_url` answers by asking, not one to assume here.
    """
    parsed = httpx.URL(url)
    if not parsed.host or not _has_path(parsed):
        return None
    return str(parsed.copy_with(path="/", query=None, fragment=None))


def front_page_candidates(checks: Mapping[str, LinkCheck]) -> list[str]:
    """Front pages worth checking, given what is already known.

    One entry per distinct root behind a 404 or a 410, minus anything already checked. This
    is the second, much smaller pass of a run: on the August 2026 corpus it is ~100 URLs
    against the first pass's 1,016, and it is what makes a substitution possible rather than
    a suppression.
    """
    roots: dict[str, None] = {}
    for check in checks.values():
        if check.verdict != "dead" or check.reason not in FRONT_PAGE_REASONS:
            continue
        root = site_root(check.url)
        if root is not None and root not in checks:
            roots[root] = None
    return list(roots)


def front_page_for(checks: Mapping[str, LinkCheck], url: str | None) -> str | None:
    """A working front page on the same host as ``url``, or ``None``.

    ``None`` covers every way there might not be one -- unchecked, not dead, dead for a
    reason a front page cannot answer, no front page checked, or a front page that did not
    answer either. None of those is a claim about the provider.
    """
    if url is None:
        return None
    check = checks.get(url)
    if check is None or check.verdict != "dead" or check.reason not in FRONT_PAGE_REASONS:
        return None
    root = site_root(check.url)
    front = None if root is None else checks.get(root)
    if front is None or front.reason not in FRONT_PAGE_ACCEPTED_REASONS:
        return None
    return front.https_alternative or front.url


# --------------------------------------------------------------------------------------
# What to publish
# --------------------------------------------------------------------------------------

LinkLabel = Literal["program_page", "provider_home_page"]
"""What the link reaches, which is not always what the record said it would."""

LinkNotice = Literal["page_unreachable"]
"""What must be said. One value, because there is exactly one thing this module has ever
established that is worth printing beside a link."""

LinkSubstitution = Literal["https_upgrade", "provider_front_page"]
"""Why the published destination differs from the recorded one."""

LABEL_PROGRAM_PAGE: Final[LinkLabel] = "program_page"
"""The link goes where the federal record said it does: the provider's page for this
program."""

LABEL_PROVIDER_HOME: Final[LinkLabel] = "provider_home_page"
"""The link goes to the provider's front door, not to this program. The interface must say
so, because "Provider's website" over a link that reaches a home page implies a page about
the program that is not there."""

SUBSTITUTION_HTTPS: Final[LinkSubstitution] = "https_upgrade"
"""Same page, same site, over TLS. A verified equivalent, never a guessed one."""

SUBSTITUTION_FRONT_PAGE: Final[LinkSubstitution] = "provider_front_page"
"""A different page on the same host, offered because the recorded one is not there."""

NOTICE_UNREACHABLE: Final[LinkNotice] = "page_unreachable"
"""Something must be said about the recorded URL, and it is a statement about *our* reading
of it on a date -- never about the provider. See :attr:`LinkDecision.checked_on`."""


@dataclass(frozen=True)
class LinkDecision:
    """What an interface should do with one program's provider link.

    Every field is answerable from a single :class:`LinkCheck` plus, for a 404, the check of
    the same host's front page. The decision is made here rather than in the interface so
    that the rule is in one place, is tested, and cannot drift between two renderers.

    The unchecked case is not a special case with a default -- it is the *first* case, and it
    reproduces exactly what a build with no link data has always published: link the URL as
    filed, say nothing about it, claim nothing.
    """

    url: str
    """The URL as the federal record filed it. Always shown, even when not linked: it is the
    source's own value, and a reader may want to try the Internet Archive with it."""
    href: str | None
    """Where the link should point, or ``None`` for "publish no link". ``None`` here is a
    decision reached from evidence, unlike every other ``None`` in this module."""
    linked: bool
    label: LinkLabel
    verdict: Verdict | None
    """``None`` means this URL was never checked. Not alive, not dead -- unexamined."""
    reason: Reason | None
    checked_on: str | None
    """ISO date of the observation, ``None`` when there was none. Any sentence an interface
    prints about this link must carry it: a verdict has a shelf life."""
    notice: LinkNotice | None
    """Set only when something must be said. ``None`` for every alive and every
    indeterminate result, so an interface cannot annotate a page nobody established anything
    about."""
    substitution: LinkSubstitution | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "href": self.href,
            "linked": self.linked,
            "label": self.label,
            "verdict": self.verdict,
            "reason": self.reason,
            "checked_on": self.checked_on,
            "notice": self.notice,
            "substitution": self.substitution,
        }


def _unchecked(url: str) -> LinkDecision:
    """What to publish about a URL nobody read: exactly what was published before any of
    this existed."""
    return LinkDecision(
        url=url,
        href=url,
        linked=True,
        label=LABEL_PROGRAM_PAGE,
        verdict=None,
        reason=None,
        checked_on=None,
        notice=None,
        substitution=None,
    )


def decide(checks: Mapping[str, LinkCheck], url: str | None) -> LinkDecision | None:
    """Decide what to publish for one provider URL. ``None`` when there is no URL at all.

    The rule, class by class, and the reasoning for each is in
    ``docs/dead-provider-links-2026-08-04.md``:

    * **unchecked** -- link it as filed. An unchecked URL is not a dead URL.
    * **alive** -- link it, swapped for a verified ``https`` equivalent where one was
      observed. A deep path that answered only at the site root is relabelled, not
      suppressed: the provider is there, the specific page is not.
    * **indeterminate** -- link it as filed, say nothing. A 403 is a statement about the
      requester and a timeout is a statement about the wire; neither is evidence about a
      school, and printing "we could not reach this" next to a working institution's WIOA
      figures would be a false claim about a named organisation.
    * **dead** -- do not link the dead path. Where the same host's front page answers, link
      *that*, labelled as the provider's home page. Where it does not, publish no link and
      keep the URL as plain text.

    A ``dead`` decision always carries :data:`NOTICE_UNREACHABLE` and a date, whether or not
    a front page was substituted: silently rerouting a reader to a different page, or
    silently dropping a URL the federal record contains, would each be a quiet lie of its
    own kind.
    """
    if url is None:
        return None
    check = checks.get(url)
    if check is None:
        return _unchecked(url)

    checked_on = check.checked_at.date().isoformat()
    if check.verdict == "alive":
        upgraded = check.https_alternative
        return LinkDecision(
            url=url,
            href=upgraded or check.url,
            linked=True,
            label=(
                LABEL_PROVIDER_HOME
                if check.reason == "redirected_to_site_root"
                else LABEL_PROGRAM_PAGE
            ),
            verdict=check.verdict,
            reason=check.reason,
            checked_on=checked_on,
            notice=None,
            substitution=SUBSTITUTION_HTTPS if upgraded else None,
        )

    if check.verdict == "indeterminate":
        # Change nothing. Not even the scheme: an https equivalent is only offered on the
        # strength of an answer, and this URL did not give us one to reason from.
        return LinkDecision(
            url=url,
            href=url,
            linked=True,
            label=LABEL_PROGRAM_PAGE,
            verdict=check.verdict,
            reason=check.reason,
            checked_on=checked_on,
            notice=None,
            substitution=None,
        )

    front = front_page_for(checks, url)
    return LinkDecision(
        url=url,
        href=front,
        linked=front is not None,
        label=LABEL_PROVIDER_HOME if front is not None else LABEL_PROGRAM_PAGE,
        verdict=check.verdict,
        reason=check.reason,
        checked_on=checked_on,
        notice=NOTICE_UNREACHABLE,
        substitution=SUBSTITUTION_FRONT_PAGE if front is not None else None,
    )


# --------------------------------------------------------------------------------------
# The report a build reads
# --------------------------------------------------------------------------------------

DOCUMENT_VERSION: Final = 1
"""Bumped if the on-disk shape ever changes incompatibly, so a build can refuse an old file
rather than misread one."""


def checks_document(
    checks: Mapping[str, LinkCheck], *, checked_at: datetime | None = None
) -> dict[str, Any]:
    """The run's results, as the document a later build reads.

    A list rather than an object keyed by URL: the URL is already inside each entry, and one
    place for it means a file that cannot disagree with itself.
    """
    return {
        "version": DOCUMENT_VERSION,
        "checked_at": (checked_at or _utcnow()).isoformat(),
        "urls": len(checks),
        "checks": [check.as_dict() for check in checks.values()],
    }


def checks_from_document(payload: Mapping[str, Any]) -> dict[str, LinkCheck]:
    """Rebuild a run's results from :func:`checks_document`.

    Strict on purpose, unlike :class:`LinkCheckCache`. A cache that cannot be read costs a
    re-check; a *report* that cannot be read is an operator pointing a build at a file that
    does not say what they think it says, and quietly treating it as "nothing was checked"
    would publish links this project had already established were broken.
    """
    version = payload.get("version")
    if version != DOCUMENT_VERSION:
        raise ValueError(f"unsupported link-check document version {version!r}")
    checks = [LinkCheck.from_dict(entry) for entry in payload["checks"]]
    return {check.url: check for check in checks}


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
