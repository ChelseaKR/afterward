"""Tests for the SOC aggregation table.

The stakes here are asymmetric. A missing mapping costs a program its occupation panel; a
wrong mapping puts another occupation's wage and outlook next to a training programme
someone is deciding whether to spend a year on. The tests are weighted accordingly: the
table's structural invariants are asserted exhaustively, and every "must return None" case
is asserted explicitly rather than left to fall through.
"""

from __future__ import annotations

import pytest

from camino.sources.soc_vintage import (
    AGGREGATIONS,
    SocAggregation,
    aggregation_for,
    resolve_published_soc,
    resolve_published_socs,
)

# The codes EDD publishes for these occupations in the 2024-2034 projections snapshot.
PUBLISHED = frozenset(
    {
        "13-1020",
        "13-2020",
        "21-1018",
        "25-2052",
        "25-9045",
        "29-2010",
        "31-1120",
        "39-7010",
        "47-4090",
        "51-2028",
        "51-2090",
        "53-1047",
        # A detailed occupation EDD publishes under its own code, for the identity path.
        "29-1141",
    }
)

# Codes carried by the 77 unmatched California programs that have no defensible target:
# BLS publishes each under its own code, so there is no aggregate to fall back to, and EDD
# simply does not publish it for California.
REFUSED = [
    "19-1032",  # Foresters
    "19-3041",  # Sociologists
    "19-3094",  # Political Scientists
    "19-4042",  # Environmental Science and Protection Technicians, Including Health
    "19-4043",  # Geological Technicians, Except Hydrologic Technicians
    "19-4044",  # Hydrologic Technicians
    "37-2021",  # Pest Control Workers
    "39-3099",  # Entertainment Attendants and Related Workers, All Other
    "45-4029",  # Logging Workers, All Other
    "47-2011",  # Boilermakers
    "47-2043",  # Floor Sanders and Finishers
    "47-5022",  # Excavating and Loading Machine and Dragline Operators, Surface Mining
    "49-9081",  # Wind Turbine Service Technicians
    "55-2013",  # First-Line Supervisors of All Other Tactical Operations Specialists
]


class TestTableInvariants:
    def test_every_broad_group_target_is_the_source_s_own_parent(self) -> None:
        """The SOC hierarchy derives the parent arithmetically -- no judgement involved.

        A detailed code ``XX-XXXY`` sits in broad group ``XX-XXX0``. Any broad-group row
        that fails this is not a roll-up, it is a guess.
        """
        for aggregation in AGGREGATIONS.values():
            if aggregation.kind == "soc_broad_group":
                assert aggregation.target == aggregation.source[:-1] + "0"

    def test_hybrid_targets_are_not_broad_group_parents(self) -> None:
        """Hybrid codes are cross-cutting, so the arithmetic parent test must not apply.

        21-1018 is not the parent of 21-1011: both are 21-1010 Counselors' business, and
        21-1018 exists only because BLS cannot split the two.
        """
        hybrids = [a for a in AGGREGATIONS.values() if a.kind == "bls_hybrid_occupation"]
        assert hybrids
        assert all(a.target != a.source[:-1] + "0" for a in hybrids)

    def test_no_code_maps_to_itself(self) -> None:
        assert all(a.source != a.target for a in AGGREGATIONS.values())

    def test_targets_are_never_also_sources(self) -> None:
        """One hop only. A chain would silently widen a mapping past the broad group."""
        targets = {a.target for a in AGGREGATIONS.values()}
        assert targets.isdisjoint(AGGREGATIONS)

    def test_keys_agree_with_their_entries(self) -> None:
        assert all(code == aggregation.source for code, aggregation in AGGREGATIONS.items())

    def test_all_codes_are_well_formed(self) -> None:
        for aggregation in AGGREGATIONS.values():
            for code in (aggregation.source, aggregation.target):
                assert len(code) == 7
                assert code[2] == "-"
                assert code.replace("-", "").isdigit()

    def test_no_target_is_a_minor_or_major_group(self) -> None:
        """Guards the rule that mapping stops at broad group.

        Major groups end ``-0000`` and minor groups ``-X000``. O*NET would happily send
        45-3031 to the 45-0000 major group; a major group's median wage is not a wage for
        any job and must never reach a programme page.
        """
        for aggregation in AGGREGATIONS.values():
            assert not aggregation.target.endswith("000")


class TestAggregationFor:
    @pytest.mark.parametrize(
        ("code", "target", "kind"),
        [
            ("31-1121", "31-1120", "soc_broad_group"),
            ("31-1122", "31-1120", "soc_broad_group"),
            ("29-2011", "29-2010", "soc_broad_group"),
            ("29-2012", "29-2010", "soc_broad_group"),
            ("47-4099", "47-4090", "soc_broad_group"),
            ("21-1011", "21-1018", "bls_hybrid_occupation"),
            ("21-1014", "21-1018", "bls_hybrid_occupation"),
            ("25-9042", "25-9045", "bls_hybrid_occupation"),
            ("25-9043", "25-9045", "bls_hybrid_occupation"),
            ("25-9049", "25-9045", "bls_hybrid_occupation"),
        ],
    )
    def test_documented_mappings(self, code: str, target: str, kind: str) -> None:
        aggregation = aggregation_for(code)
        assert aggregation == SocAggregation(source=code, target=target, kind=kind)

    @pytest.mark.parametrize("code", REFUSED)
    def test_codes_without_a_defensible_target_return_none(self, code: str) -> None:
        assert aggregation_for(code) is None

    def test_onet_detail_suffix_is_accepted(self) -> None:
        """The O*NET sources behind this table are written ``31-1121.00``."""
        assert aggregation_for("31-1121.00") == aggregation_for("31-1121")

    def test_surrounding_whitespace_is_tolerated(self) -> None:
        assert aggregation_for("  31-1121 ") == aggregation_for("31-1121")

    @pytest.mark.parametrize(
        "value", ["", "   ", "311121", "31-1121.0", "31-112", "31-11211", "abc", "-", "31-abcd"]
    )
    def test_malformed_input_returns_none_rather_than_raising(self, value: str) -> None:
        """A single bad feed value must not take down a build."""
        assert aggregation_for(value) is None


class TestResolvePublishedSoc:
    def test_a_published_code_resolves_to_itself(self) -> None:
        assert resolve_published_soc("29-1141", PUBLISHED) == "29-1141"

    def test_an_aggregated_code_resolves_to_its_aggregate(self) -> None:
        assert resolve_published_soc("31-1121", PUBLISHED) == "31-1120"
        assert resolve_published_soc("21-1014", PUBLISHED) == "21-1018"

    @pytest.mark.parametrize("code", REFUSED)
    def test_refused_codes_resolve_to_none(self, code: str) -> None:
        assert resolve_published_soc(code, PUBLISHED) is None

    def test_mapping_is_dropped_when_edd_stops_publishing_the_target(self) -> None:
        """EDD re-publishes these files every cycle; the table must not outlive the data."""
        assert resolve_published_soc("31-1121", PUBLISHED - {"31-1120"}) is None

    def test_exact_match_wins_over_aggregation(self) -> None:
        """If EDD ever starts breaking out the detail, the detail is what should be used."""
        assert resolve_published_soc("31-1121", PUBLISHED | {"31-1121"}) == "31-1121"

    def test_unknown_code_resolves_to_none(self) -> None:
        assert resolve_published_soc("15-1252", PUBLISHED) is None


class TestResolvePublishedSocs:
    def test_two_codes_collapsing_to_one_aggregate_are_emitted_once(self) -> None:
        assert resolve_published_socs(["31-1121", "31-1122"], PUBLISHED) == ("31-1120",)

    def test_feed_order_is_preserved(self) -> None:
        codes = ["21-1011", "29-1141", "29-2012"]
        assert resolve_published_socs(codes, PUBLISHED) == ("21-1018", "29-1141", "29-2010")

    def test_unresolvable_codes_are_dropped_not_substituted(self) -> None:
        assert resolve_published_socs(["47-2011", "31-1121"], PUBLISHED) == ("31-1120",)

    def test_all_unresolvable_yields_empty(self) -> None:
        assert resolve_published_socs(REFUSED, PUBLISHED) == ()

    def test_empty_input(self) -> None:
        assert resolve_published_socs([], PUBLISHED) == ()
