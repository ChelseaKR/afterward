"""Client for O*NET Web Services (USDOL/ETA).

Source D5 in PROVENANCE.md. This is the direct O*NET API, as distinct from the O*NET content
that already reaches this project second-hand through CareerOneStop (D6).

**Attribution is a licence condition, not a courtesy.** The O*NET Web Services Data License
requires any product using the Services to credit and link to O*NET. The exact string the
site must display is :data:`ATTRIBUTION`, and it must not be removed while any field derived
from this module is on screen. See "Notes on D5" in PROVENANCE.md.

Four things shape this module.

**The credential never enters the repository.** The API wants an ``X-API-Key`` header, read
from the environment (``ONET_API_KEY``, conventionally via a gitignored ``.env.local``). It is
build-time only and never reaches the browser, since the site ships as static files.

**Enrichment is optional by design.** CI has no key and must still build. With none
configured :func:`fetch_profiles` returns an empty mapping and the pipeline emits exactly
what it emitted before. An occupation with no O*NET profile must render as an occupation
without tasks, never as an error.

**Bulk tables, not 670 per-occupation calls.** The occupation records are HATEOAS -- each one
links its sub-resources by ``href`` -- and reading tasks, tools, job zone and reported titles
that way costs four requests per occupation, some 2,700 for California's 670. The same four
things are published whole under ``/database/rows/``, and the whole set costs 61 requests. The
tables are served in the same order as the per-occupation views (verified against
``details/tasks``: identical set *and* identical importance ordering for 29-1141.00), so this
is cheaper without being different. Same reasoning as ``dol_etp``: a public service funded by
taxpayers is not a firehose.

**Spanish is the point.** O*NET runs *Mi Próximo Paso* at ``/mpp/``, and it serves Spanish
occupation titles and descriptions for every one of the 923 occupations O*NET holds data for
-- set-identical to the coverage of the English tables above, so there is no field this
project can show in English and not in Spanish. That is the one thing here that fixes a real
defect rather than adding a feature: the site's Spanish pages currently render occupation
titles and descriptions in English. Spanish has no bulk table, so it is the one thing fetched
per occupation -- throttled, serialised, and cached.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from afterward.sources.dol_etp import USER_AGENT, FetchError, get_with_retry

BASE_URL = "https://api-v2.onetcenter.org"
"""The v2 host. The older ``services.onetcenter.org`` answers 401 to everything, key or not."""

REQUEST_TIMEOUT = 45.0
PAUSE_BETWEEN_CALLS = 0.3
"""Deliberate throttle, and nothing here fetches in parallel. This is a public service."""

BULK_PAGE_SIZE = 1000
"""Largest ``start``/``end`` window the service accepts; 10,000 is refused with a 422."""

API_KEY_ENV = "ONET_API_KEY"
# The name of the variable to read, not a credential. The real value lives only in a
# gitignored .env.local and must never appear in this repository.

ATTRIBUTION = (
    "This site incorporates information from O*NET Web Services by the U.S. Department of "
    "Labor, Employment and Training Administration (USDOL/ETA). O*NET® is a trademark of "
    "USDOL/ETA."
)
"""The credit the O*NET Web Services Data License requires a product using it to display.

Must appear with a link to https://services.onetcenter.org/ wherever O*NET-derived fields are
shown. This is a licence obligation and is owed on the *published* site, not just in this
repository -- and it is owed for the CareerOneStop-sourced O*NET fields too, which is why the
notice predates this module.
"""

ATTRIBUTION_URL = "https://services.onetcenter.org/"

TOP_TASKS = 8
"""Enough to picture a working day; more and nobody reads it. O*NET lists up to 40."""

TOP_TECHNOLOGIES = 10
REPORTED_TITLE_LIMIT = 12
"""Caps the search index. O*NET publishes 8.6 reported titles per occupation on average."""

JOB_ZONE_TABLE = "job_zones"
JOB_ZONE_REFERENCE_TABLE = "job_zone_reference"
TASK_TABLE = "task_statements"
REPORTED_TITLE_TABLE = "sample_of_reported_titles"
TECHNOLOGY_TABLE = "software_skills"

MPP_CAREERS = f"{BASE_URL}/mpp/careers"
"""Mi Próximo Paso: the Spanish-language service, same occupation codes as the English one."""


def api_key() -> str | None:
    """Return the O*NET API key from the environment, or None when unconfigured."""
    key = os.environ.get(API_KEY_ENV, "").strip()
    return key or None


def build_client(key: str) -> httpx.Client:
    """A client carrying the API key, for callers reading more than one resource.

    A build shares a single client rather than standing one up per table. The key reaches the
    header and nothing else: it is never logged, echoed, or written to the cache.
    """
    return httpx.Client(
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
        headers={
            "User-Agent": USER_AGENT,
            "X-API-Key": key,
            "Accept": "application/json",
        },
    )


def onet_code(soc_code: str) -> str:
    """Map a 6-digit SOC to the base O*NET-SOC code.

    EDD publishes ``29-1141``; O*NET's taxonomy is ``29-1141.00``, with ``.01``/``.02``
    variants for specialisations this project does not distinguish. Deliberately a local
    definition rather than a shared one: this is O*NET's own taxonomy rule, and it is only a
    coincidence that CareerOneStop -- an O*NET front end -- needs the same mapping.
    """
    return soc_code if "." in soc_code else f"{soc_code}.00"


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _count(value: Any) -> float | None:
    """Parse a reported count. Blank and unparseable both mean absent, never zero.

    A survey count of zero and an unreported survey count are different facts, and the second
    must never be published as the first.
    """
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _flag(value: Any) -> bool:
    """Read O*NET's ``Y``/``N`` flag columns. Anything that is not ``Y`` is not a claim."""
    return _text(value) == "Y"


@dataclass(frozen=True)
class Task:
    """One thing people in this occupation actually do, as reported by incumbents."""

    title: str
    core: bool
    """O*NET's Core/Supplemental split. Core means central to the occupation."""
    incumbents_responding: float | None
    """How many surveyed workers answered about this task. None means not reported."""


@dataclass(frozen=True)
class Technology:
    """A named piece of software someone in this occupation is expected to use.

    The most concrete thing O*NET publishes, and the most useful for choosing a program: a
    course that never mentions Epic is a weak preparation for a hospital nursing job.
    """

    name: str
    category: str | None
    hot: bool
    """O*NET "Hot Technology": frequently named in current job postings."""
    in_demand: bool
    """O*NET "In Demand": named as a requirement rather than a nice-to-have."""


@dataclass(frozen=True)
class JobZone:
    """O*NET's 1-5 preparation level, with the prose that explains what the number means.

    More useful than a single "typically needs an associate's degree" line because it says
    what *else* is needed -- years of experience, on-the-job training, licensure -- which is
    exactly what decides whether a one-year programme is enough.
    """

    code: int
    title: str | None
    education: str | None
    experience: str | None
    training: str | None
    examples: str | None
    svp_range: str | None


@dataclass(frozen=True)
class SpanishOccupation:
    """Occupation text in Spanish, from Mi Próximo Paso.

    Only the professionally-translated fields are carried. Mi Próximo Paso also serves a
    Spanish task list, and it is machine-translated badly enough to be misleading -- see the
    assessment doc -- so it is deliberately not represented here.
    """

    title: str
    description: str | None
    also_called: tuple[str, ...]


@dataclass(frozen=True)
class OnetProfile:
    """What O*NET adds to an occupation this project already knows about."""

    soc_code: str
    onet_code: str
    reported_titles: tuple[str, ...]
    """Real-world job titles ("Staff RN", "Charge Nurse"), for search recall."""
    tasks: tuple[Task, ...]
    technologies: tuple[Technology, ...]
    job_zone: JobZone | None
    spanish: SpanishOccupation | None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def as_dict(self) -> dict[str, Any]:
        return {
            "onet_code": self.onet_code,
            "reported_titles": list(self.reported_titles),
            "tasks": [
                {
                    "title": t.title,
                    "core": t.core,
                    "incumbents_responding": t.incumbents_responding,
                }
                for t in self.tasks
            ],
            "technologies": [
                {
                    "name": t.name,
                    "category": t.category,
                    "hot": t.hot,
                    "in_demand": t.in_demand,
                }
                for t in self.technologies
            ],
            "job_zone": (
                None
                if self.job_zone is None
                else {
                    "code": self.job_zone.code,
                    "title": self.job_zone.title,
                    "education": self.job_zone.education,
                    "experience": self.job_zone.experience,
                    "training": self.job_zone.training,
                    "examples": self.job_zone.examples,
                    "svp_range": self.job_zone.svp_range,
                }
            ),
            "es": (
                None
                if self.spanish is None
                else {
                    "title": self.spanish.title,
                    "description": self.spanish.description,
                    "also_called": list(self.spanish.also_called),
                }
            ),
            "attribution": ATTRIBUTION,
        }


Rows = Sequence[dict[str, Any]]


def _index_by_code(rows: Rows) -> dict[str, list[dict[str, Any]]]:
    """Group bulk rows by O*NET-SOC code, preserving the order the service served them in.

    That order is load-bearing for tasks: the table arrives sorted by importance, matching
    the ``details/tasks`` view exactly, so preserving it means the top task really is the
    most important one rather than whichever happened to be listed first.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        code = _text(row.get("onetsoc_code"))
        if code:
            grouped.setdefault(code, []).append(row)
    return grouped


def parse_tasks(rows: Rows, *, limit: int = TOP_TASKS) -> tuple[Task, ...]:
    """Take the most important tasks, in the order O*NET published them.

    No re-sorting. The table is already in importance order and this module has no importance
    figure of its own; reordering Core ahead of Supplemental would look tidier and would
    quietly assert a ranking O*NET did not make.
    """
    tasks: list[Task] = []
    for row in rows:
        title = _text(row.get("task"))
        if not title:
            continue
        tasks.append(
            Task(
                title=title,
                core=_text(row.get("task_type")) == "Core",
                incumbents_responding=_count(row.get("incumbents_responding")),
            )
        )
        if len(tasks) >= limit:
            break
    return tuple(tasks)


def parse_technologies(rows: Rows, *, limit: int = TOP_TECHNOLOGIES) -> tuple[Technology, ...]:
    """Take the named tools, hot and in-demand ones first.

    Unlike tasks the source order here is alphabetical by product name, which carries no
    information, so ranking by O*NET's own currency flags is a genuine improvement rather
    than a re-interpretation. Ties keep source order, so the result is stable between builds.
    """
    seen: set[str] = set()
    parsed: list[Technology] = []
    for row in rows:
        name = _text(row.get("workplace_example"))
        if not name or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        parsed.append(
            Technology(
                name=name,
                category=_text(row.get("element_name")),
                hot=_flag(row.get("hot_technology")),
                in_demand=_flag(row.get("in_demand")),
            )
        )
    parsed.sort(key=lambda t: (not t.hot, not t.in_demand))
    return tuple(parsed[:limit])


def parse_reported_titles(rows: Rows, *, limit: int = REPORTED_TITLE_LIMIT) -> tuple[str, ...]:
    """Real job titles for the occupation, deduplicated, in published order."""
    seen: set[str] = set()
    titles: list[str] = []
    for row in rows:
        title = _text(row.get("reported_job_title"))
        if not title or title.casefold() in seen:
            continue
        seen.add(title.casefold())
        titles.append(title)
        if len(titles) >= limit:
            break
    return tuple(titles)


def parse_job_zones(rows: Rows, reference: Rows) -> dict[str, JobZone]:
    """Join each occupation's job-zone number to the prose describing that zone.

    The reference table publishes four rows, not five: O*NET merges zones 1 and 2 into a
    single "Job Zone 1-2" entry keyed on 2. An occupation rated 1 therefore has no matching
    description, and it keeps its number with empty prose rather than being dropped or
    silently promoted to zone 2. That branch is defensive rather than observed -- no
    occupation in O*NET 30.3 is rated zone 1 -- but promoting one to zone 2 would overstate
    the preparation a job needs, which is precisely the error this site cannot afford.
    """
    described: dict[int, dict[str, Any]] = {}
    for row in reference:
        zone = _count(row.get("job_zone"))
        if zone is not None:
            described[int(zone)] = row

    zones: dict[str, JobZone] = {}
    for row in rows:
        code = _text(row.get("onetsoc_code"))
        zone = _count(row.get("job_zone"))
        if code is None or zone is None:
            continue
        prose = described.get(int(zone), {})
        zones[code] = JobZone(
            code=int(zone),
            title=_text(prose.get("name")),
            education=_text(prose.get("education")),
            experience=_text(prose.get("experience")),
            training=_text(prose.get("job_training")),
            examples=_text(prose.get("examples")),
            svp_range=_text(prose.get("svp_range")),
        )
    return zones


def parse_spanish(payload: dict[str, Any]) -> SpanishOccupation | None:
    """Read a Mi Próximo Paso career record.

    Requires a title: a record with no Spanish title is nothing this project can show a
    Spanish-speaking reader, and returning a hollow object would let the site claim a
    translation it does not have.
    """
    title = _text(payload.get("title"))
    if title is None:
        return None
    also_called: list[str] = []
    seen: set[str] = set()
    for entry in payload.get("also_called") or []:
        name = _text(entry.get("title")) if isinstance(entry, dict) else _text(entry)
        if name and name.casefold() not in seen:
            seen.add(name.casefold())
            also_called.append(name)
    return SpanishOccupation(
        title=title,
        description=_text(payload.get("what_they_do")),
        also_called=tuple(also_called),
    )


def _cache_path(cache_dir: Path | None, name: str) -> Path | None:
    if cache_dir is None:
        return None
    return cache_dir / f"{name.replace('/', '_')}.json"


def _read_cache(cache_dir: Path | None, name: str) -> Any:
    """Responses are cached so a rebuild does not re-ask for data that has not changed."""
    path = _cache_path(cache_dir, name)
    if path is None or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache(cache_dir: Path | None, name: str, payload: Any) -> None:
    path = _cache_path(cache_dir, name)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def fetch_table(
    table: str,
    *,
    client: httpx.Client,
    cache_dir: Path | None = None,
    page_size: int = BULK_PAGE_SIZE,
) -> list[dict[str, Any]]:
    """Read one whole ``/database/rows/`` table, paginated and cached.

    Returns an empty list rather than raising if the table cannot be read. A missing table
    costs the site a section of an occupation page; it must not cost the whole build.
    """
    cached = _read_cache(cache_dir, f"table-{table}")
    if isinstance(cached, list):
        return cached

    rows: list[dict[str, Any]] = []
    start = 1
    while True:
        try:
            response = get_with_retry(
                client,
                f"{BASE_URL}/database/rows/{table}",
                params={"start": start, "end": start + page_size - 1},
            )
        except FetchError as exc:
            print(f"onet: table {table} unavailable ({exc})")
            return []
        payload = response.json()
        page = payload.get("row") or []
        rows.extend(page)
        # Pagination metadata, deliberately not run through _count: these are the envelope's
        # own cursors, not measures, and an absent one means "stop" rather than "not reported".
        # An empty page is the backstop, so a malformed envelope ends the loop instead of
        # spinning on it.
        end = _count(payload.get("end"))
        total = _count(payload.get("total"))
        if not page or end is None or total is None or end >= total:
            break
        start = int(end) + 1
        time.sleep(PAUSE_BETWEEN_CALLS)

    _write_cache(cache_dir, f"table-{table}", rows)
    return rows


def fetch_spanish(
    code: str,
    *,
    client: httpx.Client,
    cache_dir: Path | None = None,
) -> SpanishOccupation | None:
    """Fetch one occupation's Spanish record from Mi Próximo Paso, or None if it has none.

    Mi Próximo Paso covers 923 of O*NET's 1,016 occupations, so a 404 here is ordinary and
    means "no Spanish record", not "the build is broken".
    """
    cached = _read_cache(cache_dir, f"mpp-{code}")
    if isinstance(cached, dict):
        return parse_spanish(cached)

    try:
        response = get_with_retry(client, f"{MPP_CAREERS}/{code}/")
    except FetchError as exc:
        if exc.status_code != 404:
            print(f"onet: Spanish record for {code} unavailable ({exc})")
        return None

    payload = response.json()
    _write_cache(cache_dir, f"mpp-{code}", payload)
    time.sleep(PAUSE_BETWEEN_CALLS)
    return parse_spanish(payload)


def fetch_profiles(
    soc_codes: Iterable[str],
    *,
    client: httpx.Client | None = None,
    cache_dir: Path | None = None,
    spanish: bool = True,
) -> dict[str, OnetProfile]:
    """Fetch O*NET profiles for the given SOC codes, keyed by the code that was passed in.

    Returns an empty mapping when no key is configured, so a caller can write
    ``profiles.get(soc)`` unconditionally and CI can build with nothing set.

    Occupations O*NET does not carry are simply absent from the result. Twelve of
    California's 670 are broad SOC groups (``31-1120``, ``29-2010``) with no detailed O*NET
    occupation behind them, and inventing an empty profile for those would put an empty
    "What they do" heading on a page that has nothing to put under it.
    """
    key = api_key()
    if key is None:
        return {}

    owns_client = client is None
    http = client or build_client(key)
    try:
        tasks = _index_by_code(fetch_table(TASK_TABLE, client=http, cache_dir=cache_dir))
        technologies = _index_by_code(
            fetch_table(TECHNOLOGY_TABLE, client=http, cache_dir=cache_dir)
        )
        titles = _index_by_code(fetch_table(REPORTED_TITLE_TABLE, client=http, cache_dir=cache_dir))
        zones = parse_job_zones(
            fetch_table(JOB_ZONE_TABLE, client=http, cache_dir=cache_dir),
            fetch_table(JOB_ZONE_REFERENCE_TABLE, client=http, cache_dir=cache_dir),
        )

        profiles: dict[str, OnetProfile] = {}
        for soc_code in soc_codes:
            code = onet_code(soc_code)
            rows = tasks.get(code, [])
            tech_rows = technologies.get(code, [])
            title_rows = titles.get(code, [])
            zone = zones.get(code)
            if not (rows or tech_rows or title_rows or zone):
                continue
            profiles[soc_code] = OnetProfile(
                soc_code=soc_code,
                onet_code=code,
                reported_titles=parse_reported_titles(title_rows),
                tasks=parse_tasks(rows),
                technologies=parse_technologies(tech_rows),
                job_zone=zone,
                spanish=(
                    fetch_spanish(code, client=http, cache_dir=cache_dir) if spanish else None
                ),
            )
        return profiles
    finally:
        if owns_client:
            http.close()
