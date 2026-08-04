"""Client for the CareerOneStop Web API (U.S. Department of Labor).

Source D6 in PROVENANCE.md. Adds what neither the ETP scorecard nor EDD's projections carry:
a plain-language description of what an occupation actually involves, O*NET skill ratings,
and O*NET's own related-occupation list.

Two things shape this module.

**Credentials never enter the repository.** The API requires a user id and token, read from
the environment (``CAREERONESTOP_USER_ID`` / ``CAREERONESTOP_TOKEN``, conventionally via a
gitignored ``.env.local``). They are build-time only and never reach the browser, since the
site ships as static files.

**Enrichment is optional by design.** CI has no credentials and must still build. With none
configured, :func:`fetch_occupation` returns ``None`` and the pipeline emits exactly what it
emitted before. An occupation with no enrichment must render as an occupation without a
description, never as an error and never as a blank claim.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from camino.sources.dol_etp import USER_AGENT, FetchError, get_with_retry

BASE_URL = "https://api.careeronestop.org/v1"
REQUEST_TIMEOUT = 45.0
PAUSE_BETWEEN_CALLS = 0.3
"""One occupation per call and ~670 occupations, so pace it. This is a public service."""

TOP_SKILLS = 6
RELATED_LIMIT = 8

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
    bare SOC. ``.00`` is the base occupation — O*NET's ``.01``/``.02`` variants are
    specialisations this project does not distinguish.
    """
    return soc_code if "." in soc_code else f"{soc_code}.00"


@dataclass(frozen=True)
class Skill:
    name: str
    importance: float | None


@dataclass(frozen=True)
class OccupationEnrichment:
    """What CareerOneStop adds to an occupation this project already knows about."""

    soc_code: str
    onet_code: str | None
    description: str | None
    skills: tuple[Skill, ...]
    related: tuple[tuple[str, str], ...]
    """(soc_code, title) pairs from O*NET's own related-occupation list."""
    bright_outlook: str | None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def as_dict(self) -> dict[str, Any]:
        return {
            "onet_code": self.onet_code,
            "description": self.description,
            "skills": [{"name": s.name, "importance": s.importance} for s in self.skills],
            "related_onet": [{"soc_code": code, "title": title} for code, title in self.related],
            "bright_outlook": self.bright_outlook,
        }


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _number(value: Any) -> float | None:
    """Parse an API number. Blank and unparseable both mean absent, never zero."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_occupation(soc_code: str, payload: dict[str, Any]) -> OccupationEnrichment | None:
    details = payload.get("OccupationDetail")
    if not isinstance(details, list) or not details:
        return None
    detail = details[0]

    skills: list[Skill] = []
    for entry in detail.get("SkillsDataList") or []:
        name = _text(entry.get("ElementName"))
        if name:
            skills.append(Skill(name=name, importance=_number(entry.get("DataValue"))))
    # Most important first. Unrated skills sort last rather than being treated as zero
    # importance, which would silently rank them below a genuinely unimportant skill.
    skills.sort(key=lambda s: (s.importance is None, -(s.importance or 0.0)))

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
        skills=tuple(skills[:TOP_SKILLS]),
        related=tuple(related[:RELATED_LIMIT]),
        bright_outlook=_text(detail.get("BrightOutlookCategory")),
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
    """
    creds = credentials()
    if creds is None:
        return None
    user_id, token = creds

    code = onet_code(soc_code)
    cached = _read_cache(cache_dir, code)
    if cached is not None:
        return parse_occupation(soc_code, cached)

    owns_client = client is None
    http = client or build_client(token)
    try:
        response = get_with_retry(
            http,
            f"{BASE_URL}/occupation/{user_id}/{code}/{state}",
            params={
                "training": "false",
                "interest": "false",
                "videos": "false",
                "tasks": "false",
                "wages": "false",
                "projectedEmployment": "false",
                "relatedOnetTitles": "true",
                "skills": "true",
                "knowledge": "false",
                "ability": "false",
            },
        )
    except FetchError as exc:
        # 404 means "no entry for this occupation", which is ordinary. Anything else is
        # worth knowing about, but still must not take the build down.
        if exc.status_code != 404:
            print(f"careeronestop: {soc_code} unavailable ({exc})")
        return None
    finally:
        if owns_client:
            http.close()

    payload = response.json()
    _write_cache(cache_dir, code, payload)
    time.sleep(PAUSE_BETWEEN_CALLS)
    return parse_occupation(soc_code, payload)


def _cache_path(cache_dir: Path | None, code: str) -> Path | None:
    if cache_dir is None:
        return None
    return cache_dir / f"{code.replace('/', '_')}.json"


def _read_cache(cache_dir: Path | None, code: str) -> dict[str, Any] | None:
    """Responses are cached so a rebuild does not re-ask for data that has not changed."""
    path = _cache_path(cache_dir, code)
    if path is None or not path.exists():
        return None
    try:
        loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return loaded


def _write_cache(cache_dir: Path | None, code: str, payload: dict[str, Any]) -> None:
    path = _cache_path(cache_dir, code)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
