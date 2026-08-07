"""Project the emitted site dataset into CTDL JSON-LD.

A demonstration export of California ETPL-derived program data as CTDL (Credential
Transparency Description Language) JSON-LD: one ``ceterms:LearningProgram`` per program the
site publishes, one ``ceterms:CredentialOrganization`` per distinct provider name, in a
single JSON-LD graph document. Nothing here is published to, drawn from, or claimed about
any registry; the CTIDs are derived locally (see :func:`entity_ctid`) and the ``@id`` URIs
live under this project's own host.

Every class and property emitted was checked against the term definitions Credential Engine
publishes at credreg.net, fetched 2026-08-06 from
``https://credreg.net/ctdl/terms/<Term>/json``:

* ``ceterms:LearningProgram`` -- "Set of learning opportunities that leads to an outcome,
  usually a credential like a degree or certificate." Every record in this dataset is a
  state-listed training program, so every entity uses this class; ``ceterms:Course`` exists
  for a "single structured sequence" and the source data does not distinguish courses, so it
  is never used here. (Term status ``vs:unstable`` as fetched.)
* ``ceterms:offeredBy`` -- "Agent that offers the resource", range includes
  ``ceterms:CredentialOrganization``. Chosen over ``ceterms:ownedBy``, whose definition is
  "agent with an enforceable claim or legal title to the resource": the ETPL asserts that a
  provider offers a program, and says nothing about legal title, so ``ownedBy`` would be a
  stronger claim than the source makes.
* ``ceterms:occupationType`` -- sub-property of ``ceterms:credentialAlignment``, range
  ``ceterms:CredentialAlignmentObject``; its usage note names SOC among the expected
  frameworks. Alignment objects carry ``ceterms:codedNotation`` for the SOC code the source
  filed, and ``ceterms:targetNodeName`` only when this dataset joined that exact code to an
  EDD occupation title (an aggregation match names a broader group, not the filed code, so
  its title is not used).
* ``ceterms:estimatedCost`` -- range ``ceterms:CostProfile`` with ``ceterms:price`` and
  ``ceterms:currency``. Emitted only when the source's cost total is complete: when a
  component was suppressed the total is a floor, and a floor published as "the price" would
  drop the caveat the dataset carries.
* ``ceterms:aggregateData`` -- range ``ceterms:AggregateDataProfile``, which is the only
  place core CTDL accepts summary outcome statistics (``ceterms:medianEarnings``,
  ``ceterms:numberAwarded``, ``ceterms:jobsObtained``). Note recorded for the record: as
  fetched, ``ceterms:aggregateData`` lists ``ceterms:LearningOpportunityProfile`` in its
  domain and ``ceterms:LearningProgram`` is a subclass of it, but credreg.net's generated
  per-class property list for LearningProgram does not include ``aggregateData``. This
  export relies on the subclass relation. Completion and employment *rates*, which the
  source reports, have no AggregateDataProfile property at all and would need the QData
  layer (``qdata:DataSetProfile``); they are deliberately not projected, and the coverage
  statement says so rather than leaving them to be presumed absent from the source.

The honesty rules of the rest of this codebase transfer whole:

* A suppressed or unreported measure is *absent* from the CTDL entity. Never zero, never a
  placeholder. :func:`projection_problems` re-derives this from the source payloads and the
  emitted graph, and the export refuses to write output that violates it.
* No property is emitted on inference. No language tag beyond the structural one the
  context requires, no lifecycle status, no organization address (the location on a record
  is the program's, not necessarily the provider's), no controlled-vocabulary concept from
  vocabularies that could not be fetched as data (credreg.net serves its concept schemes as
  HTML pages), and no provider identity beyond the name the source filed.
* Every emitted term must be defined in the vendored copy of the CTDL context
  (``ctdl-context.json``, provenance in ``ctdl-context.source.json``);
  :func:`unknown_term_problems` enforces it mechanically, so an invented term cannot ship.
* The coverage statement written beside the export is recomputed from the emitted graph by
  :func:`ctdl_coverage_problems` in the same spirit as ``check_coverage_counts`` in
  :mod:`afterward.build`: a figure the artifact contradicts refuses to publish.

Determinism: same input, byte-identical output. Entities are ordered by CTID, dict key
order is fixed by construction, and nothing derived from the wall clock is written -- the
only date in the output is the dataset's own ``snapshot_date``.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

CTDL_CONTEXT_URL: Final = "https://credreg.net/ctdl/schema/context/json"
"""The canonical CTDL context, referenced (not inlined) by every exported document."""

VENDORED_CONTEXT_PATH: Final = Path(__file__).parent / "ctdl-context.json"

RESOURCE_BASE: Final = "https://afterward.chelseakr.com/ctdl/resources/"
"""Where exported ``@id`` URIs live: this project's own host.

Deliberately not ``credentialengineregistry.org``. A registry-shaped URI would imply these
records exist in the Credential Registry, and they do not.
"""

CTID_NAMESPACE: Final = uuid.uuid5(uuid.NAMESPACE_URL, "https://afterward.chelseakr.com/ctdl")
"""Fixed UUIDv5 namespace for locally derived CTIDs. See :func:`entity_ctid`."""

SOC_FRAMEWORK: Final = "https://www.bls.gov/soc/2018/"
SOC_FRAMEWORK_NAME: Final = "Standard Occupational Classification (2018)"
"""Both sources are on the 2018 SOC; :mod:`afterward.sources.soc_vintage` establishes it."""

ETP_SOURCE_URL: Final = "https://www.trainingproviderresults.gov/"
"""Public face of the DOL ETP scorecard data behind every outcome figure (PROVENANCE D1)."""

LANG: Final = "en"
"""Key for CTDL language-mapped strings. The context types ``ceterms:name`` and friends as
``@container: @language``, so a language key is structurally required to say anything."""

OUTCOME_DESCRIPTION: Final = (
    "WIOA Eligible Training Provider performance measures reported for this program "
    "to the U.S. Department of Labor. Measures the provider did not report, or that were "
    "suppressed at the source, are absent from this profile rather than zero."
)
JOBS_OBTAINED_DESCRIPTION: Final = (
    "Program exiters employed in the second quarter after exit, as reported under WIOA."
)
COST_DESCRIPTION: Final = (
    "Total out-of-pocket cost (tuition and supplies) to a student not funded under WIOA, "
    "as reported to the U.S. Department of Labor's Eligible Training Provider scorecard."
)

EMITTED_CLASSES: Final = frozenset(
    {
        "ceterms:LearningProgram",
        "ceterms:CredentialOrganization",
        "ceterms:CredentialAlignmentObject",
        "ceterms:CostProfile",
        "ceterms:AggregateDataProfile",
        "schema:QuantitativeValue",
    }
)
"""Every ``@type`` this export may write. Each one was verified against its credreg.net
term definition (URLs in the module docstring); :func:`unknown_term_problems` refuses any
other."""

AGGREGATE_MEASURES: Final = (
    ("ceterms:medianEarnings", "median_earnings"),
    ("ceterms:numberAwarded", "credentials_earned"),
    ("ceterms:jobsObtained", "employed_q2"),
)
"""CTDL property on the AggregateDataProfile -> source outcome field it projects."""

COUNT_MEASURES: Final = frozenset({"credentials_earned", "employed_q2"})
"""Source measures that are headcounts and must be emitted as integers
(``ceterms:numberAwarded`` is typed ``xsd:integer`` in the context)."""

RATE_MEASURES_NOT_PROJECTED: Final = ("completion_rate", "employment_rate_q2")
"""Reported by the source, not projectable into core CTDL. AggregateDataProfile has no
rate property; expressing these would need ``qdata:DataSetProfile``, which is out of scope
for a demonstration export. Counted in the coverage statement so their absence reads as a
mapping limit, not as missing source data."""


def load_vendored_context() -> dict[str, Any]:
    """The ``@context`` mapping from the vendored CTDL context file."""
    document = json.loads(VENDORED_CONTEXT_PATH.read_text(encoding="utf-8"))
    context: dict[str, Any] = document["@context"]
    return context


def entity_ctid(kind: str, identifier: str) -> str:
    """A deterministic, locally derived CTID: ``ce-`` plus UUIDv5 over a fixed namespace.

    ``kind`` partitions the namespace ("learning-program", "credential-organization") so a
    program and a provider can never collide, and ``identifier`` is the stable identity the
    source data carries -- the DOL-assigned program UUID, or the provider name exactly as
    filed. Re-exporting the same dataset therefore reproduces the same CTIDs byte for byte.

    These are demonstration CTIDs. A real CTID is assigned when a resource is published to
    the Credential Registry, which these records are not; the ``ce-`` shape is kept only so
    the documents exercise the same identifier format registry tooling expects. One known
    limit, on the record: credreg.net's CTID page (``https://credreg.net/ctdl/ctid``,
    retrieved 2026-08-06) says a CTID is "a standard UUID v4 prefixed with ce-", and a v4
    is random -- which is exactly what a deterministic re-export cannot use. This export
    chooses v5 so identity survives re-export; a record actually published to a registry
    would carry that registry's assigned v4 CTID instead.
    """
    if not identifier:
        raise ValueError(
            f"refusing to derive a CTID for a {kind} with no identifier: an invented "
            "identity would survive re-export and read as a stable fact about the source"
        )
    return "ce-" + str(uuid.uuid5(CTID_NAMESPACE, f"{kind}:{identifier}"))


def program_ctid(source_uuid: str) -> str:
    return entity_ctid("learning-program", source_uuid)


def organization_ctid(provider_name: str) -> str:
    """CTID for a provider, keyed on the name exactly as the source filed it.

    The name is the only provider identity the dataset carries, so it is the only honest
    key: two spellings of one school stay two organizations rather than being merged on a
    similarity judgement this codebase refuses to make.
    """
    return entity_ctid("credential-organization", provider_name)


def _lang(text: str) -> dict[str, str]:
    return {LANG: text}


def _as_count(value: float, field: str, where: str) -> int:
    """A source headcount as the integer CTDL requires, refusing to round.

    ``int(9.4)`` would publish a number nobody reported; a non-integral headcount is a data
    error upstream and stops the export instead.
    """
    if value != int(value):
        raise ValueError(f"{where}.{field}: {value!r} is not a whole count; refusing to round")
    return int(value)


def project_organization(provider_name: str) -> dict[str, Any]:
    """One ``ceterms:CredentialOrganization`` per distinct provider name.

    Name only. The dataset asserts nothing else about the organization itself: the location
    on each program record is the program's, an address put here would be a guess, and
    ``entity_type`` values like "Higher Ed: Associate's Degree" do not map onto CTDL's
    agentSector concept scheme without judgement calls (and credreg.net serves that scheme
    as an HTML page, not fetchable data to check against).
    """
    ctid = organization_ctid(provider_name)
    return {
        "@type": "ceterms:CredentialOrganization",
        "@id": RESOURCE_BASE + ctid,
        "ceterms:ctid": ctid,
        "ceterms:name": _lang(provider_name),
    }


def _exact_titles(payload: Mapping[str, Any]) -> dict[str, str]:
    """SOC code -> occupation title, for exact matches only.

    An aggregation match's title names a broader BLS group, not the code the program filed,
    so using it as ``targetNodeName`` would label the filed code with another node's name.
    """
    return {
        occupation["soc_code"]: occupation["title"]
        for occupation in payload.get("occupations") or []
        if occupation["match"]["kind"] == "exact" and occupation.get("title")
    }


def _occupation_alignments(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    titles = _exact_titles(payload)
    alignments: list[dict[str, Any]] = []
    for code in payload.get("soc_codes") or []:
        alignment: dict[str, Any] = {
            "@type": "ceterms:CredentialAlignmentObject",
            "ceterms:framework": SOC_FRAMEWORK,
            "ceterms:frameworkName": _lang(SOC_FRAMEWORK_NAME),
            "ceterms:codedNotation": code,
        }
        if code in titles:
            alignment["ceterms:targetNodeName"] = _lang(titles[code])
        alignments.append(alignment)
    return alignments


def _cost_profiles(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The ``ceterms:estimatedCost`` value, or nothing.

    Only a complete total is published as a price. When a cost component was suppressed the
    source total is a floor (see ``Program.total_cost`` in
    :mod:`afterward.sources.dol_etp`), and CTDL's ``ceterms:price`` has no way to say "at
    least" -- so the caveat would be dropped, and the profile is omitted instead. The
    coverage statement counts these omissions. Currency is USD by the source's own terms:
    these are dollar figures filed with a U.S. federal scorecard.
    """
    cost = payload.get("cost") or {}
    total = cost.get("total_out_of_pocket")
    if total is None or not cost.get("total_is_complete"):
        return []
    return [
        {
            "@type": "ceterms:CostProfile",
            "ceterms:description": _lang(COST_DESCRIPTION),
            "ceterms:price": total,
            "ceterms:currency": "USD",
        }
    ]


def _aggregate_data(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The ``ceterms:aggregateData`` value, or nothing.

    One profile, carrying only the measures the source reported. All three suppressed means
    no profile at all: an empty statistics block would read as "measured, and empty".
    """
    outcomes = payload["outcomes"]
    where = str(payload.get("uuid", "<no uuid>"))
    profile: dict[str, Any] = {
        "@type": "ceterms:AggregateDataProfile",
        "ceterms:description": _lang(OUTCOME_DESCRIPTION),
        "ceterms:source": ETP_SOURCE_URL,
    }
    reported = False
    for term, field in AGGREGATE_MEASURES:
        value = outcomes.get(field)
        if value is None:
            continue
        reported = True
        if field in COUNT_MEASURES:
            value = _as_count(value, field, where)
        if term == "ceterms:jobsObtained":
            # Range is schema:QuantitativeValue, and the wrapper is where the number says
            # exactly what it counts.
            profile[term] = [
                {
                    "@type": "schema:QuantitativeValue",
                    "schema:description": _lang(JOBS_OBTAINED_DESCRIPTION),
                    "schema:value": value,
                }
            ]
        else:
            profile[term] = value
    return [profile] if reported else []


def project_program(payload: Mapping[str, Any]) -> dict[str, Any]:
    """One program payload as one ``ceterms:LearningProgram`` entity.

    Absence is meaningful everywhere: a key appears only when the source asserted a value.
    ``ceterms:subjectWebpage`` follows the site's own link-check verdicts -- the URL
    published is the one the site itself publishes (possibly https-upgraded or sent to the
    provider's front page), and a program whose link the site withholds gets no webpage
    property here either.
    """
    ctid = program_ctid(str(payload["uuid"]))
    entity: dict[str, Any] = {
        "@type": "ceterms:LearningProgram",
        "@id": RESOURCE_BASE + ctid,
        "ceterms:ctid": ctid,
        "ceterms:name": _lang(payload["program_name"]),
    }
    if payload.get("description"):
        entity["ceterms:description"] = _lang(payload["description"])
    link = payload.get("provider_link") or {}
    if link.get("linked") and link.get("href"):
        entity["ceterms:subjectWebpage"] = link["href"]
    entity["ceterms:offeredBy"] = [RESOURCE_BASE + organization_ctid(payload["provider_name"])]
    alignments = _occupation_alignments(payload)
    if alignments:
        entity["ceterms:occupationType"] = alignments
    costs = _cost_profiles(payload)
    if costs:
        entity["ceterms:estimatedCost"] = costs
    aggregate = _aggregate_data(payload)
    if aggregate:
        entity["ceterms:aggregateData"] = aggregate
    return entity


def project_graph(payloads: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The whole export as one JSON-LD graph document, deterministically ordered.

    Organizations first (owner before owned reads better in a diff), each block sorted by
    CTID. The order is a function of the data alone, so the same dataset always serializes
    to the same bytes.
    """
    organizations = {
        organization_ctid(p["provider_name"]): project_organization(p["provider_name"])
        for p in payloads
    }
    programs: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        entity = project_program(payload)
        ctid = str(entity["ceterms:ctid"])
        if ctid in programs:
            raise ValueError(
                f"two programs derive the same CTID {ctid}: the source identifier is not "
                "the stable identity this export assumes"
            )
        programs[ctid] = entity
    graph = [organizations[k] for k in sorted(organizations)]
    graph += [programs[k] for k in sorted(programs)]
    return {"@context": CTDL_CONTEXT_URL, "@graph": graph}


def _is_language_map(key: str, context: Mapping[str, Any]) -> bool:
    """Whether the context types this term's value as a language map.

    Language maps are leaves: their keys are language tags, not terms to be checked.
    """
    entry = context.get(key)
    return isinstance(entry, Mapping) and entry.get("@container") == "@language"


def _walk_terms(node: Any, path: str, context: Mapping[str, Any], problems: list[str]) -> None:
    """Collect unknown-term problems from one node of an emitted document, recursively."""
    if isinstance(node, list):
        for index, item in enumerate(node):
            _walk_terms(item, f"{path}[{index}]", context, problems)
        return
    if not isinstance(node, Mapping):
        return
    declared = node.get("@type")
    if declared is not None and declared not in EMITTED_CLASSES:
        problems.append(f"{path}: @type {declared!r} is not a class this export vetted")
    for key, value in node.items():
        if key.startswith("@"):
            continue
        if ":" in key and key not in context:
            problems.append(f"{path}: {key} is not defined in the CTDL context")
        if not _is_language_map(key, context):
            _walk_terms(value, f"{path}.{key}", context, problems)


def unknown_term_problems(document: Mapping[str, Any], context: Mapping[str, Any]) -> list[str]:
    """Every emitted key or type the CTDL context does not define.

    This is the mechanical form of "do not map from memory": a term invented in code fails
    here against the vendored schema rather than shipping and failing in a validator
    somewhere else, later, silently.
    """
    problems: list[str] = []
    for index, entity in enumerate(document.get("@graph", [])):
        _walk_terms(entity, f"@graph[{index}]", context, problems)
    return problems


def check_ctdl_terms(document: Mapping[str, Any], context: Mapping[str, Any]) -> None:
    """Refuse to write a document that uses a term the schema does not define."""
    problems = unknown_term_problems(document, context)
    if problems:
        shown = problems[:10]
        more = f" (and {len(problems) - len(shown)} more)" if len(problems) > len(shown) else ""
        raise ValueError(
            "export emits terms the CTDL context does not define: " + "; ".join(shown) + more
        )


def _measure_problems(
    where: str, outcomes: Mapping[str, Any], profiles: Sequence[Mapping[str, Any]]
) -> list[str]:
    """How one program's emitted statistics diverge from its source outcomes."""
    problems: list[str] = []
    profile = profiles[0] if profiles else {}
    for term, field in AGGREGATE_MEASURES:
        source = outcomes.get(field)
        if term == "ceterms:jobsObtained":
            wrappers = profile.get(term)
            emitted = wrappers[0].get("schema:value") if wrappers else None
        else:
            emitted = profile.get(term)
        if source is None and emitted is not None:
            problems.append(f"{where}: {term} is {emitted!r} where the source reports nothing")
        elif source is not None and emitted is None:
            problems.append(f"{where}: {term} is absent where the source reports {source!r}")
        elif source is not None and emitted != source:
            problems.append(f"{where}: {term} is {emitted!r}, the source says {source!r}")
    return problems


def projection_problems(
    payloads: Sequence[Mapping[str, Any]], document: Mapping[str, Any]
) -> list[str]:
    """Every way the emitted graph puts words in the source data's mouth.

    The invariant the rest of this codebase enforces at every boundary, restated for this
    one: a measure appears on the CTDL entity if and only if the source reported it, with
    the value the source reported. "If" rules out the zero-for-suppressed failure -- a
    suppressed measure can never surface as 0 because it can never surface at all -- and
    "only if" rules out losing data in projection without saying so.
    """
    entities = {
        e["ceterms:ctid"]: e
        for e in document.get("@graph", [])
        if e.get("@type") == "ceterms:LearningProgram"
    }
    problems: list[str] = []
    for payload in payloads:
        ctid = program_ctid(str(payload["uuid"]))
        where = str(payload["uuid"])
        entity = entities.get(ctid)
        if entity is None:
            problems.append(f"{where}: no LearningProgram entity in the graph")
            continue
        problems += _measure_problems(
            where, payload["outcomes"], entity.get("ceterms:aggregateData", [])
        )
    if len(entities) != len(payloads):
        problems.append(
            f"graph carries {len(entities)} LearningProgram entities "
            f"for {len(payloads)} source programs"
        )
    return problems


def check_projection(payloads: Sequence[Mapping[str, Any]], document: Mapping[str, Any]) -> None:
    """Refuse to write a graph that asserts a measure the source does not."""
    problems = projection_problems(payloads, document)
    if problems:
        shown = problems[:10]
        more = f" (and {len(problems) - len(shown)} more)" if len(problems) > len(shown) else ""
        raise ValueError(
            "CTDL export diverges from the source outcomes: " + "; ".join(shown) + more
        )


PROGRAM_PROPERTIES: Final = (
    "ceterms:name",
    "ceterms:description",
    "ceterms:subjectWebpage",
    "ceterms:offeredBy",
    "ceterms:occupationType",
    "ceterms:estimatedCost",
    "ceterms:aggregateData",
)
"""LearningProgram properties the coverage statement counts, in publication order."""


def ctdl_coverage(
    document: Mapping[str, Any],
    payloads: Sequence[Mapping[str, Any]],
    snapshot_date: str,
) -> dict[str, Any]:
    """The coverage statement published beside the export, counted from the export itself.

    Same discipline as the site's ``coverage.json``: every figure is derived from the
    artifact it describes at the moment of writing, and :func:`ctdl_coverage_problems`
    recomputes the lot before anything is written. ``not_projected`` names what the source
    reports that this export deliberately does not carry, with the reason -- absence with
    an explanation, rather than absence a reader has to interpret.
    """
    graph: list[Mapping[str, Any]] = list(document.get("@graph", []))
    programs = [e for e in graph if e.get("@type") == "ceterms:LearningProgram"]
    organizations = [e for e in graph if e.get("@type") == "ceterms:CredentialOrganization"]
    profiles = [p for e in programs for p in e.get("ceterms:aggregateData", [])]
    incomplete_costs = sum(
        1
        for p in payloads
        if (p.get("cost") or {}).get("total_out_of_pocket") is not None
        and not (p.get("cost") or {}).get("total_is_complete")
    )
    return {
        "note": (
            "Demonstration export of California ETPL-derived program data as CTDL JSON-LD. "
            "These records are not published to any registry; CTIDs are derived locally "
            "and are not Registry-assigned."
        ),
        "snapshot_date": snapshot_date,
        "source_programs": len(payloads),
        "entities": {
            "ceterms:LearningProgram": len(programs),
            "ceterms:CredentialOrganization": len(organizations),
        },
        "learning_program_properties": {
            term: sum(1 for e in programs if term in e) for term in PROGRAM_PROPERTIES
        },
        "aggregate_data_properties": {
            term: sum(1 for p in profiles if term in p) for term, _ in AGGREGATE_MEASURES
        },
        "not_projected": {
            field: {
                "reported_in_source": sum(
                    1 for p in payloads if p["outcomes"].get(field) is not None
                ),
                "reason": (
                    "core CTDL's AggregateDataProfile has no property for a rate; "
                    "expressing this would need qdata:DataSetProfile, which this "
                    "demonstration does not use"
                ),
            }
            for field in RATE_MEASURES_NOT_PROJECTED
        }
        | {
            "cost_total_incomplete": {
                "reported_in_source": incomplete_costs,
                "reason": (
                    "a cost component was suppressed at the source, so the total is a "
                    "floor; ceterms:price cannot say 'at least', so no cost is published"
                ),
            }
        },
    }


def ctdl_coverage_problems(
    coverage: Mapping[str, Any],
    document: Mapping[str, Any],
    payloads: Sequence[Mapping[str, Any]],
) -> list[str]:
    """Every figure in a coverage statement that the export beside it contradicts."""
    expected = ctdl_coverage(document, payloads, str(coverage.get("snapshot_date")))
    problems: list[str] = []
    for key in (
        "source_programs",
        "entities",
        "learning_program_properties",
        "aggregate_data_properties",
        "not_projected",
    ):
        if coverage.get(key) != expected[key]:
            problems.append(
                f"{key}: says {coverage.get(key)!r}, the export gives {expected[key]!r}"
            )
    return problems


def check_ctdl_coverage(
    coverage: Mapping[str, Any],
    document: Mapping[str, Any],
    payloads: Sequence[Mapping[str, Any]],
) -> None:
    """Refuse to publish a coverage statement the export contradicts."""
    problems = ctdl_coverage_problems(coverage, document, payloads)
    if problems:
        raise ValueError(
            "CTDL coverage statement does not describe the export beside it: " + "; ".join(problems)
        )


@dataclass(frozen=True)
class CtdlExportReport:
    """What one export run produced, for the CLI to say out loud."""

    snapshot_date: str
    programs: int
    organizations: int
    document_path: Path
    coverage_path: Path
    property_counts: dict[str, int]


GRAPH_FILENAME: Final = "learning-programs.jsonld"
COVERAGE_FILENAME: Final = "ctdl-coverage.json"


def _serialize(document: Mapping[str, Any]) -> str:
    """One canonical serialization, so determinism is a property rather than a habit."""
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def export_ctdl(dataset_dir: Path, output_dir: Path) -> CtdlExportReport:
    """Project the emitted dataset at ``dataset_dir`` into CTDL JSON-LD in ``output_dir``.

    Reads the same ``programs.json`` the site serves, so the export can never disagree with
    the site about what the data says. Every guard runs before anything is written: a
    failed check leaves no partial output to mistake for a good one.
    """
    dataset = json.loads((dataset_dir / "programs.json").read_text(encoding="utf-8"))
    site_coverage = json.loads((dataset_dir / "coverage.json").read_text(encoding="utf-8"))
    payloads: list[dict[str, Any]] = dataset["programs"]
    snapshot_date = str(site_coverage["snapshot_date"])

    document = project_graph(payloads)
    check_ctdl_terms(document, load_vendored_context())
    check_projection(payloads, document)
    coverage = ctdl_coverage(document, payloads, snapshot_date)
    check_ctdl_coverage(coverage, document, payloads)

    output_dir.mkdir(parents=True, exist_ok=True)
    document_path = output_dir / GRAPH_FILENAME
    coverage_path = output_dir / COVERAGE_FILENAME
    document_path.write_text(_serialize(document), encoding="utf-8")
    coverage_path.write_text(_serialize(coverage), encoding="utf-8")

    entities: dict[str, int] = coverage["entities"]
    return CtdlExportReport(
        snapshot_date=snapshot_date,
        programs=entities["ceterms:LearningProgram"],
        organizations=entities["ceterms:CredentialOrganization"],
        document_path=document_path,
        coverage_path=coverage_path,
        property_counts=dict(coverage["learning_program_properties"]),
    )
