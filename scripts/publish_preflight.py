#!/usr/bin/env python3
"""Refuse to publish a build that was made from the test fixture, or that links a hijacked
address.

`deploy.yml` guards against the fixture and I do not go through `deploy.yml`. The dataset is
gitignored and `aws s3 sync` will publish whatever is in `out/` without asking, so the guard
has to exist on the path actually used, which is a person at a terminal.

The failure this prevents is the one the deploy workflow describes as the reason it is
dispatch-only: publishing the 60-program fixture over 3,266 real ones produces a site with
correct chrome, correct styling, working search and the wrong world -- and nothing about it
looks broken. On 2026-08-04 a local dataset was found replaced by the fixture with no command
run that should have done it; production was unaffected only because the last publish
happened to predate it.

The second guard is #34's. `scripts/provider_link_check.py` reads the dataset; this reads the
*pages*, because the pages are what a reader clicks and because a check that reads the input
to a renderer is not a check on what the renderer emitted. It searches the built program
pages for an anchor pointing at any address the provider-link review rejected -- the three
domains that now serve gambling, lottery and charity sites in place of California colleges,
and the five that redirect into domain marketplaces.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from afterward.sources.link_review import ReviewEntry, load_review, rejected_hosts

# The fixture is 60 programs. Real California data is in the low thousands. Anything under
# this is not a production dataset, whatever else it might be.
MINIMUM_PROGRAMS = 1000


def _anchor_to(host: str) -> re.Pattern[str]:
    """An href pointing at ``host``, however the page spells the scheme and the ``www.``.

    Anchored to the start of the URL rather than searched for anywhere in the file, so a
    hostname appearing in prose -- which is exactly what a page carrying the notice instead
    of the link does -- is not mistaken for a link to it.
    """
    return re.compile(rf'href="https?://(?:www\.)?{re.escape(host)}[/"?#]', re.IGNORECASE)


def rejected_links(out: Path, entries: tuple[ReviewEntry, ...]) -> list[str]:
    """Every built page that links an address a review found is not the provider's."""
    rejected = rejected_hosts(entries)
    patterns = {host: _anchor_to(host) for host in rejected}
    found: list[str] = []
    for page in sorted(out.glob("*/programs/*/index.html")):
        html = page.read_text(encoding="utf-8", errors="replace")
        for host, pattern in patterns.items():
            # Cheap substring first: almost every page fails it and never touches the regex.
            if host in html and pattern.search(html):
                found.append(f"{page.relative_to(out)} links {host} ({rejected[host].status})")
    return found


def main(out_dir: str = "web/out") -> int:
    out = Path(out_dir)
    if not out.is_dir():
        print(f"publish-preflight: no build at {out}")
        return 1

    pages = list((out / "en" / "programs").glob("*/index.html"))
    count = len(pages)
    if count < MINIMUM_PROGRAMS:
        print(
            f"publish-preflight: REFUSING -- {count} program pages built.\n"
            f"  Fewer than {MINIMUM_PROGRAMS} means this is the fixture, not California.\n"
            f"  Restore the dataset (see `make backup-data`) and rebuild before publishing."
        )
        return 1

    sitemap = out / "sitemap.xml"
    if not sitemap.exists():
        print("publish-preflight: REFUSING -- no sitemap in the build")
        return 1
    if "example.invalid" in sitemap.read_text():
        print("publish-preflight: REFUSING -- sitemap carries the placeholder host")
        return 1

    linked = rejected_links(out, load_review())
    if linked:
        print("publish-preflight: REFUSING -- pages link an address the review rejected")
        for line in linked[:10]:
            print(f"  {line}")
        if len(linked) > 10:
            print(f"  ... and {len(linked) - 10} more")
        print("  Rebuild the dataset with `make data` so the review is applied, then rebuild")
        print("  the site. Never publish over this.")
        return 1

    print(
        f"publish-preflight: {count} program pages, sitemap present and addressed, "
        "no page links a rejected address"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "web/out"))
