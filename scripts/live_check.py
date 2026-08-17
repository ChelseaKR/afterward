#!/usr/bin/env python3
"""Ask the live site whether it is serving a dataset this repository would still publish.

Every gate that can refuse a hijacked provider link, or a dataset older than the code that
describes it, runs on the way *out*: `make dataset-verify` before packaging, three guards in
`.github/workflows/deploy.yml` before uploading, `scripts/publish_preflight.py` before a hand
sync. All of them are excellent and none of them runs unless somebody deploys.

That is the gap this closes, and it is not hypothetical. The provider-link review landed on
2026-08-15 and named `giligiacollege.com` as an address the college no longer holds -- it
answers 302 to `seinquote.com`, which serves an Indonesian slot-gambling page. The deploy
workflow has refused that dataset ever since. The site has gone on serving it, because the
last deploy predates the review and no deploy has run since. Confirmed on 2026-08-17 by
fetching `/data/programs.json` from the live host: four program pages under Giligia College
still publish that address as "Provider's website", and so do the pages of seven other
providers whose filed addresses are now marketplaces or somebody else's site.

Nothing was broken. Nothing failed. Nothing asked. A review that lands in the repository has
no effect on what a reader clicks until someone chooses to publish, and until then the only
record of the difference is a commit nobody is watching.

So this asks, from outside: it reads the dataset the site actually serves and runs the same
two gates over it that the deploy path runs over the dataset it is about to upload -- the
same functions, imported, not a second implementation that could form its own opinion.

Network-bound, so deliberately not part of `make verify`, exactly like `make link-check` and
`make deploy-check`. It belongs to a schedule and to a person, and its failure means the same
thing every time: rebuild with `make data`, publish with `make dataset-publish`, deploy.

Usage: python3 scripts/live_check.py [https://site]
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:  # pragma: no cover - import plumbing
    sys.path.insert(0, str(SCRIPTS))

from dataset_shape_check import problems as shape_problems  # noqa: E402
from provider_link_check import problems_in as link_problems  # noqa: E402

SITE = "https://afterward.chelseakr.com"
TIMEOUT = 60
"""programs.json is roughly eleven megabytes, so this is not the thirty seconds a page gets."""


def fetch_json(url: str) -> Any:
    """One document from the live site, or a raised error naming why not.

    HTTPS is pinned rather than assumed for the reason `scripts/deploy_check.py` pins it: a
    stray argument must not be able to turn a check on what the world can see into a read of
    a file on this disk, which would then pass.
    """
    if not url.startswith("https://"):
        raise ValueError(f"refusing a non-https URL: {url}")
    request = urllib.request.Request(  # noqa: S310 - scheme pinned to https above
        url, headers={"User-Agent": "afterward-live-check"}
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310 - same
            if response.status != 200:
                raise ValueError(f"{url} answered HTTP {response.status}")
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ValueError(f"{url} answered HTTP {exc.code}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{url} could not be read — {exc}") from exc


def unmeasured(coverage: Any, programs: Any) -> list[str]:
    """Every reason this run learned nothing, stated as a refusal rather than as a pass.

    A check made of searches passes whenever there is nothing to search, and this one runs
    unattended against a document fetched over a network: an edge serving an empty body, a
    redirect to a login page, a bucket half way through a sync. Each of those hands the two
    gates below an empty list, which they clear without objection.

    The count in `coverage.json` is what makes that answerable. The site publishes both
    documents; if they disagree, or if either is the wrong shape, this run cannot say
    anything about the site and must not report that it did.
    """
    if not isinstance(coverage, dict):
        return ["coverage.json is not an object"]
    if not isinstance(programs, dict) or not isinstance(programs.get("programs"), list):
        return ["programs.json carries no 'programs' list"]

    records = programs["programs"]
    claimed = coverage.get("total_programs")
    found: list[str] = []
    if not records:
        found.append("the site is serving a programs.json with no programs in it")
    if not isinstance(claimed, int) or claimed <= 0:
        found.append(f"coverage.json claims total_programs={claimed!r}")
    elif len(records) != claimed:
        found.append(
            f"the site serves {len(records)} programs and claims {claimed}; the two "
            "documents describe different datasets"
        )
    return found


def report(base: str) -> int:
    base = base.rstrip("/")
    try:
        coverage = fetch_json(f"{base}/data/coverage.json")
        programs = fetch_json(f"{base}/data/programs.json")
    except ValueError as exc:
        print(f"live-check: REFUSING — {exc}")
        print("  Unreachable is not the same as clean. This run established nothing.")
        return 1

    blind = unmeasured(coverage, programs)
    if blind:
        print("live-check: REFUSING — nothing here could be measured")
        for line in blind:
            print(f"  {line}")
        return 1

    records = programs["programs"]
    snapshot = coverage.get("snapshot_date", "unknown")
    stale = shape_problems(records)
    unvouched = link_problems(records)
    if not stale and not unvouched:
        print(
            f"live-check: {base} serves snapshot {snapshot}, {len(records)} programs, "
            "and every gate on the deploy path would accept it again today"
        )
        return 0

    print(f"live-check: REFUSING — {base} is serving snapshot {snapshot}, which this")
    print("  repository would no longer publish. The deploy path already refuses it; the")
    print("  site has it anyway, because nothing has deployed since the code moved on.")
    for line in stale:
        print(f"  {line}")
    for line in unvouched[:20]:
        print(f"  {line}")
    if len(unvouched) > 20:
        print(f"  ... and {len(unvouched) - 20} more published links nothing vouches for")
    print("  Rebuild with `make data`, publish with `make dataset-publish`, then deploy.")
    return 1


def main(argv: list[str]) -> int:
    return report(argv[0] if argv else SITE)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
