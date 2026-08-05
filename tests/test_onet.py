"""Tests for the O*NET Web Services client.

Four properties matter most.

The build must survive having no API key, since CI has none. Nothing here may turn an absent
value into a number. The Spanish record must never be half-claimed -- a page that says it is
in Spanish and is not is worse than an honest English one. And the attribution string the
licence requires must survive round-tripping to the site's JSON, because dropping it is a
licence breach and not merely a missing field.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from afterward.sources.onet import (
    API_KEY_ENV,
    ATTRIBUTION,
    BASE_URL,
    JOB_ZONE_REFERENCE_TABLE,
    JOB_ZONE_TABLE,
    REPORTED_TITLE_TABLE,
    TASK_TABLE,
    TECHNOLOGY_TABLE,
    JobZone,
    Task,
    Technology,
    api_key,
    build_client,
    fetch_profiles,
    fetch_spanish,
    fetch_table,
    onet_code,
    parse_job_zones,
    parse_reported_titles,
    parse_spanish,
    parse_tasks,
    parse_technologies,
)

TASK_ROWS: list[dict[str, Any]] = [
    {
        "onetsoc_code": "29-1141.00",
        "task": "Record patients' medical information and vital signs.",
        "task_type": "Core",
        "incumbents_responding": 94,
    },
    {
        "onetsoc_code": "29-1141.00",
        "task": "Maintain accurate, detailed reports and records.",
        "task_type": "Core",
        "incumbents_responding": "",
    },
    {
        "onetsoc_code": "29-1141.00",
        "task": "Prepare patients for and assist with examinations or treatments.",
        "task_type": "Supplemental",
        "incumbents_responding": 12,
    },
    {"onetsoc_code": "29-1141.00", "task": "   ", "task_type": "Core"},
]

TECHNOLOGY_ROWS: list[dict[str, Any]] = [
    {
        "onetsoc_code": "29-1141.00",
        "workplace_example": "Allscripts Sunrise",
        "element_name": "Medical software",
        "hot_technology": "N",
        "in_demand": "N",
    },
    {
        "onetsoc_code": "29-1141.00",
        "workplace_example": "Cerner Millennium",
        "element_name": "Medical software",
        "hot_technology": "N",
        "in_demand": "Y",
    },
    {
        "onetsoc_code": "29-1141.00",
        "workplace_example": "Epic Systems",
        "element_name": "Medical software",
        "hot_technology": "Y",
        "in_demand": "Y",
    },
    {
        "onetsoc_code": "29-1141.00",
        "workplace_example": "epic systems",
        "element_name": "Medical software",
        "hot_technology": "Y",
        "in_demand": "Y",
    },
    {
        "onetsoc_code": "29-1141.00",
        "workplace_example": "Microsoft Word",
        "element_name": "Word processing software",
        "hot_technology": "Y",
        "in_demand": "N",
    },
]

TITLE_ROWS: list[dict[str, Any]] = [
    {"onetsoc_code": "29-1141.00", "reported_job_title": "Staff RN (Staff Registered Nurse)"},
    {"onetsoc_code": "29-1141.00", "reported_job_title": "Charge Nurse"},
    {"onetsoc_code": "29-1141.00", "reported_job_title": "charge nurse"},
    {"onetsoc_code": "29-1141.00", "reported_job_title": None},
]

ZONE_ROWS: list[dict[str, Any]] = [
    {"onetsoc_code": "29-1141.00", "job_zone": 4},
    {"onetsoc_code": "35-9021.00", "job_zone": 1},
    {"onetsoc_code": "99-9999.00", "job_zone": None},
]

ZONE_REFERENCE: list[dict[str, Any]] = [
    {
        "job_zone": 4,
        "name": "Job Zone Four: Considerable Preparation Needed",
        "education": "Most of these occupations require a four-year bachelor's degree.",
        "experience": "A considerable amount of work-related skill is needed.",
        "job_training": "Several years of work-related experience.",
        "examples": "Real estate brokers, sales managers, database administrators.",
        "svp_range": "(7.0 to < 8.0)",
    }
]

MPP_PAYLOAD: dict[str, Any] = {
    "code": "29-1141.00",
    "title": "Enfermeros Graduados",
    "what_they_do": "Evalúan los problemas y necesidades de salud de los pacientes.",
    "also_called": [
        {"title": "Enfermero de Personal", "summary": True},
        {"title": "enfermero de personal", "summary": False},
        {"title": "Enfermero Escolar", "summary": False},
    ],
    # Machine-translated and visibly garbled. Must not reach the site.
    "on_the_job": ["información de los pacientes Record 'médicos y los signos vitales."],
}


class TestOnetCode:
    def test_appends_the_base_variant(self) -> None:
        # EDD only ever publishes bare SOCs; O*NET's taxonomy is <soc>.00.
        assert onet_code("29-1141") == "29-1141.00"

    def test_leaves_a_full_onet_code_alone(self) -> None:
        assert onet_code("29-1141.04") == "29-1141.04"


class TestApiKey:
    def test_absent_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(API_KEY_ENV, raising=False)
        assert api_key() is None

    def test_absent_when_blank(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(API_KEY_ENV, "   ")
        assert api_key() is None

    def test_present_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(API_KEY_ENV, "abc123")
        assert api_key() == "abc123"


class TestParseTasks:
    def test_keeps_the_published_order(self) -> None:
        # The bulk table arrives in importance order, matching the per-occupation view.
        # Re-sorting would assert a ranking O*NET did not make.
        titles = [t.title for t in parse_tasks(TASK_ROWS)]
        assert titles[0].startswith("Record patients'")
        assert titles[-1].startswith("Prepare patients")

    def test_marks_core_tasks(self) -> None:
        parsed = parse_tasks(TASK_ROWS)
        assert parsed[0].core is True
        assert parsed[2].core is False

    def test_an_unreported_count_is_none_not_zero(self) -> None:
        assert parse_tasks(TASK_ROWS)[1].incumbents_responding is None

    def test_drops_blank_titles(self) -> None:
        assert all(t.title.strip() for t in parse_tasks(TASK_ROWS))
        assert len(parse_tasks(TASK_ROWS)) == 3

    def test_honours_the_limit(self) -> None:
        assert len(parse_tasks(TASK_ROWS, limit=2)) == 2


class TestParseTechnologies:
    def test_hot_technologies_come_first(self) -> None:
        # Source order is alphabetical by product name, which carries no information.
        names = [t.name for t in parse_technologies(TECHNOLOGY_ROWS)]
        assert names[:2] == ["Epic Systems", "Microsoft Word"]

    def test_in_demand_outranks_neither(self) -> None:
        names = [t.name for t in parse_technologies(TECHNOLOGY_ROWS)]
        assert names.index("Cerner Millennium") < names.index("Allscripts Sunrise")

    def test_deduplicates_case_insensitively(self) -> None:
        names = [t.name.casefold() for t in parse_technologies(TECHNOLOGY_ROWS)]
        assert names.count("epic systems") == 1

    def test_reads_the_flag_columns(self) -> None:
        epic = parse_technologies(TECHNOLOGY_ROWS)[0]
        assert epic.hot is True
        assert epic.in_demand is True
        assert epic.category == "Medical software"

    def test_a_missing_flag_is_not_a_claim(self) -> None:
        parsed = parse_technologies([{"workplace_example": "Notepad"}])
        assert parsed[0].hot is False
        assert parsed[0].in_demand is False

    def test_honours_the_limit(self) -> None:
        assert len(parse_technologies(TECHNOLOGY_ROWS, limit=2)) == 2


class TestParseReportedTitles:
    def test_reads_real_world_titles(self) -> None:
        # The reason this is worth fetching: someone typing "RN" should find nurses.
        titles = parse_reported_titles(TITLE_ROWS)
        assert "Staff RN (Staff Registered Nurse)" in titles

    def test_deduplicates_case_insensitively(self) -> None:
        assert parse_reported_titles(TITLE_ROWS) == (
            "Staff RN (Staff Registered Nurse)",
            "Charge Nurse",
        )

    def test_honours_the_limit(self) -> None:
        assert len(parse_reported_titles(TITLE_ROWS, limit=1)) == 1


class TestParseJobZones:
    def test_joins_the_prose_to_the_number(self) -> None:
        zones = parse_job_zones(ZONE_ROWS, ZONE_REFERENCE)
        assert zones["29-1141.00"].code == 4
        assert zones["29-1141.00"].title == "Job Zone Four: Considerable Preparation Needed"
        assert zones["29-1141.00"].training == "Several years of work-related experience."

    def test_zone_one_keeps_its_number_without_prose(self) -> None:
        # O*NET's reference table merges zones 1 and 2 under a row keyed on 2, so a zone-1
        # occupation has no description. It must not be dropped or promoted to zone 2.
        # Defensive: no occupation in O*NET 30.3 is rated zone 1. Promoting one would
        # overstate the preparation a job needs, which is the error that costs a reader a year.
        zone = parse_job_zones(ZONE_ROWS, ZONE_REFERENCE)["35-9021.00"]
        assert zone.code == 1
        assert zone.title is None
        assert zone.education is None

    def test_an_unrated_occupation_is_absent_rather_than_zone_zero(self) -> None:
        assert "99-9999.00" not in parse_job_zones(ZONE_ROWS, ZONE_REFERENCE)


class TestParseSpanish:
    def test_reads_the_translated_title_and_description(self) -> None:
        parsed = parse_spanish(MPP_PAYLOAD)
        assert parsed is not None
        assert parsed.title == "Enfermeros Graduados"
        assert parsed.description is not None
        assert parsed.description.startswith("Evalúan los problemas")

    def test_reads_spanish_job_titles(self) -> None:
        parsed = parse_spanish(MPP_PAYLOAD)
        assert parsed is not None
        assert parsed.also_called == ("Enfermero de Personal", "Enfermero Escolar")

    def test_does_not_carry_the_machine_translated_task_list(self) -> None:
        # Mi Próximo Paso's on_the_job strings are inconsistently machine-translated and
        # some are word-salad. Shipping them would look like a Spanish page and read as a
        # broken one, which is worse than an honest English task list.
        parsed = parse_spanish(MPP_PAYLOAD)
        assert not hasattr(parsed, "on_the_job")
        assert "Record" not in json.dumps(
            [parsed.title, parsed.description, *parsed.also_called]  # type: ignore[union-attr]
        )

    def test_a_record_with_no_title_is_no_record(self) -> None:
        # Half a translation is not a translation.
        assert parse_spanish({"what_they_do": "algo"}) is None
        assert parse_spanish({}) is None

    def test_a_blank_description_is_none(self) -> None:
        parsed = parse_spanish({"title": "Electricistas", "what_they_do": "  "})
        assert parsed is not None
        assert parsed.description is None


class TestWithoutAnApiKey:
    def test_fetch_profiles_returns_nothing_and_makes_no_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CI has no key and must still build."""
        monkeypatch.delenv(API_KEY_ENV, raising=False)

        def explode(*args: object, **kwargs: object) -> None:
            raise AssertionError("attempted a request without an API key")

        monkeypatch.setattr(httpx.Client, "get", explode)
        assert fetch_profiles(["29-1141"]) == {}


class TestSharedClient:
    def test_carries_the_key_and_identifies_itself(self) -> None:
        with build_client("abc123") as client:
            assert client.headers["X-API-Key"] == "abc123"
            assert client.headers["Accept"] == "application/json"
            assert "afterward" in client.headers["User-Agent"]

    def test_a_supplied_client_is_left_open_for_its_owner(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(API_KEY_ENV, "abc123")
        _warm_cache(tmp_path)
        with build_client("abc123") as client:
            fetch_profiles(["29-1141"], client=client, cache_dir=tmp_path)
            assert client.is_closed is False


def _warm_cache(cache_dir: Path) -> None:
    """Write every response :func:`fetch_profiles` needs, so no request is made."""
    for name, payload in (
        (f"table-{TASK_TABLE}", TASK_ROWS),
        (f"table-{TECHNOLOGY_TABLE}", TECHNOLOGY_ROWS),
        (f"table-{REPORTED_TITLE_TABLE}", TITLE_ROWS),
        (f"table-{JOB_ZONE_TABLE}", ZONE_ROWS),
        (f"table-{JOB_ZONE_REFERENCE_TABLE}", ZONE_REFERENCE),
        ("mpp-29-1141.00", MPP_PAYLOAD),
    ):
        (cache_dir / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")


class TestCache:
    def test_a_warm_cache_serves_a_whole_profile_without_a_request(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(API_KEY_ENV, "abc123")
        _warm_cache(tmp_path)

        def explode(*args: object, **kwargs: object) -> None:
            raise AssertionError("hit the network despite a warm cache")

        monkeypatch.setattr(httpx.Client, "get", explode)
        profiles = fetch_profiles(["29-1141"], cache_dir=tmp_path)

        profile = profiles["29-1141"]
        assert profile.onet_code == "29-1141.00"
        assert profile.tasks[0].title.startswith("Record patients'")
        assert profile.technologies[0].name == "Epic Systems"
        assert profile.job_zone is not None and profile.job_zone.code == 4
        assert profile.spanish is not None
        assert profile.spanish.title == "Enfermeros Graduados"

    def test_a_corrupt_cache_entry_is_ignored_rather_than_fatal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(API_KEY_ENV, raising=False)
        (tmp_path / f"table-{TASK_TABLE}.json").write_text("{not json", encoding="utf-8")
        assert fetch_profiles(["29-1141"], cache_dir=tmp_path) == {}

    def test_an_occupation_onet_does_not_carry_is_absent_not_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Twelve of California's 670 are broad SOC groups with no O*NET occupation behind
        # them. An empty profile would put an empty heading on the page.
        monkeypatch.setenv(API_KEY_ENV, "abc123")
        _warm_cache(tmp_path)
        profiles = fetch_profiles(["29-1141", "31-1120"], cache_dir=tmp_path)
        assert "31-1120" not in profiles


def _client(*outcomes: httpx.Response | Exception) -> tuple[httpx.Client, list[httpx.Request]]:
    """A client whose transport replays canned outcomes and records what it was asked."""
    seen: list[httpx.Request] = []
    remaining = list(outcomes)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert remaining, f"unexpected extra request to {request.url}"
        outcome = remaining.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


class TestBulkReads:
    """670 occupations times four sub-resources is 2,700 requests. The tables cost 60."""

    def test_pages_until_the_table_is_exhausted(self, tmp_path: Path) -> None:
        first = httpx.Response(
            200, json={"start": 1, "end": 2, "total": 3, "row": [{"a": 1}, {"a": 2}]}
        )
        second = httpx.Response(200, json={"start": 3, "end": 3, "total": 3, "row": [{"a": 3}]})
        client, seen = _client(first, second)
        with client:
            rows = fetch_table(TASK_TABLE, client=client, cache_dir=tmp_path, page_size=2)

        assert rows == [{"a": 1}, {"a": 2}, {"a": 3}]
        assert seen[0].url.params["start"] == "1"
        assert seen[1].url.params["start"] == "3"

    def test_the_whole_table_is_cached_so_a_rebuild_asks_for_nothing(self, tmp_path: Path) -> None:
        page = httpx.Response(200, json={"start": 1, "end": 1, "total": 1, "row": [{"a": 1}]})
        client, _ = _client(page)
        with client:
            fetch_table(TASK_TABLE, client=client, cache_dir=tmp_path)
        client, seen_again = _client()
        with client:
            assert fetch_table(TASK_TABLE, client=client, cache_dir=tmp_path) == [{"a": 1}]
        assert seen_again == []

    def test_an_unreadable_table_degrades_rather_than_failing_the_build(
        self, tmp_path: Path
    ) -> None:
        client, _ = _client(httpx.Response(404))
        with client:
            assert fetch_table(TASK_TABLE, client=client, cache_dir=tmp_path) == []

    def test_a_failed_table_is_not_cached_as_empty(self, tmp_path: Path) -> None:
        # Caching a failure would make one bad afternoon permanent.
        client, _ = _client(httpx.Response(404))
        with client:
            fetch_table(TASK_TABLE, client=client, cache_dir=tmp_path)
        assert not (tmp_path / f"table-{TASK_TABLE}.json").exists()

    def test_it_reads_the_v2_host(self, tmp_path: Path) -> None:
        # services.onetcenter.org answers 401 to everything, key or not.
        assert BASE_URL == "https://api-v2.onetcenter.org"
        client, seen = _client(
            httpx.Response(200, json={"start": 1, "end": 0, "total": 0, "row": []})
        )
        with client:
            fetch_table(JOB_ZONE_TABLE, client=client, cache_dir=tmp_path)
        assert str(seen[0].url).startswith(f"{BASE_URL}/database/rows/{JOB_ZONE_TABLE}")


class TestSpanishFetch:
    def test_a_missing_spanish_record_is_ordinary(self, tmp_path: Path) -> None:
        # Mi Próximo Paso covers 923 of O*NET's 1,016 occupations, so 404 means "no Spanish
        # record", not "the build is broken".
        client, _ = _client(httpx.Response(404))
        with client:
            assert fetch_spanish("29-1141.00", client=client, cache_dir=tmp_path) is None

    def test_it_asks_mi_proximo_paso_not_the_english_service(self, tmp_path: Path) -> None:
        client, seen = _client(httpx.Response(200, json=MPP_PAYLOAD))
        with client:
            fetch_spanish("29-1141.00", client=client, cache_dir=tmp_path)
        assert str(seen[0].url) == f"{BASE_URL}/mpp/careers/29-1141.00/"


class TestSerialisation:
    def _profile(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
        monkeypatch.setenv(API_KEY_ENV, "abc123")
        _warm_cache(tmp_path)
        return fetch_profiles(["29-1141"], cache_dir=tmp_path)["29-1141"].as_dict()

    def test_carries_the_required_attribution(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A licence condition, not a nicety: the credit travels with the data so it cannot
        # be lost between the pipeline and the page.
        payload = self._profile(tmp_path, monkeypatch)
        assert payload["attribution"] == ATTRIBUTION
        assert "U.S. Department of Labor" in ATTRIBUTION
        assert "O*NET" in ATTRIBUTION

    def test_never_invents_a_value(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = self._profile(tmp_path, monkeypatch)
        unreported = [t for t in payload["tasks"] if t["title"].startswith("Maintain accurate")]
        assert unreported[0]["incumbents_responding"] is None

    def test_round_trips_through_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        payload = self._profile(tmp_path, monkeypatch)
        restored = json.loads(json.dumps(payload))
        assert restored["es"]["title"] == "Enfermeros Graduados"
        assert restored["job_zone"]["code"] == 4

    def test_an_occupation_with_no_spanish_says_so_rather_than_falling_back(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A null here is what lets the site fall back to English *deliberately*, with the
        # reader able to tell. An English string in a field labelled Spanish cannot be.
        monkeypatch.setenv(API_KEY_ENV, "abc123")
        _warm_cache(tmp_path)
        (tmp_path / "mpp-29-1141.00.json").unlink()
        client, _ = _client(httpx.Response(404))
        with client:
            payload = fetch_profiles(["29-1141"], client=client, cache_dir=tmp_path)[
                "29-1141"
            ].as_dict()
        assert payload["es"] is None


class TestTypes:
    """The dataclasses are the contract the build and the web layer share."""

    def test_a_task_records_what_it_knows_and_no_more(self) -> None:
        task = Task(title="x", core=True, incumbents_responding=None)
        assert task.incumbents_responding is None

    def test_a_technology_names_a_real_product(self) -> None:
        tech = Technology(
            name="Epic Systems", category="Medical software", hot=True, in_demand=True
        )
        assert tech.name == "Epic Systems"

    def test_a_job_zone_is_one_to_five(self) -> None:
        zone = JobZone(
            code=3,
            title="Job Zone Three: Medium Preparation Needed",
            education=None,
            experience=None,
            training=None,
            examples=None,
            svp_range=None,
        )
        assert 1 <= zone.code <= 5
