"""Spanish at runtime, labelled, and never allowed to touch a number.

Two gaps in the static catalogue are English-only by source: the 70 of 670 occupations that
Mi Próximo Paso does not cover, and every program description, which is the provider's own
filed text. On request the service asks the model for a Spanish rendering of one record's
title and description. The result is labelled AI-translated and unreviewed everywhere it
appears, and a verifier refuses any translation that changes, drops or adds a number --
"160 horas" must still say 160 -- or that is empty or wildly different in length. The
static catalogue is untouched; issue #32 (native Spanish review) stays open.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from afterward.ask import PROMPT_VERSION
from afterward.ask.dataset import Dataset
from afterward.ask.provider import ModelProvider, ProviderError, Usage

TRANSLATE_SYSTEM = """\
You translate short English texts about California training programs and occupations into
plain Spanish for a general reader in California. Keep the register neutral and clear. Do not
add information, do not remove information, and do not explain. Every number in the English
must appear in the Spanish exactly as written: the same digits, the same units. Proper names
of schools, programs and credentials stay as they are. If a field is empty, return it empty.
Return only the fields asked for.
"""

TRANSLATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
    },
    "required": ["title", "description"],
    "additionalProperties": False,
}

LABEL = {
    "en": "Translated by AI, not reviewed by a person. The English is the record.",
    "es": "Traducido por IA, sin revisión humana. La versión en inglés es el registro.",
}

MAX_CACHE = 512
MAX_SOURCE_CHARS = 4000
LENGTH_RATIO = (0.4, 3.0)
"""A Spanish rendering longer than three times the English, or shorter than 40% of it, has
not translated the text; it has done something else."""

Kind = Literal["occupation", "program"]


class TranslationFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    description: str


@dataclass(frozen=True)
class Translated:
    kind: Kind
    id: str
    title: str | None
    description: str | None
    source_title: str | None
    source_description: str | None
    label: str
    ai_translated: bool
    reviewed: bool
    prompt_version: str
    model: str
    usage: Usage
    withheld: list[str]
    """Problems the verifier found; when non-empty, ``title``/``description`` are None."""

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "source": {"title": self.source_title, "description": self.source_description},
            "label": self.label,
            "ai_translated": self.ai_translated,
            "reviewed": self.reviewed,
            "prompt_version": self.prompt_version,
            "model": self.model,
            "withheld": list(self.withheld),
        }


class Translator:
    """One model call per record, cached per process, verified before it is returned."""

    def __init__(self, dataset: Dataset, provider: ModelProvider | None) -> None:
        self.dataset = dataset
        self.provider = provider
        self._cache: OrderedDict[tuple[str, str], Translated] = OrderedDict()

    def source(self, kind: Kind, record_id: str) -> tuple[str | None, str | None] | None:
        """The English the catalogue carries. ``None`` when there is no such record."""
        if kind == "occupation":
            occupation = self.dataset.occupation(record_id)
            if occupation is None:
                return None
            return occupation.get("title"), occupation.get("description")
        program = self.dataset.program(record_id)
        if program is None:
            return None
        return program.get("program_name"), program.get("description")

    def already_in_spanish(self, kind: Kind, record_id: str) -> dict[str, Any] | None:
        """The published Spanish, when Mi Próximo Paso has it. The model is not asked then."""
        if kind != "occupation":
            return None
        occupation = self.dataset.occupation(record_id)
        spanish = (occupation or {}).get("spanish") or {}
        if spanish.get("title"):
            return {"title": spanish.get("title"), "description": spanish.get("description")}
        return None

    def translate(self, kind: Kind, record_id: str) -> Translated | None:
        """Translate one record, or ``None`` when it does not exist or AI is off."""
        if self.provider is None:
            return None
        source = self.source(kind, record_id)
        if source is None:
            return None
        key = (kind, record_id)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached
        translated = self._translate(kind, record_id, source)
        self._cache[key] = translated
        if len(self._cache) > MAX_CACHE:
            self._cache.popitem(last=False)
        return translated

    def _translate(
        self, kind: Kind, record_id: str, source: tuple[str | None, str | None]
    ) -> Translated:
        provider = self.provider
        if provider is None:  # pragma: no cover - guarded by the caller
            raise ProviderError("translate: no provider")
        title, description = source
        completion = provider.complete_json(
            route="translate",
            system=TRANSLATE_SYSTEM,
            user=user_message(title, description),
            schema=TRANSLATE_SCHEMA,
            effort="low",
            max_tokens=2000,
        )
        try:
            fields = TranslationFields.model_validate(completion.data)
        except ValidationError as exc:
            raise ProviderError("translate: the model's answer did not match the schema") from exc
        problems = verify_translation(title, fields.title) + verify_translation(
            description, fields.description
        )
        return Translated(
            kind=kind,
            id=record_id,
            title=fields.title if not problems else None,
            description=fields.description if not problems else None,
            source_title=title,
            source_description=description,
            label=LABEL["es"],
            ai_translated=True,
            reviewed=False,
            prompt_version=PROMPT_VERSION,
            model=completion.model,
            usage=completion.usage,
            withheld=problems,
        )


def user_message(title: str | None, description: str | None) -> str:
    return "\n".join(
        [
            "Translate into Spanish. Keep every number exactly.",
            f"title: {(title or '').strip()[:MAX_SOURCE_CHARS]}",
            f"description: {(description or '').strip()[:MAX_SOURCE_CHARS]}",
        ]
    )


_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def numbers_in(text: str | None) -> list[str]:
    """Every numeric token, digits only, in order of appearance, as a multiset key."""
    return sorted(re.sub(r"[.,]", "", n) for n in _NUMBER.findall(text or ""))


def verify_translation(source: str | None, rendered: str) -> list[str]:
    """Why a rendering may not be shown. Empty means it may."""
    problems: list[str] = []
    source_text = (source or "").strip()
    if not source_text:
        if rendered.strip():
            problems.append("text_added_where_source_is_empty")
        return problems
    if not rendered.strip():
        problems.append("translation_empty")
        return problems
    if numbers_in(source_text) != numbers_in(rendered):
        problems.append("numbers_changed")
    ratio = len(rendered) / max(1, len(source_text))
    if not LENGTH_RATIO[0] <= ratio <= LENGTH_RATIO[1]:
        problems.append("length_implausible")
    return problems
