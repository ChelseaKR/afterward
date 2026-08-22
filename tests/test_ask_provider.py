"""The provider layer reads credentials from the environment only and fails closed.

No network here. The SDK client is replaced by a stub that returns what a response looks
like, so every failure shape the service must survive -- a refusal, a token-cap stop, a
non-JSON body, an HTTP error, a connection error -- is exercised, and the request the
service sends is inspected: system prompt marked for caching, schema in output_config.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import anthropic
import pytest

from afterward.ask.provider import (
    DEFAULT_MODEL,
    AnthropicProvider,
    FakeProvider,
    ProviderError,
    Usage,
    provider_from_env,
)
from afterward.ask.structure import Turn, parse_query, structure, user_message


def _response(
    text: str | None = '{"ok": true}',
    *,
    stop_reason: str = "end_turn",
    model: str = "m",
) -> SimpleNamespace:
    content: list[Any] = [SimpleNamespace(type="thinking", thinking="...")]
    if text is not None:
        content.append(SimpleNamespace(type="text", text=text))
    usage = SimpleNamespace(
        input_tokens=10,
        output_tokens=5,
        cache_read_input_tokens=3,
        cache_creation_input_tokens=None,
    )
    return SimpleNamespace(content=content, stop_reason=stop_reason, usage=usage, model=model)


class StubMessages:
    def __init__(self, outcome: Any) -> None:
        self.outcome = outcome
        self.requests: list[dict[str, Any]] = []

    def create(self, **request: Any) -> Any:
        self.requests.append(request)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _provider(outcome: Any, *, bedrock: bool = False) -> tuple[AnthropicProvider, StubMessages]:
    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider.model = "test-model"
    provider.name = "bedrock" if bedrock else "anthropic"
    stub = StubMessages(outcome)
    provider._client = SimpleNamespace(messages=stub)
    provider._errors = anthropic
    return provider, stub


def _call(provider: AnthropicProvider) -> Any:
    return provider.complete_json(
        route="structure", system="SYSTEM", user="USER", schema={"type": "object"}, effort="low"
    )


class TestRequestShape:
    def test_system_is_cached_and_schema_is_enforced(self) -> None:
        provider, stub = _provider(_response())
        completion = _call(provider)
        request = stub.requests[0]
        assert request["model"] == "test-model"
        assert request["system"] == [
            {"type": "text", "text": "SYSTEM", "cache_control": {"type": "ephemeral"}}
        ]
        assert request["messages"] == [{"role": "user", "content": "USER"}]
        assert request["output_config"]["format"] == {
            "type": "json_schema",
            "schema": {"type": "object"},
        }
        assert request["output_config"]["effort"] == "low"
        assert request["thinking"] == {"type": "adaptive"}
        assert completion.data == {"ok": True} and completion.model == "m"
        assert completion.usage == Usage(10, 5, 3, 0)


class TestFailures:
    def test_refusal(self) -> None:
        provider, _ = _provider(_response(stop_reason="refusal"))
        with pytest.raises(ProviderError, match="declined"):
            _call(provider)

    def test_token_cap(self) -> None:
        provider, _ = _provider(_response(text=None, stop_reason="max_tokens"))
        with pytest.raises(ProviderError, match="token cap"):
            _call(provider)

    def test_not_json_and_not_object(self) -> None:
        provider, _ = _provider(_response(text="nope"))
        with pytest.raises(ProviderError, match="not JSON"):
            _call(provider)
        provider, _ = _provider(_response(text="[1]"))
        with pytest.raises(ProviderError, match="not an object"):
            _call(provider)

    def test_http_and_connection_errors(self) -> None:
        import httpx

        status = anthropic.APIStatusError(
            "bad",
            response=httpx.Response(429, request=httpx.Request("POST", "https://x")),
            body=None,
        )
        provider, _ = _provider(status, bedrock=True)
        with pytest.raises(ProviderError, match="bedrock structure: HTTP 429"):
            _call(provider)
        provider, _ = _provider(
            anthropic.APIConnectionError(request=httpx.Request("POST", "https://x"))
        )
        with pytest.raises(ProviderError, match="connection failed"):
            _call(provider)


class TestProviderFromEnv:
    def test_off_and_empty(self) -> None:
        assert provider_from_env({"AFTERWARD_AI_PROVIDER": "off"}) is None
        assert provider_from_env({}) is None
        assert provider_from_env({"ANTHROPIC_API_KEY": "k", "AFTERWARD_AI_PROVIDER": "OFF"}) is None

    def test_unknown_is_an_error(self) -> None:
        with pytest.raises(ProviderError):
            provider_from_env({"AFTERWARD_AI_PROVIDER": "oracle"})

    def test_anthropic_from_key_and_model_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        built: list[dict[str, Any]] = []

        class Client:
            def __init__(self, **kwargs: Any) -> None:
                built.append(kwargs)

        monkeypatch.setattr(anthropic, "Anthropic", Client)
        provider = provider_from_env({"ANTHROPIC_API_KEY": "k"})
        assert (
            provider is not None
            and provider.name == "anthropic"
            and provider.model == DEFAULT_MODEL
        )
        assert built == [{}]  # the key is read by the SDK from the environment, never passed

    def test_bedrock_derives_the_model_id_and_region(self, monkeypatch: pytest.MonkeyPatch) -> None:
        built: list[dict[str, Any]] = []

        class Client:
            def __init__(self, **kwargs: Any) -> None:
                built.append(kwargs)

        monkeypatch.setattr(anthropic, "AnthropicBedrock", Client)
        provider = provider_from_env(
            {"AFTERWARD_AI_PROVIDER": "bedrock", "AFTERWARD_AI_MODEL": "claude-sonnet-4-6"}
        )
        assert provider is not None and provider.name == "bedrock"
        assert provider.model == "global.anthropic.claude-sonnet-4-6"
        assert built == [{"aws_region": "us-east-1"}]
        explicit = provider_from_env(
            {
                "AFTERWARD_AI_PROVIDER": "bedrock",
                "AFTERWARD_AI_BEDROCK_MODEL": "us.anthropic.x",
                "AFTERWARD_AI_BEDROCK_REGION": "us-west-2",
            }
        )
        assert explicit is not None and explicit.model == "us.anthropic.x"
        assert built[-1] == {"aws_region": "us-west-2"}


class TestFake:
    def test_records_calls(self) -> None:
        fake = FakeProvider(lambda route, user: {"route": route})
        completion = fake.complete_json(route="r", system="s", user="u", schema={})
        assert completion.data == {"route": "r"} and fake.calls[0]["route"] == "r"
        assert (Usage(1, 2, 3, 4) + Usage(1, 1, 1, 1)).as_dict() == {
            "input_tokens": 2,
            "output_tokens": 3,
            "cache_read_input_tokens": 4,
            "cache_creation_input_tokens": 5,
        }


class TestStructureStep:
    def test_user_message_carries_everything_per_request(self) -> None:
        text = user_message(
            "x" * 3000,
            language_hint="es",
            history=[Turn("user", "a" * 700), Turn("assistant", "b")],
            page_context="the program page for P",
        )
        assert text.startswith("Interface language: es.")
        assert "The person is reading: the program page for P." in text
        assert "user: " + "a" * 600 + " [...]" in text
        assert text.endswith("x" * 2000 + " [...]")

    def test_structure_validates_and_reports_usage(self) -> None:
        fake = FakeProvider(
            lambda route, user: {"language": "es", "intent": "pathways", "occupation_terms": ["x"]}
        )
        structured = structure(fake, "hola", language_hint="es")
        assert structured.query.intent == "pathways" and structured.query.occupation_terms == ["x"]
        assert fake.calls[0]["effort"] == "low"
        assert structured.usage.input_tokens == 1 and structured.model == "fake-model"

    def test_invalid_query_is_a_provider_error(self) -> None:
        fake = FakeProvider(lambda route, user: {"language": "fr", "intent": "find_programs"})
        with pytest.raises(ProviderError, match="schema"):
            parse_query(fake.complete_json(route="structure", system="", user="", schema={}))
