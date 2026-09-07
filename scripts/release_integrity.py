#!/usr/bin/env python3
"""Is every published dataset release still the dataset it says it is?

ADR 0001 declares the Release & Versioning standard's semver pipeline N/A here, for a stated
reason: nothing consumes an afterward *version*. What this project does release through GitHub
Releases is the **dataset** -- `make dataset-publish` cuts `dataset-<snapshot>` with a tarball
and a sha256 beside it -- and `deploy.yml` consumes exactly that. The release is the handshake
between a workstation that can reach DOL and a runner that cannot.

The gap this closes is *when* that handshake is checked.

`deploy.yml` checks it well: one tarball, `sha256sum -c`, refuse a fixture, refuse a count
below the floor, refuse a manifest that disagrees with what is on disk. But every one of those
runs only for the single tag somebody typed into a dispatch form, at the moment they typed it.
The workflow is dispatch-only by design, and on 2026-09-07 it had not run for 21 days. So a
release can be malformed, mis-tagged, or missing an asset for an unbounded time with nothing
anywhere saying so -- and the first thing to find out would be a deploy, which is the worst
place to find out.

This asks the same questions on a schedule, of **every** published release rather than one, and
publishes nothing.

WHAT IT CHECKS THAT A DEPLOY CANNOT

Two of these are only answerable across the set, and one is answerable per release but nothing
asks it:

* **The tag's date against the snapshot date inside its own tarball.** `make dataset-publish`
  derives both from the same `coverage.json`, so they agree by construction -- which is exactly
  why nothing has ever checked them, and exactly why a hand-cut or re-uploaded release could
  disagree. A release tagged `dataset-2026-08-17` carrying an 2026-08-04 snapshot would deploy
  cleanly and publish three-week-old data under today's name. Every guard in `deploy.yml` would
  pass it.
* **Assets that are absent or duplicated.** `deploy.yml` refuses anything but exactly one
  tarball, but only for the tag being deployed.
* **A draft or a prerelease.** `gh release download` will fetch a draft for an authorised
  caller, so a half-finished release sitting in the list is a thing a dispatch can reach.

REFUSALS: NOTHING HERE MAY REPORT A COMFORTABLE NUMBER IT DID NOT MEASURE

An empty release list is a **refusal**, not a pass. "0 releases checked, 0 problems" is the
portfolio's dominant defect wearing a checker's clothes: a green signal that means nothing was
measured. Same for a listing that failed, an asset that would not download, and a tarball that
will not open. Every one exits non-zero with the reason named.

Usage:
    python3 scripts/release_integrity.py [--repo OWNER/NAME] [--tag TAG] [--json]
                                         [--min-programs N] [--keep DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_REPO = "ChelseaKR/afterward"

MIN_PROGRAMS = 2000
"""The floor `Makefile` and `deploy.yml` both use. Real: 3,266. Fixture: 60."""

TAG_PATTERN = re.compile(r"^dataset-(\d{4}-\d{2}-\d{2})$")
"""The shape `make dataset-publish` cuts. A tag that does not match is not one of ours."""

READ_CHUNK = 1024 * 1024


@dataclass
class ReleaseReport:
    """One release, and every way it failed to be what it claims."""

    tag: str
    problems: list[str] = field(default_factory=list)
    snapshot_date: str | None = None
    total_programs: int | None = None

    @property
    def ok(self) -> bool:
        return not self.problems


def _gh(args: list[str]) -> str:
    """Run the GitHub CLI and return stdout, or raise with what it said on stderr.

    Fixed argv, never a shell string: nothing here interpolates into a command line. The
    repository is named by the caller rather than appended here, because `gh api` addresses it
    in the endpoint path and rejects `--repo` -- which is how the first run of this script
    failed, printing a usage message and, through a pipe, an exit code of zero.
    """
    completed = subprocess.run(  # noqa: S603
        ["gh", *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"`gh {' '.join(args)}` failed ({completed.returncode}): "
            f"{completed.stderr.strip() or 'no stderr'}"
        )
    return completed.stdout


def list_releases(repo: str) -> list[dict[str, object]]:
    """Every published release, newest first, as the API reports them."""
    raw = _gh(
        [
            "api",
            f"repos/{repo}/releases",
            "--paginate",
            "--jq",
            ".[] | {tag_name, draft, prerelease, assets: [.assets[].name]}",
        ]
    )
    releases: list[dict[str, object]] = []
    for line in raw.splitlines():
        line = line.strip()
        if line:
            releases.append(json.loads(line))
    return releases


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(READ_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def digest_from_sidecar(text: str) -> str | None:
    """The hex digest out of a `sha256sum` / `shasum -a 256` line, or None if unreadable.

    None rather than an exception, and never a partial parse: a sidecar this cannot read is a
    release that cannot be verified, which the caller records as a problem. Silently accepting
    a malformed sidecar would make the comparison below pass for want of anything to compare.
    """
    for line in text.splitlines():
        candidate = line.strip().split()
        if candidate and re.fullmatch(r"[0-9a-fA-F]{64}", candidate[0]):
            return candidate[0].lower()
    return None


def unsafe_members(archive: tarfile.TarFile) -> list[str]:
    """Members that would write outside the directory they are extracted into.

    `deploy.yml` extracts one of these tarballs straight into `web/public/data` in the runner
    workspace. An absolute path or a `..` segment would put files somewhere else entirely, and
    a symlink pointing out of the tree does the same on the next write. The tarballs are cut by
    `make dataset-package` from a directory this project wrote, so this should always be empty
    -- which is the reason to check it rather than the reason not to.
    """
    bad: list[str] = []
    for member in archive.getmembers():
        name = member.name
        if (
            name.startswith("/")
            or Path(name).is_absolute()
            or any(part == ".." for part in Path(name).parts)
        ):
            bad.append(name)
        elif (member.issym() or member.islnk()) and (
            member.linkname.startswith("/") or ".." in Path(member.linkname).parts
        ):
            bad.append(f"{name} -> {member.linkname}")
    return bad


def check_extracted_dataset(
    root: Path, *, expected_snapshot: str, min_programs: int
) -> tuple[list[str], str | None, int | None]:
    """The dataset inside a release, against the tag that names it.

    Returns ``(problems, snapshot_date, total_programs)``. The two values are returned even
    when there are problems, so a report can say what it read rather than only that it
    objected.
    """
    problems: list[str] = []
    coverage_path = root / "coverage.json"
    if not coverage_path.is_file():
        return ["no coverage.json in the tarball"], None, None

    try:
        coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return [f"coverage.json is not readable JSON: {error}"], None, None
    if not isinstance(coverage, dict):
        return ["coverage.json is not an object"], None, None

    snapshot = str(coverage.get("snapshot_date", "")).strip() or None
    total_raw = coverage.get("total_programs")
    total = total_raw if isinstance(total_raw, int) else None

    if coverage.get("is_fixture"):
        problems.append(
            "coverage.json carries is_fixture: true -- this release holds the 60-program CI "
            "fixture, not production data"
        )
    if snapshot is None:
        problems.append("coverage.json states no snapshot_date")
    elif snapshot != expected_snapshot:
        problems.append(
            f"the tag names snapshot {expected_snapshot} and the dataset inside it says "
            f"{snapshot}; a deploy of this tag would publish one under the other's name"
        )
    if total is None:
        problems.append("coverage.json states no integer total_programs")
    else:
        if total < min_programs:
            problems.append(f"total_programs={total} is below the {min_programs} floor")
        on_disk = len(list((root / "programs").glob("*.json")))
        if on_disk != total:
            problems.append(
                f"{on_disk} program files in the tarball but coverage.json claims {total}"
            )
    return problems, snapshot, total


@dataclass
class ReleaseShape:
    """What the API says about a release, before anything is downloaded.

    ``asset_names`` is None when the assets are not the one-tarball-and-one-sidecar pair the
    rest of this cannot proceed without. The caller stops there rather than downloading, so a
    release with two tarballs is reported as that and not as a confusing digest mismatch.
    """

    snapshot: str | None
    problems: list[str]
    asset_names: tuple[str, str] | None


def check_release_shape(release: dict[str, object]) -> ReleaseShape:
    """The tag's shape, the draft/prerelease flags, and the asset pair."""
    tag = str(release.get("tag_name", ""))
    matched = TAG_PATTERN.match(tag)
    if matched is None:
        return ReleaseShape(
            snapshot=None,
            problems=[
                f"tag {tag!r} is not the dataset-YYYY-MM-DD shape `make dataset-publish` cuts"
            ],
            asset_names=None,
        )

    problems: list[str] = []
    if release.get("draft"):
        problems.append("published as a draft; a dispatch could still download it")
    if release.get("prerelease"):
        problems.append("marked prerelease; the deploy path makes no such distinction")

    raw_assets = release.get("assets") or []
    assets = [str(name) for name in raw_assets] if isinstance(raw_assets, list) else []
    tarballs = [name for name in assets if name.endswith(".tar.gz")]
    sidecars = [name for name in assets if name.endswith(".tar.gz.sha256")]
    if len(tarballs) != 1:
        problems.append(f"carries {len(tarballs)} tarballs; expected exactly one")
    if len(sidecars) != 1:
        problems.append(f"carries {len(sidecars)} sha256 sidecars; expected exactly one")

    pair = (tarballs[0], sidecars[0]) if len(tarballs) == 1 and len(sidecars) == 1 else None
    return ReleaseShape(snapshot=matched.group(1), problems=problems, asset_names=pair)


def check_release(
    release: dict[str, object], *, repo: str, work_dir: Path, min_programs: int
) -> ReleaseReport:
    """Download one release's assets and hold them to everything the tag claims."""
    tag = str(release.get("tag_name", ""))
    report = ReleaseReport(tag=tag)

    shape = check_release_shape(release)
    report.problems.extend(shape.problems)
    if shape.snapshot is None or shape.asset_names is None:
        return report
    expected_snapshot = shape.snapshot
    tarballs = [shape.asset_names[0]]
    sidecars = [shape.asset_names[1]]

    target = work_dir / tag
    target.mkdir(parents=True, exist_ok=True)
    try:
        _gh(
            [
                "release",
                "download",
                tag,
                "--dir",
                str(target),
                "--pattern",
                "*.tar.gz",
                "--pattern",
                "*.tar.gz.sha256",
                "--clobber",
                "--repo",
                repo,
            ]
        )
    except RuntimeError as error:
        report.problems.append(f"assets would not download: {error}")
        return report

    tarball = target / tarballs[0]
    sidecar = target / sidecars[0]
    if not tarball.is_file() or not sidecar.is_file():
        report.problems.append("the download did not produce both assets")
        return report

    declared = digest_from_sidecar(sidecar.read_text(encoding="utf-8"))
    if declared is None:
        report.problems.append(f"{sidecar.name} carries no readable sha256 digest")
    else:
        actual = sha256_of(tarball)
        if actual != declared:
            report.problems.append(
                f"{tarball.name} hashes to {actual}, its sidecar says {declared}"
            )
            return report

    extract_root = target / "unpacked"
    try:
        with tarfile.open(tarball, "r:gz") as archive:
            escaping = unsafe_members(archive)
            if escaping:
                report.problems.append(
                    "tarball members would write outside the extraction directory: "
                    + ", ".join(escaping[:5])
                )
                return report
            extract_root.mkdir(parents=True, exist_ok=True)
            archive.extractall(extract_root, filter="data")  # nosec B202 - members checked above
    except (tarfile.TarError, OSError) as error:
        report.problems.append(f"tarball will not open: {error}")
        return report

    problems, snapshot, total = check_extracted_dataset(
        extract_root, expected_snapshot=expected_snapshot, min_programs=min_programs
    )
    report.problems.extend(problems)
    report.snapshot_date = snapshot
    report.total_programs = total
    return report


def run(
    *, repo: str, tag: str | None, min_programs: int, work_dir: Path
) -> tuple[int, dict[str, object]]:
    """Check every release (or one), and return ``(exit_code, result)``."""
    try:
        releases = list_releases(repo)
    except (RuntimeError, ValueError) as error:
        return 2, {"verdict": "cannot-check", "reason": f"could not list releases: {error}"}

    if tag is not None:
        releases = [r for r in releases if r.get("tag_name") == tag]
        if not releases:
            return 2, {"verdict": "cannot-check", "reason": f"no release tagged {tag}"}

    dataset_releases = [r for r in releases if TAG_PATTERN.match(str(r.get("tag_name", "")))]
    if not dataset_releases:
        # The refusal that matters. This project's delivery *is* the dataset release, so a
        # run that found none has not established that everything is fine; it has established
        # nothing, and saying "0 problems" would be a green signal over an empty set.
        return 2, {
            "verdict": "cannot-check",
            "reason": (
                "no dataset-YYYY-MM-DD releases found. That is not a clean bill of health: "
                "the dataset release is this project's delivery, and none was checked."
            ),
        }

    reports = [
        check_release(release, repo=repo, work_dir=work_dir, min_programs=min_programs)
        for release in dataset_releases
    ]
    failing = [report for report in reports if not report.ok]
    result: dict[str, object] = {
        "verdict": "ok" if not failing else "problems",
        "repo": repo,
        "checked": len(reports),
        "releases": [
            {
                "tag": report.tag,
                "ok": report.ok,
                "snapshot_date": report.snapshot_date,
                "total_programs": report.total_programs,
                "problems": report.problems,
            }
            for report in reports
        ],
    }
    return (0 if not failing else 1), result


def _print_human(result: dict[str, object]) -> None:
    if result["verdict"] == "cannot-check":
        print(f"REFUSING: {result['reason']}")
        return
    entries = result.get("releases")
    if not isinstance(entries, list):
        print("REFUSING: the result carries no release list")
        return
    for entry in entries:
        head = "ok  " if entry["ok"] else "BAD "
        snapshot = entry["snapshot_date"] or "?"
        total = entry["total_programs"]
        count = f"{total:,} programs" if isinstance(total, int) else "programs unknown"
        print(f"{head}{entry['tag']}  snapshot {snapshot}, {count}")
        for problem in entry["problems"]:
            print(f"      - {problem}")
    print(f"\n{result['checked']} release(s) checked; verdict: {result['verdict']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--tag", default=None, help="check one release instead of all of them")
    parser.add_argument("--min-programs", type=int, default=MIN_PROGRAMS)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--keep",
        default=None,
        help="download into this directory and leave it in place, for inspection",
    )
    args = parser.parse_args(argv)

    if args.keep:
        keep = Path(args.keep)
        keep.mkdir(parents=True, exist_ok=True)
        code, result = run(
            repo=args.repo, tag=args.tag, min_programs=args.min_programs, work_dir=keep
        )
    else:
        with tempfile.TemporaryDirectory(prefix="afterward-release-") as scratch:
            code, result = run(
                repo=args.repo,
                tag=args.tag,
                min_programs=args.min_programs,
                work_dir=Path(scratch),
            )

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        _print_human(result)
    return code


if __name__ == "__main__":
    sys.exit(main())
