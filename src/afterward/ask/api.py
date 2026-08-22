"""The service core, free of any HTTP framework: a request in, a verified response out.

:class:`Assistant` is what the FastAPI app, the Lambda handler, the CLI and the eval harness
all call. It owns the one sequence the ADR fixes: admit → structure → execute → evidence →
narrate → verify → respond. Each step's output is on the response, so a reader (or a test)
can see what the model was asked, what the dataset returned, what the model said, and what
the verifier removed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from afterward.ask import PROMPT_VERSION
from afterward.ask.dataset import Dataset
from afterward.ask.evidence import EvidencePack, build_pack
from afterward.ask.limits import Meter
from afterward.ask.narrate import Narration, narrate
from afterward.ask.provider import ModelProvider, ProviderError, Usage
from afterward.ask.query import QueryResult, StructuredQuery, execute
from afterward.ask.structure import Turn, structure
from afterward.ask.verify import Verified, verify

NOTICE = {
    "en": (
        "AI-generated from the published dataset. Every figure shown was checked against the "
        "data; statements that could not be checked were removed and counted. This is not "
        "official information and not a recommendation from the State of California."
    ),
    "es": (
        "Generado por IA a partir del conjunto de datos publicado. Cada cifra mostrada se "
        "verificó contra los datos; las afirmaciones que no pudieron verificarse se eliminaron "
        "y se contaron. No es información oficial ni una recomendación del Estado de California."
    ),
}

UNAVAILABLE = {
    "en": "The assistant is not available right now. Everything on this page still works.",
    "es": "El asistente no está disponible ahora. Todo lo demás en esta página sigue funcionando.",
}


class HistoryTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    text: str = Field(max_length=2000)


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2000)
    lang: Literal["en", "es"] = "en"
    history: list[HistoryTurn] = Field(default_factory=list, max_length=6)
    program_id: str | None = None
    """The program page the person is reading, if any."""
    soc_code: str | None = None
    """The occupation page the person is reading, if any."""


class ProgramSummary(BaseModel):
    id: str
    name: str
    provider: str
    city: str | None
    reported: bool
    path: str


class OccupationSummary(BaseModel):
    soc_code: str
    title: str
    spanish_title: str | None
    percent_change: float | None
    path: str


class ShownClaim(BaseModel):
    text: str
    kind: str
    cites: list[str]


class WithheldSummary(BaseModel):
    count: int
    reasons: dict[str, int]


class Provenance(BaseModel):
    provider: str
    model: str
    prompt_version: str
    snapshot_date: str
    is_fixture: bool
    generated_at: str
    usage: dict[str, int]


class AskResponse(BaseModel):
    status: Literal["ok", "unavailable"]
    lang: Literal["en", "es"]
    notice: str
    message: str | None = None
    query: dict[str, Any] | None = None
    resolution: dict[str, Any] | None = None
    programs: list[ProgramSummary] = Field(default_factory=list)
    occupations: list[OccupationSummary] = Field(default_factory=list)
    claims: list[ShownClaim] = Field(default_factory=list)
    withheld: WithheldSummary = Field(default_factory=lambda: WithheldSummary(count=0, reasons={}))
    follow_up_questions: list[str] = Field(default_factory=list)
    clarifications_needed: list[str] = Field(default_factory=list)
    out_of_scope: str | None = None
    notes: list[str] = Field(default_factory=list)
    provenance: Provenance | None = None


@dataclass
class Trace:
    """Everything that happened, for the eval harness and for tests. Never sent to a browser."""

    query: StructuredQuery | None = None
    result: QueryResult | None = None
    pack: EvidencePack | None = None
    narration: Narration | None = None
    verified: Verified | None = None
    usage: Usage = field(default_factory=Usage)
    model: str = ""


class Assistant:
    def __init__(
        self,
        dataset: Dataset,
        provider: ModelProvider | None,
        *,
        meter: Meter | None = None,
        site_root: str = "",
    ) -> None:
        self.dataset = dataset
        self.provider = provider
        self.meter = meter or Meter()
        self.site_root = site_root.rstrip("/")

    @property
    def available(self) -> bool:
        return self.provider is not None

    def ask(self, request: AskRequest, *, client_key: str = "local") -> AskResponse:
        """Admit, then run the sequence. A provider failure yields ``unavailable``, not a guess."""
        self.meter.admit(client_key)
        response, _ = self.ask_traced(request)
        return response

    def ask_traced(self, request: AskRequest) -> tuple[AskResponse, Trace]:
        trace = Trace()
        if self.provider is None:
            return self._unavailable(request.lang), trace
        try:
            return self._run(self.provider, request, trace), trace
        except ProviderError:
            return self._unavailable(request.lang), trace

    def _run(self, provider: ModelProvider, request: AskRequest, trace: Trace) -> AskResponse:
        structured = structure(
            provider,
            request.text,
            language_hint=request.lang,
            history=[Turn(t.role, t.text) for t in request.history],
            page_context=self._page_context(request),
        )
        trace.query = structured.query
        trace.usage = trace.usage + structured.usage
        trace.model = structured.model

        result = execute(
            structured.query,
            self.dataset,
            context_program=request.program_id,
            context_occupation=request.soc_code,
        )
        trace.result = result
        pack = build_pack(result, self.dataset)
        trace.pack = pack

        narrated = narrate(provider, pack, question=request.text, query=structured.query)
        trace.narration = narrated.narration
        trace.usage = trace.usage + narrated.usage
        self.meter.record_output_tokens(trace.usage.output_tokens)

        verified = verify(narrated.narration, pack)
        trace.verified = verified
        return self._respond(provider, request, structured.query, result, verified, trace)

    def _respond(
        self,
        provider: ModelProvider,
        request: AskRequest,
        query: StructuredQuery,
        result: QueryResult,
        verified: Verified,
        trace: Trace,
    ) -> AskResponse:
        lang = query.language if query.language in ("en", "es") else request.lang
        return AskResponse(
            status="ok",
            lang=lang,
            notice=NOTICE[lang],
            query=query.model_dump(),
            resolution=_resolution_summary(result),
            programs=[self._program_summary(p, lang) for p in result.programs],
            occupations=[self._occupation_summary(o, lang) for o in result.occupations],
            claims=[ShownClaim(text=c.text, kind=c.kind, cites=c.cites) for c in verified.accepted],
            withheld=WithheldSummary(count=verified.withheld_count, reasons=dict(verified.reasons)),
            follow_up_questions=verified.follow_up_questions,
            clarifications_needed=list(query.clarifications_needed),
            out_of_scope=query.out_of_scope,
            notes=list(result.notes),
            provenance=Provenance(
                provider=provider.name,
                model=trace.model or provider.model,
                prompt_version=PROMPT_VERSION,
                snapshot_date=self.dataset.snapshot_date,
                is_fixture=self.dataset.is_fixture,
                generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
                usage=trace.usage.as_dict(),
            ),
        )

    def _unavailable(self, lang: Literal["en", "es"]) -> AskResponse:
        return AskResponse(
            status="unavailable", lang=lang, notice=NOTICE[lang], message=UNAVAILABLE[lang]
        )

    def _page_context(self, request: AskRequest) -> str | None:
        if request.program_id:
            program = self.dataset.program(request.program_id)
            if program:
                return (
                    f"the program page for {program['program_name']} ({program['provider_name']})"
                )
        if request.soc_code:
            occupation = self.dataset.occupation(request.soc_code)
            if occupation:
                return f"the occupation page for {occupation['title']}"
        return None

    def _program_summary(self, program: dict[str, Any], lang: str) -> ProgramSummary:
        return ProgramSummary(
            id=program["uuid"],
            name=program.get("program_name") or "",
            provider=program.get("provider_name") or "",
            city=(program.get("location") or {}).get("city"),
            reported=bool((program.get("outcomes") or {}).get("reported")),
            path=f"{self.site_root}/{lang}/programs/{program['uuid']}/",
        )

    def _occupation_summary(self, occupation: dict[str, Any], lang: str) -> OccupationSummary:
        spanish = occupation.get("spanish") or {}
        return OccupationSummary(
            soc_code=occupation["soc_code"],
            title=occupation["title"],
            spanish_title=spanish.get("title"),
            percent_change=occupation.get("percent_change"),
            path=f"{self.site_root}/{lang}/occupations/{occupation['soc_code']}/",
        )


def _resolution_summary(result: QueryResult) -> dict[str, Any]:
    res = result.resolution
    return {
        "occupations": [
            {"soc_code": h.soc_code, "title": h.title, "matched": h.matched}
            for h in res.occupations
        ],
        "current_occupations": [
            {"soc_code": h.soc_code, "title": h.title, "matched": h.matched}
            for h in res.current_occupations
        ],
        "region": None
        if res.region is None
        else {
            "term": res.region.term,
            "area_name": res.region.area_name,
            "city": res.region.city,
            "matched_on": res.region.matched_on,
        },
        "unresolved_occupation_terms": list(res.unresolved_occupation_terms),
        "unresolved_region_terms": list(res.unresolved_region_terms),
        "candidates": result.candidates,
        "excluded": result.excluded.as_dict(),
    }


def history_from(turns: Sequence[HistoryTurn]) -> list[Turn]:
    return [Turn(t.role, t.text) for t in turns]
