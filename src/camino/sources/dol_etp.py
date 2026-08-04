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
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx

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
        """Non-WIOA out-of-pocket cost, when any component was reported."""
        parts = [c for c in (self.cost_tuition, self.cost_supplies) if c is not None]
        return sum(parts) if parts else None


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
        program_url=clean_text(source.get("field_program_url")),
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
        completed_percent=clean_measure(source.get("field_c_completed_percent")),
        total_credential=clean_measure(source.get("field_c_total_credential")),
        median_earnings=clean_measure(source.get("field_c_median_earnings")),
        q2_employment_percent=clean_measure(source.get("field_c_q2_employment_percent")),
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
        completion_rate=clean_measure(source.get("field_c_completed_percent")),
        q2_employment_rate=clean_measure(source.get("field_c_q2_employment_percent")),
        median_earnings=clean_measure(source.get("field_c_median_earnings")),
        credential_rate=clean_measure(source.get("field_c_cred_attainment_percent")),
        total_exited=clean_measure(source.get("field_c_total_exited")),
        total_completed=clean_measure(source.get("field_c_total_completed")),
    )


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
    http = client or httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True)
    try:
        response = http.get(
            f"{BASE_URL}/_search",
            params={"source": json.dumps(body), "source_content_type": "application/json"},
        )
        response.raise_for_status()
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
    http = client or httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True)
    after: list[Any] | None = None
    try:
        while True:
            body = _query_body(state, page_size, after)
            response = http.get(
                f"{BASE_URL}/_search",
                params={
                    "source": json.dumps(body),
                    "source_content_type": "application/json",
                },
            )
            response.raise_for_status()
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
