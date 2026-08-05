#!/usr/bin/env python3
"""Verify a deployed page by what it serves, not by how many objects exist.

Written after a deploy that passed every check and left the search page dead for real
visitors.

Every deploy used `aws s3 sync --size-only`. Next.js names chunks with fixed-length hashes,
so when a page's only change is which chunk it references, the HTML is byte-for-byte the
same *length* — and `--size-only` compares length and nothing else, so it skipped the file.
The assets sync ran with `--delete` and correctly removed chunks the new build no longer
contained, including ones the stale HTML still pointed at. The page loaded, a chunk 404'd,
React never hydrated, and the search page rendered no search box and no results.

The check in place at the time compared the local file count to the S3 object count. Those
matched exactly, every time, because a count cannot see a stale file. It was a check that
could not fail for the failure it existed to catch.

So this asks the CDN for the page a visitor gets, extracts every asset it references, and
requires each to come back 200.
"""

from __future__ import annotations

import re
import sys
import urllib.request

ASSET = re.compile(r"/_next/static/[A-Za-z0-9_./-]+\.(?:js|css)")
PAGES = ("/en/", "/es/", "/en/occupations/", "/en/paying-for-training/")


def fetch(url: str) -> tuple[int, str]:
    # This only ever asks a CDN for a page a visitor would get. Pinning the scheme keeps a
    # stray argv value from turning the check into a local file read that then "passes".
    if not url.startswith("https://"):
        print(f"  refusing non-https URL: {url}")
        return 0, ""
    request = urllib.request.Request(  # noqa: S310 - scheme pinned to https above
        url, headers={"User-Agent": "camino-deploy-check"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - same
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except OSError as exc:
        print(f"  unreachable: {exc}")
        return 0, ""


def main(base: str) -> int:
    failures = 0
    for page in PAGES:
        status, body = fetch(base + page)
        if status != 200:
            print(f"FAIL {page} -> HTTP {status}")
            failures += 1
            continue
        assets = sorted(set(ASSET.findall(body)))
        if not assets:
            print(f"FAIL {page} -> references no assets, which no built page does")
            failures += 1
            continue
        missing = [a for a in assets if fetch(base + a)[0] != 200]
        if missing:
            failures += 1
            print(f"FAIL {page} -> {len(missing)} of {len(assets)} assets missing")
            for asset in missing[:5]:
                print(f"       {asset}")
        else:
            print(f"ok   {page} ({len(assets)} assets all present)")
    if failures:
        print(f"\ndeploy-check: {failures} page(s) serving references to assets that are not there")
        return 1
    print("\ndeploy-check: every asset referenced by every checked page resolves")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "https://camino.chelseakr.com"))
