#!/usr/bin/env python3
"""Confirm a CI build is the unpublishable thing it is supposed to be.

CI cannot build a production artifact and must not appear to. The DOL endpoint answers
GitHub Actions runners with 403, so CI builds the site from the committed 60-program
fixture, and it sets no ``NEXT_PUBLIC_SITE_URL``, so every absolute URL in the export names
``example.invalid``. Both facts are correct for a test build and catastrophic in a published
one, which is why ``.github/workflows/deploy.yml`` refuses both markers rather than trusting
anyone to remember the difference. This is the same pair of questions asked from the other
side: if CI ever starts producing something that looks deployable, the guards over there need
re-reading before it is.

This lived as inline shell in ``.github/workflows/ci.yml`` until 2026-08-28, which made it
the one assertion in the pipeline a developer could not reproduce: a tree that passed
``make verify`` and ``make web-verify`` could still be rejected by CI, and the only way to
find out was to push. It is a ``make`` target now, and CI calls the target.

Standard library only, and no ``afterward`` import, for the reason
``scripts/dataset_shape_check.py`` gives: a check is worth more when every job that needs it
can run it.

Usage: python3 scripts/ci_artifact_check.py [dataset-dir] [export-dir]
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from pathlib import Path

DATA = Path("web/public/data")
EXPORT = Path("web/out")

#: The hostname a build with no ``NEXT_PUBLIC_SITE_URL`` falls back to.
PLACEHOLDER_HOST = "example.invalid"


def problems(dataset_dir: Path, export_dir: Path) -> list[str]:
    """Every way this build looks more publishable than a CI build may look."""
    found: list[str] = []

    coverage = dataset_dir / "coverage.json"
    if not coverage.is_file():
        found.append(f"no {coverage}: this build has no dataset to be the fixture or not.")
    else:
        try:
            document = json.loads(coverage.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            found.append(f"{coverage} is unreadable: {exc}")
        else:
            if not document.get("is_fixture"):
                found.append(
                    f"{coverage} says is_fixture={document.get('is_fixture')!r}. "
                    "CI built a dataset that is not the fixture."
                )

    robots = export_dir / "robots.txt"
    if not robots.is_file():
        found.append(f"no {robots}: there is no export here to judge.")
    elif PLACEHOLDER_HOST not in robots.read_text(encoding="utf-8"):
        found.append(
            f"{robots} does not name {PLACEHOLDER_HOST}. A CI build carrying a real site "
            "URL is a publishable artifact."
        )

    return found


def main(argv: Sequence[str]) -> int:
    dataset_dir = Path(argv[0]) if len(argv) > 0 else DATA
    export_dir = Path(argv[1]) if len(argv) > 1 else EXPORT

    found = problems(dataset_dir, export_dir)
    if found:
        print("ci-artifact-check: REFUSING — this build looks deployable, and CI's must not")
        for line in found:
            print(f"  {line}")
        print("  Re-read the guards in .github/workflows/deploy.yml before publishing it.")
        return 1

    print("ci-artifact-check: fixture-backed and placeholder-hosted, as a CI artifact must be")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
