"""Ask the model to narrate an evidence pack as claims that cite records and declare numbers.

The output shape is the contract the verifier enforces. A claim is text plus the record ids it
rests on plus every number it used, each number named by record and field. A model that
follows the prompt produces claims that verify; a model that does not produces claims that
are withheld. Either way the reader sees only what the dataset supports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from afterward.ask.evidence import EvidencePack
from afterward.ask.prompts import NARRATE_SYSTEM
from afterward.ask.provider import Completion, ModelProvider, ProviderError, Usage
from afterward.ask.query import StructuredQuery


class DeclaredNumber(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record: str
    field: str
    value: float


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    kind: Literal["data", "guidance"]
    cites: list[str] = Field(default_factory=list)
    numbers: list[DeclaredNumber] = Field(default_factory=list)


class Narration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[Claim]
    follow_up_questions: list[str] = Field(default_factory=list)
    """Things the person could say next that would sharpen the query. Not answers."""


NARRATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "kind": {"type": "string", "enum": ["data", "guidance"]},
                    "cites": {"type": "array", "items": {"type": "string"}},
                    "numbers": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "record": {"type": "string"},
                                "field": {"type": "string"},
                                "value": {"type": "number"},
                            },
                            "required": ["record", "field", "value"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["text", "kind", "cites", "numbers"],
                "additionalProperties": False,
            },
        },
        "follow_up_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["claims", "follow_up_questions"],
    "additionalProperties": False,
}
"""Hand-written and flat for the same reason as ``QUERY_SCHEMA``; :class:`Narration` validates."""

MAX_CLAIMS = 12


@dataclass(frozen=True)
class Narrated:
    narration: Narration
    usage: Usage
    model: str


def narrate(
    provider: ModelProvider,
    pack: EvidencePack,
    *,
    question: str,
    query: StructuredQuery,
) -> Narrated:
    completion = provider.complete_json(
        route="narrate",
        system=NARRATE_SYSTEM,
        user=user_message(pack, question=question, query=query),
        schema=NARRATION_SCHEMA,
        effort="low",
    )
    return Narrated(parse_narration(completion), completion.usage, completion.model)


def parse_narration(completion: Completion) -> Narration:
    try:
        narration = Narration.model_validate(completion.data)
    except ValidationError as exc:
        raise ProviderError("narrate: the model's claims did not match the schema") from exc
    narration.claims = narration.claims[:MAX_CLAIMS]
    return narration


def user_message(pack: EvidencePack, *, question: str, query: StructuredQuery) -> str:
    language = "Spanish" if pack.language == "es" else "English"
    parts = [
        f"Answer in {language}.",
        f"Intent: {query.intent}.",
    ]
    if query.out_of_scope:
        parts.append(
            "Part of the question is outside the dataset and must be named as such: "
            + query.out_of_scope
        )
    if query.clarifications_needed:
        parts.append(
            "The question was underspecified; these would sharpen it: "
            + " | ".join(query.clarifications_needed)
        )
    parts.append("The person asked: " + question.strip())
    parts.append("")
    parts.append("EVIDENCE PACK")
    parts.append(pack.render())
    return "\n".join(parts)
