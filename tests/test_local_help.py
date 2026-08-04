"""Tests for the America's Job Center locator and the WIOA next-step content.

This module is different from the other source clients in one way that matters: it does not
describe a training program, it tells a person where to go and hints that public money might
pay for them. So the tests fall into two groups.

The first group is the usual discipline -- an unpublished phone number is ``None`` and not
an empty string, a center with no coordinates is never ranked as though it were nearby, a
cached response fetched with a different request is never served as the answer to this one,
and a build with no credentials still finishes.

The second group has no equivalent elsewhere in this repository. It asserts that the
published wording cannot promise anyone funding, that the "who decides this" sentence cannot
be separated from the steps it qualifies, and that every claim carries a citation. Those are
not style preferences. The harm this feature can do is send someone to an office expecting
money they will not get, and these are the checks that stand between the code and that.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from camino.sources.careeronestop import TOKEN_ENV, USER_ID_ENV
from camino.sources.local_help import (
    COMPREHENSIVE,
    ETPL_SNAPSHOT_CAVEAT,
    QUESTIONS,
    STEPS,
    WHO_DECIDES,
    AmericanJobCenter,
    Place,
    cache_envelope,
    distance_miles,
    etpl_listing_note,
    fetch_centers,
    fetch_centers_near,
    funding_guidance,
    measure_coverage,
    nearest_centers,
    parse_center,
    parse_centers,
    places_from_programs,
)

RECORD: dict[str, Any] = {
    "ID": "58175",
    "Name": "Asian Resources, Inc. (ARI) AJCC",
    "Address1": "2411 Alhambra Blvd",
    "Address2": "Suite 110",
    "City": "Sacramento",
    "StateAbbr": "CA",
    "StateName": "California",
    "Zip": "95817",
    "Phone": "916-324-6202",
    "Distance": "1.9",
    "ProgramType": "Affiliate Center",
    "OpenHour": "Monday - Friday, 8:00am - 4:30pm",
    "CenterIsOpen": "Y",
    "VeteranRep": "No",
    "GeneralEmail": "",
    "LastUpdated": "07/22/2026",
    "WhyClosed": "",
    "Latitude": 38.556739,
    "Longitude": -121.472093,
    "WebSiteUrl": "https://example.org/job-center-services/",
    "WorkersServices": [
        {"ServiceName": "Getting Skills and Education"},
        {"ServiceName": "Finding Work"},
        {"ServiceName": "Getting Skills and Education"},
        {"ServiceName": "  "},
    ],
    "YouthServices": [{"ServiceName": "Summer Opportunities"}],
}

PAYLOAD: dict[str, Any] = {"OneStopCenterList": [RECORD], "RecordCount": 1}


def _center(**overrides: Any) -> AmericanJobCenter:
    parsed = parse_center({**RECORD, **overrides})
    assert parsed is not None
    return parsed


def _built(
    name: str,
    lat: float | None,
    lon: float | None,
    *,
    center_type: str | None = COMPREHENSIVE,
) -> AmericanJobCenter:
    """A minimal center, for the geometry tests that do not care about contact fields."""
    return AmericanJobCenter(
        center_id=name,
        name=name,
        address=(),
        city=None,
        state="CA",
        postal_code=None,
        phone=None,
        email=None,
        website=None,
        hours=None,
        center_type=center_type,
        lat=lat,
        lon=lon,
        veterans_representative=None,
        temporarily_closed=None,
        closure_note=None,
        worker_services=(),
        youth_services=(),
        last_updated=None,
    )


class TestParseCenter:
    def test_reads_the_contact_details_a_person_needs(self) -> None:
        center = _center()
        assert center.name == "Asian Resources, Inc. (ARI) AJCC"
        assert center.address == ("2411 Alhambra Blvd", "Suite 110")
        assert center.phone == "916-324-6202"
        assert center.hours == "Monday - Friday, 8:00am - 4:30pm"

    def test_a_blank_field_is_null_not_an_empty_string(self) -> None:
        # An empty string reaches a template as a rendered blank beside a label, which reads
        # as "this center has no email" rather than "nobody filled the box in".
        assert _center().email is None

    def test_an_unstated_veterans_representative_is_unknown_not_no(self) -> None:
        # The difference decides whether a veteran bothers going. "No" is a claim; blank
        # is the absence of one, and they must not be collapsed.
        assert _center(VeteranRep="").veterans_representative is None
        assert _center(VeteranRep="No").veterans_representative is False
        assert _center(VeteranRep="Yes").veterans_representative is True

    def test_reads_whether_the_center_is_temporarily_closed(self) -> None:
        assert _center().temporarily_closed is False
        assert _center(CenterIsOpen="N").temporarily_closed is True
        assert _center(CenterIsOpen="").temporarily_closed is None

    def test_labels_the_center_type_without_flattening_it(self) -> None:
        assert _center().is_comprehensive is False
        assert _center(ProgramType=COMPREHENSIVE).is_comprehensive is True
        # An unlabeled center is not an affiliate; it is a center nobody classified.
        assert _center(ProgramType="").is_comprehensive is None

    def test_validates_the_website_rather_than_trusting_it(self) -> None:
        # Same reasoning as the provider links: a third-party string in an href is a script
        # injection sink, and this one is on the page telling somebody where to go.
        assert _center(WebSiteUrl="javascript:alert(1)").website is None
        assert _center(WebSiteUrl="example.org/ajcc").website == "https://example.org/ajcc"
        assert _center(WebSiteUrl="").website is None

    def test_a_zero_coordinate_is_missing_rather_than_the_gulf_of_guinea(self) -> None:
        # 0,0 is the null island. Kept as a number it would place a Sacramento office in the
        # Atlantic and make it the "nearest" center to nothing at all.
        assert _center(Latitude=0, Longitude=0).lat is None
        assert _center(Latitude="", Longitude="").lon is None

    def test_deduplicates_services_and_drops_blanks(self) -> None:
        assert _center().worker_services == ("Getting Skills and Education", "Finding Work")

    def test_a_null_service_list_is_an_empty_tuple(self) -> None:
        assert _center(YouthServices=None).youth_services == ()

    def test_a_record_with_no_name_or_id_is_dropped(self) -> None:
        # Not a place this site can send anyone, so it must not become a blank card.
        assert parse_center({**RECORD, "Name": " "}) is None
        assert parse_center({**RECORD, "ID": ""}) is None

    def test_parses_a_whole_payload_and_survives_a_junk_row(self) -> None:
        payload = {"OneStopCenterList": [RECORD, {"Name": "nameless"}, "not a dict"]}
        assert len(parse_centers(payload)) == 1

    def test_an_absent_list_is_empty_rather_than_an_error(self) -> None:
        assert parse_centers({}) == ()
        assert parse_centers({"OneStopCenterList": None}) == ()

    def test_serializes_nulls_faithfully(self) -> None:
        payload = _center(GeneralEmail="", VeteranRep="").as_dict()
        assert payload["email"] is None
        assert payload["veterans_representative"] is None
        assert payload["is_comprehensive"] is False


class TestDistance:
    def test_matches_the_apis_own_figure(self) -> None:
        """Cross-check against CareerOneStop's distance for the same pair.

        The finder reported 42.3 miles from Coalinga (93210) to the Mendota center; this
        computes 42.2 from the coordinates in the same response. Agreeing to a tenth of a
        mile is what licenses ranking locally instead of asking the endpoint 227 times.
        """
        miles = distance_miles(36.1397, -120.3603, 36.7538, -120.3813)
        assert 42.0 < miles < 42.5

    def test_is_zero_for_the_same_point(self) -> None:
        assert distance_miles(38.5, -121.4, 38.5, -121.4) == pytest.approx(0.0)


class TestNearestCenters:
    CENTERS = (
        _built("far", 38.0, -121.0),
        _built("near", 38.55, -121.47),
        _built("middling", 38.3, -121.2, center_type="Affiliate Center"),
    )

    def test_orders_by_distance(self) -> None:
        found = nearest_centers(self.CENTERS, 38.556, -121.472, limit=3)
        assert [n.center.name for n in found] == ["near", "middling", "far"]

    def test_respects_the_limit_and_the_radius(self) -> None:
        assert len(nearest_centers(self.CENTERS, 38.556, -121.472, limit=1)) == 1
        found = nearest_centers(self.CENTERS, 38.556, -121.472, limit=5, within_miles=5)
        assert [n.center.name for n in found] == ["near"]

    def test_can_ask_for_comprehensive_centers_only(self) -> None:
        found = nearest_centers(self.CENTERS, 38.556, -121.472, limit=5, comprehensive_only=True)
        assert [n.center.name for n in found] == ["near", "far"]

    def test_a_center_without_coordinates_is_excluded_not_ranked_as_zero_miles(self) -> None:
        """The failure this guards against puts an unplaceable center top of the list.

        Treating a missing coordinate as 0 would make it the nearest thing to everywhere,
        which is the same unknown-as-zero error the outcome data is protected from.
        """
        centers = (*self.CENTERS, _built("unplaceable", None, None))
        found = nearest_centers(centers, 38.556, -121.472, limit=10)
        assert "unplaceable" not in [n.center.name for n in found]
        assert all(n.miles is not None for n in found)

    def test_returns_nothing_rather_than_a_guess_when_nothing_is_placeable(self) -> None:
        assert nearest_centers((_built("unplaceable", None, None),), 38.5, -121.4) == ()


class TestCoverage:
    CENTERS = (_built("sacramento", 38.55, -121.47), _built("stockton", 37.95, -121.29))

    def test_counts_places_within_each_band(self) -> None:
        places = (Place("Sacramento", 38.56, -121.47), Place("Redding", 40.58, -122.39))
        coverage = measure_coverage(self.CENTERS, places, bands=(10.0, 200.0))
        assert [(b.miles, b.with_any_center) for b in coverage.bands] == [(10.0, 1), (200.0, 2)]

    def test_an_unlocatable_place_is_not_counted_as_uncovered(self) -> None:
        """It was never measured, which is a different fact from being badly served."""
        places = (Place("Sacramento", 38.56, -121.47), Place("Nowhere", None, None))
        coverage = measure_coverage(self.CENTERS, places)
        assert coverage.places_total == 2
        assert coverage.places_located == 1

    def test_median_is_null_rather_than_zero_when_nothing_could_be_measured(self) -> None:
        coverage = measure_coverage(self.CENTERS, (Place("Nowhere", None, None),))
        assert coverage.median_miles is None
        assert coverage.farthest == ()

    def test_reports_how_many_centers_could_be_placed(self) -> None:
        centers = (*self.CENTERS, _built("unplaceable", None, None))
        coverage = measure_coverage(centers, (Place("Sacramento", 38.56, -121.47),))
        assert coverage.centers_total == 3
        assert coverage.centers_located == 2

    def test_names_the_worst_served_places_worst_first(self) -> None:
        places = (
            Place("Sacramento", 38.56, -121.47),
            Place("Redding", 40.58, -122.39),
            Place("Stockton", 37.95, -121.29),
        )
        coverage = measure_coverage(self.CENTERS, places, farthest=2)
        assert [name for name, _ in coverage.farthest] == ["Redding", "Sacramento"]

    def test_serializes_without_inventing_numbers(self) -> None:
        payload = measure_coverage(self.CENTERS, (Place("Nowhere", None, None),)).as_dict()
        assert payload["median_miles"] is None
        assert payload["farthest"] == []


class TestPlacesFromPrograms:
    def test_one_place_per_city_keeping_the_first_coordinates(self) -> None:
        programs = [
            {"location": {"city": "Fresno", "lat": 36.7, "lon": -119.8}},
            {"location": {"city": "Fresno", "lat": 36.9, "lon": -119.9}},
            {"location": {"city": "Chico", "lat": 39.7, "lon": -121.8}},
        ]
        places = places_from_programs(programs)
        assert [p.name for p in places] == ["Fresno", "Chico"]
        assert places[0].lat == 36.7

    def test_a_program_with_no_city_is_skipped_rather_than_grouped_under_a_blank(self) -> None:
        assert places_from_programs([{"location": {"city": None}}, {}]) == ()

    def test_a_city_with_no_coordinates_is_kept_as_unlocated(self) -> None:
        # Dropping it would quietly shrink the denominator and flatter the coverage figure.
        places = places_from_programs([{"location": {"city": "Nowhere", "lat": "", "lon": ""}}])
        assert places[0].name == "Nowhere"
        assert places[0].lat is None


class _StubClient(httpx.Client):
    """An httpx client answering from a canned map, recording what it was asked for.

    Records the *raw* path rather than the decoded one, because half of what these tests
    check is whether a place name was percent-encoded before it became route segments.
    ``url.path`` decodes it back and would let an unescaped comma pass.
    """

    def __init__(self, responses: dict[str, dict[str, Any]]) -> None:
        self.requested: list[str] = []

        def handle(request: httpx.Request) -> httpx.Response:
            self.requested.append(request.url.raw_path.decode("ascii"))
            body = responses.get(request.url.path)
            if body is None:
                return httpx.Response(404, json={"error": "not found"})
            return httpx.Response(200, json=body)

        super().__init__(transport=httpx.MockTransport(handle))


STATE_PATH = "/v1/ajcfinder/user/CA/25/0/0/0/0/0/0/0/500"


@pytest.fixture
def _credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(USER_ID_ENV, "user")
    monkeypatch.setenv(TOKEN_ENV, "token")
    monkeypatch.setattr("camino.sources.local_help.time.sleep", lambda _: None)


class TestFetchWithoutCredentials:
    def test_returns_none_and_makes_no_request(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CI has no credentials and must still build."""
        monkeypatch.delenv(USER_ID_ENV, raising=False)
        monkeypatch.delenv(TOKEN_ENV, raising=False)

        def explode(*args: object, **kwargs: object) -> None:
            raise AssertionError("attempted a request without credentials")

        monkeypatch.setattr(httpx.Client, "get", explode)
        assert fetch_centers("CA") is None
        assert fetch_centers_near("95814") is None


@pytest.mark.usefixtures("_credentials")
class TestFetchCenters:
    def test_sends_every_route_segment(self) -> None:
        """The regression this endpoint deserves a test for.

        The finder's route is positional and takes eleven segments. A probe of
        ``/v1/ajcfinder/{user}/{zip}`` answers 404 because no route matches, which reads as
        "there is no such endpoint" and is why this API was written off as unreachable. If
        the segment list is ever shortened, that misdiagnosis happens again.
        """
        with _StubClient({STATE_PATH: PAYLOAD}) as client:
            fetch_centers("CA", client=client)
        assert client.requested == [STATE_PATH]
        # v1 / ajcfinder / userId, then the ten positional arguments the route requires.
        assert len(STATE_PATH.strip("/").split("/")) == 13

    def test_returns_parsed_centers(self) -> None:
        with _StubClient({STATE_PATH: PAYLOAD}) as client:
            centers = fetch_centers("CA", client=client)
        assert centers is not None
        assert [c.name for c in centers] == ["Asian Resources, Inc. (ARI) AJCC"]

    def test_an_unreachable_endpoint_is_none_rather_than_an_exception(self) -> None:
        # A page that cannot name the nearest job center is a page missing a section. A
        # build that dies because a federal endpoint blinked helps nobody.
        with _StubClient({}) as client:
            assert fetch_centers("CA", client=client) is None

    def test_an_empty_answer_is_distinct_from_an_unreachable_one(self) -> None:
        """ "We could not check" is not "California has no job centers"."""
        with _StubClient({STATE_PATH: {"OneStopCenterList": []}}) as client:
            assert fetch_centers("CA", client=client) == ()

    def test_a_supplied_client_is_left_open_for_its_owner(self) -> None:
        with _StubClient({STATE_PATH: PAYLOAD}) as client:
            fetch_centers("CA", client=client)
            assert client.is_closed is False


@pytest.mark.usefixtures("_credentials")
class TestFetchCentersNear:
    ZIP_PATH = "/v1/ajcfinder/user/95814/25/0/0/0/0/0/0/0/10"
    CITY_PATH = "/v1/ajcfinder/user/los%20angeles%2C%20ca/25/0/0/0/0/0/0/0/10"

    def test_looks_up_a_zip_code(self) -> None:
        with _StubClient({self.ZIP_PATH: PAYLOAD}) as client:
            found = fetch_centers_near("95814", client=client)
        assert found is not None
        assert found[0].miles == 1.9

    def test_percent_encodes_a_city_and_state(self) -> None:
        # The space and comma are data, not route separators. Passing them raw would let a
        # place name change which endpoint is called.
        with _StubClient({self.CITY_PATH: PAYLOAD}) as client:
            fetch_centers_near("los angeles, ca", client=client)
        assert client.requested == [self.CITY_PATH]

    def test_a_blank_distance_is_null_not_zero(self) -> None:
        payload = {"OneStopCenterList": [{**RECORD, "Distance": ""}]}
        with _StubClient({self.ZIP_PATH: payload}) as client:
            found = fetch_centers_near("95814", client=client)
        assert found is not None
        assert found[0].miles is None


@pytest.mark.usefixtures("_credentials")
class TestCache:
    def test_a_cached_response_is_reused_without_a_request(self, tmp_path: Path) -> None:
        envelope = cache_envelope(PAYLOAD, location="CA", radius=25, limit=500)
        (tmp_path / "ajc-ca-25.json").write_text(json.dumps(envelope), encoding="utf-8")
        with _StubClient({}) as client:
            centers = fetch_centers("CA", client=client, cache_dir=tmp_path)
            assert client.requested == []
        assert centers is not None
        assert len(centers) == 1

    def test_an_entry_fetched_with_a_narrower_request_is_not_reused(self, tmp_path: Path) -> None:
        """A truncated earlier read is not a smaller version of the current answer.

        Serving one would publish "the nearest center is 40 miles away" when the truth is
        that the nearer ones were never asked for.
        """
        envelope = cache_envelope(PAYLOAD, location="CA", radius=25, limit=10)
        (tmp_path / "ajc-ca-25.json").write_text(json.dumps(envelope), encoding="utf-8")
        with _StubClient({STATE_PATH: PAYLOAD}) as client:
            fetch_centers("CA", client=client, cache_dir=tmp_path)
            assert client.requested == [STATE_PATH]

    def test_an_entry_with_no_record_of_its_request_is_not_reused(self, tmp_path: Path) -> None:
        (tmp_path / "ajc-ca-25.json").write_text(json.dumps(PAYLOAD), encoding="utf-8")
        with _StubClient({STATE_PATH: PAYLOAD}) as client:
            fetch_centers("CA", client=client, cache_dir=tmp_path)
            assert client.requested == [STATE_PATH]

    def test_a_corrupt_entry_is_ignored_rather_than_fatal(self, tmp_path: Path) -> None:
        (tmp_path / "ajc-ca-25.json").write_text("{not json", encoding="utf-8")
        with _StubClient({STATE_PATH: PAYLOAD}) as client:
            assert fetch_centers("CA", client=client, cache_dir=tmp_path) is not None

    def test_the_credential_never_reaches_the_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(USER_ID_ENV, "secret-user")
        monkeypatch.setenv(TOKEN_ENV, "secret-token")
        path = "/v1/ajcfinder/secret-user/CA/25/0/0/0/0/0/0/0/500"
        with _StubClient({path: PAYLOAD}) as client:
            fetch_centers("CA", client=client, cache_dir=tmp_path)
        written = (tmp_path / "ajc-ca-25.json").read_text(encoding="utf-8")
        assert "secret-user" not in written
        assert "secret-token" not in written


# --------------------------------------------------------------------------------------
# The wording
#
# Everything below asserts something about English sentences rather than about data. That
# is unusual for a test suite and deliberate here: these sentences are the part of this
# feature that can hurt somebody, and a reviewer changing them should have to change a test
# that says why the old wording was the way it was.
# --------------------------------------------------------------------------------------

PROMISES = (
    "you qualify",
    "you are eligible",
    "you will be eligible",
    "guarantee",
    "guaranteed",
    "we will pay",
    "we can pay",
    "we'll pay",
    "free training",
    "at no cost to you",
    "apply here",
    "get funded",
    "you will receive",
)
"""Phrasings that turn a description of a public program into a promise to one reader.

Not an exhaustive filter and not meant to be. It is a tripwire: anyone adding a sentence
that trips it has to come here and argue for it, which is the point.

Matched inside negations too, and that is deliberate rather than a limitation. California's
own guidance says training "does not mean that they are guaranteed services" — true, useful,
and still the wrong sentence to publish, because a reader skimming official-looking prose
takes the word and drops the "not", and a negation is the first thing to be lost in
translation. The module says the same thing without the word. It has already caught that
once.
"""


def _published_strings() -> list[str]:
    guidance = funding_guidance()
    strings = [guidance.who_decides, ETPL_SNAPSHOT_CAVEAT, etpl_listing_note("2026-08-04")]
    for step in guidance.steps:
        strings += [step.heading, step.detail]
    for question in guidance.questions:
        strings += [question.ask, question.because]
    return strings


class TestWording:
    def test_nothing_published_promises_anyone_funding(self) -> None:
        offences = [
            (text, phrase)
            for text in _published_strings()
            for phrase in PROMISES
            if phrase in text.casefold()
        ]
        assert offences == []

    def test_the_disclaimer_says_who_actually_decides(self) -> None:
        lowered = WHO_DECIDES.casefold()
        assert "local workforce development board" in lowered
        assert "not by this site" in lowered

    def test_the_steps_cannot_be_obtained_without_the_disclaimer(self) -> None:
        """The one structural guarantee in this module.

        Three module constants would let a template render the steps and forget the
        sentence explaining that this site does not decide. A field cannot be forgotten.
        """
        guidance = funding_guidance()
        assert guidance.who_decides == WHO_DECIDES
        assert guidance.steps
        assert "who_decides" in guidance.as_dict()

    def test_the_etpl_note_is_a_claim_about_a_moment_not_about_today(self) -> None:
        note = etpl_listing_note("2026-08-04")
        assert "2026-08-04" in note
        assert "can lapse" in note
        assert "may not be listed today" in note

    def test_the_etpl_note_says_the_list_is_what_makes_funding_possible(self) -> None:
        assert "Individual Training Account" in etpl_listing_note("2026-08-04")


class TestCitations:
    def test_every_step_cites_something(self) -> None:
        assert all(step.citations for step in STEPS)

    def test_every_question_cites_something(self) -> None:
        assert all(question.citations for question in QUESTIONS)

    def test_every_citation_is_an_https_url_with_a_label(self) -> None:
        for item in (*STEPS, *QUESTIONS):
            for citation in item.citations:
                assert citation.url.startswith("https://"), citation
                assert citation.label.strip(), citation

    def test_citations_survive_serialization(self) -> None:
        payload = funding_guidance().as_dict()
        assert payload["steps"][0]["citations"][0]["url"].startswith("https://")

    def test_questions_are_split_by_who_can_answer_them(self) -> None:
        guidance = funding_guidance()
        for_center = guidance.questions_for("job_center")
        for_provider = guidance.questions_for("provider")
        assert for_center and for_provider
        assert len(for_center) + len(for_provider) == len(guidance.questions)

    def test_the_funding_route_names_the_rule_that_makes_it_real(self) -> None:
        # 20 CFR 680.410 is the load-bearing citation for the whole feature: an ITA can only
        # pay a provider on the state list, which is the list every program here came from.
        urls = {c.url for step in STEPS for c in step.citations}
        assert any("680.410" in url for url in urls)

    def test_the_local_variation_is_cited_rather_than_asserted(self) -> None:
        detail = " ".join(step.detail for step in STEPS)
        assert "45 local workforce development areas" in detail
