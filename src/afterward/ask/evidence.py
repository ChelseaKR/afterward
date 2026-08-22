"""The records the model is handed, as typed facts and as text.

One structure, two readers. The model reads :meth:`EvidencePack.render`, a plain text
listing in which every field carries its record id and its published value, or the words
NOT REPORTED. The verifier reads the same pack's :class:`Fact` objects and checks the model's
claims against them. Because both come from the same object, the model cannot be shown a
value the verifier does not know about, and a suppressed cell is visible to both as
suppressed rather than absent.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from afterward.ask.dataset import OUTCOME_MEASURES, Dataset, RegionHit
from afterward.ask.query import QueryResult

PEERS_ID = "PEERS"

QUARTER = "quarter"
ANNUAL = "annual"


@dataclass(frozen=True)
class Fact:
    """One published field: its value (``None`` is a real state), what kind, and its period."""

    field: str
    value: Any
    kind: str
    """One of ``rate`` (0..1), ``money``, ``percent``, ``count``, ``weeks``, ``hours``, ``text``,
    ``flag``."""
    period: str | None = None
    """``quarter`` for WIOA earnings, ``annual`` for EDD wages, else ``None``."""
    suppressed: bool = False
    """True when the record could carry this measure and the dataset says null."""
    note: str | None = None


@dataclass
class Record:
    id: str
    kind: str
    name: str
    facts: dict[str, Fact] = field(default_factory=dict)
    names: list[str] = field(default_factory=list)
    """Free text on the record (program name, provider) whose digits are not claims."""
    links: list[str] = field(default_factory=list)

    def fact(self, name: str) -> Fact | None:
        return self.facts.get(name)

    def suppressed_fields(self) -> list[str]:
        return [f.field for f in self.facts.values() if f.suppressed]


@dataclass
class EvidencePack:
    language: str
    records: dict[str, Record] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    region: RegionHit | None = None

    def record(self, record_id: str) -> Record | None:
        return self.records.get(record_id)

    def render(self) -> str:
        lines: list[str] = []
        if self.notes:
            lines.append("NOTES: " + "; ".join(self.notes))
        if self.region is not None:
            where = self.region.area_name or f"city of {self.region.city}"
            lines.append(f"REGION: {where} ({self.region.matched_on})")
        if not self.records:
            lines.append("No records matched.")
        for record in self.records.values():
            lines.extend(_render_record(record))
        return "\n".join(lines)


def build_pack(result: QueryResult, dataset: Dataset) -> EvidencePack:
    pack = EvidencePack(language=result.query.language, region=result.resolution.region)
    pack.notes = list(_notes(result))
    for program in result.programs:
        record = program_record(program)
        pack.records[record.id] = record
    for occupation in result.occupations:
        record = occupation_record(occupation, result.resolution.region)
        pack.records[record.id] = record
    peers = peers_record(dataset.peer_medians())
    if peers.facts:
        pack.records[peers.id] = peers
    return pack


def _notes(result: QueryResult) -> list[str]:
    notes = list(result.notes)
    res = result.resolution
    if res.unresolved_occupation_terms:
        notes.append(
            "terms not in the occupation vocabulary: " + ", ".join(res.unresolved_occupation_terms)
        )
    if res.unresolved_region_terms:
        notes.append(
            "places not among the dataset's areas: " + ", ".join(res.unresolved_region_terms)
        )
    if result.candidates > len(result.programs):
        notes.append(
            f"{result.candidates} programs matched; the first {len(result.programs)} are listed"
        )
    for key, count in result.excluded.as_dict().items():
        if count:
            notes.append(f"{count} programs left out because {key.replace('_', ' ')}")
    return notes


# -- programs ----------------------------------------------------------------------------


def program_record(program: Mapping[str, Any]) -> Record:
    record = Record(
        id=f"P:{program['uuid']}",
        kind="program",
        name=program.get("program_name") or "",
        names=[program.get("program_name") or "", program.get("provider_name") or ""],
    )
    f = record.facts
    f["provider_name"] = Fact("provider_name", program.get("provider_name"), "text")
    f["entity_type"] = Fact("entity_type", program.get("entity_type"), "text")
    f["program_format"] = Fact("program_format", program.get("program_format"), "text")
    location = program.get("location") or {}
    f["location.city"] = Fact("location.city", location.get("city"), "text")
    region = program.get("region")
    f["region.area_name"] = Fact(
        "region.area_name",
        region["area_name"] if region else None,
        "text",
        note=None
        if region
        else "the city is not one EDD publishes an area for; statewide figures apply",
    )
    _cost_facts(program.get("cost") or {}, f)
    _length_facts(program.get("length") or {}, f)
    _outcome_facts(program.get("outcomes") or {}, f)
    for occ in program.get("occupations") or []:
        record.links.append(f"O:{occ['soc_code']} ({occ['match']['kind']})")
    return record


def _cost_facts(cost: Mapping[str, Any], f: dict[str, Fact]) -> None:
    complete = bool(cost.get("total_is_complete"))
    for key in ("tuition", "supplies", "total_out_of_pocket"):
        value = cost.get(key)
        note = None
        if key == "total_out_of_pocket" and value is not None and not complete:
            note = "a component was not reported, so this total is a floor, not the cost"
        f[f"cost.{key}"] = Fact(f"cost.{key}", value, "money", suppressed=value is None, note=note)


def _length_facts(length: Mapping[str, Any], f: dict[str, Fact]) -> None:
    competency = bool(length.get("competency_based"))
    f["length.competency_based"] = Fact("length.competency_based", competency, "flag")
    for key, kind in (("weeks", "weeks"), ("hours", "hours")):
        value = length.get(key)
        note = (
            "competency-based: no fixed length by design" if value is None and competency else None
        )
        f[f"length.{key}"] = Fact(
            f"length.{key}", value, kind, suppressed=value is None and not competency, note=note
        )


def _outcome_facts(outcomes: Mapping[str, Any], f: dict[str, Fact]) -> None:
    f["outcomes.reported"] = Fact("outcomes.reported", bool(outcomes.get("reported")), "flag")
    for key in ("total_served", "total_exited", "total_completed", "credentials_earned"):
        value = outcomes.get(key)
        f[f"outcomes.{key}"] = Fact(f"outcomes.{key}", value, "count", suppressed=value is None)
    f["outcomes.completion_rate"] = Fact(
        "outcomes.completion_rate",
        outcomes.get("completion_rate"),
        "rate",
        suppressed=outcomes.get("completion_rate") is None,
    )
    f["outcomes.employment_rate_q2"] = Fact(
        "outcomes.employment_rate_q2",
        outcomes.get("employment_rate_q2"),
        "rate",
        suppressed=outcomes.get("employment_rate_q2") is None,
        note="share employed in the 2nd quarter after leaving",
    )
    f["outcomes.median_earnings"] = Fact(
        "outcomes.median_earnings",
        outcomes.get("median_earnings"),
        "money",
        period=QUARTER,
        suppressed=outcomes.get("median_earnings") is None,
        note="ONE QUARTER of earnings, the 2nd quarter after leaving; not a yearly salary",
    )
    cohort = outcomes.get("cohort") or {}
    f["outcomes.cohort.attributable"] = Fact(
        "outcomes.cohort.attributable",
        bool(cohort.get("attributable", True)),
        "flag",
        note=None
        if cohort.get("attributable", True)
        else "these figures cover more than this program; do not compare them",
    )


# -- occupations -------------------------------------------------------------------------


def occupation_record(occupation: Mapping[str, Any], region: RegionHit | None) -> Record:
    record = Record(id=f"O:{occupation['soc_code']}", kind="occupation", name=occupation["title"])
    f = record.facts
    f["title"] = Fact("title", occupation["title"], "text")
    f["period"] = Fact("period", occupation.get("period"), "text")
    _projection_facts(occupation, f, prefix="")
    f["entry_level_education"] = Fact(
        "entry_level_education", occupation.get("entry_level_education"), "text"
    )
    spanish = occupation.get("spanish") or {}
    f["spanish.title"] = Fact("spanish.title", spanish.get("title"), "text")
    row = _region_row(occupation, region)
    if region is not None and region.area_name:
        if row is None:
            f["region"] = Fact(
                "region", None, "text", note="no row for this occupation in the region"
            )
        else:
            f["region.area_name"] = Fact("region.area_name", row["area_name"], "text")
            f["region.period"] = Fact(
                "region.period",
                row.get("period"),
                "text",
                note="the regional projection's own period; it differs from the statewide one",
            )
            _projection_facts(row, f, prefix="region.")
    for related in occupation.get("related") or []:
        record.links.append(
            f"O:{related['soc_code']} (related, {occupation.get('related_source')})"
        )
    return record


def _projection_facts(source: Mapping[str, Any], f: dict[str, Fact], *, prefix: str) -> None:
    wage = source.get("median_annual_wage")
    f[f"{prefix}median_annual_wage"] = Fact(
        f"{prefix}median_annual_wage", wage, "money", period=ANNUAL, suppressed=wage is None
    )
    openings = source.get("total_job_openings")
    f[f"{prefix}total_job_openings"] = Fact(
        f"{prefix}total_job_openings", openings, "count", suppressed=openings is None
    )
    change = source.get("percent_change")
    f[f"{prefix}percent_change"] = Fact(
        f"{prefix}percent_change", change, "percent", suppressed=change is None
    )


def _region_row(
    occupation: Mapping[str, Any], region: RegionHit | None
) -> Mapping[str, Any] | None:
    if region is None or not region.area_name:
        return None
    for row in occupation.get("regions") or []:
        if row.get("area_name") == region.area_name:
            found: Mapping[str, Any] = row
            return found
    return None


# -- peers -------------------------------------------------------------------------------


def peers_record(peer_medians: Mapping[str, Mapping[str, Any]]) -> Record:
    record = Record(
        id=PEERS_ID, kind="peers", name="median of California programs reporting the same measure"
    )
    for measure in OUTCOME_MEASURES:
        peer = peer_medians.get(measure)
        if not peer or peer.get("median") is None:
            continue
        kind = "money" if measure == "median_earnings" else "rate"
        period = QUARTER if measure == "median_earnings" else None
        record.facts[measure] = Fact(measure, peer["median"], kind, period=period)
        record.facts[f"{measure}.reporting"] = Fact(
            f"{measure}.reporting", peer["reporting"], "count"
        )
    return record


# -- rendering ---------------------------------------------------------------------------


def _render_record(record: Record) -> list[str]:
    lines = [f"[{record.id}] {record.kind.upper()}: {record.name}"]
    for fact in record.facts.values():
        lines.append(f"  {fact.field}: {_render_value(fact)}")
    if record.links:
        lines.append("  linked: " + ", ".join(record.links))
    return lines


def _render_value(fact: Fact) -> str:
    if fact.value is None:
        # Only a suppressed measure is NOT REPORTED. A null that means something else -- no
        # fixed length by design, no EDD area for this city -- says what it means instead.
        text = "NOT REPORTED" if fact.suppressed else "none"
    elif fact.kind in {"count", "weeks", "hours"} and float(fact.value).is_integer():
        text = f"{int(fact.value):,}"
    elif fact.kind == "rate":
        text = f"{fact.value} ({round(float(fact.value) * 100)}%)"
    elif fact.kind == "money":
        text = f"${float(fact.value):,.0f}"
    elif fact.kind == "percent":
        text = f"{fact.value:+}%"
    elif fact.kind == "flag":
        text = "yes" if fact.value else "no"
    else:
        text = str(fact.value)
    if fact.period == QUARTER:
        text += " [one quarter]"
    elif fact.period == ANNUAL:
        text += " [per year]"
    if fact.note:
        text += f" -- {fact.note}"
    return text
