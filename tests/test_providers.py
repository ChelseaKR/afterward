"""One snapshot, one provider count.

`dataset-2026-09-12` published three: 584 on the About page, 581 on the provider index, and
583 as the duplicate-cohort pass's key. All three counted the same 3,266 records; the first
counted distinct filed strings, and three of California's providers file under two spellings
each. #155.

The identity rule is now written once per language -- `afterward.providers.provider_slug`
here, `slugify` in `web/lib/providers.ts`, which mints the URLs -- because neither side can
call the other. `fixtures/provider-identity.json` is what stops that from being two rules:
this suite and `web/lib/providers.test.ts` both read it and assert every row, so a change to
one implementation that the table does not sanction turns the other language's suite red.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from afterward.providers import SLUG_MAX_LENGTH, count_providers, provider_slug

IDENTITY_TABLE = Path(__file__).resolve().parent.parent / "fixtures" / "provider-identity.json"


def _table() -> dict:
    return json.loads(IDENTITY_TABLE.read_text(encoding="utf-8"))


class TestTheSharedCaseTable:
    """The rows both languages have to agree on."""

    def test_every_case_slugs_as_the_table_says(self) -> None:
        cases = _table()["cases"]
        # A table that emptied itself would pass every assertion below it, so the table's own
        # size is asserted before anything is read from it.
        assert len(cases) >= 15
        wrong = [
            (case["name"], provider_slug(case["name"]) or "", case["slug"])
            for case in cases
            if (provider_slug(case["name"]) or "") != case["slug"]
        ]
        assert wrong == []

    def test_every_pair_the_table_calls_a_collision_is_one(self) -> None:
        pairs = _table()["collisions"]
        assert len(pairs) >= 4
        for first, second in pairs:
            slug = provider_slug(first)
            assert slug is not None
            assert slug == provider_slug(second)
            # The point of the pair is that the strings differ. A pair of identical strings
            # would collide trivially and prove nothing about the rule.
            assert first != second

    def test_the_table_names_the_filings_that_made_155(self) -> None:
        """The three real pairs, by name, so a later edit cannot quietly drop the evidence."""
        names = {case["name"] for case in _table()["cases"]}
        assert {"PROCAREER ACADEMY", "Procareer Academy"} <= names
        assert {"DIALYSIS EDUCATION SERVICES LLC", "Dialysis Education Services, LLC"} <= names
        assert {
            "Virtual Design & Construction Institute",
            "Virtual Design and Construction Institute",
        } <= names


class TestProviderSlug:
    def test_a_name_with_no_letters_or_digits_has_no_identity(self) -> None:
        # None rather than "", and excluded from counts rather than pooled: two anonymous
        # filers under one blank key would be published as one provider.
        assert provider_slug("!!!") is None
        assert provider_slug("   ") is None
        assert provider_slug("") is None
        assert provider_slug(None) is None

    def test_truncation_is_part_of_the_identity(self) -> None:
        """Two names that differ only past the cut share a URL, so they share a count."""
        stem = "California Institute of "
        long_one = stem + "A" * 200
        other = stem + "A" * 201
        assert len(provider_slug(long_one) or "") == SLUG_MAX_LENGTH
        assert provider_slug(long_one) == provider_slug(other)

    def test_two_different_schools_stay_two(self) -> None:
        assert provider_slug("Merced College") != provider_slug("Merced Adult School")


class TestCountProviders:
    def test_two_spellings_of_one_name_are_one_provider(self) -> None:
        assert (
            count_providers(
                [
                    "Procareer Academy",
                    "PROCAREER ACADEMY",
                    "Virtual Design & Construction Institute",
                    "Virtual Design and Construction Institute",
                    "Dialysis Education Services, LLC",
                    "DIALYSIS EDUCATION SERVICES LLC",
                ]
            )
            == 3
        )

    def test_the_raw_rule_would_have_said_six(self) -> None:
        """The defect, stated as a test: the count this replaced, on the same six filings.

        Not a test of the old code -- it is gone -- but of the gap between the rules, so that
        a change quietly restoring the raw rule cannot leave this file green.
        """
        filings = [
            "Procareer Academy",
            "PROCAREER ACADEMY",
            "Virtual Design & Construction Institute",
            "Virtual Design and Construction Institute",
            "Dialysis Education Services, LLC",
            "DIALYSIS EDUCATION SERVICES LLC",
        ]
        assert len({name for name in filings}) == 6
        assert count_providers(filings) == 3

    @pytest.mark.parametrize("blank", ["", "   ", "!!!", None])
    def test_names_carrying_no_identity_are_not_a_provider(self, blank: str | None) -> None:
        assert count_providers(["Merced College", blank]) == 1
