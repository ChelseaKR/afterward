"""The detector that answers "is the site a visitor gets the site this repository has?".

`deploy.yml` is dispatch-only for a reason its own header states, and nothing here argues with
it. What was missing is a clock: between 2026-08-17 and 2026-09-06 the live site stood still
while `main` took 44 commits, 18 of them changing what a visitor receives, and every gate in
the repository stayed green because none of them was asking.

These tests are written from both directions. A detector that cannot fire gets deleted as
noise; a detector that fires on a number it did not really measure is worse than none, because
the number reads as a measurement. So the cases below cover the drift it must report AND every
way the comparison can be meaningless -- no successful deploy in the history, a deploy from
another branch, a commit this clone does not have, a history that has diverged. Each of those
must end in a refusal, never in a reassuring zero.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"


def _script(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Registered before execution, not after: `@dataclass` resolves annotations through
    # `sys.modules[cls.__module__]`, so a module that is not there yet raises on the
    # decorator rather than on anything to do with this repository.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


staleness = _script("deploy_staleness")

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


def _run(**over: Any) -> dict[str, Any]:
    run = {
        "id": 1,
        "conclusion": "success",
        "head_sha": "a" * 40,
        "head_branch": "main",
        "updated_at": "2026-08-17T16:40:00Z",
        "html_url": "https://example.test/run/1",
    }
    run.update(over)
    return run


def _record(**over: Any) -> Any:
    fields = {
        "run_id": 1,
        "head_sha": "a" * 40,
        "head_branch": "main",
        "finished_at": NOW - timedelta(days=20),
        "html_url": "https://example.test/run/1",
    }
    fields.update(over)
    return staleness.DeployRecord(**fields)


class TestWhichCommitIsLive:
    def test_the_newest_successful_run_is_chosen_by_time_not_by_position(self) -> None:
        """`?status=success` is a filter, not an ordering guarantee.

        Reading element zero because the answer usually arrives newest-first is how a
        detector starts reporting the wrong commit on the day that stops holding, without
        anything looking different.
        """
        runs = [
            _run(id=7, head_sha="b" * 40, updated_at="2026-08-06T06:10:00Z"),
            _run(id=9, head_sha="c" * 40, updated_at="2026-08-17T16:40:00Z"),
            _run(id=8, head_sha="d" * 40, updated_at="2026-08-14T16:10:00Z"),
        ]
        assert staleness.newest_successful_deploy(runs).run_id == 9

    def test_a_failed_run_is_not_a_deploy(self) -> None:
        runs = [
            _run(id=2, conclusion="failure", updated_at="2026-09-01T00:00:00Z"),
            _run(id=1, updated_at="2026-08-17T16:40:00Z"),
        ]
        assert staleness.newest_successful_deploy(runs).run_id == 1

    def test_no_successful_run_is_a_refusal_and_not_zero_days(self) -> None:
        """ "Never deployed" and "deployed just now" must not produce the same report."""
        with pytest.raises(staleness.StalenessUnknown, match="never been deployed"):
            staleness.newest_successful_deploy([_run(conclusion="failure")])
        with pytest.raises(staleness.StalenessUnknown):
            staleness.newest_successful_deploy([])

    def test_a_deploy_from_another_branch_is_a_refusal(self) -> None:
        with pytest.raises(staleness.StalenessUnknown, match="not main"):
            staleness.newest_successful_deploy([_run(head_branch="experiment")])

    def test_a_run_without_a_usable_sha_is_skipped_rather_than_trusted(self) -> None:
        runs = [
            _run(id=3, head_sha="not-a-sha", updated_at="2026-09-05T00:00:00Z"),
            _run(id=1, updated_at="2026-08-17T16:40:00Z"),
        ]
        assert staleness.newest_successful_deploy(runs).run_id == 1


class TestWhatReachesAVisitor:
    @pytest.mark.parametrize(
        "path",
        [
            "web/app/[locale]/page.tsx",
            "web/lib/i18n.ts",
            "web/public/favicon.ico",
            "web/next.config.ts",
        ],
    )
    def test_site_sources_ship(self, path: str) -> None:
        assert staleness.ships_to_visitors(path)

    @pytest.mark.parametrize(
        "path",
        [
            # The dataset's builder. It reaches production as a release asset on its own
            # clock, guarded on the deploy path by dataset_shape_check.py, so counting a
            # Python change as a reason to redeploy the site would fire on nearly every
            # commit and teach everyone to ignore this.
            "src/afterward/build.py",
            "tests/test_build.py",
            "docs/ROADMAP.md",
            "README.md",
            "web/scripts/verify-wiring.test.ts",
            "web/lib/search.test.ts",
            "web/vitest.config.ts",
            "web/__tests__/home.tsx",
        ],
    )
    def test_everything_else_does_not(self, path: str) -> None:
        assert not staleness.ships_to_visitors(path)


class TestTheVerdict:
    def _drift(self, commits: list[tuple[str, datetime, list[str]]], **over: Any) -> Any:
        return staleness.measure(
            _record(), commits, now=NOW, max_age_days=over.get("max_age_days", 14)
        )

    def test_a_site_three_weeks_behind_on_visitor_facing_code_is_stale(self) -> None:
        drift = self._drift(
            [
                ("f" * 40, NOW - timedelta(days=19), ["web/app/page.tsx"]),
                ("e" * 40, NOW - timedelta(days=2), ["src/afterward/build.py"]),
            ]
        )
        assert drift.verdict == "stale"
        assert drift.total_commits == 2
        assert drift.shipping_commits == 1
        assert drift.days_waiting is not None
        assert round(drift.days_waiting) == 19

    def test_undeployed_python_alone_is_not_staleness(self) -> None:
        drift = self._drift(
            [("e" * 40, NOW - timedelta(days=40), ["src/afterward/build.py", "tests/test_x.py"])]
        )
        assert drift.total_commits == 1
        assert drift.shipping_commits == 0
        assert drift.verdict == "current"

    def test_nothing_waiting_is_none_and_never_zero(self) -> None:
        """The dominant defect in this portfolio, in its smallest possible form.

        "No visitor-visible commit is waiting" and "one landed a moment ago" are different
        facts. If the second were rendered as `0.0 days`, so would the first be, and the
        report would be stating a measurement it never took.
        """
        drift = self._drift([])
        assert drift.days_waiting is None
        assert drift.oldest_shipping_sha is None
        rendered = staleness.render(drift)
        assert "nothing a visitor sees is waiting" in rendered
        assert "0.0 days" not in rendered
        assert staleness.as_json(drift)["days_waiting"] is None

    def test_the_threshold_is_a_threshold(self) -> None:
        just_under = self._drift([("f" * 40, NOW - timedelta(days=13, hours=23), ["web/a.ts"])])
        just_over = self._drift([("f" * 40, NOW - timedelta(days=14, hours=1), ["web/a.ts"])])
        assert just_under.verdict == "current"
        assert just_over.verdict == "stale"

    def test_the_threshold_is_the_one_it_was_given(self) -> None:
        commits = [("f" * 40, NOW - timedelta(days=20), ["web/a.ts"])]
        assert self._drift(commits, max_age_days=30).verdict == "current"
        assert self._drift(commits, max_age_days=7).verdict == "stale"


def _git(repository: Path, *args: str) -> None:
    subprocess.run(  # noqa: S603
        ["git", "-C", str(repository), *args],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.test",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.test",
            "HOME": str(repository),
        },
    )


@pytest.fixture
def repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway repository the git-touching checks can be pointed at."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    (root / "web").mkdir()
    (root / "web" / "page.tsx").write_text("one\n", encoding="utf-8")
    _git(root, "add", "web/page.tsx")
    _git(root, "commit", "-q", "-m", "first")
    monkeypatch.setattr(staleness, "REPO_ROOT", root)
    return root


def _head(repository: Path) -> str:
    return subprocess.run(  # noqa: S603
        ["git", "-C", str(repository), "rev-parse", "HEAD"],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class TestRefusingAMeaninglessComparison:
    def test_a_deployed_commit_this_clone_does_not_have_is_a_refusal(
        self, repository: Path
    ) -> None:
        """The shallow-checkout trap, which fails silently in the wrong direction.

        `git log <absent>..HEAD` does not error usefully and an unguarded reader would treat
        an empty range as "nothing undeployed", i.e. as a site that is perfectly current.
        """
        with pytest.raises(staleness.StalenessUnknown, match="not in this clone"):
            staleness.require_comparable("b" * 40, _head(repository))

    def test_a_diverged_history_is_a_refusal(self, repository: Path) -> None:
        base = _head(repository)
        _git(repository, "checkout", "-q", "-b", "side")
        (repository / "web" / "page.tsx").write_text("side\n", encoding="utf-8")
        _git(repository, "commit", "-q", "-am", "side change")
        side = _head(repository)
        _git(repository, "checkout", "-q", "main")
        (repository / "web" / "page.tsx").write_text("main\n", encoding="utf-8")
        _git(repository, "commit", "-q", "-am", "main change")

        # The side commit exists, so the previous refusal does not cover this one.
        staleness.require_comparable(base, _head(repository))
        with pytest.raises(staleness.StalenessUnknown, match="not an ancestor"):
            staleness.require_comparable(side, _head(repository))

    def test_the_commit_reader_reports_paths_per_commit(self, repository: Path) -> None:
        base = _head(repository)
        (repository / "web" / "page.tsx").write_text("two\n", encoding="utf-8")
        _git(repository, "commit", "-q", "-am", "site change")
        (repository / "notes.md").write_text("hello\n", encoding="utf-8")
        _git(repository, "add", "notes.md")
        _git(repository, "commit", "-q", "-m", "docs change")

        commits = staleness.commits_between(base, _head(repository))
        assert [paths for _sha, _when, paths in commits] == [["web/page.tsx"], ["notes.md"]]
        drift = staleness.measure(_record(), commits, now=NOW, max_age_days=14)
        assert (drift.total_commits, drift.shipping_commits) == (2, 1)


class TestTheSentinelCannotDeploy:
    """The workflow watches the deploy path; it must never become part of it.

    `deploy.yml` holds `id-token: write` and assumes an AWS role that can write the bucket
    and invalidate the distribution. A reporting workflow that acquired any of that would be
    the automatic deploy this project has deliberately refused, arriving by the back door.
    """

    WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy-staleness.yml"

    def test_the_workflow_exists_and_runs_the_detector(self) -> None:
        text = self.WORKFLOW.read_text(encoding="utf-8")
        assert "python3 scripts/deploy_staleness.py" in text
        assert "schedule:" in text and "workflow_dispatch:" in text

    def test_it_holds_no_capability_to_publish(self) -> None:
        text = self.WORKFLOW.read_text(encoding="utf-8")
        for forbidden in (
            "id-token: write",
            "contents: write",
            "configure-aws-credentials",
            "aws s3",
            "aws cloudfront",
            "role-to-assume",
            "environment:",
        ):
            assert forbidden not in text, f"the staleness sentinel references {forbidden!r}"

    def test_the_deploy_workflow_still_has_no_automatic_trigger(self) -> None:
        """The point of the sentinel is that this stays true.

        If a push or schedule trigger is ever added to `deploy.yml`, the fixture-publishing
        failure its header describes becomes reachable, and this test is where that gets
        argued rather than merged.
        """
        deploy = (REPO_ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
        triggers = deploy.split("\non:", 1)[1].split("\npermissions:", 1)[0]
        assert "workflow_dispatch:" in triggers
        assert "push:" not in triggers
        assert "schedule:" not in triggers
        assert "pull_request" not in triggers
