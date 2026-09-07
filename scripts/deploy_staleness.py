#!/usr/bin/env python3
"""How far behind `main` is the site a visitor actually gets?

`.github/workflows/deploy.yml` is dispatch-only, and that is a decision rather than an
omission: the production dataset cannot be built on a hosted runner (DOL answers Actions
with 403), so the only dataset an automatic deploy could reach is the committed 60-program
fixture. Publishing that would replace 3,266 real programs with 60 fake ones and look
entirely plausible doing it. The workflow's own header says so, and this script does not
argue with it.

What the decision costs is a clock nobody watches. `main` moves; the site does not; nothing
reports the gap. Measured on 2026-09-06: the last successful deploy ran on 2026-08-17
against 41b8f7c, and `main` had moved 44 commits ahead, 47 files of them under `web/`. No
gate anywhere is red, because no gate is asking. The live integrity sentinel asks whether
the site serves the dataset it names -- a different and equally necessary question that a
site frozen twenty days behind `main` passes perfectly.

So this asks the missing one, and only reports. It deploys nothing, and it cannot: a static
site whose data arrives by hand is not a thing to publish on a schedule.

WHERE "WHAT IS LIVE" COMES FROM

ADR 0001 says every production deploy "names exactly which dataset snapshot and which commit
it published, in the workflow run summary, so 'what is live' stays answerable without version
tags". That is the source used here: the newest *successful* `deploy.yml` run, and the commit
it ran against. Nothing is published that records the live commit -- `next.config.ts` mints a
random buildId per build and there is no version.json -- and adding one would change what gets
deployed, which `live-integrity.yml` declined to do for the same reason.

WHAT IT REFUSES TO GUESS

Every way this comparison can be meaningless ends in `unknown` and a non-zero exit, never in
a reassuring number:

* no successful deploy run in the API's answer -- "never deployed" is not "zero days behind";
* a successful run against a branch other than `main`;
* a deployed commit this clone does not have (a shallow checkout will do it), where
  `git log A..B` happily prints nothing and would read as "up to date";
* a deployed commit that is not an ancestor of `main`, where the two histories have diverged
  and the count of commits between them is not a measure of anything.

`stale` and `current` both exit 0. A scheduled workflow that goes red the moment a deploy is
overdue is a workflow that is red for weeks and then ignored; the issue it opens is the
signal. A red run here means the detector could not tell, which is worth waking up for.

Usage:
    python3 scripts/deploy_staleness.py [--max-age-days N] [--repo OWNER/NAME] [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_REPO = "ChelseaKR/afterward"
DEFAULT_WORKFLOW = "deploy.yml"
DEFAULT_MAX_AGE_DAYS = 14

#: The paths whose contents become bytes a visitor receives. The Next.js export is built
#: from `web/`; `src/` builds the *dataset*, which reaches production as a release asset on
#: its own clock and is guarded on the deploy path by `scripts/dataset_shape_check.py`. A
#: Python change is therefore not a reason to redeploy the site, and counting it as one
#: would make this report cry wolf on almost every commit.
SITE_SOURCE_PREFIX = "web/"

#: Files under `web/` that no visitor ever receives. Deliberately short: a path wrongly
#: called shippable produces one unnecessary line in a report, and a path wrongly called
#: test-only hides a real change, so the list only holds spellings this repository uses.
NON_SHIPPING_SUFFIXES = (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")
NON_SHIPPING_NAMES = ("vitest.config.ts", "playwright.config.ts")
NON_SHIPPING_DIRECTORIES = ("__tests__/", "e2e/")

_SHA = re.compile(r"^[0-9a-f]{40}$")


class StalenessUnknown(Exception):
    """The comparison cannot be made, so no number about it may be reported."""


@dataclass(frozen=True)
class DeployRecord:
    """The commit a successful production deploy ran against."""

    run_id: int
    head_sha: str
    head_branch: str
    finished_at: datetime
    html_url: str


@dataclass(frozen=True)
class Drift:
    """How far the deployed commit is behind `main`, and whether that is too far."""

    deployed: DeployRecord
    total_commits: int
    shipping_commits: int
    oldest_shipping_sha: str | None
    oldest_shipping_at: datetime | None
    now: datetime
    max_age_days: int

    @property
    def days_since_deploy(self) -> float:
        return (self.now - self.deployed.finished_at).total_seconds() / 86400.0

    @property
    def days_waiting(self) -> float | None:
        """How long the oldest undeployed visitor-visible commit has been waiting.

        `None` when there is no such commit, which is not the same as zero and must not be
        rendered as it.
        """
        if self.oldest_shipping_at is None:
            return None
        return (self.now - self.oldest_shipping_at).total_seconds() / 86400.0

    @property
    def verdict(self) -> str:
        waiting = self.days_waiting
        if waiting is None:
            return "current"
        return "stale" if waiting >= self.max_age_days else "current"


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def newest_successful_deploy(runs: Iterable[Mapping[str, Any]]) -> DeployRecord:
    """The most recently finished successful deploy, or a refusal to guess.

    Sorted here rather than trusted from the API: `?status=success` is a filter, not an
    ordering guarantee, and reading `[0]` because the answer usually arrives newest-first is
    the kind of assumption that reports the wrong commit on the day it stops holding.
    """
    candidates: list[DeployRecord] = []
    for run in runs:
        if run.get("conclusion") != "success":
            continue
        finished = run.get("updated_at") or run.get("created_at")
        head_sha = str(run.get("head_sha", ""))
        if not finished or not _SHA.fullmatch(head_sha):
            continue
        candidates.append(
            DeployRecord(
                run_id=int(run["id"]),
                head_sha=head_sha,
                head_branch=str(run.get("head_branch", "")),
                finished_at=_parse_timestamp(str(finished)),
                html_url=str(run.get("html_url", "")),
            )
        )
    if not candidates:
        raise StalenessUnknown(
            "no successful run of the deploy workflow was found. That is not 'zero days "
            "behind': it means this site has never been deployed by this workflow, or the "
            "run history no longer reaches back to when it was."
        )
    newest = max(candidates, key=lambda record: record.finished_at)
    if newest.head_branch != "main":
        raise StalenessUnknown(
            f"the newest successful deploy (run {newest.run_id}) ran against branch "
            f"{newest.head_branch!r}, not main, so comparing it with main measures nothing."
        )
    return newest


def ships_to_visitors(path: str) -> bool:
    """Does a change to this path change the bytes a visitor receives?"""
    if not path.startswith(SITE_SOURCE_PREFIX):
        return False
    tail = path[len(SITE_SOURCE_PREFIX) :]
    if any(tail.endswith(suffix) for suffix in NON_SHIPPING_SUFFIXES):
        return False
    if tail.split("/")[-1] in NON_SHIPPING_NAMES:
        return False
    return not any(directory in f"{tail}" for directory in NON_SHIPPING_DIRECTORIES)


def _git(*args: str) -> str:
    command = ["git", "-C", str(REPO_ROOT), *args]
    # A fixed argument vector; every interpolated value is a 40-hex SHA or a literal
    # written above. No shell.
    result = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode != 0:
        raise StalenessUnknown(
            f"`{' '.join(args)}` failed, so the comparison could not be made:\n"
            f"{result.stdout}{result.stderr}".strip()
        )
    return result.stdout


def require_comparable(deployed_sha: str, head: str) -> None:
    """Refuse to compare two commits whose relationship makes a count meaningless."""
    for sha, label in ((deployed_sha, "the deployed commit"), (head, "the head commit")):
        probe = subprocess.run(  # noqa: S603
            ["git", "-C", str(REPO_ROOT), "cat-file", "-e", f"{sha}^{{commit}}"],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode != 0:
            raise StalenessUnknown(
                f"{label} {sha} is not in this clone, so `git log` between them would "
                "print nothing and read as 'up to date'. Check out with fetch-depth: 0."
            )
    ancestry = subprocess.run(  # noqa: S603
        ["git", "-C", str(REPO_ROOT), "merge-base", "--is-ancestor", deployed_sha, head],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    if ancestry.returncode != 0:
        raise StalenessUnknown(
            f"the deployed commit {deployed_sha[:8]} is not an ancestor of {head}. The two "
            "histories have diverged, and the number of commits between them is not a "
            "measure of how far behind the site is."
        )


def commits_between(deployed_sha: str, head: str) -> list[tuple[str, datetime, list[str]]]:
    """Every commit on `head` that the deployed commit does not have, with its paths."""
    raw = _git(
        "log",
        "--first-parent",
        "--reverse",
        "--name-only",
        "--format=%x00%H%x1f%cI",
        f"{deployed_sha}..{head}",
    )
    commits: list[tuple[str, datetime, list[str]]] = []
    for block in raw.split("\0"):
        if not block.strip():
            continue
        header, _, body = block.partition("\n")
        sha, _, committed = header.partition("\x1f")
        paths = [line for line in body.splitlines() if line.strip()]
        commits.append((sha, _parse_timestamp(committed), paths))
    return commits


def measure(
    deployed: DeployRecord,
    commits: Sequence[tuple[str, datetime, list[str]]],
    *,
    now: datetime,
    max_age_days: int,
) -> Drift:
    shipping = [
        (sha, when) for sha, when, paths in commits if any(ships_to_visitors(p) for p in paths)
    ]
    oldest_sha, oldest_at = shipping[0] if shipping else (None, None)
    return Drift(
        deployed=deployed,
        total_commits=len(commits),
        shipping_commits=len(shipping),
        oldest_shipping_sha=oldest_sha,
        oldest_shipping_at=oldest_at,
        now=now,
        max_age_days=max_age_days,
    )


def render(drift: Drift) -> str:
    """The human report. Every number in it is one the comparison actually produced."""
    lines = [
        f"Live commit:   {drift.deployed.head_sha[:8]} "
        f"(deploy run {drift.deployed.run_id}, {drift.deployed.finished_at:%Y-%m-%d})",
        f"Days since the last successful deploy: {drift.days_since_deploy:.1f}",
        f"Commits on main since then:            {drift.total_commits}",
        f"...of which change what visitors get:  {drift.shipping_commits}",
    ]
    waiting = drift.days_waiting
    if waiting is None or drift.oldest_shipping_sha is None:
        lines.append("No undeployed change touches web/, so nothing a visitor sees is waiting.")
    else:
        lines.append(
            f"Oldest undeployed visitor-visible commit: {drift.oldest_shipping_sha[:8]} "
            f"({waiting:.1f} days ago, threshold {drift.max_age_days})"
        )
    lines.append(f"Verdict: {drift.verdict}")
    return "\n".join(lines)


def as_json(drift: Drift) -> dict[str, Any]:
    return {
        "verdict": drift.verdict,
        "live_commit": drift.deployed.head_sha,
        "deploy_run_id": drift.deployed.run_id,
        "deploy_run_url": drift.deployed.html_url,
        "deployed_at": drift.deployed.finished_at.isoformat(),
        "days_since_deploy": round(drift.days_since_deploy, 1),
        "commits_behind": drift.total_commits,
        "shipping_commits_behind": drift.shipping_commits,
        "oldest_shipping_commit": drift.oldest_shipping_sha,
        "days_waiting": None if drift.days_waiting is None else round(drift.days_waiting, 1),
        "max_age_days": drift.max_age_days,
    }


def fetch_runs(repo: str, workflow: str) -> list[dict[str, Any]]:
    command = [
        "gh",
        "api",
        "--paginate",
        f"repos/{repo}/actions/workflows/{workflow}/runs?status=success&per_page=100",
        "--jq",
        ".workflow_runs[]",
    ]
    # A fixed argument vector built from literals and `--repo`, which is validated below.
    result = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode != 0:
        raise StalenessUnknown(
            f"`gh api` could not read the run history of {workflow} in {repo}:\n"
            f"{result.stdout}{result.stderr}".strip()
        )
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def _write_github_output(drift: Drift | None, error: str | None) -> None:
    destination = os.environ.get("GITHUB_OUTPUT")
    if not destination:
        return
    payload = (
        {"verdict": "unknown", "detail": error or "unknown"}
        if drift is None
        else {**as_json(drift), "detail": render(drift)}
    )
    with open(destination, "a", encoding="utf-8") as handle:
        handle.write(f"verdict={payload['verdict']}\n")
        handle.write("report<<DEPLOY_STALENESS_EOF\n")
        handle.write(f"{payload.get('detail', '')}\n")
        handle.write("DEPLOY_STALENESS_EOF\n")
        handle.write(f"json={json.dumps(payload)}\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--workflow", default=DEFAULT_WORKFLOW)
    parser.add_argument("--head", default="origin/main")
    parser.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS)
    parser.add_argument("--json", action="store_true", help="emit the machine-readable report")
    arguments = parser.parse_args(argv)

    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", arguments.repo):
        print(f"::error::--repo {arguments.repo!r} is not an owner/name pair.", file=sys.stderr)
        return 1
    if arguments.max_age_days < 1:
        print("::error::--max-age-days must be at least 1.", file=sys.stderr)
        return 1

    try:
        deployed = newest_successful_deploy(fetch_runs(arguments.repo, arguments.workflow))
        require_comparable(deployed.head_sha, arguments.head)
        drift = measure(
            deployed,
            commits_between(deployed.head_sha, arguments.head),
            now=datetime.now(UTC),
            max_age_days=arguments.max_age_days,
        )
    except StalenessUnknown as unknown:
        print(f"::error::Deploy staleness is unknown: {unknown}", file=sys.stderr)
        _write_github_output(None, str(unknown))
        return 1

    print(json.dumps(as_json(drift), indent=2) if arguments.json else render(drift))
    _write_github_output(drift, None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
