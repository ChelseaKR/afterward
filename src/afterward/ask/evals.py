"""The eval harness: four committed suites, scored by code, stamped with provenance.

Each suite runs the same :class:`afterward.ask.api.Assistant` a reader would, over the
committed fixture or the real dataset, and scores what happened from the trace -- both what
the model said (before the verifier) and what the reader would have seen (after it). The
second number is the product; the first is how much the verifier is doing.

A results file is written only with provenance: provider, model, prompt version, commit,
date, dataset snapshot. A run on the scripted fake is ``dry_run`` and exists to prove the
harness works; it is never a measurement and a test refuses to let one be committed as one.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from afterward.ask import PROMPT_VERSION
from afterward.ask.api import AskRequest, Assistant, Trace
from afterward.ask.dataset import normalize
from afterward.ask.narrate import Claim
from afterward.ask.query import QueryResult
from afterward.ask.verify import (
    ANNUAL_LABEL,
    BENCHMARK_NOT_PEERS,
    NOT_REPORTED,
    QUARTER_LABEL,
    ZERO_PHRASE,
)

CASES_DIR = Path("evals/cases")
RESULTS_DIR = Path("evals/results")
SUITES = ("structuring", "suppression", "grounding", "comparability")

PROVENANCE_KEYS = (
    "provider",
    "model",
    "prompt_version",
    "commit",
    "date",
    "dataset_snapshot",
    "is_fixture",
)
STATUSES = ("run", "not_run", "dry_run")

STATE_BENCHMARK_FIGURES = (0.27, 27.0, 16978.95, 16979.0, 0.71, 71.0, 0.37, 37.0)
"""DOL's statewide aggregate, which the site does not compare against and the pack never
carries. A narration that uses one of these got it from somewhere other than the evidence."""


@dataclass
class CaseResult:
    id: str
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class SuiteResult:
    name: str
    cases: list[CaseResult]
    summary: dict[str, Any]

    @property
    def passed(self) -> int:
        return sum(1 for c in self.cases if c.passed)

    def as_dict(self) -> dict[str, Any]:
        return {
            "cases": len(self.cases),
            "passed": self.passed,
            "summary": self.summary,
            "per_case": [{"id": c.id, "passed": c.passed, **c.details} for c in self.cases],
        }


def load_cases(suite: str, cases_dir: Path = CASES_DIR) -> list[dict[str, Any]]:
    doc = json.loads((cases_dir / f"{suite}.json").read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = doc["cases"]
    return cases


def run_suite(suite: str, assistant: Assistant, cases: Sequence[Mapping[str, Any]]) -> SuiteResult:
    runner = {
        "structuring": _structuring,
        "suppression": _suppression,
        "grounding": _grounding,
        "comparability": _comparability,
    }[suite]
    return runner(assistant, cases)


def run_all(
    assistant: Assistant, *, suites: Iterable[str] = SUITES, cases_dir: Path = CASES_DIR
) -> dict[str, SuiteResult]:
    return {suite: run_suite(suite, assistant, load_cases(suite, cases_dir)) for suite in suites}


# -- (a) structuring ---------------------------------------------------------------------

SCALAR_FIELDS = ("intent", "language", "projection", "format", "requires_reported_outcomes")
NUMBER_FIELDS = ("min_annual_wage", "max_cost", "max_weeks")


def _structuring(assistant: Assistant, cases: Sequence[Mapping[str, Any]]) -> SuiteResult:
    results: list[CaseResult] = []
    field_hits = 0
    field_total = 0
    vague = 0
    refused = 0
    for case in cases:
        _, trace = assistant.ask_traced(AskRequest(text=case["text"], lang=case.get("lang", "en")))
        if trace.query is None or trace.result is None:
            results.append(CaseResult(case["id"], False, {"error": "no query"}))
            continue
        checks = _structuring_checks(case, trace)
        hits = sum(1 for ok in checks.values() if ok)
        field_hits += hits
        field_total += len(checks)
        details: dict[str, Any] = {"checks": checks, "query": trace.query.model_dump()}
        ok = hits == len(checks)
        if case.get("vague"):
            vague += 1
            guessed = _guessed(case, trace)
            abstained = not guessed and bool(trace.query.clarifications_needed)
            refused += int(abstained)
            details["refused_to_guess"] = abstained
            details["guessed_fields"] = guessed
            ok = ok and abstained
        results.append(CaseResult(case["id"], ok, details))
    summary = {
        "field_accuracy": _rate(field_hits, field_total),
        "fields_scored": field_total,
        "abstention": {
            "vague_cases": vague,
            "refused_to_guess": refused,
            "rate": _rate(refused, vague),
        },
    }
    return SuiteResult("structuring", results, summary)


def _structuring_checks(case: Mapping[str, Any], trace: Trace) -> dict[str, bool]:
    expected = case.get("expected", {})
    query = trace.query
    result = trace.result
    if query is None or result is None:
        return {}
    checks: dict[str, bool] = {}
    for name in SCALAR_FIELDS:
        if name in expected:
            checks[name] = getattr(query, name) == expected[name]
    for name in NUMBER_FIELDS:
        if name in expected:
            checks[name] = _close(getattr(query, name), expected[name])
    if "out_of_scope" in expected:
        checks["out_of_scope"] = bool(query.out_of_scope) == expected["out_of_scope"]
    checks.update(_resolution_checks(expected, result))
    return checks


def _resolution_checks(expected: Mapping[str, Any], result: QueryResult) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    res = result.resolution
    if "resolves_to" in expected:
        found = {h.soc_code for h in res.occupations}
        checks["resolves_to"] = any(soc in found for soc in expected["resolves_to"])
    if "current_resolves_to" in expected:
        found = {h.soc_code for h in res.current_occupations}
        checks["current_resolves_to"] = any(soc in found for soc in expected["current_resolves_to"])
    if "region" in expected:
        region = res.region
        checks["region"] = region is not None and normalize(expected["region"]) in normalize(
            region.area_name or region.city or ""
        )
    if "region_unresolved" in expected:
        checks["region_unresolved"] = res.region is None and bool(res.unresolved_region_terms)
    return checks


def _guessed(case: Mapping[str, Any], trace: Trace) -> list[str]:
    """Fields the model filled that the case says it had no basis to fill."""
    query = trace.query
    if query is None:
        return []
    guessed = []
    for name in case.get("must_be_empty", []):
        value = getattr(query, name)
        if value not in (None, [], False, "any"):
            guessed.append(name)
    return guessed


def _close(actual: float | None, expected: float | None) -> bool:
    if actual is None or expected is None:
        return actual is expected
    return abs(actual - expected) <= max(1.0, 0.01 * abs(expected))


# -- (b) suppression ---------------------------------------------------------------------


def _suppression(assistant: Assistant, cases: Sequence[Mapping[str, Any]]) -> SuiteResult:
    results: list[CaseResult] = []
    model_rendered = 0
    shown_rendered = 0
    acknowledged = 0
    for case in cases:
        _, trace = assistant.ask_traced(
            AskRequest(
                text=case["text"], lang=case.get("lang", "en"), program_id=case.get("program_id")
            )
        )
        if trace.narration is None or trace.verified is None or trace.pack is None:
            results.append(CaseResult(case["id"], False, {"error": "no narration"}))
            continue
        record_id = f"P:{case['program_id']}"
        suppressed = case["suppressed_fields"]
        before = [c for c in trace.narration.claims if record_id in c.cites]
        after = [c for c in trace.verified.accepted if record_id in c.cites]
        rendered_before = [c.text for c in before if _renders_absence(c, suppressed)]
        rendered_after = [c.text for c in after if _renders_absence(c, suppressed)]
        said_not_reported = any(NOT_REPORTED.search(c.text) for c in after)
        model_rendered += int(bool(rendered_before))
        shown_rendered += int(bool(rendered_after))
        acknowledged += int(said_not_reported)
        ok = not rendered_after and said_not_reported
        results.append(
            CaseResult(
                case["id"],
                ok,
                {
                    "model_rendered_absence_as_value": rendered_before,
                    "shown_rendered_absence_as_value": rendered_after,
                    "shown_said_not_reported": said_not_reported,
                    "withheld": trace.verified.withheld_count,
                    "withheld_reasons": dict(trace.verified.reasons),
                    "shown": [c.text for c in after],
                },
            )
        )
    summary = {
        "absence_rendered_as_value_by_model": model_rendered,
        "absence_rendered_as_value_shown": shown_rendered,
        "shown_said_not_reported": acknowledged,
        "shown_rate": _rate(len(cases) - shown_rendered, len(cases)),
    }
    return SuiteResult("suppression", results, summary)


def _renders_absence(claim: Claim, suppressed: Sequence[str]) -> bool:
    """Did this claim give a suppressed measure a value: a declared number, or a zero-phrase?"""
    if any(n.field in suppressed for n in claim.numbers):
        return True
    return bool(ZERO_PHRASE.search(claim.text)) and _mentions_any(claim.text, suppressed)


_MENTION = {
    "outcomes.employment_rate_q2": re.compile(r"employ|emple|trabaj|job|working", re.I),
    "outcomes.median_earnings": re.compile(r"earn|ingreso|gan|paid|pay", re.I),
    "outcomes.completion_rate": re.compile(r"complet|finish|termin|graduat", re.I),
}


def _mentions_any(text: str, suppressed: Sequence[str]) -> bool:
    return any(p.search(text) for f, p in _MENTION.items() if f in suppressed)


# -- (c) grounding -----------------------------------------------------------------------


def _grounding(assistant: Assistant, cases: Sequence[Mapping[str, Any]]) -> SuiteResult:
    results: list[CaseResult] = []
    claims = 0
    verified = 0
    data_claims = 0
    reasons: Counter[str] = Counter()
    for case in cases:
        _, trace = assistant.ask_traced(
            AskRequest(
                text=case["text"],
                lang=case.get("lang", "en"),
                program_id=case.get("program_id"),
                soc_code=case.get("soc_code"),
            )
        )
        if trace.verified is None:
            results.append(CaseResult(case["id"], False, {"error": "no narration"}))
            continue
        v = trace.verified
        claims += v.total
        verified += len(v.accepted)
        data_claims += sum(1 for c in v.accepted if c.kind == "data")
        reasons.update(v.reasons)
        results.append(
            CaseResult(
                case["id"],
                v.withheld_count == 0,
                {
                    "claims": v.total,
                    "verified": len(v.accepted),
                    "withheld_reasons": dict(v.reasons),
                    "withheld": [{"text": w.claim.text, "reasons": w.reasons} for w in v.withheld],
                },
            )
        )
    summary = {
        "claims": claims,
        "verified": verified,
        "verified_rate": _rate(verified, claims),
        "data_claims_shown": data_claims,
        "withheld_reasons": dict(reasons),
    }
    return SuiteResult("grounding", results, summary)


# -- (d) comparability -------------------------------------------------------------------


def _comparability(assistant: Assistant, cases: Sequence[Mapping[str, Any]]) -> SuiteResult:
    results: list[CaseResult] = []
    totals: Counter[str] = Counter()
    for case in cases:
        _, trace = assistant.ask_traced(
            AskRequest(
                text=case["text"], lang=case.get("lang", "en"), program_id=case.get("program_id")
            )
        )
        if trace.narration is None or trace.verified is None:
            results.append(CaseResult(case["id"], False, {"error": "no narration"}))
            continue
        before = trace.narration.claims
        after = trace.verified.accepted
        flags = {
            "invented_benchmark_by_model": [c.text for c in before if _invented_benchmark(c)],
            "invented_benchmark_shown": [c.text for c in after if _invented_benchmark(c)],
            "period_unlabelled_by_model": [c.text for c in before if _period_unlabelled(c)],
            "period_unlabelled_shown": [c.text for c in after if _period_unlabelled(c)],
            "peer_comparison_shown": [c.text for c in after if "PEERS" in c.cites],
        }
        for key, found in flags.items():
            totals[key] += int(bool(found))
        ok = not flags["invented_benchmark_shown"] and not flags["period_unlabelled_shown"]
        if case.get("expect_peer_comparison"):
            ok = ok and bool(flags["peer_comparison_shown"])
        results.append(
            CaseResult(case["id"], ok, {**flags, "withheld_reasons": dict(trace.verified.reasons)})
        )
    summary = {
        key: totals[key]
        for key in (
            "invented_benchmark_by_model",
            "invented_benchmark_shown",
            "period_unlabelled_by_model",
            "period_unlabelled_shown",
            "peer_comparison_shown",
        )
    }
    return SuiteResult("comparability", results, summary)


def _invented_benchmark(claim: Claim) -> bool:
    if BENCHMARK_NOT_PEERS.search(claim.text):
        return True
    declared = {round(n.value, 2) for n in claim.numbers if n.record != "PEERS"}
    return any(round(f, 2) in declared for f in STATE_BENCHMARK_FIGURES) or _state_figure_in_text(
        claim.text
    )


def _state_figure_in_text(text: str) -> bool:
    return bool(re.search(r"\b27\s?%|\$\s?16,97[89]", text))


def _period_unlabelled(claim: Claim) -> bool:
    fields = {n.field for n in claim.numbers}
    quarterly = "outcomes.median_earnings" in fields or "median_earnings" in fields
    annual = any(f.endswith("median_annual_wage") for f in fields)
    if quarterly and not QUARTER_LABEL.search(claim.text):
        return True
    return annual and not ANNUAL_LABEL.search(claim.text)


# -- results and provenance --------------------------------------------------------------


def provenance(
    assistant: Assistant, *, status: str, repo_root: Path | None = None
) -> dict[str, Any]:
    provider = assistant.provider
    return {
        "provider": provider.name if provider else "none",
        "model": provider.model if provider else "none",
        "prompt_version": PROMPT_VERSION,
        "commit": git_commit(repo_root),
        "date": datetime.now(UTC).date().isoformat(),
        "dataset_snapshot": assistant.dataset.snapshot_date,
        "is_fixture": assistant.dataset.is_fixture,
        "status": status,
    }


def git_commit(repo_root: Path | None = None) -> str:
    """The HEAD commit, read from ``.git`` directly so no process is started from a service.

    Walks up from the given root (default: this package's repository) to the first ``.git``,
    follows a symbolic ``HEAD`` through loose refs and ``packed-refs``, and answers
    ``unknown`` rather than guessing when any of that is missing.
    """
    root = _find_git_dir(repo_root or Path(__file__).resolve().parent)
    if root is None:
        return "unknown"
    head = _read(root / "HEAD")
    if not head.startswith("ref: "):
        return head or "unknown"
    ref = head[5:].strip()
    loose = _read(root / ref)
    if loose:
        return loose
    for line in _read(root / "packed-refs").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == ref:
            return parts[0]
    return "unknown"


def _find_git_dir(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        git = candidate / ".git"
        if git.is_dir():
            return git
        if git.is_file():  # a worktree: "gitdir: <path>"
            pointer = _read(git)
            if pointer.startswith("gitdir: "):
                return Path(pointer[8:].strip())
    return None


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def results_document(
    results: Mapping[str, SuiteResult], provenance_block: Mapping[str, Any]
) -> dict[str, Any]:
    status = provenance_block["status"]
    return {
        "status": status,
        "provenance": {k: provenance_block[k] for k in PROVENANCE_KEYS},
        "suites": {name: suite.as_dict() for name, suite in results.items()},
    }


def not_run_document(provenance_block: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {
        "status": "not_run",
        "reason": reason,
        "provenance": {k: provenance_block[k] for k in PROVENANCE_KEYS},
        "suites": {},
    }


def provenance_problems(doc: Mapping[str, Any]) -> list[str]:
    """Why a results document may not be committed as a measurement. Empty means it may."""
    problems: list[str] = []
    status = doc.get("status")
    if status not in STATUSES:
        problems.append(f"status must be one of {STATUSES}, not {status!r}")
    if status == "dry_run":
        problems.append(
            "a dry run on the scripted fake is not a measurement and may not be committed"
        )
    block = doc.get("provenance")
    if not isinstance(block, Mapping):
        return [*problems, "provenance block missing"]
    for key in PROVENANCE_KEYS:
        if key not in block or block[key] in (None, "", "unknown"):
            problems.append(f"provenance.{key} missing")
    if status == "run":
        if block.get("provider") in ("fake", "none"):
            problems.append("a run must name a real provider")
        if not doc.get("suites"):
            problems.append("a run must carry suite results")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(block.get("date", ""))):
            problems.append("provenance.date must be an ISO date")
    return problems


def write_results(path: Path, doc: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _rate(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else round(numerator / denominator, 3)
