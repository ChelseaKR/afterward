#!/usr/bin/env python3
"""Refuse to publish outcome figures without the statement that says how to read them.

`employed_q2` and `employment_rate_q2` ship in every program record and are not a numerator
and a denominator of each other (#25). A consumer who divides the count by `total_exited`
disagrees with the published rate on two thirds of the programs where both exist, and 65
records report more people employed than exited at all. The reason is in the federal form:
the rate's denominator is ETA-9171 DE129, which this feed does not publish.

That finding lived in `PROVENANCE.md` and in comments beside both fields. Neither travels
with the data. `coverage.json` now carries an `employment_measures` block that does, and this
gate is what keeps the two from drifting apart:

1. **The statement must be there.** A dataset that publishes `employed_q2` without it is a
   dataset that hands a consumer two figures and no way to tell which is a rate.
2. **The statement must describe *this* dataset.** The counts are re-derived from the
   packaged `programs.json` and compared with the published block. A statement copied through
   from an older snapshot -- which is exactly how the offline build carries coverage keys
   forward -- describes some other dataset, and a stale claim that reads as a current one is
   worse than no claim.

Run against a dataset directory (`web/public/data` by default).
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from afterward.build import AUTHORITATIVE_EMPLOYMENT_MEASURE, employment_measure_coverage

DATA = Path("web/public/data")

BLOCK = "employment_measures"


def problems(dataset_dir: Path) -> list[str]:
    programs = json.loads((dataset_dir / "programs.json").read_text(encoding="utf-8"))["programs"]
    coverage = json.loads((dataset_dir / "coverage.json").read_text(encoding="utf-8"))
    publishing = sum(
        1 for p in programs if (p.get("outcomes") or {}).get("employed_q2") is not None
    )
    published: Any = coverage.get(BLOCK)
    if not isinstance(published, dict):
        if publishing == 0:
            return []
        return [
            f"{publishing} programs publish employed_q2 and coverage.json carries no "
            f"{BLOCK!r} block. Nothing in this dataset says which employment figure is the "
            f"rate. Rebuild with `make data`."
        ]

    measured = asdict(employment_measure_coverage(programs))
    drifted = [
        f"{BLOCK}.{key}: says {published.get(key)!r}, this dataset measures {value!r}"
        for key, value in measured.items()
        if published.get(key) != value
    ]
    if drifted:
        return [
            "the published employment-measure statement describes a different dataset:",
            *drifted,
        ]
    if published.get("authoritative") != AUTHORITATIVE_EMPLOYMENT_MEASURE:
        return [f"{BLOCK}.authoritative names {published.get('authoritative')!r}"]
    return []


def main(argv: list[str]) -> int:
    dataset_dir = Path(argv[0]) if argv else DATA
    for name in ("programs.json", "coverage.json"):
        if not (dataset_dir / name).exists():
            print(f"outcome-claims-check: no {name} at {dataset_dir}")
            return 1
    found = problems(dataset_dir)
    if found:
        print("outcome-claims-check: REFUSING — figures without the statement that reads them")
        for line in found:
            print(f"  {line}")
        return 1
    print(
        "outcome-claims-check: the employment-measure statement is present and matches "
        f"{dataset_dir}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
