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
    return statewide


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
    (output_dir / "coverage.json").write_text(
        json.dumps(
            asdict(report)
            | {
                "outcome_coverage_pct": report.outcome_coverage_pct,
                "occupation_match_pct": report.occupation_match_pct,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    return report
