"""The next step: America's Job Centers, and the funding route that may pay for a program.

Source D6 in PROVENANCE.md -- the same CareerOneStop Web API and the same credentials as
:mod:`camino.sources.careeronestop`, a different endpoint. This module exists because the
site currently ends a program page with a link to the provider's own website and nothing
else, and for 334 programs that link is dead. A person who has just read what a program
costs and what happened to the people who took it is then on their own.

Every program this project publishes was on California's Eligible Training Provider List
when the state last reported it to the U.S. Department of Labor, because that list *is* what
the ETA-9171 report describes. Under 20 CFR 680.410 an eligible training provider is "the
only type of entity that receives funding for training services ... through an individual
training account", and it "[m]ust be included on the State list of eligible training
providers and programs". So for every program here there is a route by which somebody else
may pay for it, and the site has never mentioned it.

Three rules govern everything below, and they are the reason this module is shaped the way
it is rather than being a paragraph of copy in the web app.

**This site does not determine eligibility, and must never appear to.** The determination is
made by a one-stop center after an interview, evaluation or assessment and career planning
(20 CFR 680.220), against a local priority system the Governor and 45 separate Local
Workforce Development Boards set (20 CFR 680.600). Getting this wrong sends someone to an
office expecting money they may not get. :func:`funding_guidance` therefore cannot hand a
caller the steps without :data:`WHO_DECIDES` attached -- the disclaimer is a field of the
returned value, not a separate constant a template may forget.

**Every claim carries its citation in the data, not in a comment.** :class:`Step` and
:class:`Question` each hold the eCFR or state URL the claim came from, so the pipeline can
emit the source alongside the sentence and a reader can check it. A claim about public
money that cannot name its source does not belong on the page.

**One request for the whole state, not one per city.** CareerOneStop's finder will answer a
per-ZIP query, and :func:`fetch_centers_near` does that for ad-hoc use, but a build wanting
centers for 227 cities should call :func:`fetch_centers` once and rank locally with
:func:`nearest_centers`. California has 183 centers; sweeping them into memory once and
doing arithmetic here is both kinder to a public endpoint and more complete than 227
radius-limited searches stitched together.

The per-center detail endpoint (``/ajcfinder/{user}/{id}``) is deliberately not used. It
carries a "Language Capability" field that would matter a great deal to this project's
Spanish-speaking readers, but in a ten-center sample nine were blank -- and a blank rendered
as "languages: none" is exactly the unknown-as-absent error the rest of this codebase exists
to prevent. 183 extra requests to publish one field that is usually missing, and misleading
when it is, is not a trade worth making.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal
from urllib.parse import quote

import httpx

from camino.sources.careeronestop import BASE_URL, build_client, credentials
from camino.sources.dol_etp import FetchError, clean_text, clean_url, get_with_retry

REQUEST_TIMEOUT = 45.0
PAUSE_BETWEEN_CALLS = 0.3
"""Same throttle as the occupation client. This is a public service, not a firehose."""

STATEWIDE_RADIUS_MILES = 25
"""Radius sent with a statewide query.

The finder requires the parameter even when the location is a bare state code, and in that
case it does not appear to constrain the result: ``CA`` at radius 25 returns every center
CareerOneStop holds for California, and every center returned by border-ZIP searches that is
in California is already in it.
"""

MAX_RECORDS = 500
"""Page size for a statewide read. California returns 183; this leaves room to grow."""

CACHE_FORMAT: Final = 1
"""Bumped when the envelope's shape changes, so a stale entry misses rather than misleads."""

_UNFILTERED = "0"
"""The finder's "no filter" sentinel, used for every service and sort parameter.

Filtering server-side would silently drop centers whose service list is merely unpopulated,
which is a claim about a center that the absence of data does not support.
"""

EARTH_RADIUS_MILES = 3958.7613

COMPREHENSIVE = "Comprehensive Center"
"""A center where all required one-stop partner programs are accessible (20 CFR 678.305).

Worth distinguishing from an affiliate site, which "does not need to provide access to every
required one-stop partner program" (20 CFR 678.310(a)). A person going in to ask about
training money is more likely to find the right desk at a comprehensive center, and both are
real answers to "where do I go", so both are published and the type is labeled.
"""


# --------------------------------------------------------------------------------------
# Citations
#
# A sentence about who might pay for someone's training is only publishable if a reader can
# check it. These travel with the claims rather than living in a doc, so the pipeline emits
# them together and neither can be edited without the other being visible in the diff.
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Citation:
    """One authority for one claim."""

    label: str
    url: str

    def as_dict(self) -> dict[str, str]:
        return {"label": self.label, "url": self.url}


_ECFR = "https://www.ecfr.gov/current"
"""eCFR's own short canonical path prefix, taken from the section metadata its API returns.

Note for anyone verifying these links from a script rather than a browser: eCFR redirects
automated clients to an interstitial, so a link checker will report every one of them as a
redirect. They resolve for a human reader, which is who they are for.
"""


def _cfr(section: str, title: str) -> Citation:
    """An eCFR citation for one section of title 20."""
    return Citation(label=f"20 CFR {section} — {title}", url=f"{_ECFR}/title-20/section-{section}")


CFR_TRAINING_ELIGIBILITY = _cfr("680.210", "Who may receive training services?")
CFR_CAREER_SERVICES_FIRST = _cfr(
    "680.220", "Are there particular career services an individual must receive before training?"
)
CFR_OTHER_GRANT_SOURCES = _cfr("680.230", "Coordination of WIOA training funds and other grants")
CFR_ITA = _cfr("680.300", "How are training services provided?")
CFR_ITA_LIMITS = _cfr("680.310", "Can the duration and amount of ITAs be limited?")
CFR_CONSUMER_CHOICE = _cfr("680.340", "What are the requirements for consumer choice?")
CFR_ELIGIBLE_PROVIDER = _cfr("680.410", "What is an eligible training provider?")
CFR_PROGRAM_OF_TRAINING = _cfr("680.420", "What is a “program of training services”?")
CFR_PROVIDER_INFORMATION = _cfr("680.490", "Performance and cost information providers submit")
CFR_OUT_OF_AREA = _cfr("680.520", "May individuals choose providers outside the local area?")
CFR_ADULT_PRIORITY = _cfr("680.600", "Priority for low-income adults and public assistance")
CFR_DW_PRIORITY = _cfr("680.610", "Does the adult priority also apply to dislocated worker funds?")
CFR_SUPPORTIVE_SERVICES = _cfr("680.900", "What are supportive services for adults?")
CFR_SUPPORTIVE_LIMITS = _cfr("680.910", "When may supportive services be provided?")
CFR_NEEDS_RELATED = _cfr("680.940", "Eligibility for needs-related payments")
CFR_COMPREHENSIVE_CENTER = _cfr("678.305", "What is a comprehensive one-stop center?")
CFR_AFFILIATE_CENTER = _cfr("678.310", "What is an affiliated site?")
CFR_YOUTH_ITA = _cfr("681.550", "Are Individual Training Accounts permitted for youth?")

VETERANS_PRIORITY = Citation(
    label="20 CFR 1010.200 — Priority of service for veterans and eligible spouses",
    url=f"{_ECFR}/title-20/section-1010.200",
)
EDD_ETPL = Citation(
    label="California EDD — Eligible Training Provider List",
    url="https://edd.ca.gov/en/jobs_and_training/Eligible_Training_Provider_List/",
)
EDD_OFFICE_LOCATOR = Citation(
    label="California EDD — Office Locator",
    url="https://edd.ca.gov/en/Office_Locator/",
)
COS_CENTER_FINDER = Citation(
    label="CareerOneStop — American Job Center Finder (U.S. DOL)",
    url="https://www.careeronestop.org/LocalHelp/AmericanJobCenters/find-american-job-centers.aspx",
)
EDD_ELIGIBILITY_GUIDE = Citation(
    label="California EDD — WIOA Title I Eligibility Technical Assistance Guide (WSD24-04)",
    url="https://edd.ca.gov/siteassets/files/jobs_and_training/pubs/wsd24-04att1.docx",
)
"""California's own statement of who is eligible and what local areas must define themselves.

The single most useful state document found for this feature, and the source of the two
things a person most needs to hear: that meeting the criteria does not by itself secure a
service -- see :data:`NOT_AN_ENTITLEMENT` -- and that a great many services do not wait on
work authorization being verified.
"""
EDD_PRIORITY_DIRECTIVE = Citation(
    label="California EDD — Adult Program Priority of Service (WSD24-06)",
    url="https://edd.ca.gov/siteassets/files/jobs_and_training/pubs/wsd24-06.pdf",
)


# --------------------------------------------------------------------------------------
# Centers
# --------------------------------------------------------------------------------------


def _flag(value: Any) -> bool | None:
    """Read the API's Yes/No fields, keeping "not stated" distinct from "no".

    Blank is the common case for these fields and it means nobody filled the box in.
    Publishing that as "No veterans' representative" would tell a veteran not to bother.
    """
    text = clean_text(value)
    if text is None:
        return None
    lowered = text.casefold()
    if lowered in ("y", "yes", "true", "1"):
        return True
    return False if lowered in ("n", "no", "false", "0") else None


def _coordinate(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number == 0 else number


def _service_names(entries: Any) -> tuple[str, ...]:
    if not isinstance(entries, list):
        return ()
    names = [name for entry in entries if (name := clean_text((entry or {}).get("ServiceName")))]
    return tuple(dict.fromkeys(names))


@dataclass(frozen=True)
class AmericanJobCenter:
    """One America's Job Center, as CareerOneStop holds it.

    Contact fields are ``None`` when the record is blank, never an empty string standing in
    for a phone number nobody published. ``center_type`` is the API's own label; it is kept
    verbatim rather than collapsed to a boolean so an unrecognized third value would show up
    as itself instead of silently becoming "affiliate".

    In California these are branded America's Job Center of California (AJCC). The federal
    name is used for the type because the API is federal and serves every state.
    """

    center_id: str
    name: str
    address: tuple[str, ...]
    city: str | None
    state: str | None
    postal_code: str | None
    phone: str | None
    email: str | None
    website: str | None
    hours: str | None
    center_type: str | None
    lat: float | None
    lon: float | None
    veterans_representative: bool | None
    temporarily_closed: bool | None
    closure_note: str | None
    worker_services: tuple[str, ...]
    youth_services: tuple[str, ...]
    last_updated: str | None

    @property
    def is_comprehensive(self) -> bool | None:
        """True for a comprehensive center, False for an affiliate, None when unlabeled."""
        if self.center_type is None:
            return None
        return self.center_type.casefold() == COMPREHENSIVE.casefold()

    @property
    def has_coordinates(self) -> bool:
        return self.lat is not None and self.lon is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.center_id,
            "name": self.name,
            "address": list(self.address),
            "city": self.city,
            "state": self.state,
            "postal_code": self.postal_code,
            "phone": self.phone,
            "email": self.email,
            "website": self.website,
            "hours": self.hours,
            "center_type": self.center_type,
            "is_comprehensive": self.is_comprehensive,
            "lat": self.lat,
            "lon": self.lon,
            "veterans_representative": self.veterans_representative,
            "temporarily_closed": self.temporarily_closed,
            "closure_note": self.closure_note,
            "worker_services": list(self.worker_services),
            "youth_services": list(self.youth_services),
            "last_updated": self.last_updated,
        }


def parse_center(record: dict[str, Any]) -> AmericanJobCenter | None:
    """Build a center from one API record, or None when it cannot be offered to anyone.

    A record with no id or no name is not a place this site can send a person, so it is
    dropped rather than published as a blank card. Everything else survives with nulls.
    """
    center_id = clean_text(record.get("ID"))
    name = clean_text(record.get("Name"))
    if center_id is None or name is None:
        return None
    address = tuple(
        line
        for key in ("Address1", "Address2")
        if (line := clean_text(record.get(key))) is not None
    )
    open_flag = _flag(record.get("CenterIsOpen"))
    return AmericanJobCenter(
        center_id=center_id,
        name=name,
        address=address,
        city=clean_text(record.get("City")),
        state=clean_text(record.get("StateAbbr")),
        postal_code=clean_text(record.get("Zip")),
        phone=clean_text(record.get("Phone")),
        email=clean_text(record.get("GeneralEmail")),
        # Same validation the provider links get: a third-party string in an href is a
        # script-injection sink, and this one is going on a page telling people where to go.
        website=clean_url(record.get("WebSiteUrl")),
        hours=clean_text(record.get("OpenHour")),
        center_type=clean_text(record.get("ProgramType")),
        lat=_coordinate(record.get("Latitude")),
        lon=_coordinate(record.get("Longitude")),
        veterans_representative=_flag(record.get("VeteranRep")),
        temporarily_closed=None if open_flag is None else not open_flag,
        closure_note=clean_text(record.get("WhyClosed")),
        worker_services=_service_names(record.get("WorkersServices")),
        youth_services=_service_names(record.get("YouthServices")),
        last_updated=clean_text(record.get("LastUpdated")),
    )


def parse_centers(payload: dict[str, Any]) -> tuple[AmericanJobCenter, ...]:
    records = payload.get("OneStopCenterList")
    if not isinstance(records, list):
        return ()
    parsed = [parse_center(r) for r in records if isinstance(r, dict)]
    return tuple(c for c in parsed if c is not None)


@dataclass(frozen=True)
class NearbyCenter:
    """A center and how far it is from the place that was asked about.

    ``miles`` is ``None`` when the distance is not known -- a center with no published
    coordinates, or a search result whose distance field was blank. It is never 0 as a
    stand-in for that: 0 miles means the center is at the address asked about, which for a
    training provider co-located with a job center is a real and useful answer.
    """

    center: AmericanJobCenter
    miles: float | None

    def as_dict(self) -> dict[str, Any]:
        return {"miles": self.miles, **self.center.as_dict()}


def distance_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in statute miles.

    Straight-line, not driving distance, and the difference matters most in exactly the
    places where the nearest center is far away. Anything presenting this to a reader should
    say "about", or say nothing and just order the list.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    haversine = (
        math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(haversine))


def nearest_centers(
    centers: Sequence[AmericanJobCenter],
    lat: float,
    lon: float,
    *,
    limit: int = 3,
    within_miles: float | None = None,
    comprehensive_only: bool = False,
) -> tuple[NearbyCenter, ...]:
    """The closest centers to a point, nearest first.

    Centers with no published coordinates are excluded rather than sorted to the end: this
    function's whole output is a distance claim, and a center that cannot be placed cannot
    honestly be ranked against one that can. Nothing in the current California data is
    affected -- all 183 carry coordinates -- but a future record without them must not turn
    into a "0 miles away" entry at the top of the list.
    """
    ranked: list[NearbyCenter] = []
    for center in centers:
        if comprehensive_only and center.is_comprehensive is not True:
            continue
        if center.lat is None or center.lon is None:
            continue
        miles = distance_miles(lat, lon, center.lat, center.lon)
        if within_miles is not None and miles > within_miles:
            continue
        ranked.append(NearbyCenter(center=center, miles=miles))
    ranked.sort(key=lambda n: (n.miles if n.miles is not None else math.inf, n.center.name))
    return tuple(ranked[:limit])


# --------------------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------------------


def _finder_path(user_id: str, location: str, radius: int, limit: int) -> str:
    """The finder's positional route.

    Every segment is required. Omitting the trailing filter and paging segments is why a
    probe of ``/v1/ajcfinder/{user}/{zip}`` answers 404: the route simply does not match,
    which reads as "no such endpoint" rather than "wrong number of arguments".
    """
    segments = (
        quote(location, safe=""),
        str(radius),
        _UNFILTERED,  # centerType
        _UNFILTERED,  # youthServices
        _UNFILTERED,  # workersServices
        _UNFILTERED,  # businessServices
        _UNFILTERED,  # sortColumns
        _UNFILTERED,  # sortDirections
        "0",  # startRecord
        str(limit),
    )
    return f"{BASE_URL}/ajcfinder/{user_id}/{'/'.join(segments)}"


def cache_envelope(
    payload: dict[str, Any], *, location: str, radius: int, limit: int
) -> dict[str, Any]:
    """Wrap a response in the record of the request that produced it.

    Public for the same reason as the occupation client's: anything writing an entry by hand
    has to write one this module will accept, and restating the shape is how the two drift.
    """
    return {
        "cache_format": CACHE_FORMAT,
        "request": {"location": location, "radius": radius, "limit": limit},
        "response": payload,
    }


def _cache_path(cache_dir: Path | None, location: str, radius: int) -> Path | None:
    if cache_dir is None:
        return None
    safe = "".join(ch if ch.isalnum() else "-" for ch in location).strip("-").casefold()
    return cache_dir / f"ajc-{safe or 'all'}-{radius}.json"


def _read_cache(
    cache_dir: Path | None, location: str, radius: int, limit: int
) -> dict[str, Any] | None:
    """A cached response, but only one fetched with exactly this request.

    A narrower earlier read is not a smaller version of the current answer; it is a
    truncated one, and serving it would publish "the nearest center is 40 miles away" when
    the truth is that the nearer ones were never asked for.
    """
    path = _cache_path(cache_dir, location, radius)
    if path is None or not path.exists():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(loaded, dict) or loaded.get("cache_format") != CACHE_FORMAT:
        return None
    request = loaded.get("request")
    if not isinstance(request, dict):
        return None
    if (request.get("location"), request.get("radius"), request.get("limit")) != (
        location,
        radius,
        limit,
    ):
        return None
    response = loaded.get("response")
    return response if isinstance(response, dict) else None


def _write_cache(
    cache_dir: Path | None, location: str, radius: int, limit: int, payload: dict[str, Any]
) -> None:
    path = _cache_path(cache_dir, location, radius)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    envelope = cache_envelope(payload, location=location, radius=radius, limit=limit)
    path.write_text(json.dumps(envelope), encoding="utf-8")


def _fetch_payload(
    location: str,
    *,
    radius: int,
    limit: int,
    user_id: str,
    http: httpx.Client,
    cache_dir: Path | None,
) -> dict[str, Any] | None:
    cached = _read_cache(cache_dir, location, radius, limit)
    if cached is not None:
        return cached
    try:
        response = get_with_retry(http, _finder_path(user_id, location, radius, limit))
    except FetchError as exc:
        # Never fatal. A page that cannot name the nearest job center is a page missing a
        # section; a build that dies because a federal endpoint blinked helps nobody.
        print(f"local_help: centers for {location!r} unavailable ({exc})")
        return None
    payload: dict[str, Any] = response.json()
    _write_cache(cache_dir, location, radius, limit, payload)
    time.sleep(PAUSE_BETWEEN_CALLS)
    return payload


def fetch_centers(
    state: str = "CA",
    *,
    client: httpx.Client | None = None,
    cache_dir: Path | None = None,
) -> tuple[AmericanJobCenter, ...] | None:
    """Every America's Job Center CareerOneStop holds for ``state``, in one request.

    Returns ``None`` when no credentials are configured or the endpoint could not be read,
    and an empty tuple when the endpoint answered and held nothing. The two are different
    facts and a caller renders them differently: "we could not check" is not "there are no
    job centers in California".
    """
    creds = credentials()
    if creds is None:
        return None
    user_id, token = creds

    owns_client = client is None
    http = client or build_client(token)
    try:
        payload = _fetch_payload(
            state,
            radius=STATEWIDE_RADIUS_MILES,
            limit=MAX_RECORDS,
            user_id=user_id,
            http=http,
            cache_dir=cache_dir,
        )
        return None if payload is None else parse_centers(payload)
    finally:
        if owns_client:
            http.close()


def fetch_centers_near(
    location: str,
    *,
    radius_miles: int = 25,
    limit: int = 10,
    client: httpx.Client | None = None,
    cache_dir: Path | None = None,
) -> tuple[NearbyCenter, ...] | None:
    """Centers near a ZIP code or ``"city, ST"``, with the distance the API computed.

    For one-off lookups. A build covering many places should call :func:`fetch_centers` once
    and use :func:`nearest_centers`, which costs the endpoint a single request instead of one
    per place.

    A border search returns out-of-state centers, and that is correct rather than a bug: the
    nearest job center to Blythe is in Arizona. It is not the nearest center that can open a
    California Individual Training Account, though, so a caller publishing these for a
    Californian should filter on :attr:`AmericanJobCenter.state`.
    """
    creds = credentials()
    if creds is None:
        return None
    user_id, token = creds

    owns_client = client is None
    http = client or build_client(token)
    try:
        payload = _fetch_payload(
            location,
            radius=radius_miles,
            limit=limit,
            user_id=user_id,
            http=http,
            cache_dir=cache_dir,
        )
        if payload is None:
            return None
        records = payload.get("OneStopCenterList")
        distances = {}
        if isinstance(records, list):
            for record in records:
                if isinstance(record, dict) and (rid := clean_text(record.get("ID"))):
                    distances[rid] = _distance_field(record.get("Distance"))
        return tuple(
            NearbyCenter(center=c, miles=distances.get(c.center_id)) for c in parse_centers(payload)
        )
    finally:
        if owns_client:
            http.close()


def _distance_field(value: Any) -> float | None:
    """The API's ``Distance``, which is a string and is blank on a statewide read."""
    text = clean_text(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


# --------------------------------------------------------------------------------------
# Coverage
#
# "There is a job center near you" is a claim, and this project does not publish claims it
# has not measured. This measures it against the places programs actually are.
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Place:
    """Somewhere a person might be looking from. ``lat``/``lon`` may be unknown."""

    name: str
    lat: float | None
    lon: float | None


@dataclass(frozen=True)
class CoverageBand:
    """How many places have a center within ``miles``."""

    miles: float
    with_any_center: int
    with_comprehensive_center: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "miles": self.miles,
            "with_any_center": self.with_any_center,
            "with_comprehensive_center": self.with_comprehensive_center,
        }


@dataclass(frozen=True)
class Coverage:
    """What fraction of places can be told where to go, and how far away it is.

    ``places_located`` is the denominator every band should be read against: a place with no
    coordinates was not found to be uncovered, it was never measured. ``median_miles`` and
    ``farthest`` are ``None`` and empty when nothing could be measured at all, rather than 0
    and a fabricated list.
    """

    places_total: int
    places_located: int
    centers_total: int
    centers_located: int
    bands: tuple[CoverageBand, ...]
    median_miles: float | None
    farthest: tuple[tuple[str, float], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "places_total": self.places_total,
            "places_located": self.places_located,
            "centers_total": self.centers_total,
            "centers_located": self.centers_located,
            "bands": [band.as_dict() for band in self.bands],
            "median_miles": self.median_miles,
            "farthest": [{"place": name, "miles": miles} for name, miles in self.farthest],
        }


DEFAULT_BANDS: Final[tuple[float, ...]] = (10.0, 25.0, 50.0)


def measure_coverage(
    centers: Sequence[AmericanJobCenter],
    places: Sequence[Place],
    *,
    bands: Sequence[float] = DEFAULT_BANDS,
    farthest: int = 8,
) -> Coverage:
    """Measure how close the nearest center is to each place.

    Distances are straight-line, so this is an upper bound on how well served somewhere is,
    not a lower one. It is still the right measurement for the question being asked -- "can
    this site name a real office for this person at all" -- and it is reported rather than
    asserted so a reader can see the places where the answer is "barely".
    """
    located = [(p.name, p.lat, p.lon) for p in places if p.lat is not None and p.lon is not None]
    nearest_any: list[tuple[str, float]] = []
    nearest_comprehensive: list[float] = []
    for name, lat, lon in located:
        any_hit = nearest_centers(centers, lat, lon, limit=1)
        comprehensive = nearest_centers(centers, lat, lon, limit=1, comprehensive_only=True)
        if any_hit and any_hit[0].miles is not None:
            nearest_any.append((name, any_hit[0].miles))
        if comprehensive and comprehensive[0].miles is not None:
            nearest_comprehensive.append(comprehensive[0].miles)

    distances = sorted(miles for _, miles in nearest_any)
    return Coverage(
        places_total=len(places),
        places_located=len(located),
        centers_total=len(centers),
        centers_located=sum(1 for c in centers if c.has_coordinates),
        bands=tuple(
            CoverageBand(
                miles=float(band),
                with_any_center=sum(1 for miles in distances if miles <= band),
                with_comprehensive_center=sum(1 for m in nearest_comprehensive if m <= band),
            )
            for band in bands
        ),
        median_miles=_median(distances),
        farthest=tuple(sorted(nearest_any, key=lambda pair: -pair[1])[:farthest]),
    )


def _median(values: Sequence[float]) -> float | None:
    """The median, or None when there is nothing to take a median of. Never 0."""
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def places_from_programs(programs: Sequence[dict[str, Any]]) -> tuple[Place, ...]:
    """One :class:`Place` per distinct city in a program feed.

    Takes the first coordinates seen for a city rather than averaging them: an average of
    two campuses in the same city is a point where neither of them is, and the question here
    is how far a real address is from a real office.
    """
    seen: dict[str, Place] = {}
    for program in programs:
        location = program.get("location") or {}
        city = clean_text(location.get("city"))
        if city is None or city in seen:
            continue
        seen[city] = Place(
            name=city, lat=_coordinate(location.get("lat")), lon=_coordinate(location.get("lon"))
        )
    return tuple(seen.values())


# --------------------------------------------------------------------------------------
# What the site may say
#
# Everything below is content, and it is here rather than in the web app because every
# sentence is a statement about public money that has to keep its citation. A template can
# drop a comment; it cannot drop a field.
# --------------------------------------------------------------------------------------

Audience = Literal["job_center", "provider"]


@dataclass(frozen=True)
class Step:
    """One move a person can actually make, and the rule that says it is real.

    ``step_id`` is a stable name for the claim rather than for the sentence. The site
    publishes these in two languages, and a translation has to be attached to *something*:
    attached to position it silently re-points when a step is inserted, and attached to the
    English text it has to be rewritten whenever a comma moves. The id is what a Spanish
    string is keyed on, so it may be renamed only by someone prepared to re-point the
    translation with it.

    ``on_program_page`` records an editorial decision that belongs here rather than in a
    template: which of these a person should meet without asking for them, on a page they
    reached to read about one program. It is a small set on purpose -- a wall of federal
    procedure at the foot of every page is not read, and the steps left out of it are the
    ones the questions below already carry into the room where they can be answered.
    """

    step_id: str
    heading: str
    detail: str
    citations: tuple[Citation, ...]
    on_program_page: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.step_id,
            "heading": self.heading,
            "detail": self.detail,
            "on_program_page": self.on_program_page,
            "citations": [c.as_dict() for c in self.citations],
        }


@dataclass(frozen=True)
class Question:
    """Something to ask before committing, and what the answer decides.

    ``question_id`` is stable for the same reason :attr:`Step.step_id` is: it is what a
    published translation of this question is keyed on.
    """

    question_id: str
    ask: str
    because: str
    audience: Audience
    citations: tuple[Citation, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.question_id,
            "ask": self.ask,
            "because": self.because,
            "audience": self.audience,
            "citations": [c.as_dict() for c in self.citations],
        }


WHO_DECIDES: Final = (
    "Whether a person can have a program paid for is decided by their local workforce "
    "development board and the America's Job Center staff who interview them — not by this "
    "site, and not by the training provider. California has 45 local workforce development "
    "areas and each sets its own policies, so the answer can differ between two people in "
    "neighboring counties. Nothing here is a promise of funding or a determination of "
    "eligibility."
)
"""The sentence that must accompany any rendering of the steps below.

Not optional and not a footnote. The failure mode this feature has is a person taking a
morning off work, traveling to an office, and being told no — and the difference between
that being a disappointment and being this site's fault is whether it was clear from the
start who decides.
"""

ETPL_SNAPSHOT_CAVEAT: Final = (
    "Listings are renewed periodically and can lapse, so a program listed when the state "
    "last reported may not be listed today. Ask before you rely on it."
)

NOT_AN_ENTITLEMENT: Final = (
    "Meeting every rule here still does not secure a place. California's own guidance to "
    "job center staff says so plainly: WIOA is not an entitlement program, funding for it "
    "is not unlimited, and local boards offer services to eligible applicants when funding "
    "is available."
)
"""Paraphrase of the California TAG's §2.4, which is blunter than anything else found.

Kept as its own constant because it is the sentence a reader is least likely to be told
anywhere else and most likely to need. Every other source describes what someone might get;
this one describes the ceiling.

Deliberately paraphrased rather than quoted. The source sentence is "it does not mean that
they are guaranteed services", and the promissory-language check in the tests refuses the
word "guaranteed" even inside a negation -- correctly, because a reader skimming a block of
official-looking prose sees the word, not the "not", and because a negation is the first
thing to evaporate in translation. Saying the same thing without the word is strictly safer
and costs nothing.
"""


def etpl_listing_note(snapshot_date: str) -> str:
    """What may honestly be said about a program's presence on California's ETPL.

    Takes the snapshot date rather than hard-coding one, because the whole point of the
    sentence is that it is a claim about a moment. The DOL scorecard reports on programs on
    a state's Eligible Training Provider List, so a program in this data was listed as of
    that report — which is not the same as being listed now, and the difference is the part
    a person needs to hear.
    """
    return (
        f"This program was on California's Eligible Training Provider List when the state "
        f"last reported it to the U.S. Department of Labor ({snapshot_date}). Programs on "
        f"that list can be paid for through an Individual Training Account. "
        f"{ETPL_SNAPSHOT_CAVEAT}"
    )


STEPS: Final[tuple[Step, ...]] = (
    Step(
        step_id="ita",
        on_program_page=True,
        heading="Someone else may be able to pay for this",
        detail=(
            "Federal training money under the Workforce Innovation and Opportunity Act is "
            "paid through an Individual Training Account: an agreement between a local "
            "workforce board and a training provider, set up on behalf of one person. That "
            "money can only go to a provider on the state's Eligible Training Provider "
            "List, which is the list every program on this site comes from."
        ),
        citations=(CFR_ITA, CFR_ELIGIBLE_PROVIDER, EDD_ETPL),
    ),
    Step(
        step_id="where_to_ask",
        on_program_page=True,
        heading="The place to ask is an America's Job Center of California",
        detail=(
            "A comprehensive center is where all the required partner programs can be "
            "reached; an affiliate site offers some of them. California's Employment "
            "Development Department directs people to CareerOneStop's finder to locate "
            "one. Contacting a center before traveling is worth it — the state notes that "
            "its own staff are not physically present at every location."
        ),
        citations=(CFR_COMPREHENSIVE_CENTER, CFR_AFFILIATE_CENTER, EDD_OFFICE_LOCATOR),
    ),
    Step(
        step_id="who_can_be_served",
        on_program_page=True,
        heading="Who can be served at all",
        detail=(
            "California states the general criteria as three things: age, Selective Service "
            "registration where it applies, and authorization to work in the United States. "
            "Work authorization is checked when someone moves into a service that needs it, "
            "not at the door — career assessments, an employment plan, case management, "
            "basic skills and English instruction, help finishing work-authorization "
            "paperwork, and referrals for transport, childcare, food and housing are all "
            "listed as services a local area may deliver without verifying it first."
        ),
        citations=(EDD_ELIGIBILITY_GUIDE,),
    ),
    Step(
        step_id="expect_an_interview",
        heading="Expect an interview, not a form",
        detail=(
            "Before anyone can be found eligible for training services they must receive an "
            "interview, evaluation or assessment and career planning, or something else "
            "that gives the center enough information to decide. There is no federally "
            "required waiting period, but there is no way to skip the conversation either — "
            "which is why this site cannot tell anyone whether they qualify."
        ),
        citations=(CFR_CAREER_SERVICES_FIRST, CFR_TRAINING_ELIGIBILITY),
    ),
    Step(
        step_id="what_the_center_decides",
        heading="What the center is deciding",
        detail=(
            "Training services may be made available to adults and dislocated workers whom "
            "the center determines are unlikely or unable to obtain employment leading to "
            "self-sufficiency through career services alone, need training to get there, "
            "and have the skills and qualifications to succeed in it. The program also has "
            "to be linked to employment opportunities in the local area, or somewhere the "
            "person is willing to commute or move to."
        ),
        citations=(CFR_TRAINING_ELIGIBILITY,),
    ),
    Step(
        step_id="say_your_priority_status",
        on_program_page=True,
        heading="Say if you receive public assistance, are low income, or need basic skills help",
        detail=(
            "For the adult funding stream, federal law requires priority to be given to "
            "recipients of public assistance, other low-income individuals, and individuals "
            "who are basic skills deficient. California instructs job center staff to work "
            "an explicit order: veterans and eligible spouses who are also in one of those "
            "groups, then the groups themselves, then other veterans and eligible spouses, "
            "then any populations the Governor or the local board has added, then everyone "
            "else. Priority does not exclude anyone else, and it does not apply to the "
            "dislocated worker stream. It only operates if the center is told, and "
            "California fixes a person's priority status at the moment eligibility is "
            "determined — so it is the first appointment that counts."
        ),
        citations=(
            CFR_ADULT_PRIORITY,
            CFR_DW_PRIORITY,
            VETERANS_PRIORITY,
            EDD_PRIORITY_DIRECTIVE,
        ),
    ),
    Step(
        step_id="other_funding_first",
        heading="Bring what you already have — this money fills a gap",
        detail=(
            "WIOA training funding is limited to people who cannot get grant assistance "
            "from other sources, or who need help beyond what those sources cover. Centers "
            "must consider Pell Grants, state training funds and assistance for needy "
            "families first. Someone can enrol while a Pell application is still pending, "
            "if the center arranges it with the provider in advance."
        ),
        citations=(CFR_OTHER_GRANT_SOURCES,),
    ),
    Step(
        step_id="supportive_services",
        on_program_page=True,
        heading="Ask what else can be covered while you train",
        detail=(
            "Supportive services — help with transport, child care and dependent care, and "
            "others — may be provided to people taking part in career or training services "
            "who cannot obtain them elsewhere. Adults who are unemployed, do not qualify "
            "for unemployment compensation, and are enrolled in training may be eligible "
            "for needs-related payments as well."
        ),
        citations=(CFR_SUPPORTIVE_SERVICES, CFR_SUPPORTIVE_LIMITS, CFR_NEEDS_RELATED),
    ),
    Step(
        step_id="local_and_annual",
        on_program_page=True,
        heading="The answer depends on the local area, and on the year",
        detail=(
            "Once someone has been found eligible and has chosen a provider, the center "
            "must refer them and set up an account — unless the program has exhausted its "
            "training funds for the program year. How much an account is worth, which "
            "occupations a board will fund, what counts as employment that supports a "
            "person, and how priority is applied are all set locally, across California's "
            f"45 local workforce development areas. {NOT_AN_ENTITLEMENT}"
        ),
        citations=(CFR_CONSUMER_CHOICE, CFR_ITA_LIMITS, EDD_ELIGIBILITY_GUIDE, EDD_ETPL),
    ),
)


QUESTIONS: Final[tuple[Question, ...]] = (
    Question(
        question_id="etpl_now",
        ask="Is this program on California's Eligible Training Provider List right now?",
        because=(
            "An Individual Training Account can only pay a provider on that list, and "
            "listings are granted per program rather than per school — a listed provider "
            "can have unlisted programs. Eligibility is also time-limited and renewed."
        ),
        audience="provider",
        citations=(CFR_ELIGIBLE_PROVIDER, EDD_ETPL),
    ),
    Question(
        question_id="full_price",
        ask=(
            "What does the price include, and what will I still have to buy — books, tools, "
            "uniforms, exam fees, license fees?"
        ),
        because=(
            "Providers report tuition and supplies to the state as separate figures and "
            "either can be missing, so the cost shown here may be a floor rather than a "
            "total. Exam and licensing fees are often outside both."
        ),
        audience="provider",
        citations=(CFR_PROVIDER_INFORMATION,),
    ),
    Question(
        question_id="credential",
        ask=(
            "What exactly do I hold at the end, who issues it, and does an employer or a "
            "licensing board recognize it?"
        ),
        because=(
            "A program on the list has to lead to a credential, employment, or measurable "
            "progress toward one — but 'certificate of completion' from a school and a "
            "license a state board recognizes are very different things to be holding."
        ),
        audience="provider",
        citations=(CFR_PROGRAM_OF_TRAINING,),
    ),
    Question(
        question_id="withdrawal",
        ask="If I stop partway through, what do I owe, and what happens to funding already paid?",
        because=(
            "An Individual Training Account is a payment agreement with the provider and "
            "may be paid in instalments, so who is owed what on a withdrawal is a question "
            "for the provider and the center together, before enrolling rather than after."
        ),
        audience="provider",
        citations=(CFR_ITA,),
    ),
    Question(
        question_id="schedule",
        ask="When does the next cohort start, and how many hours a week is it?",
        because=(
            "The schedule decides whether someone can keep working while training, and "
            "needs-related payments are only for people who are unemployed and already "
            "enrolled — so the timetable and the money question are the same question."
        ),
        audience="provider",
        citations=(CFR_NEEDS_RELATED,),
    ),
    Question(
        question_id="funding_stream",
        ask="Which funding stream would I be served under — adult, dislocated worker, or youth?",
        because=(
            "They are different pots with different rules. The statutory priority for "
            "public assistance recipients, low-income individuals and people who are basic "
            "skills deficient applies to adult funds only. Out-of-school youth aged 16 to "
            "24 can be served by Individual Training Accounts from youth funds."
        ),
        audience="job_center",
        citations=(CFR_ADULT_PRIORITY, CFR_DW_PRIORITY, CFR_YOUTH_ITA),
    ),
    Question(
        question_id="local_demand",
        ask="Is this occupation one this local area funds training for?",
        because=(
            "The program has to be linked to employment opportunities in the local area or "
            "one the person will commute to, and boards give priority to credentials "
            "aligned with in-demand sectors. A program can be on the state list and still "
            "not be one a particular board will pay for."
        ),
        audience="job_center",
        citations=(CFR_TRAINING_ELIGIBILITY, CFR_CONSUMER_CHOICE),
    ),
    Question(
        question_id="ita_cap",
        ask=(
            "What is the most this area will put into an Individual Training Account, and "
            "would that cover this program?"
        ),
        because=(
            "Caps and duration limits are local policy, not federal, so the same program "
            "can be fully funded in one county and partly funded in the next. A cap is also "
            "not necessarily the end of it: the rules allow someone to choose training that "
            "costs more than the maximum when other funds are available to make up the "
            "difference. Ask what the gap would be and what could close it."
        ),
        audience="job_center",
        citations=(CFR_ITA_LIMITS, CFR_OTHER_GRANT_SOURCES),
    ),
    Question(
        question_id="self_sufficiency",
        ask="How does this area define employment that supports a person?",
        because=(
            "The determination turns on whether someone can reach self-sufficiency without "
            "training, and California requires each local board to set that threshold "
            "itself — at least the lower living standard income level for the area, and "
            "often higher. It is a local number, and it is the number the decision rests on."
        ),
        audience="job_center",
        citations=(CFR_TRAINING_ELIGIBILITY, EDD_ELIGIBILITY_GUIDE),
    ),
    Question(
        question_id="out_of_area",
        ask="Can I use this for a program in another county, or another state?",
        because=(
            "Training outside the local area is allowed where the program is on the state "
            "list, and outside California where state and local policies permit — both "
            "subject to local procedure. Worth asking anywhere the nearest program is a "
            "long drive, which in this state is a lot of places."
        ),
        audience="job_center",
        citations=(CFR_OUT_OF_AREA,),
    ),
    Question(
        question_id="funds_left",
        ask="Are there training funds left for this program year?",
        because=(
            "The obligation to refer an eligible person and set up an account holds unless "
            "the program has exhausted its training funds for the year. That is the one "
            "answer a website can never know, and it decides everything."
        ),
        audience="job_center",
        citations=(CFR_CONSUMER_CHOICE,),
    ),
    Question(
        question_id="other_grants_first",
        ask="What should I apply for first — a Pell Grant, or anything else?",
        because=(
            "WIOA funds are for people who cannot get grant assistance elsewhere or who "
            "need more than it covers, and centers must consider other sources first. "
            "Enrolling with a Pell application pending is allowed if arranged in advance."
        ),
        audience="job_center",
        citations=(CFR_OTHER_GRANT_SOURCES,),
    ),
    Question(
        question_id="support_costs",
        ask="Can you help with transport, child care, or living costs while I train?",
        because=(
            "Supportive services and needs-related payments are separate from tuition, and "
            "are only available to people already taking part in career or training "
            "services who cannot get that help anywhere else. They are worth asking about "
            "in the same conversation, not a later one."
        ),
        audience="job_center",
        citations=(CFR_SUPPORTIVE_SERVICES, CFR_NEEDS_RELATED),
    ),
    Question(
        question_id="what_to_bring",
        ask="What should I bring, and how long does a determination take?",
        because=(
            "The determination rests on an interview, evaluation or assessment and career "
            "planning, and the center has to be able to document it. There is no federal "
            "minimum waiting period, so the answer is local and worth knowing before "
            "taking a day off work."
        ),
        audience="job_center",
        citations=(CFR_CAREER_SERVICES_FIRST,),
    ),
)


@dataclass(frozen=True)
class FundingGuidance:
    """The funding route, its questions, and the disclaimer that must travel with them.

    A single value rather than three module constants so that a consumer cannot render the
    steps having forgotten :attr:`who_decides`. Every claim about who might pay for
    somebody's training has to arrive attached to the statement that this site is not the
    one deciding.
    """

    who_decides: str
    steps: tuple[Step, ...]
    questions: tuple[Question, ...]
    finders: tuple[Citation, ...]
    """Where a reader goes when this project cannot name an office for them.

    Carried here rather than written into a template because two of the obvious candidates
    do not resolve at all -- ``etpl.edd.ca.gov`` and ``americasjobcenter.ca.gov`` are both
    dead in DNS -- and a page whose purpose is to replace a dead link must not add one. These
    three were checked, and this is the only place they are written down.
    """

    def questions_for(self, audience: Audience) -> tuple[Question, ...]:
        return tuple(q for q in self.questions if q.audience == audience)

    def steps_for_program_page(self) -> tuple[Step, ...]:
        """The steps meant to be read without being asked for, in their published order."""
        return tuple(step for step in self.steps if step.on_program_page)

    def as_dict(self) -> dict[str, Any]:
        return {
            "who_decides": self.who_decides,
            "steps": [s.as_dict() for s in self.steps],
            "questions": [q.as_dict() for q in self.questions],
            "finders": [c.as_dict() for c in self.finders],
        }


def funding_guidance() -> FundingGuidance:
    """The whole next-step story, disclaimer included. The only way to get the steps."""
    return FundingGuidance(
        who_decides=WHO_DECIDES,
        steps=STEPS,
        questions=QUESTIONS,
        finders=(COS_CENTER_FINDER, EDD_OFFICE_LOCATOR, EDD_ETPL),
    )
