"""Join California training programs to occupation outlook data and emit the site dataset.

The join is the product: a program's reported WIOA outcomes on one side, and the state's
own projection of what the occupation it feeds actually pays and how many openings it has
on the other. Nothing in California publishes those two facts next to each other today.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Final

from camino.sources import careeronestop, dol_etp, edd_lmi, soc_vintage

DEFAULT_STATE = "CA"

COS_CACHE_DIR = Path("data/raw/cos-cache")
"""Where CareerOneStop responses are kept so a rebuild does not re-ask for unchanged data."""


@dataclass(frozen=True)
class EnrichmentCoverage:
    """How far CareerOneStop enrichment reached, and where each related list came from.

    Published rather than assumed, because the enrichment is optional: a build with no
    credentials emits this block full of zeros instead of omitting it, so a reader can tell
    an unenriched dataset from an enriched one rather than guessing why the pages carry no
    descriptions.
    """

    occupations: int
    enriched: int
    with_description: int
    with_skills: int
    with_bright_outlook: int
    # Which answer each occupation's related list is. Carried as two counts plus the
    # leftover rather than one number and a subtraction, because "we had to fall back to the
    # classification here" is a finding about the data and not an arithmetic remainder.
    related_from_onet: int
    related_from_soc_siblings: int
    without_related: int


@dataclass(frozen=True)
class AggregateMatchCoverage:
    """How much of the program-to-occupation join runs through a published aggregate.

    Published rather than folded into the headline match rate, because "matched" and
    "matched to the broad group above the occupation it trains for" are different claims and
    a reader auditing the 99.5% is entitled to see how many of them are the second kind.

    ``programs_with_education_withheld`` is the cost of the treatment in
    :func:`occupation_summary`, counted rather than estimated: that many program pages carry
    an occupation whose typical-entry credential this pipeline declined to publish because it
    describes a wider population than the program's own occupation.
    """

    programs: int
    recovered_programs: int
    occupation_matches: int
    programs_with_education_withheld: int


@dataclass(frozen=True)
class CohortIntegrityCoverage:
    """How many published figures cannot be read as describing the program they sit on.

    Published rather than quietly handled, because the scale is the finding. A reader who
    is told 103 of California's programs carry a cohort this pipeline will not attribute to
    them can weigh that; a reader shown 3,266 clean-looking pages cannot.

    The three failures are counted separately and not summed into one "bad data" number:
    they have different causes, different remedies in the interface, and only two of them
    stop a figure being comparable. ``not_attributable`` is the union of those two, carried
    explicitly rather than left to a reader to derive from an overlap they cannot see.
    """

    programs_with_cohort_counts: int
    # 1. One cohort filed against several of a provider's programs.
    shared_cohorts: int
    shared_cohort_groups: int
    largest_shared_cohort: int
    # 2. A record whose own counts disagree about the population they describe. Counted per
    # violation and as a union, since the two overlap heavily: every program reporting more
    # completers than entrants also reports more exiters than entrants.
    exited_exceeds_served: int
    completed_exceeds_served: int
    internally_contradictory: int
    # 3. Cohorts too large to be one program, at a provider filing several such.
    oversized_for_one_program: int
    oversized_providers: int
    not_attributable: int


@dataclass
class CoverageReport:
    """Honest accounting of what the data does and does not cover.

    Published alongside the dataset. A tool that hides its own gaps is worse than the
    portal it replaces, and the gaps here are a finding in their own right.
    """

    snapshot_date: str
    total_programs: int
    programs_with_any_outcome: int
    programs_with_median_earnings: int
    programs_with_employment_rate: int
    programs_with_completion_rate: int
    programs_with_cost: int
    programs_with_soc: int
    programs_matched_to_occupation: int
    # Of those matches, the ones reached through a broader published occupation rather than
    # the program's own SOC code. Carried so the headline match rate can be read honestly.
    aggregate_matches: AggregateMatchCoverage
    distinct_providers: int
    distinct_occupations_matched: int
    occupation_rows_loaded: int
    # Geography. `programs_without_area` is carried as its own number rather than left to
    # be subtracted, because "we declined to place this program" is a published finding
    # about the dataset and not an arithmetic leftover.
    programs_mapped_to_area: int
    programs_without_area: int
    programs_with_regional_projection: int
    # How many outcome figures this build declines to attribute to the program they sit on.
    cohort_integrity: CohortIntegrityCoverage
    # Occupation-side coverage from CareerOneStop (D6). Zeroed, not absent, when the build
    # ran without credentials.
    enrichment: EnrichmentCoverage

    @property
    def outcome_coverage_pct(self) -> float:
        return self._pct(self.programs_with_any_outcome)

    @property
    def occupation_match_pct(self) -> float:
        return self._pct(self.programs_matched_to_occupation)

    @property
    def area_match_pct(self) -> float:
        return self._pct(self.programs_mapped_to_area)

    def _pct(self, numerator: int) -> float:
        return round(100.0 * numerator / self.total_programs, 1) if self.total_programs else 0.0


PEER_MEASURES = ("completion_rate", "employment_rate_q2", "median_earnings")


def peer_medians(payloads: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Median of each outcome across the California programs that reported it.

    This replaced a comparison against DOL's published statewide aggregate, which turned out
    not to be the same statistic: DOL reports 27% employed at two quarters, while the median
    reporting California program reports 69%. Comparing one to the other made 91% of programs
    read as "above the California average", which flatters nearly everyone and tells a reader
    nothing.

    A median over the identical population, measured the identical way, supports the claim
    the interface actually wants to make: is this program better or worse than the typical
    California program that reported the same number? The count is carried alongside so the
    page can say how many programs the comparison rests on.

    Programs whose cohort this build will not attribute to them are left out of the median
    entirely -- see :class:`camino.sources.dol_etp.CohortIntegrity`. Including them would let
    one institution-level filing vote eleven times, once per program row it was stamped on,
    which is the same misattribution the flag exists to stop, laundered into the yardstick
    every other program is then measured against. ``excluded_not_attributable`` publishes how
    many were dropped, so the median can be audited rather than taken on trust.
    """
    summary: dict[str, dict[str, Any]] = {}
    attributable = [p for p in payloads if p["outcomes"]["cohort"]["attributable"]]
    for measure in PEER_MEASURES:
        values = sorted(
            payload["outcomes"][measure]
            for payload in attributable
            if payload["outcomes"].get(measure) is not None
        )
        reported = sum(1 for p in payloads if p["outcomes"].get(measure) is not None)
        summary[measure] = {
            "median": _median(values),
            "reporting": len(values),
            "excluded_not_attributable": reported - len(values),
        }
    return summary


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return (values[middle - 1] + values[middle]) / 2


def detailed_soc_codes(projections: Iterable[edd_lmi.OccupationProjection]) -> list[str]:
    """The SOC codes this build will publish an occupation record for.

    The same rows :func:`index_occupations` keeps, in the order EDD published them. Exposed
    so enrichment can be fetched for exactly the occupations that will exist, and no others:
    asking a public API about occupations we are going to discard would be rude.
    """
    codes: dict[str, None] = {}
    for row in projections:
        if row.soc_code and row.is_detailed_occupation and row.is_statewide:
            codes[row.soc_code] = None
    return list(codes)


def fetch_enrichment(
    soc_codes: Iterable[str],
    *,
    state: str = DEFAULT_STATE,
    cache_dir: Path | None = COS_CACHE_DIR,
) -> dict[str, careeronestop.OccupationEnrichment]:
    """Look up CareerOneStop enrichment for each occupation, keyed by SOC.

    Returns an empty mapping when no credentials are configured. That is the CI case and it
    is not an error: the build then emits exactly what it emitted before this source was
    wired in, with the enrichment fields present and empty. Occupations the API has no entry
    for are simply absent from the result for the same reason -- a missing description is a
    gap in a page, never a failed build.

    Responses are cached on disk, so a rebuild with a warm cache asks the network only about
    occupations it has not seen before.
    """
    creds = careeronestop.credentials()
    if creds is None:
        return {}
    _, token = creds

    found: dict[str, careeronestop.OccupationEnrichment] = {}
    with careeronestop.build_client(token) as http:
        for soc_code in soc_codes:
            enrichment = careeronestop.fetch_occupation(
                soc_code, state=state, client=http, cache_dir=cache_dir
            )
            if enrichment is not None:
                found[soc_code] = enrichment
    return found


def index_occupations(
    projections: list[edd_lmi.OccupationProjection],
    *,
    enrichment: Mapping[str, careeronestop.OccupationEnrichment] | None = None,
) -> dict[str, dict[str, Any]]:
    """Index statewide detailed-SOC projections by SOC code.

    Regional rows are retained under ``regions`` so a program can later be shown wages for
    the area it is actually in, but the statewide row is the default because a program's
    graduates do not necessarily work in the county where they trained.

    ``enrichment`` is optional. Passing none is a supported build, not a degraded one: every
    occupation still carries every enrichment key, empty.
    """
    statewide: dict[str, dict[str, Any]] = {}
    regional: dict[str, list[dict[str, Any]]] = {}

    for row in projections:
        if not row.soc_code or not row.is_detailed_occupation:
            continue
        payload = {
            "soc_code": row.soc_code,
            "title": row.title,
            "period": row.period,
            "median_annual_wage": row.median_annual_wage,
            "median_hourly_wage": row.median_hourly_wage,
            "total_job_openings": row.total_job_openings,
            "percent_change": row.percent_change,
            "numeric_change": row.numeric_change,
            "base_employment": row.base_employment,
            "projected_employment": row.projected_employment,
            "entry_level_education": row.entry_level_education,
            "work_experience": row.work_experience,
            "job_training": row.job_training,
        }
        if row.is_statewide:
            statewide[row.soc_code] = payload
        else:
            regional.setdefault(row.soc_code, []).append(
                {"area_type": row.area_type, "area_name": row.area_name, **payload}
            )

    for soc_code, occupation in statewide.items():
        occupation["regions"] = regional.get(soc_code, [])

    _attach_enrichment(statewide, enrichment or {})
    _attach_related(statewide)
    return statewide


def _attach_enrichment(
    occupations: dict[str, dict[str, Any]],
    enrichment: Mapping[str, careeronestop.OccupationEnrichment],
) -> None:
    """Attach CareerOneStop's description, skills, Bright Outlook and related list.

    The keys are always written, so nobody downstream has to tell "this build had no
    credentials" from "this record predates the field". An occupation the API has no entry
    for carries a null description and empty lists: absence, not a blank claim.

    ``related_onet`` keeps only occupations EDD also projects. O*NET relates work to work
    without regard to what California publishes, and an occupation with no projection has no
    page to open, no wage to show and no opening count to compare -- it would render as a
    dead link. Filtering here rather than at the point of use means nothing downstream can
    reintroduce one.

    A skill importance the API did not rate stays null. Zero is a rating, and asserting one
    this project was never given would be an invention.
    """
    for soc_code, occupation in occupations.items():
        found = enrichment.get(soc_code)
        occupation["description"] = found.description if found is not None else None
        occupation["skills"] = (
            [{"name": skill.name, "importance": skill.importance} for skill in found.skills]
            if found is not None
            else []
        )
        occupation["related_onet"] = _published_related(occupations, soc_code, found)
        occupation["bright_outlook"] = found.bright_outlook if found is not None else None


def _published_related(
    occupations: Mapping[str, dict[str, Any]],
    soc_code: str,
    found: careeronestop.OccupationEnrichment | None,
) -> list[dict[str, Any]]:
    """O*NET's related occupations, less the ones this dataset cannot open a page for.

    O*NET's order is kept: it is a relevance ranking by the source that made the claim, and
    re-sorting it would quietly restate someone else's judgement as ours. Two O*NET
    specialisations can collapse onto the same six-digit SOC, so the first mention wins.
    """
    if found is None:
        return []
    titles: dict[str, str] = {}
    for related_soc, title in found.related:
        if related_soc != soc_code and related_soc in occupations:
            titles.setdefault(related_soc, title)
    return [{"soc_code": code, "title": title} for code, title in titles.items()]


RELATED_LIMIT = 6

RELATED_SOURCE_ONET = "onet"
"""O*NET's own related-occupation list: work judged similar to this work."""

RELATED_SOURCE_SOC_SIBLINGS = "soc_major_group"
"""Occupations sharing this one's SOC major group: adjacent by classification, not by task."""


def _attach_related(occupations: dict[str, dict[str, Any]]) -> None:
    """Attach a related-occupation list, and record which of the two answers it is.

    O*NET's list is preferred wherever it survives, because it reflects an assessment of the
    work itself -- what a person doing this job could plausibly do instead. The SOC fallback
    is a weaker claim: the first two digits of a SOC code are its major group, so "29-1141
    Registered Nurses" and "29-2061 Licensed Practical Nurses" are adjacent by the
    classification's own definition, which is a statement about filing, not about tasks.
    Siblings are ranked by projected openings, since the useful question standing on an
    occupation page is "what nearby work is actually hiring".

    The two are never merged. A list padded from the second source would leave the page
    unable to say what any given row means, so an occupation gets one source or the other
    and ``related_source`` names it -- ``null`` when there was no list to be had from either.
    """
    by_group: dict[str, list[str]] = {}
    for soc_code in occupations:
        by_group.setdefault(soc_code[:2], []).append(soc_code)

    for soc_code, occupation in occupations.items():
        from_onet = [occupations[entry["soc_code"]] for entry in occupation["related_onet"]]
        if from_onet:
            chosen = from_onet
            source = RELATED_SOURCE_ONET
        else:
            chosen = _soc_siblings(occupations, by_group, soc_code)
            source = RELATED_SOURCE_SOC_SIBLINGS
        occupation["related"] = [_related_row(other) for other in chosen[:RELATED_LIMIT]]
        occupation["related_source"] = source if occupation["related"] else None


def _soc_siblings(
    occupations: Mapping[str, dict[str, Any]],
    by_group: Mapping[str, list[str]],
    soc_code: str,
) -> list[dict[str, Any]]:
    siblings = [occupations[other] for other in by_group.get(soc_code[:2], []) if other != soc_code]
    # `or -1` would fold a reported zero openings into the same bucket as unreported.
    # Nothing has zero openings today, but this is the exact confusion the project
    # exists to avoid, and it has no business sitting inside a sort key.
    siblings.sort(
        key=lambda o: o["total_job_openings"] if o.get("total_job_openings") is not None else -1,
        reverse=True,
    )
    return siblings


def _related_row(occupation: Mapping[str, Any]) -> dict[str, Any]:
    """One related occupation, described by this dataset's own figures for it.

    The title is EDD's rather than O*NET's even when O*NET supplied the relationship, so the
    link text matches the heading of the page it opens.
    """
    return {
        "soc_code": occupation["soc_code"],
        "title": occupation["title"],
        "median_annual_wage": occupation["median_annual_wage"],
        "total_job_openings": occupation["total_job_openings"],
        "percent_change": occupation["percent_change"],
    }


def enrichment_coverage(occupations: Mapping[str, dict[str, Any]]) -> EnrichmentCoverage:
    """Count what the enrichment reached, from the emitted records rather than the fetch.

    Counting the records is the honest version: it measures what a reader will actually
    find on the pages, not how many API responses came back.
    """
    records = list(occupations.values())
    sources = Counter(record["related_source"] for record in records)
    return EnrichmentCoverage(
        occupations=len(records),
        enriched=sum(1 for record in records if _is_enriched(record)),
        with_description=sum(1 for record in records if record["description"] is not None),
        with_skills=sum(1 for record in records if record["skills"]),
        with_bright_outlook=sum(1 for record in records if record["bright_outlook"] is not None),
        related_from_onet=sources[RELATED_SOURCE_ONET],
        related_from_soc_siblings=sources[RELATED_SOURCE_SOC_SIBLINGS],
        without_related=sources[None],
    )


def _is_enriched(record: Mapping[str, Any]) -> bool:
    return (
        record["description"] is not None
        or bool(record["skills"])
        or bool(record["related_onet"])
        or record["bright_outlook"] is not None
    )


MATCH_EXACT: Final = "exact"
"""The program's own SOC code is one EDD publishes, so the figures are that occupation's.

The other values ``OccupationMatch.kind`` can take are the two ``SocAggregation.kind``
values, and both mean something weaker: the figures belong to a larger published occupation
that *contains* the one the program trains for.
"""


@dataclass(frozen=True)
class OccupationMatch:
    """One occupation a program feeds, and how the join reached it.

    ``program_soc_codes`` holds the program's own codes that landed here, plural because two
    of them can resolve to one aggregate: a home health aide programme tagged both 31-1121
    and 31-1122 gets a single 31-1120 row, and this is what says why it is single.
    """

    soc_code: str
    kind: str
    program_soc_codes: tuple[str, ...]

    @property
    def is_aggregate(self) -> bool:
        """True when the figures describe a population wider than the program's occupation."""
        return self.kind != MATCH_EXACT


def match_occupations(
    soc_codes: Iterable[str], occupations: Mapping[str, Any]
) -> list[OccupationMatch]:
    """Resolve a program's SOC codes to occupations this dataset can actually show.

    A code EDD publishes matches itself. A code EDD publishes only inside a larger occupation
    matches that aggregate, on the containment argument cited row by row in
    :mod:`camino.sources.soc_vintage` -- without it, 61 California programs have no
    occupation panel at all, and 74 more are missing one of theirs. A code with neither is
    dropped rather than guessed at.

    The feed's order is kept, since it is the provider's own priority order, and a target
    appears once however many of the program's codes reached it. Where one code matches a
    published occupation exactly and another reaches the same occupation only as an
    aggregate, the exact match wins and the row is labelled ``exact``: DOL naming the
    published code itself is a stronger claim than one this pipeline derived, and it is not
    this pipeline's to weaken.
    """
    order: list[str] = []
    kinds: dict[str, str] = {}
    sources: dict[str, list[str]] = {}

    for code in soc_codes:
        target = soc_vintage.resolve_published_soc(code, occupations)
        if target is None:
            continue
        # An aggregation row only describes this match when it is the row that produced it.
        # A code EDD publishes under its own name resolves to itself even if it also appears
        # as a member of some group, and that is an exact match.
        aggregation = soc_vintage.aggregation_for(code)
        kind = (
            aggregation.kind
            if aggregation is not None and aggregation.target == target
            else MATCH_EXACT
        )
        if target not in kinds:
            order.append(target)
            kinds[target] = kind
        elif kind == MATCH_EXACT:
            kinds[target] = kind
        contributing = sources.setdefault(target, [])
        if code not in contributing:
            contributing.append(code)

    return [
        OccupationMatch(soc_code=code, kind=kinds[code], program_soc_codes=tuple(sources[code]))
        for code in order
    ]


OCCUPATION_SUMMARY_FIELDS = (
    "soc_code",
    "title",
    "median_annual_wage",
    "total_job_openings",
    "percent_change",
    "entry_level_education",
)


REGION_PROJECTION_FIELDS = (
    "median_annual_wage",
    "median_hourly_wage",
    "total_job_openings",
    "percent_change",
)

AREA_MATCH_PRINCIPAL_CITY = "principal_city"
"""How an area was decided. Emitted so a reader can audit the claim rather than trust it."""


def regional_projection(
    occupation: Mapping[str, Any], area_name: str | None
) -> dict[str, Any] | None:
    """The occupation's own row for one EDD area, or None when EDD published no such row.

    Two different absences reach the page as null and must not be conflated with each
    other or with zero:

    * ``area_name`` is None -- this program's city could not be placed in an EDD area, so
      no regional figure is claimed for any of its occupations.
    * ``area_name`` is set but the occupation has no row there -- EDD publishes a great
      many occupations statewide and not in every small area.

    The program-level ``region`` block distinguishes them: it is null in the first case and
    populated in the second. Measures inside a row that does exist may themselves be null;
    ``_to_wage`` upstream already maps EDD's literal ``$0`` placeholder to null, and
    nothing here refills it.
    """
    if area_name is None:
        return None
    for region in occupation.get("regions", []):
        if region.get("area_name") == area_name:
            return {
                "area_name": area_name,
                "area_type": region.get("area_type"),
                **{field: region.get(field) for field in REGION_PROJECTION_FIELDS},
            }
    return None


def occupation_summary(
    occupation: dict[str, Any], match: OccupationMatch, area_name: str | None = None
) -> dict[str, Any]:
    """Slim projection of an occupation for embedding in a program record.

    Programs reference occupations by SOC rather than carrying a copy: the full record,
    including every regional wage row, lives once in ``occupations.json``. Embedding it
    per-program inflated the dataset by two orders of magnitude, which matters because this
    is meant to ship as static files to phones.

    The top-level figures stay statewide (decision D4: a program's graduates do not
    necessarily work in the county where they trained). ``region`` carries the one area row
    that applies to the program being built, so the page can show both and say which is
    which -- a Fresno program's occupation is not well described by a statewide median that
    a Bay Area concentration has pulled upward.

    ``match`` says how the join reached this occupation, and is never omitted: an exact match
    and an aggregate one look identical once the figures are in hand, and a consumer that
    cannot tell them apart will present a broad group's numbers as the occupation's own.

    **``entry_level_education`` is dropped on an aggregate match.** The other figures survive
    because a median wage or an opening count over a wider population is still an estimate of
    a population the trainee belongs to -- approximate, labelled, and the only one California
    publishes for those workers. The typical-entry credential is not that kind of figure. It
    is a single category BLS assigns to the whole aggregate, so on a union of occupations with
    different credentials it is not an approximation of the member's answer, it is a different
    answer: 21-1018 reads "Master's degree" from its mental-health-counselor half and would
    land on community-college substance-use-counseling certificates, and 29-2010 reads
    "Bachelor's degree" from its technologist half and would land on associate-level
    phlebotomy and MLT programs. Telling someone they need a degree they do not need, for the
    job they are training for right now, is the same class of error as rendering a suppressed
    measure as zero, and it is worse than saying nothing.

    The rule is mechanical -- every aggregate match, not the ones judged wrong. Deciding
    case by case which aggregate's credential happens to fit a given program is precisely the
    similarity judgement :mod:`camino.sources.soc_vintage` refuses to make, and it would put
    that judgement somewhere nobody could audit it.

    Two absences would otherwise reach the page as the same null, so
    ``match.entry_level_education_withheld`` separates them: true means EDD published a
    credential for the aggregate and this pipeline declined to attach it to the program,
    false means there was none to publish. Consumers must not treat the withheld case as
    "the provider did not report it".
    """
    summary = {key: occupation.get(key) for key in OCCUPATION_SUMMARY_FIELDS}
    withheld = match.is_aggregate and summary["entry_level_education"] is not None
    if withheld:
        summary["entry_level_education"] = None
    summary["match"] = {
        "kind": match.kind,
        # The program's own codes, so the claim can be audited against the cited table
        # rather than taken on trust.
        "program_soc_codes": list(match.program_soc_codes),
        "entry_level_education_withheld": withheld,
    }
    summary["region"] = regional_projection(occupation, area_name)
    return summary


def area_for_city(
    city: str | None, city_areas: Mapping[str, edd_lmi.ProjectionArea] | None
) -> edd_lmi.ProjectionArea | None:
    """The EDD area whose published title names this city, or None.

    Exact match against EDD's own principal-city names, and nothing else. A city EDD does
    not name gets no region at all: the nearest metro's wages would render identically to a
    correct answer, so a reader could not tell a fact from a guess, and roughly half of
    California's programs sit in cities no CBSA title mentions. Saying nothing about them
    is the only version of this that stays honest.
    """
    if city_areas is None:
        return None
    key = edd_lmi.normalise_place(city)
    if key is None:
        return None
    return city_areas.get(key)


def program_payload(
    program: dol_etp.Program,
    occupations: dict[str, dict[str, Any]],
    city_areas: Mapping[str, edd_lmi.ProjectionArea] | None = None,
    cohort: dol_etp.CohortIntegrity | None = None,
) -> dict[str, Any]:
    """One program record, with its outcomes labelled by who they actually describe.

    ``cohort`` comes from :func:`camino.sources.dol_etp.cohort_integrity` run over the whole
    snapshot, because a cohort republished across a provider's programs is invisible from
    inside any one of them. Omitting it judges the program against itself alone, which is a
    real answer -- the contradiction checks still run -- and is what a caller holding a
    single record can honestly say.
    """
    integrity = (
        cohort
        if cohort is not None
        else dol_etp.cohort_integrity([dol_etp.CohortFiling.of(program)])[0]
    )
    area = area_for_city(program.city, city_areas)
    area_name = None if area is None else area.area_name
    matched = [
        occupation_summary(occupations[match.soc_code], match, area_name)
        for match in match_occupations(program.soc_codes, occupations)
    ]
    return {
        "uuid": program.uuid,
        "provider_name": program.provider_name,
        "program_name": program.program_name,
        "description": program.description,
        "program_format": program.program_format,
        "program_url": program.program_url,
        "entity_type": program.entity_type,
        "cip_code": program.cip_code,
        "soc_codes": list(program.soc_codes),
        "location": {
            "city": program.city,
            "state": program.state,
            "zip": program.zip_code,
            "lat": program.lat,
            "lon": program.lon,
        },
        # Null means this program's city is not one EDD names, so no regional figure is
        # claimed for it anywhere in this record. Not "statewide"; not "unknown region".
        "region": None
        if area is None
        else {
            "area_name": area.area_name,
            "area_short_name": area.short_name,
            "area_type": area.area_type,
            "matched_on": AREA_MATCH_PRINCIPAL_CITY,
        },
        "length": {"weeks": program.length_weeks, "hours": program.length_hours},
        "cost": {
            "tuition": program.cost_tuition,
            "supplies": program.cost_supplies,
            "total_out_of_pocket": program.total_cost,
            # False when a component was suppressed, making the total a floor rather than
            # a total. The UI must say "at least" instead of presenting it as the price.
            "total_is_complete": program.cost_is_complete,
            "wioa_funded_cost": program.cost_wioa,
        },
        # Every field here may legitimately be null, meaning "not reported or suppressed".
        # Consumers must render that distinctly from a reported zero.
        "outcomes": {
            "total_served": program.total_served,
            "total_exited": program.total_exited,
            "total_completed": program.total_completed,
            "completion_rate": program.completed_percent,
            "credentials_earned": program.total_credential,
            "median_earnings": program.median_earnings,
            "employment_rate_q2": program.q2_employment_percent,
            "employed_q2": program.employed_q2,
            "employed_q4": program.employed_q4,
            "reported": program.has_outcomes,
            # Who the counts above describe. `reported` says a figure exists; this says
            # whether it is this program's to be judged on. Never omitted, so "checked and
            # sound" stays distinguishable from "built before the check existed".
            "cohort": integrity.as_dict(),
        },
        "occupations": matched,
    }


def search_entry(program: dict[str, Any]) -> dict[str, Any]:
    """One row of the client-side search index.

    Short keys and only the fields a result card or filter actually needs. Everything else
    is fetched per-program on demand, so the first paint does not cost megabytes on a phone.

    ``a`` carries the program's published EDD area, and only its short name: the full
    ``area_name`` repeats a county gloss ("Fresno MSA (Fresno and Madera Counties)") that a
    filter has no use for, and the gloss is one fetch away on the program page. Measured on
    the 3,266-program build, the field costs 5.1 KB gzipped (178.4 KB to 183.5 KB, +2.8%).
    Interning the 27 distinct names into a lookup table and shipping an integer per row would
    have cost 1.9 KB instead, and was rejected: an integer means nothing without the table, so
    a table that ever slipped out of step with the rows would attribute programs to the wrong
    labour market silently, which is the one failure this dataset is built to refuse. 3.2 KB
    is a cheap price for a row that can be read on its own.

    ``a`` is null for the 1,741 programs whose city EDD does not name. That is a third state,
    not an absence to be tidied away: it is neither "not reported" (the city is known, and
    published in ``c``) nor membership in some residual area. The key is always written so a
    consumer can tell an unplaced program from an index built before this field existed.
    """
    occupations = program["occupations"]
    outcomes = program["outcomes"]

    # A program can feed up to three occupations, and 1,588 of California's 3,266 feed more
    # than one. Reading only the first understated the programs training for declining work
    # by more than half (219 against 518), because the shrinking occupation is frequently
    # not the one listed first. Summarise across all of them.
    changes = [o["percent_change"] for o in occupations if o.get("percent_change") is not None]
    wages = [
        o["median_annual_wage"] for o in occupations if o.get("median_annual_wage") is not None
    ]
    openings = [
        o["total_job_openings"] for o in occupations if o.get("total_job_openings") is not None
    ]
    # The worst outlook among the jobs this trains for: a program is only as safe as its
    # weakest destination, and that is the fact a prospective student needs first.
    worst_change = min(changes) if changes else None
    region = program["region"]
    return {
        "i": program["uuid"],
        "n": program["program_name"],
        "p": program["provider_name"],
        "c": program["location"]["city"],
        # Short name of the EDD labour-market area, or null for "this city is in none of
        # them". Never a nearest-metro guess and never a catch-all bucket.
        "a": None if region is None else region["area_short_name"],
        "$": program["cost"]["total_out_of_pocket"],
        "$partial": not program["cost"]["total_is_complete"],
        "w": program["length"]["weeks"],
        "s": program["soc_codes"],
        # Every occupation this program feeds, not just the first.
        "o": [o.get("title") for o in occupations if o.get("title")],
        # Worst projected outlook across those occupations, so "trains for a shrinking job"
        # is filterable without a second fetch. None stays None: unknown is not flat.
        "g": worst_change,
        # Best wage and most openings available down any of its paths.
        "wage": max(wages) if wages else None,
        "op": max(openings) if openings else None,
        # Headline outcomes, null-preserving.
        "cr": outcomes["completion_rate"],
        "er": outcomes["employment_rate_q2"],
        "me": outcomes["median_earnings"],
        "r": outcomes["reported"],
        # False when the three figures above describe a population wider than this program
        # -- a cohort the provider filed against several of its programs, or one too large
        # to be a single program at a provider filing many such.
        #
        # The values themselves stay, deliberately. Nulling them here would say "not
        # reported", which is false and is the one confusion this dataset refuses to make;
        # dropping the row would hide a real program. So the row is published whole and
        # labelled, and anything that ranks, badges or sorts on `cr`/`er`/`me` has to read
        # this key first.
        "at": outcomes["cohort"]["attributable"],
    }


def area_coverage(
    payloads: list[dict[str, Any]], areas: list[edd_lmi.ProjectionArea]
) -> list[dict[str, Any]]:
    """Every EDD area, what it is made of, and how many programs landed in it.

    Published so the geography can be audited without re-deriving it: a reader can see
    that the three rural Consortium regions received zero programs, and why (their names
    are region coinages, not city-titled CBSAs, so no program city can match one).
    """
    placed = Counter(
        payload["region"]["area_name"] for payload in payloads if payload["region"] is not None
    )
    return [
        {
            "area_name": area.area_name,
            "area_type": area.area_type,
            "principal_cities": list(area.principal_cities),
            "counties": list(area.counties),
            # A genuine zero: we counted, and nothing mapped here. Unlike every measure in
            # this dataset, this number is ours, so it can be zero without ambiguity.
            "programs": placed.get(area.area_name, 0),
        }
        for area in areas
    ]


def aggregate_match_coverage(payloads: list[dict[str, Any]]) -> AggregateMatchCoverage:
    """Count the aggregate half of the join, from the emitted records rather than the table.

    Counted the same way :func:`enrichment_coverage` is, and for the same reason: this
    measures what a reader will actually find on the pages, not what the mapping table would
    have allowed. ``recovered_programs`` is the subset with no exact match at all -- programs
    that would show no occupation whatsoever without the aggregation, as distinct from the
    ones that merely gained a row.
    """
    programs = 0
    recovered = 0
    matches = 0
    with_education_withheld = 0
    for payload in payloads:
        occupations = payload["occupations"]
        aggregates = [o for o in occupations if o["match"]["kind"] != MATCH_EXACT]
        if not aggregates:
            continue
        programs += 1
        matches += len(aggregates)
        if len(aggregates) == len(occupations):
            recovered += 1
        if any(o["match"]["entry_level_education_withheld"] for o in aggregates):
            with_education_withheld += 1
    return AggregateMatchCoverage(
        programs=programs,
        recovered_programs=recovered,
        occupation_matches=matches,
        programs_with_education_withheld=with_education_withheld,
    )


def cohort_integrity_coverage(payloads: list[dict[str, Any]]) -> CohortIntegrityCoverage:
    """Count the marked cohorts, from the emitted records rather than the checks.

    Same discipline as :func:`enrichment_coverage` and :func:`aggregate_match_coverage`:
    counting what shipped is the only count that describes what a reader will meet.

    ``shared_cohort_groups`` is recovered from the sibling counts rather than by regrouping
    the records. A group of *n* programs writes ``n - 1`` on each of its *n* members, so the
    programs carrying a given sibling count always divide exactly by the group size, and the
    arithmetic is a second, independent check on the grouping that produced them.
    """
    cohorts = [payload["outcomes"]["cohort"] for payload in payloads]
    siblings = Counter(
        cohort["shared_with_sibling_programs"]
        for cohort in cohorts
        if cohort["shared_with_sibling_programs"] is not None
    )
    exited_over = sum(1 for cohort in cohorts if cohort["exited_exceeds_served"])
    completed_over = sum(1 for cohort in cohorts if cohort["completed_exceeds_served"])
    return CohortIntegrityCoverage(
        programs_with_cohort_counts=sum(
            1
            for payload in payloads
            if any(
                payload["outcomes"][measure] is not None
                for measure in ("total_served", "total_exited", "total_completed")
            )
        ),
        shared_cohorts=sum(siblings.values()),
        shared_cohort_groups=sum(count // (n + 1) for n, count in siblings.items()),
        # A genuine zero when nothing is shared: this number is ours, counted, not reported.
        largest_shared_cohort=max(siblings, default=-1) + 1 if siblings else 0,
        exited_exceeds_served=exited_over,
        completed_exceeds_served=completed_over,
        internally_contradictory=sum(
            1 for cohort in cohorts if not cohort["internally_consistent"]
        ),
        oversized_for_one_program=sum(
            1 for cohort in cohorts if cohort["oversized_for_one_program"]
        ),
        oversized_providers=len(
            {
                dol_etp.normalise_provider(payload["provider_name"])
                for payload in payloads
                if payload["outcomes"]["cohort"]["oversized_for_one_program"]
            }
        ),
        not_attributable=sum(1 for cohort in cohorts if not cohort["attributable"]),
    )


def unmapped_cities(payloads: list[dict[str, Any]]) -> dict[str, int]:
    """Cities this build declined to place, with how many programs each cost.

    The refusals are the interesting half of the coverage story, so they ship rather than
    being summarised away: whoever reads this can see exactly which places would be
    recovered by adding a documented address-to-county source, and how much each is worth.
    """
    counts = Counter(
        payload["location"]["city"]
        for payload in payloads
        if payload["region"] is None and payload["location"]["city"] is not None
    )
    return {city: count for city, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))}


def _fresh_dir(path: Path) -> Path:
    """Empty a shard directory before rewriting it.

    Without this, shards from an earlier build survive alongside the new ones. The site
    pre-renders a page per shard file, so a small fixture build was still emitting pages for
    thousands of stale programs -- pages carrying data no longer in the dataset.
    """
    if path.exists():
        for stale in path.glob("*.json"):
            stale.unlink()
    path.mkdir(parents=True, exist_ok=True)
    return path


def emit_site_bundle(
    payloads: list[dict[str, Any]],
    occupations: dict[str, dict[str, Any]],
    *,
    output_dir: Path,
    snapshot: str,
    state: str,
) -> None:
    """Write the sharded artifacts a static front end consumes.

    One slim index for search and filtering, plus per-program and per-occupation detail
    fetched only when something is opened.
    """
    (output_dir / "search-index.json").write_text(
        json.dumps(
            {
                "snapshot_date": snapshot,
                "state": state,
                "programs": [search_entry(p) for p in payloads],
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )

    program_dir = _fresh_dir(output_dir / "programs")
    for payload in payloads:
        if payload["uuid"]:
            (program_dir / f"{payload['uuid']}.json").write_text(
                json.dumps(payload, separators=(",", ":")), encoding="utf-8"
            )

    occupation_dir = _fresh_dir(output_dir / "occupations")
    for soc_code, occupation in occupations.items():
        (occupation_dir / f"{soc_code}.json").write_text(
            json.dumps(occupation, separators=(",", ":")), encoding="utf-8"
        )


def _attach_cohort_integrity(payloads: list[dict[str, Any]]) -> None:
    """Re-derive every record's cohort verdict from the records themselves, in place.

    The offline build reads a committed snapshot of this pipeline's own output, so the
    verdicts could in principle be trusted as they were written. They are recomputed anyway,
    for two reasons. A fixture predating the check carries no verdict at all, and defaulting
    one in would publish "we checked this and it was fine" about a record nothing had
    checked. And a fixture is a *sample*: the two cross-program checks are relative to the
    population they run over, so verdicts copied from a 3,266-program build would assert
    things about a 60-program one that its own contents do not support.

    The rule is the same rule over the same four fields, so on a full snapshot this
    reproduces what :func:`build` wrote.
    """
    for payload, verdict in zip(
        payloads,
        dol_etp.cohort_integrity(
            [
                dol_etp.CohortFiling(
                    provider_name=payload["provider_name"],
                    total_served=payload["outcomes"]["total_served"],
                    total_exited=payload["outcomes"]["total_exited"],
                    total_completed=payload["outcomes"]["total_completed"],
                )
                for payload in payloads
            ]
        ),
        strict=True,
    ):
        payload["outcomes"]["cohort"] = verdict.as_dict()


def build_offline(fixture_dir: Path, *, output_dir: Path | None = None) -> int:
    """Emit the site bundle from a committed fixture instead of the live sources.

    CI uses this. The upstream DOL endpoint refuses requests from GitHub Actions runners,
    and a build that depends on a third party being reachable fails for reasons that have
    nothing to do with the change under test. This runs the same emit code as a real build,
    so the shape of what the site consumes is exercised either way.
    """
    output_dir = output_dir or Path("web/public/data")
    output_dir.mkdir(parents=True, exist_ok=True)

    programs_doc = json.loads((fixture_dir / "programs.json").read_text(encoding="utf-8"))
    occupations_doc = json.loads((fixture_dir / "occupations.json").read_text(encoding="utf-8"))
    coverage = json.loads((fixture_dir / "coverage.json").read_text(encoding="utf-8"))

    payloads = programs_doc["programs"]
    occupations = occupations_doc["occupations"]
    snapshot = programs_doc["snapshot_date"]
    _attach_cohort_integrity(payloads)
    coverage["cohort_integrity"] = asdict(cohort_integrity_coverage(payloads))
    coverage["peer_medians"] = peer_medians(payloads)

    for name, document in (
        ("programs.json", programs_doc),
        ("occupations.json", occupations_doc),
        ("coverage.json", coverage),
    ):
        (output_dir / name).write_text(json.dumps(document, indent=1), encoding="utf-8")

    emit_site_bundle(
        payloads,
        occupations,
        output_dir=output_dir,
        snapshot=snapshot,
        state=programs_doc.get("state", DEFAULT_STATE),
    )
    return len(payloads)


def build(
    state: str = DEFAULT_STATE,
    *,
    output_dir: Path | None = None,
    snapshot: str | None = None,
) -> CoverageReport:
    output_dir = output_dir or Path("data/processed")
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot = snapshot or date.today().isoformat()

    programs = list(dol_etp.fetch_programs(state))
    benchmark = dol_etp.fetch_state_benchmark(state)
    projections = edd_lmi.fetch_projections()
    # Enrichment first, so the occupation index is built once with it rather than rewritten.
    # Empty when no credentials are configured, which is a complete build, not a failed one.
    enrichment = fetch_enrichment(
        detailed_soc_codes(projections), state=state, cache_dir=COS_CACHE_DIR
    )
    occupations = index_occupations(projections, enrichment=enrichment)
    areas = edd_lmi.area_definitions(projections)
    city_areas = edd_lmi.principal_city_areas(areas)

    # Judged over the whole snapshot before any record is built: a cohort republished across
    # a provider's programs, and a provider filing many impossible ones, are both invisible
    # from inside a single row.
    integrity = dol_etp.cohort_integrity([dol_etp.CohortFiling.of(p) for p in programs])
    payloads = [
        program_payload(p, occupations, city_areas, cohort=c)
        for p, c in zip(programs, integrity, strict=True)
    ]
    # Counted from the occupations actually attached, not from the raw SOC codes: after the
    # aggregation those are no longer the same set, and the emitted records are the ones a
    # reader can check.
    matched_socs = {o["soc_code"] for p in payloads for o in p["occupations"]}
    mapped_to_area = sum(1 for p in payloads if p["region"] is not None)

    report = CoverageReport(
        snapshot_date=snapshot,
        total_programs=len(programs),
        programs_with_any_outcome=sum(1 for p in programs if p.has_outcomes),
        programs_with_median_earnings=sum(1 for p in programs if p.median_earnings is not None),
        programs_with_employment_rate=sum(
            1 for p in programs if p.q2_employment_percent is not None
        ),
        programs_with_completion_rate=sum(1 for p in programs if p.completed_percent is not None),
        programs_with_cost=sum(1 for p in programs if p.total_cost is not None),
        programs_with_soc=sum(1 for p in programs if p.soc_codes),
        programs_matched_to_occupation=sum(1 for p in payloads if p["occupations"]),
        aggregate_matches=aggregate_match_coverage(payloads),
        distinct_providers=len({p.provider_name for p in programs if p.provider_name}),
        distinct_occupations_matched=len(matched_socs),
        occupation_rows_loaded=len(occupations),
        programs_mapped_to_area=mapped_to_area,
        programs_without_area=len(payloads) - mapped_to_area,
        programs_with_regional_projection=sum(
            1 for p in payloads if any(o["region"] is not None for o in p["occupations"])
        ),
        cohort_integrity=cohort_integrity_coverage(payloads),
        enrichment=enrichment_coverage(occupations),
    )

    (output_dir / "programs.json").write_text(
        json.dumps({"snapshot_date": snapshot, "state": state, "programs": payloads}, indent=1),
        encoding="utf-8",
    )
    (output_dir / "occupations.json").write_text(
        json.dumps({"snapshot_date": snapshot, "occupations": occupations}, indent=1),
        encoding="utf-8",
    )
    emit_site_bundle(payloads, occupations, output_dir=output_dir, snapshot=snapshot, state=state)
    (output_dir / "coverage.json").write_text(
        json.dumps(
            asdict(report)
            | {
                "outcome_coverage_pct": report.outcome_coverage_pct,
                "occupation_match_pct": report.occupation_match_pct,
                "area_match_pct": report.area_match_pct,
                "areas": area_coverage(payloads, areas),
                "unmapped_cities": unmapped_cities(payloads),
                # DOL's own statewide aggregate. Kept as published context, but NOT used
                # for per-program comparison: it is computed on a different basis (27%
                # employed against a 69% median among reporting programs).
                "state_benchmark": benchmark.as_dict() if benchmark else None,
                "peer_medians": peer_medians(payloads),
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    return report
