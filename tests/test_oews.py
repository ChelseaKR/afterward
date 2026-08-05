"""Tests for the OEWS wage-distribution client.

The rows below are copied verbatim from the published 2009-2026 extract (checked
2026-08-04), header included, so the parser is exercised against EDD's real spellings rather
than a tidied paraphrase. Every irregularity in them is EDD's: the unhyphenated SOC code,
the two capitalisations of the wage-type label, the three spellings of the statewide area
type, the older vintages' zero-as-suppression and the newer ones' blank.

Most of these tests assert that a wage does *not* appear. That is the point: the invariant
this module exists to hold is that a suppressed wage is None and never zero.
"""

from __future__ import annotations

from afterward.sources.edd_lmi import STATEWIDE_AREA, parse_area
from afterward.sources.oews import (
    ANNUAL,
    HOURLY,
    WageDistribution,
    area_name_joins_to_projections,
    latest_year,
    normalise_soc,
    parse_wage_statistics,
    select,
    statewide_index,
    wage_index,
)
from tests.test_edd_regions import PUBLISHED_AREAS

HEADER = "Area Type,Area Name,Year,Quarter,Industry Name,Standard Occupational Classification,Occupational Title,Wage Type,Number of Employed,Mean Wage,10th Percentile Wage,25th Percentile Wage,50th Percentile (Median) Wage,75th Percentile Wage,90th Percentile Wage,Mean Relative Standard Error for Wage"

# 2026 vintage: blanks suppress, wage-type labels are Title Case, area type is hyphenated.
ROW_STATE_ANNUAL = 'California-Statewide,California,2026,1st Qtr,"Total, All Industry",151252,Software Developers,Annual Wage or Salary,196750,178142.63,101088.25,131295.44,168970.32,215832.91,268624.99,1.2'
ROW_STATE_HOURLY = 'California-Statewide,California,2026,1st Qtr,"Total, All Industry",151252,Software Developers,Hourly Wage,196750,85.65,48.60,63.12,81.24,103.77,129.15,1.2'
ROW_METRO_ANNUAL = 'Metropolitan Area,Fresno MSA,2026,1st Qtr,"Total, All Industry",291141,Registered Nurses,Annual Wage or Salary,7830,137904.11,92613.44,111238.09,133210.55,161422.87,190338.20,2.4'
ROW_REGION_ANNUAL = 'OES Survey Region,North Coast Region,2026,1st Qtr,"Total, All Industry",291141,Registered Nurses,Annual Wage or Salary,1120,129554.02,88214.10,104772.33,127006.44,150881.72,178264.03,3.1'
# One published 2026 row withholds only the 90th percentile.
ROW_PARTIAL = 'California-Statewide,California,2026,1st Qtr,"Total, All Industry",272021,Athletes and Sports Competitors,Annual Wage or Salary,3210,98221.44,41243.07,67621.37,81252.56,153674.65,,18.6'
# A fully suppressed 2026 row: every wage field blank, headcount blank.
ROW_BLANK = 'Metropolitan Area,Yuba City MSA,2026,1st Qtr,"Total, All Industry",111031,Legislators,Annual Wage or Salary,,,,,,,,'
# 2015 vintage: suppression is written as 0, and the result runs backwards.
ROW_2015_ZERO = 'Metropolitan Area,Anaheim-Santa Ana-Irvine MD,2015,1st Qtr,"Total, All Industries",111011,Chief Executives,Annual wage or salary,2850,0.00,99662.99,158290.67,0.00,0.00,0.00,4.7'
# 2009 vintage: a published wage alongside a headcount of zero.
ROW_2009_ZERO_EMP = 'Metropolitan Area,Bakersfield MSA,2009,1st Qtr,"Total, All Industries",119032,"Education Administrators, Elementary",Annual wage or salary,0,84120.00,55110.00,68430.00,82190.00,98760.00,115320.00,6.2'
# Older vintages label the roll-up row with a bare 0 rather than a SOC code.
ROW_TOTAL_ALL = 'Metropolitan Area,Chico,2009,1st Qtr,"Total, All Industries",0,"Total, All Occupations",Annual wage or salary,72340,38210.00,17420.00,22110.00,31280.00,46990.00,71340.00,1.1'
# Statewide area type is spelled with spaces around the hyphen in some vintages.
ROW_SPACED_TYPE = 'California - Statewide,California,2017,1st Qtr,"Total, All Industries",291141,Registered Nurses,Annual wage or salary,282290,101750.00,68420.00,81330.00,98400.00,120110.00,142330.00,0.9'


def csv_text(*rows: str) -> str:
    return "\n".join([HEADER, *rows]) + "\n"


def parse_one(row: str) -> WageDistribution:
    return next(iter(parse_wage_statistics(csv_text(row))))


class TestSuppressedWagesAreNoneNeverZero:
    """The whole reason this module exists."""

    def test_a_zero_percentile_is_not_published_as_zero(self) -> None:
        row = parse_one(ROW_2015_ZERO)
        assert row.p50 is None
        assert row.p75 is None
        assert row.p90 is None

    def test_the_percentiles_that_were_published_survive(self) -> None:
        # Suppression is per-cell. Discarding the whole row would throw away real data.
        row = parse_one(ROW_2015_ZERO)
        assert row.p10 == 99662.99
        assert row.p25 == 158290.67

    def test_a_zero_mean_wage_is_not_published_as_zero(self) -> None:
        assert parse_one(ROW_2015_ZERO).mean_wage is None

    def test_zeroing_repairs_an_impossible_ordering(self) -> None:
        """Read literally, this row says the median is below the 25th percentile."""
        row = parse_one(ROW_2015_ZERO)
        assert row.is_monotonic
        assert not row.is_complete

    def test_a_blank_percentile_is_none(self) -> None:
        assert parse_one(ROW_BLANK).p50 is None

    def test_a_fully_suppressed_row_reports_no_wage_at_all(self) -> None:
        row = parse_one(ROW_BLANK)
        assert not row.has_any_wage
        assert not row.is_complete
        assert row.percentiles == (None,) * 5

    def test_one_withheld_percentile_does_not_suppress_the_others(self) -> None:
        row = parse_one(ROW_PARTIAL)
        assert row.has_any_wage
        assert not row.is_complete
        assert row.p75 == 153674.65
        assert row.p90 is None

    def test_a_zero_headcount_beside_a_published_wage_is_not_zero_workers(self) -> None:
        row = parse_one(ROW_2009_ZERO_EMP)
        assert row.employment is None
        assert row.p50 == 82190.00

    def test_a_real_headcount_is_preserved(self) -> None:
        assert parse_one(ROW_STATE_ANNUAL).employment == 196750


class TestSocCodes:
    def test_the_unhyphenated_code_is_reformatted(self) -> None:
        assert parse_one(ROW_STATE_ANNUAL).soc_code == "15-1252"

    def test_an_already_hyphenated_code_is_accepted(self) -> None:
        assert normalise_soc("29-1141") == "29-1141"

    def test_the_bare_zero_roll_up_row_carries_no_soc_code(self) -> None:
        # "Total, All Occupations" is not an occupation and has no code to invent.
        assert parse_one(ROW_TOTAL_ALL).soc_code is None

    def test_a_code_of_the_wrong_length_is_refused(self) -> None:
        assert normalise_soc("15125") is None
        assert normalise_soc("1512522") is None

    def test_a_non_numeric_code_is_refused(self) -> None:
        assert normalise_soc("15-12XX") is None
        assert normalise_soc("") is None
        assert normalise_soc(None) is None

    def test_a_detailed_occupation_is_recognised(self) -> None:
        assert parse_one(ROW_STATE_ANNUAL).is_detailed_occupation

    def test_roll_up_levels_are_not_detailed_occupations(self) -> None:
        # Major, minor and broad groups all end in 0 under the 2018 SOC.
        for code in ("11-0000", "11-1000", "31-1120"):
            row = parse_one(ROW_STATE_ANNUAL.replace("151252", code.replace("-", "")))
            assert not row.is_detailed_occupation, code


class TestFileSpellings:
    """OEWS writes the same thing several ways across eighteen vintages."""

    def test_both_capitalisations_of_the_annual_label_read_as_annual(self) -> None:
        assert parse_one(ROW_STATE_ANNUAL).basis == ANNUAL
        assert parse_one(ROW_2015_ZERO).basis == ANNUAL

    def test_the_hourly_label_reads_as_hourly(self) -> None:
        assert parse_one(ROW_STATE_HOURLY).basis == HOURLY

    def test_the_hyphenated_statewide_area_type_is_statewide(self) -> None:
        assert parse_one(ROW_STATE_ANNUAL).is_statewide

    def test_the_spaced_statewide_area_type_is_also_statewide(self) -> None:
        assert parse_one(ROW_SPACED_TYPE).is_statewide

    def test_a_metropolitan_row_is_not_statewide(self) -> None:
        assert not parse_one(ROW_METRO_ANNUAL).is_statewide

    def test_a_survey_region_row_is_not_statewide(self) -> None:
        assert not parse_one(ROW_REGION_ANNUAL).is_statewide

    def test_the_quoted_industry_field_survives_its_embedded_comma(self) -> None:
        assert parse_one(ROW_STATE_ANNUAL).industry == "Total, All Industry"


class TestSpread:
    """The thing a median alone cannot say."""

    def test_spread_ratio_is_p90_over_p10(self) -> None:
        row = parse_one(ROW_STATE_ANNUAL)
        assert row.spread_ratio is not None
        assert round(row.spread_ratio, 3) == round(268624.99 / 101088.25, 3)

    def test_a_suppressed_tail_yields_no_spread_rather_than_a_wrong_one(self) -> None:
        assert parse_one(ROW_PARTIAL).spread_ratio is None
        assert parse_one(ROW_BLANK).spread_ratio is None

    def test_a_complete_row_reports_complete(self) -> None:
        assert parse_one(ROW_METRO_ANNUAL).is_complete

    def test_percentiles_come_back_in_order(self) -> None:
        assert parse_one(ROW_METRO_ANNUAL).percentiles == (
            92613.44,
            111238.09,
            133210.55,
            161422.87,
            190338.20,
        )

    def test_a_backwards_row_is_reported_rather_than_quietly_reordered(self) -> None:
        backwards = ROW_METRO_ANNUAL.replace(",133210.55,", ",13321.05,")
        assert not parse_one(backwards).is_monotonic


class TestVintageSelection:
    PANEL = csv_text(
        ROW_STATE_ANNUAL,
        ROW_STATE_HOURLY,
        ROW_METRO_ANNUAL,
        ROW_REGION_ANNUAL,
        ROW_2015_ZERO,
        ROW_SPACED_TYPE,
    )

    def test_latest_year_finds_the_newest_vintage(self) -> None:
        assert latest_year(parse_wage_statistics(self.PANEL)) == 2026

    def test_latest_year_of_nothing_is_none_not_an_error(self) -> None:
        assert latest_year([]) is None

    def test_select_defaults_to_the_latest_annual_vintage(self) -> None:
        rows = select(parse_wage_statistics(self.PANEL))
        assert {r.year for r in rows} == {2026}
        assert {r.basis for r in rows} == {ANNUAL}

    def test_select_can_be_pinned_to_an_older_vintage(self) -> None:
        rows = select(parse_wage_statistics(self.PANEL), year=2015)
        assert len(rows) == 1
        assert rows[0].title == "Chief Executives"

    def test_select_can_keep_both_wage_bases(self) -> None:
        rows = select(parse_wage_statistics(self.PANEL), basis=None)
        assert {r.basis for r in rows} == {ANNUAL, HOURLY}

    def test_mixing_vintages_is_what_selection_prevents(self) -> None:
        """2015 and 2026 both publish Registered Nurses; only one of them is current."""
        rows = select(parse_wage_statistics(self.PANEL), basis=None)
        assert all(r.year == 2026 for r in rows)


class TestIndexes:
    PANEL = csv_text(
        ROW_STATE_ANNUAL,
        ROW_STATE_HOURLY,
        ROW_METRO_ANNUAL,
        ROW_REGION_ANNUAL,
        ROW_TOTAL_ALL,
        ROW_SPACED_TYPE,
    )

    def test_wage_index_is_keyed_by_area_and_soc(self) -> None:
        index = wage_index(parse_wage_statistics(self.PANEL))
        assert index[("Fresno MSA", "29-1141")].p50 == 133210.55
        assert index[("North Coast Region", "29-1141")].p50 == 127006.44

    def test_the_hourly_row_does_not_collide_with_the_annual_one(self) -> None:
        index = wage_index(parse_wage_statistics(self.PANEL), basis=ANNUAL)
        assert index[("California", "15-1252")].p50 == 168970.32

    def test_the_hourly_index_is_a_separate_read_of_the_same_estimate(self) -> None:
        index = wage_index(parse_wage_statistics(self.PANEL), basis=HOURLY)
        assert index[("California", "15-1252")].p50 == 81.24

    def test_a_row_with_no_usable_soc_code_is_not_indexed(self) -> None:
        index = wage_index(parse_wage_statistics(self.PANEL), year=2009)
        assert index == {}

    def test_statewide_index_keeps_only_california(self) -> None:
        index = statewide_index(parse_wage_statistics(self.PANEL))
        assert set(index) == {"15-1252"}

    def test_statewide_index_honours_an_older_vintage(self) -> None:
        index = statewide_index(parse_wage_statistics(self.PANEL), year=2017)
        assert index["29-1141"].p50 == 98400.00


# The 32 area names the 2026 vintage publishes, copied verbatim on 2026-08-04. Held here so
# the join is pinned to real strings: each one is also exactly what the projections put
# before their parenthetical county gloss, which is the entire basis of the area join.
OEWS_2026_AREA_NAMES = [
    "Anaheim-Santa Ana-Irvine MD",
    "Bakersfield-Delano MSA",
    "California",
    "Chico MSA",
    "Eastern Sierra-Mother Lode Region",
    "El Centro MSA",
    "Fresno MSA",
    "Hanford-Corcoran MSA",
    "Los Angeles-Long Beach-Glendale MD",
    "Merced MSA",
    "Modesto MSA",
    "Napa MSA",
    "North Coast Region",
    "North Valley-Northern Mountains Region",
    "Oakland-Fremont-Berkeley MD",
    "Oxnard-Thousand Oaks-Ventura MSA",
    "Redding MSA",
    "Riverside-San Bernardino-Ontario MSA",
    "Sacramento-Roseville-Folsom MSA",
    "Salinas MSA",
    "San Diego-Chula Vista-Carlsbad MSA",
    "San Francisco-San Mateo-Redwood City MD",
    "San Jose-Sunnyvale-Santa Clara MSA",
    "San Luis Obispo-Paso Robles MSA",
    "San Rafael MD",
    "Santa Cruz-Watsonville MSA",
    "Santa Maria-Santa Barbara MSA",
    "Santa Rosa-Petaluma MSA",
    "Stockton-Lodi MSA",
    "Vallejo MSA",
    "Visalia MSA",
    "Yuba City MSA",
]


class TestAreaJoin:
    def test_every_published_area_name_joins_to_the_projections_key(self) -> None:
        projection_keys = {parse_area(t, n).short_name for t, n in PUBLISHED_AREAS}
        projection_keys.add(STATEWIDE_AREA)
        joined = {
            name
            for name in OEWS_2026_AREA_NAMES
            if area_name_joins_to_projections(name) in projection_keys
        }
        assert joined == set(OEWS_2026_AREA_NAMES)
        assert len(projection_keys) == len(OEWS_2026_AREA_NAMES) == 32

    def test_the_join_is_exact_and_refuses_a_near_miss(self) -> None:
        """An older vintage's name for the same place must not silently match.

        "Bakersfield MSA" (2009-2022) and "Bakersfield-Delano MSA" (2023-) are the same
        county, but nothing here is allowed to decide that. Matching them would be a guess
        about California geography, and the vintages differ in coverage as well as name.
        """
        projection_keys = {parse_area(t, n).short_name for t, n in PUBLISHED_AREAS}
        assert area_name_joins_to_projections("Bakersfield MSA") not in projection_keys
        assert area_name_joins_to_projections("San Diego-Carlsbad MSA") not in projection_keys

    def test_a_missing_area_name_joins_to_nothing(self) -> None:
        assert area_name_joins_to_projections(None) is None
        assert area_name_joins_to_projections("   ") is None
