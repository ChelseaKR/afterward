"""The eval harness scores from the trace, and a results file without provenance is refused.

Two things are defended here. First, the scoring: each suite is run on the scripted fake over
the committed fixture, with narrations arranged to be faithful and then arranged to be
unfaithful, so the numbers the harness reports are shown to move for the right reasons.
Second, the record: every file under ``evals/results`` must carry provider, model, prompt
version, commit, date and dataset snapshot, must not be a dry run, and a ``run`` must name
a real provider. A number without those is not a measurement and may not be committed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from afterward import cli
from afterward.ask import PROMPT_VERSION, evals, fakes
from afterward.ask.api import Assistant
from afterward.ask.dataset import Dataset
from afterward.ask.provider import FakeProvider

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "fixtures" / "data"
CASES_DIR = REPO_ROOT / "evals" / "cases"
RESULTS_DIR = REPO_ROOT / "evals" / "results"

BIM = "f6900f55-31e5-11f1-ba03-00155dd2f085"


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(FIXTURE_DIR)


class TestCasesAreWellFormed:
    def test_every_suite_has_cases_with_ids_and_text(self) -> None:
        for suite in evals.SUITES:
            cases = evals.load_cases(suite, CASES_DIR)
            assert cases, suite
            ids = [c["id"] for c in cases]
            assert len(ids) == len(set(ids)), suite
            assert all(c["text"] for c in cases), suite

    def test_suppression_cases_name_fixture_programs_whose_ground_truth_is_null(
        self, dataset: Dataset
    ) -> None:
        for case in evals.load_cases("suppression", CASES_DIR):
            program = dataset.program(case["program_id"])
            assert program is not None, case["id"]
            for field in case["suppressed_fields"]:
                section, key = field.split(".", 1)
                assert program[section][key] is None, (case["id"], field)

    def test_other_program_contexts_exist_in_the_fixture(self, dataset: Dataset) -> None:
        for suite in ("grounding", "comparability"):
            for case in evals.load_cases(suite, CASES_DIR):
                if case.get("program_id"):
                    assert dataset.program(case["program_id"]) is not None, case["id"]
                if case.get("soc_code"):
                    assert dataset.occupation(case["soc_code"]) is not None, case["id"]

    def test_structuring_vague_cases_declare_what_must_stay_empty(self) -> None:
        for case in evals.load_cases("structuring", CASES_DIR):
            if case.get("vague"):
                assert case["must_be_empty"], case["id"]


class TestScoring:
    def test_faithful_dry_run_scores_clean(self, dataset: Dataset) -> None:
        assistant = Assistant(dataset, fakes.scripted(fakes.structured_query()))
        results = evals.run_all(assistant, cases_dir=CASES_DIR)
        assert set(results) == set(evals.SUITES)
        suppression = results["suppression"].summary
        assert suppression["absence_rendered_as_value_shown"] == 0
        assert suppression["shown_said_not_reported"] == len(results["suppression"].cases)
        grounding = results["grounding"].summary
        assert grounding["verified_rate"] == 1.0 and grounding["withheld_reasons"] == {}
        assert results["comparability"].summary["invented_benchmark_shown"] == 0

    def test_suppression_suite_catches_a_model_that_renders_absence(self, dataset: Dataset) -> None:
        def script(route: str, user: str) -> dict[str, Any]:
            if route == "structure":
                return fakes.structured_query(intent="program_detail")
            return {
                "claims": [
                    {
                        "text": "Nobody from this program was employed afterwards.",
                        "kind": "data",
                        "cites": [f"P:{BIM}"],
                        "numbers": [],
                    },
                    {
                        "text": "Earnings were $0.",
                        "kind": "data",
                        "cites": [f"P:{BIM}"],
                        "numbers": [
                            {"record": f"P:{BIM}", "field": "outcomes.median_earnings", "value": 0}
                        ],
                    },
                    {
                        "text": "Employment and earnings were not reported for this program.",
                        "kind": "data",
                        "cites": [f"P:{BIM}"],
                        "numbers": [],
                    },
                ],
                "follow_up_questions": [],
            }

        cases = [c for c in evals.load_cases("suppression", CASES_DIR) if c["program_id"] == BIM]
        result = evals.run_suite("suppression", Assistant(dataset, FakeProvider(script)), cases)
        assert result.summary["absence_rendered_as_value_by_model"] == len(cases)
        assert result.summary["absence_rendered_as_value_shown"] == 0
        assert result.summary["shown_said_not_reported"] == len(cases)
        assert all(c.passed for c in result.cases)
        assert result.cases[0].details["withheld"] == 2

    def test_suppression_suite_fails_a_case_that_never_says_not_reported(
        self, dataset: Dataset
    ) -> None:
        def script(route: str, user: str) -> dict[str, Any]:
            if route == "structure":
                return fakes.structured_query(intent="program_detail")
            return {"claims": [], "follow_up_questions": []}

        cases = [c for c in evals.load_cases("suppression", CASES_DIR) if c["program_id"] == BIM][
            :1
        ]
        result = evals.run_suite("suppression", Assistant(dataset, FakeProvider(script)), cases)
        assert not result.cases[0].passed and result.summary["shown_rate"] == 1.0

    def test_comparability_suite_catches_an_invented_benchmark(self, dataset: Dataset) -> None:
        def script(route: str, user: str) -> dict[str, Any]:
            if route == "structure":
                return fakes.structured_query(intent="compare")
            return {
                "claims": [
                    {
                        "text": "That is above the state average of 27%.",
                        "kind": "data",
                        "cites": [f"P:{BIM}"],
                        "numbers": [],
                    },
                    {
                        "text": "Median earnings were $10,000.",
                        "kind": "data",
                        "cites": ["P:f6903297-31e5-11f1-8f5f-00155dd2f085"],
                        "numbers": [
                            {
                                "record": "P:f6903297-31e5-11f1-8f5f-00155dd2f085",
                                "field": "outcomes.median_earnings",
                                "value": 10000,
                            }
                        ],
                    },
                ],
                "follow_up_questions": [],
            }

        cases = evals.load_cases("comparability", CASES_DIR)[:1]
        result = evals.run_suite("comparability", Assistant(dataset, FakeProvider(script)), cases)
        summary = result.summary
        assert (
            summary["invented_benchmark_by_model"] == 1 and summary["invented_benchmark_shown"] == 0
        )
        assert (
            summary["period_unlabelled_by_model"] == 1 and summary["period_unlabelled_shown"] == 0
        )
        assert not result.cases[0].passed  # the case expects a peer comparison to be shown

    def test_structuring_suite_scores_fields_and_abstention(self, dataset: Dataset) -> None:
        def script(route: str, user: str) -> dict[str, Any]:
            if route == "narrate":
                return fakes.echo_narrator(user)
            if "something better" in user:
                return fakes.structured_query(clarifications_needed=["Doing what?"])
            if "Can you help" in user:
                return fakes.structured_query(region_terms=["Fresno"], clarifications_needed=["?"])
            return fakes.structured_query(
                intent="find_programs",
                projection="not_shrinking",
                current_occupation_terms=["truck driver"],
                region_terms=["Los Angeles"],
                max_cost=2000,
            )

        cases = [
            c
            for c in evals.load_cases("structuring", CASES_DIR)
            if c["id"] in {"en-cna-la-cost", "vague-en-something-better", "vague-en-help"}
        ]
        result = evals.run_suite("structuring", Assistant(dataset, FakeProvider(script)), cases)
        by_id = {c.id: c for c in result.cases}
        assert by_id["vague-en-something-better"].passed
        assert by_id["vague-en-something-better"].details["refused_to_guess"] is True
        assert by_id["vague-en-help"].details["guessed_fields"] == ["region_terms"]
        assert not by_id["vague-en-help"].passed
        checks = by_id["en-cna-la-cost"].details["checks"]
        assert checks["max_cost"] is True and checks["region"] is True
        assert checks["resolves_to"] is False  # the fake named no occupation
        assert result.summary["abstention"] == {
            "vague_cases": 2,
            "refused_to_guess": 1,
            "rate": 0.5,
        }

    def test_a_failed_provider_is_an_error_row_not_a_crash(self, dataset: Dataset) -> None:
        assistant = Assistant(dataset, None)
        for suite in evals.SUITES:
            result = evals.run_suite(suite, assistant, evals.load_cases(suite, CASES_DIR)[:1])
            assert result.passed == 0 and "error" in result.cases[0].details


class TestProvenance:
    def test_stamp_carries_everything(self, dataset: Dataset) -> None:
        assistant = Assistant(dataset, fakes.scripted(fakes.structured_query()))
        stamp = evals.provenance(assistant, status="dry_run", repo_root=REPO_ROOT)
        assert set(evals.PROVENANCE_KEYS) <= set(stamp)
        assert stamp["prompt_version"] == PROMPT_VERSION and len(stamp["commit"]) == 40
        assert stamp["is_fixture"] is True and stamp["dataset_snapshot"] == dataset.snapshot_date
        assert evals.provenance(Assistant(dataset, None), status="not_run")["provider"] == "none"

    def test_commit_is_read_from_git_without_a_process(self, tmp_path: Path) -> None:
        assert evals.git_commit(tmp_path) == "unknown"
        git = tmp_path / ".git"
        git.mkdir()
        (git / "HEAD").write_text("ref: refs/heads/x\n")
        assert evals.git_commit(tmp_path) == "unknown"
        (git / "packed-refs").write_text("# pack\nabc123 refs/heads/x\n")
        assert evals.git_commit(tmp_path) == "abc123"
        (git / "refs" / "heads").mkdir(parents=True)
        (git / "refs" / "heads" / "x").write_text("def456\n")
        assert evals.git_commit(tmp_path) == "def456"
        (git / "HEAD").write_text("0123\n")
        assert evals.git_commit(tmp_path) == "0123"
        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / ".git").write_text(f"gitdir: {git}\n")
        assert evals.git_commit(worktree) == "0123"

    def test_documents_are_judged(self) -> None:
        good: dict[str, Any] = {
            "status": "run",
            "provenance": {
                "provider": "bedrock",
                "model": "m",
                "prompt_version": "v",
                "commit": "c" * 40,
                "date": "2026-08-21",
                "dataset_snapshot": "2026-08-17",
                "is_fixture": False,
            },
            "suites": {"x": {}},
        }
        assert evals.provenance_problems(good) == []
        dry = {**good, "status": "dry_run"}
        assert any("dry run" in p for p in evals.provenance_problems(dry))
        fake = {**good, "provenance": {**good["provenance"], "provider": "fake"}}
        assert any("real provider" in p for p in evals.provenance_problems(fake))
        missing = {**good, "provenance": {**good["provenance"], "commit": "unknown"}}
        assert "provenance.commit missing" in evals.provenance_problems(missing)
        assert "provenance block missing" in evals.provenance_problems({"status": "run"})
        assert any("status" in p for p in evals.provenance_problems({"status": "maybe"}))
        assert any("suite results" in p for p in evals.provenance_problems({**good, "suites": {}}))
        assert any(
            "ISO date" in p
            for p in evals.provenance_problems(
                {**good, "provenance": {**good["provenance"], "date": "yesterday"}}
            )
        )
        not_run = evals.not_run_document(good["provenance"] | {"status": "not_run"}, "no provider")
        assert evals.provenance_problems(not_run) == []

    def test_every_committed_results_file_has_provenance(self) -> None:
        files = sorted(RESULTS_DIR.glob("*.json"))
        for path in files:
            doc = json.loads(path.read_text(encoding="utf-8"))
            assert evals.provenance_problems(doc) == [], path.name
            if doc["status"] == "run":
                assert set(doc["suites"]) <= set(evals.SUITES), path.name


class TestCommand:
    def test_dry_run_writes_a_dry_run_document(self, tmp_path: Path) -> None:
        out = tmp_path / "dry.json"
        result = CliRunner().invoke(
            cli.app,
            [
                "ask-eval",
                "--dry-run",
                "--out",
                str(out),
                "--dataset-dir",
                str(FIXTURE_DIR),
                "--cases-dir",
                str(CASES_DIR),
                "--suite",
                "grounding",
            ],
        )
        assert result.exit_code == 0, result.output
        doc = json.loads(out.read_text())
        assert doc["status"] == "dry_run" and set(doc["suites"]) == {"grounding"}
        assert evals.provenance_problems(doc)  # and it would be refused as a measurement

    def test_no_provider_writes_an_honest_not_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AFTERWARD_AI_PROVIDER", "off")
        out = tmp_path / "none.json"
        result = CliRunner().invoke(
            cli.app,
            [
                "ask-eval",
                "--out",
                str(out),
                "--dataset-dir",
                str(FIXTURE_DIR),
                "--cases-dir",
                str(CASES_DIR),
            ],
        )
        assert result.exit_code == 0, result.output
        doc = json.loads(out.read_text())
        assert doc["status"] == "not_run" and doc["reason"]
        assert evals.provenance_problems(doc) == []
