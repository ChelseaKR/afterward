"""The gate that asks whether the dataset on disk is the one the manifest describes.

It guards the direction `publish-preflight` cannot: ``make backup-data`` mirrors with
``rsync --delete``, so backing up a corrupted dataset destroys the last good copy.

The case these tests were added for is a second state. Comparing a 1,069-program Nevada
dataset against California's 3,266-program manifest answers a question nobody asked, and
answers it in the words of corruption -- so the state is compared first, and a mismatch
refuses with the name of the manifest that should have been written instead.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"


def _script(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dataset_check = _script("dataset_check")


def counts(**overrides: Any) -> dict[str, Any]:
    figures: dict[str, Any] = {
        "state": "CA",
        "programs": 3266,
        "occupations": 670,
        "snapshot_date": "2026-08-04",
        "occupations_with_spanish": 600,
        "occupations_with_wage_spread": 669,
    }
    figures.update(overrides)
    return figures


class TestTheManifestIsPerState:
    def test_california_keeps_the_path_every_runbook_names(self) -> None:
        assert dataset_check.manifest_for("CA") == Path("data-manifest.json")

    def test_another_state_gets_its_own(self) -> None:
        assert dataset_check.manifest_for("nv") == Path("data-manifest-NV.json")

    def test_the_committed_manifest_says_which_state_it_describes(self) -> None:
        committed = json.loads((REPO_ROOT / "data-manifest.json").read_text())
        assert committed["state"] == "CA"


class TestComparingTwoStates:
    def test_a_state_mismatch_refuses_before_any_count_is_compared(self) -> None:
        problems = dataset_check.problems(
            counts(state="NV", programs=1069, occupations=648), counts()
        )
        assert len(problems) == 1
        assert "the dataset is NV and the manifest describes CA" in problems[0]
        assert "data-manifest-NV.json" in problems[0]

    def test_it_is_the_only_problem_reported_even_though_the_counts_also_differ(self) -> None:
        """The counts differ by a lot, and saying so would send somebody to restore a
        backup over a dataset that is perfectly sound."""
        problems = dataset_check.problems(
            counts(state="NV", programs=1069, occupations=648), counts()
        )
        assert not [problem for problem in problems if problem.startswith("programs:")]

    def test_a_manifest_written_before_the_state_key_is_read_as_california(self) -> None:
        """Which is what every manifest written before 2026-09-11 describes."""
        older = counts()
        del older["state"]
        assert dataset_check.problems(counts(), older) == []

    def test_the_same_state_still_gets_the_ordinary_comparison(self) -> None:
        problems = dataset_check.problems(counts(programs=100), counts())
        assert problems == ["programs: 100, manifest says 3266"]

    def test_a_surplus_is_a_refresh_and_not_a_problem(self) -> None:
        assert dataset_check.problems(counts(programs=3400), counts()) == []

    def test_enrichment_lost_is_still_caught_within_one_state(self) -> None:
        problems = dataset_check.problems(counts(occupations_with_spanish=0), counts())
        assert problems == ["occupations_with_spanish: 0, manifest says 600 — enrichment lost"]
