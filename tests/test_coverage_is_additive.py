"""Adding ``projection_source`` to ``coverage.json`` changes nothing a consumer already reads.

The owner accepted the new key on 2026-09-18 on one condition: it is additive, so every
existing consumer of the published ``coverage.json`` -- the site, ``dataset-verify``,
``verify_live_site.py``, the ``afterward.ask`` service, anybody who downloaded a release --
is unaffected. This file is where that condition is held rather than asserted in prose.

The baseline under ``tests/fixtures/coverage-before-projection-source/`` was produced by the
code on ``main`` immediately before the key existed (``d2e5d1e``), from the committed
California fixture:

* ``coverage.json`` is what ``build_offline`` emitted, plus the trailing newline the
  repository's end-of-file hook adds; the comparison is of parsed values.
* ``area_placement.json`` is ``area_placement_coverage`` over the programs that build
  emitted. The offline build does not publish that block (the fixture predates it), and a
  live build does, so it is pinned at the function that writes it.

Every field in the baseline must come back with the same value, and nothing may disappear.
New keys are allowed, because that is what additive means; the two this change adds are
asserted by name. If a later change deliberately alters a field consumers already read, that
is a consumer-visible change: regenerate the baseline in that change, from its own parent,
and say so in its CHANGELOG entry.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from afterward.build import (
    PROJECTION_SOURCE_KEY,
    UNPLACED_SOURCE_PUBLISHES_NO_AREAS,
    area_placement_coverage,
    build_offline,
)

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = ROOT / "fixtures" / "data"
BASELINE = ROOT / "tests" / "fixtures" / "coverage-before-projection-source"


def _leaves(value: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    """Every leaf of a JSON document with its dotted path; lists are compared whole."""
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _leaves(child, f"{path}.{key}" if path else key)
    else:
        yield path, value


def _changed_or_missing(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    after_leaves = dict(_leaves(after))
    problems = []
    for path, value in _leaves(before):
        if path not in after_leaves:
            problems.append(f"{path}: was {value!r}, now absent")
        elif after_leaves[path] != value:
            problems.append(f"{path}: was {value!r}, now {after_leaves[path]!r}")
    return problems


def _load(path: Path) -> dict[str, Any]:
    loaded: Any = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), f"{path} is not a JSON object"
    return loaded


class TestTheCoverageDocumentIsOnlyAddedTo:
    def test_the_baseline_is_the_document_it_claims_to_be(self) -> None:
        # Guards the guard: an empty or wrong baseline would make every comparison pass.
        before = _load(BASELINE / "coverage.json")
        assert before["is_fixture"] is True
        assert before["total_programs"] == 60
        assert PROJECTION_SOURCE_KEY not in before
        assert len(list(_leaves(before))) > 50

    def test_every_field_published_before_the_key_is_unchanged(self, tmp_path: Path) -> None:
        build_offline(FIXTURE_DIR, output_dir=tmp_path)
        after = _load(tmp_path / "coverage.json")
        problems = _changed_or_missing(_load(BASELINE / "coverage.json"), after)
        assert not problems, "coverage.json changed a field consumers already read: " + (
            "; ".join(problems)
        )

    def test_the_only_top_level_addition_is_the_projection_source(self, tmp_path: Path) -> None:
        build_offline(FIXTURE_DIR, output_dir=tmp_path)
        after = _load(tmp_path / "coverage.json")
        added = set(after) - set(_load(BASELINE / "coverage.json"))
        assert added == {PROJECTION_SOURCE_KEY}
        declared = after[PROJECTION_SOURCE_KEY]
        assert declared["state"] == "CA"
        assert declared["measures_this_source_does_not_publish"] == []

    def test_every_other_emitted_file_is_the_same_bytes_twice(self, tmp_path: Path) -> None:
        # The key must not leak into any other file: two builds agree everywhere, and the
        # key appears in coverage.json alone.
        build_offline(FIXTURE_DIR, output_dir=tmp_path / "a")
        build_offline(FIXTURE_DIR, output_dir=tmp_path / "b")
        files = sorted(p.relative_to(tmp_path / "a") for p in (tmp_path / "a").rglob("*.json"))
        assert len(files) > 100
        for relative in files:
            first = (tmp_path / "a" / relative).read_bytes()
            assert first == (tmp_path / "b" / relative).read_bytes(), relative
            if relative.as_posix() != "coverage.json":
                assert PROJECTION_SOURCE_KEY.encode() not in first, relative


class TestTheAreaPlacementBlockIsOnlyAddedTo:
    def test_every_count_published_before_the_new_reason_is_unchanged(self, tmp_path: Path) -> None:
        build_offline(FIXTURE_DIR, output_dir=tmp_path)
        programs = _load(tmp_path / "programs.json")["programs"]
        after = area_placement_coverage(programs)
        before = _load(BASELINE / "area_placement.json")
        assert before["unplaced"] > 0, "the baseline places everything and so tests nothing"
        problems = _changed_or_missing(before, after)
        assert not problems, "area_placement changed a count consumers already read: " + (
            "; ".join(problems)
        )

        added = set(after["unplaced_by_reason"]) - set(before["unplaced_by_reason"])
        assert added == {UNPLACED_SOURCE_PUBLISHES_NO_AREAS}
        # California's source publishes areas, so a California build never reaches it.
        assert after["unplaced_by_reason"][UNPLACED_SOURCE_PUBLISHES_NO_AREAS] == 0
