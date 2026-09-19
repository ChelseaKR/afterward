"""The projection side of a build, behind one interface, and what each source publishes.

The ETP side of this pipeline has been state-parameterised since the beginning: `afterward
build --state XX` asks DOL for that state's programs. The occupation side was California's
alone, because it read EDD directly. This is the seam that makes the whole thing a method
another state can run rather than a California site: a :class:`ProjectionSource` supplies
the occupation rows, EDD (D2) is the one California uses, and Projections Central (D9) is
the one every other state uses.

**The interesting half of this module is not the protocol. It is
:class:`PublishedMeasures`.** Two sources of "the same" measure do not publish the same
measures, and this pipeline's records have one shape for all of them. EDD publishes a median
wage, a ten-year openings total, regional rows, and the education and training a job asks
for. Projections Central publishes none of those five. Without a declaration, a Nevada
occupation carrying ``median_annual_wage: null`` is byte-for-byte indistinguishable from a
California occupation whose wage EDD withheld -- one of which is a fact about an occupation
and the other a fact about a source. That is this project's dominant defect in the shape it
is hardest to see: not an absence published as a number, but an absence published as *a
different absence*.

So every build writes into ``coverage.json`` which measures its projection source publishes
at all, and :func:`unpublished_measures_carrying_values` refuses a dataset that contradicts
its own declaration in either direction -- a measure declared absent that some record
carries, or a measure declared published that not one record does.

The declaration is a whole-dataset property and it lives where this project keeps those.
``is_fixture`` is the precedent: one flag in ``coverage.json`` that decides what may be
published. It is deliberately *not* a new key on every occupation record, because that would
change California's emitted occupations for a fact that is the same on all 671 of them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Final, Protocol

import httpx

from afterward.sources import edd_lmi, projections_central, state_fips
from afterward.sources.edd_lmi import OccupationProjection
from afterward.sources.projections_central import RefusedRow

CALIFORNIA: Final = "CA"


@dataclass(frozen=True)
class PublishedMeasures:
    """Which occupation measures this dataset's projection source publishes at all.

    One flag per field of an occupation record that a source can differ on. A ``False`` is
    a statement about the publisher, and it is the only thing standing between "this state
    does not publish wages" and "this occupation's wage was withheld", which the dataset
    otherwise renders identically.
    """

    base_employment: bool
    projected_employment: bool
    numeric_change: bool
    percent_change: bool
    total_job_openings: bool
    median_annual_wage: bool
    median_hourly_wage: bool
    entry_level_education: bool
    work_experience: bool
    job_training: bool
    regions: bool

    def as_dict(self) -> dict[str, bool]:
        return asdict(self)

    @property
    def absent(self) -> tuple[str, ...]:
        return tuple(name for name, published in sorted(self.as_dict().items()) if not published)


EDD_MEASURES: Final = PublishedMeasures(
    base_employment=True,
    projected_employment=True,
    numeric_change=True,
    percent_change=True,
    total_job_openings=True,
    median_annual_wage=True,
    median_hourly_wage=True,
    entry_level_education=True,
    work_experience=True,
    job_training=True,
    regions=True,
)
"""Every measure in the record: EDD's file carries a column for each of them.

``True`` here means *the publisher has a column for it*, not that every row is filled in.
EDD withholds a median wage for some occupations, and that null stays a fact about the
occupation -- which is exactly the distinction this table exists to preserve.
"""

PROJECTIONS_CENTRAL_MEASURES: Final = PublishedMeasures(
    base_employment=True,
    projected_employment=True,
    numeric_change=True,
    percent_change=True,
    # Not a column. AvgAnnualOpenings is an annual average against this field's ten-year
    # total -- measured at a ratio of 10.0 across all 56 occupations in the committed
    # California dataset -- so the source's openings figure has no field here to go in.
    total_job_openings=False,
    median_annual_wage=False,
    median_hourly_wage=False,
    entry_level_education=False,
    work_experience=False,
    job_training=False,
    regions=False,
)
"""Four of eleven. The whole column set is in :mod:`afterward.sources.projections_central`."""


@dataclass(frozen=True)
class SourceRead:
    """What a source returned, with the source that returned it.

    One object rather than a bare list of rows, because the two things a caller needs after
    a read -- the rows, and the sentence in ``coverage.json`` saying where they came from
    and what that publisher does not carry -- must not be able to come from two different
    places. A declaration assembled separately from the read it describes is a declaration
    that can be right about a source nobody read.
    """

    state: str
    source: str
    publisher: str
    endpoint: str
    publishes: PublishedMeasures
    rows: tuple[OccupationProjection, ...]
    rows_published: int | None
    refused: tuple[RefusedRow, ...] = ()
    rows_were_read: bool = True
    """False on the offline path, which reads a committed fixture and never asks the source.

    It decides whether the row counts in the declaration are numbers or nulls, and that is
    not cosmetic. ``rows_published: 0`` beside 56 indexed occupations says the publisher
    served nothing -- a statement about a source nobody contacted, which is this project's
    own defect class written into the block that exists to prevent it.
    """

    fixture_periods: tuple[str, ...] = ()
    """The periods the fixture's own occupations carry, when no rows were read."""

    def declaration(self, *, occupations_indexed: int) -> dict[str, Any]:
        """The block a build writes into ``coverage.json``.

        ``period`` is read off the rows rather than from the source's own date-range
        endpoint. Projections Central serves both, and on 2026-09-11 the bulk CSV it links
        to was a whole cycle older (2022-2032) than the rows its JSON endpoint answered
        with (2024-2034) under a ``lastModified`` of that August. A period taken from
        anywhere but the rows it describes is a date that can drift away from its data.
        """
        periods = (
            sorted({row.period for row in self.rows if row.period})
            if self.rows_were_read
            else sorted(set(self.fixture_periods))
        )
        return {
            "state": self.state,
            "source": self.source,
            "publisher": self.publisher,
            "endpoint": self.endpoint,
            "figures_read_from": "source" if self.rows_were_read else "committed_fixture",
            "period": periods[0] if len(periods) == 1 else None,
            "periods": periods if len(periods) != 1 else None,
            "publishes": self.publishes.as_dict(),
            "measures_this_source_does_not_publish": list(self.publishes.absent),
            "rows_published": self.rows_published if self.rows_were_read else None,
            "rows_read": len(self.rows) if self.rows_were_read else None,
            "rows_refused": [row.as_dict() for row in self.refused]
            if self.rows_were_read
            else None,
            "occupations_indexed": occupations_indexed,
        }


def fixture_read(source: ProjectionSource, *, state: str, periods: Sequence[str]) -> SourceRead:
    """The declaration for a build that read a committed fixture instead of the source.

    The fixture is a slice of a real build, so the publisher and the measure table are the
    ones that built it -- but no row was read here, and the block says so rather than
    reporting zero of them.
    """
    return SourceRead(
        state=state,
        source=source.source,
        publisher=source.publisher,
        endpoint=source.endpoint,
        publishes=source.publishes,
        rows=(),
        rows_published=None,
        rows_were_read=False,
        fixture_periods=tuple(str(period) for period in periods if period),
    )


class ProjectionSource(Protocol):
    """Somewhere a state's long-term occupational projections can be read from.

    Every member is declared read-only, which is what lets a frozen dataclass satisfy it.
    That is not a typing convenience: a source is a description of a publisher, and code
    that could reassign ``publishes`` on one could make a dataset's declaration disagree
    with the reader that produced it.
    """

    @property
    def state(self) -> str:
        """The two-letter code of the state this source answers for."""

    @property
    def source(self) -> str:
        """The PROVENANCE.md source id, e.g. ``"D2"``."""

    @property
    def publisher(self) -> str:
        """Who publishes the figures, named as they should appear in ``coverage.json``."""

    @property
    def publishes(self) -> PublishedMeasures:
        """Which occupation measures this publisher carries a column for at all."""

    @property
    def endpoint(self) -> str:
        """The address the rows were read from, for the record in ``coverage.json``."""

    def fetch(self, *, client: httpx.Client | None = None) -> SourceRead:
        """Read every published row for this source's state."""


@dataclass(frozen=True)
class EddProjections:
    """California, read from EDD's own published file (D2)."""

    state: str = CALIFORNIA
    source: str = "D2"
    publisher: str = "California Employment Development Department, via data.ca.gov"
    publishes: PublishedMeasures = field(default=EDD_MEASURES)

    @property
    def endpoint(self) -> str:
        return f"{edd_lmi.CKAN_BASE}/package_show?id={edd_lmi.OCCUPATIONAL_PROJECTIONS}"

    def fetch(self, *, client: httpx.Client | None = None) -> SourceRead:
        rows = tuple(edd_lmi.fetch_projections(client=client))
        return SourceRead(
            state=self.state,
            source=self.source,
            publisher=self.publisher,
            endpoint=self.endpoint,
            publishes=self.publishes,
            rows=rows,
            rows_published=len(rows),
        )


@dataclass(frozen=True)
class ProjectionsCentralSource:
    """Any other state, read from Projections Central's long-term endpoint (D9)."""

    state: str
    source: str = "D9"
    publisher: str = (
        "Projections Central / Projections Managing Partnership, publishing each state "
        "agency's own long-term projections"
    )
    publishes: PublishedMeasures = field(default=PROJECTIONS_CENTRAL_MEASURES)

    @property
    def state_fips(self) -> str:
        return state_fips.fips_for(self.state)

    @property
    def endpoint(self) -> str:
        return (
            f"{projections_central.BASE_URL}/{projections_central.LONG_TERM_PATH}/{self.state_fips}"
        )

    def fetch(self, *, client: httpx.Client | None = None) -> SourceRead:
        read = projections_central.fetch_state_projections(self.state_fips, client=client)
        return SourceRead(
            state=self.state,
            source=self.source,
            publisher=self.publisher,
            endpoint=self.endpoint,
            publishes=self.publishes,
            rows=read.rows,
            rows_published=read.published_rows,
            refused=read.refused,
        )


def source_for(state: str) -> ProjectionSource:
    """The projection source this project reads for ``state``.

    California keeps EDD because EDD publishes more: a median wage, a ten-year openings
    total, regional rows, and the education and training an occupation asks for -- five
    things Projections Central does not carry for anybody. Every other state gets the
    common source, which is what makes this a method rather than one state's site.
    """
    code = (state or "").strip().upper()
    if code == CALIFORNIA:
        return EddProjections()
    # Raises here rather than at fetch time if the code is not a state at all, so the
    # refusal names the code instead of arriving as an unexplained 404 from the endpoint.
    state_fips.fips_for(code)
    return ProjectionsCentralSource(state=code)


_REGION_MEASURE: Final = "regions"


def unpublished_measures_carrying_values(
    occupations: Mapping[str, Mapping[str, Any]], publishes: PublishedMeasures
) -> list[str]:
    """Every way the emitted occupations contradict what their source says it publishes.

    Both directions, because each is a real failure and they fail differently.

    *A measure declared absent that some record carries* means a value reached the dataset
    from somewhere other than the declared source -- the shape that would attach California
    OEWS percentiles to Nevada occupations, which is a correct measurement of the wrong
    population.

    *A measure declared published that no record carries* means the column arrived empty
    and nothing noticed. That is the failure this project keeps meeting from the other end:
    a build that measured nothing, published as a build that found nothing.
    """
    if not occupations:
        return [
            "there are no occupations, so every count below is over nothing and the "
            "declaration cannot be checked against anything."
        ]
    problems: list[str] = []
    declared = publishes.as_dict()
    total = len(occupations)
    for measure, published in sorted(declared.items()):
        if measure == _REGION_MEASURE:
            carried = sum(1 for row in occupations.values() if row.get("regions"))
        else:
            carried = sum(1 for row in occupations.values() if row.get(measure) is not None)
        if not published and carried:
            problems.append(
                f"{carried} of {total} occupations carry {measure}, and the projection "
                f"source declares it publishes no {measure}. A value with no source is "
                "either another state's figure or one this pipeline computed."
            )
        if published and not carried:
            problems.append(
                f"0 of {total} occupations carry {measure}, and the projection source "
                f"declares it publishes {measure}. An empty column read as every "
                "occupation withholding the measure is a build that measured nothing."
            )
    return problems


def measures_absent_from(source: ProjectionSource) -> Sequence[str]:
    """The measures a reader of this state's dataset will find null on every record."""
    return source.publishes.absent
