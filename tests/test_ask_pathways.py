"""A pathway is read off the dataset's own related-occupation lists and nothing else.

The published ``related`` list and ``related_source`` are the whole basis. An occupation
with an empty list yields no pathway and says so; one whose related occupations have no
program leading there yields none and says that; and the person's current occupation is
never offered as somewhere to move to.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from afterward.ask.api import AskRequest, Assistant
from afterward.ask.dataset import Dataset, RegionHit
from afterward.ask.fakes import scripted, structured_query
from afterward.ask.pathways import pathways_from
from afterward.ask.query import StructuredQuery, execute

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "data"


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(FIXTURE_DIR)


def _occupation(soc: str, change: float | None, related: list[str], **extra: Any) -> dict[str, Any]:
    return {
        "soc_code": soc,
        "title": f"Occupation {soc}",
        "percent_change": change,
        "total_job_openings": 100.0,
        "median_annual_wage": 50_000.0,
        "regions": extra.get("regions", []),
        "related": [{"soc_code": r, "title": f"Occupation {r}"} for r in related],
        "related_source": extra.get("source", "onet"),
        "alternate_titles": [],
        "spanish": None,
    }


def _program(
    uuid: str, soc: str, *, city: str = "Chico", area: str | None = None
) -> dict[str, Any]:
    return {
        "uuid": uuid,
        "provider_name": "P",
        "program_name": f"Program {uuid}",
        "program_format": "This program provides in-person instruction only.",
        "entity_type": "Public",
        "location": {"city": city},
        "region": {"area_name": area} if area else None,
        "length": {"weeks": 4.0, "hours": None, "competency_based": False},
        "cost": {
            "tuition": 1.0,
            "supplies": 0.0,
            "total_out_of_pocket": 1.0,
            "total_is_complete": True,
        },
        "outcomes": {"reported": False, "cohort": {"attributable": True}},
        "occupations": [{"soc_code": soc, "match": {"kind": "exact"}}],
    }


def _dataset(occupations: dict[str, Any], programs: list[dict[str, Any]]) -> Dataset:
    return Dataset.from_documents(
        {"programs": programs},
        {"occupations": occupations},
        {"snapshot_date": "x", "is_fixture": True},
    )


class TestPathwaysFrom:
    def test_growing_related_with_programs_growth_first(self) -> None:
        d = _dataset(
            {
                "A": _occupation("A", 1.0, ["B", "C", "D", "E", "A"]),
                "B": _occupation("B", 3.0, []),
                "C": _occupation("C", 9.0, []),
                "D": _occupation("D", -2.0, []),
                "E": _occupation("E", 5.0, []),
            },
            [_program("pb", "B"), _program("pc", "C"), _program("pd", "D")],
        )
        found = pathways_from(d, "A", region=None, growing_only=True)
        assert found.candidates == ["C", "B"]
        assert found.related_source == "onet" and found.considered == 5
        assert "pathways_from:A" in found.notes and "related_source:onet" in found.notes
        assert any("not projected to grow" in n for n in found.notes)
        assert any("no program leads there" in n for n in found.notes)

    def test_any_projection_keeps_shrinking_related(self) -> None:
        d = _dataset(
            {"A": _occupation("A", 1.0, ["D"]), "D": _occupation("D", -2.0, [])},
            [_program("pd", "D")],
        )
        assert pathways_from(d, "A", region=None, growing_only=False).candidates == ["D"]
        assert pathways_from(d, "A", region=None, growing_only=True).candidates == []

    def test_empty_related_list_is_said_not_filled(self) -> None:
        d = _dataset({"A": _occupation("A", 1.0, [], source=None)}, [])
        found = pathways_from(d, "A", region=None, growing_only=True)
        assert found.candidates == [] and found.related_source is None
        assert found.notes == ["no_related_occupations_published"]

    def test_unknown_origin(self) -> None:
        d = _dataset({}, [])
        assert pathways_from(d, "Z", region=None, growing_only=True).notes == [
            "pathway_origin_not_in_dataset"
        ]

    def test_region_uses_the_regional_row_and_regional_programs(self) -> None:
        chico = "Chico MSA (Butte County)"
        d = _dataset(
            {
                "A": _occupation("A", 1.0, ["B", "C"]),
                "B": _occupation(
                    "B",
                    9.0,
                    [],
                    regions=[
                        {"area_name": chico, "percent_change": -1.0, "total_job_openings": 5.0}
                    ],
                ),
                "C": _occupation(
                    "C",
                    2.0,
                    [],
                    regions=[
                        {"area_name": chico, "percent_change": 4.0, "total_job_openings": 5.0}
                    ],
                ),
            },
            [
                _program("pb", "B", area=chico),
                _program("pc", "C", area=chico),
                _program("pc2", "C", city="Elsewhere"),
            ],
        )
        region = RegionHit("Chico", chico, "Chico MSA", None, "area")
        assert pathways_from(d, "A", region=region, growing_only=True).candidates == ["C"]
        city = RegionHit("Elsewhere", None, None, "Elsewhere", "city")
        assert pathways_from(d, "A", region=city, growing_only=True).candidates == ["C"]
        nowhere = RegionHit("Nowhere", None, None, "Nowhere", "city")
        found = pathways_from(d, "A", region=nowhere, growing_only=True)
        assert found.candidates == [] and "no_related_occupation_with_a_program" in found.notes


class TestInTheExecutor:
    def test_pathways_intent_puts_the_origin_first_and_its_programs_nowhere(self) -> None:
        d = _dataset(
            {"A": _occupation("A", 1.0, ["B"]), "B": _occupation("B", 3.0, [])},
            [_program("pa", "A"), _program("pb", "B")],
        )
        q = StructuredQuery(
            language="en",
            intent="pathways",
            current_occupation_terms=["Occupation A"],
            projection="growing",
        )
        result = execute(q, d)
        assert [o["soc_code"] for o in result.occupations] == ["A", "B"]
        assert [p["uuid"] for p in result.programs] == ["pb"]
        assert "pathways_from:A" in result.notes

    def test_pathways_from_the_occupation_page(self) -> None:
        d = _dataset(
            {"A": _occupation("A", 1.0, ["B"]), "B": _occupation("B", 3.0, [])},
            [_program("pb", "B")],
        )
        q = StructuredQuery(language="en", intent="pathways")
        result = execute(q, d, context_occupation="A")
        assert [o["soc_code"] for o in result.occupations] == ["A", "B"]

    def test_pathways_without_a_known_current_job_falls_back_to_criteria(self) -> None:
        d = _dataset({"B": _occupation("B", 3.0, [])}, [_program("pb", "B")])
        q = StructuredQuery(language="en", intent="pathways", current_occupation_terms=["zzz"])
        result = execute(q, d)
        assert "current_occupation_unresolved" in result.notes
        assert "occupations_chosen_by_criteria" in result.notes

    def test_end_to_end_on_the_fixture(self, dataset: Dataset) -> None:
        soc = next(soc for soc, o in dataset.occupations.items() if o.get("related"))
        title = dataset.occupations[soc]["title"]
        provider = scripted(
            structured_query(
                intent="pathways", projection="growing", current_occupation_terms=[title]
            )
        )
        response, trace = Assistant(dataset, provider).ask_traced(
            AskRequest(text=f"I am a {title}; what could I move into?")
        )
        assert response.status == "ok"
        assert response.occupations[0].soc_code == soc
        assert any(n.startswith("related_source:") for n in response.notes)
        assert trace.pack is not None and f"[O:{soc}]" in trace.pack.render()
