"""Client for California's Occupational Employment and Wage Statistics (OEWS).

Source D3 in PROVENANCE.md. OEWS is the BLS/EDD establishment survey behind almost every
published California wage figure. Where the long-term projections (D2) publish one median
per occupation, OEWS publishes the whole shape of the distribution -- 10th, 25th, 50th,
75th and 90th percentiles, plus a mean, a headcount and a relative standard error -- for the
state and for each metropolitan or survey region separately.

The resource URL is resolved through CKAN by dataset slug, and the HTTP manners come from
``dol_etp``, for the reasons those modules already give.

Three things about this file decide how it has to be read, all measured on 2026-08-04
against the full published extract (580,790 rows, 2009-2026):

**It is a panel, not a snapshot.** Every annual vintage from 2009 to 2026 is stacked in one
file, all labelled ``1st Qtr``, and EDD's own dataset notes say the estimates "should not be
used as a time series" because area definitions and methods change underneath them. Anything
that reads this file must pick one ``Year`` and stay in it; see :func:`latest_year`.

**Zero means suppressed, in the vintages that use it.** See :func:`_to_wage`.

**Its spellings drift.** Area names, area-type labels and wage-type labels are all written
differently in different vintages ("Bakersfield MSA" then "Bakersfield-Delano MSA",
``California-Statewide`` and ``California - Statewide``, ``Hourly wage`` and ``Hourly
Wage``). Everything below normalises rather than matching a literal, and the SOC code is
stored unhyphenated (``151252``), so it is reformatted on the way in to the ``15-1252`` used
everywhere else in this project.

What OEWS does **not** carry, despite being the usual source for them: no entry-level or
experienced wage columns, and no industry detail. ``Industry Name`` takes exactly two values
across the whole file, ``Total, All Industries`` and ``Total, All Industry``, which are two
spellings of the same all-industry total.
"""

from __future__ import annotations

import csv
import io
import itertools
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any, Final, Literal

import httpx

from afterward.sources.dol_etp import build_client, get_with_retry

# Resolved by slug through the same CKAN helper the projections use, so both EDD datasets
# are located the same way and neither can be pinned to a resource id that will rot.
from afterward.sources.edd_lmi import OEWS, STATEWIDE_AREA, resolve_resource_url

REQUEST_TIMEOUT = 300.0
"""Longer than the projections' timeout: the published extract is ~112 MB in one response."""

WageBasis = Literal["annual", "hourly"]
"""Which of the two rows EDD publishes for every occupation is being read.

Each (area, occupation) appears twice, once as an annual salary and once as an hourly rate,
and the two are the same estimate under a flat 2,080-hour year -- the annual figure divided
by the hourly one is 2,080 to within a rounding cent for 99.5% of 2026 rows. They are not
independent measurements, so presenting both as if they corroborate each other would be
double-counting one survey.
"""

ANNUAL: Final[WageBasis] = "annual"
HOURLY: Final[WageBasis] = "hourly"

METROPOLITAN_AREA_TYPE = "Metropolitan Area"
SURVEY_REGION_AREA_TYPE = "OES Survey Region"
"""OEWS's label for the rural areas outside any CBSA.

The projections call the same three places ``Consortium``. The *type* labels differ between
the two datasets; the *names* do not, which is what the join actually rests on. See the
module note in :func:`area_name_joins_to_projections`.
"""

_STATEWIDE_AREA_TYPE = "californiastatewide"
"""Area type casefolded with spaces and hyphens removed; the file spells it three ways."""

# Column headers, as published. Held as constants because several of them are long enough
# that a typo in a literal would silently yield None for a whole column.
_AREA_TYPE = "Area Type"
_AREA_NAME = "Area Name"
_YEAR = "Year"
_INDUSTRY = "Industry Name"
_SOC = "Standard Occupational Classification"
_TITLE = "Occupational Title"
_WAGE_TYPE = "Wage Type"
_EMPLOYMENT = "Number of Employed"
_MEAN = "Mean Wage"
_P10 = "10th Percentile Wage"
_P25 = "25th Percentile Wage"
_P50 = "50th Percentile (Median) Wage"
_P75 = "75th Percentile Wage"
_P90 = "90th Percentile Wage"
_RSE = "Mean Relative Standard Error for Wage"

_NULL_TOKENS = frozenset({"N/A", "NA", "*", "-", "**", "#"})

_SOC_DIGITS = 6


def _to_float(value: Any) -> float | None:
    """Parse a number, mapping blanks and EDD's textual null tokens to ``None``."""
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("$", "")
    if not text or text.upper() in _NULL_TOKENS:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_wage(value: Any) -> float | None:
    """Parse a wage, treating an exact zero as "not published".

    This project has already been bitten once by EDD writing 0 where it has no wage: 13
    occupations in the projections rendered "$0 a year". OEWS carries the same habit, and
    carries it far more widely.

    The evidence is in the file's own internal contradictions. Vintages 2009-2017 suppress
    with ``0`` and vintages 2018-2026 suppress with a blank -- the convention changes
    between 2017 and 2018 and never mixes. In the zero-writing vintages the sentinel is
    provable rather than inferred, because a suppressed percentile is written as 0 while its
    neighbours are not, producing orderings that no distribution can have: statewide Chief
    Executives in 2015 are published with a 10th percentile of $99,663, a 25th of $158,291,
    and a median, 75th and 90th of exactly 0. Read literally that says half of all chief
    executives earn nothing.

    Across all 580,790 rows there are 16,872 whose percentiles run backwards. Mapping zero
    to ``None`` resolves 16,870 of them, leaving 2 (one occupation in 2010, in both wage
    bases). A rule that repairs 99.99% of the impossible orderings in a file is describing
    that file's actual convention, not guessing at it.

    Nobody in a surveyed occupation earns nothing -- the occupation would not be surveyed --
    so a literal $0 on a page would be a false claim about a real job.
    """
    parsed = _to_float(value)
    return None if parsed == 0 else parsed


def _to_headcount(value: Any) -> float | None:
    """Parse an employment estimate, treating an exact zero as "not published".

    Zero is a sentinel here too, and on the same vintages. 2009-2017 carry 48,253 rows with
    an employment estimate of 0, of which 45,932 publish a positive wage in the same row: a
    wage estimated from an occupation that employs nobody is not a small number, it is an
    impossible one. The 2018-2026 vintages contain no zero headcount at all and blank the
    field instead, exactly as they do for wages.

    This is the one place where the reasoning differs from job openings in the projections,
    where a zero is kept because "no openings" is a coherent thing to publish. "No workers,
    and here is what they are paid" is not.
    """
    parsed = _to_float(value)
    return None if parsed == 0 else parsed


def _to_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return None if not text or text.upper() in _NULL_TOKENS else text


def _to_year(value: Any) -> int | None:
    parsed = _to_float(value)
    return int(parsed) if parsed is not None else None


def normalise_soc(value: Any) -> str | None:
    """Reformat OEWS's unhyphenated SOC code as the ``XX-XXXX`` used elsewhere here.

    Anything that is not six digits returns ``None``. That drops the roll-up rows the older
    vintages label with a bare ``0`` for "Total, All Occupations", which is not an
    occupation and has no code.
    """
    text = _to_text(value)
    if text is None:
        return None
    digits = text.replace("-", "").strip()
    if len(digits) != _SOC_DIGITS or not digits.isdigit():
        return None
    return f"{digits[:2]}-{digits[2:]}"


def _to_basis(value: Any) -> WageBasis | None:
    """Read the wage basis, tolerating the file's inconsistent capitalisation."""
    text = (_to_text(value) or "").casefold()
    if text.startswith("annual"):
        return ANNUAL
    if text.startswith("hourly"):
        return HOURLY
    return None


def _is_statewide_type(area_type: str | None) -> bool:
    if area_type is None:
        return False
    return area_type.replace(" ", "").replace("-", "").casefold() == _STATEWIDE_AREA_TYPE


@dataclass(frozen=True)
class WageDistribution:
    """One occupation's published wage distribution, for one area, year and wage basis.

    Every wage field is ``None`` when EDD did not publish it, never ``0``. Callers must
    treat the five percentiles as independently suppressible: a row can carry four of them
    and withhold the fifth, and one 2026 row does exactly that.
    """

    area_type: str | None
    area_name: str | None
    year: int | None
    industry: str | None
    soc_code: str | None
    title: str | None
    basis: WageBasis | None
    employment: float | None
    mean_wage: float | None
    p10: float | None
    p25: float | None
    p50: float | None
    p75: float | None
    p90: float | None
    relative_standard_error: float | None

    @property
    def is_statewide(self) -> bool:
        return (self.area_name or "").strip() == STATEWIDE_AREA or _is_statewide_type(
            self.area_type
        )

    @property
    def is_detailed_occupation(self) -> bool:
        """True for a detailed occupation, false for a statistical roll-up.

        OEWS publishes no equivalent of the projections' ``SOC Level`` column, so the level
        is read off the code's shape, which the 2018 SOC defines: a major group ends
        ``-0000``, a minor group ``-X000``, a broad group ``-XXX0``, and a detailed
        occupation's last digit is non-zero. Of the 844 distinct codes in the 2026 vintage,
        814 are detailed, 23 are major groups and 7 are broad groups.

        Broad-group codes are excluded here even though a few of them are the only estimate
        BLS publishes for some real occupations -- 31-1120 Home Health and Personal Care
        Aides is the example ``soc_vintage`` already deals with. That deliberate mapping
        belongs to the caller that owns it, not to a level test.
        """
        code = self.soc_code
        return code is not None and not code.endswith("0")

    @property
    def percentiles(self) -> tuple[float | None, ...]:
        """The five published percentiles in order, suppressed entries included as None."""
        return (self.p10, self.p25, self.p50, self.p75, self.p90)

    @property
    def has_any_wage(self) -> bool:
        return any(p is not None for p in self.percentiles)

    @property
    def is_complete(self) -> bool:
        """True when all five percentiles were published, so a full spread can be drawn."""
        return all(p is not None for p in self.percentiles)

    @property
    def is_monotonic(self) -> bool:
        """True when the published percentiles are non-decreasing.

        A false here means the row contradicts itself and no honest chart can be drawn from
        it. After :func:`_to_wage` maps zero to ``None`` only two rows in the entire
        2009-2026 file fail this, but the check is kept because it is the cheapest available
        detector of a *new* sentinel appearing in a future republication.
        """
        published = [p for p in self.percentiles if p is not None]
        return all(a <= b for a, b in itertools.pairwise(published))

    @property
    def spread_ratio(self) -> float | None:
        """How many times the 10th percentile the 90th percentile is, or ``None``.

        This is the number the median alone cannot express. Across the 657 California
        occupations that carry a full 2026 distribution it ranges from 1.0x (Taxi Drivers,
        $39,905 to $40,119) to 7.8x (Commercial Pilots, $65,289 to $511,119), with a median
        of 2.19x.
        """
        if self.p10 is None or self.p90 is None or self.p10 <= 0:
            return None
        return self.p90 / self.p10


def parse_wage_statistics(text: str) -> Iterator[WageDistribution]:
    """Parse the published CSV into records, one per area/year/occupation/wage basis."""
    for row in csv.DictReader(io.StringIO(text)):
        yield WageDistribution(
            area_type=_to_text(row.get(_AREA_TYPE)),
            area_name=_to_text(row.get(_AREA_NAME)),
            year=_to_year(row.get(_YEAR)),
            industry=_to_text(row.get(_INDUSTRY)),
            soc_code=normalise_soc(row.get(_SOC)),
            title=_to_text(row.get(_TITLE)),
            basis=_to_basis(row.get(_WAGE_TYPE)),
            employment=_to_headcount(row.get(_EMPLOYMENT)),
            mean_wage=_to_wage(row.get(_MEAN)),
            p10=_to_wage(row.get(_P10)),
            p25=_to_wage(row.get(_P25)),
            p50=_to_wage(row.get(_P50)),
            p75=_to_wage(row.get(_P75)),
            p90=_to_wage(row.get(_P90)),
            relative_standard_error=_to_float(row.get(_RSE)),
        )


def latest_year(rows: Iterable[WageDistribution]) -> int | None:
    """The most recent vintage present, or ``None`` if no row carries a year.

    Always prefer this to a hard-coded year. EDD appends a vintage to the same resource
    annually, so a pinned year quietly goes stale while continuing to parse cleanly.
    """
    years = [row.year for row in rows if row.year is not None]
    return max(years) if years else None


def select(
    rows: Iterable[WageDistribution],
    *,
    year: int | None = None,
    basis: WageBasis | None = ANNUAL,
) -> list[WageDistribution]:
    """Narrow a parsed panel to one vintage and one wage basis.

    ``year=None`` means the latest vintage present, which requires reading ``rows`` twice
    and so materialises them. ``basis=None`` keeps both the annual and hourly rows, which
    doubles every key and is only useful for inspection.
    """
    materialised = list(rows)
    wanted = latest_year(materialised) if year is None else year
    return [
        row
        for row in materialised
        if (wanted is None or row.year == wanted) and (basis is None or row.basis == basis)
    ]


def wage_index(
    rows: Iterable[WageDistribution],
    *,
    year: int | None = None,
    basis: WageBasis = ANNUAL,
) -> dict[tuple[str, str], WageDistribution]:
    """Index one vintage by ``(area_name, soc_code)``.

    The 2026 vintage has no duplicate key, but a republication that introduced one would be
    resolved here by keeping the first row seen, which is arbitrary. Rows missing an area
    name or an unreadable SOC code are dropped rather than keyed on ``None``.
    """
    index: dict[tuple[str, str], WageDistribution] = {}
    for row in select(rows, year=year, basis=basis):
        if row.area_name is None or row.soc_code is None:
            continue
        index.setdefault((row.area_name, row.soc_code), row)
    return index


def statewide_index(
    rows: Iterable[WageDistribution],
    *,
    year: int | None = None,
    basis: WageBasis = ANNUAL,
) -> dict[str, WageDistribution]:
    """Index one vintage's California-wide rows by SOC code."""
    return {
        row.soc_code: row
        for row in select(rows, year=year, basis=basis)
        if row.is_statewide and row.soc_code is not None
    }


def area_name_joins_to_projections(area_name: str | None) -> str | None:
    """The projections-side area key an OEWS area name corresponds to, or ``None``.

    There is no translation to do, and that is the finding rather than an omission. In the
    2026 vintage OEWS names its 31 non-statewide areas with exactly the strings the
    projections put before their parenthetical county gloss -- OEWS "Fresno MSA" against the
    projections' "Fresno MSA (Fresno and Madera Counties)" -- so
    :attr:`~afterward.sources.edd_lmi.ProjectionArea.short_name` is the join key on both sides
    and all 32 areas match, statewide included.

    This function exists so that fact is asserted in one place and tested, rather than being
    a coincidence a caller relies on silently. It deliberately does no normalisation: if a
    future vintage renames an area, the join must fail loudly here rather than be repaired
    by a prefix or edit-distance match that could attribute one region's wages to another.
    Older vintages in the same file *are* named differently ("Bakersfield MSA",
    "Sacramento--Roseville--Arden-Arcade MSA"), which is one more reason not to read them.
    """
    return _to_text(area_name)


def fetch_wage_statistics(
    client: httpx.Client | None = None,
    *,
    year: int | None = None,
    basis: WageBasis | None = ANNUAL,
) -> list[WageDistribution]:
    """Download and parse the published extract, narrowed to one vintage.

    The whole 2009-2026 panel is downloaded because EDD publishes no per-year resource, and
    the ~112 MB response is buffered in memory before parsing. Filtering happens after
    parsing, so what comes back is one vintage rather than eighteen. A caller that genuinely
    wants the whole panel should call :func:`parse_wage_statistics` directly on its own copy
    of the text and stay in control of the 580,790 records that produces.
    """
    owns_client = client is None
    http = client or build_client(REQUEST_TIMEOUT)
    try:
        url = resolve_resource_url(OEWS, client=http)
        response = get_with_retry(http, url)
        return select(parse_wage_statistics(response.text), year=year, basis=basis)
    finally:
        if owns_client:
            http.close()
