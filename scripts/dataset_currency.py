#!/usr/bin/env python3
"""Is the dataset a visitor is served the newest dataset this project has published?

ADR 0001 declares the semver pipeline N/A here because nothing consumes an afterward
*version*. What this project releases is the **dataset**: `make dataset-publish` cuts
`dataset-<snapshot>` with a tarball and a sha256 beside it, and `deploy.yml` -- which is
dispatch-only, deliberately -- publishes exactly one of those to the site.

Three sentinels already watch this repository and none of them asks this question.

* `live-integrity.yml` asks whether the site serves the dataset it *names*. A site serving
  a release from six weeks ago is perfectly self-consistent and answers that correctly
  every single day.
* `deploy-staleness.yml` asks how far behind `main` the deployed *commit* is. A data
  refresh moves no commit, which is the ordinary case, so it stays green through exactly
  this failure.
* `release-integrity.yml` asks whether every published release is intact and correctly
  tagged. It checks artifacts, not currency.

So the failure mode is: run `make data && make dataset-publish` on the workstation, get
distracted, never dispatch Deploy. The release exists, the site serves the previous one,
every badge is green, and the only way to find out is to notice by eye. That matters more
than the commit clock does -- an undeployed commit leaves a reader with an older interface,
while an undeployed dataset leaves them reading withdrawn programs, stale costs and outcome
figures the state has since revised, under a snapshot date that is honestly reported and
simply old.

This is a join rather than new machinery: `release_integrity.list_releases` already has the
published set and `verify_live_site.live_coverage` already has what the site says it serves.

THREE STATES, AND THE THIRD IS NOT A NUMBER

* **current** -- the live snapshot is the newest published dataset release. Exit 0.
* **behind** -- a newer release exists and has not been deployed. Exit 0, and the workflow
  opens an issue. `deploy_staleness.py`'s header gives the reason and it holds here: a
  scheduled job that is red for weeks is a job that gets ignored, and the issue is the
  signal.
* **unmeasurable** -- exit 1, with the reason named and no number reported. Every way this
  comparison can fail to mean anything lands here:

  - no published `dataset-*` release exists at all, or the listing failed. "0 releases, 0
    days behind" is this portfolio's dominant defect wearing a sentinel's clothes;
  - the site is unreachable, its `coverage.json` is unreadable, or its snapshot date parses
    as nothing (`verify_live_site.live_coverage` refuses all three on its own);
  - **the live snapshot is NEWER than every published release.** That is not "current" and
    it is not "ahead": it means the site is serving something that was never released,
    which is a different and worse finding than being behind, and it must not be rounded
    down into a reassuring word.

WHAT IS DELIBERATELY *NOT* A REFUSAL

A live snapshot that is older than the newest release but matches no published release tag
-- the release it came from having since been deleted -- is reported as `behind` with
`live_release_missing` set, not refused. Both dates are real and the arithmetic between
them is sound; what is missing is a tag, and `live-integrity.yml` is the sentinel that
fails on that. Refusing here would suppress a true "you have not deployed" finding on the
strength of a second, separate one.

Usage:
    python3 scripts/dataset_currency.py [--repo OWNER/NAME] [--url URL]
                                        [--max-age-days N] [--json]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# `scripts/` is not a package, and these two are the modules this one exists to join. When
# invoked as `python3 scripts/dataset_currency.py` the interpreter puts this directory on
# `sys.path` first, so a plain import resolves; `tests/test_dataset_currency.py` puts it
# there explicitly for the same reason. Importing rather than re-implementing is the point:
# a second copy of "which releases are published" would be free to drift from the one
# `release-integrity.yml` enforces.
import release_integrity
import verify_live_site

DEFAULT_REPO = release_integrity.DEFAULT_REPO
DEFAULT_MAX_AGE_DAYS = 7
"""How long a published-but-undeployed dataset may wait before this reports it.

Shorter than `deploy_staleness.py`'s fourteen, and for a different reason rather than a
stricter mood. A commit reaching `main` is not a decision to deploy -- most are not. Cutting
a dataset release *is*: `make dataset-publish` is a deliberate act whose only purpose is the
deploy that follows it, so a week of silence afterwards is already an anomaly.
"""

TAG_PATTERN = release_integrity.TAG_PATTERN
"""One definition of "one of ours", shared with the release checker."""

REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class CurrencyUnknown(Exception):
    """The comparison cannot be made, so no number about it may be reported."""


@dataclass(frozen=True)
class PublishedRelease:
    """One published dataset release: the snapshot it carries and when it went out."""

    tag: str
    snapshot_date: dt.date
    published_at: dt.datetime
    url: str


@dataclass(frozen=True)
class Currency:
    """What the site serves against what has been published."""

    live_date: dt.date
    newest: PublishedRelease
    waiting: tuple[PublishedRelease, ...]
    live_release_missing: bool
    now: dt.datetime
    max_age_days: int

    @property
    def data_age_days(self) -> int:
        """How much older the served snapshot is than the newest published one, in days.

        A property of the *data* a reader gets, not of the operator's calendar: it is the
        distance between two snapshot dates and it does not move when nobody is looking.
        """
        return (self.newest.snapshot_date - self.live_date).days

    @property
    def undeployed_for_days(self) -> float | None:
        """How long the oldest undeployed release has been published.

        `None` when nothing is waiting, which is not the same as zero and must not be
        rendered as it. This is the operator's clock, and it is what the threshold reads.
        """
        if not self.waiting:
            return None
        oldest = min(self.waiting, key=lambda release: release.published_at)
        return (self.now - oldest.published_at).total_seconds() / 86400.0

    @property
    def verdict(self) -> str:
        waiting = self.undeployed_for_days
        if waiting is None:
            return "current"
        return "behind" if waiting >= self.max_age_days else "current"


def _parse_timestamp(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.UTC)


def published_releases(entries: Iterable[Mapping[str, Any]]) -> list[PublishedRelease]:
    """Every published `dataset-<date>` release, newest snapshot first.

    Drafts and prereleases are excluded because they are not published, and a tag that does
    not match `TAG_PATTERN` is not one of ours. A release whose timestamp will not parse is
    dropped rather than defaulted -- `release_integrity.py` is the sentinel that reports a
    malformed release, and inventing a date here would put a fabricated day into an
    arithmetic this file exists to make trustworthy.
    """
    found: list[PublishedRelease] = []
    for entry in entries:
        if entry.get("draft") or entry.get("prerelease"):
            continue
        tag = str(entry.get("tag_name", ""))
        matched = TAG_PATTERN.match(tag)
        if matched is None:
            continue
        stamp = entry.get("published_at") or entry.get("created_at")
        if not isinstance(stamp, str) or not stamp:
            continue
        try:
            snapshot = dt.date.fromisoformat(matched.group(1))
            published = _parse_timestamp(stamp)
        except ValueError:
            continue
        found.append(
            PublishedRelease(
                tag=tag,
                snapshot_date=snapshot,
                published_at=published,
                url=str(entry.get("html_url", "")),
            )
        )
    return sorted(found, key=lambda release: release.snapshot_date, reverse=True)


def compare(
    live_date: dt.date,
    releases: Sequence[PublishedRelease],
    *,
    now: dt.datetime,
    max_age_days: int,
) -> Currency:
    """Join the two facts, refusing every arrangement of them that means nothing."""
    if not releases:
        raise CurrencyUnknown(
            "no published dataset release was found. That is not 'up to date': it means "
            "nothing has ever been released under a `dataset-<date>` tag, or the listing "
            "did not reach the ones that were."
        )
    newest = releases[0]
    if live_date > newest.snapshot_date:
        raise CurrencyUnknown(
            f"the live site serves snapshot {live_date}, which is newer than every "
            f"published release (the newest is {newest.tag}). The site is serving a "
            "dataset that was never released, so 'how far behind' is not the question to "
            "be answering about it."
        )
    waiting = tuple(r for r in releases if r.snapshot_date > live_date)
    return Currency(
        live_date=live_date,
        newest=newest,
        waiting=waiting,
        live_release_missing=not any(r.snapshot_date == live_date for r in releases),
        now=now,
        max_age_days=max_age_days,
    )


def render(currency: Currency) -> str:
    """The human report. Every number in it is one the comparison actually produced."""
    lines = [
        f"Live snapshot:            {currency.live_date}",
        f"Newest published release: {currency.newest.tag} "
        f"(published {currency.newest.published_at:%Y-%m-%d})",
    ]
    waiting = currency.undeployed_for_days
    if waiting is None:
        lines.append("The site is serving the newest dataset this project has published.")
    else:
        lines.append(
            f"Published datasets not deployed:  {len(currency.waiting)} "
            f"({', '.join(r.tag for r in reversed(currency.waiting))})"
        )
        lines.append(
            f"Oldest of them has waited:        {waiting:.1f} days "
            f"(threshold {currency.max_age_days})"
        )
        lines.append(
            f"The served data is older by:      {currency.data_age_days} days of snapshot date"
        )
    if currency.live_release_missing:
        lines.append(
            f"Caveat: no published release carries snapshot {currency.live_date}, so the "
            "release the site was deployed from is no longer listed. The comparison above "
            "is between two real dates and stands; live-integrity.yml is the check that "
            "fails on the missing tag."
        )
    lines.append(f"Verdict: {currency.verdict}")
    return "\n".join(lines)


def as_json(currency: Currency) -> dict[str, Any]:
    waiting = currency.undeployed_for_days
    return {
        "verdict": currency.verdict,
        "live_snapshot": currency.live_date.isoformat(),
        "newest_release_tag": currency.newest.tag,
        "newest_release_snapshot": currency.newest.snapshot_date.isoformat(),
        "newest_release_published_at": currency.newest.published_at.isoformat(),
        "newest_release_url": currency.newest.url,
        "undeployed_releases": [r.tag for r in reversed(currency.waiting)],
        "undeployed_for_days": None if waiting is None else round(waiting, 1),
        "data_age_days": currency.data_age_days,
        "live_release_missing": currency.live_release_missing,
        "max_age_days": currency.max_age_days,
    }


def live_snapshot_date(url: str, *, timeout_seconds: float) -> dt.date:
    """The snapshot date the live site names, or a refusal.

    `verify_live_site.live_coverage` already refuses a non-200, a body that is not JSON, a
    fixture dataset, a malformed or future snapshot date and a program count below the
    floor. Every one of those is a reason this comparison cannot be made, so they are
    re-raised as such rather than caught and softened.
    """
    origin = verify_live_site.Origin(url, timeout_seconds=timeout_seconds)
    try:
        nonce = f"dataset-currency-{dt.datetime.now(dt.UTC):%Y%m%d%H%M%S}"
        verify_live_site.prove_the_origin_discriminates(origin, nonce)
        snapshot, _ = verify_live_site.live_coverage(origin, nonce)
    except verify_live_site.LiveSiteError as exc:
        raise CurrencyUnknown(f"the live site could not be read: {exc}") from exc
    finally:
        origin.close()
    return dt.date.fromisoformat(snapshot)


def fetch_releases(repo: str) -> list[dict[str, Any]]:
    try:
        return release_integrity.list_releases(repo)
    except RuntimeError as exc:
        raise CurrencyUnknown(f"the release list could not be read: {exc}") from exc


def _write_github_output(currency: Currency | None, error: str | None) -> None:
    destination = os.environ.get("GITHUB_OUTPUT")
    if not destination:
        return
    payload = (
        {"verdict": "unknown", "detail": error or "unknown"}
        if currency is None
        else {**as_json(currency), "detail": render(currency)}
    )
    with open(destination, "a", encoding="utf-8") as handle:
        handle.write(f"verdict={payload['verdict']}\n")
        handle.write("report<<DATASET_CURRENCY_EOF\n")
        handle.write(f"{payload.get('detail', '')}\n")
        handle.write("DATASET_CURRENCY_EOF\n")
        handle.write(f"json={json.dumps(payload)}\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--url", default=verify_live_site.SITE_URL)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS)
    parser.add_argument("--json", action="store_true", help="emit the machine-readable report")
    arguments = parser.parse_args(argv)

    if REPO_PATTERN.fullmatch(arguments.repo) is None:
        print(f"::error::--repo {arguments.repo!r} is not an owner/name pair.", file=sys.stderr)
        return 1
    if arguments.max_age_days < 1:
        print("::error::--max-age-days must be at least 1.", file=sys.stderr)
        return 1

    try:
        live_date = live_snapshot_date(arguments.url, timeout_seconds=arguments.timeout_seconds)
        currency = compare(
            live_date,
            published_releases(fetch_releases(arguments.repo)),
            now=dt.datetime.now(dt.UTC),
            max_age_days=arguments.max_age_days,
        )
    except CurrencyUnknown as unknown:
        print(f"::error::Dataset currency is unknown: {unknown}", file=sys.stderr)
        _write_github_output(None, str(unknown))
        return 1

    print(json.dumps(as_json(currency), indent=2) if arguments.json else render(currency))
    _write_github_output(currency, None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
