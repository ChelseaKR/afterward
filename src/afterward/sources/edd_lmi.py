"""Client for California EDD labor market data published on data.ca.gov.

Sources D2-D4 in PROVENANCE.md. Resource URLs are resolved through the CKAN API by dataset
slug rather than hard-coded, because EDD re-publishes these files under new resource ids on
every projection cycle and a pinned URL would silently rot.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

import httpx

# The HTTP manners -- descriptive User-Agent, bounded retry with backoff, Retry-After --
# are defined once in dol_etp and shared, so both public endpoints get approached the same
# way and neither can quietly become the rude one.
from afterward.sources.dol_etp import build_client, get_with_retry

CKAN_BASE = "https://data.ca.gov/api/3/action"
OCCUPATIONAL_PROJECTIONS = "long-term-occupational-employment-projections"
OEWS = "oews"
REGIONAL_PLANNING_UNITS = "regional-planning-unit-overviews"
"""EDD's Regional Planning Unit dataset (D4).

Kept as a documented source, but it does **not** define any geography that can be used to
place a training program. Inspected 2026-08-04: it is a second copy of the occupational
projections -- identical columns -- cut by the fifteen WIOA planning units ("Bay-Peninsula",
"Inland Empire") on the older 2023-2033 cycle. The area names carry no county list and no
city list, so there is nothing in it to join a program's address to, and its regions are a
different partition of the state from the MSA/consortium areas the current projections use.
The area geography this module actually relies on is parsed out of the projections file
itself; see :func:`parse_area`.
"""
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


# --------------------------------------------------------------------------------------
# Area geography
#
# EDD writes each area's definition into the ``Area Name`` string itself -- "Fresno MSA
# (Fresno and Madera Counties)" -- so the geography is read out of the file rather than
# transcribed into this module. Nothing below asserts a fact about California that EDD has
# not written down in the row being parsed.
# --------------------------------------------------------------------------------------

METROPOLITAN_AREA_TYPE = "Metropolitan Area"
"""EDD's label for its federal core-based statistical areas (MSAs and divisions).

The other non-statewide type is ``Consortium``, whose names ("North Coast Region") are
EDD's own coinages covering the rural counties left outside any CBSA. They name no cities,
so no program can be placed in one by the rule in :func:`principal_city_areas`.
"""

AREA_TYPE_CONSORTIUM = "Consortium"

_CBSA_SUFFIX = re.compile(r"\s+(?:MSA|MD)\Z")
_COUNTY_NOUN = re.compile(r"\bCount(?:y|ies)\b", re.IGNORECASE)
_COUNTY_SEPARATOR = re.compile(r",|\band\b", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")


def normalise_place(name: str | None) -> str | None:
    """Casefold and collapse whitespace so two place names can be compared exactly.

    Exactly, and only exactly. No prefix, substring, or edit-distance matching is offered
    anywhere in this module. Two California place names that nearly match are far more
    likely to be two different places than one typo -- Ontario and Ontario, San Mateo and
    San Marino -- and quietly attributing one area's wages to a program in another would be
    indistinguishable, on the page, from having got it right.
    """
    if name is None:
        return None
    collapsed = _WHITESPACE.sub(" ", name).strip().casefold()
    return collapsed if collapsed else None


@dataclass(frozen=True)
class ProjectionArea:
    """One EDD projection geography, as EDD's own ``Area Name`` string defines it."""

    area_type: str
    area_name: str
    principal_cities: tuple[str, ...]
    counties: tuple[str, ...]

    @property
    def is_metropolitan(self) -> bool:
        return self.area_type == METROPOLITAN_AREA_TYPE

    @property
    def short_name(self) -> str:
        """The area title without EDD's parenthetical county gloss, for display."""
        return self.area_name.partition("(")[0].strip()


def _principal_cities(head: str) -> tuple[str, ...]:
    """The cities a core-based statistical area title is built from.

    A CBSA is titled after its principal cities, each of which lies inside the area by
    construction: "Bakersfield-Delano MSA" is named that because Bakersfield and Delano are
    in it. That is what makes a match against this list a restatement of EDD's own
    published definition rather than an inference about California geography made here.

    The ``MSA``/``MD`` marker is required. Without it the string is not a CBSA title and
    its hyphens carry no such guarantee -- "North Valley-Northern Mountains Region" would
    otherwise yield two cities that do not exist.
    """
    stem = head.strip()
    if not _CBSA_SUFFIX.search(stem):
        return ()
    return tuple(part.strip() for part in _CBSA_SUFFIX.sub("", stem).split("-") if part.strip())


def _counties(tail: str) -> tuple[str, ...]:
    """The counties named in an area's parenthetical gloss, if it carries one."""
    inner = tail.partition(")")[0]
    if not inner.strip():
        return ()
    parts = _COUNTY_SEPARATOR.split(_COUNTY_NOUN.sub("", inner))
    return tuple(part.strip() for part in parts if part.strip())


def parse_area(area_type: str, area_name: str) -> ProjectionArea:
    """Split an EDD ``Area Name`` into the principal cities and counties it names."""
    head, _, tail = area_name.partition("(")
    return ProjectionArea(
        area_type=area_type,
        area_name=area_name,
        principal_cities=_principal_cities(head) if area_type == METROPOLITAN_AREA_TYPE else (),
        counties=_counties(tail),
    )


def area_definitions(projections: Iterable[OccupationProjection]) -> list[ProjectionArea]:
    """Every non-statewide geography the projections file publishes, parsed once each."""
    areas: dict[tuple[str, str], ProjectionArea] = {}
    for row in projections:
        if row.is_statewide or not row.area_type or not row.area_name:
            continue
        key = (row.area_type, row.area_name)
        if key not in areas:
            areas[key] = parse_area(row.area_type, row.area_name)
    return list(areas.values())


def principal_city_areas(areas: Iterable[ProjectionArea]) -> dict[str, ProjectionArea]:
    """Map each principal city name to the one area whose title names it.

    A city claimed by two areas is dropped rather than assigned to either. Nothing in the
    current EDD file is ambiguous this way, but a re-publication that introduced an
    ambiguity must lose the city rather than have this code pick a winner.
    """
    claims: dict[str, list[ProjectionArea]] = {}
    for area in areas:
        if not area.is_metropolitan:
            continue
        for city in area.principal_cities:
            key = normalise_place(city)
            if key is not None:
                claims.setdefault(key, []).append(area)
    return {
        city: claimed[0]
        for city, claimed in claims.items()
        if len({area.area_name for area in claimed}) == 1
    }


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
