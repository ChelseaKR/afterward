"""The assertion CI makes about its own artifact, asked here rather than only on a runner.

It was six lines of inline shell in `.github/workflows/ci.yml` until 2026-08-28: the one
thing in the pipeline a developer could not run locally, so a tree that passed `make verify`
and `make web-verify` could still be rejected after a push, and nothing said which of the two
markers had moved.

Both directions matter and both are asserted. A CI build that stopped being the fixture, or
stopped advertising the placeholder host, is a build that looks deployable -- and a check
that only ever sees a correct build is a check nobody has watched fail.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _script(name: str) -> Any:
    """Load a gate script by path, as the other script tests here do: `scripts/` is not a
    package and these files are run by `make`, not imported by the application."""
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ci_artifact_check = _script("ci_artifact_check")
PLACEHOLDER_HOST = ci_artifact_check.PLACEHOLDER_HOST
main = ci_artifact_check.main
problems = ci_artifact_check.problems


def build(
    tmp_path: Path,
    *,
    is_fixture: object = True,
    robots: str | None = f"Sitemap: https://{PLACEHOLDER_HOST}/sitemap.xml",
) -> tuple[Path, Path]:
    dataset = tmp_path / "data"
    export = tmp_path / "out"
    dataset.mkdir()
    export.mkdir()
    (dataset / "coverage.json").write_text(
        json.dumps({"is_fixture": is_fixture, "total_programs": 60}), encoding="utf-8"
    )
    if robots is not None:
        (export / "robots.txt").write_text(robots, encoding="utf-8")
    return dataset, export


class TestAGoodCiBuild:
    def test_the_fixture_and_the_placeholder_host_pass(self, tmp_path: Path) -> None:
        dataset, export = build(tmp_path)
        assert problems(dataset, export) == []
        assert main([str(dataset), str(export)]) == 0


class TestABuildThatLooksDeployable:
    def test_a_dataset_that_is_not_the_fixture_is_refused(self, tmp_path: Path) -> None:
        """The direction that matters most: CI cannot reach DOL, so a non-fixture dataset in
        a CI export means something built the site from a source nobody expected."""
        dataset, export = build(tmp_path, is_fixture=False)
        assert [p for p in problems(dataset, export) if "not the fixture" in p]
        assert main([str(dataset), str(export)]) == 1

    def test_a_missing_is_fixture_key_is_refused_rather_than_assumed(self, tmp_path: Path) -> None:
        """An absent key is not a false. A dataset that does not say is a dataset that has
        not answered, and this gate does not answer for it."""
        dataset, export = build(tmp_path)
        (dataset / "coverage.json").write_text(json.dumps({"total_programs": 60}))
        assert [p for p in problems(dataset, export) if "not the fixture" in p]

    def test_a_real_site_url_in_robots_is_refused(self, tmp_path: Path) -> None:
        dataset, export = build(
            tmp_path, robots="Sitemap: https://afterward.chelseakr.com/sitemap.xml"
        )
        assert [p for p in problems(dataset, export) if PLACEHOLDER_HOST in p]
        assert main([str(dataset), str(export)]) == 1


class TestNothingToJudge:
    """A gate that cannot find its input passes over nothing, unless it says otherwise."""

    def test_a_missing_dataset_is_a_failure_not_a_pass(self, tmp_path: Path) -> None:
        _, export = build(tmp_path)
        assert [p for p in problems(tmp_path / "absent", export) if "no " in p]
        assert main([str(tmp_path / "absent"), str(export)]) == 1

    def test_a_missing_export_is_a_failure_not_a_pass(self, tmp_path: Path) -> None:
        dataset, _ = build(tmp_path, robots=None)
        assert [p for p in problems(dataset, tmp_path / "out") if "robots.txt" in p]
        assert main([str(dataset), str(tmp_path / "out")]) == 1

    def test_an_unreadable_coverage_file_is_a_failure(self, tmp_path: Path) -> None:
        dataset, export = build(tmp_path)
        (dataset / "coverage.json").write_text("{not json", encoding="utf-8")
        assert [p for p in problems(dataset, export) if "unreadable" in p]

    def test_both_faults_are_reported_together(self, tmp_path: Path) -> None:
        """One run, every reason. A gate that stops at the first fault sends the operator
        round the loop again for the second."""
        dataset, export = build(tmp_path, is_fixture=False, robots="Sitemap: https://real.example/")
        assert len(problems(dataset, export)) == 2


class TestDefaults:
    def test_it_reads_the_repository_paths_when_given_none(self) -> None:
        """`make ci-artifact-check` passes no arguments, and CI calls the target."""
        defaults = (ci_artifact_check.DATA, ci_artifact_check.EXPORT)
        assert defaults == (Path("web/public/data"), Path("web/out"))


@pytest.mark.parametrize("truthy", [True, 1, "yes"])
def test_any_truthy_is_fixture_value_is_accepted(tmp_path: Path, truthy: object) -> None:
    """`coverage.json` is written by this project's own pipeline as a bool. The check reads
    it as truthiness rather than identity so a JSON writer that emits 1 does not fail a build
    over a type, and the inverse -- absent, null, false -- all still refuse."""
    dataset, export = build(tmp_path, is_fixture=truthy)
    assert problems(dataset, export) == []
