#!/usr/bin/env python3
"""Refuse to publish a build that was made from the test fixture.

`deploy.yml` guards against this and I do not go through `deploy.yml`. The dataset is
gitignored and `aws s3 sync` will publish whatever is in `out/` without asking, so the guard
has to exist on the path actually used, which is a person at a terminal.

The failure this prevents is the one the deploy workflow describes as the reason it is
dispatch-only: publishing the 60-program fixture over 3,266 real ones produces a site with
correct chrome, correct styling, working search and the wrong world -- and nothing about it
looks broken. On 2026-08-04 a local dataset was found replaced by the fixture with no command
run that should have done it; production was unaffected only because the last publish
happened to predate it.
"""

from __future__ import annotations

import sys
from pathlib import Path

# The fixture is 60 programs. Real California data is in the low thousands. Anything under
# this is not a production dataset, whatever else it might be.
MINIMUM_PROGRAMS = 1000


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

    print(f"publish-preflight: {count} program pages, sitemap present and addressed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "web/out"))
