"""Client for the Projections Central long-term state occupational projections (D9).

Source D9 in PROVENANCE.md. This is the projection side of a build for a state other than
California: every state publishes its long-term occupational projections through the
Projections Managing Partnership, and Projections Central serves them in one shape for all
of them. California keeps EDD (D2), which publishes more -- wages, regions, education and
training -- and this reads the same figures for everybody else.

Four things about the endpoint decide how this module is written, and every one of them is
a measurement made against the live service on 2026-09-11 rather than a reading of any
documentation. They are recorded here because each is a way a careless adapter would publish
a number that is real, plausible, and about the wrong thing.

**1. The national row sits in the same array as the states.**
``/Projections/LongTermRestJson/all/<SOC>`` answers with one row per state *plus* a row
carrying ``STFIPS: "0"`` and ``Area: " United States"``, filed between Alabama and Alaska. A
reader that takes the first row, or that falls back to something when its own state is
absent, publishes a national figure as a state one. This module never asks that endpoint. It
asks the per-state one, and it then checks the answer: every row must carry the FIPS code
that was requested, and a row carrying ``"0"`` is refused by name rather than filtered out
quietly, because the only way one can arrive here is if the request went somewhere else.

**2. There is no wage column, and the openings column is a different measure.**
The whole column set is ``Area, Title, Base, Projected, Change, PercentChange,
AvgAnnualOpenings, STFIPS, StateURL, OccCode, BaseYear, ProjYear``. No median wage, no
percentile spread, no regional breakdown, no education or training column.
``AvgAnnualOpenings`` is an *annual average*, where EDD's ``Total Job Openings`` -- the field
this pipeline's occupation records carry -- is the ten-year total. Checked against the
California figures this project already publishes, the ratio is 10.0 across all 56
occupations in the committed dataset (22,890 a year against 228,840 over the cycle for
Registered Nurses). Putting one in the other's field would understate openings tenfold in a
figure nothing on the page could contradict, so :func:`parse_rows` leaves
``total_job_openings`` null and this adapter declares, through
:mod:`afterward.sources.projection_source`, that its source publishes no such measure.

**3. An unusable query parameter answers 404 "No results found.", exactly like a state with
no data.** ``items_per_page`` accepts 10, 25, 50, 100 and 1000 and answers 404 to every other
value -- 5, 20, 200, 500 and 2000 were all measured. So a 404 does not mean "this state
publishes nothing"; it can equally mean this code asked wrongly. Hence :data:`PAGE_SIZE` is
one of the accepted five and nothing else is ever sent, and a 404 is raised rather than
turned into an empty projection set.

**4. The bulk CSV the site offers is a different, older vintage.**
``projections/file/longterm/csv`` hands back a presigned S3 link to ``ltprojections.csv``,
whose metadata endpoint reports ``lastModified 08/13/2026`` -- and every one of its 36,073
rows is the **2022-2032** cycle, while ``projections/daterange/longterm`` and this JSON
endpoint both serve **2024-2034**. It is also missing one state entirely (FIPS 15, 54 states
against the JSON's 55). One file download would have been cheaper than seven paginated
requests, and it would have published a cycle-old projection under a current date. This
module reads the JSON, and it reads each row's own ``BaseYear``/``ProjYear`` rather than the
date-range endpoint, so the period on a record comes from the record.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Final

import httpx

# The HTTP manners -- descriptive User-Agent, bounded retry with backoff, Retry-After, and a
# 403 or 404 raised rather than hammered -- are defined once in dol_etp and shared, so every
# public endpoint this project reads gets approached the same way.
from afterward.sources.dol_etp import build_client, get_with_retry
from afterward.sources.edd_lmi import OccupationProjection

BASE_URL: Final = "https://public.projectionscentral.org"
LONG_TERM_PATH: Final = "Projections/LongTermRestJson"
REQUEST_TIMEOUT: Final = 120.0

NATIONAL_STFIPS: Final = "0"
"""The FIPS code Projections Central files the United States row under.

Named rather than inlined because it is refused in two places and because a bare ``"0"`` in
a filter reads like a defensive check against bad data. It is not: it is the one value in
this column that would publish a real measurement of the wrong population.
"""

PAGE_SIZE: Final = 100
"""Rows per request. One of the five values the pager accepts -- see the module docstring.

100 rather than 1000 so that a state larger than any seen today still pages correctly, and
so that the completeness check below has more than one page to check on every real state.
"""

ACCEPTED_PAGE_SIZES: Final = (10, 25, 50, 100, 1000)
"""Every ``items_per_page`` the service answered 200 to, measured 2026-09-11.

Kept as data so the test that pins :data:`PAGE_SIZE` can say *why* the value is not free to
change, rather than asserting a number against itself.
"""

MAX_PAGES: Final = 200
"""A stop, so a pager that always reports another page cannot loop forever.

200 pages is 20,000 rows against a largest observed state of 833, and reaching it raises
rather than returning what was collected so far: a truncated projection set is a set of
occupations that silently "publish no projection".
"""


class ProjectionsCentralError(RuntimeError):
    """The service answered, and what it answered cannot be used as published."""


def _to_float(value: Any) -> float | None:
    """Parse a published figure, or None where there is not one.

    None rather than zero, and no sentinel decoding: nothing in the two states measured on
    2026-09-11 (671 California rows and 657 Nevada rows) carried a non-numeric value in any
    of the five numeric columns, so there is no observed suppression marker to decode and
    inventing one would be a rule about data nobody has seen.
    """
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def is_detailed_soc(code: str | None) -> bool:
    """True for a detailed 2018 SOC occupation, false for any aggregate above it.

    Projections Central publishes no level column, so the level is read off the code, which
    the 2018 SOC structure makes unambiguous: a major group is ``XX-0000``, a minor group
    ``XX-Y000``, a broad occupation ``XX-YYY0``, and a detailed occupation is the only one
    whose last digit is not zero.

    The whole rule, not half of it. EDD's reader learned this the expensive way -- an earlier
    version of it rejected only the ``XX-0000`` major groups, so ~100 minor-group aggregates
    such as "Top Executives" entered the index as though they were jobs. Measured on the 657
    Nevada rows: 649 detailed, 7 broad occupations (13-1020, 13-2020, 29-2010, 31-1120,
    39-7010, 47-4090, 51-2090 -- the same aggregates :mod:`afterward.sources.soc_vintage`
    already maps California's detailed codes onto) and one major-group total (00-0000).
    """
    text = (code or "").strip()
    return (
        len(text) == 7
        and text[2] == "-"
        and text[:2].isdigit()
        and text[3:].isdigit()
        and (text[-1] != "0")
    )


@dataclass(frozen=True)
class RefusedRow:
    """A published row this pipeline cannot restate without asserting something false."""

    soc_code: str | None
    title: str | None
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {"soc_code": self.soc_code, "title": self.title, "reason": self.reason}


CONTRADICTORY_ZERO: Final = "base_employment_zero_with_a_non_zero_change"
"""Base employment of 0 beside a change that could not have happened from zero.

Nevada files ``45-4029 Logging Workers, All Other`` as ``Base: "0", Projected: "0",
Change: "0", PercentChange: "25"``. Employment is published to the nearest ten, so the true
figures are under five and the percentage was computed before rounding -- which means the
zeros are a rounding floor and not a count. Publishing ``base_employment: 0`` would say that
nobody in Nevada does this work; publishing ``percent_change: 25`` beside it would say that a
workforce of nobody is growing by a quarter. Neither is true, and the row says so itself, so
it is refused by name and counted rather than emitted.
"""


@dataclass(frozen=True)
class StateProjections:
    """One state's long-term projections, and what was left out of them."""

    state_fips: str
    rows: tuple[OccupationProjection, ...]
    refused: tuple[RefusedRow, ...]
    published_rows: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "state_fips": self.state_fips,
            "rows_published": self.published_rows,
            "rows_read": len(self.rows),
            "rows_refused": [row.as_dict() for row in self.refused],
        }


def _row_projection(row: dict[str, Any]) -> OccupationProjection:
    soc_code = _to_text(row.get("OccCode"))
    base_year = _to_text(row.get("BaseYear"))
    proj_year = _to_text(row.get("ProjYear"))
    return OccupationProjection(
        # The source publishes one geography per state and gives it no type. Null rather
        # than a word invented here: `area_definitions` reads the type to decide what a
        # region is, and a made-up label would create a region this source does not publish.
        area_type=None,
        area_name=_to_text(row.get("Area")),
        period=f"{base_year}-{proj_year}" if base_year and proj_year else None,
        # No level column. `is_detailed_occupation` below is decided from the code, and this
        # field stays null rather than carrying a level this publisher never stated.
        soc_level=None,
        soc_code=soc_code,
        title=_to_text(row.get("Title")),
        base_employment=_to_float(row.get("Base")),
        projected_employment=_to_float(row.get("Projected")),
        numeric_change=_to_float(row.get("Change")),
        percent_change=_to_float(row.get("PercentChange")),
        # Not AvgAnnualOpenings. See the module docstring: EDD's field is a ten-year total
        # and this source's is an annual average, measured at a ratio of 10.0 across all 56
        # occupations in the committed California dataset.
        total_job_openings=None,
        median_hourly_wage=None,
        median_annual_wage=None,
        entry_level_education=None,
        work_experience=None,
        job_training=None,
        # Every row this endpoint serves for a state code is that state's own figure; the
        # source publishes no sub-state geography at all.
        is_statewide=True,
        is_detailed_occupation=is_detailed_soc(soc_code),
    )


def _refusal(projection: OccupationProjection) -> str | None:
    if projection.base_employment == 0 and (
        (projection.percent_change or 0) != 0 or (projection.numeric_change or 0) != 0
    ):
        return CONTRADICTORY_ZERO
    return None


def parse_rows(rows: Iterable[dict[str, Any]], *, state_fips: str) -> StateProjections:
    """Turn one state's published rows into projections, refusing what cannot be restated.

    ``state_fips`` is checked against every row rather than trusted from the request. The
    national row is the reason: it is served in the same shape as a state's, it carries a
    real measurement, and nothing about the numbers on it would look wrong on a page.
    """
    published = 0
    kept: list[OccupationProjection] = []
    refused: list[RefusedRow] = []
    for row in rows:
        published += 1
        code = str(row.get("STFIPS") or "").strip()
        if code == NATIONAL_STFIPS:
            raise ProjectionsCentralError(
                "the response carries the United States row (STFIPS "
                f"{NATIONAL_STFIPS!r}, Area {row.get('Area')!r}) among the rows for state "
                f"{state_fips!r}. Refused rather than dropped: a national figure published "
                "as a state one is a real measurement of the wrong population, and the only "
                "way one reaches here is if the request was not the per-state one."
            )
        if code != state_fips:
            raise ProjectionsCentralError(
                f"state {state_fips!r} was requested and a row for state {code!r} "
                f"({row.get('Area')!r}) came back. Nothing is dropped on a mismatch; the "
                "whole read is refused, because a response mixing states is not one this "
                "code understands well enough to filter."
            )
        projection = _row_projection(row)
        reason = _refusal(projection)
        if reason is not None:
            refused.append(
                RefusedRow(soc_code=projection.soc_code, title=projection.title, reason=reason)
            )
            continue
        kept.append(projection)
    return StateProjections(
        state_fips=state_fips,
        rows=tuple(kept),
        refused=tuple(refused),
        published_rows=published,
    )


def _page(
    http: httpx.Client, state_fips: str, page: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    response = get_with_retry(
        http,
        f"{BASE_URL}/{LONG_TERM_PATH}/{state_fips}",
        params={"page": page, "items_per_page": PAGE_SIZE},
    )
    payload = response.json()
    if not isinstance(payload, dict):
        raise ProjectionsCentralError(
            f"{BASE_URL}/{LONG_TERM_PATH}/{state_fips} answered a "
            f"{type(payload).__name__}, not the object with 'rows' and 'pager' this reads."
        )
    rows = payload.get("rows")
    pager = payload.get("pager")
    if not isinstance(rows, list) or not isinstance(pager, dict):
        raise ProjectionsCentralError(
            f"page {page} for state {state_fips!r} carries no usable 'rows'/'pager' pair"
        )
    return rows, pager


def fetch_state_rows(
    state_fips: str, *, client: httpx.Client | None = None
) -> list[dict[str, Any]]:
    """Every published row for one state, paginated, or raise rather than return part of it.

    The pager's own ``total_items`` is the completeness check. Without it a dropped page is
    a set of occupations that "publish no projection" -- which is a sentence this project
    prints, and which would then be false about every occupation on the missing page.
    """
    owns_client = client is None
    http = client or build_client(REQUEST_TIMEOUT)
    collected: list[dict[str, Any]] = []
    try:
        rows, pager = _page(http, state_fips, 0)
        collected.extend(rows)
        total_items = int(pager.get("total_items") or 0)
        total_pages = int(pager.get("total_pages") or 0)
        if total_pages > MAX_PAGES:
            raise ProjectionsCentralError(
                f"state {state_fips!r} reports {total_pages} pages, past the {MAX_PAGES} "
                "this will read. Refused rather than truncated."
            )
        for page in range(1, total_pages):
            more, _ = _page(http, state_fips, page)
            collected.extend(more)
        if len(collected) != total_items:
            raise ProjectionsCentralError(
                f"state {state_fips!r} reports {total_items} rows and {len(collected)} "
                f"arrived over {total_pages} pages. Refused rather than published: the "
                "occupations on a missing page are indistinguishable, in the dataset, from "
                "occupations the state publishes no projection for."
            )
    finally:
        if owns_client:
            http.close()
    return collected


def fetch_state_projections(
    state_fips: str, *, client: httpx.Client | None = None
) -> StateProjections:
    """One state's long-term projections, checked against the code that was asked for."""
    if state_fips == NATIONAL_STFIPS:
        raise ProjectionsCentralError(
            f"state FIPS {NATIONAL_STFIPS!r} is the United States, not a state. This "
            "pipeline builds a state's dataset and has no page on which a national figure "
            "would be true."
        )
    return parse_rows(fetch_state_rows(state_fips, client=client), state_fips=state_fips)


def projections(state_projections: StateProjections) -> Sequence[OccupationProjection]:
    """The rows, for a caller that wants only them."""
    return state_projections.rows
