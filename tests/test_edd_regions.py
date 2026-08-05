"""Tests for EDD's area geography and the city -> area rule built on it.

The rule under test is deliberately narrow: a program is placed in an EDD area only when
that area's own published title names the program's city. These tests exist to keep it
narrow -- most of them assert that something is *not* matched.
"""

from __future__ import annotations

from afterward.sources.edd_lmi import (
    area_definitions,
    normalise_place,
    parse_area,
    parse_projections,
    principal_city_areas,
)

# The complete set of non-statewide Area Name strings EDD publishes in the 2024-2034
# long-term projections, copied verbatim on 2026-08-04. Held here so the parser is
# exercised against the real strings and not a tidied-up paraphrase of them: every
# irregularity below (four-county lists, an Oxford comma before "and", a metropolitan
# division suffix, a hyphenated region name that is not a city pair) is EDD's, not ours.
METROPOLITAN_AREAS = [
    "Anaheim-Santa Ana-Irvine MD (Orange County)",
    "Bakersfield-Delano MSA (Kern County)",
    "Chico MSA (Butte County)",
    "El Centro MSA (Imperial County)",
    "Fresno MSA (Fresno and Madera Counties)",
    "Hanford-Corcoran MSA (Kings County)",
    "Los Angeles-Long Beach-Glendale MD (Los Angeles County)",
    "Merced MSA (Merced County)",
    "Modesto MSA (Stanislaus County)",
    "Napa MSA (Napa County)",
    "Oakland-Fremont-Berkeley MD (Alameda and Contra Costa Counties)",
    "Oxnard-Thousand Oaks-Ventura MSA (Ventura County)",
    "Redding MSA (Shasta County)",
    "Riverside-San Bernardino-Ontario MSA (Riverside and San Bernardino Counties)",
    "Sacramento-Roseville-Folsom MSA (El Dorado, Placer, Sacramento, and Yolo Counties)",
    "Salinas MSA (Monterey County)",
    "San Diego-Chula Vista-Carlsbad MSA (San Diego County)",
    "San Francisco-San Mateo-Redwood City MD (San Francisco and San Mateo Counties)",
    "San Jose-Sunnyvale-Santa Clara MSA (San Benito and Santa Clara Counties)",
    "San Luis Obispo-Paso Robles MSA (San Luis Obispo County)",
    "San Rafael MD (Marin County)",
    "Santa Cruz-Watsonville MSA (Santa Cruz County)",
    "Santa Maria-Santa Barbara MSA (Santa Barbara County)",
    "Santa Rosa-Petaluma MSA (Sonoma County)",
    "Stockton-Lodi MSA (San Joaquin County)",
    "Vallejo MSA (Solano County)",
    "Visalia MSA (Tulare County)",
    "Yuba City MSA (Sutter and Yuba Counties)",
]

CONSORTIUM_REGIONS = [
    "Eastern Sierra-Mother Lode Region (Alpine, Amador, Calaveras, Inyo, Mariposa, Mono, and Tuolumne Counties)",
    "North Coast Region (Del Norte, Humboldt, Lake, and Mendocino Counties)",
    "North Valley-Northern Mountains Region (Colusa, Glenn, Lassen, Modoc, Nevada, Plumas, Sierra, Siskiyou, Tehama, and Trinity Counties)",
]

PUBLISHED_AREAS = [("Metropolitan Area", name) for name in METROPOLITAN_AREAS] + [
    ("Consortium", name) for name in CONSORTIUM_REGIONS
]

CALIFORNIA_COUNTIES = 58


def _published() -> list:
    return [parse_area(area_type, area_name) for area_type, area_name in PUBLISHED_AREAS]


class TestAreaNameParsing:
    def test_reads_the_counties_out_of_the_parenthetical(self) -> None:
        area = parse_area("Metropolitan Area", "Fresno MSA (Fresno and Madera Counties)")
        assert area.counties == ("Fresno", "Madera")

    def test_handles_a_comma_list_with_a_trailing_and(self) -> None:
        area = parse_area(
            "Metropolitan Area",
            "Sacramento-Roseville-Folsom MSA (El Dorado, Placer, Sacramento, and Yolo Counties)",
        )
        assert area.counties == ("El Dorado", "Placer", "Sacramento", "Yolo")

    def test_reads_the_principal_cities_out_of_a_cbsa_title(self) -> None:
        area = parse_area("Metropolitan Area", "Hanford-Corcoran MSA (Kings County)")
        assert area.principal_cities == ("Hanford", "Corcoran")

    def test_a_metropolitan_division_is_a_cbsa_title_too(self) -> None:
        area = parse_area("Metropolitan Area", "San Rafael MD (Marin County)")
        assert area.principal_cities == ("San Rafael",)

    def test_multi_word_city_names_survive_the_hyphen_split(self) -> None:
        area = parse_area("Metropolitan Area", "Oxnard-Thousand Oaks-Ventura MSA (Ventura County)")
        assert area.principal_cities == ("Oxnard", "Thousand Oaks", "Ventura")

    def test_a_consortium_region_name_yields_no_cities(self) -> None:
        """Eastern Sierra and Mother Lode are EDD's names for stretches of the state.

        Splitting them on the hyphen the way a CBSA title is split would invent two cities
        that do not exist and hand them a region's wages.
        """
        area = parse_area(
            "Consortium",
            "Eastern Sierra-Mother Lode Region (Alpine, Amador, Calaveras, Inyo, "
            "Mariposa, Mono, and Tuolumne Counties)",
        )
        assert area.principal_cities == ()
        assert area.counties[0] == "Alpine"

    def test_a_title_without_an_msa_marker_yields_no_cities(self) -> None:
        # The principal-city guarantee comes from the CBSA naming convention. Absent the
        # marker there is no convention to lean on, so nothing is claimed.
        assert parse_area("Metropolitan Area", "Somewhere-Elsewhere Region").principal_cities == ()

    def test_survives_a_title_with_no_county_gloss(self) -> None:
        area = parse_area("Metropolitan Area", "Fresno MSA")
        assert area.principal_cities == ("Fresno",)
        assert area.counties == ()

    def test_short_name_drops_the_county_gloss_for_display(self) -> None:
        area = parse_area("Metropolitan Area", "Fresno MSA (Fresno and Madera Counties)")
        assert area.short_name == "Fresno MSA"


class TestPublishedGeography:
    """The parse is only trustworthy if it reproduces California exactly."""

    def test_the_counties_cover_california_exactly_once(self) -> None:
        named = [county for area in _published() for county in area.counties]
        assert len(named) == CALIFORNIA_COUNTIES
        assert len(set(named)) == CALIFORNIA_COUNTIES

    def test_every_metropolitan_area_names_at_least_one_city(self) -> None:
        for area in _published():
            if area.is_metropolitan:
                assert area.principal_cities, area.area_name

    def test_no_consortium_region_names_a_city(self) -> None:
        for area in _published():
            if not area.is_metropolitan:
                assert area.principal_cities == (), area.area_name

    def test_no_city_is_claimed_by_two_areas(self) -> None:
        cities = [c for area in _published() for c in area.principal_cities]
        assert len(cities) == len(set(cities))


class TestPrincipalCityIndex:
    def test_maps_a_named_city_to_its_area(self) -> None:
        index = principal_city_areas(_published())
        assert index["bakersfield"].area_name == "Bakersfield-Delano MSA (Kern County)"
        assert index["delano"].area_name == "Bakersfield-Delano MSA (Kern County)"

    def test_matching_is_case_and_whitespace_insensitive(self) -> None:
        index = principal_city_areas(_published())
        assert normalise_place("  SAN   JOSE ") in index

    def test_a_city_no_title_names_is_absent(self) -> None:
        """Pleasant Hill is in Contra Costa County and therefore inside the Oakland MD.

        Knowing that is not the same as EDD having said it, and this rule only repeats
        what EDD said. 120 programs are declined here rather than placed on a guess.
        """
        assert "pleasant hill" not in principal_city_areas(_published())

    def test_a_county_name_alone_is_not_a_city_match(self) -> None:
        # "Orange" appears in "(Orange County)". A program in the city of Orange really is
        # in Orange County, but that is California knowledge, not something the file says.
        assert "orange" not in principal_city_areas(_published())

    def test_a_substring_of_a_named_city_does_not_match(self) -> None:
        index = principal_city_areas(_published())
        assert "long" not in index
        assert "san" not in index

    def test_a_city_claimed_by_two_areas_is_dropped_rather_than_assigned(self) -> None:
        contested = [
            parse_area("Metropolitan Area", "Springfield-Alpha MSA (Alpha County)"),
            parse_area("Metropolitan Area", "Springfield-Beta MSA (Beta County)"),
        ]
        index = principal_city_areas(contested)
        assert "springfield" not in index
        assert "alpha" in index and "beta" in index

    def test_consortium_regions_contribute_nothing_to_the_index(self) -> None:
        index = principal_city_areas(_published())
        assert not any(area.area_type == "Consortium" for area in index.values()), (
            "a rural consortium region was reachable by city name"
        )


class TestAreaDefinitionsFromProjections:
    CSV = """Area Type,Area Name,Period,SOC Level,Standard Occupational Classification (SOC),Occupational Title,Base Year Employment Estimate,Projected Year Employment Estimate,Numeric Change,Percentage Change,Exits,Transfers,Total Job Openings,Median Hourly Wage,Median Annual Wage,Entry Level Education,Work Experience,Job Training
State,California,2024-2034,4,15-1252,Software Developers,1000,1200,200,20.0,50,80,330,68.50,142480,Bachelor's degree,None,None
Metropolitan Area,Fresno MSA (Fresno and Madera Counties),2024-2034,4,15-1252,Software Developers,50,60,10,20.0,3,5,18,45.00,93600,Bachelor's degree,None,None
Metropolitan Area,Fresno MSA (Fresno and Madera Counties),2024-2034,4,29-1141,Registered Nurses,50,60,10,20.0,3,5,18,60.00,124800,Bachelor's degree,None,None
Consortium,"North Coast Region (Del Norte, Humboldt, Lake, and Mendocino Counties)",2024-2034,4,15-1252,Software Developers,5,6,1,20.0,1,1,2,40.00,83200,Bachelor's degree,None,None
"""

    def test_statewide_is_not_an_area(self) -> None:
        areas = area_definitions(parse_projections(self.CSV))
        assert "California" not in {a.area_name for a in areas}

    def test_each_area_is_defined_once_however_many_rows_it_has(self) -> None:
        areas = area_definitions(parse_projections(self.CSV))
        assert len(areas) == 2

    def test_parses_an_embedded_comma_list_from_a_quoted_csv_field(self) -> None:
        areas = area_definitions(parse_projections(self.CSV))
        consortium = next(a for a in areas if not a.is_metropolitan)
        assert consortium.counties == ("Del Norte", "Humboldt", "Lake", "Mendocino")


class TestNormalisePlace:
    def test_empty_and_missing_names_are_none_not_empty_string(self) -> None:
        assert normalise_place(None) is None
        assert normalise_place("   ") is None

    def test_collapses_internal_whitespace(self) -> None:
        assert normalise_place("San\tLuis  Obispo") == "san luis obispo"
