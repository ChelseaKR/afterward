"""The type checker's scope is a claim about the repository, so it is asserted here.

`pyproject.toml` read ``files = ["src"]`` until 2026-08-28 and `make typecheck` ran
``mypy src``, which meant two things at once. `scripts/` -- the eight gate scripts that
decide whether a dataset may be backed up, packaged or published -- and `tests/` -- 1,240
cases -- were never type-checked at all, while the README's Code Quality row said
"mypy --strict" without saying which third of the repository it meant. And the path on the
command line silently overrode whatever the config said, so widening the config alone would
have changed nothing: the first attempt at this fix reported "no issues found in 30 source
files", the same 30 as before.

These are cheap string assertions rather than a mypy run, because the point is not whether
the code type-checks -- `make typecheck` answers that -- but whether it is being asked to.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Every Python surface in this repository. A new one belongs here and in the config.
SURFACES = ("src", "scripts", "tests")


def _makefile_recipe(target: str) -> list[str]:
    """The command lines of one Makefile target, tabs and comments stripped."""
    lines = (REPO_ROOT / "Makefile").read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"{target}:"))
    recipe = []
    for line in lines[start + 1 :]:
        if not line.startswith("\t"):
            break
        stripped = line.lstrip("\t").strip()
        if stripped and not stripped.startswith("#"):
            recipe.append(stripped)
    return recipe


class TestTypedPackageMarker:
    def test_the_package_declares_its_types(self) -> None:
        """What the built wheel tells anything that installs it.

        `afterward` is annotated throughout and checked under ``strict``, and shipped none of
        that: without this marker an installing consumer's own type checker treats every
        import from it as ``Any``. It matters here too, in the narrow case of running mypy
        over ``scripts/`` or ``tests/`` alone, where the package resolves from site-packages
        rather than from ``src/`` and 60 imports come back untyped.
        """
        assert (REPO_ROOT / "src" / "afterward" / "py.typed").is_file()


class TestMypyScope:
    def test_every_python_surface_is_in_the_configured_scope(self) -> None:
        config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        assert config["tool"]["mypy"]["files"] == list(SURFACES)

    def test_the_configured_scope_is_strict(self) -> None:
        config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        assert config["tool"]["mypy"]["strict"] is True

    def test_only_tests_are_relaxed_and_only_in_two_named_ways(self) -> None:
        """A relaxation for `src/` or `scripts/` would be a hole in the gate, not a
        convenience. The two that exist apply to ad-hoc dict fixtures in tests and nothing
        else; the errors that matter in a test all stay on."""
        config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        overrides = config["tool"]["mypy"].get("overrides", [])
        assert [o["module"] for o in overrides] == ["tests.*"]
        assert set(overrides[0]) - {"module"} == {"disallow_any_generics", "warn_return_any"}

    def test_the_make_target_passes_no_path(self) -> None:
        """A path argument overrides `files` and is how the scope stayed at `src` after the
        config was widened to include everything."""
        recipe = _makefile_recipe("typecheck")
        assert recipe == ["uv run mypy"], recipe

    def test_the_pre_commit_hook_passes_no_path_either(self) -> None:
        """Same trap, second door: the hook ran `mypy src` and reported a pass that meant
        less than it looked like."""
        config = (REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
        hook = re.search(r"- id: mypy\n(?P<body>(?:\s{8}.*\n)+)", config)
        assert hook is not None, "no local mypy hook in .pre-commit-config.yaml"
        assert re.search(r"^\s+args:", hook.group("body"), re.M) is None, hook.group("body")
