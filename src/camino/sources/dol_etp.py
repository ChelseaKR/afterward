"""Client for the U.S. DOL Eligible Training Provider scorecard search API.

Source D1 in PROVENANCE.md. This is the public search backend behind
trainingproviderresults.gov, serving WIOA ETA-9171 performance data.

Two things about this data matter more than anything else in this module:

1. ``-1`` and ``""`` mean "not reported or suppressed", never zero. WIOA suppresses
   small-cohort cells to protect participant privacy. Rendering a suppressed cell as 0%
   would libel a training provider, so :func:`clean_measure` maps both to ``None`` and the
   distinction is preserved all the way to the UI.
2. Programs carry SOC codes directly (``field_program_soc_occ_1..3``), so the program ->
   occupation join needs no CIP/SOC crosswalk.

This module also owns the HTTP manners for the whole package -- see "HTTP citizenship"
below. ``edd_lmi`` imports that layer from here so the two clients cannot drift apart in
how they identify themselves or how hard they push a public endpoint.
"""

from __future__ import annotations

import json
import re
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from camino import __version__

BASE_URL = "https://cxsearch.dol.gov/etp"
PROGRAMS_INDEX = "etp_scorecard_programs"
PAGE_SIZE = 500
REQUEST_TIMEOUT = 60.0
PAUSE_BETWEEN_PAGES = 0.4
"""Deliberate throttle. This is a public service funded by taxpayers, not a firehose."""

SUPPRESSED = -1
"""Sentinel used by the ETP scorecard for withheld or unreported measures."""


def clean_measure(value: Any) -> float | None:
    """Map an ETP measure to a float, or ``None`` when not reported.

    Empty strings and the ``-1`` sentinel both mean "no data" and must not be confused
    with a genuine zero.
    """
    if value is None or value == "":
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return None if numeric == SUPPRESSED else numeric


def clean_rate(value: Any, *, field: str = "") -> float | None:
    """Parse a rate, enforcing the contract that it is a fraction between 0 and 1.

    Every rate in the current feed is a fraction (0.64 meaning 64%), but nothing upstream
    guarantees that, and the display layer used to hedge with "if it is above 1, assume it is
    a whole percentage". That hedge is wrong per-row rather than wholesale: it renders 64 as
    64% correctly while rendering a genuine 1% as 100% and 0.5% as 50%, and nothing would
    ever flag it.

    So the unit is checked once, here, where the data enters. A value outside 0..1 is not a
    rate this code knows how to read, so it becomes "not reported" and says so on stderr
    rather than being silently reinterpreted downstream.
    """
    parsed = clean_measure(value)
    if parsed is None:
        return None
    if not 0.0 <= parsed <= 1.0:
        print(
            f"warning: {field or 'rate'} = {parsed!r} is outside 0..1; expected a fraction. "
            "Treating as not reported — check whether the feed changed units.",
            file=sys.stderr,
        )
        return None
    return parsed


SAFE_URL_SCHEMES = ("http://", "https://")
_BARE_DOMAIN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9-]+)+(/.*)?$", re.I)


def clean_url(value: Any) -> str | None:
    """Return an absolute http(s) URL, or None.

    The feed's ``field_program_url`` is free text and providers treat it as such: some file a
    bare domain, and five California records hold a course title where a URL belongs. Those
    were rendered straight into an ``href``, so "Provider's website" navigated to a relative
    path inside this site.

    Anything that is not http(s) is dropped rather than passed through. React does not block
    ``javascript:`` in an ``href``, so an unvalidated third-party string in that position is a
    script-injection sink waiting for one bad row upstream. Nothing in the current feed
    exploits it, which is not a reason to keep the hole open.

    A bare domain is repaired to https rather than discarded: it is unambiguous, and losing a
    working provider link helps nobody.
    """
    text = clean_text(value)
    if not text:
        return None
    lowered = text.lower()
    if lowered.startswith(SAFE_URL_SCHEMES):
        return text
    if lowered.startswith("//"):
        return f"https:{text}"
    if " " not in text and _BARE_DOMAIN.match(text):
        return f"https://{text}"
    return None


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass(frozen=True)
class Program:
    """A single training program as reported to DOL under WIOA."""

    uuid: str
    provider_name: str | None
    program_name: str | None
    description: str | None
    program_format: str | None
    program_url: str | None
    cip_code: str | None
    soc_codes: tuple[str, ...]
    city: str | None
    state: str | None
    zip_code: str | None
    lat: float | None
    lon: float | None
    entity_type: str | None
    length_weeks: float | None
    length_hours: float | None
    cost_wioa: float | None
    cost_tuition: float | None
    cost_supplies: float | None
    # Outcome measures. None means "not reported"; see clean_measure.
    total_served: float | None
    total_exited: float | None
    total_completed: float | None
    completed_percent: float | None
    total_credential: float | None
    median_earnings: float | None
    q2_employment_percent: float | None
    employed_q2: float | None
    employed_q4: float | None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def has_outcomes(self) -> bool:
        """True when at least one headline outcome measure was reported."""
        return any(
            m is not None
            for m in (self.median_earnings, self.q2_employment_percent, self.completed_percent)
        )

    @property
    def total_cost(self) -> float | None:
        """Non-WIOA out-of-pocket cost, when any component was reported.

        May be a floor rather than a total -- see :attr:`cost_is_complete`. Summing a
        reported tuition with a suppressed supplies figure quietly treats the unknown part
        as zero, which is the one thing this codebase is not allowed to do, so callers must
        check completeness before presenting this as "the cost".
        """
        parts = [c for c in (self.cost_tuition, self.cost_supplies) if c is not None]
        return sum(parts) if parts else None

    @property
    def cost_is_complete(self) -> bool:
        """True when every cost component was reported, so the total really is the total."""
        return self.cost_tuition is not None and self.cost_supplies is not None


def _soc_codes(source: dict[str, Any]) -> tuple[str, ...]:
    """Extract and normalise the up-to-three SOC codes attached to a program.

    The feed writes them zero-padded to 8 digits (``15-125200``); the standard 6-digit SOC
    used by EDD is the first six (``15-1252``).
    """
    codes: list[str] = []
    for key in ("field_program_soc_occ_1", "field_program_soc_occ_2", "field_program_soc_occ_3"):
        raw = clean_text(source.get(key))
        if not raw:
            continue
        digits = raw.replace("-", "")
        if len(digits) >= 6 and digits[:6].isdigit():
            normalised = f"{digits[:2]}-{digits[2:6]}"
            if normalised not in codes:
                codes.append(normalised)
    return tuple(codes)


def parse_program(hit: dict[str, Any]) -> Program:
    source = hit.get("_source", {})
    return Program(
        uuid=str(source.get("field_uuid") or hit.get("_id") or ""),
        provider_name=clean_text(source.get("field_etp")),
        program_name=clean_text(source.get("field_program_name")),
        description=clean_text(source.get("field_program_description")),
        program_format=clean_text(source.get("field_program_format")),
        program_url=clean_url(source.get("field_program_url")),
        cip_code=clean_text(source.get("field_cip_code")),
        soc_codes=_soc_codes(source),
        city=clean_text(source.get("field_city")),
        state=clean_text(source.get("field_state")),
        zip_code=clean_text(source.get("field_zip")),
        lat=clean_measure(source.get("field_lat")),
        lon=clean_measure(source.get("field_lon")),
        entity_type=clean_text(source.get("field_entity_type")),
        length_weeks=clean_measure(source.get("field_program_length_weeks")),
        length_hours=clean_measure(source.get("field_program_length_hours")),
        cost_wioa=clean_measure(source.get("field_cost_per_wioa_num")),
        cost_tuition=clean_measure(source.get("field_non_wioa_tuition_cost")),
        cost_supplies=clean_measure(source.get("field_non_wioa_supplies_cost")),
        total_served=clean_measure(source.get("field_c_total_served")),
        total_exited=clean_measure(source.get("field_c_total_exited")),
        total_completed=clean_measure(source.get("field_c_total_completed")),
        completed_percent=clean_rate(
            source.get("field_c_completed_percent"), field="completion rate"
        ),
        total_credential=clean_measure(source.get("field_c_total_credential")),
        median_earnings=clean_measure(source.get("field_c_median_earnings")),
        q2_employment_percent=clean_rate(
            source.get("field_c_q2_employment_percent"), field="Q2 employment rate"
        ),
        employed_q2=clean_measure(source.get("field_total_employed_q2")),
        employed_q4=clean_measure(source.get("field_total_employed_q4")),
        raw=source,
    )


STATES_INDEX = "etp_scorecard_states"


@dataclass(frozen=True)
class StateBenchmark:
    """Statewide totals, so a single program's numbers can be read against something.

    Without this a rate is unanchored: a reader has no way to know whether 45% employed is
    strong or dismal. California's own statewide figure is the fairest available yardstick,
    since it is the same measure computed over the same population by the same reporters.
    """

    state: str
    completion_rate: float | None
    q2_employment_rate: float | None
    median_earnings: float | None
    credential_rate: float | None
    total_exited: float | None
    total_completed: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "completion_rate": self.completion_rate,
            "employment_rate_q2": self.q2_employment_rate,
            "median_earnings": self.median_earnings,
            "credential_rate": self.credential_rate,
            "total_exited": self.total_exited,
            "total_completed": self.total_completed,
        }


def parse_state_benchmark(state: str, source: dict[str, Any]) -> StateBenchmark:
    """Build a benchmark from a states-index document."""
    return StateBenchmark(
        state=state,
        completion_rate=clean_rate(
            source.get("field_c_completed_percent"), field="state completion rate"
        ),
        q2_employment_rate=clean_rate(
            source.get("field_c_q2_employment_percent"), field="state Q2 employment rate"
        ),
        median_earnings=clean_measure(source.get("field_c_median_earnings")),
        credential_rate=clean_rate(
            source.get("field_c_cred_attainment_percent"), field="state credential rate"
        ),
        total_exited=clean_measure(source.get("field_c_total_exited")),
        total_completed=clean_measure(source.get("field_c_total_completed")),
    )


# --------------------------------------------------------------------------------------
# HTTP citizenship
#
# Everything below is about being a guest on someone else's server. Both source clients in
# this package share it: one honest identity, one retry policy, one throttle.
# --------------------------------------------------------------------------------------

USER_AGENT = (
    f"camino/{__version__} (+https://github.com/ChelseaKR/camino; "
    "non-commercial open-data client; quarterly bulk read)"
)
"""Who we say we are.

Deliberately not a browser string. The endpoints here are public taxpayer-funded services
and their operators are entitled to know who is reading them and where to complain: a
spoofed Chrome User-Agent would buy access by lying, and would leave an operator no way to
tell this project apart from a scraper. Being identifiable is the point, even though it
means a filter can single us out.
"""

MAX_ATTEMPTS = 4
BACKOFF_INITIAL_SECONDS = 1.0
BACKOFF_MULTIPLIER = 2.0
BACKOFF_CAP_SECONDS = 30.0
RETRY_AFTER_CAP_SECONDS = 120.0
"""Longest ``Retry-After`` we will wait out rather than fail and let a human reschedule."""

RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})
"""Statuses worth a second look. 403 and 404 are decisions, not hiccups, and are absent."""


class FetchError(RuntimeError):
    """A public endpoint could not be read.

    The message is written for whoever is staring at a failed build log, not for a
    stack trace: it should say what refused us and what to do about it.
    """

    def __init__(self, message: str, *, url: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.url = url
        self.status_code = status_code


def build_client(timeout: float = REQUEST_TIMEOUT) -> httpx.Client:
    """An ``httpx.Client`` that identifies itself."""
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )


def _forbidden_message(url: str) -> str:
    host = httpx.URL(url).host
    return (
        f"{host} refused the request (HTTP 403 Forbidden). Not retried: a refusal is a "
        "decision, and repeating it would only be rude.\n"
        "This is known to happen from CI runners and other datacenter IP ranges even when "
        "the identical request succeeds from a laptop, because the endpoint sits behind a "
        "load balancer that filters on client IP reputation and on User-Agent. This client "
        f"already sends a descriptive User-Agent ({USER_AGENT!r}) and will not impersonate "
        "a browser to get around the filter.\n"
        "If this happened in CI, build from the committed data snapshot instead "
        "(`camino build-offline`) and refresh that snapshot from a workstation."
    )


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """Seconds the server asked us to wait, from either Retry-After form, or None."""
    raw = (response.headers.get("Retry-After") or "").strip()
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


def _backoff_seconds(attempt: int) -> float:
    return min(BACKOFF_INITIAL_SECONDS * BACKOFF_MULTIPLIER ** (attempt - 1), BACKOFF_CAP_SECONDS)


def _raise_if_permanent(response: httpx.Response, url: str) -> None:
    """Raise unless the status is one that might resolve itself."""
    status = response.status_code
    if status == httpx.codes.FORBIDDEN:
        raise FetchError(_forbidden_message(url), url=url, status_code=status)
    if status in RETRYABLE_STATUS:
        return
    raise FetchError(
        f"{url} returned HTTP {status} {response.reason_phrase}. Not retried: this status "
        "will not change on its own.",
        url=url,
        status_code=status,
    )


def _retry_wait(response: httpx.Response, attempt: int, url: str) -> float:
    """How long to wait before the next attempt, honouring Retry-After when present."""
    requested = _retry_after_seconds(response)
    if requested is None:
        return _backoff_seconds(attempt)
    if requested > RETRY_AFTER_CAP_SECONDS:
        raise FetchError(
            f"{url} returned HTTP {response.status_code} and asked for a "
            f"{requested:.0f}s wait, longer than this client will hold a build open. "
            "Respecting that means stopping here and retrying later.",
            url=url,
            status_code=response.status_code,
        )
    return requested


def get_with_retry(
    client: httpx.Client,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    max_attempts: int = MAX_ATTEMPTS,
    sleep: Callable[[float], None] | None = None,
) -> httpx.Response:
    """GET ``url``, retrying only what is plausibly transient.

    Timeouts, connection failures, 429 and 5xx get bounded exponential backoff, and a
    ``Retry-After`` header overrides that backoff. A 403 or 404 is raised on the first
    response instead of being hammered in a tight loop.

    The User-Agent is set per request as well as on :func:`build_client`, so a
    caller-supplied client still identifies itself.
    """
    wait_out = time.sleep if sleep is None else sleep
    problem = "no attempt was made"
    cause: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.get(url, params=params, headers={"User-Agent": USER_AGENT})
        except httpx.TransportError as exc:
            problem, cause = f"{type(exc).__name__}: {exc}", exc
            wait = _backoff_seconds(attempt)
        else:
            if not response.is_error:
                return response
            _raise_if_permanent(response, url)
            problem, cause = f"HTTP {response.status_code} {response.reason_phrase}".strip(), None
            wait = _retry_wait(response, attempt, url)
        if attempt == max_attempts:
            break
        wait_out(wait)
    raise FetchError(
        f"{url} could not be read after {max_attempts} attempts; last failure was {problem}.",
        url=url,
    ) from cause


def fetch_state_benchmark(
    state: str = "CA", *, client: httpx.Client | None = None
) -> StateBenchmark | None:
    """Fetch the statewide aggregate for ``state``, or None if it is not published."""
    body = {
        "size": 1,
        "query": {
            "bool": {
                "filter": [
                    {"term": {"_index": STATES_INDEX}},
                    {"term": {"field_state": state}},
                ]
            }
        },
    }
    owns_client = client is None
    http = client or build_client()
    try:
        response = get_with_retry(
            http,
            f"{BASE_URL}/_search",
            params={"source": json.dumps(body), "source_content_type": "application/json"},
        )
        hits = response.json().get("hits", {}).get("hits", [])
        if not hits:
            return None
        return parse_state_benchmark(state, hits[0].get("_source", {}))
    finally:
        if owns_client:
            http.close()


def _query_body(state: str, page_size: int, after: list[Any] | None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "size": page_size,
        "sort": [{"nid": "asc"}],
        "query": {
            "bool": {
                "filter": [
                    {"term": {"_index": PROGRAMS_INDEX}},
                    {"term": {"field_state": state}},
                ]
            }
        },
    }
    if after is not None:
        body["search_after"] = after
    return body


def fetch_programs(
    state: str = "CA",
    *,
    page_size: int = PAGE_SIZE,
    client: httpx.Client | None = None,
) -> Iterator[Program]:
    """Yield every ETP program reported for ``state``.

    Uses ``search_after`` rather than ``from``/``size`` so the read stays correct if the
    result set ever grows past Elasticsearch's 10k window.
    """
    owns_client = client is None
    http = client or build_client()
    after: list[Any] | None = None
    try:
        while True:
            body = _query_body(state, page_size, after)
            response = get_with_retry(
                http,
                f"{BASE_URL}/_search",
                params={
                    "source": json.dumps(body),
                    "source_content_type": "application/json",
                },
            )
            hits = response.json().get("hits", {}).get("hits", [])
            if not hits:
                return
            for hit in hits:
                yield parse_program(hit)
            last_sort = hits[-1].get("sort")
            if not last_sort or len(hits) < page_size:
                return
            after = last_sort
            time.sleep(PAUSE_BETWEEN_PAGES)
    finally:
        if owns_client:
            http.close()
