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

A status code alone does not settle it. Measured on the August 2026 corpus, 20 of the 767
URLs that answered 2xx were not pages at all: 10 were the provider's own "page not found"
screen served with HTTP 200, and 10 were domain-sale listings on hosts that had bought the
lapsed address. Every one of those 23 program pages published a confident
"Provider's website" link into nothing. So a 2xx is also asked what it *says* it is, from
its ``<title>`` and no further, and :data:`SOFT_NOT_FOUND_TITLES` and
:data:`DOMAIN_FOR_SALE_TITLES` are the two things it can say that this module treats as
evidence.

Manners, since every host here is a small college or an adult school rather than a CDN: one
GET per URL, its body read only as far as ``</title>`` and never past
:data:`BODY_READ_CAP` (median 529 characters on the real corpus), one request at a time per
site with a pause between them, bounded concurrency across sites, retries only for what is
plausibly transient, ``Retry-After`` honoured, and the honest
:data:`~afterward.sources.dol_etp.USER_AGENT` this project uses everywhere else. No browser
impersonation: a host that wants to refuse this client is entitled to recognise it and do so,
which is exactly why a refusal is classified ``indeterminate`` instead of ``dead``.

There was a HEAD before that GET until the body became part of the question. Dropping it
costs nothing and removes a measured defect: the prior audit found 33 of 769 live URLs whose
HEAD disagreed with their GET -- 8 of them answering HEAD with 404 -- and the HEAD-then-GET
second opinion existed only to survive that. Asking with the method a reader's browser uses,
once, makes the disagreement unreachable rather than survivable, and spends fewer requests
than confirming a bad HEAD ever did.

Results are cached on disk by URL so a rebuild does not re-ask 1,000 providers whether they
still exist.

A 2xx from *another domain* is a third thing again, and the one this module cannot settle by
itself. ``moler.org`` now answers from ``moler.edu`` and that is a barber college that
rebranded; ``giligiacollege.com`` now answers from an Indonesian gambling site, and from a
redirect alone the two are the same event. That question is
:mod:`afterward.sources.link_review`'s, it is answered from corroboration rather than from
the redirect, and until it is answered :func:`decide` publishes no link.

Reading a URL is only half of it. :func:`decide` turns one check into the decision an
interface needs -- link this, link that instead, or link nothing and say why -- so that the
rule lives in one tested place instead of being reinvented by whatever renders the page.
Its first case is the unchecked one, and it reproduces exactly what was published before any
of this existed.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
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

from afterward.sources import link_review
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
"""Tries for one URL, spread over a few seconds of backoff -- less than a reader hammering
reload on a broken page."""

HTTPS_PROBE_ATTEMPTS: Final = 1
"""The https probe answers "is there a free upgrade?", not "is this record's link good", so
it gets one try. Missing an upgrade costs nothing; a second round of traffic does."""

NO_HTTPS_PROBE_REASONS: Final[frozenset[str]] = frozenset({"dns_failure", "domain_for_sale"})
"""Findings about the *address* rather than about one page, for which asking the https
variant is a request spent on a foregone answer. A name DNS has never heard of does not
exist over TLS either, and a domain being advertised for sale is advertised for sale on both
schemes -- three of the corpus's for-sale URLs are plain http, and a parking host is the
last host worth knocking on twice."""

MAX_WORKERS: Final = 8
"""Sites checked at once. Never two requests to the same site concurrently -- see
:func:`check_urls`, which hands each site to one worker as a unit."""

PAUSE_BETWEEN_SAME_HOST: Final = 1.0
"""Seconds between consecutive requests to one site, including a URL and the https probe of
the same address."""

REQUEST_HEADERS: Final[Mapping[str, str]] = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
}

BODY_READ_CAP: Final = 65_536
"""Characters of body read before giving up on finding a ``<title>``.

Reading stops at ``</title>`` rather than at this cap, which on the August 2026 corpus meant
a median of 529 characters and under 1 KB for more than half of the 755 HTML responses. The
cap is the backstop for the rest: 32 of those 755 push ``</title>`` past 64 KB, and the
furthest reached 170 KB. Truncating one of those is safe in the only direction that matters
-- a title nobody read is a title nobody matched, so the page stays ``alive``. The cap can
only cost a detection, never manufacture one.
"""

TITLE_PATTERN: Final = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)

_MARKUP: Final = re.compile(r"<[^>]+>")
_WHITESPACE: Final = re.compile(r"\s+")

_TITLE_SEGMENTS: Final = re.compile(
    # Pipe, en dash, em dash, middle dot, bullet; then hyphen or Unicode hyphen, but only
    # when spaced. Escaped rather than typed because a literal en dash and a literal hyphen
    # are indistinguishable in most editors, and this is a file where the difference decides
    # whether a title splits.
    "\\s*[|\u2013\u2014\u00b7\u2022]\\s*|\\s+[-\u2010]\\s+"
)
"""How providers separate a page's own name from their institution's.

Split on these and ``404 - Elk Grove Unified School District`` yields the segment ``404``,
which is the school district saying this page is not there. A plain hyphen only separates
when it is spaced, so a hyphenated page name stays in one piece.
"""

HTML_CONTENT_TYPES: Final[tuple[str, ...]] = ("text/html", "application/xhtml+xml")
"""What is worth reading a body from. The corpus also holds 10 PDFs and 2 ``text/plain``
responses; a PDF has no ``<title>`` element and reading 64 KB of one to discover that would
be traffic spent on a provider for nothing."""

SOFT_NOT_FOUND_TITLES: Final = re.compile(
    r"""^(?:
        (?:oops[!.]?\s*)?(?:error\s*)?404
            (?:\s*[-:]?\s*(?:error|not\s+found|page\s+not\s+found|file\s+not\s+found))?
      | (?:page|file|document)\s+not\s+found
      | not\s+found
      | (?:oops[!.]?\s*)?(?:this\s+)?page\s+(?:does\s+not|doesn'?t)\s+exist[.!]?
      | we\s+(?:could\s+not|couldn'?t)\s+find\s+that\s+page
      | (?:the\s+)?page\s+(?:you\s+requested\s+)?(?:could\s+not|cannot|can'?t)\s+be\s+found
    )$""",
    re.IGNORECASE | re.VERBOSE,
)
"""Titles that are the page stating it does not exist.

Every branch is a string a real California provider served with HTTP 200 on 2026-08-05:
``404 Error`` and ``Oops! 404 Error`` (butte.edu, 3 pages), ``404`` as the first segment
(egace.egusd.net, 4 pages), ``Not Found`` (springboard.com, 2 pages),
``Page Not Found`` (maiquelascosmetology.net, 2 pages). Nothing here was invented.

The pattern is anchored to a whole title segment, not searched for inside one, because that
is the difference between a page announcing itself as missing and a page that mentions the
word. Matched against all 755 HTML titles in the corpus it fired 10 times and every one was a
genuine "page not found" screen -- no false positives. The residual risk is a bare ``404``
segment belonging to a real page, which would need a title like ``404 | Welding``; course
codes in these titles carry their subject prefix (``MATH 104``), which keeps them out of a
segment of their own. That risk is accepted, and the direction of the error is worth stating
plainly: it would hide a working provider, so if it ever fires wrongly the fix is to narrow
this pattern, not to widen it.
"""

DOMAIN_FOR_SALE_TITLES: Final = re.compile(
    r"""^(?:
        \S{1,60}\s+is\s+for\s+sale
      | buy\s+this\s+(?:expired\s+)?domain
      | (?:this\s+)?domain(?:\s+name)?\s+is\s+for\s+sale
    )$""",
    re.IGNORECASE | re.VERBOSE,
)
"""Titles that are a listing offering the address itself for sale.

``AselBeauty.com is for sale`` (HugeDomains) and ``Buy this expired domain``
(expireddomains.com) between them account for 10 URLs on 12 program pages in the corpus,
every one of them published today as a working "Provider's website" link. The single-token
requirement in the first branch is what keeps ``<something>.com is for sale`` from reaching
a sentence about property.

This is deliberately *not* a list of marketplace hostnames. A hostname list is a guess about
who is in that business and rots the day a new one opens; a page saying it is selling the
address is that page's own statement about itself, which is the only kind of evidence the
rest of this module accepts.
"""

CLASSIFIER_VERSION: Final = 2
"""What this module's judgement is worth, bumped whenever the same response would now be
classified differently.

``1`` was the status code and the redirect chain. ``2`` is that plus what a 2xx says it is,
from its ``<title>`` -- the soft-404 and domain-for-sale detection added on 2026-08-05.

This exists because of what happened to that change. Verdicts are cached per URL for 30 days
when ``alive``, so on 2026-08-15 the published dataset contained **no** ``soft_not_found`` and
**no** ``domain_for_sale`` decision at all: the report was the 2026-08-04 run, every entry in
it was still warm, and a re-run of ``check-links`` would have handed back the very verdicts
the new detector was written to replace. Ten "page not found" screens and ten domain-sale
listings stayed published as working provider links, and nothing anywhere said so.

So the cache now serves an entry only to the classifier that wrote it. A version bump costs a
full re-read -- roughly 1,100 requests, spread politely, on a pass a person invokes
deliberately -- which is the correct price for having changed what a check means.
"""

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
    "soft_not_found",
    "domain_for_sale",
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
    # Alive says a page answered. It does not say whose page, and for this reason it must not
    # be read as one: the answer came from a domain the record did not name. Who is at the
    # other end is settled -- or explicitly left unsettled -- by
    # :mod:`afterward.sources.link_review`, and :func:`decide` refuses to link an off-site
    # redirect that nothing corroborates.
    "redirected_offsite": "alive",
    # Dead. Every one of these is the far end saying so itself: DNS has never heard of the
    # name, the server states the page is not there in its status line, or -- for the two
    # added after the August 2026 audit found 23 program pages linking into them -- the page
    # that answered says in its own title that it is not a page, or that the address is for
    # sale. A 200 is not a page; it is only a promise of one.
    "dns_failure": "dead",
    "not_found": "dead",
    "gone": "dead",
    "soft_not_found": "dead",
    "domain_for_sale": "dead",
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
    classifier_version: int = CLASSIFIER_VERSION
    """Which version of this module's judgement produced the verdict.

    Written on every check and read by the cache. An entry from an older classifier is not
    wrong -- it is unasked, about whatever the newer one would have looked at -- so it is
    re-checked rather than reinterpreted.
    """

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
            "classifier_version": self.classifier_version,
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
            # A file written before the classifier was versioned gets 0, which is older than
            # every version there is. That is the fail-safe direction: it costs a re-read and
            # it cannot mistake a verdict from an unknown classifier for a current one.
            classifier_version=int(payload.get("classifier_version", 0)),
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


def _is_html(content_type: str | None) -> bool:
    """Whether a response is the kind of thing that has a ``<title>`` to read."""
    if not content_type:
        # No Content-Type at all. Reading the body would be guessing at its format, and this
        # module does not read anything it cannot say it understood.
        return False
    kind = content_type.split(";", 1)[0].strip().lower()
    return kind in HTML_CONTENT_TYPES


def read_title(response: httpx.Response) -> str | None:
    """The page's own name, taken from the front of the body and no further.

    Streams until ``</title>`` arrives or :data:`BODY_READ_CAP` characters have gone by,
    whichever is first, then stops reading and lets the caller close the response. On the
    real corpus that is a median of 529 characters per provider -- the title is the first
    thing a page says about itself, so almost nothing has to be transferred to hear it.

    ``None`` for a response with no title, an unreadable one, or a body that is not HTML.
    ``None`` means "the page did not tell us", never "the page is fine".
    """
    if not _is_html(response.headers.get("content-type")):
        return None
    buffer = ""
    try:
        for chunk in response.iter_text():
            buffer += chunk
            if len(buffer) >= BODY_READ_CAP or "</title" in buffer.lower():
                break
    except httpx.HTTPError:
        # The body stopped arriving partway through. Whatever we have is all there is; a
        # truncated read is not a finding, and the partial buffer is still worth matching.
        pass
    match = TITLE_PATTERN.search(buffer[:BODY_READ_CAP])
    return None if match is None else _plain_text(match.group(1))


def _plain_text(markup: str) -> str:
    """A title as a reader would see it: no tags, no entities, no run-on whitespace."""
    return _WHITESPACE.sub(" ", html.unescape(_MARKUP.sub(" ", markup))).strip()


def _title_segments(title: str) -> list[str]:
    """The whole title, plus each part providers separate with ``|``, ``-`` or a dash.

    Both, because a title is a not-found statement either way it is written: ``Not Found``
    entire, or ``Page Not Found`` in front of the school's name.
    """
    return [title, *(part.strip() for part in _TITLE_SEGMENTS.split(title) if part.strip())]


def _reason_for_title(title: str | None) -> Reason | None:
    """What the page says it is, when what it says settles the question.

    ``None`` for every ordinary title, which is nearly all of them: this only ever answers
    when a page has announced itself as missing or as merchandise. Anything less than that
    is not evidence, and a page that merely looks empty or unhelpful is not judged here --
    the SiteGround bot-check interstitials in this corpus are byte-for-byte as bare as a
    parking stub, and 16 working providers sit behind them.
    """
    if title is None:
        return None
    for segment in _title_segments(title):
        if SOFT_NOT_FOUND_TITLES.match(segment):
            return "soft_not_found"
        if DOMAIN_FOR_SALE_TITLES.match(segment):
            return "domain_for_sale"
    return None


@dataclass(frozen=True)
class _Outcome:
    """One request sequence, reduced to plain data so no live response escapes."""

    status_code: int | None
    final_url: str | None
    transport_reason: Reason | None
    detail: str | None
    attempts: int
    title: str | None = None
    """What the page called itself, when it answered and had a name to give."""

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

    The response is streamed, and read only as far as its ``<title>`` -- and only when it
    answered 2xx and is HTML, because a title is the one part of a page that says whether it
    is a page at all. Everything else is closed unread: a provider should not pay to serve a
    body nobody looks at, and there is nothing to learn from the body of a 404.
    ``Retry-After`` is read here, while the response is still in scope.
    """
    with client.stream(method, url, headers=REQUEST_HEADERS, follow_redirects=True) as response:
        status = response.status_code
        title = read_title(response) if 200 <= status < 300 else None
        outcome = _Outcome(status, str(response.url), None, None, attempt, title)
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
    detail = outcome.detail
    if outcome.succeeded:
        # What the page says about itself outranks the fact that it answered. A 200 whose
        # title is "Page Not Found" is the server disagreeing with its own status line, and
        # the title is the half a reader would act on.
        spoken = _reason_for_title(outcome.title)
        reason = spoken or _reason_for_success(httpx.URL(url), final)
        if spoken is not None:
            # The evidence itself, kept in the report so the verdict can be argued with
            # rather than taken on trust.
            detail = f"page title: {outcome.title}"[:200]
    else:
        reason = _reason_for_status(outcome.status_code)
    return LinkCheck(
        url=url,
        verdict=VERDICT_BY_REASON[reason],
        reason=reason,
        status_code=outcome.status_code,
        final_url=str(final),
        https_alternative=None,
        detail=detail,
        checked_at=now,
        attempts=attempts,
    )


def _probe(
    url: str,
    *,
    client: httpx.Client,
    max_attempts: int,
    sleep: Callable[[float], None],
    now: datetime,
) -> LinkCheck:
    """Read one URL, with the method a reader's browser would use.

    GET, once. This module used to ask HEAD first and confirm anything negative with a GET,
    because HEAD is the method servers implement worst -- the prior audit measured 33 of 769
    live URLs whose HEAD disagreed with their GET, 8 of them answering HEAD with 404 for a
    page that GETs perfectly well. That second opinion was the right fix for the wrong
    question. Asking the way a reader asks removes the disagreement instead of surviving it,
    it is what makes the page's own title available to judge, and it costs fewer requests
    than confirming a bad HEAD did.
    """
    return _to_check(
        url, _request(client, "GET", url, max_attempts=max_attempts, sleep=sleep), now=now
    )


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
    if check.reason in NO_HTTPS_PROBE_REASONS:
        return check
    sleep(pause)
    probed = _probe(
        candidate,
        client=client,
        max_attempts=min(max_attempts, HTTPS_PROBE_ATTEMPTS),
        sleep=sleep,
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
        if check.classifier_version != CLASSIFIER_VERSION:
            # Written by a classifier that asked a different question. Serving it would let a
            # detector improve nothing for thirty days, which is exactly what happened to the
            # 2026-08-05 title detector: see :data:`CLASSIFIER_VERSION`.
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
    check = _probe(url, client=client, max_attempts=max_attempts, sleep=sleep, now=moment)
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

FRONT_PAGE_REASONS: Final[frozenset[str]] = frozenset({"not_found", "gone", "soft_not_found"})
"""The dead reasons for which a front page is worth asking about.

A 404 is the server saying *this page* is not there while plainly still being there itself,
so the provider's own front door is a real alternative destination. ``soft_not_found`` is
the same server saying the same thing in its title instead of its status line, and it pays
off at the same rate: all four of the corpus's soft-404 hosts answer normally at their root
-- Elk Grove Adult and Community Education, Butte College, Springboard and Maiquela's
Cosmetology Academy -- so every one of those 11 program pages gains a working destination
rather than losing a broken one.

``dns_failure`` and ``domain_for_sale`` are not in this set, for the same reason as each
other: neither is a finding about one page. The name does not exist, or the whole address is
merchandise, and in both cases there is nothing under it to offer instead. Asking a parking
host for its front page would only produce a second sales listing.
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

LinkNotice = Literal[
    "page_unreachable",
    "domain_for_sale",
    "redirect_unrelated",
    "redirect_unconfirmed",
]
"""What must be said about a link, in the site's own voice.

Four values, because there are four situations a reader does something different about. A
page that is not there is a page that is not there, whether the server said so in its status
line or in its title -- so a soft 404 carries ``page_unreachable`` like any other, rather
than multiplying wording over a distinction the reader cannot act on.

An address that is for sale is not that. "We could not reach this page" would send someone
back to retry a URL that is never coming back, and would be false besides: we reached it
perfectly well, and what answered was an advertisement. That is worth its own sentence, and
it is worth it because of what it tells a reader to do instead -- look the school up by
name, or telephone it.

The last two are the off-site redirects, and they are split for the same reason.
``redirect_unrelated`` is a hand review having found somebody else's live site at the other
end -- three of this dataset's addresses now serve gambling, lottery and charity sites that
have nothing to do with the school that filed them. ``redirect_unconfirmed`` is the honest
majority case: the address goes somewhere else and nothing available here established who is
there. Neither is linked, and neither says the provider is gone: what is gone is the address.
"""

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

NOTICE_FOR_SALE: Final[LinkNotice] = "domain_for_sale"
"""The recorded address answered with a listing offering the domain for sale.

Also a statement about our reading on a date, and deliberately not one about the school. A
lapsed domain does not mean a closed school: the LAUSD adult centres behind the corpus's
largest dead domain are open and teaching, at a different address. What is gone is the
address, and that is the only thing this notice claims.
"""

NOTICE_REDIRECT_UNRELATED: Final[LinkNotice] = "redirect_unrelated"
"""The recorded address now sends a visitor to a live site that is somebody else's.

Only a hand review reaches this, recorded in ``provider-link-review.json`` with its evidence
and its date -- no signal available to a fetch distinguishes an unrelated live site from a
legitimate rebrand, which is exactly why three hijacked domains were published as working
provider links until somebody opened them.
"""

NOTICE_REDIRECT_UNCONFIRMED: Final[LinkNotice] = "redirect_unconfirmed"
"""The recorded address redirects somewhere else and nothing here established where.

The commonest of the four and the one worth being careful about: it is not an accusation, it
is an admission. It says the filed address no longer answers for itself and this project will
not vouch for what does.
"""


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
    redirect: link_review.Resolution | None = None
    """What was established about an off-site redirect, and ``None`` when the address never
    left the site it named.

    Published rather than kept internal, for the same reason ``verdict`` is: a consumer of
    this dataset joining on ``href`` deserves to know that a link survived a review rather
    than a build. It is also what lets a packaging gate tell a dataset built with the review
    from one built before it -- a distinction that is otherwise invisible, since an
    unreviewed redirect and a confirmed one looked identical in every earlier build.
    """

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
            "redirect": self.redirect,
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


NOTICE_BY_RESOLUTION: Final[Mapping[link_review.Resolution, LinkNotice]] = {
    "unrelated": NOTICE_REDIRECT_UNRELATED,
    "for_sale": NOTICE_FOR_SALE,
    "unresolved": NOTICE_REDIRECT_UNCONFIRMED,
}
"""What to say about an off-site redirect this project will not link.

``same_provider`` is absent on purpose: it is the one resolution that produces a link, and a
link that goes where the record said it goes has nothing to annotate.
"""


def _offsite(
    check: LinkCheck, *, checked_on: str, redirect: link_review.RedirectVerdict
) -> LinkDecision:
    """What to publish for a URL that answered from a different domain.

    Confirmed same-provider redirects are published exactly as they were before this rule
    existed: the filed URL, linked, unannotated. Everything else is published as the URL in
    plain text with a sentence, because the alternative -- linking a destination nobody could
    vouch for -- is how three hijacked domains came to be published as provider links.

    The filed URL is what is linked for a confirmed rebrand, rather than the destination the
    redirect ended at. The redirect is the provider's own and following it is how a reader
    reaches them; and swapping in a destination silently would be the quiet reroute this
    module refuses everywhere else.
    """
    if redirect.publishable:
        upgraded = check.https_alternative
        return LinkDecision(
            url=check.url,
            href=upgraded or check.url,
            linked=True,
            label=LABEL_PROGRAM_PAGE,
            verdict=check.verdict,
            reason=check.reason,
            checked_on=checked_on,
            notice=None,
            substitution=SUBSTITUTION_HTTPS if upgraded else None,
            redirect=redirect.resolution,
        )
    return LinkDecision(
        url=check.url,
        href=None,
        linked=False,
        label=LABEL_PROGRAM_PAGE,
        verdict=check.verdict,
        reason=check.reason,
        checked_on=checked_on,
        notice=NOTICE_BY_RESOLUTION[redirect.resolution],
        substitution=None,
        redirect=redirect.resolution,
    )


def decide(
    checks: Mapping[str, LinkCheck],
    url: str | None,
    *,
    redirect: link_review.RedirectVerdict | None = None,
) -> LinkDecision | None:
    """Decide what to publish for one provider URL. ``None`` when there is no URL at all.

    The rule, class by class, and the reasoning for each is in
    ``docs/dead-provider-links-2026-08-04.md``:

    * **unchecked** -- link it as filed. An unchecked URL is not a dead URL.
    * **alive** -- link it, swapped for a verified ``https`` equivalent where one was
      observed. A deep path that answered only at the site root is relabelled, not
      suppressed: the provider is there, the specific page is not.
    * **alive, from another domain** (``redirected_offsite``) -- link it only where
      :mod:`afterward.sources.link_review` establishes that the destination is still this
      provider. ``redirect`` carries that finding; a caller that does not resolve redirects
      gets the unresolved answer, because a redirect nobody resolved is a redirect nobody
      vouched for, and the reader is the one who pays for the difference.
    * **indeterminate** -- link it as filed, say nothing. A 403 is a statement about the
      requester and a timeout is a statement about the wire; neither is evidence about a
      school, and printing "we could not reach this" next to a working institution's WIOA
      figures would be a false claim about a named organisation.
    * **dead** -- do not link the dead path. Where the same host's front page answers, link
      *that*, labelled as the provider's home page. Where it does not, publish no link and
      keep the URL as plain text. A page that answered 200 while saying in its own title
      that it is not there is dead on exactly these terms: the reader's situation is
      identical, so the treatment is too.

    A ``dead`` decision always carries a notice and a date, whether or not a front page was
    substituted: silently rerouting a reader to a different page, or silently dropping a URL
    the federal record contains, would each be a quiet lie of its own kind. The notice is
    :data:`NOTICE_FOR_SALE` when the address turned out to be merchandise and
    :data:`NOTICE_UNREACHABLE` otherwise, because those want different sentences and only
    one of them is true of a page we could not reach.
    """
    if url is None:
        return None
    check = checks.get(url)
    if check is None:
        return _unchecked(url)

    checked_on = check.checked_at.date().isoformat()
    if check.reason == "redirected_offsite":
        return _offsite(check, checked_on=checked_on, redirect=redirect or link_review.UNRESOLVED)

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
        notice=NOTICE_FOR_SALE if check.reason == "domain_for_sale" else NOTICE_UNREACHABLE,
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
        # The classifier this run's own results were produced by. Per-entry values are what
        # decide anything -- a report can hold a mix, because a re-run re-reads only what the
        # cache would no longer serve -- and this is the run's own stamp beside them.
        "classifier_version": CLASSIFIER_VERSION,
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


def unasked_by_the_current_classifier(checks: Mapping[str, LinkCheck]) -> list[str]:
    """URLs whose verdict predates the current classifier, and so was never asked its question.

    Not an error and not a reason to refuse a build: an older verdict is still an observation,
    and withholding every link over it would hide hundreds of working schools. It is a reason
    to *say something*, which is what nothing did for the ten days the 2026-08-05 title
    detector spent judging nothing at all.
    """
    return [url for url, check in checks.items() if check.classifier_version != CLASSIFIER_VERSION]


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
