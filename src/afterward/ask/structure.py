"""Turn a person's words into a :class:`StructuredQuery`, or refuse to.

The model is asked for a JSON object that validates against the query schema. Anything it
returns that does not validate is a provider failure, not something to repair: a query with
a field the schema does not allow is exactly the kind of guess the schema exists to stop.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from afterward.ask.prompts import STRUCTURE_SYSTEM
from afterward.ask.provider import Completion, ModelProvider, ProviderError, Usage
from afterward.ask.query import QUERY_SCHEMA, StructuredQuery

MAX_TEXT_CHARS = 2000
MAX_HISTORY_TURNS = 6
MAX_HISTORY_CHARS = 600


@dataclass(frozen=True)
class Turn:
    role: str
    """``"user"`` or ``"assistant"``."""
    text: str


@dataclass(frozen=True)
class Structured:
    query: StructuredQuery
    usage: Usage
    model: str


def structure(
    provider: ModelProvider,
    text: str,
    *,
    language_hint: str,
    history: Sequence[Turn] = (),
    page_context: str | None = None,
) -> Structured:
    """One model call. The person's text goes in the user message; the system prompt is fixed."""
    completion = provider.complete_json(
        route="structure",
        system=STRUCTURE_SYSTEM,
        user=user_message(
            text, language_hint=language_hint, history=history, page_context=page_context
        ),
        schema=QUERY_SCHEMA,
        effort="low",
        max_tokens=1200,
    )
    return Structured(query=parse_query(completion), usage=completion.usage, model=completion.model)


def parse_query(completion: Completion) -> StructuredQuery:
    try:
        return StructuredQuery.model_validate(completion.data)
    except ValidationError as exc:
        raise ProviderError("structure: the model's query did not match the schema") from exc


def user_message(
    text: str,
    *,
    language_hint: str,
    history: Sequence[Turn] = (),
    page_context: str | None = None,
) -> str:
    """Everything per-request, in the user turn, so the system prompt stays cacheable."""
    parts = [f"Interface language: {language_hint}."]
    if page_context:
        parts.append(f"The person is reading: {page_context}.")
    if history:
        parts.append("Earlier in this conversation:")
        for turn in list(history)[-MAX_HISTORY_TURNS:]:
            parts.append(f"  {turn.role}: {_clip(turn.text, MAX_HISTORY_CHARS)}")
    parts.append("The person wrote:")
    parts.append(_clip(text, MAX_TEXT_CHARS))
    return "\n".join(parts)


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + " [...]"
