"""The ZIP-to-county crosswalk (D8), and the second placement rule built on it.

Two things are under test here and they fail in opposite directions. The crosswalk itself
must not answer for a ZIP nobody published a county for -- a mailing ZIP with no ZCTA is an
absence, and returning an empty county set for it would render as "this ZIP is in no county"
and place nothing while looking like a finding. The placement rule must not answer for a ZIP
that reaches more than one area, or reaches ground no area claims, because a program on the
Los Angeles side of a Los Angeles/Orange ZIP renders identically to one on the Orange side.

The vendored extract is checked against its own retrieval record and against the specific
rows that make the refusals possible. Those rows are the ones a size optimisation would
delete first.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from afterward.build import (
    AREA_MATCH_COUNTY,
    AREA_MATCH_PRINCIPAL_CITY,
    UNPLACED_COUNTY_OUTSIDE_AREAS,
    UNPLACED_CROSSWALK_NOT_READ,
    UNPLACED_NO_ZIP,
    UNPLACED_STRADDLES_AREAS,
    UNPLACED_ZIP_NOT_IN_CROSSWALK,
    CountyIndex,
    area_for_zip,
    area_placement_coverage,
    county_index,
    place_program,
    program_payload,
)
from afterward.sources import zip_county
from afterward.sources.dol_etp import Program, parse_program
from afterward.sources.edd_lmi import parse_area

# EDD writes each area's counties into its own published title, so the fixtures below are
# real ``Area Name`` strings from the 2024-2034 projections file rather than invented ones.
LOS_ANGELES = parse_area(
    "Metropolitan Area", "Los Angeles-Long Beach-Glendale MD (Los Angeles County)"
)
ORANGE = parse_area("Metropolitan Area", "Anaheim-Santa Ana-Irvine MD (Orange County)")
INLAND_EMPIRE = parse_area(
    "Metropolitan Area",
    "Riverside-San Bernardino-Ontario MSA (Riverside and San Bernardino Counties)",
)
NORTH_COAST = parse_area(
    "Consortium", "North Coast Region (Del Norte, Humboldt, Lake, and Mendocino Counties)"
)
NORTH_VALLEY = parse_area(
    "Consortium",
    "North Valley-Northern Mountains Region (Colusa, Glenn, Lassen, Modoc, Nevada, Plumas, "
    "Sierra, Siskiyou, Tehama, and Trinity Counties)",
)
AREAS = [LOS_ANGELES, ORANGE, INLAND_EMPIRE, NORTH_COAST, NORTH_VALLEY]


@pytest.fixture(scope="module")
def crosswalk() -> zip_county.ZipCountyCrosswalk:
    return zip_county.load_vendored()


@pytest.fixture(scope="module")
def counties(crosswalk: zip_county.ZipCountyCrosswalk) -> CountyIndex:
    return county_index(AREAS, crosswalk)


class TestNormaliseZip:
    """A ZIP that cannot be read is an unusable record, never a truncated one."""

    @pytest.mark.parametrize(
        ("filed", "expected"),
        [
            ("91355", "91355"),
            (" 91355 ", "91355"),
            ("91355-1234", "91355"),
            ("913551234", "91355"),
        ],
    )
    def test_reads_the_shapes_dol_files(self, filed: str, expected: str) -> None:
        assert zip_county.normalise_zip(filed) == expected

    @pytest.mark.parametrize("filed", [None, "", "   ", "9135", "9135X", "91355-12", "CA 91355"])
    def test_refuses_everything_else(self, filed: str | None) -> None:
        """A four-digit value is not a ZIP missing its leading zero; it is a value nobody
        here can tell apart from a typo, and inventing the zero would place a program."""
        assert zip_county.normalise_zip(filed) is None


class TestNormaliseCounty:
    def test_the_two_publishers_spell_the_same_county_differently(self) -> None:
        # Census writes NAMELSAD; EDD's gloss has already had the noun stripped.
        assert zip_county.normalise_county("Los Angeles County") == "los angeles"
        assert zip_county.normalise_county("Los Angeles") == "los angeles"

    def test_the_noun_only_goes_at_the_end(self) -> None:
        assert zip_county.normalise_county("Orange County") == "orange"
        assert zip_county.normalise_county("County Line") == "county line"

    def test_nothing_normalises_to_an_empty_name(self) -> None:
        assert zip_county.normalise_county("   ") is None
        assert zip_county.normalise_county(None) is None


RELATIONSHIP_HEADER = (
    "OID_ZCTA5_20|GEOID_ZCTA5_20|NAMELSAD_ZCTA5_20|AREALAND_ZCTA5_20|AREAWATER_ZCTA5_20|"
    "MTFCC_ZCTA5_20|CLASSFP_ZCTA5_20|FUNCSTAT_ZCTA5_20|OID_COUNTY_20|GEOID_COUNTY_20|"
    "NAMELSAD_COUNTY_20|AREALAND_COUNTY_20|AREAWATER_COUNTY_20|MTFCC_COUNTY_20|"
    "CLASSFP_COUNTY_20|FUNCSTAT_COUNTY_20|AREALAND_PART|AREAWATER_PART"
)


def _relationship_row(zcta: str, geoid: str, name: str) -> str:
    fields = [""] * 18
    fields[1] = zcta
    fields[9] = geoid
    fields[10] = name
    return "|".join(fields)


class TestParseRelationshipFile:
    def test_a_county_row_with_no_zcta_is_not_a_crosswalk_row(self) -> None:
        """The national file carries county records with the ZCTA columns blank. A blank
        ZCTA is not a ZIP, and reading one as the empty-string ZIP would give every such
        county to a key nothing looks up."""
        text = "\n".join(
            [
                RELATIONSHIP_HEADER,
                _relationship_row("", "06037", "Los Angeles County"),
                _relationship_row("91355", "06037", "Los Angeles County"),
            ]
        )
        rows = list(zip_county.parse_relationship_file(text))
        assert [row.zcta for row in rows] == ["91355"]


class TestCaliforniaSubset:
    def test_it_keeps_the_out_of_state_half_of_a_border_zcta(self) -> None:
        """The load-bearing case, and the one a size optimisation deletes first.

        Keeping only California's own rows would leave 89439 looking like a clean
        single-county ZIP in Sierra County, and the placement rule would place it. It is
        not: half of it is in Nevada. A refusal turned into a placement by a filter is this
        project's own defect class committed against its own geography.
        """
        text = "\n".join(
            [
                RELATIONSHIP_HEADER,
                _relationship_row("89439", "06091", "Sierra County"),
                _relationship_row("89439", "32031", "Washoe County"),
                _relationship_row("89001", "32023", "Nye County"),
            ]
        )
        subset = zip_county.california_subset(zip_county.parse_relationship_file(text))
        assert [(row.zcta, row.county_geoid) for row in subset] == [
            ("89439", "06091"),
            ("89439", "32031"),
        ]

    def test_a_zcta_nowhere_near_california_is_dropped_whole(self) -> None:
        text = "\n".join([RELATIONSHIP_HEADER, _relationship_row("89001", "32023", "Nye County")])
        assert zip_county.california_subset(zip_county.parse_relationship_file(text)) == []

    def test_the_extract_round_trips(self) -> None:
        text = "\n".join(
            [
                RELATIONSHIP_HEADER,
                _relationship_row("89439", "32031", "Washoe County"),
                _relationship_row("89439", "06091", "Sierra County"),
            ]
        )
        rows = zip_county.california_subset(zip_county.parse_relationship_file(text))
        assert list(zip_county.parse_csv(zip_county.render_csv(rows))) == rows


class TestVendoredExtract:
    """The committed file, against the record committed beside it."""

    def test_the_recorded_digest_is_the_digest_of_the_file(self) -> None:
        """A sha256 nothing recomputes is a sha256 that can drift away from its file, and a
        retrieval record that no longer describes the artifact beside it is worse than none:
        it is a citation that looks checkable and is not."""
        record = zip_county.vendored_provenance()
        digest = hashlib.sha256(zip_county.VENDORED_PATH.read_bytes()).hexdigest()
        assert record["sha256"] == digest

    def test_the_recorded_counts_are_the_counts_in_the_file(self) -> None:
        record = zip_county.vendored_provenance()
        rows = list(zip_county.parse_csv(zip_county.VENDORED_PATH.read_text(encoding="utf-8")))
        assert record["rows"] == len(rows)
        assert record["zctas"] == len({row.zcta for row in rows})
        assert record["out_of_state_rows"] == sum(1 for row in rows if not row.is_california)
        assert record["california_counties"] == len(
            {row.county_geoid for row in rows if row.is_california}
        )

    def test_it_carries_all_fifty_eight_california_counties(
        self, crosswalk: zip_county.ZipCountyCrosswalk
    ) -> None:
        assert len(crosswalk.california_county_geoids) == 58

    def test_it_still_carries_the_cross_border_rows(
        self, crosswalk: zip_county.ZipCountyCrosswalk
    ) -> None:
        """Named individually, because the count alone would survive one being swapped for
        a California row. Each of these is a ZIP the placement rule must refuse."""
        assert crosswalk.counties("89439") == frozenset({"06091", "32031"})
        assert crosswalk.counties("97635") == frozenset({"06049", "41037"})
        assert crosswalk.counties("89019") == frozenset({"06027", "06071", "32003"})

    def test_a_county_name_repeats_across_states_and_the_geoids_do_not(
        self, crosswalk: zip_county.ZipCountyCrosswalk
    ) -> None:
        """ZCTA 97635 reaches Lake County, *Oregon*. California has a Lake County of its
        own, in a different EDD area. Keyed on the name, the Oregon county would be read as
        the California one; keyed on the code, it is a county this pipeline knows nothing
        about, which is the truth."""
        assert crosswalk.california_county("Lake") == "06033"
        reached = crosswalk.counties("97635")
        assert reached is not None
        assert "41037" in reached
        assert "06033" not in reached

    def test_a_mailing_zip_with_no_zcta_is_unanswerable_not_countyless(
        self, crosswalk: zip_county.ZipCountyCrosswalk
    ) -> None:
        """90239 is a Downey PO Box range. It is a real ZIP with no ZCTA, which is the known
        and recorded cost of reading a ZCTA file for a mailing ZIP. None, not an empty
        frozenset: "nobody published a county for this" is not "this is in no county"."""
        assert crosswalk.counties("90239") is None

    def test_an_unreadable_zip_is_unanswerable_too(
        self, crosswalk: zip_county.ZipCountyCrosswalk
    ) -> None:
        assert crosswalk.counties(None) is None
        assert crosswalk.counties("9135") is None


class TestCountyIndex:
    def test_every_county_edd_names_resolves(self, counties: CountyIndex) -> None:
        assert counties.unresolved_counties == ()

    def test_a_consortium_region_is_indexed_even_though_no_city_can_match_it(
        self, counties: CountyIndex
    ) -> None:
        """The city rule cannot reach a Consortium: its name is an EDD coinage, not a CBSA
        title, so ``principal_cities`` is empty for it. Its gloss names real counties, and
        that is the half this rule reads."""
        by_county = counties.areas_by_county
        assert by_county["06023"].area_name == NORTH_COAST.area_name  # Humboldt

    def test_an_out_of_state_county_is_in_no_area(self, counties: CountyIndex) -> None:
        by_county = counties.areas_by_county
        assert "41037" not in by_county  # Lake County, Oregon
        assert "32031" not in by_county  # Washoe County, Nevada

    def test_a_county_two_areas_both_claim_is_given_to_neither(
        self, crosswalk: zip_county.ZipCountyCrosswalk
    ) -> None:
        """Nothing in the current file is ambiguous this way. A re-publication that made it
        so must lose the county rather than have this code pick a winner."""
        rival = parse_area("Metropolitan Area", "Invented MSA (Los Angeles County)")
        index = county_index([LOS_ANGELES, rival], crosswalk)
        assert "06037" not in index.areas_by_county


class TestAreaForZip:
    def test_a_zip_in_one_county_of_one_area_is_placed(self, counties: CountyIndex) -> None:
        area, reason = area_for_zip("91355", counties)  # Valencia, Los Angeles County
        assert reason is None
        assert area is not None
        assert area.area_name == LOS_ANGELES.area_name

    def test_a_zip_straddling_two_counties_inside_one_area_is_placed(
        self, counties: CountyIndex
    ) -> None:
        """92373 (Redlands) reaches Riverside and San Bernardino. Both are named in the
        Inland Empire MSA's own title, so the whole ZIP is inside one area and there is
        nothing to guess about."""
        area, reason = area_for_zip("92373", counties)
        assert reason is None
        assert area is not None
        assert area.area_name == INLAND_EMPIRE.area_name

    def test_a_zip_straddling_two_areas_stays_unplaced(self, counties: CountyIndex) -> None:
        """90630 (Cypress) reaches Los Angeles and Orange, which are different EDD areas
        with different wages. Either answer would render identically to the other."""
        assert area_for_zip("90630", counties) == (None, UNPLACED_STRADDLES_AREAS)

    def test_a_zip_reaching_out_of_state_stays_unplaced(self, counties: CountyIndex) -> None:
        """89439 is half in Sierra County, California and half in Washoe County, Nevada. The
        California half alone would place it; the ZIP as published does not."""
        assert area_for_zip("89439", counties) == (None, UNPLACED_STRADDLES_AREAS)

    def test_a_zip_wholly_outside_every_area_stays_unplaced(
        self, crosswalk: zip_county.ZipCountyCrosswalk
    ) -> None:
        """Distinct from straddling: nothing this ZIP touches is claimed by any area at all."""
        index = county_index([ORANGE], crosswalk)
        assert area_for_zip("91355", index) == (None, UNPLACED_COUNTY_OUTSIDE_AREAS)

    def test_a_zip_with_no_crosswalk_row_stays_unplaced_for_its_own_reason(
        self, counties: CountyIndex
    ) -> None:
        assert area_for_zip("90239", counties) == (None, UNPLACED_ZIP_NOT_IN_CROSSWALK)

    def test_an_unreadable_zip_stays_unplaced_for_its_own_reason(
        self, counties: CountyIndex
    ) -> None:
        assert area_for_zip(None, counties) == (None, UNPLACED_NO_ZIP)
        assert area_for_zip("9135", counties) == (None, UNPLACED_NO_ZIP)

    def test_no_crosswalk_at_all_is_not_a_finding_about_the_program(self) -> None:
        assert area_for_zip("91355", None) == (None, UNPLACED_CROSSWALK_NOT_READ)


def _program(**source: object) -> Program:
    return parse_program({"_source": {"field_uuid": "u", "field_etp": "provider", **source}})


class TestPlaceProgram:
    def test_the_city_rule_goes_first_and_says_so(self, counties: CountyIndex) -> None:
        city_areas = {"los angeles": LOS_ANGELES}
        area, matched_on, reason = place_program(
            _program(field_city="Los Angeles", field_zip="90012"), city_areas, counties
        )
        assert (matched_on, reason) == (AREA_MATCH_PRINCIPAL_CITY, None)
        assert area is not None

    def test_a_city_edd_does_not_name_falls_through_to_the_county_rule(
        self, counties: CountyIndex
    ) -> None:
        area, matched_on, reason = place_program(
            _program(field_city="Valencia", field_zip="91355"),
            {"los angeles": LOS_ANGELES},
            counties,
        )
        assert (matched_on, reason) == (AREA_MATCH_COUNTY, None)
        assert area is not None
        assert area.area_name == LOS_ANGELES.area_name

    def test_a_program_placed_by_county_has_that_county_named_in_the_areas_own_title(
        self, counties: CountyIndex
    ) -> None:
        """The claim the placement makes, checked against the string EDD published. If the
        county is not in the area's own ``area_name``, this rule has inferred a fact about
        California rather than restated one."""
        area, matched_on, _ = place_program(_program(field_zip="95521"), None, counties)  # Arcata
        assert matched_on == AREA_MATCH_COUNTY
        assert area is not None
        assert "Humboldt" in area.area_name

    def test_a_refused_program_carries_the_reason_and_no_area(self, counties: CountyIndex) -> None:
        area, matched_on, reason = place_program(
            _program(field_city="Cypress", field_zip="90630"), {}, counties
        )
        assert (area, matched_on, reason) == (None, None, UNPLACED_STRADDLES_AREAS)


class TestProgramPayloadPlacement:
    def test_the_record_says_which_rule_placed_it(self, counties: CountyIndex) -> None:
        payload = program_payload(
            _program(field_city="Valencia", field_zip="91355"), {}, {}, counties=counties
        )
        assert payload["region"]["matched_on"] == AREA_MATCH_COUNTY
        assert payload["region_unplaced_reason"] is None

    def test_an_unplaced_record_says_why(self, counties: CountyIndex) -> None:
        payload = program_payload(
            _program(field_city="Cypress", field_zip="90630"), {}, {}, counties=counties
        )
        assert payload["region"] is None
        assert payload["region_unplaced_reason"] == UNPLACED_STRADDLES_AREAS

    def test_a_build_that_read_no_crosswalk_places_nothing_and_claims_nothing(self) -> None:
        """The hermetic path. Every unplaced record says the crosswalk was not read, which
        is a statement about the build and must not be counted as a refusal."""
        payload = program_payload(_program(field_city="Valencia", field_zip="91355"), {}, {})
        assert payload["region"] is None
        assert payload["region_unplaced_reason"] == UNPLACED_CROSSWALK_NOT_READ


class TestAreaPlacementCoverage:
    def _payload(self, matched_on: str | None, reason: str | None = None) -> dict[str, object]:
        region = None if matched_on is None else {"area_name": "A", "matched_on": matched_on}
        return {"region": region, "region_unplaced_reason": reason}

    def test_it_counts_by_rule_and_by_refusal(self) -> None:
        payloads = [
            self._payload(AREA_MATCH_PRINCIPAL_CITY),
            self._payload(AREA_MATCH_COUNTY),
            self._payload(AREA_MATCH_COUNTY),
            self._payload(None, UNPLACED_STRADDLES_AREAS),
            self._payload(None, UNPLACED_ZIP_NOT_IN_CROSSWALK),
        ]
        coverage = area_placement_coverage(payloads)
        assert coverage["placed"] == 3
        assert coverage["placed_by_rule"] == {AREA_MATCH_PRINCIPAL_CITY: 1, AREA_MATCH_COUNTY: 2}
        assert coverage["unplaced"] == 2
        assert coverage["unplaced_by_reason"][UNPLACED_STRADDLES_AREAS] == 1
        assert coverage["unplaced_by_reason"][UNPLACED_ZIP_NOT_IN_CROSSWALK] == 1

    def test_a_reason_that_did_not_occur_is_a_zero_not_an_absence(self) -> None:
        """An absent key reads as "this cannot happen". A zero reads as "it did not happen
        in this build", which is the only one of the two that is true."""
        coverage = area_placement_coverage([self._payload(AREA_MATCH_COUNTY)])
        assert coverage["unplaced_by_reason"][UNPLACED_NO_ZIP] == 0
        assert set(coverage["unplaced_by_reason"]) == {
            UNPLACED_CROSSWALK_NOT_READ,
            UNPLACED_NO_ZIP,
            UNPLACED_ZIP_NOT_IN_CROSSWALK,
            UNPLACED_COUNTY_OUTSIDE_AREAS,
            UNPLACED_STRADDLES_AREAS,
        }

    def test_an_unplaced_record_carrying_no_reason_is_counted_as_such(self) -> None:
        """A payload built before this field existed. Attributing it to any of the five
        named reasons would be this dataset's own defect class committed in the block that
        measures it."""
        coverage = area_placement_coverage([{"region": None}])
        assert coverage["unplaced_reason_absent"] == 1
        assert sum(coverage["unplaced_by_reason"].values()) == 0

    def test_unresolved_counties_are_published_rather_than_dropped(self) -> None:
        coverage = area_placement_coverage([], ["Ynys Môn", "Ynys Môn"])
        assert coverage["counties_unresolved"] == ["Ynys Môn"]


class TestRefreshScriptRecord:
    def test_the_record_names_the_url_the_module_fetches(self) -> None:
        record = zip_county.vendored_provenance()
        assert record["source_url"] == zip_county.RELATIONSHIP_URL

    def test_the_record_is_valid_json_with_the_keys_the_refresh_rewrites(self) -> None:
        raw = json.loads(zip_county.VENDORED_PROVENANCE_PATH.read_text(encoding="utf-8"))
        for key in ("retrieved", "sha256", "upstream_sha256", "rows", "zctas"):
            assert key in raw
