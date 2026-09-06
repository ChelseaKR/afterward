"""The query layer without the model: named criteria in, records and resolution notes out.

:mod:`afterward.ask` answers a person's sentence in three steps -- a model structures the
words into a :class:`~afterward.ask.query.StructuredQuery`, :func:`~afterward.ask.query.execute`
runs that query over the published dataset, and the verifier checks every claim before anything
is shown. The middle step is the whole of what a case manager or a script wants, and it needs no
model, no provider and no network: the criteria arrive already named.

This module is that middle step given a front door. It builds a ``StructuredQuery`` from
explicit criteria rather than from prose, runs the same executor the assistant runs, and
returns the records with a written account of what each term resolved to.

**Unresolved stays unresolved.** That is the rule this module adds, and it is the reason the
module exists rather than the CLI calling :func:`~afterward.ask.query.execute` directly. The
executor is written for a narrated answer, where an unresolved term becomes a *note* that the
narration is obliged to say out loud: ``region_not_covered`` beside results the model must
introduce as statewide. On a silent path there is nobody to say it.
:func:`~afterward.ask.query.execute` would then answer ``--area Bakersfield`` -- not an EDD
area name -- with programs from the whole of California, because
:func:`~afterward.ask.query._in_region` treats a region of ``None`` as "no region filter". A
filter that silently did not apply, returning a full result set that looks like an answer to
the question asked, is an absence rendered as a value: the same defect this project grades
other people's datasets on. So a named criterion that resolves to nothing ends the query with
``status="unresolved"`` and no records at all.

The criteria that *are* about absence are already handled correctly by the executor and are
left alone: an unreported cost is excluded from a ``--max-cost`` result rather than treated as
zero, a competency-based program is excluded from ``--max-weeks`` rather than counted as short,
and each exclusion is counted so the caller can see how many records the filter could not
speak to.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from afterward.ask.dataset import Dataset
from afterward.ask.query import (
    Format,
    Language,
    Projection,
    QueryResult,
    StructuredQuery,
    execute,
)

__all__ = [
    "SCHEMA_VERSION",
    "Answer",
    "Criteria",
    "Unresolved",
    "answer",
    "structured_query",
]

SCHEMA_VERSION = 1
"""The response shape's version, carried in every answer.

A consumer pins this. It changes when a field is removed or its meaning changes, never when a
field is added, so a reader that ignores unknown keys keeps working.
"""

Status = Literal["ok", "unresolved"]


@dataclass(frozen=True)
class Criteria:
    """What the caller asked for, in terms the dataset can be asked about directly.

    Every field is optional and absent means "no filter", except that an *unresolvable*
    :attr:`occupations` or :attr:`area` is not a missing filter -- see :func:`answer`.
    """

    occupations: tuple[str, ...] = ()
    area: str | None = None
    max_cost: float | None = None
    max_weeks: float | None = None
    min_annual_wage: float | None = None
    program_format: Format = "any"
    projection: Projection = "any"
    reported_only: bool = False
    language: Language = "en"


@dataclass(frozen=True)
class Unresolved:
    """One term the caller named that the dataset holds nothing for."""

    term: str
    kind: Literal["occupation", "area"]

    def as_dict(self) -> dict[str, str]:
        return {"term": self.term, "kind": self.kind}


@dataclass(frozen=True)
class Answer:
    """The records, and everything needed to read them without guessing."""

    status: Status
    programs: list[dict[str, Any]]
    occupations: list[dict[str, Any]]
    unresolved: list[Unresolved]
    resolution_notes: list[str]
    excluded: dict[str, int]
    candidates: int
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """The response, in a shape that is stable across runs of the same inputs."""
        return {
            "schema_version": SCHEMA_VERSION,
            "status": self.status,
            "candidates": self.candidates,
            "programs": self.programs,
            "occupations": self.occupations,
            "unresolved": [u.as_dict() for u in self.unresolved],
            "resolution_notes": self.resolution_notes,
            "excluded": self.excluded,
            "notes": self.notes,
        }

    def as_json(self) -> str:
        """Deterministic JSON: sorted keys, fixed separators, no wall-clock anywhere.

        The same criteria against the same dataset produce the same bytes, which is what makes
        the output safe to diff, cache, or paste into a case note as a record of what was asked.
        """
        return json.dumps(self.as_dict(), sort_keys=True, indent=2, ensure_ascii=False)


def structured_query(criteria: Criteria) -> StructuredQuery:
    """The criteria as the query object the executor already understands.

    ``intent`` is always ``find_programs``: the other intents exist because a person's sentence
    can be about one program or a career pathway, and a caller who wants those asks for them by
    id through the existing verbs rather than by prose here.

    The English-gloss fields stay empty. They exist so a model can offer a translation of a
    Spanish word it was given; a caller naming terms directly has no such second guess to make,
    and inventing one here would be this module doing the guessing it refuses to do.
    """
    return StructuredQuery(
        language=criteria.language,
        intent="find_programs",
        occupation_terms=list(criteria.occupations),
        region_terms=[criteria.area] if criteria.area else [],
        projection=criteria.projection,
        min_annual_wage=criteria.min_annual_wage,
        max_cost=criteria.max_cost,
        max_weeks=criteria.max_weeks,
        format=criteria.program_format,
        requires_reported_outcomes=criteria.reported_only,
    )


def _unresolved_terms(criteria: Criteria, result: QueryResult) -> list[Unresolved]:
    """Every named term the dataset could not place, in the order the caller gave them.

    An occupation term counts as unresolved only when *no* term resolved. One term of three
    finding nothing still leaves a query the dataset can answer, and the surviving terms are
    what it is answered from; the miss is reported in :attr:`Answer.resolution_notes` by the
    executor's own ``occupation_terms_unresolved`` note rather than by emptying the result.
    """
    resolution = result.resolution
    found: list[Unresolved] = []
    if criteria.occupations and not resolution.occupations:
        found.extend(
            Unresolved(term=term, kind="occupation")
            for term in resolution.unresolved_occupation_terms
        )
    if criteria.area and resolution.region is None:
        found.extend(
            Unresolved(term=term, kind="area") for term in resolution.unresolved_region_terms
        )
    return found


def answer(criteria: Criteria, dataset: Dataset) -> Answer:
    """Run the criteria over the dataset, and refuse to widen a filter that did not apply.

    Two ways a named criterion can fail to become a filter, and both end the query rather than
    quietly broadening it:

    * an ``area`` that is neither an EDD projection area nor a city the dataset places programs
      in. The executor would leave ``region=None`` and return the whole state.
    * ``occupations`` where not one term resolved. The executor would fall through to
      :func:`~afterward.ask.query._occupations_by_criteria` and choose occupations from the
      *other* filters -- reasonable when a model is about to explain that it did so, and a
      guess when nobody is going to.

    In both cases the caller gets ``status="unresolved"``, the terms that failed, and no
    records. A caller that wanted the statewide answer can ask for it by leaving ``area`` out,
    which is a different question and now looks like one.
    """
    result = execute(structured_query(criteria), dataset)
    unresolved = _unresolved_terms(criteria, result)
    if unresolved:
        return Answer(
            status="unresolved",
            programs=[],
            occupations=[],
            unresolved=unresolved,
            resolution_notes=result.notes,
            excluded=result.excluded.as_dict(),
            candidates=0,
            notes=["no_records_returned_because_a_named_term_resolved_to_nothing"],
        )
    return Answer(
        status="ok",
        programs=result.programs,
        occupations=result.occupations,
        unresolved=[],
        resolution_notes=result.notes,
        excluded=result.excluded.as_dict(),
        candidates=result.candidates,
    )
