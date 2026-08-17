#!/usr/bin/env python3
"""Refuse to publish a dataset that links an address this project has not vouched for.

A provider URL that answers from a different domain is either the school having moved or
somebody else holding the lapsed address. `afterward.sources.link_review` decides which, and
`decide` links only the confirmed ones. This is the gate that says so about an artifact
rather than about the code: it reads the built dataset and refuses two shapes.

1. **A link this build would not have made.** Any program publishing a link whose reason is
   `redirected_offsite` and whose `redirect` is anything other than `same_provider` -- which
   includes `null`, the shape of every dataset built before the review existed. That null is
   the whole reason this gate exists: on 2026-08-15 the live site was serving a dataset in
   which 109 program pages linked off-site redirects, three of them to domains someone else
   now controls, and nothing about the file distinguished them from a reviewed one.

2. **A destination a review found is not the provider.** Any published `href` on a host the
   ledger records as `unrelated` or `for_sale`. Cheap, blunt, and it holds even if the shape
   check is ever weakened by accident.

Run against a dataset directory (`web/public/data` by default) or a built site's copy of it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from afterward.sources.link_review import ReviewEntry, host_of, load_review, rejected_hosts

DATA = Path("web/public/data")


def unvouched(programs: list[dict[str, Any]]) -> list[str]:
    """Every published link that no review or corroboration stands behind."""
    found: list[str] = []
    for program in programs:
        link = program.get("provider_link")
        if not link or not link.get("linked"):
            continue
        if link.get("reason") == "redirected_offsite" and link.get("redirect") != "same_provider":
            resolution = link.get("redirect") or "not resolved at all (built before the review)"
            found.append(
                f"{program.get('provider_name')}: {link.get('href')} — off-site redirect, "
                f"{resolution}"
            )
    return found


def linking_a_reviewed_destination(
    programs: list[dict[str, Any]], hosts: dict[str, ReviewEntry]
) -> list[str]:
    """Every published link that points at a host a review rejected."""
    found: list[str] = []
    for program in programs:
        link = program.get("provider_link")
        if not link or not link.get("linked"):
            continue
        for candidate in (link.get("href"), link.get("url")):
            entry = hosts.get(host_of(candidate) or "")
            if entry is not None:
                found.append(
                    f"{program.get('provider_name')}: {candidate} — reviewed "
                    f"{entry.reviewed_on} as {entry.status} ({entry.evidence})"
                )
                break
    return found


def problems_in(programs: list[dict[str, Any]]) -> list[str]:
    """Both refusals, over records already in hand.

    Separate from :func:`problems` so the same two rules can be applied to a dataset that
    never came off this disk -- see ``scripts/live_check.py``, which asks them of the copy
    the site is actually serving.
    """
    hosts = rejected_hosts(load_review())
    return unvouched(programs) + linking_a_reviewed_destination(programs, hosts)


def problems(dataset_dir: Path) -> list[str]:
    programs = json.loads((dataset_dir / "programs.json").read_text(encoding="utf-8"))["programs"]
    return problems_in(programs)


def read_programs(dataset_dir: Path) -> list[dict[str, Any]]:
    """The dataset's programs, or a refusal if there are none to read.

    An empty list is not a dataset with no bad links in it; it is a file this gate could not
    learn anything from. Both of the checks above are searches, and a search over nothing
    finds nothing, so without this the gate prints "every published provider link is vouched
    for" over a file with no links in it at all -- word for word what it prints when a real
    dataset passes.
    """
    programs = json.loads((dataset_dir / "programs.json").read_text(encoding="utf-8"))["programs"]
    if not isinstance(programs, list) or not programs:
        raise ValueError(
            f"{dataset_dir}/programs.json carries no programs. Both checks here are searches, "
            "and a search over nothing passes without reading anything."
        )
    return programs


def main(argv: list[str]) -> int:
    dataset_dir = Path(argv[0]) if argv else DATA
    if not (dataset_dir / "programs.json").exists():
        print(f"provider-link-check: no dataset at {dataset_dir}/programs.json")
        return 1
    try:
        programs = read_programs(dataset_dir)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"provider-link-check: REFUSING — {exc}")
        return 1
    found = problems_in(programs)
    if found:
        print("provider-link-check: REFUSING — links nothing has vouched for")
        for line in found[:20]:
            print(f"  {line}")
        if len(found) > 20:
            print(f"  ... and {len(found) - 20} more")
        print("  Rebuild with `make data` so the review is applied, or review the redirect")
        print("  in src/afterward/sources/provider-link-review.json.")
        return 1
    print(
        f"provider-link-check: {len(programs)} programs read from {dataset_dir}, "
        "every published provider link vouched for"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
