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
* Outcome statistics use the QData layer: one ``qdata:DataSetProfile`` per program with
  reported outcomes, carrying ``qdata:Metric`` / ``qdata:Observation`` pairs, linked from
  the program by ``qdata:relevantDataSet`` and back by ``qdata:relevantDataSetFor``. This
  replaced ``ceterms:aggregateData`` on 2026-08-07 following Credential Engine's guidance
  on Schema-Development issue #1080 (filed from this project): the Credential Registry no
  longer accepts ``aggregateData`` for publishing, and the maintainers named
  DataSetProfile-with-Metrics-and-Observations as the supported pattern. Every QData term
  was checked against the schema encoding fetched 2026-08-07 from
  ``https://credreg.net/qdata/schema/encoding/json``:

  - ``qdata:relevantDataSet`` -- "Data Set on which earnings or employment data is based";
    its ``schema:domainIncludes`` names ``ceterms:LearningProgram`` explicitly (no reliance
    on a subclass relation, the gap #1080 was about), and ``qdata:relevantDataSetFor``
    names it in range.
  - ``qdata:Metric`` -- "What is being measured and the method of measurement"; carries
    name, description, and ``qdata:metricType`` drawn from the ``qdata:MetricCategory``
    concept scheme, whose 66 concepts ship as machine-readable data in the same schema
    encoding (unlike core CTDL's HTML-only schemes, so emitting them honors the
    fetchable-as-data rule below).
  - ``qdata:Observation`` -- "Numeric value or category observed for a metric", linked to
    its Metric by ``qdata:isObservationOf``. Headcounts ride ``schema:value``; median
    earnings ride ``qdata:median`` with ``schema:currency`` USD; rates ride
    ``qdata:percentage``. The source's completion and employment rates -- unprojectable
    under AggregateDataProfile, which has no rate property -- are therefore now projected.
    The source validates rates as 0-1 fractions (``clean_rate``); ``qdata:percentage`` is
    "expressed as a percentage", so the projection multiplies by 100 (see
    :func:`_as_percentage`) -- a unit conversion, applied identically by the export and
    the round-trip guard, never a value judgement.
  - ``qdata:DataSetTimeFrame`` is deliberately NOT emitted: the source carries no explicit
    reporting-period start or end dates, and inventing them would violate the no-inference
    rule. The measure descriptions carry the temporal semantics the source does state
    ("second quarter after exit").

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
        "qdata:DataSetProfile",
        "qdata:Metric",
        "qdata:Observation",
    }
)
"""Every ``@type`` this export may write. Each one was verified against its credreg.net
term definition (URLs in the module docstring); :func:`unknown_term_problems` refuses any
other."""

METRICCAT_BASE: Final = "https://credreg.net/qdata/vocabs/metricCat/"
"""IRI base of the ``qdata:MetricCategory`` concept scheme, from the QData context fetched
2026-08-07 (``https://credreg.net/qdata/schema/context/json``). Values are emitted as full
IRIs because the vendored CTDL context does not declare the ``metricCat:`` prefix."""


@dataclass(frozen=True)
class Measure:
    """One source outcome field and the Metric/Observation pair that projects it.

    ``kind`` selects the Observation's value property, per the term definitions:
    ``count`` -> ``schema:value`` (whole headcounts, integer-checked), ``median_usd`` ->
    ``qdata:median`` + ``schema:currency`` USD, ``percentage`` -> ``qdata:percentage``
    (source fraction x 100, see :func:`_as_percentage`).
    """

    field: str
    slug: str
    kind: str
    metric_category: str
    name: str
    description: str


MEASURES: Final = (
    Measure(
        field="median_earnings",
        slug="median-earnings-q2",
        kind="median_usd",
        metric_category="Earnings",
        name="Median earnings, second quarter after exit",
        description=(
            "Median quarterly earnings of program exiters in the second quarter after "
            "exit, in U.S. dollars, as reported under WIOA to the U.S. Department of "
            "Labor's Eligible Training Provider scorecard."
        ),
    ),
    Measure(
        field="credentials_earned",
        slug="credentials-earned",
        kind="count",
        metric_category="CredentialAttainment",
        name="Credentials earned",
        description=("Program exiters who earned a recognized credential, as reported under WIOA."),
    ),
    Measure(
        field="employed_q2",
        slug="employed-q2",
        kind="count",
        metric_category="Employment",
        name="Employed in the second quarter after exit",
        description=JOBS_OBTAINED_DESCRIPTION,
    ),
    Measure(
        field="completion_rate",
        slug="completion-rate",
        kind="percentage",
        metric_category="Completion",
        name="Program completion rate",
        description=(
            "Share of program participants who completed the program, as reported under "
            "WIOA. The source reports a 0-1 fraction; projected as a percentage."
        ),
    ),
    Measure(
        field="employment_rate_q2",
        slug="employment-rate-q2",
        kind="percentage",
        metric_category="Employment",
        name="Employment rate, second quarter after exit",
        description=(
            "Share of program exiters employed in the second quarter after exit, as "
            "reported under WIOA. The source reports a 0-1 fraction; projected as a "
            "percentage."
        ),
    ),
)
"""Every outcome measure the source reports, in publication order. All five are now
projected: the QData move made the two rates expressible (``qdata:percentage``), so the
old not-projected carve-out is gone."""


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


def _as_percentage(fraction: float) -> float:
    """A source 0-1 fraction as the 0-100 figure ``qdata:percentage`` is defined to carry.

    A unit conversion, not a value change: the source validates rates as fractions
    (``clean_rate`` in :mod:`afterward.sources.dol_etp`), and the QData term is "quotient
    of two values ... expressed as a percentage". The rounding exists only to strip binary
    float noise (``0.64 * 100`` is not exactly ``64.0``); ten decimal places is far beyond
    any precision the source asserts. :func:`projection_problems` applies this SAME
    function to the source value when checking the round trip, so the conversion can never
    drift from its own guard.
    """
    return round(fraction * 100, 10)


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


def dataset_profile_ctid(source_uuid: str) -> str:
    return entity_ctid("dataset-profile", source_uuid)


def _metric_id(profile_iri: str, measure: Measure) -> str:
    """The Metric's ``@id``: a fragment on its DataSetProfile's own IRI.

    Deterministic by construction, obviously non-registry, and it keeps each Metric
    resolvable relative to the one document that defines it -- ``qdata:isObservationOf``
    on the Observations references exactly this string.
    """
    return f"{profile_iri}#metric-{measure.slug}"


def _observation(measure: Measure, value: float, profile_iri: str, where: str) -> dict[str, Any]:
    """One ``qdata:Observation``, valued per the measure's kind (see :class:`Measure`)."""
    observation: dict[str, Any] = {
        "@type": "qdata:Observation",
        "qdata:isObservationOf": _metric_id(profile_iri, measure),
    }
    if measure.kind == "count":
        observation["schema:value"] = _as_count(value, measure.field, where)
    elif measure.kind == "median_usd":
        observation["qdata:median"] = value
        # Dollar figures filed with a U.S. federal scorecard, by the source's own terms.
        observation["schema:currency"] = "USD"
    elif measure.kind == "percentage":
        observation["qdata:percentage"] = _as_percentage(value)
    else:  # pragma: no cover - Measure kinds are a closed set defined above
        raise ValueError(f"unknown measure kind: {measure.kind!r}")
    return observation


def dataset_profile(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """The program's ``qdata:DataSetProfile`` entity, or None.

    One profile per program with at least one reported outcome, carrying one
    ``qdata:Metric`` / ``qdata:Observation`` pair per reported measure. All measures
    suppressed means no profile at all: an empty statistics entity would read as
    "measured, and empty". The back-link ``qdata:relevantDataSetFor`` names the program;
    the program's forward ``qdata:relevantDataSet`` is written by :func:`project_program`
    and the pair is verified by :func:`projection_problems`.
    """
    outcomes = payload["outcomes"]
    where = str(payload.get("uuid", "<no uuid>"))
    reported = [m for m in MEASURES if outcomes.get(m.field) is not None]
    if not reported:
        return None
    ctid = dataset_profile_ctid(str(payload["uuid"]))
    profile_iri = RESOURCE_BASE + ctid
    program_iri = RESOURCE_BASE + program_ctid(str(payload["uuid"]))
    metrics = [
        {
            "@type": "qdata:Metric",
            "@id": _metric_id(profile_iri, m),
            "ceterms:name": _lang(m.name),
            "ceterms:description": _lang(m.description),
            "qdata:metricType": METRICCAT_BASE + m.metric_category,
        }
        for m in reported
    ]
    observations = [_observation(m, outcomes[m.field], profile_iri, where) for m in reported]
    return {
        "@type": "qdata:DataSetProfile",
        "@id": profile_iri,
        "ceterms:ctid": ctid,
        "ceterms:name": _lang(
            f"WIOA Eligible Training Provider outcomes: {payload['program_name']}"
        ),
        "ceterms:description": _lang(OUTCOME_DESCRIPTION),
        "ceterms:source": ETP_SOURCE_URL,
        "qdata:relevantDataSetFor": [program_iri],
        "qdata:hasMetric": metrics,
        "qdata:hasObservation": observations,
    }


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
    profile = dataset_profile(payload)
    if profile is not None:
        entity["qdata:relevantDataSet"] = [str(profile["@id"])]
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
    profiles: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        entity = project_program(payload)
        ctid = str(entity["ceterms:ctid"])
        if ctid in programs:
            raise ValueError(
                f"two programs derive the same CTID {ctid}: the source identifier is not "
                "the stable identity this export assumes"
            )
        programs[ctid] = entity
        profile = dataset_profile(payload)
        if profile is not None:
            profiles[str(profile["ceterms:ctid"])] = profile
    graph = [organizations[k] for k in sorted(organizations)]
    graph += [programs[k] for k in sorted(programs)]
    graph += [profiles[k] for k in sorted(profiles)]
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


def _observation_value(measure: Measure, observation: Mapping[str, Any]) -> Any:
    if measure.kind == "count":
        return observation.get("schema:value")
    if measure.kind == "median_usd":
        return observation.get("qdata:median")
    return observation.get("qdata:percentage")


def _expected_value(measure: Measure, source: float) -> Any:
    if measure.kind == "count":
        return int(source)
    if measure.kind == "percentage":
        return _as_percentage(source)
    return source


def _measure_problems(
    where: str, outcomes: Mapping[str, Any], profile: Mapping[str, Any] | None
) -> list[str]:
    """How one program's emitted observations diverge from its source outcomes.

    An observation exists if and only if the source reported the measure, valued exactly as
    the projection defines it (counts as integers, medians verbatim, rates through the same
    :func:`_as_percentage` the export used -- so the unit conversion is checked by its own
    definition, not re-derived).
    """
    problems: list[str] = []
    profile = profile or {}
    profile_iri = str(profile.get("@id", ""))
    observations = {
        str(o.get("qdata:isObservationOf", "")): o for o in profile.get("qdata:hasObservation", [])
    }
    for measure in MEASURES:
        source = outcomes.get(measure.field)
        observation = observations.get(_metric_id(profile_iri, measure)) if profile_iri else None
        emitted = _observation_value(measure, observation) if observation else None
        if source is None and emitted is not None:
            problems.append(
                f"{where}: {measure.slug} observes {emitted!r} where the source reports nothing"
            )
        elif source is not None and emitted is None:
            problems.append(
                f"{where}: {measure.slug} has no observation where the source reports {source!r}"
            )
        elif source is not None and emitted != _expected_value(measure, source):
            problems.append(
                f"{where}: {measure.slug} observes {emitted!r}, the source says {source!r} "
                f"(expected {_expected_value(measure, source)!r})"
            )
    return problems


def _link_problems(
    where: str,
    program: Mapping[str, Any],
    profile: Mapping[str, Any] | None,
) -> list[str]:
    """Both halves of the program <-> DataSetProfile link, or neither."""
    problems: list[str] = []
    forward = program.get("qdata:relevantDataSet")
    if profile is None:
        if forward is not None:
            problems.append(
                f"{where}: program links qdata:relevantDataSet {forward!r} "
                "but the graph carries no DataSetProfile for it"
            )
        return problems
    profile_iri = str(profile.get("@id", ""))
    program_iri = str(program.get("@id", ""))
    if forward != [profile_iri]:
        problems.append(
            f"{where}: qdata:relevantDataSet is {forward!r}, expected [{profile_iri!r}]"
        )
    if profile.get("qdata:relevantDataSetFor") != [program_iri]:
        problems.append(
            f"{where}: qdata:relevantDataSetFor is "
            f"{profile.get('qdata:relevantDataSetFor')!r}, expected [{program_iri!r}]"
        )
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
    profiles = {
        e["ceterms:ctid"]: e
        for e in document.get("@graph", [])
        if e.get("@type") == "qdata:DataSetProfile"
    }
    problems: list[str] = []
    expected_profiles = 0
    for payload in payloads:
        ctid = program_ctid(str(payload["uuid"]))
        where = str(payload["uuid"])
        entity = entities.get(ctid)
        if entity is None:
            problems.append(f"{where}: no LearningProgram entity in the graph")
            continue
        profile = profiles.get(dataset_profile_ctid(str(payload["uuid"])))
        if profile is not None:
            expected_profiles += 1
        problems += _measure_problems(where, payload["outcomes"], profile)
        problems += _link_problems(where, entity, profile)
    if len(entities) != len(payloads):
        problems.append(
            f"graph carries {len(entities)} LearningProgram entities "
            f"for {len(payloads)} source programs"
        )
    if len(profiles) != expected_profiles:
        problems.append(
            f"graph carries {len(profiles)} DataSetProfile entities where the source "
            f"outcomes call for {expected_profiles}"
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
    "qdata:relevantDataSet",
)
"""LearningProgram properties the coverage statement counts, in publication order."""


@dataclass(frozen=True)
class UnprojectedField:
    """One thing the source record says that the export does not carry.

    A coverage statement that counts only what was emitted describes a projection as though
    it were the whole record. These are the other half: source fields this export drops, the
    CTDL term that would have carried each one where such a term exists, and the reason.

    ``ctdl_term`` being non-empty is the uncomfortable case and the one worth publishing --
    the vocabulary has somewhere to put this and the export does not use it, which is a gap
    in the export rather than a limit of CTDL. Saying which kind of gap it is, per field, is
    the difference between a coverage statement and a feature list.
    """

    key: str
    source_fields: tuple[str, ...]
    ctdl_term: str
    reason: str


UNPROJECTED_SOURCE_FIELDS: Final = (
    UnprojectedField(
        key="outcome_measures",
        source_fields=(
            "outcomes.total_served",
            "outcomes.total_exited",
            "outcomes.total_completed",
            "outcomes.employed_q4",
        ),
        ctdl_term="qdata:Metric / qdata:Observation",
        reason=(
            "The source reports nine WIOA performance measures. This export projects the "
            "five counted under observation_measures. These four are reported and are not "
            "carried; the QData layer could express them in the same Metric/Observation "
            "shape, so this is a gap in the export rather than an absence in the vocabulary."
        ),
    ),
    UnprojectedField(
        key="program_length",
        source_fields=("length.weeks", "length.hours", "length.competency_based"),
        ctdl_term="ceterms:estimatedDuration",
        reason=(
            "CTDL declares ceterms:estimatedDuration for how long a learning opportunity "
            "takes. The source's program length is not carried, including the "
            "competency-based flag, which means a program finishes when the student can do "
            "the work and therefore has no fixed length by design. A gap in the export."
        ),
    ),
    UnprojectedField(
        key="program_format",
        source_fields=("program_format",),
        ctdl_term="ceterms:learningDeliveryType",
        reason=(
            "CTDL declares ceterms:learningDeliveryType, whose value is a concept from a "
            "controlled vocabulary credreg.net serves as an HTML page rather than as "
            "fetchable data. This export emits no concept it cannot check against "
            "machine-readable data, so the source's online, in-person or blended statement "
            "is not carried."
        ),
    ),
    UnprojectedField(
        key="instructional_program_code",
        source_fields=("cip_code",),
        ctdl_term="ceterms:instructionalProgramType",
        reason=(
            "CTDL declares ceterms:instructionalProgramType for a CIP alignment, in the same "
            "ceterms:CredentialAlignmentObject shape this export already uses for SOC. The "
            "source's CIP code is not carried. A gap in the export."
        ),
    ),
    UnprojectedField(
        key="program_location",
        source_fields=("location", "region"),
        ctdl_term="ceterms:availableAt",
        reason=(
            "CTDL declares ceterms:availableAt for where a learning opportunity is offered. "
            "The source's program location, and the region this project derives from it, are "
            "not carried. Separately and for a different reason, no address is placed on the "
            "organization either: the location on a record is the program's, not necessarily "
            "the provider's."
        ),
    ),
    UnprojectedField(
        key="provider_category",
        source_fields=("entity_type",),
        ctdl_term="ceterms:agentSectorType",
        reason=(
            "The source's provider category -- 'Higher Ed: Associate's Degree' and the like "
            "-- does not map onto CTDL's agent-sector concept scheme without judgement "
            "calls, and credreg.net serves that scheme as an HTML page rather than as "
            "fetchable data. The organization carries the name the source filed and nothing "
            "else."
        ),
    ),
    UnprojectedField(
        key="wioa_funded_cost",
        source_fields=("cost.wioa_funded_cost",),
        ctdl_term="ceterms:CostProfile with ceterms:directCostType",
        reason=(
            "The source reports what the same program costs a student whose training is "
            "funded under WIOA, which is a different cost to a different payer. CTDL can "
            "carry it as a second CostProfile distinguished by ceterms:directCostType, whose "
            "value is a concept from a scheme credreg.net serves as HTML rather than as "
            "data. Only the out-of-pocket total is carried."
        ),
    ),
    UnprojectedField(
        key="occupation_projections",
        source_fields=("occupations",),
        ctdl_term="",
        reason=(
            "This export projects the ETPL program record. California EDD's ten-year "
            "projections for the occupation each program feeds -- median wage, projected "
            "openings, growth, entry-level education -- are joined to the program on the "
            "site and are not carried here, and no ceterms:Occupation entity is emitted. "
            "They describe an occupation rather than this program, and hanging them off the "
            "program would assert that this program leads to that wage, which the source "
            "does not say. The SOC code the source filed is carried, on "
            "ceterms:occupationType, so the alignment is stated and the projection is not."
        ),
    ),
)
"""Every source field this export drops, in publication order.

Counted rather than described: :func:`unprojected_field_counts` reports how many programs
actually report each one, so a gap nobody hits and a gap affecting every record cannot read
the same way.
"""


def _reports(payload: Mapping[str, Any], path: str) -> bool:
    """Whether one program payload asserts a value at a dotted source path.

    Absent, ``None`` and empty all count as not reported, for the same reason they do
    everywhere else in this codebase: a key present and empty is not a fact.
    """
    node: Any = payload
    for segment in path.split("."):
        if not isinstance(node, Mapping):
            return False
        node = node.get(segment)
    if node is None or node is False:
        return False
    return not (isinstance(node, (list, tuple, str, dict)) and len(node) == 0)


def unprojected_field_counts(payloads: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """How many programs report each thing the export does not carry.

    ``reported_in_source`` is programs reporting *any* of a field group, which is the number
    a reader wants ("how many records lose something here"); the per-path counts beside it
    are what makes that number checkable.
    """
    return {
        field.key: {
            "reported_in_source": sum(
                1 for p in payloads if any(_reports(p, path) for path in field.source_fields)
            ),
            "source_fields": {
                path: sum(1 for p in payloads if _reports(p, path)) for path in field.source_fields
            },
            "ctdl_term": field.ctdl_term,
            "reason": field.reason,
        }
        for field in UNPROJECTED_SOURCE_FIELDS
    }


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
    an explanation, rather than absence a reader has to interpret. Its ``source_fields``
    block is the part that is uncomfortable to publish and therefore the part worth
    publishing: eight things the ETPL record says that this projection drops, each with the
    CTDL term that would have carried it where one exists, so a reader can tell a limit of
    the vocabulary from a limit of this export.
    """
    graph: list[Mapping[str, Any]] = list(document.get("@graph", []))
    programs = [e for e in graph if e.get("@type") == "ceterms:LearningProgram"]
    organizations = [e for e in graph if e.get("@type") == "ceterms:CredentialOrganization"]
    profiles = [e for e in graph if e.get("@type") == "qdata:DataSetProfile"]
    observations = [o for e in profiles for o in e.get("qdata:hasObservation", [])]
    metric_tails = {f"#metric-{m.slug}": m.field for m in MEASURES}

    def _observed_field(observation: Mapping[str, Any]) -> str | None:
        target = str(observation.get("qdata:isObservationOf", ""))
        for tail, field in metric_tails.items():
            if target.endswith(tail):
                return field
        return None

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
            "qdata:DataSetProfile": len(profiles),
        },
        "learning_program_properties": {
            term: sum(1 for e in programs if term in e) for term in PROGRAM_PROPERTIES
        },
        "observation_measures": {
            m.field: sum(1 for o in observations if _observed_field(o) == m.field) for m in MEASURES
        },
        "not_projected": {
            "cost_total_incomplete": {
                "reported_in_source": incomplete_costs,
                "reason": (
                    "a cost component was suppressed at the source, so the total is a "
                    "floor; ceterms:price cannot say 'at least', so no cost is published"
                ),
            },
            "source_fields": unprojected_field_counts(payloads),
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
        "observation_measures",
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
