"""Client for California EDD labor market data published on data.ca.gov.

Sources D2-D4 in PROVENANCE.md. Resource URLs are resolved through the CKAN API by dataset
slug rather than hard-coded, because EDD re-publishes these files under new resource ids on
every projection cycle and a pinned URL would silently rot.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx

# The HTTP manners -- descriptive User-Agent, bounded retry with backoff, Retry-After --
# are defined once in dol_etp and shared, so both public endpoints get approached the same
# way and neither can quietly become the rude one.
from camino.sources.dol_etp import build_client, get_with_retry

CKAN_BASE = "https://data.ca.gov/api/3/action"
OCCUPATIONAL_PROJECTIONS = "long-term-occupational-employment-projections"
OEWS = "oews"
REGIONAL_PLANNING_UNITS = "regional-planning-unit-overviews"
REQUEST_TIMEOUT = 120.0

STATEWIDE_AREA = "California"

DETAILED_SOC_LEVEL = 4
"""EDD's own hierarchy level for a detailed occupation. 1-3 are progressively broader
roll-ups (all occupations, major group, minor group) and are not jobs anyone trains for."""


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("$", "")
    if not text or text.upper() in {"N/A", "NA", "*", "-", "**"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_wage(value: Any) -> float | None:
    """Parse a wage, treating an exact zero as "not published".

    EDD writes 0 where it has no wage to publish -- typically irregular or hourly-only work
    such as Actors, Dancers and Legislators, and occasionally a detailed occupation like
    Chemical Engineers. Nobody in these occupations earns nothing, so a literal $0 on the
    page would be a lie about a real job. Job openings are left alone: zero openings is a
    coherent and meaningful figure.
    """
    parsed = _to_float(value)
    return None if parsed == 0 else parsed


def _to_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return None if not text or text.upper() in {"N/A", "NA"} else text


@dataclass(frozen=True)
class OccupationProjection:
    """One occupation's outlook for one geography, from the EDD long-term projections."""

    area_type: str | None
    area_name: str | None
    period: str | None
    soc_level: int | None
    soc_code: str | None
    title: str | None
    base_employment: float | None
    projected_employment: float | None
    numeric_change: float | None
    percent_change: float | None
    total_job_openings: float | None
    median_hourly_wage: float | None
    median_annual_wage: float | None
    entry_level_education: str | None
    work_experience: str | None
    job_training: str | None

    @property
    def is_statewide(self) -> bool:
        return (self.area_name or "").strip() == STATEWIDE_AREA

    @property
    def is_detailed_occupation(self) -> bool:
        """True only for real occupations, not statistical roll-ups.

        EDD publishes its own hierarchy level, so use it. An earlier version guessed from
        the code shape and rejected only major groups (``XX-0000``); minor groups end
        ``-1000``, ``-2000`` and so on and slipped through, putting ~100 aggregates such as
        "Top Executives" into the index as though they were jobs. EDD publishes no wage for
        an aggregate, so each arrived carrying a median wage of 0 and rendered as "$0 a
        year" -- a suppressed-versus-zero failure reached by a different route.
        """
        return self.soc_level == DETAILED_SOC_LEVEL and self.soc_code is not None


def resolve_resource_url(
    dataset: str, *, fmt: str = "CSV", client: httpx.Client | None = None
) -> str:
    """Return the download URL of a dataset's first resource matching ``fmt``."""
    owns_client = client is None
    http = client or build_client(REQUEST_TIMEOUT)
    try:
        response = get_with_retry(http, f"{CKAN_BASE}/package_show", params={"id": dataset})
        resources = response.json()["result"]["resources"]
        for resource in resources:
            url = resource.get("url")
            if (resource.get("format") or "").upper() == fmt.upper() and url:
                return str(url)
        raise LookupError(f"no {fmt} resource on data.ca.gov dataset {dataset!r}")
    finally:
        if owns_client:
            http.close()


def _download_csv(url: str, client: httpx.Client | None = None) -> str:
    owns_client = client is None
    http = client or build_client(REQUEST_TIMEOUT)
    try:
        response = get_with_retry(http, url)
        return response.text
    finally:
        if owns_client:
            http.close()


def parse_projections(text: str) -> Iterator[OccupationProjection]:
    for row in csv.DictReader(io.StringIO(text)):
        soc_level = _to_float(row.get("SOC Level"))
        yield OccupationProjection(
            area_type=_to_text(row.get("Area Type")),
            area_name=_to_text(row.get("Area Name")),
            period=_to_text(row.get("Period")),
            soc_level=int(soc_level) if soc_level is not None else None,
            soc_code=_to_text(row.get("Standard Occupational Classification (SOC)")),
            title=_to_text(row.get("Occupational Title")),
            base_employment=_to_float(row.get("Base Year Employment Estimate")),
            projected_employment=_to_float(row.get("Projected Year Employment Estimate")),
            numeric_change=_to_float(row.get("Numeric Change")),
            percent_change=_to_float(row.get("Percentage Change")),
            total_job_openings=_to_float(row.get("Total Job Openings")),
            median_hourly_wage=_to_wage(row.get("Median Hourly Wage")),
            median_annual_wage=_to_wage(row.get("Median Annual Wage")),
            entry_level_education=_to_text(row.get("Entry Level Education")),
            work_experience=_to_text(row.get("Work Experience")),
            job_training=_to_text(row.get("Job Training")),
        )


def fetch_projections(client: httpx.Client | None = None) -> list[OccupationProjection]:
    url = resolve_resource_url(OCCUPATIONAL_PROJECTIONS, client=client)
    return list(parse_projections(_download_csv(url, client=client)))
