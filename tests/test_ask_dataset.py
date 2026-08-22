"""Free text resolves against the dataset's own vocabulary, and against nothing else.

The service never lets a model name a SOC code or an EDD area. Everything a person says is a
term, and this module is what decides what a term means. These tests hold the two properties
that matter: a term that names something in the dataset resolves to it, and a term that names
nothing resolves to nothing -- never to the nearest plausible thing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from afterward.ask.dataset import Dataset, normalize, stems, tokens

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "data"


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(FIXTURE_DIR)


class TestLoading:
    def test_loads_the_three_published_files(self, dataset: Dataset) -> None:
        assert dataset.is_fixture is True
        assert len(dataset.programs) == 60
        assert len(dataset.occupations) == 56
        assert dataset.snapshot_date

    def test_indexes_programs_by_every_soc_they_lead_to(self, dataset: Dataset) -> None:
        programs = json.loads((FIXTURE_DIR / "programs.json").read_text())["programs"]
        expected = {oc["soc_code"] for p in programs for oc in p["occupations"]}
        assert set(dataset.programs_by_soc) == expected
        for soc, ids in dataset.programs_by_soc.items():
            for uuid in ids:
                assert any(oc["soc_code"] == soc for oc in dataset.programs[uuid]["occupations"])

    def test_areas_come_from_programs_and_occupation_rows(self, dataset: Dataset) -> None:
        names = dataset.area_names()
        assert names == sorted(names)
        assert any("Los Angeles" in n for n in names)

    def test_peer_medians_are_the_site_s_own(self, dataset: Dataset) -> None:
        peers = dataset.peer_medians()
        assert set(peers) == {"completion_rate", "employment_rate_q2", "median_earnings"}
        assert all("reporting" in p for p in peers.values())

    def test_from_documents_without_snapshot_in_coverage(self) -> None:
        d = Dataset.from_documents(
            {"snapshot_date": "2026-01-01", "programs": []},
            {"occupations": {}},
            {},
        )
        assert d.snapshot_date == "2026-01-01"
        assert d.peer_medians() == {}


class TestNormalisation:
    def test_accents_and_case_and_punctuation_fold(self) -> None:
        assert normalize("Técnico, Médico!") == "tecnico medico"

    def test_stopwords_drop_in_both_languages(self) -> None:
        assert tokens("Drafters, All Other") == {"drafters"}
        assert tokens("Trabajadores de la Construcción") == {"construccion"}

    def test_stems_meet_plurals_and_gender(self) -> None:
        assert stems("nurses") == stems("nurse")
        assert stems("enfermeras") == stems("enfermero")


class TestOccupationResolution:
    """A term that names an occupation finds it; a term that names nothing finds nothing."""

    def test_exact_title(self, dataset: Dataset) -> None:
        hits = dataset.resolve_occupations("Veterinary Assistants and Laboratory Animal Caretakers")
        assert hits[0].soc_code == "31-9096"
        assert hits[0].score == 1.0

    def test_everyday_words_meet_the_title(self, dataset: Dataset) -> None:
        hits = dataset.resolve_occupations("veterinary assistant")
        assert hits[0].soc_code == "31-9096"

    def test_alternate_title_resolves(self, dataset: Dataset) -> None:
        hits = dataset.resolve_occupations("Accounts Payable Clerk")
        assert hits and hits[0].matched == "Accounts Payable Clerk"

    def test_spanish_title_resolves(self, dataset: Dataset) -> None:
        spanish = next(
            (soc, o["spanish"]["title"])
            for soc, o in dataset.occupations.items()
            if o.get("spanish") and o["spanish"].get("title")
        )
        hits = dataset.resolve_occupations(spanish[1])
        assert hits[0].soc_code == spanish[0]

    def test_abbreviation_in_parentheses_resolves(self, dataset: Dataset) -> None:
        # Alternate titles carry "(ACG)"-style abbreviations; the abbreviation alone finds it.
        hits = dataset.resolve_occupations("ACG")
        assert hits and "(ACG)" in hits[0].matched

    def test_nothing_resolves_to_nothing(self, dataset: Dataset) -> None:
        assert dataset.resolve_occupations("xyzzy plugh") == []
        assert dataset.resolve_occupations("") == []
        assert dataset.resolve_occupations("the of and") == []

    def test_limit_and_ordering(self, dataset: Dataset) -> None:
        hits = dataset.resolve_occupations("assistant", limit=2)
        assert len(hits) == 2
        assert hits[0].score >= hits[1].score

    def test_lookup_by_code(self, dataset: Dataset) -> None:
        assert dataset.occupation("31-9096") is not None
        assert dataset.occupation("00-0000") is None


class TestRegionResolution:
    """An EDD area or a program city, or honestly nothing. Never the nearest area."""

    def test_area_by_principal_city(self, dataset: Dataset) -> None:
        hit = dataset.resolve_region("Los Angeles")
        assert hit is not None and hit.matched_on == "area"
        assert hit.area_name and hit.area_name.startswith("Los Angeles")
        assert hit.area_short_name == "Los Angeles-Long Beach-Glendale MD"

    def test_area_by_county_named_in_parentheses(self, dataset: Dataset) -> None:
        hit = dataset.resolve_region("Alameda")
        assert hit is not None and hit.matched_on == "area"
        assert "Alameda" in (hit.area_name or "")

    def test_city_that_is_not_an_area(self, dataset: Dataset) -> None:
        hit = dataset.resolve_region("Valencia")
        assert hit is not None
        assert hit.matched_on == "city" and hit.city == "Valencia" and hit.area_name is None

    def test_place_the_dataset_does_not_cover(self, dataset: Dataset) -> None:
        assert dataset.resolve_region("Lake Tahoe") is None
        assert dataset.resolve_region("") is None

    def test_short_name_falls_back_to_text_before_parenthesis(self) -> None:
        d = Dataset.from_documents(
            {"programs": []},
            {
                "occupations": {
                    "11-1011": {
                        "soc_code": "11-1011",
                        "title": "Chief Executives",
                        "regions": [
                            {
                                "area_name": "Chico MSA (Butte County)",
                                "area_type": "Metropolitan Area",
                            }
                        ],
                    }
                }
            },
            {"snapshot_date": "x"},
        )
        hit = d.resolve_region("Butte")
        assert hit is not None and hit.area_short_name == "Chico MSA"


class TestPrograms:
    def test_programs_for_dedupes_across_codes(self, dataset: Dataset) -> None:
        codes = list(dataset.programs_by_soc)[:3]
        found = dataset.programs_for(codes + codes)
        ids = [p["uuid"] for p in found]
        assert len(ids) == len(set(ids))
        assert dataset.programs_for(["00-0000"]) == []

    def test_program_lookup(self, dataset: Dataset) -> None:
        uuid = next(iter(dataset.programs))
        assert dataset.program(uuid) is dataset.programs[uuid]
        assert dataset.program("nope") is None
