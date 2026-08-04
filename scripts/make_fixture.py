#!/usr/bin/env python3
"""Build a small, committed dataset the site can be built and tested against offline.

Why this exists: CI cannot fetch the live sources. The U.S. DOL endpoint returns 403 to
GitHub Actions runners, and even if it did not, a build that depends on a third party being
up is a build that fails for reasons unrelated to the change under test.

The fixture is deliberately chosen rather than randomly sampled. It has to contain every
case the UI renders differently, or a green CI run would prove very little:

  * programs with full outcomes, and programs that reported nothing at all
  * a suppressed measure sitting next to a reported one on the same record
  * an occupation projected to shrink, and one projected to grow
  * a small cohort that should trigger the sample-size caution
  * a program with no matching occupation
  * at least one program with no reported cost

Regenerate with `make fixture` after a real `make data`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "web" / "public" / "data"
DEST = REPO_ROOT / "fixtures" / "data"

TARGET_PROGRAMS = 60


def load(name: str) -> Any:
    return json.loads((SOURCE / name).read_text(encoding="utf-8"))


def pick(programs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Choose programs covering every rendering case, then top up to TARGET_PROGRAMS."""
    chosen: dict[str, dict[str, Any]] = {}

    def take(label: str, predicate: Any, limit: int = 4) -> None:
        count = 0
        for program in programs:
            if count >= limit:
                break
            if program["uuid"] in chosen or not predicate(program):
                continue
            chosen[program["uuid"]] = program
            count += 1
        if count == 0:
            print(f"  warning: no program matched {label!r}")

    outcomes = lambda p: p["outcomes"]  # noqa: E731

    take("full outcomes", lambda p: outcomes(p)["reported"] and p["occupations"])
    take("nothing reported", lambda p: not outcomes(p)["reported"])
    take(
        "partially suppressed",
        lambda p: (
            outcomes(p)["reported"]
            and any(outcomes(p)[k] is None for k in ("median_earnings", "employment_rate_q2"))
        ),
    )
    take(
        "shrinking occupation",
        lambda p: p["occupations"] and (p["occupations"][0].get("percent_change") or 0) < 0,
    )
    take(
        "growing occupation",
        lambda p: p["occupations"] and (p["occupations"][0].get("percent_change") or 0) > 0,
    )
    take(
        "small cohort",
        lambda p: (
            (outcomes(p)["total_exited"] or 0) > 0 and (outcomes(p)["total_exited"] or 0) <= 25
        ),
    )
    take("no matching occupation", lambda p: not p["occupations"])
    take("no reported cost", lambda p: p["cost"]["total_out_of_pocket"] is None)
    take("has a description", lambda p: bool(p.get("description")))

    for program in programs:
        if len(chosen) >= TARGET_PROGRAMS:
            break
        chosen.setdefault(program["uuid"], program)

    return list(chosen.values())


def main() -> int:
    if not (SOURCE / "programs.json").exists():
        print(f"no dataset at {SOURCE} — run `make data` first")
        return 1

    programs_doc = load("programs.json")
    occupations_doc = load("occupations.json")
    coverage = load("coverage.json")

    programs = pick(programs_doc["programs"])
    needed = {soc for p in programs for soc in p["soc_codes"]}
    occupations = {soc: occ for soc, occ in occupations_doc["occupations"].items() if soc in needed}

    DEST.mkdir(parents=True, exist_ok=True)
    snapshot = programs_doc["snapshot_date"]

    (DEST / "programs.json").write_text(
        json.dumps(
            {"snapshot_date": snapshot, "state": programs_doc["state"], "programs": programs},
            indent=1,
        ),
        encoding="utf-8",
    )
    (DEST / "occupations.json").write_text(
        json.dumps({"snapshot_date": snapshot, "occupations": occupations}, indent=1),
        encoding="utf-8",
    )

    # Real statewide benchmark and snapshot date are kept so the fixture exercises the
    # comparison rendering; the counts are recomputed to describe the fixture itself.
    reported = sum(1 for p in programs if p["outcomes"]["reported"])
    matched = sum(1 for p in programs if p["occupations"])
    (DEST / "coverage.json").write_text(
        json.dumps(
            coverage
            | {
                "total_programs": len(programs),
                "programs_with_any_outcome": reported,
                "programs_matched_to_occupation": matched,
                "distinct_occupations_matched": len(occupations),
                "outcome_coverage_pct": round(100 * reported / len(programs), 1),
                "occupation_match_pct": round(100 * matched / len(programs), 1),
                "is_fixture": True,
            },
            indent=1,
        ),
        encoding="utf-8",
    )

    shrinking = sum(
        1
        for p in programs
        if p["occupations"] and (p["occupations"][0].get("percent_change") or 0) < 0
    )
    print(
        f"fixture: {len(programs)} programs, {len(occupations)} occupations "
        f"({reported} reporting outcomes, {shrinking} shrinking) -> {DEST}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
