"""ZIP-to-county crosswalk, from the Census 2020 ZCTA-to-county relationship file (D8).

Source D8 in PROVENANCE.md, where the choice of this file over HUD's USPS crosswalk is
recorded with the measurement it was made on.

This module exists for one join and refuses to be used for any other. A training program
carries a mailing ZIP; EDD writes the counties of each labor market area into that area's
own published title; nothing in between says which county a ZIP is in. This file is that
missing link, and it is read the way every other source here is read -- to restate what a
publisher has published, never to infer California geography in this repository.

**Counties are keyed on their five-digit FIPS code, never on their name.** The relationship
file is national, and county names repeat across states: ZCTA 97635 straddles Modoc County,
California (``06049``) and **Lake County, Oregon** (``41037``), while California has its own
Lake County (``06033``) in a different EDD area. A name-keyed join would read the Oregon
county as the California one. Every lookup here goes through the GEOID, and the name-to-GEOID
map is built from California's own rows in the same file rather than transcribed.

**The vendored extract keeps the out-of-state half of every border ZCTA.** Filtering the
national file down to California's own rows would have dropped seven rows, and each of those
seven turns a refusal into a placement: ZCTA 89439 covers Sierra County, California and
Washoe County, Nevada, so a program filed there cannot be placed in the North Valley region
-- but with the Washoe row removed it would look like a clean single-county ZIP. That is the
absence-rendered-as-a-value failure this project exists to argue against, reached by way of a
file-size optimisation. The subset rule is therefore stated on the extract itself: every row
of every ZCTA that touches California, not every California row.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

import httpx

# Same HTTP manners as every other source here -- descriptive User-Agent, bounded retry,
# Retry-After -- defined once in dol_etp so no endpoint gets approached differently.
from afterward.sources.dol_etp import build_client, get_with_retry

RELATIONSHIP_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/"
    "tab20_zcta520_county20_natl.txt"
)
"""The national 2020 ZCTA-to-county relationship file, as the Census Bureau publishes it.

Decennial, not periodic. The 2020 relationship files are a fixed product of the 2020 census
and do not move until the 2030 geography is published, which is why a vendored extract of
this file is a snapshot of something that has stopped changing rather than a copy that is
already going stale. HUD's USPS crosswalk, the alternative, is republished quarterly.
"""

REQUEST_TIMEOUT = 120.0

CALIFORNIA_STATE_FIPS = "06"

VENDORED_PATH = Path(__file__).with_name("zcta-county-ca-2020.csv")
VENDORED_PROVENANCE_PATH = Path(__file__).with_name("zcta-county-ca-2020.source.json")

ZCTA_FIELD = "GEOID_ZCTA5_20"
COUNTY_GEOID_FIELD = "GEOID_COUNTY_20"
COUNTY_NAME_FIELD = "NAMELSAD_COUNTY_20"

_ZIP5 = re.compile(r"\A(\d{5})(?:-\d{4}|\d{4})?\Z")
_COUNTY_NOUN = re.compile(r"\s+(?:Count(?:y|ies)|Parish|Borough)\Z", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")


def normalise_zip(value: str | None) -> str | None:
    """The five-digit ZIP in ``value``, or None when there is not exactly one.

    DOL files ``field_zip`` as five digits, and has been seen to file ZIP+4. Anything else --
    blank, four digits, a word, a range -- is not a ZIP this can look up, and returning None
    puts the record in the *unplaced because there is no usable ZIP* bucket rather than
    guessing at a truncation. A four-digit value is not a ZIP missing its leading zero; it is
    a value nobody here can tell apart from a typo.
    """
    if value is None:
        return None
    match = _ZIP5.match(str(value).strip())
    return match.group(1) if match else None


def normalise_county(name: str | None) -> str | None:
    """Casefold a county name and drop the ``County`` noun, so two spellings compare exactly.

    Exactly, and only exactly, for the reason :func:`afterward.sources.edd_lmi.normalise_place`
    gives about place names: California has a Lake County and a Los Angeles County and a
    Los Banos that is not a county at all, and a near-match between two of them is far more
    likely to be two different places than one typo.

    The noun is dropped because the two publishers write it differently and neither is wrong:
    the Census file says ``Los Angeles County`` in ``NAMELSAD_COUNTY_20`` and EDD's area title
    says ``Los Angeles`` inside ``(Los Angeles County)``, having already had the noun stripped
    by :func:`afterward.sources.edd_lmi._counties` when it split the gloss.
    """
    if name is None:
        return None
    stripped = _COUNTY_NOUN.sub("", _WHITESPACE.sub(" ", name).strip())
    collapsed = stripped.strip().casefold()
    return collapsed or None


@dataclass(frozen=True)
class CrosswalkRow:
    """One published (ZCTA, county) pair: this ZIP area reaches into this county."""

    zcta: str
    county_geoid: str
    county_name: str

    @property
    def is_california(self) -> bool:
        return self.county_geoid.startswith(CALIFORNIA_STATE_FIPS)


def parse_relationship_file(text: str) -> Iterator[CrosswalkRow]:
    """Read the Census relationship file, keeping only rows that name both geographies.

    The file carries a row for every county with no ZCTA part as well, with the ZCTA columns
    blank. Those are county records, not crosswalk records, and a blank ZCTA is not a ZIP.
    """
    for row in csv.DictReader(io.StringIO(text), delimiter="|"):
        zcta = (row.get(ZCTA_FIELD) or "").strip()
        geoid = (row.get(COUNTY_GEOID_FIELD) or "").strip()
        name = (row.get(COUNTY_NAME_FIELD) or "").strip()
        if zcta and geoid and name:
            yield CrosswalkRow(zcta=zcta, county_geoid=geoid, county_name=name)


def california_subset(rows: Iterable[CrosswalkRow]) -> list[CrosswalkRow]:
    """Every row of every ZCTA that touches California -- **not** every California row.

    The distinction is the whole point of this function and is load-bearing: see the module
    docstring. Keeping only ``is_california`` rows would silently complete a border ZCTA's
    county set, and a ZIP that must be refused would place cleanly instead.
    """
    materialised = list(rows)
    touching = {row.zcta for row in materialised if row.is_california}
    return sorted(
        {row for row in materialised if row.zcta in touching},
        key=lambda row: (row.zcta, row.county_geoid),
    )


def render_csv(rows: Iterable[CrosswalkRow]) -> str:
    """The vendored extract's exact bytes, so a refresh can be diffed rather than trusted."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["zcta5", "county_geoid", "county_name"])
    for row in rows:
        writer.writerow([row.zcta, row.county_geoid, row.county_name])
    return buffer.getvalue()


def parse_csv(text: str) -> Iterator[CrosswalkRow]:
    """Read the vendored extract back."""
    for row in csv.DictReader(io.StringIO(text)):
        zcta = (row.get("zcta5") or "").strip()
        geoid = (row.get("county_geoid") or "").strip()
        name = (row.get("county_name") or "").strip()
        if zcta and geoid and name:
            yield CrosswalkRow(zcta=zcta, county_geoid=geoid, county_name=name)


@dataclass(frozen=True)
class ZipCountyCrosswalk:
    """Which counties a ZIP area reaches, and which GEOID a California county name is.

    Both directions come from the same file, so nothing here asserts a fact about California
    that the Census Bureau has not published in the row being read.
    """

    counties_by_zip: Mapping[str, frozenset[str]]
    california_county_geoids: Mapping[str, str]

    @classmethod
    def of(cls, rows: Iterable[CrosswalkRow]) -> ZipCountyCrosswalk:
        by_zip: dict[str, set[str]] = {}
        names: dict[str, str] = {}
        for row in rows:
            by_zip.setdefault(row.zcta, set()).add(row.county_geoid)
            if row.is_california:
                key = normalise_county(row.county_name)
                if key is not None:
                    names[key] = row.county_geoid
        return cls(
            counties_by_zip={zcta: frozenset(geoids) for zcta, geoids in by_zip.items()},
            california_county_geoids=names,
        )

    def counties(self, zip_code: str | None) -> frozenset[str] | None:
        """The counties this ZIP reaches, or None when the file does not carry it.

        None is not "no counties". It is "this crosswalk has nothing to say about this ZIP",
        which is the state a mailing ZIP with no ZCTA lands in -- a PO Box range, or a unique
        ZIP assigned to one large recipient. Those are exactly the ZIPs a ZCTA-based
        crosswalk cannot answer for, and the caller has to keep the two apart: a ZIP that
        reaches no county and a ZIP nobody published a county for are different absences.
        """
        zip5 = normalise_zip(zip_code)
        if zip5 is None:
            return None
        return self.counties_by_zip.get(zip5)

    def california_county(self, name: str | None) -> str | None:
        """The GEOID of the California county with this name, or None if there is none."""
        key = normalise_county(name)
        if key is None:
            return None
        return self.california_county_geoids.get(key)


def load_vendored(path: Path | None = None) -> ZipCountyCrosswalk:
    """Read the committed extract. No network, and no build depends on Census being up."""
    source = path or VENDORED_PATH
    return ZipCountyCrosswalk.of(parse_csv(source.read_text(encoding="utf-8")))


def vendored_provenance(path: Path | None = None) -> dict[str, object]:
    """The retrieval record committed beside the extract."""
    source = path or VENDORED_PROVENANCE_PATH
    loaded = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):  # pragma: no cover - a hand-edit, not a code path
        raise ValueError(f"{source} does not hold an object")
    return loaded


def fetch_relationship_file(client: httpx.Client | None = None) -> str:
    """Download the national relationship file. Used to refresh the extract, not to build."""
    owns_client = client is None
    http = client or build_client(REQUEST_TIMEOUT)
    try:
        return get_with_retry(http, RELATIONSHIP_URL).text
    finally:
        if owns_client:
            http.close()
