"""Tests for the offline build and the committed fixture.

The fixture is what CI builds against, so if it stops covering a rendering case, CI goes on
passing while testing less. These tests assert the coverage the fixture is supposed to have.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from afterward.build import build_offline

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "data"


@pytest.fixture(scope="module")
def programs() -> list[dict[str, object]]:
    return json.loads((FIXTURE_DIR / "programs.json").read_text(encoding="utf-8"))["programs"]


class TestFixtureCoverage:
    """The fixture must keep exercising every case the UI renders differently."""

    def test_has_programs_with_reported_outcomes(self, programs: list[dict]) -> None:
        assert any(p["outcomes"]["reported"] for p in programs)

    def test_has_programs_that_reported_nothing(self, programs: list[dict]) -> None:
        # Drives the explanatory panel, which is a distinct rendering path.
        assert any(not p["outcomes"]["reported"] for p in programs)

    def test_has_a_partially_suppressed_record(self, programs: list[dict]) -> None:
        # A reported measure beside a withheld one on the same card is the case most likely
        # to regress into rendering a null as zero.
        assert any(
            p["outcomes"]["reported"]
            and any(
                p["outcomes"][key] is None
                for key in ("median_earnings", "employment_rate_q2", "completion_rate")
            )
            for p in programs
        )

    def test_has_a_shrinking_and_a_growing_occupation(self, programs: list[dict]) -> None:
        changes = [
            p["occupations"][0].get("percent_change")
            for p in programs
            if p["occupations"] and p["occupations"][0].get("percent_change") is not None
        ]
        assert any(c < 0 for c in changes), "no shrinking occupation in fixture"
        assert any(c > 0 for c in changes), "no growing occupation in fixture"

    def test_has_a_small_cohort(self, programs: list[dict]) -> None:
        assert any(
            (p["outcomes"]["total_exited"] or 0) > 0 and (p["outcomes"]["total_exited"] or 0) <= 25
            for p in programs
        )

    def test_has_a_program_with_no_matching_occupation(self, programs: list[dict]) -> None:
        assert any(not p["occupations"] for p in programs)

    def test_no_suppression_sentinel_survived_into_the_fixture(self, programs: list[dict]) -> None:
        """A -1 reaching the fixture would mean the sentinel leaked through the pipeline."""
        for program in programs:
            for key, value in program["outcomes"].items():
                assert value != -1, f"{program['uuid']} has sentinel -1 in {key}"


class TestBuildOffline:
    def test_emits_the_full_site_bundle(self, tmp_path: Path) -> None:
        count = build_offline(FIXTURE_DIR, output_dir=tmp_path)
        assert count > 0

        for name in ("programs.json", "occupations.json", "coverage.json", "search-index.json"):
            assert (tmp_path / name).exists(), f"missing {name}"

        assert len(list((tmp_path / "programs").glob("*.json"))) == count
        assert list((tmp_path / "occupations").glob("*.json"))

    def test_search_index_row_count_matches_programs(self, tmp_path: Path) -> None:
        count = build_offline(FIXTURE_DIR, output_dir=tmp_path)
        index = json.loads((tmp_path / "search-index.json").read_text(encoding="utf-8"))
        assert len(index["programs"]) == count

    def test_marks_the_output_as_a_fixture(self, tmp_path: Path) -> None:
        # So nobody mistakes a fixture build for real California data.
        build_offline(FIXTURE_DIR, output_dir=tmp_path)
        coverage = json.loads((tmp_path / "coverage.json").read_text(encoding="utf-8"))
        assert coverage["is_fixture"] is True

    def test_makes_no_network_calls(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """The whole point of this path is that CI can run without reaching anyone."""
        import httpx

        def explode(*args: object, **kwargs: object) -> None:
            raise AssertionError("offline build attempted a network request")

        monkeypatch.setattr(httpx.Client, "get", explode)
        monkeypatch.setattr(httpx.Client, "request", explode)
        build_offline(FIXTURE_DIR, output_dir=tmp_path)


class TestFixtureIsCurrent:
    """The fixture is what CI builds the site from, so it must carry every field the site reads.

    A stale fixture does not fail quietly: the export crashes mid-render on a field the
    pipeline started emitting and the fixture never did. That is exactly how `main` broke
    once — the program page read `occupation.match.entry_level_education_withheld` against a
    fixture generated before `match` existed. Regenerate with `make data && make fixture`.
    """

    def _programs(self) -> list[dict]:
        return json.loads((FIXTURE_DIR / "programs.json").read_text(encoding="utf-8"))["programs"]

    def test_every_matched_occupation_carries_its_match_provenance(self) -> None:
        for program in self._programs():
            for occupation in program["occupations"]:
                assert "match" in occupation, f"{program['uuid']} predates the match field"
                assert "entry_level_education_withheld" in occupation["match"]

    def test_every_program_carries_cohort_integrity(self) -> None:
        for program in self._programs():
            assert "cohort" in program["outcomes"], f"{program['uuid']} predates cohort checks"
            assert "attributable" in program["outcomes"]["cohort"]

    def test_every_program_carries_the_region_key(self) -> None:
        # Present-but-null is "unplaced"; a missing key means the fixture predates the field.
        for program in self._programs():
            assert "region" in program, f"{program['uuid']} predates regional matching"


class TestFixtureShapeMatchesReal:
    """A fixture whose *shape* differs from a real build tests less than it appears to.

    The fixture predates the wage spread, so `build_offline` passed occupations through with
    the key absent rather than null. Nothing in Python noticed -- the divergence only showed
    up in the static export, where a page guarding `wage_spread !== null` let `undefined`
    through and crashed the whole build. Absent and null are different shapes, and only one
    of them is a shape a real build can produce.
    """

    def test_every_occupation_carries_the_wage_spread_key(self, tmp_path: Path) -> None:
        build_offline(FIXTURE_DIR, output_dir=tmp_path)
        details = sorted((tmp_path / "occupations").glob("*.json"))
        assert details, "fixture should emit occupation detail pages"
        absent = [p.name for p in details if "wage_spread" not in json.loads(p.read_text())]
        assert absent == [], f"wage_spread key absent (not null) in: {absent[:5]}"

    def test_wage_spread_is_null_when_no_extract_is_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CI has no OEWS extract, so the honest answer is null -- never a missing key."""
        import afterward.build as build_module

        # `load_wage_spread(path=WAGE_SPREAD_PATH)` binds its default at definition time, so
        # repointing the module constant would not reach it. Patch the loaders themselves.
        monkeypatch.setattr(build_module, "load_wage_spread", dict)
        monkeypatch.setattr(build_module, "load_wage_regions", dict)
        out = tmp_path / "out"
        build_offline(FIXTURE_DIR, output_dir=out)
        details = sorted((out / "occupations").glob("*.json"))
        spreads = [json.loads(p.read_text()).get("wage_spread", "MISSING") for p in details]
        assert spreads and all(s is None for s in spreads), "expected null, not a missing key"
