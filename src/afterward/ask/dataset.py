"""The published dataset, indexed for the service, and lexical resolution of free text against it.

The service never lets the model name a SOC code or an EDD area. A person says "warehouse" or
"Fresno"; the model hands those words back as terms; this module decides what they resolve to,
against the dataset's own titles, alternate titles, Spanish titles and area names, and reports
what it could not resolve. A term that resolves to nothing is a finding the reader sees, not a
gap the model fills.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_DATASET_DIR = Path("web/public/data")

OUTCOME_MEASURES = ("completion_rate", "employment_rate_q2", "median_earnings")
"""The three measures the site benchmarks and the service may compare (``peer_medians``)."""

_STOPWORDS = frozenset(
    {
        # English
        "a", "an", "and", "the", "of", "in", "for", "to", "or", "all", "other", "except",
        "job", "jobs", "work", "worker", "workers",
        # Spanish
        "de", "del", "la", "el", "los", "las", "y", "o", "en", "para", "trabajo", "trabajos",
        "trabajador", "trabajadores", "otros", "otras",
    }
)  # fmt: skip


def normalize(text: str) -> str:
    """Lowercase, strip accents and punctuation. ``Técnico`` and ``tecnico`` should meet."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", stripped.lower()).strip()


def tokens(text: str) -> frozenset[str]:
    return frozenset(t for t in normalize(text).split() if t and t not in _STOPWORDS)


def stems(text: str) -> frozenset[str]:
    return frozenset(_stem(t) for t in tokens(text))


@dataclass(frozen=True)
class OccupationHit:
    """An occupation a free-text term resolved to, and how well."""

    soc_code: str
    title: str
    score: float
    matched: str
    """The vocabulary entry that matched: the title, an alternate title, or a Spanish title."""


@dataclass(frozen=True)
class RegionHit:
    """An EDD area, or a city the dataset places programs in, that a term resolved to."""

    term: str
    area_name: str | None
    area_short_name: str | None
    city: str | None
    matched_on: str
    """``"area"`` when an EDD projection area matched; ``"city"`` when only a program city did."""


@dataclass(frozen=True)
class _VocabularyEntry:
    soc_code: str
    text: str
    normalized: str
    stems: frozenset[str]
    weight: float


@dataclass
class Dataset:
    """The three published files plus the indexes the executor and resolver need."""

    snapshot_date: str
    is_fixture: bool
    programs: dict[str, dict[str, Any]]
    occupations: dict[str, dict[str, Any]]
    coverage: dict[str, Any]
    programs_by_soc: dict[str, list[str]] = field(default_factory=dict)
    areas: list[dict[str, str]] = field(default_factory=list)
    cities: dict[str, str] = field(default_factory=dict)
    _vocabulary: list[_VocabularyEntry] = field(default_factory=list, repr=False)

    @classmethod
    def load(cls, dataset_dir: Path = DEFAULT_DATASET_DIR) -> Dataset:
        programs_doc = _read(dataset_dir / "programs.json")
        occupations_doc = _read(dataset_dir / "occupations.json")
        coverage = _read(dataset_dir / "coverage.json")
        return cls.from_documents(programs_doc, occupations_doc, coverage)

    @classmethod
    def from_documents(
        cls,
        programs_doc: Mapping[str, Any],
        occupations_doc: Mapping[str, Any],
        coverage: Mapping[str, Any],
    ) -> Dataset:
        programs = {p["uuid"]: p for p in programs_doc["programs"]}
        occupations = dict(occupations_doc["occupations"])
        dataset = cls(
            snapshot_date=str(coverage.get("snapshot_date", programs_doc.get("snapshot_date"))),
            is_fixture=bool(coverage.get("is_fixture", False)),
            programs=programs,
            occupations=occupations,
            coverage=dict(coverage),
        )
        dataset._index()
        return dataset

    def _index(self) -> None:
        by_soc: dict[str, list[str]] = {}
        areas: dict[str, dict[str, str]] = {}
        cities: dict[str, str] = {}
        for uuid, program in self.programs.items():
            for occ in program.get("occupations") or []:
                by_soc.setdefault(occ["soc_code"], []).append(uuid)
            region = program.get("region")
            if region:
                areas.setdefault(region["area_name"], dict(region))
            city = (program.get("location") or {}).get("city")
            if city:
                cities[normalize(city)] = city
        for occupation in self.occupations.values():
            for row in occupation.get("regions") or []:
                areas.setdefault(
                    row["area_name"],
                    {"area_name": row["area_name"], "area_type": row.get("area_type", "")},
                )
        self.programs_by_soc = {soc: sorted(ids) for soc, ids in by_soc.items()}
        self.areas = sorted(areas.values(), key=lambda a: a["area_name"])
        self.cities = cities
        self._vocabulary = list(_vocabulary(self.occupations))

    # -- occupations ---------------------------------------------------------------------

    def resolve_occupations(self, term: str, *, limit: int = 5) -> list[OccupationHit]:
        """Occupations a term names, best first. Empty when nothing in the vocabulary matches.

        Lexical on purpose: a title match, an alternate-title match, a Spanish-title match,
        or a token overlap, each scored so an exact title outranks a partial one. No model,
        no embeddings, nothing that could return an occupation the dataset does not carry.
        """
        needle = normalize(term)
        needle_stems = stems(term)
        if not needle:
            return []
        best: dict[str, OccupationHit] = {}
        for entry in self._vocabulary:
            score = _score(needle, needle_stems, entry)
            if score <= 0:
                continue
            current = best.get(entry.soc_code)
            if current is None or score > current.score:
                title = self.occupations[entry.soc_code]["title"]
                best[entry.soc_code] = OccupationHit(entry.soc_code, title, score, entry.text)
        ranked = sorted(best.values(), key=lambda h: (-h.score, h.soc_code))
        return ranked[:limit]

    def occupation(self, soc_code: str) -> dict[str, Any] | None:
        return self.occupations.get(soc_code)

    # -- regions -------------------------------------------------------------------------

    def resolve_region(self, term: str) -> RegionHit | None:
        """The EDD area a term names, or failing that a city the dataset places programs in.

        An area is preferred because it is what the projections are published by. A city
        match filters programs but cannot select a regional projection row, and the hit says
        which it is so the narration can say so too. ``None`` means the dataset does not cover
        the place, and that is the answer -- not the nearest area.
        """
        needle_tokens = tokens(term)
        if not needle_tokens:
            return None
        for area in self.areas:
            if needle_tokens <= tokens(area["area_name"]):
                return RegionHit(
                    term=term,
                    area_name=area["area_name"],
                    area_short_name=area.get("area_short_name") or _short(area["area_name"]),
                    city=None,
                    matched_on="area",
                )
        city = self.cities.get(normalize(term))
        if city is not None:
            return RegionHit(
                term=term, area_name=None, area_short_name=None, city=city, matched_on="city"
            )
        return None

    def area_names(self) -> list[str]:
        return [a["area_name"] for a in self.areas]

    # -- programs ------------------------------------------------------------------------

    def programs_for(self, soc_codes: Iterable[str]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for soc in soc_codes:
            for uuid in self.programs_by_soc.get(soc, []):
                if uuid not in seen:
                    seen.add(uuid)
                    out.append(self.programs[uuid])
        return out

    def program(self, uuid: str) -> dict[str, Any] | None:
        return self.programs.get(uuid)

    def peer_medians(self) -> dict[str, dict[str, Any]]:
        """The site's own comparison basis. The only benchmark the service ever offers."""
        peers = self.coverage.get("peer_medians") or {}
        return {measure: dict(peers[measure]) for measure in OUTCOME_MEASURES if measure in peers}


def _read(path: Path) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return doc


def _short(area_name: str) -> str:
    return area_name.split(" (", 1)[0]


def _vocabulary(occupations: Mapping[str, Mapping[str, Any]]) -> Iterable[_VocabularyEntry]:
    for soc, occupation in occupations.items():
        yield _entry(soc, occupation["title"], 1.0)
        for alternate in occupation.get("alternate_titles") or []:
            yield _entry(soc, alternate, 0.9)
        spanish = occupation.get("spanish") or {}
        if spanish.get("title"):
            yield _entry(soc, spanish["title"], 1.0)
        for also in spanish.get("also_called") or []:
            yield _entry(soc, also, 0.9)


def _entry(soc: str, text: str, weight: float) -> _VocabularyEntry:
    # Alternate titles often carry a parenthesised abbreviation: "Registered Nurse (RN)".
    # Index the abbreviation too, so "RN" resolves, but keep the full text as what matched.
    return _VocabularyEntry(soc, text, normalize(text), stems(text) | _abbreviations(text), weight)


def _abbreviations(text: str) -> frozenset[str]:
    return frozenset(normalize(m) for m in re.findall(r"\(([^)]{1,12})\)", text))


def _score(needle: str, needle_stems: frozenset[str], entry: _VocabularyEntry) -> float:
    if needle == entry.normalized:
        return entry.weight
    if not needle_stems or not entry.stems:
        return 0.0
    if needle_stems <= entry.stems:
        # Every word the person said is in this title: "dental assistant" meets
        # "Dental Assistants", and the closer the title is to only those words the better.
        return entry.weight * (0.6 + 0.3 * len(needle_stems) / len(entry.stems))
    overlap = len(needle_stems & entry.stems)
    if overlap == 0:
        return 0.0
    return entry.weight * 0.5 * overlap / len(needle_stems | entry.stems)


def _stem(token: str) -> str:
    # Enough morphology to let "nurses" meet "nurse" and "enfermeras" meet "enfermera";
    # not a stemmer, and not trying to be one. Applied to both sides of every comparison,
    # so it only has to be consistent, not correct: "nurses" and "nurse" both become "nurs".
    if len(token) > 4 and token.endswith("s"):
        token = token[:-1]
    if len(token) > 4 and token.endswith("e"):
        token = token[:-1]
    # Spanish gender: "enfermero" and "enfermera" are one occupation.
    if len(token) > 5 and token[-1] in "oa":
        token = token[:-1]
    return token
