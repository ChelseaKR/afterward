"""Client for the CareerOneStop Web API (U.S. Department of Labor).

Source D6 in PROVENANCE.md. Adds what neither the ETP scorecard nor EDD's projections carry:
a plain-language description of what an occupation actually involves, the concrete tasks the
work is made of, O*NET skill ratings, O*NET's own related-occupation list, the alternate
titles people actually use for the job, and BLS's measured distribution of the education
workers in the occupation *hold*.

Three things shape this module.

**Credentials never enter the repository.** The API requires a user id and token, read from
the environment (``CAREERONESTOP_USER_ID`` / ``CAREERONESTOP_TOKEN``, conventionally via a
gitignored ``.env.local``). They are build-time only and never reach the browser, since the
site ships as static files.

**Enrichment is optional by design.** CI has no credentials and must still build. With none
configured, :func:`fetch_occupation` returns ``None`` and the pipeline emits exactly what it
emitted before. An occupation with no enrichment must render as an occupation without a
description, never as an error and never as a blank claim.

**The cache records what it was fetched with.** The response is shaped by the query
parameters, so a cached entry fetched with a narrower parameter set is not a smaller version
of the current answer, it is a different answer with fields missing. Serving one would put
"this occupation reports no tasks" on a page when the truth is "nobody asked for tasks".
:func:`cache_envelope` stamps every entry with the exact request that produced it and
:func:`_read_cache` refuses anything that does not match, so widening
:data:`REQUEST_PARAMS` invalidates the cache by construction rather than by anyone
remembering to clear it.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

import httpx

from camino.sources.dol_etp import USER_AGENT, FetchError, get_with_retry
from camino.sources.soc_vintage import AGGREGATIONS

BASE_URL = "https://api.careeronestop.org/v1"
REQUEST_TIMEOUT = 45.0
PAUSE_BETWEEN_CALLS = 0.3
"""One occupation per call and ~670 occupations, so pace it. This is a public service."""

TOP_SKILLS = 6
TOP_TASKS = 8
RELATED_LIMIT = 8
ALTERNATE_TITLE_LIMIT = 20

REQUEST_PARAMS: Final[MappingProxyType[str, str]] = MappingProxyType(
    {
        # Fetched and used.
        "relatedOnetTitles": "true",
        "skills": "true",
        "tasks": "true",
        "alternateOnetTitles": "true",
        "training": "true",  # the only switch that returns EducationTraining
        # Deliberately not fetched. See docs/enrichment-expansion-2026-08-04.md for the
        # argument on each; the short version is that wages and projections would restate a
        # national figure next to the California one this project already publishes from
        # EDD, and knowledge/ability/interest add a second and third unlabelled 1-5 rating
        # scale to a page that already carries one.
        "wages": "false",
        "projectedEmployment": "false",
        "knowledge": "false",
        "ability": "false",
        "interest": "false",
        "videos": "false",
    }
)
"""The exact query this module sends. Also the cache key -- change it and the cache misses."""

CACHE_FORMAT: Final = 2
"""Bumped when the envelope's own shape changes, independently of the parameters."""

USER_ID_ENV = "CAREERONESTOP_USER_ID"
# The name of the variable to read, not a credential. Real values live only in a gitignored
# .env.local and must never appear in this repository.
TOKEN_ENV = "CAREERONESTOP_TOKEN"  # noqa: S105  # nosec B105 - variable name, not a secret


def credentials() -> tuple[str, str] | None:
    """Return (user_id, token) from the environment, or None when unconfigured."""
    user_id = os.environ.get(USER_ID_ENV, "").strip()
    token = os.environ.get(TOKEN_ENV, "").strip()
    return (user_id, token) if user_id and token else None


def build_client(token: str) -> httpx.Client:
    """A client carrying the API credential, for callers fetching more than one occupation.

    The whole occupation set is one call each, so a build shares a single client rather than
    standing up a connection per occupation. The token reaches the header and nothing else:
    it is never logged, echoed, or written to the cache.
    """
    return httpx.Client(
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Authorization": f"Bearer {token}"},
    )


def onet_code(soc_code: str) -> str:
    """Map a 6-digit SOC to the base O*NET code the API expects.

    EDD publishes ``29-1141``; CareerOneStop wants ``29-1141.00`` and returns 404 for the
    bare SOC. ``.00`` is the base occupation -- O*NET's ``.01``/``.02`` variants are
    specialisations this project does not distinguish.
    """
    return soc_code if "." in soc_code else f"{soc_code}.00"


def _soc_from_mat(value: Any) -> str | None:
    """Read BLS's 6-digit matrix occupation code back as ``XX-XXXX``.

    ``MatOccCode`` is the occupation the education figures were actually measured for, which
    is not always the occupation asked about. Anything that is not six digits returns None
    rather than a guess, because this code's whole job is to let a caller check the figures
    describe the population it is about to attach them to.
    """
    digits = str(value).strip() if value is not None else ""
    return f"{digits[:2]}-{digits[2:]}" if len(digits) == 6 and digits.isdigit() else None


_AGGREGATE_MEMBERS: Final[MappingProxyType[str, tuple[str, ...]]] = MappingProxyType(
    {
        target: tuple(sorted(src for src, agg in AGGREGATIONS.items() if agg.target == target))
        for target in sorted({agg.target for agg in AGGREGATIONS.values()})
    }
)
"""Each aggregate EDD publishes, and the detailed occupations it is published in place of.

Inverted from :data:`camino.sources.soc_vintage.AGGREGATIONS` rather than restated, so the
two cannot drift. Every one of these codes 404s on this API -- they are BLS publication
aggregates and BLS hybrids, not O*NET occupations -- which is why an occupation page for one
carries no description and no skills. See :func:`_aggregate_education`.
"""


@dataclass(frozen=True)
class Skill:
    name: str
    importance: float | None


@dataclass(frozen=True)
class Task:
    """One concrete thing a person in this occupation does.

    ``importance`` is O*NET's rating of the task within the occupation, or None when the
    task carries no rating. None is not zero: an unrated task is not an unimportant one.
    """

    description: str
    importance: float | None


@dataclass(frozen=True)
class EducationLevelShare:
    """The share of workers in an occupation holding one level of education.

    ``percent`` may legitimately be ``0.0`` -- a level nobody in the occupation holds is a
    measured result. ``None`` is the different claim that no figure was published for that
    level, and the two must never be collapsed.
    """

    level: str
    percent: float | None


@dataclass(frozen=True)
class EducationProfile:
    """What BLS reports about how people actually enter this occupation.

    ``distribution`` is the education workers in the occupation *hold*, in BLS's own level
    order (least to most). It is a population measurement, not a requirement: 25.6% of
    registered nurses hold an associate's degree, which is a fact about who is doing the job
    rather than a statement about who is allowed to.

    ``typical_experience`` and ``typical_on_the_job_training`` are BLS's single-category
    assignments for prior related experience and post-hire training. They matter to a
    training decision in a way the credential category does not: "Apprenticeship" or "5 years
    or more" means the classroom certificate on offer is not by itself the route in.

    ``reported_for_soc`` is the occupation BLS measured, taken from ``MatOccCode``. It is not
    always the occupation that was asked about, and a caller attaching this to a page must
    check it: these figures are published per BLS matrix occupation, so the detailed O*NET
    occupations inside an aggregate all return the aggregate's single distribution.

    Everything here is national. EDD supplies the California figures this project prefers,
    and EDD does not publish this distribution.
    """

    distribution: tuple[EducationLevelShare, ...]
    typical_experience: str | None
    typical_on_the_job_training: str | None
    reported_for_soc: str | None
    reported_for_title: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "distribution": [
                {"level": share.level, "percent": share.percent} for share in self.distribution
            ],
            "typical_experience": self.typical_experience,
            "typical_on_the_job_training": self.typical_on_the_job_training,
            "reported_for_soc": self.reported_for_soc,
            "reported_for_title": self.reported_for_title,
        }


@dataclass(frozen=True)
class OccupationEnrichment:
    """What CareerOneStop adds to an occupation this project already knows about.

    Every field added after the first release carries a default, because callers construct
    this directly in their own tests and a required field would break them.
    """

    soc_code: str
    onet_code: str | None
    description: str | None
    skills: tuple[Skill, ...]
    related: tuple[tuple[str, str], ...]
    """(soc_code, title) pairs from O*NET's own related-occupation list."""
    bright_outlook: str | None
    tasks: tuple[Task, ...] = ()
    alternate_titles: tuple[str, ...] = ()
    """Titles the same work is advertised under. "RN" should find Registered Nurses."""
    education: EducationProfile | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def as_dict(self) -> dict[str, Any]:
        return {
            "onet_code": self.onet_code,
            "description": self.description,
            "skills": [{"name": s.name, "importance": s.importance} for s in self.skills],
            "related_onet": [{"soc_code": code, "title": title} for code, title in self.related],
            "bright_outlook": self.bright_outlook,
            "tasks": [
                {"description": t.description, "importance": t.importance} for t in self.tasks
            ],
            "alternate_titles": list(self.alternate_titles),
            "education": self.education.as_dict() if self.education is not None else None,
        }


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _number(value: Any) -> float | None:
    """Parse an API number. Blank and unparseable both mean absent, never zero.

    A parsed ``0`` is kept as ``0.0``: the education distribution genuinely reports levels at
    ``0`` and at ``.5``, and folding either into None would delete a measurement.
    """
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rank(importance: float | None) -> tuple[int, float]:
    """Sort key: rated before unrated, then most important first.

    Unrated sorts last rather than as zero, which would rank it below something genuinely
    rated as unimportant -- a different and false claim. Written as an explicit two-part key
    rather than ``-(importance or 0)`` so a real ``0.0`` rating cannot be caught by
    truthiness and treated as missing.
    """
    return (1, 0.0) if importance is None else (0, -importance)


def _parse_skills(detail: dict[str, Any]) -> tuple[Skill, ...]:
    skills = [
        Skill(name=name, importance=_number(entry.get("DataValue")))
        for entry in detail.get("SkillsDataList") or []
        if (name := _text(entry.get("ElementName")))
    ]
    skills.sort(key=lambda s: _rank(s.importance))
    return tuple(skills[:TOP_SKILLS])


def _parse_tasks(detail: dict[str, Any]) -> tuple[Task, ...]:
    """The concrete work, most important first.

    The API returns tasks in no useful order -- 29-1141's first entry is rated below its
    third -- so this ranks them. A page cannot show 41 of them, and showing the first eight
    the API happened to list would be an arbitrary sample presented as a summary.
    """
    tasks = [
        Task(description=described, importance=_number(entry.get("DataValue")))
        for entry in detail.get("Tasks") or []
        if (described := _text(entry.get("TaskDescription")))
    ]
    tasks.sort(key=lambda t: _rank(t.importance))
    return tuple(tasks[:TOP_TASKS])


def _parse_alternate_titles(detail: dict[str, Any]) -> tuple[str, ...]:
    """Alternate titles, de-duplicated case-insensitively, in the API's order.

    The order is O*NET's and is left alone. These exist to be matched against, not read, so
    the limit is generous: truncating hard is how the one alias somebody actually types gets
    dropped.
    """
    seen: dict[str, str] = {}
    for entry in detail.get("AlternateTitles") or []:
        title = _text(entry)
        if title is not None:
            seen.setdefault(title.casefold(), title)
    return tuple(list(seen.values())[:ALTERNATE_TITLE_LIMIT])


def _parse_education(detail: dict[str, Any]) -> EducationProfile | None:
    """Read the ``EducationTraining`` block, or None when the API published none.

    Levels are kept in the order given, which is BLS's own least-to-most ordering; sorting
    by share would destroy the only thing that makes the numbers readable as a distribution.
    A level with no published value is kept with ``percent=None`` rather than dropped, so a
    consumer can tell a suppressed cell from a level that was never listed.
    """
    block = detail.get("EducationTraining")
    if not isinstance(block, dict):
        return None

    distribution = tuple(
        EducationLevelShare(level=level, percent=_number(entry.get("Value")))
        for entry in block.get("EducationType") or []
        if (level := _text(entry.get("EducationLevel")))
    )
    matrix = block.get("MatOccupation")
    matrix = matrix if isinstance(matrix, dict) else {}
    profile = EducationProfile(
        distribution=distribution,
        typical_experience=_text(block.get("ExperienceTitle")),
        typical_on_the_job_training=_text(block.get("TrainingTitle")),
        reported_for_soc=_soc_from_mat(matrix.get("MatOccCode")),
        reported_for_title=_text(matrix.get("MatOccTitle")),
    )
    empty = not distribution and profile.typical_experience is None
    return None if empty and profile.typical_on_the_job_training is None else profile


def parse_occupation(soc_code: str, payload: dict[str, Any]) -> OccupationEnrichment | None:
    details = payload.get("OccupationDetail")
    if not isinstance(details, list) or not details:
        return None
    detail = details[0]

    related: list[tuple[str, str]] = []
    raw_related = detail.get("RelatedOnetTitles")
    if isinstance(raw_related, dict):
        for code, title in raw_related.items():
            soc = str(code).split(".")[0]
            name = _text(title)
            if name and soc != soc_code:
                related.append((soc, name))

    return OccupationEnrichment(
        soc_code=soc_code,
        onet_code=_text(detail.get("OnetCode")),
        description=_text(detail.get("OnetDescription")),
        skills=_parse_skills(detail),
        related=tuple(related[:RELATED_LIMIT]),
        bright_outlook=_text(detail.get("BrightOutlookCategory")),
        tasks=_parse_tasks(detail),
        alternate_titles=_parse_alternate_titles(detail),
        education=_parse_education(detail),
    )


def fetch_occupation(
    soc_code: str,
    *,
    state: str = "CA",
    client: httpx.Client | None = None,
    cache_dir: Path | None = None,
) -> OccupationEnrichment | None:
    """Fetch enrichment for one occupation, or None if unconfigured or unavailable.

    Returns None rather than raising when the API has nothing for a SOC. Not every
    occupation EDD projects has a CareerOneStop entry, and a missing description is a gap in
    the page, not a failure of the build.

    The twelve aggregates EDD publishes in place of detailed occupations have no O*NET entry
    at all and 404 here. For those, and only for those, this falls back to
    :func:`_aggregate_education` -- see there for why that is a lookup rather than a
    substitution.
    """
    creds = credentials()
    if creds is None:
        return None
    user_id, token = creds

    owns_client = client is None
    http = client or build_client(token)
    try:
        payload = _fetch_payload(
            onet_code(soc_code), state=state, user_id=user_id, http=http, cache_dir=cache_dir
        )
        if payload is not None:
            return parse_occupation(soc_code, payload)
        education = _aggregate_education(
            soc_code, state=state, user_id=user_id, http=http, cache_dir=cache_dir
        )
        if education is None:
            return None
        # Every other field is deliberately empty. See _aggregate_education.
        return OccupationEnrichment(
            soc_code=soc_code,
            onet_code=None,
            description=None,
            skills=(),
            related=(),
            bright_outlook=None,
            education=education,
        )
    finally:
        if owns_client:
            http.close()


def _fetch_payload(
    code: str,
    *,
    state: str,
    user_id: str,
    http: httpx.Client,
    cache_dir: Path | None,
) -> dict[str, Any] | None:
    """One occupation's raw response, from the cache or the API. None means no entry."""
    cached = _read_cache(cache_dir, code, state)
    if cached is not None:
        return cached
    try:
        response = get_with_retry(
            http,
            f"{BASE_URL}/occupation/{user_id}/{code}/{state}",
            params=dict(REQUEST_PARAMS),
        )
    except FetchError as exc:
        # 404 means "no entry for this occupation", which is ordinary. Anything else is
        # worth knowing about, but still must not take the build down.
        if exc.status_code != 404:
            print(f"careeronestop: {code} unavailable ({exc})")
        return None
    payload: dict[str, Any] = response.json()
    _write_cache(cache_dir, code, state, payload)
    time.sleep(PAUSE_BETWEEN_CALLS)
    return payload


def _aggregate_education(
    soc_code: str,
    *,
    state: str,
    user_id: str,
    http: httpx.Client,
    cache_dir: Path | None,
) -> EducationProfile | None:
    """The education profile for an aggregate EDD publishes, read via one of its members.

    This is a lookup, not a substitution, and the difference is the whole justification.
    BLS publishes education attainment per *matrix* occupation, and for every detailed
    occupation inside one of these aggregates the matrix occupation **is the aggregate**:
    21-1011 and 21-1014 both return the identical distribution stamped
    ``MatOccCode: 211018``. So the figures fetched here were never the member's own -- they
    are the aggregate's, which is exactly the population EDD's wage and opening counts for
    that aggregate describe.

    That equality is checked rather than assumed: a member whose ``MatOccCode`` is not this
    aggregate is discarded and the next member tried. Nothing else from the member's
    response is used. Its description, tasks and skills *are* the member's own, and putting
    Home Health Aides' tasks on a Home Health and Personal Care Aides page would be the
    substitution this function is careful not to make.
    """
    for member in _AGGREGATE_MEMBERS.get(soc_code, ()):
        payload = _fetch_payload(
            onet_code(member), state=state, user_id=user_id, http=http, cache_dir=cache_dir
        )
        if payload is None:
            continue
        details = payload.get("OccupationDetail")
        if not isinstance(details, list) or not details:
            continue
        education = _parse_education(details[0])
        if education is not None and education.reported_for_soc == soc_code:
            return education
    return None


def cache_envelope(payload: dict[str, Any], *, onet_code: str, state: str) -> dict[str, Any]:
    """Wrap a response in the record of the request that produced it.

    Public because anything that writes a cache entry by hand -- a test, a fixture, a
    backfill script -- has to write one this module will accept, and duplicating the shape
    is how the two drift apart.
    """
    return {
        "cache_format": CACHE_FORMAT,
        "request": {"onet_code": onet_code, "state": state, "params": dict(REQUEST_PARAMS)},
        "response": payload,
    }


def _cache_path(cache_dir: Path | None, code: str) -> Path | None:
    if cache_dir is None:
        return None
    return cache_dir / f"{code.replace('/', '_')}.json"


def _read_cache(cache_dir: Path | None, code: str, state: str) -> dict[str, Any] | None:
    """A cached response, but only one fetched with exactly the request being made now.

    An entry that does not say what it was fetched with, or that says something different,
    is a miss. That includes every entry written before this module asked for tasks,
    alternate titles and education: those responses are missing fields the current request
    asks for, and a missing field would reach a page as "this occupation reports no tasks"
    rather than "nobody asked". Refetching costs one throttled request; the alternative is a
    false statement on a public page.
    """
    path = _cache_path(cache_dir, code)
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
    fetched_with = (request.get("onet_code"), request.get("state"), request.get("params"))
    if fetched_with != (code, state, dict(REQUEST_PARAMS)):
        return None
    response = loaded.get("response")
    return response if isinstance(response, dict) else None


def _write_cache(cache_dir: Path | None, code: str, state: str, payload: dict[str, Any]) -> None:
    path = _cache_path(cache_dir, code)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    envelope = cache_envelope(payload, onet_code=code, state=state)
    path.write_text(json.dumps(envelope), encoding="utf-8")
