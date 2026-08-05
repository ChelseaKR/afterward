#!/usr/bin/env python3
"""Assert the working dataset is the real one, before anything copies or publishes it.

The dataset is gitignored and untracked, so it is the only copy of roughly 3,300 programs of
DOL and EDD fetches. On 2026-08-05 it silently became the 60-program test fixture with no
command run that should have done it, and that was noticed only because a page 404'd during
unrelated work.

`publish-preflight` stops a fixture reaching the site. This stops it reaching the *backup*,
which is the more dangerous direction: `make backup-data` mirrors with `rsync --delete`, so
backing up a corrupted dataset overwrites the last good copy with the bad one. A backup step
that runs automatically without this check is worse than a manual one that does not run.

Compares against a committed manifest so drift is detectable offline, with no network and no
memory of what the numbers ought to be.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MANIFEST = Path("data-manifest.json")
DATA = Path("web/public/data")


def counts() -> dict[str, int | str | None]:
    programs = json.loads((DATA / "programs.json").read_text())
    occupations = json.loads((DATA / "occupations.json").read_text())
    occ = occupations["occupations"]
    return {
        "programs": len(programs["programs"]),
        "occupations": len(occ),
        "snapshot_date": programs.get("snapshot_date"),
        "occupations_with_spanish": sum(1 for r in occ.values() if r.get("spanish")),
        "occupations_with_wage_spread": sum(1 for r in occ.values() if r.get("wage_spread")),
    }


def main(argv: list[str]) -> int:
    if not DATA.exists():
        print(f"dataset-check: no dataset at {DATA}")
        return 1
    try:
        actual = counts()
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"dataset-check: dataset unreadable — {exc}")
        return 1

    if "--write" in argv:
        MANIFEST.write_text(json.dumps(actual, indent=2) + "\n")
        print(f"dataset-check: manifest written — {actual['programs']} programs, "
              f"{actual['occupations']} occupations")
        return 0

    if not MANIFEST.exists():
        print("dataset-check: no manifest; run `make dataset-manifest` once the dataset is known good")
        return 1

    expected = json.loads(MANIFEST.read_text())
    problems = []

    # A shortfall is corruption. A surplus is a refresh, which is fine and expected, so only
    # the downward direction fails: a real refresh should never lose most of the dataset.
    for key in ("programs", "occupations"):
        if actual[key] < expected[key] * 0.9:
            problems.append(f"{key}: {actual[key]}, manifest says {expected[key]}")

    for key in ("occupations_with_spanish", "occupations_with_wage_spread"):
        if actual[key] == 0 and expected[key] > 0:
            problems.append(f"{key}: 0, manifest says {expected[key]} — enrichment lost")

    if problems:
        print("dataset-check: REFUSING — the working dataset does not look like the real one")
        for p in problems:
            print(f"  {p}")
        print("  Restore from the backup before copying over it or publishing it.")
        return 1

    print(
        f"dataset-check: {actual['programs']} programs, {actual['occupations']} occupations, "
        f"{actual['occupations_with_spanish']} Spanish, "
        f"{actual['occupations_with_wage_spread']} wage spreads"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
