"""The one place the model is called.

Two real providers through the public ``anthropic`` SDK -- the Anthropic API and Amazon
Bedrock -- and a scripted fake for tests and for the eval harness's dry run. Credentials come
from the environment only: ``ANTHROPIC_API_KEY`` for the API, the AWS credential chain for
Bedrock. Nothing here reads a key from a file or writes one anywhere.

Every call asks for a JSON object that validates against a schema the caller supplies
(``output_config.format``), so the model's output is parsed, never pattern-matched. The system
prompt is marked for prompt caching: it is the same bytes on every request and it is the
largest part of the request.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

DEFAULT_MODEL = "claude-sonnet-5"
"""The configurable default. ``AFTERWARD_AI_MODEL`` overrides it."""

PROVIDER_ENV = "AFTERWARD_AI_PROVIDER"
MODEL_ENV = "AFTERWARD_AI_MODEL"
BEDROCK_MODEL_ENV = "AFTERWARD_AI_BEDROCK_MODEL"
BEDROCK_REGION_ENV = "AFTERWARD_AI_BEDROCK_REGION"
DEFAULT_BEDROCK_REGION = "us-east-1"

MAX_OUTPUT_TOKENS = 8000
"""Adaptive thinking spends from the same budget as the answer, and on a ten-record pack a
model has been measured to think past 4,000 tokens before writing a word. This is a cost
bound; a response that still hits it is a provider failure, never a partial answer."""


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read_input_tokens + other.cache_read_input_tokens,
            self.cache_creation_input_tokens + other.cache_creation_input_tokens,
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
        }


@dataclass(frozen=True)
class Completion:
    data: dict[str, Any]
    usage: Usage
    model: str


class ProviderError(RuntimeError):
    """The provider could not answer. The service fails closed: the page stays deterministic."""


class ModelProvider(Protocol):
    """What the service needs from a model: a JSON object matching a schema, and the bill."""

    name: str
    model: str

    def complete_json(
        self,
        *,
        route: str,
        system: str,
        user: str,
        schema: dict[str, Any],
        effort: str = "medium",
        max_tokens: int = MAX_OUTPUT_TOKENS,
    ) -> Completion: ...


class AnthropicProvider:
    """The Anthropic API, or Amazon Bedrock, through the same SDK and the same request shape."""

    def __init__(self, *, model: str = DEFAULT_MODEL, bedrock_region: str | None = None) -> None:
        # Imported here so the pipeline never pays for the SDK it does not use.
        import anthropic

        self.model = model
        if bedrock_region:
            self.name = "bedrock"
            self._client: Any = anthropic.AnthropicBedrock(aws_region=bedrock_region)
        else:
            self.name = "anthropic"
            self._client = anthropic.Anthropic()
        self._errors = anthropic

    def complete_json(
        self,
        *,
        route: str,
        system: str,
        user: str,
        schema: dict[str, Any],
        effort: str = "medium",
        max_tokens: int = MAX_OUTPUT_TOKENS,
    ) -> Completion:
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
                thinking={"type": "adaptive"},
                output_config={
                    "effort": effort,
                    "format": {"type": "json_schema", "schema": schema},
                },
            )
        except self._errors.APIStatusError as exc:
            raise ProviderError(f"{self.name} {route}: HTTP {exc.status_code}") from exc
        except self._errors.APIConnectionError as exc:
            raise ProviderError(f"{self.name} {route}: connection failed") from exc
        if response.stop_reason == "refusal":
            raise ProviderError(f"{self.name} {route}: the model declined the request")
        if response.stop_reason == "max_tokens":
            raise ProviderError(f"{self.name} {route}: the response hit the token cap")
        text = "".join(block.text for block in response.content if block.type == "text")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"{self.name} {route}: response was not JSON") from exc
        if not isinstance(data, dict):
            raise ProviderError(f"{self.name} {route}: response was not an object")
        usage = response.usage
        return Completion(
            data=data,
            usage=Usage(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_input_tokens=usage.cache_read_input_tokens or 0,
                cache_creation_input_tokens=usage.cache_creation_input_tokens or 0,
            ),
            model=response.model,
        )


Script = Callable[[str, str], dict[str, Any]]
"""A fake's answer for one route: ``(route, user_text) -> data``."""


class FakeProvider:
    """Scripted answers, for tests and for running the eval harness without a model.

    It records every call so a test can assert what the service sent -- in particular that
    the system prompt is identical across requests, which is what prompt caching needs.
    """

    name = "fake"

    def __init__(self, script: Script, *, model: str = "fake-model") -> None:
        self.model = model
        self._script = script
        self.calls: list[dict[str, Any]] = []

    def complete_json(
        self,
        *,
        route: str,
        system: str,
        user: str,
        schema: dict[str, Any],
        effort: str = "medium",
        max_tokens: int = MAX_OUTPUT_TOKENS,
    ) -> Completion:
        self.calls.append(
            {"route": route, "system": system, "user": user, "schema": schema, "effort": effort}
        )
        data = self._script(route, user)
        return Completion(data=data, usage=Usage(input_tokens=1, output_tokens=1), model=self.model)


def provider_from_env(environ: dict[str, str] | None = None) -> ModelProvider | None:
    """Build the provider the environment names, or ``None`` when AI is off.

    ``AFTERWARD_AI_PROVIDER`` is ``anthropic`` (default when ``ANTHROPIC_API_KEY`` is set),
    ``bedrock``, or ``off``. With nothing configured the service starts with AI off and
    answers every request with the deterministic result and an honest ``ai: unavailable``.
    """
    env = os.environ if environ is None else environ
    choice = env.get(PROVIDER_ENV, "").strip().lower()
    if choice == "off":
        return None
    if not choice:
        choice = "anthropic" if env.get("ANTHROPIC_API_KEY") else "off"
        if choice == "off":
            return None
    model = env.get(MODEL_ENV, "").strip() or DEFAULT_MODEL
    if choice == "bedrock":
        bedrock_model = env.get(BEDROCK_MODEL_ENV, "").strip() or f"global.anthropic.{model}"
        region = env.get(BEDROCK_REGION_ENV, "").strip() or DEFAULT_BEDROCK_REGION
        return AnthropicProvider(model=bedrock_model, bedrock_region=region)
    if choice == "anthropic":
        return AnthropicProvider(model=model)
    raise ProviderError(f"{PROVIDER_ENV}={choice!r} is not a provider this service knows")
