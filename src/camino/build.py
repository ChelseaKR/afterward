"""Join California training programs to occupation outlook data and emit the site dataset.

The join is the product: a program's reported WIOA outcomes on one side, and the state's
own projection of what the occupation it feeds actually pays and how many openings it has
on the other. Nothing in California publishes those two facts next to each other today.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from camino.sources import dol_etp, edd_lmi

DEFAULT_STATE = "CA"


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
    distinct_providers: int
    distinct_occupations_matched: int
    occupation_rows_loaded: int
    # Geography. `programs_without_area` is carried as its own number rather than left to
    # be subtracted, because "we declined to place this program" is a published finding
    # about the dataset and not an arithmetic leftover.
    programs_mapped_to_area: int
    programs_without_area: int
    programs_with_regional_projection: int

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
    """
    summary: dict[str, dict[str, Any]] = {}
    for measure in PEER_MEASURES:
        values = sorted(
            payload["outcomes"][measure]
            for payload in payloads
            if payload["outcomes"].get(measure) is not None
        )
        summary[measure] = {
            "median": _median(values),
            "reporting": len(values),
        }
    return summary


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return (values[middle - 1] + values[middle]) / 2


def index_occupations(
    projections: list[edd_lmi.OccupationProjection],
) -> dict[str, dict[str, Any]]:
    """Index statewide detailed-SOC projections by SOC code.

    Regional rows are retained under ``regions`` so a program can later be shown wages for
    the area it is actually in, but the statewide row is the default because a program's
    graduates do not necessarily work in the county where they trained.
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

    _attach_related(statewide)
    return statewide


RELATED_LIMIT = 6


def _attach_related(occupations: dict[str, dict[str, Any]]) -> None:
    """Attach sibling occupations from the same SOC major group.

    Derived from the SOC hierarchy rather than a skills model: the first two digits of a SOC
    code are its major group, so "29-1141 Registered Nurses" and "29-2061 Licensed Practical
    Nurses" are genuinely adjacent by the classification's own definition. That is a weaker
    claim than skill similarity, and deliberately so -- asserting that two jobs need the same
    skills would need O*NET data this project does not yet carry.

    Siblings are ranked by projected openings, because the useful question standing on an
    occupation page is "what nearby work is actually hiring".
    """
    by_group: dict[str, list[str]] = {}
    for soc_code in occupations:
        by_group.setdefault(soc_code[:2], []).append(soc_code)

    for soc_code, occupation in occupations.items():
        siblings = [
            occupations[other] for other in by_group.get(soc_code[:2], []) if other != soc_code
        ]
        # `or -1` would fold a reported zero openings into the same bucket as unreported.
        # Nothing has zero openings today, but this is the exact confusion the project
        # exists to avoid, and it has no business sitting inside a sort key.
        siblings.sort(
            key=lambda o: (
                o["total_job_openings"] if o.get("total_job_openings") is not None else -1
            ),
            reverse=True,
        )
        occupation["related"] = [
            {
                "soc_code": sibling["soc_code"],
                "title": sibling["title"],
                "median_annual_wage": sibling["median_annual_wage"],
                "total_job_openings": sibling["total_job_openings"],
                "percent_change": sibling["percent_change"],
            }
            for sibling in siblings[:RELATED_LIMIT]
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


def occupation_summary(occupation: dict[str, Any], area_name: str | None = None) -> dict[str, Any]:
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
    """
    summary = {key: occupation.get(key) for key in OCCUPATION_SUMMARY_FIELDS}
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
) -> dict[str, Any]:
    area = area_for_city(program.city, city_areas)
    area_name = None if area is None else area.area_name
    matched = [
        occupation_summary(occupations[soc], area_name)
        for soc in program.soc_codes
        if soc in occupations
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
        },
        "occupations": matched,
    }


def search_entry(program: dict[str, Any]) -> dict[str, Any]:
    """One row of the client-side search index.

    Short keys and only the fields a result card or filter actually needs. Everything else
    is fetched per-program on demand, so the first paint does not cost megabytes on a phone.
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
    return {
        "i": program["uuid"],
        "n": program["program_name"],
        "p": program["provider_name"],
        "c": program["location"]["city"],
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
    occupations = index_occupations(projections)
    areas = edd_lmi.area_definitions(projections)
    city_areas = edd_lmi.principal_city_areas(areas)

    payloads = [program_payload(p, occupations, city_areas) for p in programs]
    matched_socs = {soc for p in payloads for soc in p["soc_codes"] if soc in occupations}
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
        distinct_providers=len({p.provider_name for p in programs if p.provider_name}),
        distinct_occupations_matched=len(matched_socs),
        occupation_rows_loaded=len(occupations),
        programs_mapped_to_area=mapped_to_area,
        programs_without_area=len(payloads) - mapped_to_area,
        programs_with_regional_projection=sum(
            1 for p in payloads if any(o["region"] is not None for o in p["occupations"])
        ),
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
