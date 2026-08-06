"""Join California training programs to occupation outlook data and emit the site dataset.

The join is the product: a program's reported WIOA outcomes on one side, and the state's
own projection of what the occupation it feeds actually pays and how many openings it has
on the other. Nothing in California publishes those two facts next to each other today.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Final

from afterward.sources import (
    careeronestop,
    dol_etp,
    edd_lmi,
    link_check,
    local_help,
    onet,
    soc_vintage,
)

DEFAULT_STATE = "CA"

COS_CACHE_DIR = Path("data/raw/cos-cache")
"""Where CareerOneStop responses are kept so a rebuild does not re-ask for unchanged data."""

LINK_CACHE_DIR = Path("data/raw") / link_check.DEFAULT_CACHE_SUBDIR
"""Per-URL link verdicts, kept so a re-run asks only about what has expired."""

LINK_CHECK_PATH = Path("data/interim/link-checks.json")
"""Where ``afterward check-links`` leaves its report and where ``afterward build`` looks for one.

Under ``data/interim`` rather than ``data/processed`` because it is not part of the site
dataset: it is advisory input to the build, produced by a separate, explicitly-invoked step,
and a build that finds nothing here is a complete build."""


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


@dataclass(frozen=True)
class ProviderLinkCoverage:
    """What this build does with the "Provider's website" link on each program page.

    Published because the link is an assertion this project makes on a reader's behalf and
    the federal feed does not maintain it. A reader who is shown fewer links than the dataset
    contains URLs is owed the count and the reason.

    The three-state rule is visible in the shape rather than implied by it.
    ``programs_unchecked`` is its own number and is never folded into ``programs_alive``:
    nothing was established about those links, which is a different fact from establishing
    that they work. ``earliest_check`` and ``latest_check`` are null on a build that read no
    link data, and a null there means "nothing was looked at", never "nothing was wrong".
    """

    programs_with_link: int
    distinct_urls: int
    checked_urls: int
    unchecked_urls: int
    programs_checked: int
    programs_unchecked: int
    # By verdict, counted over program pages rather than URLs, because one dead domain on 126
    # pages is a 126-page problem and a per-URL count would report it as one.
    programs_alive: int
    programs_dead: int
    programs_indeterminate: int
    # What the reader actually gets.
    programs_linked: int
    programs_not_linked: int
    programs_upgraded_to_https: int
    programs_sent_to_front_page: int
    programs_labelled_home_page: int
    earliest_check: str | None
    latest_check: str | None


@dataclass(frozen=True)
class LocalHelpCoverage:
    """How many program pages can name a real office where the funding question is decided.

    ``centers_loaded`` carries the one distinction everything else here depends on. ``None``
    means this build did not read the federal centre directory at all -- no credentials, or
    the endpoint could not be reached -- and every count below it is then a count of a search
    that never happened. ``0`` would be a different claim entirely: that the directory
    answered and California has no job centres in it. The same distinction is written on each
    program record, where a null list means "not looked for" and an empty list means "looked
    for, and none within the radius".

    The program counts are counts of what shipped rather than of what was fetched, in the
    same spirit as :func:`enrichment_coverage`: the only honest measure of this feature is
    how many pages a reader will actually find an address on.

    ``nearest_median_miles`` and ``nearest_farthest_miles`` are straight-line distances and
    ``None`` rather than 0 when nothing could be measured.
    """

    centers_loaded: int | None
    radius_miles: float
    programs_searched: int
    # Programs that could not be searched even though the directory was read, because the
    # federal record gives them no coordinates. Its own number, never folded into
    # "no centre nearby" -- one is a fact about California, the other about a filing.
    programs_not_searched: int
    programs_with_a_center: int
    programs_with_none_within_radius: int
    programs_with_a_comprehensive_center: int
    programs_with_a_center_within_10_miles: int
    nearest_median_miles: float | None
    nearest_farthest_miles: float | None


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
    # What became of the provider links. All-unchecked, not absent, when the build read no
    # link report -- which is the CI case and a complete build.
    provider_links: ProviderLinkCoverage
    # How many pages can name an America's Job Center. Present with a null `centers_loaded`,
    # not absent, when the build had no credentials to read the directory with.
    local_help: LocalHelpCoverage

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
    entirely -- see :class:`afterward.sources.dol_etp.CohortIntegrity`. Including them would let
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


SITE_COVERAGE_KEYS: Final = (
    "snapshot_date",
    "state_benchmark",
    "peer_medians",
    "total_programs",
    "programs_with_any_outcome",
    "programs_with_median_earnings",
    "programs_with_employment_rate",
    "programs_with_completion_rate",
    "programs_matched_to_occupation",
    "distinct_providers",
    "distinct_occupations_matched",
    "outcome_coverage_pct",
    "occupation_match_pct",
)
"""What the site requires ``coverage.json`` to carry. Mirrors ``Coverage`` in web/lib/types.ts.

Kept as an explicit list rather than derived from :class:`CoverageReport`, because the two
answer different questions. The dataclass is what a build happens to publish; this is what a
page will silently lose if it goes missing, and it includes keys -- ``peer_medians``,
``outcome_coverage_pct`` -- that are computed beside the report rather than inside it.
"""

NULLABLE_COVERAGE_KEYS: Final = frozenset({"state_benchmark"})
"""Keys the site types as nullable, where a null is a published finding rather than a gap.

Everything else must carry a value. A null ``total_programs`` is not "we counted nothing";
it is a build that failed to count, rendered as a blank where a number belongs.
"""


def coverage_shape_problems(document: Mapping[str, Any]) -> list[str]:
    """Every way an emitted coverage document falls short of what the site reads from it."""
    problems = [
        f"{key}: {'absent' if key not in document else 'null'}"
        for key in SITE_COVERAGE_KEYS
        if key not in document or (document[key] is None and key not in NULLABLE_COVERAGE_KEYS)
    ]
    peers = document.get("peer_medians")
    if isinstance(peers, Mapping):
        problems += [
            f"peer_medians.{measure}: absent" for measure in PEER_MEASURES if measure not in peers
        ]
    return problems


def check_coverage_shape(document: Mapping[str, Any]) -> None:
    """Refuse to emit a coverage document the site cannot read.

    This exists because of a measured near-miss rather than a hypothetical. A snapshot taken
    before ``state_benchmark`` was written carried no such key, and the program page reads it
    with optional chaining -- so every statewide comparison vanished from all 2,057 outcome
    pages with no error, no warning and no visible difference beyond three absent lines.
    Nothing checked the shape, so nothing said anything.

    The offline path can reach the same state today. It copies a fixture's coverage document
    through wholesale and overwrites four keys, so any key the site needs and the fixture
    predates would go missing exactly that way -- and the committed fixture is already missing
    four the current build emits (``aggregate_matches``, ``areas``, ``unmapped_cities``,
    ``programs_with_regional_projection``), none of which the site happens to read. "Happens
    to" is what this replaces.

    Loud rather than repaired. A default filled in here would publish a number this build did
    not compute, which is the failure it exists to prevent, one level up.
    """
    problems = coverage_shape_problems(document)
    if problems:
        raise ValueError(
            "coverage.json is missing what the site reads from it: "
            + "; ".join(problems)
            + ". Pages would render with those comparisons silently absent rather than fail."
        )


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


ONET_CACHE_DIR = COS_CACHE_DIR

WAGE_SPREAD_PATH = Path("data/interim/oews-statewide.json")


def load_wage_spread(path: Path = WAGE_SPREAD_PATH) -> dict[str, dict[str, Any]]:
    """Read the OEWS statewide percentiles a previous fetch left, or an empty mapping.

    A separate step for the same reason `check-links` is one: the published extract is the
    whole 2009-2026 panel, ~112 MB and 580,790 records, because EDD publishes no per-year
    resource. No build should pay that to learn a set of numbers that changes annually, and a
    build with no file is complete -- the pages then say what they said before, which is the
    median alone.
    """
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    occupations = payload.get("occupations")
    return occupations if isinstance(occupations, dict) else {}


def load_wage_regions(path: Path = WAGE_SPREAD_PATH) -> dict[str, dict[str, Any]]:
    """The same extract's per-area percentiles, keyed by SOC then by published area name.

    Areas are kept under the names OEWS publishes. Those are the strings the projections use
    before their parenthetical county gloss, so joining is an equality test: a vintage that
    renamed an area drops out here rather than being repaired by a prefix or edit-distance
    match, which could attribute one region's wages to another.
    """
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    regions = payload.get("regions")
    return regions if isinstance(regions, dict) else {}


def fetch_spanish_occupations(
    soc_codes: Iterable[str],
    *,
    cache_dir: Path | None = ONET_CACHE_DIR,
) -> dict[str, onet.SpanishOccupation]:
    """Look up each occupation's Spanish record from O*NET's Mi Próximo Paso, keyed by SOC.

    Every program page tells a Spanish reader that occupation titles appear in English
    "because that is the only language the federal and state records publish them in". That
    was true of the sources this build already read and false of the Department of Labor as a
    whole: O*NET publishes the same occupations in Spanish, and this fills the gap rather
    than continuing to explain it.

    Same contract as :func:`fetch_enrichment`. No key is the CI case and is not an error --
    the build then emits what it emitted before, with the field present and null. Mi Próximo
    Paso covers 923 of O*NET's 1,016 occupations, so an occupation with no Spanish record is
    ordinary; it carries null and its page keeps the English title, which is the honest
    outcome rather than a machine translation this project did not make.
    """
    key = onet.api_key()
    if key is None:
        return {}

    found: dict[str, onet.SpanishOccupation] = {}
    with onet.build_client(key) as http:
        for soc_code in soc_codes:
            record = onet.fetch_spanish(onet.onet_code(soc_code), client=http, cache_dir=cache_dir)
            if record is not None:
                found[soc_code] = record
    return found


# --------------------------------------------------------------------------------------
# Provider links
#
# The check is not part of a build and must never become one. It costs ~1,500 HTTP requests
# against small colleges and adult schools, CI has no network at all, and a build that
# depends on a thousand third parties being reachable fails for reasons that have nothing to
# do with the data. So it is a separate command, cached on disk, whose report a later build
# reads if it is there. No report is not an error and not a gap to be filled with a default:
# it means nothing was established, and the build publishes every link exactly as filed.
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class LinkCheckRun:
    """What one explicit link-check pass established, for the operator who invoked it."""

    urls: int
    pages: int
    front_pages_checked: int
    by_verdict: Mapping[link_check.Verdict, int]
    pages_by_verdict: Mapping[link_check.Verdict, int]
    upgradeable_urls: int
    upgradeable_pages: int
    recorded_requests: int
    """HTTP requests these results cost. A cached entry carries the cost of the run that
    made it, so on a warm cache this is a record of the traffic, not of this pass."""
    output_path: Path


def provider_link_pages(payloads: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Each distinct provider URL in a dataset, and how many program pages render it.

    The weighting is the point. 1,016 URLs sit on 1,836 pages and the distribution is
    extremely top-heavy -- one lapsed adult-education domain is on 126 of them -- so a
    per-URL count would describe the wrong problem.
    """
    counts = Counter(url for payload in payloads if (url := payload.get("program_url")) is not None)
    return dict(counts)


def load_link_checks(path: Path | None) -> dict[str, link_check.LinkCheck]:
    """Read a link-check report, or return nothing at all.

    An absent file is the ordinary case and returns an empty mapping, which every consumer
    treats as "unchecked" rather than as any verdict. A file that exists and cannot be read
    raises: an operator pointed the build at it, and silently downgrading a malformed report
    to "nothing was checked" would republish links this project had already established were
    broken.
    """
    if path is None or not path.exists():
        return {}
    return link_check.checks_from_document(json.loads(path.read_text(encoding="utf-8")))


def check_provider_links(
    dataset_dir: Path,
    *,
    output_path: Path = LINK_CHECK_PATH,
    cache_dir: Path | None = LINK_CACHE_DIR,
    max_workers: int = link_check.MAX_WORKERS,
    on_result: Callable[[link_check.LinkCheck], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> LinkCheckRun:
    """Ask every provider URL in an emitted dataset whether it still goes anywhere.

    Two passes over one client. The first reads every distinct ``program_url``. The second
    reads the front page of each host that answered a 404, because "this page is gone" and
    "this provider is gone" are different findings and the first one has a better answer than
    suppression: link the front door instead. The second pass is roughly a tenth the size of
    the first.

    The URLs come from a dataset this pipeline has already emitted rather than from a fresh
    fetch, so checking links costs DOL nothing and can be run against exactly what is
    published. Run ``afterward build`` first; run it again afterwards to pick the report up.

    ``sleep`` is injectable for the reason
    :func:`afterward.sources.link_check.check_urls` makes it injectable: the pacing between
    requests to one provider is a property worth testing and not worth waiting for.
    """
    programs_path = dataset_dir / "programs.json"
    if not programs_path.exists():
        raise FileNotFoundError(
            f"no dataset at {programs_path}. Run `afterward build` first: the check reads the "
            "URLs from an emitted dataset rather than re-fetching them."
        )
    document = json.loads(programs_path.read_text(encoding="utf-8"))
    pages = provider_link_pages(document["programs"])

    cache = link_check.LinkCheckCache(cache_dir)
    with link_check.build_client(max_workers=max_workers) as client:
        checks = link_check.check_urls(
            pages,
            client=client,
            cache=cache,
            max_workers=max_workers,
            on_result=on_result,
            sleep=sleep,
        )
        front_pages = link_check.check_urls(
            link_check.front_page_candidates(checks),
            client=client,
            cache=cache,
            max_workers=max_workers,
            on_result=on_result,
            sleep=sleep,
        )

    # Front pages are merged into one mapping because that is what `decide` reads, but they
    # are summarised out of the headline counts: they are evidence about a substitution, not
    # links this dataset publishes, and counting them would inflate every figure in the
    # report that motivated this work.
    merged = {**checks, **front_pages}
    summary = link_check.summarise(checks, pages_per_url=pages)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(link_check.checks_document(merged), indent=1), encoding="utf-8"
    )
    return LinkCheckRun(
        urls=summary.urls_checked,
        pages=summary.pages_affected,
        front_pages_checked=len(front_pages),
        by_verdict=summary.by_verdict,
        pages_by_verdict=summary.pages_by_verdict,
        upgradeable_urls=summary.upgradeable_urls,
        upgradeable_pages=summary.upgradeable_pages,
        recorded_requests=sum(check.attempts for check in merged.values()),
        output_path=output_path,
    )


def provider_link(
    url: str | None, checks: Mapping[str, link_check.LinkCheck]
) -> dict[str, Any] | None:
    """The provider-link block for one program, or ``None`` when it has no URL at all.

    Null means this program filed no provider website, which is 1,430 of California's 3,266
    programs and has nothing to do with the check. It is not "we suppressed it": that case is
    a populated block whose ``href`` is null and whose ``notice`` says on what date we failed
    to reach the page.
    """
    decision = link_check.decide(checks, url)
    return None if decision is None else decision.as_dict()


def _attach_provider_links(
    payloads: list[dict[str, Any]], checks: Mapping[str, link_check.LinkCheck]
) -> None:
    """Write every record's link decision, in place.

    Always written, even with no link data, for the same reason the cohort verdict always is:
    a consumer must be able to tell "checked, and there is nothing to say" from "built before
    this existed". With no link data every block reads unchecked, and unchecked renders
    exactly as this dataset has always rendered -- the URL, linked, unannotated.
    """
    for payload in payloads:
        payload["provider_link"] = provider_link(payload["program_url"], checks)


def provider_link_coverage(payloads: list[dict[str, Any]]) -> ProviderLinkCoverage:
    """Count what became of the links, from the emitted records rather than the checks.

    Same discipline as :func:`enrichment_coverage` and :func:`cohort_integrity_coverage`:
    the only honest count is of what a reader will actually meet on the pages.
    """
    links = [payload["provider_link"] for payload in payloads if payload["provider_link"]]
    checked = [link for link in links if link["verdict"] is not None]
    dates = sorted(link["checked_on"] for link in checked)
    urls = {link["url"] for link in links}
    checked_urls = {link["url"] for link in checked}
    verdicts = Counter(link["verdict"] for link in checked)
    substitutions = Counter(link["substitution"] for link in links)
    return ProviderLinkCoverage(
        programs_with_link=len(links),
        distinct_urls=len(urls),
        checked_urls=len(checked_urls),
        unchecked_urls=len(urls - checked_urls),
        programs_checked=len(checked),
        programs_unchecked=len(links) - len(checked),
        programs_alive=verdicts["alive"],
        programs_dead=verdicts["dead"],
        programs_indeterminate=verdicts["indeterminate"],
        programs_linked=sum(1 for link in links if link["linked"]),
        programs_not_linked=sum(1 for link in links if not link["linked"]),
        programs_upgraded_to_https=substitutions[link_check.SUBSTITUTION_HTTPS],
        programs_sent_to_front_page=substitutions[link_check.SUBSTITUTION_FRONT_PAGE],
        programs_labelled_home_page=sum(
            1 for link in links if link["label"] == link_check.LABEL_PROVIDER_HOME
        ),
        earliest_check=dates[0] if dates else None,
        latest_check=dates[-1] if dates else None,
    )


# --------------------------------------------------------------------------------------
# The next step
#
# Every program in this dataset was on California's Eligible Training Provider List when the
# state last reported it, and under 20 CFR 680.410 that listing is the precondition for an
# Individual Training Account paying a provider for someone's training. A page that ends at
# the price leaves that unsaid, and the person who would most benefit from knowing it is the
# person least likely to be told anywhere else.
#
# This site cannot determine anybody's eligibility and must never appear to -- that is done
# by a one-stop centre after an interview (20 CFR 680.220). What it can do is name the
# nearest offices where the question is answered. Those come from one statewide read of the
# federal finder, ranked locally, exactly as `afterward.sources.local_help` was built to be
# used: 183 centres in one request, not 227 requests for the same 183.
# --------------------------------------------------------------------------------------

CENTER_RADIUS_MILES: Final = 25.0
"""How far away an office may be and still be published as somewhere to ask.

Chosen from the measured distribution rather than picked. 3,234 of California's 3,266
program pages have a centre inside it and the median page's nearest is about three miles;
widening it to 50 would gain the last 32 pages at the price of offering somebody a mountain
pass as "nearby". The 32 are told plainly that there is none within this distance, and given
the statewide finder instead, which is a better answer than a two-hour drive presented as a
local office.

Straight-line, so it is generous rather than conservative wherever the road is not.
"""

NEAREST_CENTERS: Final = 3
"""How many centres to publish per program.

One is a single point of failure: a phone nobody answers, an office open two mornings a
week, a site that turns out to be the wrong side of a county line. Three is enough to make a
second call and few enough not to be a directory.
"""

CLOSE_ENOUGH_MILES: Final = 10.0
"""Reported in coverage as the band that is plausibly reachable without a car."""


def fetch_job_centers(
    state: str = DEFAULT_STATE, *, cache_dir: Path | None = COS_CACHE_DIR
) -> tuple[local_help.AmericanJobCenter, ...] | None:
    """Every America's Job Center the federal finder holds for ``state``, in one request.

    ``None`` means this build established nothing about where the centres are -- no
    credentials are configured, or the endpoint could not be read. That is the CI case and a
    complete build: the pages then carry the funding route and the statewide finder without
    claiming anything about what is nearby. An empty tuple would be the other thing entirely,
    and neither is ever rendered as the other.

    Centres outside the state are dropped. A border search legitimately returns them -- the
    nearest office to Blythe is in Arizona -- but an Individual Training Account is opened by
    a California local board, so an out-of-state office is not an answer to the question this
    dataset is attaching it to. Nothing is lost today: all 183 California records carry
    ``CA``.
    """
    centers = local_help.fetch_centers(state, cache_dir=cache_dir)
    if centers is None:
        return None
    return tuple(
        center for center in centers if (center.state or "").casefold() == state.casefold()
    )


def local_help_block(
    location: Mapping[str, Any], centers: Sequence[local_help.AmericanJobCenter] | None
) -> dict[str, Any]:
    """The nearest centres to one program, or the record that none were looked for.

    ``centers`` is a list of ``{"id", "miles"}`` rather than whole records: the same three
    offices are the nearest ones to hundreds of programs, and copying 183 addresses across
    3,266 files to say so would add megabytes to a dataset meant to be served to phones. The
    directory itself is published once, in ``coverage.json``, and these point into it.

    Three states, never collapsed into two:

    * ``None`` -- nothing was looked for. Either no directory was read, or this program's own
      record carries no coordinates to search from.
    * ``[]`` -- looked for, and there is no centre within :data:`CENTER_RADIUS_MILES`.
    * a list -- the nearest ones, closest first.

    ``miles`` is rounded to a tenth because it is a great-circle distance being offered to
    somebody deciding whether to travel, and further precision would be a claim about roads
    this has not measured.
    """
    if centers is None:
        return {"radius_miles": CENTER_RADIUS_MILES, "centers": None}

    lat, lon = location.get("lat"), location.get("lon")
    if lat is None or lon is None:
        return {"radius_miles": CENTER_RADIUS_MILES, "centers": None}

    nearby = local_help.nearest_centers(
        centers, lat, lon, limit=NEAREST_CENTERS, within_miles=CENTER_RADIUS_MILES
    )
    return {
        "radius_miles": CENTER_RADIUS_MILES,
        "centers": [
            {
                "id": found.center.center_id,
                "miles": None if found.miles is None else round(found.miles, 1),
            }
            for found in nearby
        ],
    }


def _attach_local_help(
    payloads: list[dict[str, Any]], centers: Sequence[local_help.AmericanJobCenter] | None
) -> None:
    """Write every record's nearest centres, in place.

    Always written, like the cohort verdict and the link decision, so that a consumer can
    tell "this build looked and found nothing" from "this record predates the field".
    """
    for payload in payloads:
        payload["local_help"] = local_help_block(payload["location"], centers)


def local_help_coverage(
    payloads: list[dict[str, Any]], centers: Sequence[local_help.AmericanJobCenter] | None
) -> LocalHelpCoverage:
    """Count what became of the centres, from the emitted records rather than the fetch."""
    # `is True`, not truthiness: a centre the directory left unlabelled is not an affiliate,
    # it is a centre nobody classified, and it must not be counted as either.
    comprehensive = {c.center_id for c in centers or () if c.is_comprehensive is True}
    attached = [payload["local_help"]["centers"] for payload in payloads]
    searched = [rows for rows in attached if rows is not None]
    found = [rows for rows in searched if rows]
    nearest = sorted(rows[0]["miles"] for rows in found if rows[0]["miles"] is not None)
    return LocalHelpCoverage(
        centers_loaded=None if centers is None else len(centers),
        radius_miles=CENTER_RADIUS_MILES,
        programs_searched=len(searched),
        programs_not_searched=len(attached) - len(searched),
        programs_with_a_center=len(found),
        programs_with_none_within_radius=len(searched) - len(found),
        programs_with_a_comprehensive_center=sum(
            1 for rows in found if any(row["id"] in comprehensive for row in rows)
        ),
        programs_with_a_center_within_10_miles=sum(1 for m in nearest if m <= CLOSE_ENOUGH_MILES),
        nearest_median_miles=_median(nearest),
        nearest_farthest_miles=nearest[-1] if nearest else None,
    )


def local_help_document(
    coverage: LocalHelpCoverage,
    centers: Sequence[local_help.AmericanJobCenter] | None,
    payloads: list[dict[str, Any]],
) -> dict[str, Any]:
    """The whole next-step block, as ``coverage.json`` carries it.

    ``guidance`` is present on every build, credentials or not: what the Workforce Innovation
    and Opportunity Act route is, and what to ask about it, does not depend on whether this
    machine could reach a directory of offices. It arrives from
    :func:`afterward.sources.local_help.funding_guidance`, which is the only way to obtain the
    steps, so the sentence naming who actually decides eligibility cannot be emitted apart
    from them.

    ``centers`` is the directory itself, published once and pointed into by every program
    record. ``cities`` is the coverage measurement behind the claim that there is an office
    near almost everywhere this dataset publishes a program -- measured, not asserted, and
    null on a build that measured nothing.
    """
    guidance = local_help.funding_guidance()
    places = local_help.places_from_programs(payloads)
    return asdict(coverage) | {
        "guidance": guidance.as_dict(),
        "centers": None if centers is None else [center.as_dict() for center in centers],
        "cities": None
        if centers is None
        else local_help.measure_coverage(centers, places).as_dict(),
    }


def index_occupations(
    projections: list[edd_lmi.OccupationProjection],
    *,
    enrichment: Mapping[str, careeronestop.OccupationEnrichment] | None = None,
    spanish: Mapping[str, onet.SpanishOccupation] | None = None,
    wage_spread: Mapping[str, Mapping[str, Any]] | None = None,
    wage_regions: Mapping[str, Mapping[str, Any]] | None = None,
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
    _attach_spanish(statewide, spanish or {})
    _attach_wage_spread(statewide, wage_spread or {}, wage_regions or {})
    _attach_related(statewide)
    return statewide


def _attach_wage_spread(
    occupations: dict[str, dict[str, Any]],
    spread: Mapping[str, Mapping[str, Any]],
    regions: Mapping[str, Mapping[str, Any]] | None = None,
) -> None:
    """Attach the five OEWS percentiles, or null.

    California publishes one median for an occupation, which answers "what does this pay?"
    and not "what would it pay me?" -- and the gap between those is the whole question for
    someone deciding whether a year of training is worth it. The tenth and ninetieth
    percentiles are the honest bracket around the median already on the page.

    Every percentile is independently suppressible at source and stays null when it was
    suppressed. None is interpolated from its neighbours, and none is read as zero: a
    withheld wage is a wage nobody published, which is the same rule the rest of this
    dataset follows.
    """
    regions = regions or {}
    for soc_code, occupation in occupations.items():
        row = spread.get(soc_code)
        if row is None:
            occupation["wage_spread"] = None
            continue
        # Only areas this dataset can name. An OEWS area the projections do not publish has
        # no region page, no median beside it and nothing to compare, so carrying it would
        # put a row on the page that nothing else on the site can corroborate.
        published = {
            area["short_name"] for area in occupation.get("regions", []) if area.get("short_name")
        }
        by_area = {
            area: {k: cells.get(k) for k in ("p10", "p25", "p50", "p75", "p90")}
            for area, cells in (regions.get(soc_code) or {}).items()
            if not published or area in published
        }
        occupation["wage_spread"] = {
            "p10": row.get("p10"),
            "p25": row.get("p25"),
            "p50": row.get("p50"),
            "p75": row.get("p75"),
            "p90": row.get("p90"),
            "year": row.get("year"),
            "regions": by_area,
        }


def _attach_spanish(
    occupations: dict[str, dict[str, Any]],
    spanish: Mapping[str, onet.SpanishOccupation],
) -> None:
    """Attach the Spanish title, description and reported titles, or null.

    Written for every occupation whether or not a record was found, so a reader downstream
    can tell "no Spanish record exists" from "this dataset predates the field". Nothing here
    is translated by this project: it is O*NET's own Spanish text or it is absent.
    """
    for soc_code, occupation in occupations.items():
        record = spanish.get(soc_code)
        occupation["spanish"] = (
            None
            if record is None
            else {
                "title": record.title,
                "description": record.description,
                "also_called": list(record.also_called),
            }
        )


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

        # Tasks say what the work actually is; alternate titles are what the job is called
        # in the wild, which is how someone typing "RN" should reach Registered Nurses. The
        # education profile is a measurement of what people in the occupation hold, which is
        # a different kind of claim from the single category EDD assigns.
        occupation["tasks"] = (
            [
                {"description": task.description, "importance": task.importance}
                for task in found.tasks
            ]
            if found is not None
            else []
        )
        occupation["alternate_titles"] = list(found.alternate_titles) if found is not None else []
        occupation["education"] = (
            found.education.as_dict() if found is not None and found.education is not None else None
        )


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
    :mod:`afterward.sources.soc_vintage` -- without it, 61 California programs have no
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
    similarity judgement :mod:`afterward.sources.soc_vintage` refuses to make, and it would put
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
    link_checks: Mapping[str, link_check.LinkCheck] | None = None,
    centers: Sequence[local_help.AmericanJobCenter] | None = None,
) -> dict[str, Any]:
    """One program record, with its outcomes labelled by who they actually describe.

    ``cohort`` comes from :func:`afterward.sources.dol_etp.cohort_integrity` run over the whole
    snapshot, because a cohort republished across a provider's programs is invisible from
    inside any one of them. Omitting it judges the program against itself alone, which is a
    real answer -- the contradiction checks still run -- and is what a caller holding a
    single record can honestly say.

    ``link_checks`` comes from a separate, explicitly-invoked pass over the provider URLs.
    Omitting it is the ordinary case -- CI has no network -- and produces a record that
    publishes its link exactly as the federal feed filed it, claiming nothing about it.

    ``centers`` is the state's America's Job Centers, read once for the whole build. Omitting
    it produces a record whose ``local_help.centers`` is null: nowhere was looked for, which
    is not the same as nowhere being near.
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
        # The URL exactly as filed, never rewritten. What to *do* with it -- link it, link
        # the provider's front page instead, or link nothing and say why -- is the block
        # below, so a consumer can always see the source's own value alongside the decision.
        "program_url": program.program_url,
        "provider_link": provider_link(program.program_url, link_checks or {}),
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
            # NOT the numerator and denominator of the rate above, however they read sitting
            # next to it. `completion_rate` does reconcile with completed/exited -- 2,047
            # agree, 0 disagree -- so the shape of this block invites the same arithmetic on
            # the employment pair, where it does not hold: of the 1,760 programs publishing a
            # rate and a Q2 count against a non-zero exit count, the median gap between
            # employed_q2/total_exited and the published rate is 0.17, 1,177 (66.9%) differ by
            # more than 10 points, only 165 (9.4%) agree within a rounding step, and 65 report
            # more people employed than exited at all. DOL computes the rate on an exiter
            # denominator it does not publish. Both are carried because both are filed and a
            # reader is entitled to them; neither is derived from the other here, and nothing
            # downstream may derive one either.
            "employed_q2": program.employed_q2,
            "employed_q4": program.employed_q4,
            "reported": program.has_outcomes,
            # Who the counts above describe. `reported` says a figure exists; this says
            # whether it is this program's to be judged on. Never omitted, so "checked and
            # sound" stays distinguishable from "built before the check existed".
            "cohort": integrity.as_dict(),
        },
        "occupations": matched,
        # Where a person can ask whether somebody else will pay for this. Points into the
        # centre directory published once in coverage.json; null means not looked for.
        "local_help": local_help_block({"lat": program.lat, "lon": program.lon}, centers),
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


def build_offline(
    fixture_dir: Path, *, output_dir: Path | None = None, link_checks_path: Path | None = None
) -> int:
    """Emit the site bundle from a committed fixture instead of the live sources.

    CI uses this. The upstream DOL endpoint refuses requests from GitHub Actions runners,
    and a build that depends on a third party being reachable fails for reasons that have
    nothing to do with the change under test. This runs the same emit code as a real build,
    so the shape of what the site consumes is exercised either way.

    ``link_checks_path`` defaults to nothing, so this build establishes nothing about any
    provider link and publishes every one as filed. That is deliberate: the fixture build is
    the hermetic one, and a link verdict copied out of some other machine's report would be
    an observation this build did not make. It is recomputed rather than trusted from the
    fixture for the same reason :func:`_attach_cohort_integrity` recomputes -- a fixture
    predating the field carries no block, and defaulting one in would publish "we checked
    this" about a link nothing had checked.
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
    _attach_provider_links(payloads, load_link_checks(link_checks_path))
    # The fixture predates the wage spread and carries no such key, so without this every
    # occupation reaches the page with the field absent rather than null -- a shape no real
    # build produces, which is how a page that guards `!== null` still crashed the export.
    # With no OEWS extract on the machine this attaches null everywhere, which is the honest
    # answer: nothing published a spread here, so the pages say the median alone.
    _attach_wage_spread(occupations, load_wage_spread(), load_wage_regions())
    # No centres are looked up here, for the same reason no links are checked: this is the
    # hermetic build, and a distance copied out of another machine's read would be an
    # observation this build did not make. The pages it produces carry the funding route and
    # the statewide finder, and claim nothing about what is near any particular city.
    _attach_local_help(payloads, None)
    coverage["cohort_integrity"] = asdict(cohort_integrity_coverage(payloads))
    coverage["provider_links"] = asdict(provider_link_coverage(payloads))
    coverage["local_help"] = local_help_document(
        local_help_coverage(payloads, None), None, payloads
    )
    coverage["peer_medians"] = peer_medians(payloads)
    # The fixture's own coverage block is carried through untouched apart from the keys above,
    # so a fixture older than a field the site reads would ship a document missing it. Checked
    # before anything is written, so the failure is a build that stops rather than a site that
    # quietly renders one section fewer.
    check_coverage_shape(coverage)

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
    link_checks_path: Path | None = LINK_CHECK_PATH,
) -> CoverageReport:
    """Fetch, join and emit. Reads a provider-link report if one has been left for it.

    ``link_checks_path`` is consumed, never produced: the check is
    :func:`check_provider_links`, invoked deliberately by ``afterward check-links``, and a build
    that found no report is a complete build whose links are published exactly as filed.
    """
    output_dir = output_dir or Path("data/processed")
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot = snapshot or date.today().isoformat()
    link_checks = load_link_checks(link_checks_path)

    programs = list(dol_etp.fetch_programs(state))
    benchmark = dol_etp.fetch_state_benchmark(state)
    projections = edd_lmi.fetch_projections()
    # Enrichment first, so the occupation index is built once with it rather than rewritten.
    # Empty when no credentials are configured, which is a complete build, not a failed one.
    enrichment = fetch_enrichment(
        detailed_soc_codes(projections), state=state, cache_dir=COS_CACHE_DIR
    )
    # O*NET's Spanish records, for the same occupations and on the same terms: absent
    # without a key, absent for the occupations Mi Próximo Paso does not carry.
    spanish = fetch_spanish_occupations(detailed_soc_codes(projections))
    # Whatever a previous `afterward fetch-wages` left behind; absent is a complete build.
    wage_spread = load_wage_spread()
    wage_regions = load_wage_regions()
    occupations = index_occupations(
        projections,
        enrichment=enrichment,
        spanish=spanish,
        wage_spread=wage_spread,
        wage_regions=wage_regions,
    )
    areas = edd_lmi.area_definitions(projections)
    city_areas = edd_lmi.principal_city_areas(areas)

    # Judged over the whole snapshot before any record is built: a cohort republished across
    # a provider's programs, and a provider filing many impossible ones, are both invisible
    # from inside a single row.
    integrity = dol_etp.cohort_integrity([dol_etp.CohortFiling.of(p) for p in programs])
    # One statewide read for every program, cached on disk like the occupation enrichment.
    # None with no credentials, which is a complete build carrying no distance claims.
    centers = fetch_job_centers(state, cache_dir=COS_CACHE_DIR)
    payloads = [
        program_payload(
            p, occupations, city_areas, cohort=c, link_checks=link_checks, centers=centers
        )
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
        provider_links=provider_link_coverage(payloads),
        local_help=local_help_coverage(payloads, centers),
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
    coverage = asdict(report) | {
        "outcome_coverage_pct": report.outcome_coverage_pct,
        "occupation_match_pct": report.occupation_match_pct,
        "area_match_pct": report.area_match_pct,
        "areas": area_coverage(payloads, areas),
        "unmapped_cities": unmapped_cities(payloads),
        # The counts, plus the centre directory the program records point into and
        # the guidance the site publishes with them. Overrides the plain counts
        # `asdict(report)` already wrote under this key.
        "local_help": local_help_document(report.local_help, centers, payloads),
        # DOL's own statewide aggregate. Kept as published context, but NOT used
        # for per-program comparison: it is computed on a different basis (27%
        # employed against a 69% median among reporting programs).
        "state_benchmark": benchmark.as_dict() if benchmark else None,
        "peer_medians": peer_medians(payloads),
    }
    check_coverage_shape(coverage)
    (output_dir / "coverage.json").write_text(json.dumps(coverage, indent=1), encoding="utf-8")
    return report
