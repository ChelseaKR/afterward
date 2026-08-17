"""The gate that reads a dataset's age off the dataset, rather than trusting its tag.

Written against the artifact that was actually in production. `dataset-2026-08-07` was
published at 18:18 UTC on 2026-08-07; `clean_length` -- which reads the scorecard's `-1` on
the two program-length fields as "competency-based" rather than "suppressed" -- landed four
hours later. The deploy on 2026-08-14 shipped that release, so twelve California programs
whose providers stated they have no fixed length by design were published as providers who
filed no length at all.

Every gate on that path passed. `make dataset-verify` checked for the *previous* generation
of this same failure and nothing else; the deploy workflow checked size, completeness and the
fixture marker, none of which a stale-but-complete dataset fails. So these tests are written
from both directions: a dataset in each broken shape must be refused, and a current one must
be accepted -- because a gate that cannot pass gets switched off as fast as one that cannot
fail.
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


dataset_shape_check = _script("dataset_shape_check")


def _program(**over: Any) -> dict[str, Any]:
    """One record in the shape the current pipeline emits."""
    base: dict[str, Any] = {
        "uuid": "f6903297-31e5-11f1-8f5f-00155dd2f085",
        "provider_name": "Animal Behavior College",
        "description": "Veterinary assistant training.",
        "length": {"weeks": None, "hours": None, "competency_based": True},
    }
    return {**base, **over}


def _dataset(tmp_path: Path, *programs: dict[str, Any]) -> Path:
    (tmp_path / "programs.json").write_text(
        json.dumps({"snapshot_date": "2026-08-07", "programs": list(programs)}), encoding="utf-8"
    )
    return tmp_path


class TestALengthNobodyCanReadIsRefused:
    def test_the_shape_of_the_release_that_was_live(self) -> None:
        """No `competency_based` key at all: the pipeline predates the fix, and a program
        with no fixed length by design is now indistinguishable from one that reported
        nothing. This is the record that reached twelve providers' pages."""
        found = dataset_shape_check.problems([_program(length={"weeks": None, "hours": None})])
        assert found
        assert "competency_based" in found[0]
        assert "904c231" in found[0]

    def test_a_length_that_is_not_even_a_block_is_refused(self) -> None:
        assert dataset_shape_check.problems([_program(length=None)])

    def test_a_current_record_passes(self) -> None:
        assert dataset_shape_check.problems([_program()]) == []

    def test_competency_based_false_is_a_current_record_too(self) -> None:
        """The key present and false is the answer for 3,254 of the 3,266. Refusing it would
        make the gate unpassable, which is its own way of not being a gate."""
        current = _program(length={"weeks": 12.0, "hours": 400.0, "competency_based": False})
        assert dataset_shape_check.problems([current]) == []


class TestTheRowIdLeakIsStillRefused:
    """Moved out of the Makefile so the deploy workflow can run it too. Same check, and now
    with the test it never had while it was a shell one-liner."""

    def test_a_description_carrying_the_feed_row_id(self) -> None:
        found = dataset_shape_check.problems([_program(description="12345|Some course.")])
        assert found
        assert "ec25f6d" in found[0]

    def test_a_cleaned_description_passes(self) -> None:
        assert dataset_shape_check.problems([_program(description="Some course.")]) == []

    def test_a_number_inside_a_sentence_is_not_a_row_id(self) -> None:
        clean = _program(description="Covers 12|volt systems? No: 240 hours of instruction.")
        assert dataset_shape_check.problems([clean]) == []


class TestTheGateItself:
    def test_a_missing_dataset_fails_rather_than_passing_quietly(self, tmp_path: Path) -> None:
        assert dataset_shape_check.main([str(tmp_path / "nowhere")]) == 1

    def test_an_unreadable_dataset_fails(self, tmp_path: Path) -> None:
        (tmp_path / "programs.json").write_text("{not json", encoding="utf-8")
        assert dataset_shape_check.main([str(tmp_path)]) == 1

    def test_a_stale_dataset_exits_nonzero(self, tmp_path: Path) -> None:
        stale = _program(length={"weeks": None, "hours": None})
        assert dataset_shape_check.main([str(_dataset(tmp_path, stale))]) == 1

    def test_a_current_dataset_exits_zero(self, tmp_path: Path) -> None:
        assert dataset_shape_check.main([str(_dataset(tmp_path, _program()))]) == 0


class TestTheGateIsWiredIntoBothPathsAStaleDatasetTravels:
    """A check nothing calls is documentation.

    Packaging and publishing are two separate routes to a reader, and this failure took the
    second one: the dataset was packaged before the fix existed, so no packaging-time gate
    could ever have seen it, and the deploy consumed the frozen asset by tag a week later.
    Asserting the wiring is the only way this file can speak to that, and it is worth
    asserting precisely because the second call site is the one that is easy to forget.
    """

    def test_make_dataset_verify_runs_it(self) -> None:
        makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
        assert "scripts/dataset_shape_check.py" in makefile

    def test_the_deploy_workflow_runs_it_before_it_builds_anything(self) -> None:
        workflow = (REPO_ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
        assert "scripts/dataset_shape_check.py" in workflow
        assert workflow.index("scripts/dataset_shape_check.py") < workflow.index(
            "Build the static export"
        )
