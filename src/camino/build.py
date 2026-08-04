"""Join California training programs to occupation outlook data and emit the site dataset.

The join is the product: a program's reported WIOA outcomes on one side, and the state's
own projection of what the occupation it feeds actually pays and how many openings it has
on the other. Nothing in California publishes those two facts next to each other today.
"""

from __future__ import annotations

import json
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

    @property
    def outcome_coverage_pct(self) -> float:
        return self._pct(self.programs_with_any_outcome)

    @property
    def occupation_match_pct(self) -> float:
        return self._pct(self.programs_matched_to_occupation)

    def _pct(self, numerator: int) -> float:
        return round(100.0 * numerator / self.total_programs, 1) if self.total_programs else 0.0


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
        siblings.sort(key=lambda o: o.get("total_job_openings") or -1, reverse=True)
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


def occupation_summary(occupation: dict[str, Any]) -> dict[str, Any]:
    """Slim projection of an occupation for embedding in a program record.

    Programs reference occupations by SOC rather than carrying a copy: the full record,
    including every regional wage row, lives once in ``occupations.json``. Embedding it
    per-program inflated the dataset by two orders of magnitude, which matters because this
    is meant to ship as static files to phones.
    """
    return {key: occupation.get(key) for key in OCCUPATION_SUMMARY_FIELDS}


def program_payload(
    program: dol_etp.Program, occupations: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    matched = [
        occupation_summary(occupations[soc]) for soc in program.soc_codes if soc in occupations
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
        "length": {"weeks": program.length_weeks, "hours": program.length_hours},
        "cost": {
            "tuition": program.cost_tuition,
            "supplies": program.cost_supplies,
            "total_out_of_pocket": program.total_cost,
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
    occupation = (program["occupations"] or [{}])[0]
    outcomes = program["outcomes"]
    return {
        "i": program["uuid"],
        "n": program["program_name"],
        "p": program["provider_name"],
        "c": program["location"]["city"],
        "$": program["cost"]["total_out_of_pocket"],
        "w": program["length"]["weeks"],
        "s": program["soc_codes"],
        "o": occupation.get("title"),
        # Occupation outlook, so "trains for a shrinking job" is filterable without a
        # second fetch. None stays None: unknown is not the same as flat.
        "g": occupation.get("percent_change"),
        "wage": occupation.get("median_annual_wage"),
        "op": occupation.get("total_job_openings"),
        # Headline outcomes, null-preserving.
        "cr": outcomes["completion_rate"],
        "er": outcomes["employment_rate_q2"],
        "me": outcomes["median_earnings"],
        "r": outcomes["reported"],
    }


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

    payloads = [program_payload(p, occupations) for p in programs]
    matched_socs = {soc for p in payloads for soc in p["soc_codes"] if soc in occupations}

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
                "state_benchmark": benchmark.as_dict() if benchmark else None,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    return report
