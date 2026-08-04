"""Tests for the clean-room guard.

The guard is a compliance control, so its false-negative behaviour matters: a pattern that
silently stops matching would let the constraint lapse without anyone noticing.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "provenance_check", Path(__file__).resolve().parent.parent / "scripts" / "provenance_check.py"
)
assert SPEC and SPEC.loader
provenance_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(provenance_check)


def _matches(text: str) -> bool:
    return any(pattern.search(text) for pattern in provenance_check.PATTERNS)


class TestPatterns:
    def test_catches_excluded_references(self) -> None:
        for text in (
            "see MCNJ for reference",
            "ported from My Career NJ",
            "https://mycareer.nj.gov/navigator",
            "cloned newjersey/d4ad",
            "based on the D4AD schema",
            "adapted from https://nj.gov/labor",
            "modeled on the New Jersey approach",
        ):
            assert _matches(text), f"should have matched: {text!r}"

    def test_does_not_match_ordinary_text(self) -> None:
        for text in (
            "California training programs",
            "the project name is camino",
            "adjacency scoring for occupations",
            "New Mexico and New York are unrelated",
            "injects a dependency",
        ):
            assert not _matches(text), f"should not have matched: {text!r}"


class TestScan:
    def test_repository_is_clean(self) -> None:
        """The live repository must always pass its own guard."""
        assert provenance_check.scan() == []

    def test_vendor_directories_are_excluded(self) -> None:
        """Third-party code contains unrelated matches (e.g. SPDX licence names)."""
        assert ".venv" in provenance_check.EXCLUDED_DIRS
        assert "node_modules" in provenance_check.EXCLUDED_DIRS
