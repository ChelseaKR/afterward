#!/usr/bin/env python3
"""Refuse a dataset whose receipts do not describe the records beside them.

Every program record in an emitted dataset gets a receipt (`afterward.receipts`), and the one
claim in it that a reader can settle with `shasum -a 256` is ``record_sha256``: the digest of
the exact bytes of ``programs/<uuid>.json``. That pairing is the whole value of the artifact,
and a pairing field that nothing consumes is not a check -- so this consumes it, on the two
paths a dataset can reach a reader by.

WHAT THIS CATCHES THAT NOTHING ELSE DOES

`dataset_shape_check.py` asks whether the records were written by code as new as this
checkout. `verify_live_site.py` asks whether the bytes the site serves are the bytes of the
release the site names. Neither can see a dataset directory **assembled from two builds** --
records from one snapshot beside receipts from another. Every count agrees, every file is
well formed, the tarball hashes to its own sidecar, and each record's receipt describes a
record that is no longer there. That is not hypothetical here: `make data` overwrites
``web/public/data`` in place, and an interrupted build leaves exactly that state.

THREE ANSWERS, NOT TWO

A dataset with **no receipts at all** predates the feature. Three published releases do
(`dataset-2026-08-04`, `-08-07`, `-08-17`), and `deploy.yml` can be asked to publish any of
them by tag, so refusing them would break a deploy over an absence that is simply history.
It is reported by name and passes -- and it is the one state that must never be silent,
because "no receipts were checked" and "every receipt checked out" are the two things a
one-line pass would make indistinguishable.

A dataset with **some** receipts is refused. That is the assembled-from-two-builds state and
there is no benign reading of it.

Standard library only, and no `afterward` import, for the same reason
`dataset_shape_check.py` has neither: `.github/workflows/deploy.yml` installs Node and no
Python toolchain, and a check the publishing path cannot run only guards the packaging path
-- which was never the one a stale dataset arrives by.

This checks the pairing, not the whole receipt. Recomputing every field needs the pipeline
that wrote it, which is `afterward verify-record`; that verb is the reader's, and
`tests/test_receipts.py` runs it over every record of a whole build.

Usage: python3 scripts/receipt_check.py [dataset-dir]
Exit codes: 0 the receipts pair with their records (or there are none), 1 they do not.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path

DATA = Path("web/public/data")

SCHEMA_VERSION = "afterward.receipt/1"
"""Kept in step with `afterward.receipts.SCHEMA_VERSION` by a test, not by hand.

Duplicated rather than imported because this file may not import the package (see the module
docstring). `tests/test_receipts.py` asserts the two strings are equal, so the copy cannot
drift silently -- which is the only thing that makes a second spelling of a constant safe.
"""


def _uuids(dataset_dir: Path) -> list[str]:
    return sorted(path.stem for path in (dataset_dir / "programs").glob("*.json"))


def problems(dataset_dir: Path) -> tuple[list[str], str, int, int]:
    """``(problems, state, receipts_checked, programs)`` for one dataset directory.

    ``state`` is one of ``paired``, ``predates_receipts`` or ``refused``, so a caller can
    tell the three apart without parsing prose.
    """
    programs = _uuids(dataset_dir)
    if not programs:
        return (
            [f"{dataset_dir}/programs holds no records, so there is nothing to pair."],
            "refused",
            0,
            0,
        )

    receipt_dir = dataset_dir / "receipts"
    receipts = (
        sorted(path.stem for path in receipt_dir.glob("*.json")) if receipt_dir.is_dir() else []
    )
    if not receipts:
        return [], "predates_receipts", 0, len(programs)

    missing = sorted(set(programs) - set(receipts))
    found = _set_problems(missing, sorted(set(receipts) - set(programs)))

    checked = 0
    for uuid in programs:
        if uuid in missing:
            continue
        record_bytes = (dataset_dir / "programs" / f"{uuid}.json").read_bytes()
        try:
            receipt = json.loads((receipt_dir / f"{uuid}.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            found.append(f"{uuid}: receipt unreadable — {exc}")
            continue
        if not isinstance(receipt, dict):
            found.append(f"{uuid}: receipt is not a JSON object")
            continue
        checked += 1
        found += _pairing_problems(uuid, receipt, record_bytes)

    return found, ("refused" if found else "paired"), checked, len(programs)


def _set_problems(missing: list[str], orphaned: list[str]) -> list[str]:
    """Records with no receipt, and receipts with no record. Both are the same event seen
    from two sides, and naming only one of them would leave half of it invisible."""
    found: list[str] = [f"{uuid}: a record with no receipt beside it" for uuid in missing[:5]]
    if len(missing) > 5:
        found.append(f"...and {len(missing) - 5} more record(s) with no receipt")
    found += [f"{uuid}: a receipt for a record this dataset does not hold" for uuid in orphaned[:5]]
    if len(orphaned) > 5:
        found.append(f"...and {len(orphaned) - 5} more receipt(s) with no record")
    return found


def _pairing_problems(uuid: str, receipt: dict[str, object], record_bytes: bytes) -> list[str]:
    """Every way one receipt fails to describe the record beside it."""
    found: list[str] = []
    if receipt.get("schema") != SCHEMA_VERSION:
        found.append(f"{uuid}: receipt schema {receipt.get('schema')!r} is not {SCHEMA_VERSION!r}")
    if receipt.get("uuid") != uuid:
        found.append(f"{uuid}: receipt names record {receipt.get('uuid')!r}")
    if receipt.get("record_path") != f"programs/{uuid}.json":
        found.append(f"{uuid}: receipt points at {receipt.get('record_path')!r}")
    expected = f"sha256:{hashlib.sha256(record_bytes).hexdigest()}"
    if receipt.get("record_sha256") != expected:
        found.append(
            f"{uuid}: receipt attests {receipt.get('record_sha256')!r}, the record beside "
            f"it hashes to {expected!r}"
        )
    return found


def main(argv: Sequence[str]) -> int:
    dataset_dir = Path(argv[0]) if argv else DATA
    if not (dataset_dir / "programs").is_dir():
        print(f"receipt-check: no {dataset_dir}/programs — there is no dataset here to check")
        return 1

    found, state, checked, programs = problems(dataset_dir)

    if state == "predates_receipts":
        # Named, never silent: this is the one passing state in which nothing was compared.
        print(
            f"receipt-check: 0 of {programs} records carry a receipt — this dataset was built "
            "before receipts existed. Nothing was compared; that is not agreement."
        )
        return 0

    if found:
        print("receipt-check: REFUSING — the receipts do not describe the records beside them")
        for line in found:
            print(f"  {line}")
        print(
            "  A dataset holding records from one build and receipts from another is what "
            "this looks like. Rebuild it rather than repairing either side."
        )
        return 1

    print(f"receipt-check: {checked} of {programs} records pair with the receipt beside them")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
