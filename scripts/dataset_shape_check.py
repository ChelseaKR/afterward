#!/usr/bin/env python3
"""Refuse a dataset built by a pipeline older than the code that describes it.

This is the failure this project keeps meeting: a repair lands in the repository, correct and
tested, and the artifact in production was built before it. `make data` writes the dataset on
an operator's workstation, `make dataset-publish` freezes it as an immutable release asset,
and `.github/workflows/deploy.yml` consumes that asset by tag -- so the dataset and the code
move on separate clocks and nothing in the file says which pipeline wrote it. #28 was that
shape (`clean_description` shipped and nothing rebuilt the dataset it was written to fix);
#34 was that shape again (three hijacked domains published as provider links while the review
that rejects them sat in the repository).

It happened a third time, and this is the check for it. On 2026-08-07 `clean_length` shipped:
the ETP scorecard's `-1` on the two program-length fields means the program is
competency-based -- it finishes when the student can do the work, so it has no fixed length by
design -- and not "suppressed", which is what that number means in every other column. Twelve
of California's 3,266 programs file it. The dataset release tagged `dataset-2026-08-07` was
cut hours before that commit, so every one of those twelve carries no `competency_based` key
at all, and the site published under twelve named providers' programs the words "Length: Not
reported" -- a project limitation rendered as a provider who never answered, which is the
error class this project exists to refuse.

`afterward.build.length_integrity_problems` already refuses exactly that record, and answers
"3,266 problems" when pointed at that release. It runs during a build, over payloads the
build just produced, so it can only ever see a dataset that is new by construction. Nothing
ran it on the packaging path or the publishing path, which are the two places a dataset older
than the code can actually arrive.

Standard library only, and no `afterward` import, deliberately: the deploy workflow installs
Node and no Python toolchain, so a check it cannot run there is a check that only guards the
half of the path that was never the problem.

Usage: python3 scripts/dataset_shape_check.py [dataset-dir]
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

DATA = Path("web/public/data")

ROW_ID_PREFIX = re.compile(r"^\d+\|")
"""The feed's row id, left on the front of a description by a pipeline older than ec25f6d."""


def _programs(dataset_dir: Path) -> list[dict[str, Any]]:
    document = json.loads((dataset_dir / "programs.json").read_text(encoding="utf-8"))
    programs = document["programs"]
    if not isinstance(programs, list):
        raise TypeError(f"{dataset_dir}/programs.json: 'programs' is not a list")
    return programs


def problems(programs: Sequence[dict[str, Any]]) -> list[str]:
    """Every way these records show they were written before the code that describes them.

    Counted rather than listed. Each of these is a whole-dataset property -- a pipeline
    either had the fix or it did not -- so three thousand identical lines would bury the one
    sentence that says what to do about it.

    A dataset with no records in it is refused before anything else is asked, because every
    question below is a count and every count over nothing is zero. Without this the gate
    prints "0 programs, all written by a pipeline that carries every fix this check knows
    about" and exits 0 -- a pass whose only difference from a real one is a number nobody
    reads. That is the same shape as the object-count check this project already replaced
    once: a green signal that says "nothing was measured" in the same words it uses for
    "everything is fine".
    """
    total = len(programs)
    if not total:
        return [
            "programs.json carries no programs at all. Every check below is a count, so an "
            "empty dataset passes all of them without anything having been read."
        ]

    found: list[str] = []

    leaked = sum(
        1
        for program in programs
        if isinstance(program.get("description"), str)
        and ROW_ID_PREFIX.match(program["description"])
    )
    if leaked:
        found.append(
            f"{leaked} of {total} descriptions still carry the feed row id (match ^N|). "
            "This dataset was built by a pipeline older than commit ec25f6d."
        )

    predates_length = sum(
        1
        for program in programs
        if not isinstance(program.get("length"), dict)
        or "competency_based" not in program["length"]
    )
    if predates_length:
        found.append(
            f"{predates_length} of {total} records carry no length.competency_based key. "
            "This dataset was built by a pipeline older than commit 904c231, so a program "
            "the provider filed as competency-based is indistinguishable from one that "
            "reported no length, and the site publishes 'Length: Not reported' over a fact."
        )

    return found


def miscounted(dataset_dir: Path, programs: Sequence[dict[str, Any]]) -> list[str]:
    """Whether the file this gate reads describes the same dataset the deploy counted.

    The gates on the publishing path do not all read the same file. ``make dataset-verify``
    and the deploy workflow establish that a dataset is real by comparing
    ``coverage.json``'s ``total_programs`` against the number of ``programs/*.json`` shards
    on disk -- the shards being what the site renders a page from. This check and
    ``scripts/provider_link_check.py`` both read ``programs.json``, which is a third file,
    and until now nothing compared it to either of the other two.

    So a ``programs.json`` that had lost its records -- a truncated write, a hand-edit, a
    half-finished extract -- would leave every published page intact and both of the gates
    that read it with nothing to object to. The count is the cheapest possible way to say
    that the file being audited is the dataset being shipped.
    """
    coverage_path = dataset_dir / "coverage.json"
    if not coverage_path.exists():
        return [
            f"no {coverage_path}, so there is nothing to check programs.json against. "
            "This gate runs after the coverage checks on both paths a dataset travels; "
            "reaching it without one means it is being run somewhere new."
        ]
    try:
        claimed = json.loads(coverage_path.read_text(encoding="utf-8"))["total_programs"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return [f"{coverage_path} is unreadable or carries no total_programs — {exc}"]
    if claimed != len(programs):
        return [
            f"programs.json holds {len(programs)} programs and coverage.json claims "
            f"{claimed!r}. The two describe different datasets, and the shards the site "
            "renders from are counted against coverage.json rather than against this file."
        ]
    return []


def main(argv: Sequence[str]) -> int:
    dataset_dir = Path(argv[0]) if argv else DATA
    if not (dataset_dir / "programs.json").exists():
        print(f"dataset-shape-check: no dataset at {dataset_dir}/programs.json")
        return 1
    try:
        programs = _programs(dataset_dir)
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"dataset-shape-check: dataset unreadable — {exc}")
        return 1

    found = miscounted(dataset_dir, programs) + problems(programs)
    if found:
        print("dataset-shape-check: REFUSING — this dataset is not one this code would write")
        for line in found:
            print(f"  {line}")
        print("  Run `make data` to rebuild, then `make dataset-publish` for a new release.")
        return 1

    print(
        f"dataset-shape-check: {len(programs)} programs, counted against coverage.json, "
        "all written by a pipeline that carries every fix this check knows about"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
