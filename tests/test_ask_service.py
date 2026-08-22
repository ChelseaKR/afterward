"""The HTTP layer adds nothing the core does not have, and takes nothing away.

A 429 is a 429 with a Retry-After, /health says whether a model is configured and nothing
about who asked, and CORS is off unless an origin is named. The client key for rate
limiting comes from the connection or the first forwarded address and goes nowhere else.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from afterward.ask.api import Assistant
from afterward.ask.dataset import Dataset
from afterward.ask.fakes import scripted, structured_query
from afterward.ask.limits import Limits, Meter
from afterward.ask.service import app_from_env, create_app

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "data"


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(FIXTURE_DIR)


class TestRoutes:
    def test_root_and_health(self, dataset: Dataset) -> None:
        provider = scripted(structured_query())
        app = create_app(Assistant(dataset, provider))
        with TestClient(app) as client:
            assert client.get("/").json()["service"] == "afterward.ask"
            health = client.get("/health").json()
        assert health["ok"] is True and health["ai"] == "configured"
        assert health["provider"] == "fake" and health["model"] == "fake-model"
        assert health["programs"] == 60 and health["is_fixture"] is True
        assert set(health["limits"]) == {"client_per_hour", "daily_requests", "daily_output_tokens"}
        assert "day_requests" not in health

    def test_health_with_ai_off(self, dataset: Dataset) -> None:
        with TestClient(create_app(Assistant(dataset, None))) as client:
            health = client.get("/health").json()
        assert health["ai"] == "off" and health["provider"] is None

    def test_ask_round_trip(self, dataset: Dataset) -> None:
        provider = scripted(structured_query(occupation_terms=["veterinary assistant"]))
        with TestClient(create_app(Assistant(dataset, provider))) as client:
            response = client.post("/ask", json={"text": "vet assistant", "lang": "en"})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok" and body["claims"]
        assert body["provenance"]["provider"] == "fake"

    def test_bad_request_is_422_and_never_reaches_the_model(self, dataset: Dataset) -> None:
        provider = scripted(structured_query())
        with TestClient(create_app(Assistant(dataset, provider))) as client:
            assert client.post("/ask", json={"text": ""}).status_code == 422
            assert client.post("/ask", json={"text": "x", "extra": 1}).status_code == 422
        assert provider.calls == []

    def test_limit_is_a_429_with_retry_after(self, dataset: Dataset) -> None:
        provider = scripted(structured_query())
        meter = Meter(limits=Limits(client_per_hour=1))
        with TestClient(create_app(Assistant(dataset, provider, meter=meter))) as client:
            assert client.post("/ask", json={"text": "one"}).status_code == 200
            limited = client.post("/ask", json={"text": "two"})
        assert limited.status_code == 429
        assert limited.json()["scope"] == "client_per_hour"
        assert int(limited.headers["Retry-After"]) >= 1

    def test_forwarded_address_is_the_client_key(self, dataset: Dataset) -> None:
        provider = scripted(structured_query())
        meter = Meter(limits=Limits(client_per_hour=1))
        with TestClient(create_app(Assistant(dataset, provider, meter=meter))) as client:
            first = client.post(
                "/ask", json={"text": "a"}, headers={"x-forwarded-for": "10.0.0.1, proxy"}
            )
            second = client.post(
                "/ask", json={"text": "b"}, headers={"x-forwarded-for": "10.0.0.2"}
            )
            third = client.post("/ask", json={"text": "c"}, headers={"x-forwarded-for": "10.0.0.1"})
        assert (first.status_code, second.status_code, third.status_code) == (200, 200, 429)


class TestCors:
    def test_no_origin_configured_means_no_cors_headers(self, dataset: Dataset) -> None:
        with TestClient(create_app(Assistant(dataset, None))) as client:
            response = client.get("/health", headers={"origin": "https://evil.test"})
        assert "access-control-allow-origin" not in response.headers

    def test_configured_origin_is_the_only_one_allowed(self, dataset: Dataset) -> None:
        app = create_app(
            Assistant(dataset, None), allowed_origins=["https://afterward.chelseakr.com"]
        )
        with TestClient(app) as client:
            ok = client.get("/health", headers={"origin": "https://afterward.chelseakr.com"})
            other = client.get("/health", headers={"origin": "https://evil.test"})
            preflight = client.options(
                "/ask",
                headers={
                    "origin": "https://afterward.chelseakr.com",
                    "access-control-request-method": "POST",
                    "access-control-request-headers": "content-type",
                },
            )
        assert ok.headers["access-control-allow-origin"] == "https://afterward.chelseakr.com"
        assert "access-control-allow-origin" not in other.headers
        assert preflight.status_code == 200
        assert "access-control-allow-credentials" not in ok.headers


class TestFromEnvironment:
    def test_app_from_env_with_ai_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AFTERWARD_AI_PROVIDER", "off")
        monkeypatch.setenv("AFTERWARD_AI_ALLOWED_ORIGINS", "https://a.test, https://b.test")
        monkeypatch.setenv("AFTERWARD_AI_SITE_ROOT", "https://a.test/")
        monkeypatch.setenv("AFTERWARD_AI_DAILY_REQUESTS", "7")
        app = app_from_env(FIXTURE_DIR)
        with TestClient(app) as client:
            health = client.get("/health", headers={"origin": "https://b.test"}).json()
            body = client.post("/ask", json={"text": "hola", "lang": "es"}).json()
        assert health["ai"] == "off" and health["limits"]["daily_requests"] == 7
        assert body["status"] == "unavailable"

    def test_dataset_dir_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AFTERWARD_AI_PROVIDER", "off")
        monkeypatch.setenv("AFTERWARD_DATASET_DIR", str(FIXTURE_DIR))
        monkeypatch.delenv("AFTERWARD_AI_ALLOWED_ORIGINS", raising=False)
        with TestClient(app_from_env()) as client:
            assert client.get("/health").json()["programs"] == 60
        assert os.environ["AFTERWARD_DATASET_DIR"] == str(FIXTURE_DIR)
