"""The Makefile says credentials live in `.env.local`. This asserts `data` reads it.

Until 2026-09-12 nothing in the repository loaded that file. `make data` then produced a
complete-looking 3,266-program dataset with zero descriptions, zero Spanish titles and zero
America's Job Centers, because `build` only ever read the process environment. The shape
check caught it -- but only after a full network rebuild had already overwritten the working
dataset.

The recipe is parsed rather than the whole file grepped: a match anywhere in a Makefile can
come from a comment, and this promise is only kept if the loading happens in the recipe that
runs the build.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = ROOT / "Makefile"


def _recipe(target: str) -> str:
    """The recipe lines for one target: tab-indented lines under `target:`."""
    lines = MAKEFILE.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if re.match(rf"^{re.escape(target)}\s*:", line))
    body: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("\t"):
            body.append(line)
        elif line.strip() == "":
            continue
        else:
            break
    return "\n".join(body)


def test_the_data_recipe_loads_env_local() -> None:
    recipe = _recipe("data")
    assert ".env.local" in recipe, (
        "`make data` no longer reads .env.local. The Makefile comment and .env.example both "
        "tell a developer to put CareerOneStop credentials there; if the recipe stops loading "
        "it, a rebuild silently drops every occupation description and job centre."
    )
    assert "set -a" in recipe and ". ./.env.local" in recipe, (
        "`.env.local` is mentioned in the data recipe but not sourced into the build's "
        "environment; naming the file is not reading it."
    )


def test_the_build_still_runs_without_env_local() -> None:
    """CI has no .env.local, and the comment says that build is complete and expected."""
    recipe = _recipe("data")
    assert "if [ -f .env.local ]" in recipe, (
        "loading .env.local must be conditional: CI has no such file, and an unconditional "
        "`.` would fail the build there rather than skipping the optional enrichment."
    )
    assert recipe.count("uv run afterward build") == 2, (
        "both branches of the conditional must run the build, so a missing .env.local skips "
        "the credentials and nothing else."
    )
