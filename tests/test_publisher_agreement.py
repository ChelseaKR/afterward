"""Two publishers write to `s3://afterward.chelseakr.com`. This asserts they agree.

`.github/workflows/deploy.yml` is the one that runs, and `make publish` is the one a person
runs by hand -- the Makefile's own comment says why it exists and records the three distinct
ways it was got wrong when it was assembled from scratch. Both upload the same `web/out` to
the same bucket, and each states the `Cache-Control` it writes in its own copy of the sync
commands.

Two copies of a value is how the values drift, and they had. Until this file, the hand
publisher wrote `max-age=300` on every page while the workflow wrote `max-age=0`, so the same
page carried a different caching instruction depending on who published it. Nothing was
serving it wrong today: the distribution's response-headers policy overrides `Cache-Control`
at the edge, which is also why `deploy.yml`'s GUARD 4 reads the object metadata rather than an
HTTPS response, and why no live check could ever have found this. Remove that policy and the
divergence becomes visible immediately.

`deploy.yml` carries a guard for this (GUARD 4) and `make publish` does not, which is the
shape worth naming: two publishers, one address, one of them gated. The guard also only
asserts `must-revalidate`, which both spellings satisfy, so it could not have caught it
either. This file is the part that compares the two publishers to each other.

Both sides are parsed from the commands that actually run, not grepped out of the whole file:
a `--cache-control` in a comment or in prose is not a thing any publisher does, and a check
that counts those passes on text nobody executes.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = ROOT / "Makefile"
WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"

#: The class of object each sync pass writes. Both publishers split the bucket the same way
#: and for the same reason (infra/README.md): content-hashed files under `_next/static/` never
#: change under a given name and are immutable, everything else sits at a stable URL with the
#: dataset changing underneath it and must revalidate.
ASSETS = "assets"
PAGES = "pages"

_CACHE_CONTROL = re.compile(r'--cache-control "([^"]+)"')


def _strip_comments(text: str) -> str:
    """Drop whole-line comments from either file.

    The Makefile records the pass ordering in a long comment block that names flags, and the
    workflow does the same. Neither is executed, and a sweep that reads them is measuring
    prose.
    """
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def _join_continuations(text: str) -> str:
    return text.replace("\\\n", " ")


def _recipe(target: str) -> str:
    """The recipe lines for one target: tab-indented lines under `target:`."""
    lines = MAKEFILE.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    collecting = False
    for line in lines:
        if re.match(rf"^{re.escape(target)}\s*:", line):
            collecting = True
            continue
        if collecting:
            if line.startswith("\t") or line.strip() == "":
                out.append(line)
            else:
                break
    return "\n".join(out)


def _declarations(text: str) -> dict[str, set[str]]:
    """Every `aws s3 sync` in `text`, as {object class: the Cache-Control values it writes}.

    A pass whose destination is the hashed-asset prefix writes assets; anything else writes
    pages. A sync with no `--cache-control` states nothing and is not a declaration.
    """
    found: dict[str, set[str]] = {ASSETS: set(), PAGES: set()}
    for command in re.findall(r"aws s3 sync [^\n]*", _join_continuations(_strip_comments(text))):
        cache = _CACHE_CONTROL.search(command)
        if not cache:
            continue
        destination = re.search(r'"s3://[^"]*"', command)
        target = destination.group(0) if destination else ""
        found[ASSETS if "_next/static" in target else PAGES].add(cache.group(1))
    return found


def _workflow_declarations() -> dict[str, set[str]]:
    return _declarations(WORKFLOW.read_text(encoding="utf-8"))


def _makefile_declarations() -> dict[str, set[str]]:
    return _declarations(_recipe("publish"))


def test_both_publishers_were_actually_read() -> None:
    """A sweep that parsed nothing reports no disagreement and reads exactly like a pass.

    This is the assertion that stops the rest of the file being vacuous, so it comes first and
    names real counts rather than "not empty".
    """
    workflow = _workflow_declarations()
    makefile = _makefile_declarations()

    assert len(workflow[ASSETS]) >= 1 and len(workflow[PAGES]) >= 1, workflow
    assert len(makefile[ASSETS]) >= 1 and len(makefile[PAGES]) >= 1, makefile


def test_each_publisher_is_internally_consistent() -> None:
    """One publisher, several passes, one value per class.

    `deploy.yml` writes assets in three places (two passes plus the bounded re-sync GUARD 3
    performs) and pages in two. If those ever disagreed with each other, the object's headers
    would depend on which pass last touched it.
    """
    for name, declared in (
        ("deploy.yml", _workflow_declarations()),
        ("Makefile", _makefile_declarations()),
    ):
        assert len(declared[ASSETS]) == 1, (
            f"{name} writes assets {len(declared[ASSETS])} ways: {declared[ASSETS]}"
        )
        assert len(declared[PAGES]) == 1, (
            f"{name} writes pages {len(declared[PAGES])} ways: {declared[PAGES]}"
        )


def test_the_two_publishers_write_the_same_cache_control() -> None:
    """The regression this file was written for.

    A page published by hand and the same page published by CI must carry the same caching
    instruction, because they are the same page at the same address.
    """
    workflow = _workflow_declarations()
    makefile = _makefile_declarations()

    assert workflow[PAGES] == makefile[PAGES], (
        f"deploy.yml publishes pages as {workflow[PAGES]} and `make publish` as "
        f"{makefile[PAGES]}: the same page carries a different Cache-Control depending on who "
        "published it"
    )
    assert workflow[ASSETS] == makefile[ASSETS], (
        f"deploy.yml publishes assets as {workflow[ASSETS]} and `make publish` as "
        f"{makefile[ASSETS]}"
    )


def test_the_two_classes_are_not_published_the_same_way() -> None:
    """Assets immutable, pages revalidating. Collapsing the split is the failure the split

    exists to prevent: a content-hashed chunk that revalidates costs a request per load, and a
    page that does not revalidate serves a superseded dataset from a browser cache under a URL
    that never changes.
    """
    workflow = _workflow_declarations()

    (assets,) = workflow[ASSETS]
    (pages,) = workflow[PAGES]

    assert "immutable" in assets, assets
    assert "must-revalidate" in pages, pages
    assert assets != pages
