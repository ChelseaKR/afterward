"""Transition pathways: from the job a person has, to related occupations the state projects
will grow, to the California programs that lead there.

Every relation comes from the dataset. Each occupation record carries a ``related`` list the
pipeline published -- from O*NET's related-occupation data where CareerOneStop supplied it,
or from the SOC major group where it did not -- and ``related_source`` says which. This
module reads that list and nothing else: no model names a relation, and an occupation whose
published list is empty yields an honest "the dataset carries no related occupations",
never a plausible one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from afterward.ask.dataset import Dataset, RegionHit

MAX_RELATED = 5


@dataclass
class Pathways:
    from_soc: str
    related_source: str | None
    """``onet`` or ``soc_major_group`` as published, or ``None`` when the list is empty."""
    candidates: list[str]
    """Related SOC codes, filtered and ordered, that at least one program leads to."""
    considered: int
    """How many related occupations the record published before filtering."""
    notes: list[str] = field(default_factory=list)


def pathways_from(
    dataset: Dataset,
    from_soc: str,
    *,
    region: RegionHit | None,
    growing_only: bool,
) -> Pathways:
    """Related occupations of ``from_soc`` with a program leading there, growth-first.

    Ordered by the published percent change (the region's row where there is one), so the
    occupations the state projects to grow most come first; ties broken by openings. Not a
    recommendation: the person's current occupation is excluded because "stay" is not a
    pathway, and nothing here weighs whether a transition is feasible for anyone.
    """
    occupation = dataset.occupation(from_soc)
    if occupation is None:
        return Pathways(from_soc, None, [], 0, ["pathway_origin_not_in_dataset"])
    related = occupation.get("related") or []
    source = occupation.get("related_source")
    if not related:
        return Pathways(from_soc, None, [], 0, ["no_related_occupations_published"])
    scored: list[tuple[float, float, str]] = []
    dropped_no_program = 0
    dropped_not_growing = 0
    for row in related:
        soc = row.get("soc_code")
        target = dataset.occupation(soc) if soc else None
        if target is None or soc == from_soc:
            continue
        change, openings = _figures(target, region)
        if growing_only and (change is None or change <= 0):
            dropped_not_growing += 1
            continue
        if not _has_program(dataset, soc, region):
            dropped_no_program += 1
            continue
        scored.append((-(change if change is not None else float("-inf")), -(openings or 0.0), soc))
    notes = [f"pathways_from:{from_soc}", f"related_source:{source}"]
    if dropped_not_growing:
        notes.append(
            f"{dropped_not_growing} related occupations left out because not projected to grow"
        )
    if dropped_no_program:
        notes.append(
            f"{dropped_no_program} related occupations left out because no program leads there"
        )
    candidates = [soc for _, _, soc in sorted(scored)[:MAX_RELATED]]
    if not candidates:
        notes.append("no_related_occupation_with_a_program")
    return Pathways(from_soc, str(source) if source else None, candidates, len(related), notes)


def _figures(
    occupation: dict[str, Any], region: RegionHit | None
) -> tuple[float | None, float | None]:
    if region is not None and region.area_name:
        for row in occupation.get("regions") or []:
            if row.get("area_name") == region.area_name:
                return row.get("percent_change"), row.get("total_job_openings")
    return occupation.get("percent_change"), occupation.get("total_job_openings")


def _has_program(dataset: Dataset, soc: str, region: RegionHit | None) -> bool:
    for program in dataset.programs_for([soc]):
        if region is None:
            return True
        if region.matched_on == "city":
            if (program.get("location") or {}).get("city") == region.city:
                return True
        elif (program.get("region") or {}).get("area_name") == region.area_name:
            return True
    return False
