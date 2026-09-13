"""The two-letter state code to FIPS code link, from the Census ANSI table (D9B).

One join and nothing else. The ETP scorecard (D1) reports a program's state as a two-letter
USPS abbreviation; Projections Central's long-term endpoint (D9) is keyed by the numeric
state FIPS code. Nothing either publisher serves says the two are the same state, so the
link is read out of a vendored extract of the Census Bureau's own code table rather than
typed into this module.

**Names are deliberately absent.** The upstream file carries a state name column and this
extract drops it, because no join in this repository matches on a state's name: the feed
keys on the abbreviation, Projections Central keys on the code, and every check the adapter
makes against a fetched payload compares codes. A name column would be fifty-seven spellings
to keep in step with no join to serve.

**A row here is not a claim that anybody publishes anything for that state.** It says only
that the Census Bureau assigns that code to that abbreviation. Whether the ETP feed reports
programs for a state, and whether Projections Central publishes projections for it, are
questions for those two sources, asked at build time -- see
:func:`afterward.sources.dol_etp.fetch_states` and
:func:`afterward.sources.projections_central.fetch_state_projections`.
"""

from __future__ import annotations

import csv
import json
import re
from functools import cache
from pathlib import Path
from typing import Final

VENDORED_PATH: Final = Path(__file__).with_name("state-fips-ansi.csv")
VENDORED_PROVENANCE_PATH: Final = Path(__file__).with_name("state-fips-ansi.source.json")

_USPS = re.compile(r"\A[A-Z]{2}\Z")
_FIPS = re.compile(r"\A[0-9]{2}\Z")


class StateCodeError(LookupError):
    """A state code that is not in the Census table, or a table that is not usable."""


def _rows() -> list[tuple[str, str]]:
    text = VENDORED_PATH.read_text(encoding="utf-8")
    parsed: list[tuple[str, str]] = []
    for row in csv.DictReader(text.splitlines()):
        fips = (row.get("state_fips") or "").strip()
        usps = (row.get("usps") or "").strip().upper()
        if not _FIPS.match(fips) or not _USPS.match(usps):
            raise StateCodeError(
                f"{VENDORED_PATH.name} carries a row this module cannot read: "
                f"state_fips={fips!r}, usps={usps!r}. The extract is derived, never "
                "hand-edited; re-derive it with the command in its .source.json."
            )
        parsed.append((fips, usps))
    if not parsed:
        raise StateCodeError(
            f"{VENDORED_PATH.name} holds no rows. An empty table would make every state "
            "code unknown, which is a statement about this repository and not about the "
            "state somebody asked for."
        )
    return parsed


@cache
def by_usps() -> dict[str, str]:
    """Every two-letter code the Census table carries, mapped to its FIPS code."""
    table: dict[str, str] = {}
    for fips, usps in _rows():
        if usps in table:
            raise StateCodeError(f"{VENDORED_PATH.name} maps {usps} to two FIPS codes")
        table[usps] = fips
    return table


def fips_for(state: str) -> str:
    """The FIPS code for a two-letter state code, or raise naming what is known.

    Raising rather than returning None: the caller is about to ask a state-keyed endpoint
    for data, and a missing code there is indistinguishable, in the response, from a state
    that publishes nothing. The two must not arrive at the same place.
    """
    key = (state or "").strip().upper()
    table = by_usps()
    if key not in table:
        known = ", ".join(sorted(table))
        raise StateCodeError(
            f"{state!r} is not a state code in {VENDORED_PATH.name}. Known: {known}"
        )
    return table[key]


def provenance() -> dict[str, object]:
    """The retrieval record committed beside the extract."""
    return dict(json.loads(VENDORED_PROVENANCE_PATH.read_text(encoding="utf-8")))
