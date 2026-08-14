"""Check the CTDL export with an independent validator, and publish what it found.

:mod:`afterward.ctdl.export` already refuses to write a document whose terms the vendored
CTDL context does not define, and refuses to write a graph that says anything the source
data does not. Both of those checks are written by the same hand as the export, against the
same reading of the same schema, which is exactly the reading a mistake would survive.

So the export is also put through `ctdl-validate <https://pypi.org/project/ctdl-validate/>`_,
a separate tool with its own vendored copies of Credential Engine's schema encodings and its
own citation for every rule it applies. It is consumed here as an ordinary dependency and is
never modified from this repository. Where the two disagree, the disagreement is the finding.

What this module adds on top of running the validator is the part a bare pass/fail hides:

* **Accepted findings are named, with reasons.** :data:`ACCEPTED_CODES` lists every finding
  code this export is allowed to produce and why. Anything else fails
  (:func:`validation_problems`), so a new class of finding cannot arrive quietly -- and an
  accepted one cannot be mistaken for a clean bill of health, because it is counted and
  published rather than filtered out.
* **The validator's own scope is measured, not assumed.** ctdl-validate drives its domain,
  range, inverse and unknown-term checks from the schema encodings it vendors: core CTDL and
  CTDL-ASN. The QData layer has its own schema encoding at
  ``https://credreg.net/qdata/schema/encoding/json``, which those two documents do not
  contain -- so most of the qdata terms this export emits are terms the validator's schema
  index has never heard of, and a term it has never heard of is one it silently declines to
  judge rather than one it approves. :func:`term_scope` asks the validator's own schema index
  about every term the export emits and reports which of them it could judge. A clean run
  over terms nobody checked is not evidence, and publishing the count is the difference
  between saying so and hoping nobody asks.

Nothing here validates against a registry, and nothing is submitted anywhere: ctdl-validate
performs no network access at validation time, by its own stated policy.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from ctdl_validate import __version__ as CTDL_VALIDATE_VERSION
from ctdl_validate import validate_document
from ctdl_validate.findings import Finding, Severity
from ctdl_validate.schema import load_schema

from afterward.ctdl.export import COVERAGE_FILENAME, GRAPH_FILENAME

VALIDATION_FILENAME: Final = "ctdl-validation.json"

TOOL_NAME: Final = "ctdl-validate"
TOOL_URL: Final = "https://pypi.org/project/ctdl-validate/"
TOOL_SOURCE: Final = "https://github.com/ChelseaKR/ctdl-validate"

ACCEPTED_CODES: Final[Mapping[str, str]] = {
    "CTID_NOT_UUIDV4": (
        "Known and documented. credreg.net's CTID page says a CTID is 'a standard UUID v4 "
        "prefixed with ce-', and v4 means random -- the one thing a deterministic re-export "
        "cannot be. This export derives CTIDs as UUIDv5 over a fixed namespace so that "
        "re-exporting the same dataset reproduces the same identifiers, and says so rather "
        "than pretending the tension away. These are demonstration identifiers; a record "
        "actually published to the Credential Registry would carry that registry's assigned "
        "CTID instead. See afterward.ctdl.export.entity_ctid."
    ),
}
"""Every finding code this export is allowed to produce, and why it is allowed.

An entry here is a decision on the record, not a suppression: the finding is still counted,
still published in the validation statement, and still stated on the site. What the entry
buys is that a *different* finding -- one nobody has reasoned about -- fails the run.
"""

NO_NETWORK_NOTE: Final = (
    "Structural validation only, with no network access at validation time and nothing "
    "submitted anywhere. Nothing in this export has been published to the Credential "
    "Registry."
)


def _severity_counts(findings: Sequence[Finding]) -> dict[str, int]:
    """Every severity the validator defines, including the ones that did not occur.

    A severity block that lists only what happened cannot be read as "no errors"; it can
    only be read as "no errors are mentioned". Zeroes are the whole point of the block.
    """
    counted = Counter(f.severity.value for f in findings)
    return {severity.value: counted.get(severity.value, 0) for severity in Severity}


def _code_summaries(findings: Sequence[Finding]) -> dict[str, Any]:
    """One block per finding code: how many, how severe, why accepted, and the cited rule.

    The rule citation travels with the count. A number on its own invites the reader to take
    this project's word for what the rule was; the citation lets them go and read it.
    """
    by_code: dict[str, list[Finding]] = {}
    for finding in findings:
        by_code.setdefault(finding.code, []).append(finding)
    summaries: dict[str, Any] = {}
    for code in sorted(by_code):
        group = by_code[code]
        first = group[0]
        summaries[code] = {
            "severity": first.severity.value,
            "count": len(group),
            "entities": len({f.entity for f in group}),
            "accepted": code in ACCEPTED_CODES,
            "reason": ACCEPTED_CODES.get(code, "not accepted: this run should have failed"),
            "message": first.message,
            "rule": {
                "citation": first.rule.citation,
                "url": first.rule.url,
                "retrieved": first.rule.retrieved,
            },
        }
    return summaries


def emitted_terms(document: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    """Every prefixed class and property name the document actually uses.

    Walked from the emitted document rather than read off the export's own constants, so the
    scope statement below describes what was validated and not what was meant to be.
    """
    classes: set[str] = set()
    properties: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, Mapping):
            return
        declared = node.get("@type")
        for value in [declared] if isinstance(declared, str) else (declared or []):
            if isinstance(value, str) and ":" in value:
                classes.add(value)
        for key, value in node.items():
            if key.startswith("@"):
                continue
            if ":" in key:
                properties.add(key)
            walk(value)

    walk(document.get("@graph", []))
    return sorted(classes), sorted(properties)


def term_scope(document: Mapping[str, Any]) -> dict[str, Any]:
    """Which of the terms this export emits the validator's schema index can judge.

    The honest denominator for every check the validator drives off the schema: domain,
    range, inverse consistency, and unknown-term detection. A term absent from its index is
    not a term that passed. ctdl-validate vendors the core CTDL and CTDL-ASN schema
    encodings; the QData layer publishes its own at
    ``https://credreg.net/qdata/schema/encoding/json``, which neither of those contains.
    """
    schema = load_schema()
    classes, properties = emitted_terms(document)
    known_classes = [term for term in classes if term in schema.classes]
    known_properties = [term for term in properties if term in schema.properties]
    return {
        "note": (
            "ctdl-validate drives its domain, range, inverse and unknown-term checks from "
            "the schema encodings it vendors (core CTDL and CTDL-ASN). Terms outside those "
            "documents are left alone rather than guessed at, so they are neither flagged "
            "nor confirmed. This block counts which of the terms this export emits the "
            "validator was in a position to judge."
        ),
        "classes_emitted": len(classes),
        "classes_in_validator_schema": len(known_classes),
        "classes_not_in_validator_schema": [t for t in classes if t not in schema.classes],
        "properties_emitted": len(properties),
        "properties_in_validator_schema": len(known_properties),
        "properties_not_in_validator_schema": [t for t in properties if t not in schema.properties],
    }


def validation_statement(
    document: Mapping[str, Any],
    findings: Sequence[Finding],
    snapshot_date: str,
) -> dict[str, Any]:
    """The statement published beside the export: what was checked, and what came back.

    Same discipline as ``ctdl-coverage.json``: every figure is counted from the artifact it
    describes at the moment of writing. Nothing here is typed by hand except the reasons.
    """
    return {
        "note": NO_NETWORK_NOTE,
        "snapshot_date": snapshot_date,
        "document": GRAPH_FILENAME,
        "tool": {
            "name": TOOL_NAME,
            "version": CTDL_VALIDATE_VERSION,
            "package": TOOL_URL,
            "source": TOOL_SOURCE,
        },
        "entities_validated": len(document.get("@graph", [])),
        "findings": _severity_counts(findings),
        "codes": _code_summaries(findings),
        "accepted_codes": dict(sorted(ACCEPTED_CODES.items())),
        "validator_scope": term_scope(document),
    }


def validation_problems(statement: Mapping[str, Any]) -> list[str]:
    """Every reason this validation run should stop the build.

    Two: an ERROR of any kind, and a finding code nobody has written a reason for. The second
    is the one that matters over time -- an accepted warning stays a decision only for as
    long as the set of things being accepted cannot grow by itself.
    """
    problems: list[str] = []
    findings: Mapping[str, int] = statement.get("findings", {})
    errors = int(findings.get(Severity.ERROR.value, 0))
    if errors:
        problems.append(f"{errors} ERROR finding(s) from {TOOL_NAME}")
    for code, summary in sorted(statement.get("codes", {}).items()):
        if not summary.get("accepted"):
            problems.append(
                f"{summary.get('count')} {summary.get('severity')} finding(s) of code "
                f"{code}, which is not in ACCEPTED_CODES: decide what it means and record "
                "the decision, or fix the export"
            )
    return problems


def check_validation(statement: Mapping[str, Any]) -> None:
    """Refuse a validation run that found something nobody has reasoned about."""
    problems = validation_problems(statement)
    if problems:
        raise ValueError("CTDL export failed independent validation: " + "; ".join(problems))


@dataclass(frozen=True)
class CtdlValidationReport:
    """What one validation run found, for the CLI to say out loud."""

    snapshot_date: str
    entities: int
    severity_counts: dict[str, int]
    codes: dict[str, Any]
    scope: dict[str, Any]
    statement_path: Path


def _serialize(statement: Mapping[str, Any]) -> str:
    return json.dumps(statement, ensure_ascii=False, indent=2) + "\n"


def validate_export(export_dir: Path) -> CtdlValidationReport:
    """Validate the CTDL export in ``export_dir`` and write the statement beside it.

    Reads the exact bytes ``make ctdl-export`` wrote, so what is validated is what would be
    published. The statement is written only after :func:`check_validation` passes: a failed
    run leaves no statement to mistake for a good one.
    """
    document: dict[str, Any] = json.loads((export_dir / GRAPH_FILENAME).read_text(encoding="utf-8"))
    coverage = json.loads((export_dir / COVERAGE_FILENAME).read_text(encoding="utf-8"))
    snapshot_date = str(coverage["snapshot_date"])

    findings = validate_document(document)
    statement = validation_statement(document, findings, snapshot_date)
    check_validation(statement)

    statement_path = export_dir / VALIDATION_FILENAME
    statement_path.write_text(_serialize(statement), encoding="utf-8")
    return CtdlValidationReport(
        snapshot_date=snapshot_date,
        entities=int(statement["entities_validated"]),
        severity_counts=dict(statement["findings"]),
        codes=dict(statement["codes"]),
        scope=dict(statement["validator_scope"]),
        statement_path=statement_path,
    )
