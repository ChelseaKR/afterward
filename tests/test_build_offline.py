"""Tests for the offline build and the committed fixture.

The fixture is what CI builds against, so if it stops covering a rendering case, CI goes on
passing while testing less. These tests assert the coverage the fixture is supposed to have.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from camino.build import build_offline

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
