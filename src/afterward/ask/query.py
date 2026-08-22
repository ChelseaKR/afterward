"""The structured query the model may produce, and the deterministic executor that runs it.

The model's whole contribution to *finding* anything is an instance of :class:`StructuredQuery`.
Every field is either a free-text term this module resolves against the dataset's own
vocabulary, a bounded choice, or a number the person stated. There is no field in which the
model could name a SOC code, an area, or a program, because a model will produce a plausible
one that the dataset does not carry. What it could not tell from the text it leaves empty and
says so in ``clarifications_needed``; the eval for that is "refused to guess".

:func:`execute` then does what a search form would do, and records what it could not do.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from afterward.ask.dataset import Dataset, OccupationHit, RegionHit

Language = Literal["en", "es"]
Intent = Literal[
    "find_programs",
    "program_detail",
    "occupation_detail",
    "compare",
    "pathways",
    "coverage_question",
    "other",
]
Projection = Literal["growing", "not_shrinking", "shrinking", "any"]
Format = Literal["online", "in_person", "hybrid", "any"]
Measure = Literal[
    "completion_rate",
    "employment_rate_q2",
    "median_earnings",
    "cost",
    "length",
    "wage",
    "openings",
    "growth",
]

MAX_PROGRAMS = 8
MAX_OCCUPATIONS = 5


class StructuredQuery(BaseModel):
    """What the model extracted from the person's words. Terms, not identifiers."""

    model_config = ConfigDict(extra="forbid")

    language: Language
    intent: Intent
    occupation_terms: list[str] = Field(default_factory=list)
    """Occupations the person wants to move *into*, in their own words."""
    occupation_terms_english: list[str] = Field(default_factory=list)
    """Plain English for each Spanish term in ``occupation_terms``; empty when they wrote in
    English. A gloss of a word, not a title or a code: "camionero" -> "truck driver"."""
    current_occupation_terms: list[str] = Field(default_factory=list)
    """What the person does now, when they said; used for pathways."""
    current_occupation_terms_english: list[str] = Field(default_factory=list)
    region_terms: list[str] = Field(default_factory=list)
    projection: Projection = "any"
    min_annual_wage: float | None = None
    max_cost: float | None = None
    max_weeks: float | None = None
    format: Format = "any"
    requires_reported_outcomes: bool = False
    measures_of_interest: list[Measure] = Field(default_factory=list)
    clarifications_needed: list[str] = Field(default_factory=list)
    """Questions the person would need to answer before the query could be specific."""
    out_of_scope: str | None = None
    """The part of the question this dataset cannot answer, in the person's language."""


def _enum(*values: str) -> dict[str, Any]:
    return {"type": "string", "enum": list(values)}


def _strings() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}}


QUERY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "language": _enum("en", "es"),
        "intent": _enum(
            "find_programs",
            "program_detail",
            "occupation_detail",
            "compare",
            "pathways",
            "coverage_question",
            "other",
        ),
        "occupation_terms": _strings(),
        "occupation_terms_english": _strings(),
        "current_occupation_terms": _strings(),
        "current_occupation_terms_english": _strings(),
        "region_terms": _strings(),
        "projection": _enum("growing", "not_shrinking", "shrinking", "any"),
        "min_annual_wage": {"type": ["number", "null"]},
        "max_cost": {"type": ["number", "null"]},
        "max_weeks": {"type": ["number", "null"]},
        "format": _enum("online", "in_person", "hybrid", "any"),
        "requires_reported_outcomes": {"type": "boolean"},
        "measures_of_interest": {
            "type": "array",
            "items": _enum(
                "completion_rate",
                "employment_rate_q2",
                "median_earnings",
                "cost",
                "length",
                "wage",
                "openings",
                "growth",
            ),
        },
        "clarifications_needed": _strings(),
        "out_of_scope": {"type": ["string", "null"]},
    },
    "required": [
        "language",
        "intent",
        "occupation_terms",
        "occupation_terms_english",
        "current_occupation_terms",
        "current_occupation_terms_english",
        "region_terms",
        "projection",
        "min_annual_wage",
        "max_cost",
        "max_weeks",
        "format",
        "requires_reported_outcomes",
        "measures_of_interest",
        "clarifications_needed",
        "out_of_scope",
    ],
    "additionalProperties": False,
}
"""Written by hand, flat, every field required, nullable by type array. Pydantic's generated
schema carries ``$defs``, ``anyOf`` and defaults that one provider rejects as "too complex";
this one is what every provider accepts, and :class:`StructuredQuery` validates what comes
back. A test holds the two in agreement."""


@dataclass(frozen=True)
class Resolution:
    """What the terms resolved to, and what they did not."""

    occupations: list[OccupationHit]
    current_occupations: list[OccupationHit]
    region: RegionHit | None
    unresolved_occupation_terms: list[str]
    unresolved_current_terms: list[str]
    unresolved_region_terms: list[str]


@dataclass
class Exclusions:
    """Programs a filter removed because the record could not answer it, counted."""

    cost_not_reported: int = 0
    length_not_comparable: int = 0
    outcomes_not_reported: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "cost_not_reported": self.cost_not_reported,
            "length_not_comparable": self.length_not_comparable,
            "outcomes_not_reported": self.outcomes_not_reported,
        }


@dataclass
class QueryResult:
    query: StructuredQuery
    resolution: Resolution
    programs: list[dict[str, Any]]
    occupations: list[dict[str, Any]]
    excluded: Exclusions
    notes: list[str] = field(default_factory=list)
    """Findings the narration must carry: an uncovered region, an unknown occupation."""
    candidates: int = 0
    """How many programs matched before the list was cut to :data:`MAX_PROGRAMS`."""


def resolve(query: StructuredQuery, dataset: Dataset) -> Resolution:
    occupations, unresolved = _resolve_terms(
        query.occupation_terms, dataset, glosses=query.occupation_terms_english
    )
    current, unresolved_current = _resolve_terms(
        query.current_occupation_terms, dataset, glosses=query.current_occupation_terms_english
    )
    region: RegionHit | None = None
    unresolved_regions: list[str] = []
    for term in query.region_terms:
        hit = dataset.resolve_region(term)
        if hit is None:
            unresolved_regions.append(term)
        elif region is None or (region.matched_on == "city" and hit.matched_on == "area"):
            region = hit
    return Resolution(
        occupations=occupations,
        current_occupations=current,
        region=region,
        unresolved_occupation_terms=unresolved,
        unresolved_current_terms=unresolved_current,
        unresolved_region_terms=unresolved_regions,
    )


def _resolve_terms(
    terms: Sequence[str], dataset: Dataset, *, glosses: Sequence[str] = ()
) -> tuple[list[OccupationHit], list[str]]:
    """Resolve each term, and where a Spanish term finds nothing, its English gloss.

    The gloss is tried second and only when the term itself resolved to nothing, so a term
    the dataset's own Spanish vocabulary covers is never overridden by a translation.
    """
    hits: dict[str, OccupationHit] = {}
    unresolved: list[str] = []
    for index, term in enumerate(terms):
        found = dataset.resolve_occupations(term, limit=3)
        if not found and index < len(glosses):
            found = dataset.resolve_occupations(glosses[index], limit=3)
        if not found:
            unresolved.append(term)
        for hit in found:
            if hit.soc_code not in hits or hit.score > hits[hit.soc_code].score:
                hits[hit.soc_code] = hit
    ranked = sorted(hits.values(), key=lambda h: (-h.score, h.soc_code))
    return ranked, unresolved


def execute(
    query: StructuredQuery,
    dataset: Dataset,
    *,
    context_program: str | None = None,
    context_occupation: str | None = None,
) -> QueryResult:
    """Run the query over the dataset, deterministically, and record what could not be done."""
    resolution = resolve(query, dataset)
    notes = _resolution_notes(resolution, dataset)
    excluded = Exclusions()

    program = dataset.program(context_program) if context_program else None
    if program is not None:
        occupations = [
            o
            for soc in (oc["soc_code"] for oc in program["occupations"])
            if (o := dataset.occupation(soc)) is not None
        ]
        return QueryResult(query, resolution, [program], occupations, excluded, notes, 1)

    query = _with_implied_wage_floor(query, resolution, dataset, notes)
    soc_codes = [hit.soc_code for hit in resolution.occupations]
    if context_occupation and dataset.occupation(context_occupation):
        soc_codes = [context_occupation, *[s for s in soc_codes if s != context_occupation]]
    if not soc_codes:
        soc_codes = _occupations_by_criteria(query, dataset, resolution.region)
        if soc_codes:
            notes.append("occupations_chosen_by_criteria")

    occupations = [o for soc in soc_codes[:MAX_OCCUPATIONS] if (o := dataset.occupation(soc))]
    candidates = dataset.programs_for(soc_codes[:MAX_OCCUPATIONS])
    kept = [p for p in candidates if _passes(p, query, resolution.region, dataset, excluded)]
    kept.sort(key=lambda p: _rank_key(p, resolution.region))
    if candidates and not kept:
        notes.append("filters_removed_every_program")
    return QueryResult(
        query,
        resolution,
        kept[:MAX_PROGRAMS],
        occupations,
        excluded,
        notes,
        candidates=len(kept),
    )


def _resolution_notes(resolution: Resolution, dataset: Dataset) -> list[str]:
    notes: list[str] = []
    if resolution.unresolved_occupation_terms:
        notes.append("occupation_terms_unresolved")
    if resolution.unresolved_current_terms:
        notes.append("current_occupation_unresolved")
    if resolution.unresolved_region_terms and resolution.region is None:
        notes.append("region_not_covered")
    if resolution.region is not None and resolution.region.matched_on == "city":
        notes.append("region_is_city_only")
    return notes


def _with_implied_wage_floor(
    query: StructuredQuery, resolution: Resolution, dataset: Dataset, notes: list[str]
) -> StructuredQuery:
    """ "Pays more" with no number means more than what the person does now, when they said.

    The floor is the current occupation's published median annual wage -- the regional row
    where the region has one -- which is the only reading of "more" the dataset can support.
    With no current occupation resolved, or a number already given, the query is unchanged.
    """
    if query.min_annual_wage is not None or "wage" not in query.measures_of_interest:
        return query
    if not resolution.current_occupations:
        return query
    current = dataset.occupation(resolution.current_occupations[0].soc_code)
    wage = _figures(current, resolution.region)["median_annual_wage"] if current else None
    if wage is None:
        return query
    notes.append(f"wage floor taken from the current occupation's median: {wage:,.0f} a year")
    # "More" is strictly more: the current occupation itself does not pay more than itself.
    return query.model_copy(update={"min_annual_wage": math.nextafter(float(wage), math.inf)})


def _occupations_by_criteria(
    query: StructuredQuery, dataset: Dataset, region: RegionHit | None
) -> list[str]:
    """With no occupation named, pick the occupations the criteria alone select.

    Only occupations that at least one program in the person's area leads to are candidates,
    because an occupation with no program is not an answer to "what could I train for".
    Ranked by projected openings (regional where the region has a row), because after the
    wage floor has done the filtering, openings is the figure that says whether a field has
    room; and capped so the narration is about a handful of real records rather than a
    catalogue. Not a quality ranking.
    """
    scored: list[tuple[float, str]] = []
    for soc, occupation in dataset.occupations.items():
        figures = _figures(occupation, region)
        if not _projection_ok(figures["percent_change"], query.projection):
            continue
        wage = figures["median_annual_wage"]
        if query.min_annual_wage is not None and (wage is None or wage < query.min_annual_wage):
            continue
        if not any(_in_region(p, region) for p in dataset.programs_for([soc])):
            continue
        scored.append((-(figures["total_job_openings"] or 0.0), soc))
    return [soc for _, soc in sorted(scored)[:MAX_OCCUPATIONS]]


def _figures(occupation: dict[str, Any], region: RegionHit | None) -> dict[str, float | None]:
    """Statewide figures, or the region's row when the region has one for this occupation."""
    if region is not None and region.area_name:
        for row in occupation.get("regions") or []:
            if row["area_name"] == region.area_name:
                return {
                    "percent_change": row.get("percent_change"),
                    "median_annual_wage": row.get("median_annual_wage"),
                    "total_job_openings": row.get("total_job_openings"),
                }
    return {
        "percent_change": occupation.get("percent_change"),
        "median_annual_wage": occupation.get("median_annual_wage"),
        "total_job_openings": occupation.get("total_job_openings"),
    }


def _projection_ok(change: float | None, projection: Projection) -> bool:
    if projection == "any":
        return True
    if change is None:
        # A projection that is not published cannot satisfy a projection filter. It is not
        # assumed to be growing, and it is not assumed to be shrinking.
        return False
    if projection == "growing":
        return change > 0
    if projection == "not_shrinking":
        return change >= 0
    return change < 0


def _passes(
    program: dict[str, Any],
    query: StructuredQuery,
    region: RegionHit | None,
    dataset: Dataset,
    excluded: Exclusions,
) -> bool:
    if not _in_region(program, region):
        return False
    if not _format_ok(program.get("program_format"), query.format):
        return False
    if query.projection != "any" and not _program_projection_ok(program, query, region, dataset):
        return False
    if query.min_annual_wage is not None and not _wage_ok(program, query, region, dataset):
        return False
    return (
        _cost_ok(program, query, excluded)
        and _length_ok(program, query, excluded)
        and (_outcomes_ok(program, query, excluded))
    )


def _in_region(program: dict[str, Any], region: RegionHit | None) -> bool:
    if region is None:
        return True
    if region.matched_on == "city":
        return bool((program.get("location") or {}).get("city") == region.city)
    program_region = program.get("region")
    return bool(program_region and program_region["area_name"] == region.area_name)


def _format_ok(program_format: str | None, wanted: Format) -> bool:
    if wanted == "any":
        return True
    text = (program_format or "").lower()
    if wanted == "online":
        return "online" in text and "hybrid" not in text
    if wanted == "hybrid":
        return "hybrid" in text
    return "in-person" in text and "hybrid" not in text


def _program_projection_ok(
    program: dict[str, Any], query: StructuredQuery, region: RegionHit | None, dataset: Dataset
) -> bool:
    changes = [
        _figures(o, region)["percent_change"]
        for soc in (oc["soc_code"] for oc in program.get("occupations") or [])
        if (o := dataset.occupation(soc)) is not None
    ]
    if not changes:
        return False
    if query.projection == "shrinking":
        return any(c is not None and c < 0 for c in changes)
    if query.projection == "growing":
        return any(c is not None and c > 0 for c in changes)
    return all(c is not None and c >= 0 for c in changes)


def _wage_ok(
    program: dict[str, Any], query: StructuredQuery, region: RegionHit | None, dataset: Dataset
) -> bool:
    floor = query.min_annual_wage or 0.0
    for oc in program.get("occupations") or []:
        occupation = dataset.occupation(oc["soc_code"])
        wage = _figures(occupation, region)["median_annual_wage"] if occupation else None
        if wage is not None and wage >= floor:
            return True
    return False


def _cost_ok(program: dict[str, Any], query: StructuredQuery, excluded: Exclusions) -> bool:
    if query.max_cost is None:
        return True
    cost = (program.get("cost") or {}).get("total_out_of_pocket")
    if cost is None:
        # An unreported cost is not a cost of zero and cannot be under a ceiling.
        excluded.cost_not_reported += 1
        return False
    return bool(cost <= query.max_cost)


def _length_ok(program: dict[str, Any], query: StructuredQuery, excluded: Exclusions) -> bool:
    if query.max_weeks is None:
        return True
    length = program.get("length") or {}
    weeks = length.get("weeks")
    if weeks is None:
        # Competency-based (no fixed length by design) or unfiled: neither is "short".
        excluded.length_not_comparable += 1
        return False
    return bool(weeks <= query.max_weeks)


def _outcomes_ok(program: dict[str, Any], query: StructuredQuery, excluded: Exclusions) -> bool:
    if not query.requires_reported_outcomes:
        return True
    if (program.get("outcomes") or {}).get("reported"):
        return True
    excluded.outcomes_not_reported += 1
    return False


def _rank_key(program: dict[str, Any], region: RegionHit | None) -> tuple[Any, ...]:
    """Reported outcomes first, then the person's own area, then cost, then a stable id.

    Not a quality ranking. The site declines to rank programs against each other on
    outcomes (see ``web/lib/compare.ts``), and so does this: a program that reported is
    listed before one that did not because it can be narrated, not because it is better.
    """
    outcomes = program.get("outcomes") or {}
    in_area = region is not None and _in_region(program, region)
    cost = (program.get("cost") or {}).get("total_out_of_pocket")
    return (
        0 if outcomes.get("reported") else 1,
        0 if in_area else 1,
        cost if cost is not None else float("inf"),
        program["uuid"],
    )


def program_ids(programs: Iterable[dict[str, Any]]) -> list[str]:
    return [p["uuid"] for p in programs]
