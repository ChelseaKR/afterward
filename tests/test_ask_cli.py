"""The command line is the first place the service can be tried, and it tells the truth
about an assistant that is off."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from afterward import cli
from afterward.ask import fakes, provider

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "data"


class TestAskCommand:
    def test_off_prints_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AFTERWARD_AI_PROVIDER", "off")
        result = CliRunner().invoke(cli.app, ["ask", "anything", "--dataset-dir", str(FIXTURE_DIR)])
        assert result.exit_code == 0
        assert "not available" in result.output

    def test_scripted_answer_prints_claims_and_links(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            provider,
            "provider_from_env",
            lambda environ=None: fakes.scripted(
                fakes.structured_query(language="es", occupation_terms=["veterinary assistant"])
            ),
        )
        result = CliRunner().invoke(
            cli.app, ["ask", "vet assistant", "--lang", "es", "--dataset-dir", str(FIXTURE_DIR)]
        )
        assert result.exit_code == 0, result.output
        assert "claim(s) withheld" in result.output
        assert "/es/programs/" in result.output
        assert "Generado por IA" in result.output

    def test_json_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            provider,
            "provider_from_env",
            lambda environ=None: fakes.scripted(fakes.structured_query()),
        )
        result = CliRunner().invoke(
            cli.app, ["ask", "x", "--dataset-dir", str(FIXTURE_DIR), "--json"]
        )
        assert result.exit_code == 0, result.output
        body = json.loads(result.output)
        assert body["status"] == "ok" and body["provenance"]["provider"] == "fake"
