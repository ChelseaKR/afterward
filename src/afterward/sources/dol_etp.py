"""Client for the U.S. DOL Eligible Training Provider scorecard search API.

Source D1 in PROVENANCE.md. This is the public search backend behind
trainingproviderresults.gov, serving WIOA ETA-9171 performance data.

Three things about this data matter more than anything else in this module:

1. ``-1`` and ``""`` mean "not reported or suppressed", never zero. WIOA suppresses
   small-cohort cells to protect participant privacy. Rendering a suppressed cell as 0%
   would libel a training provider, so :func:`clean_measure` maps both to ``None`` and the
   distinction is preserved all the way to the UI.
2. On the two program-length fields, and only there, ``-1`` means something else entirely:
   the program is competency-based. See :func:`clean_length`. Reading that sentinel as
   "not reported" reports a deliberate design decision as missing data.
3. Programs carry SOC codes directly (``field_program_soc_occ_1..3``), so the program ->
   occupation join needs no CIP/SOC crosswalk.

This module also owns the HTTP manners for the whole package -- see "HTTP citizenship"
below. ``edd_lmi`` imports that layer from here so the two clients cannot drift apart in
how they identify themselves or how hard they push a public endpoint.
"""

from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from afterward import __version__

BASE_URL = "https://cxsearch.dol.gov/etp"
PROGRAMS_INDEX = "etp_scorecard_programs"
PAGE_SIZE = 500
REQUEST_TIMEOUT = 60.0
PAUSE_BETWEEN_PAGES = 0.4
"""Deliberate throttle. This is a public service funded by taxpayers, not a firehose."""

SUPPRESSED = -1
"""Sentinel used by the ETP scorecard for withheld or unreported measures.

Except on the two program-length fields, where the same number means something else. See
:data:`COMPETENCY_BASED` and :func:`clean_length`.
"""

COMPETENCY_BASED = -1
"""The same ``-1``, on ``field_program_length_hours`` and ``field_program_length_weeks``.

A separate name for the same number because it is a separate fact, and code that reaches for
one of these two constants should have to say which meaning it is claiming. The ETP Scorecard
data dictionary (v4.0, updated 2024-05-15) attaches a note to those two elements and to no
others: "NOTE: For this element, a suppressed value (-1) indicates it was reported as a
competency-based program." Its general suppression note -- the one that covers every other
column, and gives the three documented causes -- does not apply here.
"""


def clean_measure(value: Any) -> float | None:
    """Map an ETP measure to a float, or ``None`` when not reported.

    Empty strings and the ``-1`` sentinel both mean "no data" and must not be confused
    with a genuine zero.

    Not for the program-length fields: see :func:`clean_length`, which reads the same ``-1``
    as the positive fact the data dictionary says it is.
    """
    if value is None or value == "":
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return None if numeric == SUPPRESSED else numeric


def clean_rate(value: Any, *, field: str = "") -> float | None:
    """Parse a rate, enforcing the contract that it is a fraction between 0 and 1.

    Every rate in the current feed is a fraction (0.64 meaning 64%), but nothing upstream
    guarantees that, and the display layer used to hedge with "if it is above 1, assume it is
    a whole percentage". That hedge is wrong per-row rather than wholesale: it renders 64 as
    64% correctly while rendering a genuine 1% as 100% and 0.5% as 50%, and nothing would
    ever flag it.

    So the unit is checked once, here, where the data enters. A value outside 0..1 is not a
    rate this code knows how to read, so it becomes "not reported" and says so on stderr
    rather than being silently reinterpreted downstream.
    """
    parsed = clean_measure(value)
    if parsed is None:
        return None
    if not 0.0 <= parsed <= 1.0:
        print(
            f"warning: {field or 'rate'} = {parsed!r} is outside 0..1; expected a fraction. "
            "Treating as not reported — check whether the feed changed units.",
            file=sys.stderr,
        )
        return None
    return parsed


IMPLAUSIBLE_QUARTERLY_EARNINGS = 3000.0
"""Below this, a "quarterly earnings" figure is almost certainly a different unit.

Someone employed for a quarter at California's minimum wage earns several thousand dollars.
Fourteen California programs report a median between $16 and $99 -- an hourly rate filed in a
quarterly field -- and 34 more fall under $3,000. Rendered literally, the lowest reads
"Earnings in one quarter after: $16 ... Worse than typical" beside the name of a real
business, which is a defamatory claim produced by a unit error.
"""


def clean_earnings(value: Any, *, context: str = "") -> float | None:
    """Parse quarterly earnings, refusing figures too small to be a quarter's pay.

    Same reasoning as :func:`clean_rate`: decide what a number means where it enters, not
    where it is displayed. A value this small is not quarterly earnings, so it is treated as
    not reported rather than published as a verdict about a named provider.
    """
    parsed = clean_measure(value)
    if parsed is None:
        return None
    if 0 < parsed < IMPLAUSIBLE_QUARTERLY_EARNINGS:
        print(
            f"warning: {context or 'median earnings'} = {parsed!r} is too small to be a "
            "quarter's earnings; treating as not reported.",
            file=sys.stderr,
        )
        return None
    return parsed


def reconcile_rate(
    rate: float | None, numerator: float | None, denominator: float | None
) -> float | None:
    """Drop a rate of exactly zero that the record's own counts contradict.

    DOL publishes rates to two decimal places, so 0.00 means "below 0.5%", not "nobody". Six
    California programs pair a 0.00 employment rate with a non-zero count of people employed:
    one reports 86 people working against 15,335 exits, a real 0.56% that rounds to zero.

    Rendered literally that becomes "Working 6 months later: 0%" and "Worse than typical" on a
    page naming a public community college. The rate is a rounding artefact, and the honest
    move is to say it was not usefully reported rather than to publish a zero the record
    itself refutes. A genuine zero -- rate 0.00 with nobody employed -- is preserved, because
    that is a real and important finding.
    """
    if rate != 0 or numerator is None or denominator in (None, 0):
        return rate
    return None if numerator > 0 else rate


@dataclass(frozen=True)
class ProgramLength:
    """How long a program takes, or the reason it has no clock length to report.

    Three states, not two, and the middle one is what this type exists for:

    * a clock length, filed in weeks, in hours, or in both;
    * **competency-based**: the program ends when the student can do the work, so it has no
      fixed length *by design*. A positive fact the provider filed about the course, not an
      absence;
    * nothing filed at all, which is the only one of the three that is missing data.

    Competency-based is carried as its own flag rather than as a magic value in ``weeks``,
    because every consumer that compares, sorts, bands or filters on a length has to treat it
    as "no number here" -- and a number chosen to stand for "no number" is the failure this
    module spends most of its length preventing. ``weeks`` and ``hours`` stay strictly
    numeric-or-null, so existing null handling downstream stays correct without knowing this
    state exists; ``competency_based`` then tells a page *why* they are null, which is what
    lets it say "competency-based, no fixed length" instead of "not reported".
    """

    weeks: float | None
    hours: float | None
    competency_based: bool

    @property
    def reported(self) -> bool:
        """True when the provider filed a clock length in either unit."""
        return self.weeks is not None or self.hours is not None

    @property
    def unstated(self) -> bool:
        """True only for a record that says nothing about length at all.

        The state the site used to attribute to competency-based programs, and the one it
        must keep distinguishable from them: nobody said, as against nobody could.
        """
        return not self.reported and not self.competency_based

    def as_dict(self) -> dict[str, Any]:
        return {
            "weeks": self.weeks,
            "hours": self.hours,
            # Always written, never omitted when false. A consumer has to be able to tell a
            # program that is not competency-based from a record built before the field
            # existed, and an absent key reads as the first while meaning the second.
            "competency_based": self.competency_based,
        }


def _is_competency_sentinel(value: Any) -> bool:
    """True when a length field holds the ``-1`` the dictionary calls competency-based."""
    if value is None or value == "":
        return False
    try:
        return float(value) == COMPETENCY_BASED
    except (TypeError, ValueError):
        return False


def clean_length(hours: Any, weeks: Any) -> ProgramLength:
    """Read the two program-length fields together, honouring their own sentinel.

    ``clean_measure`` was applied to these two fields until 2026-08-07, which mapped ``-1`` to
    null exactly as it does for an outcome measure. That is wrong here and only here: the ETP
    Scorecard data dictionary (v4.0) documents ``-1`` on ``d113_program_length_hours`` and
    ``d114_program_length_weeks`` as meaning the program was "reported as a competency-based
    program", where the general suppression note it carries for every other column does not
    apply. Twelve of California's 3,266 programs filed it, and every one of them reached the
    site as "length not reported" and was dropped by the length filter: a course whose provider
    deliberately stated it has no fixed length, published as a provider who never answered.
    That is the error class this project exists to refuse, committed by this project.

    Both fields are read here rather than one at a time, because competency-based is a fact
    about the *program* and not about a column: a record carrying the sentinel in either field
    is competency-based whichever unit it appears in. In the 2026-08-07 California snapshot
    all 12 carry it in both fields and none carries it in only one, so the mixed case is
    defined here rather than left to be discovered later. A real length filed alongside the
    sentinel in the other unit is kept, because it is a real filing and dropping it would lose
    a fact the provider took the trouble to state.
    """
    competency_based = _is_competency_sentinel(hours) or _is_competency_sentinel(weeks)
    return ProgramLength(
        weeks=clean_measure(weeks),
        hours=clean_measure(hours),
        competency_based=competency_based,
    )


SAFE_URL_SCHEMES = ("http://", "https://")
_BARE_DOMAIN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9-]+)+(/.*)?$", re.I)


def clean_url(value: Any) -> str | None:
    """Return an absolute http(s) URL, or None.

    The feed's ``field_program_url`` is free text and providers treat it as such: some file a
    bare domain, and five California records hold a course title where a URL belongs. Those
    were rendered straight into an ``href``, so "Provider's website" navigated to a relative
    path inside this site.

    Anything that is not http(s) is dropped rather than passed through. React does not block
    ``javascript:`` in an ``href``, so an unvalidated third-party string in that position is a
    script-injection sink waiting for one bad row upstream. Nothing in the current feed
    exploits it, which is not a reason to keep the hole open.

    A bare domain is repaired to https rather than discarded: it is unambiguous, and losing a
    working provider link helps nobody.
    """
    text = clean_text(value)
    if not text:
        return None
    lowered = text.lower()
    if lowered.startswith(SAFE_URL_SCHEMES):
        return text
    if lowered.startswith("//"):
        return f"https:{text}"
    if " " not in text and _BARE_DOMAIN.match(text):
        return f"https://{text}"
    return None


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


_ROW_ID_PREFIX = re.compile(r"^\d+\|")


def clean_description(value: Any) -> str | None:
    """Drop the source row id the feed prefixes to a program description.

    3,223 of California's 3,266 descriptions arrive as ``"6091|Covers understanding user
    needs to create products that..."``. The number is unique per record -- 3,223 distinct
    values across the 3,223 tagged descriptions -- so it is the upstream row's own identifier
    leaking into a prose field, not anything a reader is being told.

    Stripped here rather than where it is rendered. The site removed it in one component with
    one regex, which left the artifact in every published copy of ``programs.json``: anybody
    reading the dataset rather than the page got the raw field, and a second place that
    rendered a description would have had to remember the same repair.

    The description only. :func:`clean_text` is shared with provider names, program names,
    cities and ZIPs, and none of those carries the artifact -- 0 of 3,266 on each, measured --
    so teaching the general cleaner to delete leading digits would be a licence to eat a real
    value somewhere it means something.
    """
    text = clean_text(value)
    if text is None:
        return None
    return clean_text(_ROW_ID_PREFIX.sub("", text, count=1))


_CIP_CODE = re.compile(r"^(\d{1,2})(?:\.(\d{1,4}))?$")


def clean_cip_code(value: Any) -> str | None:
    """Restore the zero padding a CIP code lost to being read as a number.

    NCES publishes CIP as fixed-width decimals: a two-digit series (``46``), a four-digit
    family (``12.05``) and a six-digit code (``51.0710``). 239 of California's 3,266 programs
    carry one that has been through a float somewhere upstream, and leading and trailing zeros
    are exactly what that loses -- ``01.0505`` arrives as ``1.0505`` (113 programs), ``51.0710``
    as ``51.071`` (124), and two more lose a leading zero from a four-digit family. Nothing
    renders the code today, so nobody is misled on a page; it is published in
    ``programs.json``, where it will not join to anything.

    308 is the count of every non-canonical width in the snapshot, which is not the same
    number: it also contains the 69 below that CIP genuinely publishes and this function
    leaves alone. Only 239 lost a digit.

    Both losses are repaired, because both are reversible without deciding anything:

    * A CIP series is two digits. There is no series ``1``, so ``1.0505`` can only be
      ``01.0505`` -- corroborated by the record it sits on, a "Dog Obedience Instructor
      Program", against 01.0505 Animal Training.
    * A CIP detail is two or four digits, never three, so a three-digit one has dropped a
      trailing zero: ``51.071`` on a "Medical Office Assistant" is 51.0710, Medical Office
      Assistant/Specialist.

    Everything else is left exactly as filed, including this snapshot's 45 bare series codes
    (``46``) and 24 four-digit families (``12.05``). Those are widths CIP genuinely publishes,
    so padding them to ``46.0000`` and ``12.0500`` would not restore a lost zero -- it would
    swap a family for one particular member of it, which is a reclassification made here that
    nothing upstream asked for. A one-digit detail is left for the same reason: ``51.7`` has
    certainly lost trailing zeros, but to ``51.70`` and to ``51.7000`` equally, and this
    module does not pick between two readings of a code. None occurs in this snapshot.
    """
    text = clean_text(value)
    if text is None:
        return None
    match = _CIP_CODE.match(text)
    if match is None:
        return text
    series, detail = match.group(1).zfill(2), match.group(2)
    if detail is None:
        return series
    return f"{series}.{detail}0" if len(detail) == 3 else f"{series}.{detail}"


@dataclass(frozen=True)
class Program:
    """A single training program as reported to DOL under WIOA."""

    uuid: str
    provider_name: str | None
    program_name: str | None
    description: str | None
    program_format: str | None
    program_url: str | None
    cip_code: str | None
    soc_codes: tuple[str, ...]
    city: str | None
    state: str | None
    zip_code: str | None
    lat: float | None
    lon: float | None
    entity_type: str | None
    # Not two nullable floats: a competency-based program has no clock length by design, and
    # that has to survive as a distinct state rather than as a pair of nulls. See ProgramLength.
    length: ProgramLength
    cost_wioa: float | None
    cost_tuition: float | None
    cost_supplies: float | None
    # Outcome measures. None means "not reported"; see clean_measure.
    total_served: float | None
    total_exited: float | None
    total_completed: float | None
    completed_percent: float | None
    total_credential: float | None
    median_earnings: float | None
    # employed_q2 is NOT q2_employment_percent's numerator, despite the names. The rate's
    # actual denominator (ETA-9171 DE129) is a differently-scoped exiter cohort than
    # total_exited (DE121), not the same population under another name. See build.py's
    # search_entry / program_payload and PROVENANCE.md "Notes on D1" (#25).
    q2_employment_percent: float | None
    employed_q2: float | None
    employed_q4: float | None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def has_outcomes(self) -> bool:
        """True when at least one headline outcome measure was reported."""
        return any(
            m is not None
            for m in (self.median_earnings, self.q2_employment_percent, self.completed_percent)
        )

    @property
    def total_cost(self) -> float | None:
        """Non-WIOA out-of-pocket cost, when any component was reported.

        May be a floor rather than a total -- see :attr:`cost_is_complete`. Summing a
        reported tuition with a suppressed supplies figure quietly treats the unknown part
        as zero, which is the one thing this codebase is not allowed to do, so callers must
        check completeness before presenting this as "the cost".
        """
        parts = [c for c in (self.cost_tuition, self.cost_supplies) if c is not None]
        return sum(parts) if parts else None

    @property
    def cost_is_complete(self) -> bool:
        """True when every cost component was reported, so the total really is the total."""
        return self.cost_tuition is not None and self.cost_supplies is not None


def _soc_codes(source: dict[str, Any]) -> tuple[str, ...]:
    """Extract and normalise the up-to-three SOC codes attached to a program.

    The feed writes them zero-padded to 8 digits (``15-125200``); the standard 6-digit SOC
    used by EDD is the first six (``15-1252``).
    """
    codes: list[str] = []
    for key in ("field_program_soc_occ_1", "field_program_soc_occ_2", "field_program_soc_occ_3"):
        raw = clean_text(source.get(key))
        if not raw:
            continue
        digits = raw.replace("-", "")
        if len(digits) >= 6 and digits[:6].isdigit():
            normalised = f"{digits[:2]}-{digits[2:6]}"
            if normalised not in codes:
                codes.append(normalised)
    return tuple(codes)


def parse_program(hit: dict[str, Any]) -> Program:
    source = hit.get("_source", {})
    return Program(
        uuid=str(source.get("field_uuid") or hit.get("_id") or ""),
        provider_name=clean_text(source.get("field_etp")),
        program_name=clean_text(source.get("field_program_name")),
        description=clean_description(source.get("field_program_description")),
        program_format=clean_text(source.get("field_program_format")),
        program_url=clean_url(source.get("field_program_url")),
        cip_code=clean_cip_code(source.get("field_cip_code")),
        soc_codes=_soc_codes(source),
        city=clean_text(source.get("field_city")),
        state=clean_text(source.get("field_state")),
        zip_code=clean_text(source.get("field_zip")),
        lat=clean_measure(source.get("field_lat")),
        lon=clean_measure(source.get("field_lon")),
        entity_type=clean_text(source.get("field_entity_type")),
        length=clean_length(
            source.get("field_program_length_hours"),
            source.get("field_program_length_weeks"),
        ),
        cost_wioa=clean_measure(source.get("field_cost_per_wioa_num")),
        cost_tuition=clean_measure(source.get("field_non_wioa_tuition_cost")),
        cost_supplies=clean_measure(source.get("field_non_wioa_supplies_cost")),
        total_served=clean_measure(source.get("field_c_total_served")),
        total_exited=clean_measure(source.get("field_c_total_exited")),
        total_completed=clean_measure(source.get("field_c_total_completed")),
        completed_percent=clean_rate(
            source.get("field_c_completed_percent"), field="completion rate"
        ),
        total_credential=clean_measure(source.get("field_c_total_credential")),
        median_earnings=clean_earnings(
            source.get("field_c_median_earnings"), context="program median earnings"
        ),
        q2_employment_percent=reconcile_rate(
            clean_rate(source.get("field_c_q2_employment_percent"), field="Q2 employment rate"),
            clean_measure(source.get("field_total_employed_q2")),
            clean_measure(source.get("field_c_total_exited")),
        ),
        employed_q2=clean_measure(source.get("field_total_employed_q2")),
        employed_q4=clean_measure(source.get("field_total_employed_q4")),
        raw=source,
    )


# --------------------------------------------------------------------------------------
# Cohort integrity
#
# Everything above cleans one measure at a time. This section asks a different question:
# *who* is the population a record's counts describe? A measure can survive every check
# above and still be attached to the wrong people, and that is the version of this data
# that libels a named provider, because the site then stamps a verdict on it.
#
# Three failures are detectable from the feed itself, and none of them is a judgement about
# whether a provider trains anyone well:
#
# 1. The same cohort is filed against several of one provider's programs.
# 2. The record's own counts disagree about which population they describe.
# 3. One provider files many cohorts far too large to be single programs.
#
# All three are *marked*, never deleted. The figures are real filings and a reader is
# entitled to see them; what they are not entitled to be told is that a figure describing
# some larger population describes the one program whose page they are reading.
# --------------------------------------------------------------------------------------


def normalise_provider(name: str | None) -> str | None:
    """Key a provider by, so the same filer under two spellings is one filer.

    Case and internal whitespace only. Two of California's providers file under both a
    cased and a shouting form of the same name ("Procareer Academy" / "PROCAREER ACADEMY"),
    and a duplicate-detection pass keyed on the literal string would let a provider evade it
    by shouting. Nothing else is normalised: guessing that two differently-*spelled* names
    are one organisation is a similarity judgement, and this module does not make those.
    """
    if name is None:
        return None
    collapsed = re.sub(r"\s+", " ", name).strip()
    return collapsed.casefold() or None


OVERSIZED_COHORT_SERVED = 3000.0
"""A single program cohort at or above this is large enough to want corroborating.

Argued from the 2026-08-04 California snapshot, over the 2,099 programs that report
``total_served``: the median is 112, the 90th percentile 634, the 95th 1,221. 3,000 is the
97.3rd percentile — 56 programs.

That tail is not shaped like a distribution of cohort sizes. Those 56 programs account for
67% of everyone reported served in the whole state, and they come from 10 of 584 providers.
The threshold alone is therefore *not* enough to conclude anything: California's community
colleges are genuinely large, and one flagship course really can put thousands of people
through a year. Project Heartbeat's Basic Life Support renewal (5,896 served, and the
provider's only large program) is exactly that, and must not be second-guessed here.
"""

OVERSIZED_COHORT_MIN_PROGRAMS = 3
"""How many such cohorts one provider must file before the size stops being credible.

This is the half of the test that does the work. One very large program at a provider is
ordinary. Three or more separate cohorts of 3,000+ at a single provider is a claim to have
served 9,000+ people in distinct programs, and in this snapshot every provider that makes it
is visibly republishing one pool: De Anza's Occupational Training Institute files 32 such
rows summing to 417,753 served — 40% of every Californian reported served by any of the 584
providers here — with its top nine cohorts landing within a few hundred of each other
(25,890 / 25,862 / 25,855 / 25,761 …). College of the Desert files the same 8,692 eleven
times.

Measured on that snapshot the pair catches 49 programs from 4 providers, and deliberately
leaves alone the six providers whose one or two large programs are plausible flagships
(Project Heartbeat 5,896; Calbright 5,738; 160 Driving Academy 5,921 and 4,577; American
Career College 4,070; Gurnick 3,613; Antelope Valley Adult School 3,131). Two of the four it
does catch — San Joaquin Valley College and UEI College, three rows each — are large
multi-campus chains whose figures may well be genuine. They are marked, not suppressed, and
losing a comparative badge is a far smaller harm than publishing one that is wrong.
"""


def _exceeds(numerator: float | None, denominator: float | None) -> bool:
    """True only when both counts were reported and the first is genuinely the larger.

    Explicit ``is not None`` rather than truthiness: a reported zero is a count, and folding
    it in with "not reported" is the one thing this module exists to prevent.
    """
    return numerator is not None and denominator is not None and numerator > denominator


@dataclass(frozen=True)
class CohortIntegrity:
    """What a program's cohort counts can, and cannot, be read to describe.

    Written on every program, including programs that reported nothing: a consumer must be
    able to tell "checked, and nothing was wrong" from "this record predates the check".
    """

    shared_with_sibling_programs: int | None
    """Other programs at the same provider filing this identical (served, exited, completed).

    ``None`` means the cohort is this program's alone, or that there was no cohort to
    compare. Never 0 — a zero here would read as a count of siblings, and the absence of
    siblings is not a measurement.
    """

    exited_exceeds_served: bool
    completed_exceeds_served: bool
    oversized_for_one_program: bool

    @property
    def internally_consistent(self) -> bool:
        """True when the record's own counts agree about the population they describe.

        Under ETA-9171 the served, exited and completed counts are drawn from different
        reporting windows, so more exiters than entrants is not upstream corruption. It does
        mean the two numbers are not one population, and a page showing "enrolled 1,796"
        above "based on 5,214 people" is asserting that they are.
        """
        return not (self.exited_exceeds_served or self.completed_exceeds_served)

    @property
    def attributable(self) -> bool:
        """True when these figures may be presented as measuring *this* program.

        False for a cohort filed against several programs and for a cohort too large to be
        one program at a provider that files many such. Both mean the same thing to a
        reader: whatever population this describes, it is not only the program in front of
        them, so nothing here may carry a comparative verdict.

        Internal contradiction deliberately does not clear this flag. The published rates
        reconcile exactly against completed/exited, so the rate is sound; it is the
        *enrolled* label that is wrong, which is a different repair.
        """
        return self.shared_with_sibling_programs is None and not self.oversized_for_one_program

    def as_dict(self) -> dict[str, Any]:
        return {
            "attributable": self.attributable,
            "internally_consistent": self.internally_consistent,
            "shared_with_sibling_programs": self.shared_with_sibling_programs,
            "exited_exceeds_served": self.exited_exceeds_served,
            "completed_exceeds_served": self.completed_exceeds_served,
            "oversized_for_one_program": self.oversized_for_one_program,
        }


@dataclass(frozen=True)
class CohortFiling:
    """The four fields a claim about "who was measured" is made of.

    A separate type from :class:`Program` so the check can run over records this module did
    not parse -- the offline build reconstructs these from a committed snapshot of pipeline
    output, and asking it to rebuild whole ``Program`` objects to answer a question about
    four fields would be ceremony that invites the two paths to drift apart.
    """

    provider_name: str | None
    total_served: float | None
    total_exited: float | None
    total_completed: float | None

    @classmethod
    def of(cls, program: Program) -> CohortFiling:
        return cls(
            provider_name=program.provider_name,
            total_served=program.total_served,
            total_exited=program.total_exited,
            total_completed=program.total_completed,
        )


CohortKey = tuple[float | None, float | None, float | None]


def _cohort_key(program: CohortFiling) -> CohortKey | None:
    """The population claim a record makes, or None when it makes none.

    Keyed on the three counts rather than the whole outcome tuple. The counts are the claim
    about *who was measured*; the rates are arithmetic on top of them. Keying on everything
    would have missed one of College of the Desert's eleven identical filings, because that
    one row also carries a median-earnings figure the other ten suppress — the population
    claim is identical, and it is the population claim that is being republished.

    An all-null cohort is not a claim and never groups: otherwise every silent program at a
    provider would be flagged as sharing a cohort with every other, which would turn the
    single most common state in this dataset into a warning.
    """
    key = (program.total_served, program.total_exited, program.total_completed)
    return None if all(count is None for count in key) else key


def _is_oversized_cohort(program: CohortFiling) -> bool:
    return program.total_served is not None and program.total_served >= OVERSIZED_COHORT_SERVED


def cohort_integrity(programs: Sequence[CohortFiling]) -> list[CohortIntegrity]:
    """Judge every program's cohort against its provider's other filings.

    The verdicts are relative to the population passed in, which is the only honest thing
    they can be. Over a subset they come out weaker rather than wrong: a provider whose nine
    impossible cohorts are represented by two rows in a sample has not been shown to file
    many of them, and this says so rather than guessing.

    Returns one verdict per filing, in the order given, because two of the three checks are
    about a population of records rather than a record: a duplicate is invisible from inside
    one row, and so is a provider filing nine impossible cohorts. Passing a single program
    is therefore a supported call that yields exactly what one row can prove about itself —
    the contradiction checks — and asserts nothing about sharing or scale.

    Programs with no provider name are excluded from both cross-program checks rather than
    grouped under a shared blank, which would attribute one anonymous filer's duplicate to
    another's.
    """
    filings: Counter[tuple[str, CohortKey]] = Counter()
    oversized_per_provider: Counter[str] = Counter()
    for program in programs:
        provider = normalise_provider(program.provider_name)
        if provider is None:
            continue
        cohort = _cohort_key(program)
        if cohort is not None:
            filings[(provider, cohort)] += 1
        if _is_oversized_cohort(program):
            oversized_per_provider[provider] += 1

    verdicts: list[CohortIntegrity] = []
    for program in programs:
        provider = normalise_provider(program.provider_name)
        cohort = _cohort_key(program)
        filed = filings[(provider, cohort)] if provider is not None and cohort is not None else 1
        verdicts.append(
            CohortIntegrity(
                shared_with_sibling_programs=filed - 1 if filed > 1 else None,
                exited_exceeds_served=_exceeds(program.total_exited, program.total_served),
                completed_exceeds_served=_exceeds(program.total_completed, program.total_served),
                oversized_for_one_program=(
                    provider is not None
                    and _is_oversized_cohort(program)
                    and oversized_per_provider[provider] >= OVERSIZED_COHORT_MIN_PROGRAMS
                ),
            )
        )
    return verdicts


STATES_INDEX = "etp_scorecard_states"


@dataclass(frozen=True)
class StateBenchmark:
    """Statewide totals, so a single program's numbers can be read against something.

    Without this a rate is unanchored: a reader has no way to know whether 45% employed is
    strong or dismal. California's own statewide figure is the fairest available yardstick,
    since it is the same measure computed over the same population by the same reporters.
    """

    state: str
    completion_rate: float | None
    q2_employment_rate: float | None
    median_earnings: float | None
    credential_rate: float | None
    total_exited: float | None
    total_completed: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "completion_rate": self.completion_rate,
            "employment_rate_q2": self.q2_employment_rate,
            "median_earnings": self.median_earnings,
            "credential_rate": self.credential_rate,
            "total_exited": self.total_exited,
            "total_completed": self.total_completed,
        }


def parse_state_benchmark(state: str, source: dict[str, Any]) -> StateBenchmark:
    """Build a benchmark from a states-index document."""
    return StateBenchmark(
        state=state,
        completion_rate=clean_rate(
            source.get("field_c_completed_percent"), field="state completion rate"
        ),
        q2_employment_rate=clean_rate(
            source.get("field_c_q2_employment_percent"), field="state Q2 employment rate"
        ),
        median_earnings=clean_earnings(
            source.get("field_c_median_earnings"), context="program median earnings"
        ),
        credential_rate=clean_rate(
            source.get("field_c_cred_attainment_percent"), field="state credential rate"
        ),
        total_exited=clean_measure(source.get("field_c_total_exited")),
        total_completed=clean_measure(source.get("field_c_total_completed")),
    )


# --------------------------------------------------------------------------------------
# HTTP citizenship
#
# Everything below is about being a guest on someone else's server. Both source clients in
# this package share it: one honest identity, one retry policy, one throttle.
# --------------------------------------------------------------------------------------

USER_AGENT = (
    f"afterward/{__version__} (+https://github.com/ChelseaKR/afterward; "
    "non-commercial open-data client; quarterly bulk read)"
)
"""Who we say we are.

Deliberately not a browser string. The endpoints here are public taxpayer-funded services
and their operators are entitled to know who is reading them and where to complain: a
spoofed Chrome User-Agent would buy access by lying, and would leave an operator no way to
tell this project apart from a scraper. Being identifiable is the point, even though it
means a filter can single us out.
"""

MAX_ATTEMPTS = 4
BACKOFF_INITIAL_SECONDS = 1.0
BACKOFF_MULTIPLIER = 2.0
BACKOFF_CAP_SECONDS = 30.0
RETRY_AFTER_CAP_SECONDS = 120.0
"""Longest ``Retry-After`` we will wait out rather than fail and let a human reschedule."""

RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})
"""Statuses worth a second look. 403 and 404 are decisions, not hiccups, and are absent."""


class FetchError(RuntimeError):
    """A public endpoint could not be read.

    The message is written for whoever is staring at a failed build log, not for a
    stack trace: it should say what refused us and what to do about it.
    """

    def __init__(self, message: str, *, url: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.url = url
        self.status_code = status_code


def build_client(timeout: float = REQUEST_TIMEOUT) -> httpx.Client:
    """An ``httpx.Client`` that identifies itself."""
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )


def _forbidden_message(url: str) -> str:
    host = httpx.URL(url).host
    return (
        f"{host} refused the request (HTTP 403 Forbidden). Not retried: a refusal is a "
        "decision, and repeating it would only be rude.\n"
        "This is known to happen from CI runners and other datacenter IP ranges even when "
        "the identical request succeeds from a laptop, because the endpoint sits behind a "
        "load balancer that filters on client IP reputation and on User-Agent. This client "
        f"already sends a descriptive User-Agent ({USER_AGENT!r}) and will not impersonate "
        "a browser to get around the filter.\n"
        "If this happened in CI, build from the committed data snapshot instead "
        "(`afterward build-offline`) and refresh that snapshot from a workstation."
    )


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """Seconds the server asked us to wait, from either Retry-After form, or None."""
    raw = (response.headers.get("Retry-After") or "").strip()
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


def _backoff_seconds(attempt: int) -> float:
    return min(BACKOFF_INITIAL_SECONDS * BACKOFF_MULTIPLIER ** (attempt - 1), BACKOFF_CAP_SECONDS)


def _raise_if_permanent(response: httpx.Response, url: str) -> None:
    """Raise unless the status is one that might resolve itself."""
    status = response.status_code
    if status == httpx.codes.FORBIDDEN:
        raise FetchError(_forbidden_message(url), url=url, status_code=status)
    if status in RETRYABLE_STATUS:
        return
    raise FetchError(
        f"{url} returned HTTP {status} {response.reason_phrase}. Not retried: this status "
        "will not change on its own.",
        url=url,
        status_code=status,
    )


def _retry_wait(response: httpx.Response, attempt: int, url: str) -> float:
    """How long to wait before the next attempt, honouring Retry-After when present."""
    requested = _retry_after_seconds(response)
    if requested is None:
        return _backoff_seconds(attempt)
    if requested > RETRY_AFTER_CAP_SECONDS:
        raise FetchError(
            f"{url} returned HTTP {response.status_code} and asked for a "
            f"{requested:.0f}s wait, longer than this client will hold a build open. "
            "Respecting that means stopping here and retrying later.",
            url=url,
            status_code=response.status_code,
        )
    return requested


def get_with_retry(
    client: httpx.Client,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    max_attempts: int = MAX_ATTEMPTS,
    sleep: Callable[[float], None] | None = None,
) -> httpx.Response:
    """GET ``url``, retrying only what is plausibly transient.

    Timeouts, connection failures, 429 and 5xx get bounded exponential backoff, and a
    ``Retry-After`` header overrides that backoff. A 403 or 404 is raised on the first
    response instead of being hammered in a tight loop.

    The User-Agent is set per request as well as on :func:`build_client`, so a
    caller-supplied client still identifies itself.
    """
    wait_out = time.sleep if sleep is None else sleep
    problem = "no attempt was made"
    cause: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.get(url, params=params, headers={"User-Agent": USER_AGENT})
        except httpx.TransportError as exc:
            problem, cause = f"{type(exc).__name__}: {exc}", exc
            wait = _backoff_seconds(attempt)
        else:
            if not response.is_error:
                return response
            _raise_if_permanent(response, url)
            problem, cause = f"HTTP {response.status_code} {response.reason_phrase}".strip(), None
            wait = _retry_wait(response, attempt, url)
        if attempt == max_attempts:
            break
        wait_out(wait)
    raise FetchError(
        f"{url} could not be read after {max_attempts} attempts; last failure was {problem}.",
        url=url,
    ) from cause


def fetch_state_benchmark(
    state: str = "CA", *, client: httpx.Client | None = None
) -> StateBenchmark | None:
    """Fetch the statewide aggregate for ``state``, or None if it is not published."""
    body = {
        "size": 1,
        "query": {
            "bool": {
                "filter": [
                    {"term": {"_index": STATES_INDEX}},
                    {"term": {"field_state": state}},
                ]
            }
        },
    }
    owns_client = client is None
    http = client or build_client()
    try:
        response = get_with_retry(
            http,
            f"{BASE_URL}/_search",
            params={"source": json.dumps(body), "source_content_type": "application/json"},
        )
        hits = response.json().get("hits", {}).get("hits", [])
        if not hits:
            return None
        return parse_state_benchmark(state, hits[0].get("_source", {}))
    finally:
        if owns_client:
            http.close()


def _query_body(state: str, page_size: int, after: list[Any] | None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "size": page_size,
        "sort": [{"nid": "asc"}],
        "query": {
            "bool": {
                "filter": [
                    {"term": {"_index": PROGRAMS_INDEX}},
                    {"term": {"field_state": state}},
                ]
            }
        },
    }
    if after is not None:
        body["search_after"] = after
    return body


def fetch_programs(
    state: str = "CA",
    *,
    page_size: int = PAGE_SIZE,
    client: httpx.Client | None = None,
) -> Iterator[Program]:
    """Yield every ETP program reported for ``state``.

    Uses ``search_after`` rather than ``from``/``size`` so the read stays correct if the
    result set ever grows past Elasticsearch's 10k window.
    """
    owns_client = client is None
    http = client or build_client()
    after: list[Any] | None = None
    try:
        while True:
            body = _query_body(state, page_size, after)
            response = get_with_retry(
                http,
                f"{BASE_URL}/_search",
                params={
                    "source": json.dumps(body),
                    "source_content_type": "application/json",
                },
            )
            hits = response.json().get("hits", {}).get("hits", [])
            if not hits:
                return
            for hit in hits:
                yield parse_program(hit)
            last_sort = hits[-1].get("sort")
            if not last_sort or len(hits) < page_size:
                return
            after = last_sort
            time.sleep(PAUSE_BETWEEN_PAGES)
    finally:
        if owns_client:
            http.close()
