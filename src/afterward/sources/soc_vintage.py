"""Reconcile the SOC codes on federal training records with the ones EDD publishes.

Despite the name this is not a SOC revision problem. Source D1 (DOL ETP) and source D2 (CA
EDD projections) are both on the 2018 SOC: the BLS 2010-to-2018 crosswalk leaves every code
involved here either unchanged or absent from the 2010 SOC entirely. What differs is the
level of detail. D1 labels a program with a *detailed* 2018 SOC occupation. D2 follows the
BLS publication taxonomy, which for some occupations produces no separate estimate and
reports them only as an aggregate -- either the SOC broad group directly above them, or a
BLS "hybrid" code that exists in the publication taxonomy but not in the SOC at all. An
exact join therefore drops the program even though California does publish a wage and an
outlook for those workers.

Every row in ``AGGREGATIONS`` satisfies one rule: by BLS's own published definition, the
target's population *contains* the source occupation. Nothing here is a similarity
judgement, and there is no fuzzy or title-based fallback -- a training program carrying the
wrong occupation would show a reader the wrong wage and the wrong outlook for a decision
that costs them a year, which is strictly worse than showing nothing.

Two consequences the caller has to respect:

* A mapped program is shown a *broader* group's figures. That is the only estimate
  California publishes for those workers, but it is not the detailed occupation's estimate.
  ``SocAggregation.kind`` and ``aggregation_for`` exist so the interface can label it.
* Mapping never climbs past the broad group. O*NET reports, for instance, that wage data for
  45-3031 Fishing and Hunting Workers is collected under 45-0000, an entire major group.
  A major group is not an occupation and its median wage means nothing to a trainee, so a
  code whose only aggregate sits above broad-group level gets no row here and returns None.

Sources, all accessed 2026-08-04:

* 2018 SOC structure, https://www.bls.gov/soc/2018/soc_structure_2018.xlsx -- establishes
  the broad group above each detailed occupation, and establishes that the five hybrid
  targets below are not SOC codes, since they appear nowhere in it.
* 2010-to-2018 SOC crosswalk, https://www.bls.gov/soc/2018/soc_2010_to_2018_crosswalk.xlsx
  -- used to rule out a revision mismatch as the explanation.
* BLS OEWS occupation profiles, ``https://www.bls.gov/oes/current/oes<digits>.htm`` -- each
  hybrid profile states "This occupation includes the 2018 SOC occupations ...".
* O*NET OnLine and My Next Move data-source notes, e.g.
  https://www.onetonline.org/link/summary/31-1121.00 and
  https://www.mynextmove.org/help/data/31-1121.00 -- state the same relation from the other
  end, one source code at a time ("BLS wage data was collected under the 2018 SOC
  occupation 31-1120 (Home Health and Personal Care Aides)"), which is what allowed every
  row below to be confirmed individually rather than inferred from a group definition.
"""

from __future__ import annotations

import re
from collections.abc import Container, Iterable, Mapping
from dataclasses import dataclass
from typing import Final, Literal

MappingKind = Literal["soc_broad_group", "bls_hybrid_occupation"]
"""How the target is justified.

``soc_broad_group``
    The target is the source's own parent in the 2018 SOC hierarchy. Containment is part of
    the classification and needs no further argument.
``bls_hybrid_occupation``
    The target is not an SOC code. It exists only in the BLS publication taxonomy, which
    defines it as the union of named 2018 SOC occupations because BLS cannot estimate them
    separately.
"""

_BROAD_GROUP_MEMBERS: Final[Mapping[str, tuple[str, ...]]] = {
    # Buyers and Purchasing Agents
    "13-1020": ("13-1021", "13-1022", "13-1023"),
    # Property Appraisers and Assessors
    "13-2020": ("13-2022", "13-2023"),
    # Clinical Laboratory Technologists and Technicians
    "29-2010": ("29-2011", "29-2012"),
    # Home Health and Personal Care Aides
    "31-1120": ("31-1121", "31-1122"),
    # Tour and Travel Guides
    "39-7010": ("39-7011", "39-7012"),
    # Miscellaneous Construction and Related Workers
    "47-4090": ("47-4091", "47-4099"),
    # Miscellaneous Assemblers and Fabricators
    "51-2090": ("51-2091", "51-2092", "51-2099"),
}
"""Broad groups EDD publishes in place of their detailed members, and every member.

Members are listed exhaustively from the SOC structure rather than only the ones seen in a
particular ETP snapshot: the federal feed is refreshed quarterly and a partial table would
reopen the gap for whichever sibling appears next.
"""

_HYBRID_MEMBERS: Final[Mapping[str, tuple[str, ...]]] = {
    # Substance Abuse, Behavioral Disorder, and Mental Health Counselors
    "21-1018": ("21-1011", "21-1014"),
    # Special Education Teachers, Kindergarten and Elementary School
    "25-2052": ("25-2055", "25-2056"),
    # Teaching Assistants, Except Postsecondary
    "25-9045": ("25-9042", "25-9043", "25-9049"),
    # Electrical, Electronic, and Electromechanical Assemblers, Except Coil Winders,
    # Tapers, and Finishers
    "51-2028": ("51-2022", "51-2023"),
    # First-Line Supervisors of Transportation and Material Moving Workers, Except
    # Aircraft Cargo Handling Supervisors
    "53-1047": ("53-1042", "53-1043", "53-1044", "53-1049"),
}
"""BLS hybrid publication codes EDD reports, and the 2018 SOC occupations each subsumes.

Membership is quoted from the BLS OEWS profile for each target and cross-checked against the
O*NET data-source note on each source, so both directions of every row were read.
"""


@dataclass(frozen=True, slots=True)
class SocAggregation:
    """A detailed occupation and the aggregate published in its place.

    ``target`` is a code to look up, never a code to display a title from: for 53-1047 the
    EDD title is an abbreviation of the BLS one, and the record found in the EDD table is
    the only title a reader should ever see.
    """

    source: str
    target: str
    kind: MappingKind


def _build() -> Mapping[str, SocAggregation]:
    groups: tuple[tuple[MappingKind, Mapping[str, tuple[str, ...]]], ...] = (
        ("soc_broad_group", _BROAD_GROUP_MEMBERS),
        ("bls_hybrid_occupation", _HYBRID_MEMBERS),
    )
    table: dict[str, SocAggregation] = {}
    for kind, members_by_target in groups:
        for target, members in members_by_target.items():
            for source in members:
                table[source] = SocAggregation(source=source, target=target, kind=kind)
    return table


AGGREGATIONS: Final[Mapping[str, SocAggregation]] = _build()
"""Every detailed 2018 SOC code EDD reports only inside a larger published occupation."""

_SOC = re.compile(r"^(\d{2}-\d{4})(?:\.\d{2})?$")


def _canonical(code: str) -> str | None:
    """Return ``code`` as ``XX-XXXX``, or None if it is not a usable SOC code.

    Accepts the O*NET-SOC detail suffix (``31-1121.00``) because the O*NET sources used to
    justify this table are written that way. It does *not* re-implement the ETP feed's
    8-digit zero-padding, which ``dol_etp._soc_codes`` has already undone by the time a code
    reaches here; anything else unrecognised returns None rather than raising, so a single
    malformed feed value cannot take down a build.
    """
    match = _SOC.match(code.strip())
    return match.group(1) if match else None


def aggregation_for(code: str) -> SocAggregation | None:
    """Return the aggregate published in place of ``code``, or None if it stands alone.

    None covers three different situations the caller cannot distinguish and should not try
    to: the code is published under its own name, the code has no defensible aggregate, or
    the string is not a SOC code at all.
    """
    canonical = _canonical(code)
    return None if canonical is None else AGGREGATIONS.get(canonical)


def resolve_published_soc(code: str, published: Container[str]) -> str | None:
    """Return the code to look up in the EDD occupation table, or None.

    ``published`` is the set of codes the current EDD snapshot actually carries. It is a
    required argument rather than a baked-in assumption because EDD re-publishes these files
    every projection cycle: if a target disappears, or a target's members start being
    published separately, this returns None or the exact code instead of quietly attaching a
    row that is no longer there.
    """
    canonical = _canonical(code)
    if canonical is None:
        return None
    if canonical in published:
        return canonical
    aggregation = AGGREGATIONS.get(canonical)
    if aggregation is not None and aggregation.target in published:
        return aggregation.target
    return None


def resolve_published_socs(codes: Iterable[str], published: Container[str]) -> tuple[str, ...]:
    """Resolve a program's SOC codes, dropping unresolvable ones and de-duplicating.

    Order is preserved because the ETP feed lists a program's occupations in its own
    priority order, and two codes on one program can resolve to the same aggregate -- a
    home health aide programme tagged both 31-1121 and 31-1122 must not show the same
    occupation twice.
    """
    resolved: list[str] = []
    for code in codes:
        target = resolve_published_soc(code, published)
        if target is not None and target not in resolved:
            resolved.append(target)
    return tuple(resolved)
