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
  * a competency-based program, which has no clock length by design and must render as that
    rather than as "length not reported"

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
        """Add up to ``limit`` programs matching ``predicate``, and say if the case is missing.

        The warning asks whether the *fixture* covers the case, not whether this call added
        anything to it. A case an earlier call already satisfied is covered, and saying "no
        program matched" about it would send the next person looking for a gap that is not
        there. It reads the whole snapshot rather than only what was chosen, so a case absent
        from the source is still reported as absent.
        """
        count = 0
        for program in programs:
            if count >= limit:
                break
            if program["uuid"] in chosen or not predicate(program):
                continue
            chosen[program["uuid"]] = program
            count += 1
        if count == 0 and not any(predicate(program) for program in chosen.values()):
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
    # Two of them, one that publishes outcomes and one that publishes none, because the
    # length cell and the outcome block are rendered by different code and a competency-based
    # program has to survive both. Only 12 of California's 3,266 programs are in this state,
    # so a top-up sample would almost certainly contain none and CI would build a site that
    # never exercises the label at all.
    take(
        "competency-based, reporting outcomes",
        lambda p: p["length"]["competency_based"] and outcomes(p)["reported"],
        limit=1,
    )
    take(
        "competency-based, reporting nothing",
        lambda p: p["length"]["competency_based"] and not outcomes(p)["reported"],
        limit=1,
    )
    # A program that genuinely filed no length, if the snapshot still has one. It had none on
    # 2026-08-07: every California program either files a length or is competency-based, and
    # all 12 that once looked unreported were the latter. The case is still asked for, because
    # the site renders it differently and a later snapshot may bring one back.
    take(
        "no length filed at all",
        lambda p: (
            not p["length"]["competency_based"]
            and p["length"]["weeks"] is None
            and p["length"]["hours"] is None
        ),
        limit=1,
    )

    for program in programs:
        if len(chosen) >= TARGET_PROGRAMS:
            break
        chosen.setdefault(program["uuid"], program)

    return list(chosen.values())


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def fixture_coverage(
    programs: list[dict[str, Any]],
    occupations: dict[str, Any],
    source: dict[str, Any],
) -> dict[str, Any]:
    """Describe the fixture, not the dataset it was cut from.

    An earlier version overrode six keys and carried the rest across, so the fixture's
    coverage file claimed 60 programs alongside 3,266 with a cost and 584 providers. That is
    not merely untidy: ``peer_medians[...].reporting`` is rendered, so every program page in
    the CI-built site read "Typical California program: 69% of 1,766 reporting" for a dataset
    holding sixty. Every count is therefore recomputed here, and anything that cannot be
    is dropped rather than inherited.
    """
    outcomes = [p["outcomes"] for p in programs]
    total = len(programs)
    reported = sum(1 for o in outcomes if o["reported"])
    matched = sum(1 for p in programs if p["occupations"])
    mapped = sum(1 for p in programs if p.get("region"))

    def counted(key: str) -> int:
        return sum(1 for o in outcomes if o.get(key) is not None)

    def pct(part: int) -> float:
        return round(100 * part / total, 1) if total else 0.0

    peers = {
        measure: {
            "median": _median([o[measure] for o in outcomes if o.get(measure) is not None]),
            "reporting": counted(measure),
        }
        for measure in ("completion_rate", "employment_rate_q2", "median_earnings")
    }

    return {
        "snapshot_date": source["snapshot_date"],
        "is_fixture": True,
        "total_programs": total,
        "programs_with_any_outcome": reported,
        "programs_with_median_earnings": counted("median_earnings"),
        "programs_with_employment_rate": counted("employment_rate_q2"),
        "programs_with_completion_rate": counted("completion_rate"),
        "programs_with_cost": sum(
            1 for p in programs if p["cost"]["total_out_of_pocket"] is not None
        ),
        "programs_with_soc": sum(1 for p in programs if p["soc_codes"]),
        "programs_matched_to_occupation": matched,
        "distinct_providers": len({p["provider_name"] for p in programs if p["provider_name"]}),
        "distinct_occupations_matched": len(occupations),
        "occupation_rows_loaded": len(occupations),
        "programs_mapped_to_area": mapped,
        "programs_without_area": total - mapped,
        "outcome_coverage_pct": pct(reported),
        "occupation_match_pct": pct(matched),
        "area_match_pct": pct(mapped),
        # A genuine statewide figure from DOL, not a property of this sample, so it carries
        # over unchanged. Everything else above describes the sixty rows in this file.
        "state_benchmark": source.get("state_benchmark"),
        "peer_medians": peers,
    }


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

    (DEST / "coverage.json").write_text(
        json.dumps(fixture_coverage(programs, occupations, coverage), indent=1),
        encoding="utf-8",
    )

    summary = fixture_coverage(programs, occupations, coverage)
    # Across every occupation a program feeds, not just its first — the same bug that once
    # made the site's headline shrinking count 229 instead of 538.
    shrinking = sum(
        1
        for p in programs
        if any(
            o.get("percent_change") is not None and o["percent_change"] < 0
            for o in p["occupations"]
        )
    )
    print(
        f"fixture: {len(programs)} programs, {len(occupations)} occupations "
        f"({summary['programs_with_any_outcome']} reporting outcomes, "
        f"{shrinking} shrinking) -> {DEST}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
