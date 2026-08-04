"""Tests for the CareerOneStop client.

Two properties matter most: the build must survive having no credentials, since CI has none,
and nothing here may turn an absent value into a number.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from camino.sources.careeronestop import (
    TOKEN_ENV,
    USER_ID_ENV,
    OccupationEnrichment,
    build_client,
    credentials,
    fetch_occupation,
    onet_code,
    parse_occupation,
)

PAYLOAD: dict[str, Any] = {
    "OccupationDetail": [
        {
            "OnetCode": "29-1141.00",
            "OnetTitle": "Registered Nurses",
            "OnetDescription": "Assess patient health problems and needs.",
            "BrightOutlookCategory": "Rapid Growth; Numerous Job Openings",
            "SkillsDataList": [
                {"ElementName": "Operations Monitoring", "DataValue": "3"},
                {"ElementName": "Critical Thinking", "DataValue": "4"},
                {"ElementName": "Troubleshooting", "DataValue": "1.88"},
                {"ElementName": "Unrated Skill", "DataValue": ""},
            ],
            "RelatedOnetTitles": {
                "29-1141.04": "Clinical Nurse Specialists",
                "29-1171.00": "Nurse Practitioners",
            },
        }
    ]
}


class TestOnetCode:
    def test_appends_the_base_variant(self) -> None:
        # CareerOneStop 404s on a bare SOC; EDD only ever publishes bare SOCs.
        assert onet_code("29-1141") == "29-1141.00"

    def test_leaves_a_full_onet_code_alone(self) -> None:
        assert onet_code("29-1141.04") == "29-1141.04"


class TestCredentials:
    def test_absent_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(USER_ID_ENV, raising=False)
        monkeypatch.delenv(TOKEN_ENV, raising=False)
        assert credentials() is None

    def test_absent_when_blank(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(USER_ID_ENV, "  ")
        monkeypatch.setenv(TOKEN_ENV, "token")
        assert credentials() is None

    def test_present_when_both_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(USER_ID_ENV, "user")
        monkeypatch.setenv(TOKEN_ENV, "token")
        assert credentials() == ("user", "token")


class TestParse:
    def _parsed(self) -> OccupationEnrichment:
        result = parse_occupation("29-1141", PAYLOAD)
        assert result is not None
        return result

    def test_reads_the_description(self) -> None:
        assert self._parsed().description == "Assess patient health problems and needs."

    def test_orders_skills_by_importance(self) -> None:
        names = [s.name for s in self._parsed().skills]
        assert names[:3] == ["Critical Thinking", "Operations Monitoring", "Troubleshooting"]

    def test_unrated_skills_sort_last_rather_than_as_zero(self) -> None:
        # Treating an unrated skill as importance 0 would rank it below a skill genuinely
        # rated as unimportant, which is a different and false claim.
        parsed = self._parsed()
        assert parsed.skills[-1].name == "Unrated Skill"
        assert parsed.skills[-1].importance is None

    def test_reads_related_occupations_as_bare_socs(self) -> None:
        related = dict(self._parsed().related)
        assert related["29-1171"] == "Nurse Practitioners"

    def test_never_relates_an_occupation_to_itself(self) -> None:
        # 29-1141.04 is a specialisation of 29-1141 and collapses onto it.
        assert all(code != "29-1141" for code, _ in self._parsed().related)

    def test_returns_none_for_an_empty_payload(self) -> None:
        assert parse_occupation("29-1141", {}) is None
        assert parse_occupation("29-1141", {"OccupationDetail": []}) is None

    def test_serialises_without_inventing_values(self) -> None:
        payload = self._parsed().as_dict()
        unrated = [s for s in payload["skills"] if s["name"] == "Unrated Skill"]
        assert unrated[0]["importance"] is None


class TestFetchWithoutCredentials:
    def test_returns_none_and_makes_no_request(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CI has no credentials and must still build."""
        monkeypatch.delenv(USER_ID_ENV, raising=False)
        monkeypatch.delenv(TOKEN_ENV, raising=False)

        import httpx

        def explode(*args: object, **kwargs: object) -> None:
            raise AssertionError("attempted a request without credentials")

        monkeypatch.setattr(httpx.Client, "get", explode)
        assert fetch_occupation("29-1141") is None


class TestSharedClient:
    """A build fetches every occupation, so it shares one client rather than 670."""

    def test_carries_the_credential_and_identifies_itself(self) -> None:
        with build_client("token") as client:
            assert client.headers["Authorization"] == "Bearer token"
            assert "camino" in client.headers["User-Agent"]

    def test_a_supplied_client_is_left_open_for_its_owner(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Closing a caller's client after one occupation would break the next 669.
        monkeypatch.setenv(USER_ID_ENV, "user")
        monkeypatch.setenv(TOKEN_ENV, "token")
        (tmp_path / "29-1141.00.json").write_text(json.dumps(PAYLOAD), encoding="utf-8")

        with build_client("token") as client:
            fetch_occupation("29-1141", client=client, cache_dir=tmp_path)
            assert client.is_closed is False


class TestCache:
    def test_a_cached_response_is_reused_without_a_request(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(USER_ID_ENV, "user")
        monkeypatch.setenv(TOKEN_ENV, "token")
        (tmp_path / "29-1141.00.json").write_text(json.dumps(PAYLOAD), encoding="utf-8")

        import httpx

        def explode(*args: object, **kwargs: object) -> None:
            raise AssertionError("hit the network despite a warm cache")

        monkeypatch.setattr(httpx.Client, "get", explode)
        result = fetch_occupation("29-1141", cache_dir=tmp_path)
        assert result is not None
        assert result.description == "Assess patient health problems and needs."

    def test_a_corrupt_cache_entry_is_ignored_rather_than_fatal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(USER_ID_ENV, raising=False)
        monkeypatch.delenv(TOKEN_ENV, raising=False)
        (tmp_path / "29-1141.00.json").write_text("{not json", encoding="utf-8")
        assert fetch_occupation("29-1141", cache_dir=tmp_path) is None
