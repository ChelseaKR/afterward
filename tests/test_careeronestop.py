"""Tests for the CareerOneStop client.

Three properties matter most: the build must survive having no credentials, since CI has
none; nothing here may turn an absent value into a number; and a cached response fetched
with a different request must never be served as if it answered this one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

import httpx
import pytest

from camino.sources.careeronestop import (
    ALTERNATE_TITLE_LIMIT,
    REQUEST_PARAMS,
    TOKEN_ENV,
    TOP_TASKS,
    USER_ID_ENV,
    OccupationEnrichment,
    build_client,
    cache_envelope,
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
            # The API returns tasks in no useful order: the first entry here is rated below
            # the second, exactly as 29-1141 does live.
            "Tasks": [
                {"TaskDescription": "Consult with institutions.", "DataValue": "3.85"},
                {"TaskDescription": "Monitor all aspects of patient care.", "DataValue": "4.44"},
                {"TaskDescription": "Order diagnostic tests.", "DataValue": "4.41"},
                {"TaskDescription": "Unrated task.", "DataValue": ""},
            ],
            "AlternateTitles": ["Charge Nurse", "Staff RN", "charge nurse", "  "],
            "EducationTraining": {
                "EducationType": [
                    {"EducationLevel": "Less than high school diploma", "Value": ".5"},
                    {"EducationLevel": "High school diploma or equivalent", "Value": "0"},
                    {"EducationLevel": "Associate's degree", "Value": "25.6"},
                    {"EducationLevel": "Bachelor's degree", "Value": "54.4"},
                    {"EducationLevel": "Doctoral or professional degree", "Value": ""},
                ],
                "EducationCode": "3",
                "EducationTitle": "Bachelor's degree",
                "ExperienceTitle": "No work experience",
                "TrainingTitle": "No on-the-job training",
                "MatOccupation": {"MatOccCode": "291141", "MatOccTitle": "Registered Nurses"},
            },
        }
    ]
}


def _cached(payload: dict[str, Any], code: str = "29-1141.00", state: str = "CA") -> str:
    return json.dumps(cache_envelope(payload, onet_code=code, state=state))


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


class TestTasks:
    """The concrete work. The one thing the site could never say before."""

    def _tasks(self) -> tuple[Any, ...]:
        parsed = parse_occupation("29-1141", PAYLOAD)
        assert parsed is not None
        return parsed.tasks

    def test_ranks_by_importance_rather_than_the_order_returned(self) -> None:
        # The API's own order is not a ranking, so showing the first few would be an
        # arbitrary sample presented as a summary.
        assert [t.description for t in self._tasks()][:3] == [
            "Monitor all aspects of patient care.",
            "Order diagnostic tests.",
            "Consult with institutions.",
        ]

    def test_an_unrated_task_keeps_a_null_rating_and_sorts_last(self) -> None:
        assert self._tasks()[-1].description == "Unrated task."
        assert self._tasks()[-1].importance is None

    def test_caps_the_list(self) -> None:
        many = {
            "OccupationDetail": [
                {
                    "Tasks": [
                        {"TaskDescription": f"Task {n}", "DataValue": str(n)} for n in range(40)
                    ]
                }
            ]
        }
        parsed = parse_occupation("29-1141", many)
        assert parsed is not None
        assert len(parsed.tasks) == TOP_TASKS
        # The cap keeps the most important, not the first returned.
        assert parsed.tasks[0].description == "Task 39"

    def test_absent_tasks_are_an_empty_list_not_an_error(self) -> None:
        parsed = parse_occupation("29-1141", {"OccupationDetail": [{"OnetCode": "29-1141.00"}]})
        assert parsed is not None
        assert parsed.tasks == ()


class TestAlternateTitles:
    def _titles(self) -> tuple[str, ...]:
        parsed = parse_occupation("29-1141", PAYLOAD)
        assert parsed is not None
        return parsed.alternate_titles

    def test_keeps_the_api_order_and_drops_blanks(self) -> None:
        assert self._titles() == ("Charge Nurse", "Staff RN")

    def test_deduplicates_case_insensitively_keeping_the_first_spelling(self) -> None:
        assert "charge nurse" not in self._titles()

    def test_caps_the_list(self) -> None:
        many = {"OccupationDetail": [{"AlternateTitles": [f"Title {n}" for n in range(50)]}]}
        parsed = parse_occupation("29-1141", many)
        assert parsed is not None
        assert len(parsed.alternate_titles) == ALTERNATE_TITLE_LIMIT

    def test_a_null_alternate_titles_field_is_an_empty_tuple(self) -> None:
        # The API returns null here rather than [] when it has nothing.
        parsed = parse_occupation("29-1141", {"OccupationDetail": [{"AlternateTitles": None}]})
        assert parsed is not None
        assert parsed.alternate_titles == ()


class TestEducationDistribution:
    """A population measurement, not a requirement, and zero in it is a real number."""

    def _education(self) -> Any:
        parsed = parse_occupation("29-1141", PAYLOAD)
        assert parsed is not None
        assert parsed.education is not None
        return parsed.education

    def test_keeps_the_published_level_order(self) -> None:
        # BLS orders least to most. Sorting by share would destroy the only thing that makes
        # the numbers readable as a distribution.
        assert [share.level for share in self._education().distribution][:3] == [
            "Less than high school diploma",
            "High school diploma or equivalent",
            "Associate's degree",
        ]

    def test_a_small_real_share_survives(self) -> None:
        assert self._education().distribution[0].percent == 0.5

    def test_a_genuine_zero_is_kept_as_zero_not_dropped_and_not_nulled(self) -> None:
        # 0.0% of workers holding a level is a measured result. This is the exact confusion
        # the project exists to avoid, running in the opposite direction from the usual one.
        zero = self._education().distribution[1]
        assert zero.level == "High school diploma or equivalent"
        assert zero.percent == 0.0
        assert zero.percent is not None

    def test_an_unpublished_share_is_null_and_the_level_is_still_listed(self) -> None:
        blank = self._education().distribution[-1]
        assert blank.level == "Doctoral or professional degree"
        assert blank.percent is None

    def test_reads_the_experience_and_training_categories(self) -> None:
        assert self._education().typical_experience == "No work experience"
        assert self._education().typical_on_the_job_training == "No on-the-job training"

    def test_records_the_occupation_the_figures_were_measured_for(self) -> None:
        # BLS publishes attainment per matrix occupation, which is not always the occupation
        # asked about. A consumer has to be able to check.
        assert self._education().reported_for_soc == "29-1141"
        assert self._education().reported_for_title == "Registered Nurses"

    def test_an_unreadable_matrix_code_is_null_rather_than_a_guess(self) -> None:
        payload = {
            "OccupationDetail": [
                {
                    "EducationTraining": {
                        "EducationType": [{"EducationLevel": "Some college", "Value": "3.9"}],
                        "MatOccupation": {"MatOccCode": "29114", "MatOccTitle": "Odd"},
                    }
                }
            ]
        }
        parsed = parse_occupation("29-1141", payload)
        assert parsed is not None
        assert parsed.education is not None
        assert parsed.education.reported_for_soc is None

    def test_is_none_when_the_api_published_no_block(self) -> None:
        parsed = parse_occupation("29-1141", {"OccupationDetail": [{"OnetCode": "29-1141.00"}]})
        assert parsed is not None
        assert parsed.education is None

    def test_serialises_nulls_and_zeroes_faithfully(self) -> None:
        payload = parse_occupation("29-1141", PAYLOAD)
        assert payload is not None
        levels = payload.as_dict()["education"]["distribution"]
        assert levels[1] == {"level": "High school diploma or equivalent", "percent": 0.0}
        assert levels[-1]["percent"] is None

    def test_serialises_to_null_when_absent(self) -> None:
        parsed = parse_occupation("29-1141", {"OccupationDetail": [{"OnetCode": "29-1141.00"}]})
        assert parsed is not None
        assert parsed.as_dict()["education"] is None


class TestBackwardCompatibility:
    """build.py and its tests construct and read this type. Nothing may move under them."""

    def test_constructible_from_the_original_fields_alone(self) -> None:
        record = OccupationEnrichment(
            soc_code="29-1141",
            onet_code="29-1141.00",
            description="Assess patient health problems and needs.",
            skills=(),
            related=(("29-2061", "Licensed Practical Nurses"),),
            bright_outlook=None,
        )
        assert record.tasks == ()
        assert record.alternate_titles == ()
        assert record.education is None

    def test_the_original_serialised_keys_are_all_still_there(self) -> None:
        parsed = parse_occupation("29-1141", PAYLOAD)
        assert parsed is not None
        assert {
            "onet_code",
            "description",
            "skills",
            "related_onet",
            "bright_outlook",
        } <= set(parsed.as_dict())


class TestFetchWithoutCredentials:
    def test_returns_none_and_makes_no_request(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CI has no credentials and must still build."""
        monkeypatch.delenv(USER_ID_ENV, raising=False)
        monkeypatch.delenv(TOKEN_ENV, raising=False)

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
        (tmp_path / "29-1141.00.json").write_text(_cached(PAYLOAD), encoding="utf-8")

        with build_client("token") as client:
            fetch_occupation("29-1141", client=client, cache_dir=tmp_path)
            assert client.is_closed is False


class TestCache:
    def test_a_cached_response_is_reused_without_a_request(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(USER_ID_ENV, "user")
        monkeypatch.setenv(TOKEN_ENV, "token")
        (tmp_path / "29-1141.00.json").write_text(_cached(PAYLOAD), encoding="utf-8")

        def explode(*args: object, **kwargs: object) -> None:
            raise AssertionError("hit the network despite a warm cache")

        monkeypatch.setattr(httpx.Client, "get", explode)
        result = fetch_occupation("29-1141", cache_dir=tmp_path)
        assert result is not None
        assert result.description == "Assess patient health problems and needs."
        assert result.tasks

    def test_a_corrupt_cache_entry_is_ignored_rather_than_fatal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(USER_ID_ENV, raising=False)
        monkeypatch.delenv(TOKEN_ENV, raising=False)
        (tmp_path / "29-1141.00.json").write_text("{not json", encoding="utf-8")
        assert fetch_occupation("29-1141", cache_dir=tmp_path) is None

    def test_an_entry_fetched_with_a_narrower_request_is_not_reused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The core of the cache change.

        The 658 entries already on disk were fetched without tasks, alternate titles or
        education. Serving one would put "this occupation reports no tasks" on a page when
        the truth is that nobody asked for tasks.
        """
        monkeypatch.setenv(USER_ID_ENV, "user")
        monkeypatch.setenv(TOKEN_ENV, "token")
        stale = cache_envelope(PAYLOAD, onet_code="29-1141.00", state="CA")
        stale["request"]["params"] = {**REQUEST_PARAMS, "tasks": "false"}
        (tmp_path / "29-1141.00.json").write_text(json.dumps(stale), encoding="utf-8")
        assert _refetched(tmp_path, monkeypatch) is True

    def test_an_entry_with_no_record_of_its_request_is_not_reused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The pre-envelope on-disk format: a bare payload that cannot say what produced it.
        monkeypatch.setenv(USER_ID_ENV, "user")
        monkeypatch.setenv(TOKEN_ENV, "token")
        (tmp_path / "29-1141.00.json").write_text(json.dumps(PAYLOAD), encoding="utf-8")
        assert _refetched(tmp_path, monkeypatch) is True

    def test_an_entry_fetched_for_another_state_is_not_reused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(USER_ID_ENV, "user")
        monkeypatch.setenv(TOKEN_ENV, "token")
        (tmp_path / "29-1141.00.json").write_text(_cached(PAYLOAD, state="TX"), encoding="utf-8")
        assert _refetched(tmp_path, monkeypatch) is True

    def test_a_written_entry_records_the_request_that_produced_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(USER_ID_ENV, "user")
        monkeypatch.setenv(TOKEN_ENV, "token")
        monkeypatch.setattr("camino.sources.careeronestop.time.sleep", lambda _: None)
        with _stub_client({"/v1/occupation/user/29-1141.00/CA": PAYLOAD}) as client:
            fetch_occupation("29-1141", client=client, cache_dir=tmp_path)

        written = json.loads((tmp_path / "29-1141.00.json").read_text(encoding="utf-8"))
        assert written["request"] == {
            "onet_code": "29-1141.00",
            "state": "CA",
            "params": dict(REQUEST_PARAMS),
        }
        assert written["response"] == PAYLOAD

    def test_the_credential_never_reaches_the_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(USER_ID_ENV, "secret-user")
        monkeypatch.setenv(TOKEN_ENV, "secret-token")
        monkeypatch.setattr("camino.sources.careeronestop.time.sleep", lambda _: None)
        with _stub_client({"/v1/occupation/secret-user/29-1141.00/CA": PAYLOAD}) as client:
            fetch_occupation("29-1141", client=client, cache_dir=tmp_path)

        written = (tmp_path / "29-1141.00.json").read_text(encoding="utf-8")
        assert "secret-user" not in written
        assert "secret-token" not in written


def _refetched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> bool:
    """True when a fetch against ``tmp_path`` went to the network rather than the cache."""
    monkeypatch.setattr("camino.sources.careeronestop.time.sleep", lambda _: None)
    with _stub_client({"/v1/occupation/user/29-1141.00/CA": PAYLOAD}) as client:
        fetch_occupation("29-1141", client=client, cache_dir=tmp_path)
        return bool(client.requested)


class _StubClient(httpx.Client):
    """An httpx client answering from a canned map, recording what it was asked for."""

    def __init__(self, responses: dict[str, dict[str, Any]]) -> None:
        self.requested: list[str] = []

        def handle(request: httpx.Request) -> httpx.Response:
            self.requested.append(request.url.path)
            body = responses.get(request.url.path)
            if body is None:
                return httpx.Response(404, json={"error": "not found"})
            return httpx.Response(200, json=body)

        super().__init__(transport=httpx.MockTransport(handle))


def _stub_client(responses: dict[str, dict[str, Any]]) -> _StubClient:
    return _StubClient(responses)


AGGREGATE_MEMBER_PAYLOAD: dict[str, Any] = {
    "OccupationDetail": [
        {
            "OnetCode": "21-1011.00",
            "OnetTitle": "Substance Abuse and Behavioral Disorder Counselors",
            "OnetDescription": "Counsel and advise individuals.",
            "BrightOutlookCategory": "Rapid Growth",
            "SkillsDataList": [{"ElementName": "Active Listening", "DataValue": "4.5"}],
            "Tasks": [{"TaskDescription": "Counsel clients.", "DataValue": "4.7"}],
            "AlternateTitles": ["Chemical Dependency Counselor"],
            "EducationTraining": {
                "EducationType": [
                    {"EducationLevel": "Some college, no degree", "Value": "5.9"},
                    {"EducationLevel": "Master's degree", "Value": "55.7"},
                ],
                "ExperienceTitle": "No work experience",
                "TrainingTitle": "None",
                "MatOccupation": {
                    "MatOccCode": "211018",
                    "MatOccTitle": "Substance Abuse, Behavioral Disorder, and Mental Health "
                    "Counselors",
                },
            },
        }
    ]
}


class TestAggregateEducation:
    """The twelve aggregates EDD publishes have no O*NET entry, but BLS still measured them.

    Their education figures are reported per BLS *matrix* occupation, and for a detailed
    occupation inside one of these aggregates the matrix occupation is the aggregate itself.
    Reading them through a member is a lookup, not a substitution -- but only for the block
    that carries the aggregate's own code.
    """

    ROUTES: ClassVar[dict[str, dict[str, Any]]] = {
        "/v1/occupation/user/21-1011.00/CA": AGGREGATE_MEMBER_PAYLOAD
    }

    def _fetch(
        self, monkeypatch: pytest.MonkeyPatch, routes: dict[str, dict[str, Any]] | None = None
    ) -> OccupationEnrichment | None:
        monkeypatch.setenv(USER_ID_ENV, "user")
        monkeypatch.setenv(TOKEN_ENV, "token")
        monkeypatch.setattr("camino.sources.careeronestop.time.sleep", lambda _: None)
        with _stub_client(self.ROUTES if routes is None else routes) as client:
            return fetch_occupation("21-1018", client=client)

    def test_recovers_the_distribution_for_an_occupation_that_404s(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        found = self._fetch(monkeypatch)
        assert found is not None
        assert found.education is not None
        assert [s.level for s in found.education.distribution] == [
            "Some college, no degree",
            "Master's degree",
        ]

    def test_the_figures_are_stamped_with_the_aggregate_they_describe(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        found = self._fetch(monkeypatch)
        assert found is not None
        assert found.education is not None
        assert found.education.reported_for_soc == "21-1018"

    def test_nothing_else_from_the_member_is_carried_over(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The member's description, tasks and skills are the member's own. Putting them on
        # the aggregate's page would describe one half of a union as the whole of it.
        found = self._fetch(monkeypatch)
        assert found is not None
        assert found.description is None
        assert found.onet_code is None
        assert found.skills == ()
        assert found.tasks == ()
        assert found.alternate_titles == ()
        assert found.bright_outlook is None
        assert found.related == ()

    def test_a_member_reporting_for_something_else_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The equality is checked, not assumed.

        O*NET reports 45-3031's wage data under the whole 45-0000 major group. A rule of
        "follow the member's block" would swallow that; requiring MatOccCode to be this
        aggregate is what stops it.
        """
        elsewhere = json.loads(json.dumps(AGGREGATE_MEMBER_PAYLOAD))
        elsewhere["OccupationDetail"][0]["EducationTraining"]["MatOccupation"]["MatOccCode"] = (
            "210000"
        )
        found = self._fetch(monkeypatch, {"/v1/occupation/user/21-1011.00/CA": elsewhere})
        assert found is None

    def test_an_ordinary_missing_occupation_stays_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 15-1252 is a real occupation with a real entry; a 404 for it means the API has
        # nothing, and there is no aggregate to reach for.
        monkeypatch.setenv(USER_ID_ENV, "user")
        monkeypatch.setenv(TOKEN_ENV, "token")
        monkeypatch.setattr("camino.sources.careeronestop.time.sleep", lambda _: None)
        with _stub_client({}) as client:
            assert fetch_occupation("15-1252", client=client) is None
            assert client.requested == ["/v1/occupation/user/15-1252.00/CA"]
