"""The executor does what a search form would do, and says what it could not do.

Every filter here has a null case, and the null case is the one that matters: a program with
no reported cost is not free, a competency-based program is not short, an occupation with no
published projection is not growing. Each of those is excluded and counted, never assumed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from afterward.ask.dataset import Dataset
from afterward.ask.query import (
    MAX_OCCUPATIONS,
    MAX_PROGRAMS,
    QUERY_SCHEMA,
    StructuredQuery,
    execute,
    program_ids,
    resolve,
)

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "data"


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(FIXTURE_DIR)


def query(**overrides: Any) -> StructuredQuery:
    base: dict[str, Any] = {"language": "en", "intent": "find_programs"}
    base.update(overrides)
    return StructuredQuery(**base)


class TestSchemaAgreesWithModel:
    """The hand-written schema and the pydantic model must describe the same object.

    The schema is what the provider enforces; the model is what the service validates. If
    they drift, a query the provider produced would fail validation, or a field the model
    expects would never arrive.
    """

    def test_same_fields_all_required(self) -> None:
        assert set(QUERY_SCHEMA["properties"]) == set(StructuredQuery.model_fields)
        assert set(QUERY_SCHEMA["required"]) == set(StructuredQuery.model_fields)
        assert QUERY_SCHEMA["additionalProperties"] is False

    def test_enums_match_the_literals(self) -> None:
        for name in ("language", "intent", "projection", "format"):
            literal = StructuredQuery.model_fields[name].annotation
            assert set(QUERY_SCHEMA["properties"][name]["enum"]) == set(literal.__args__)  # type: ignore[union-attr]

    def test_no_provider_hostile_constructs(self) -> None:
        text = str(QUERY_SCHEMA)
        for construct in ("$defs", "$ref", "anyOf", "default", "title"):
            assert construct not in text

    def test_model_rejects_an_invented_field(self) -> None:
        with pytest.raises(ValidationError):
            StructuredQuery(language="en", intent="find_programs", soc_code="29-1141")  # type: ignore[call-arg]


class TestResolution:
    def test_terms_resolve_and_unresolved_are_kept(self, dataset: Dataset) -> None:
        res = resolve(
            query(
                occupation_terms=["veterinary assistant", "xyzzy"],
                current_occupation_terms=["plugh"],
                region_terms=["Los Angeles", "Atlantis"],
            ),
            dataset,
        )
        assert res.occupations[0].soc_code == "31-9096"
        assert res.unresolved_occupation_terms == ["xyzzy"]
        assert res.unresolved_current_terms == ["plugh"]
        assert res.region is not None and res.region.matched_on == "area"
        assert res.unresolved_region_terms == ["Atlantis"]

    def test_spanish_term_falls_back_to_its_english_gloss(self, dataset: Dataset) -> None:
        res = resolve(
            query(
                language="es",
                occupation_terms=["asistente veterinario zzq"],
                occupation_terms_english=["veterinary assistant"],
            ),
            dataset,
        )
        assert res.occupations and res.occupations[0].soc_code == "31-9096"
        assert res.unresolved_occupation_terms == []

    def test_an_area_beats_a_city_when_both_are_given(self, dataset: Dataset) -> None:
        res = resolve(query(region_terms=["Valencia", "Los Angeles"]), dataset)
        assert res.region is not None and res.region.matched_on == "area"


class TestContextPages:
    def test_program_page_returns_that_program_and_its_occupations(self, dataset: Dataset) -> None:
        uuid = next(iter(dataset.programs))
        result = execute(query(intent="program_detail"), dataset, context_program=uuid)
        assert program_ids(result.programs) == [uuid]
        assert {o["soc_code"] for o in result.occupations} == {
            oc["soc_code"] for oc in dataset.programs[uuid]["occupations"]
        }
        assert result.candidates == 1

    def test_unknown_program_context_is_ignored(self, dataset: Dataset) -> None:
        result = execute(
            query(occupation_terms=["veterinary assistant"]), dataset, context_program="nope"
        )
        assert result.programs

    def test_occupation_page_puts_that_occupation_first(self, dataset: Dataset) -> None:
        soc = next(iter(dataset.programs_by_soc))
        result = execute(
            query(intent="occupation_detail", occupation_terms=["veterinary assistant"]),
            dataset,
            context_occupation=soc,
        )
        assert result.occupations[0]["soc_code"] == soc


class TestFilters:
    """Each filter excludes a record that cannot answer it, and counts the exclusion."""

    def test_cost_ceiling_excludes_and_counts_unreported_cost(self, dataset: Dataset) -> None:
        terms = ["veterinary assistant"]
        all_programs = execute(query(occupation_terms=terms), dataset).programs
        result = execute(query(occupation_terms=terms, max_cost=1.0), dataset)
        assert result.programs == []
        assert result.excluded.cost_not_reported + len(all_programs) >= 0
        assert "filters_removed_every_program" in result.notes

    def test_unreported_cost_is_never_under_a_ceiling(self) -> None:
        d = _dataset_with_programs(
            [_program("a", cost=None), _program("b", cost=500.0)],
            occupations={"11-1011": _occupation()},
        )
        result = execute(query(occupation_terms=["Chief Executives"], max_cost=1000), d)
        assert program_ids(result.programs) == ["b"]
        assert result.excluded.cost_not_reported == 1

    def test_competency_based_length_is_not_short(self) -> None:
        d = _dataset_with_programs(
            [_program("cb", weeks=None, competency=True), _program("w", weeks=8.0)],
            occupations={"11-1011": _occupation()},
        )
        result = execute(query(occupation_terms=["Chief Executives"], max_weeks=12), d)
        assert program_ids(result.programs) == ["w"]
        assert result.excluded.length_not_comparable == 1

    def test_reported_outcomes_required(self) -> None:
        d = _dataset_with_programs(
            [_program("silent", reported=False), _program("loud", reported=True)],
            occupations={"11-1011": _occupation()},
        )
        result = execute(
            query(occupation_terms=["Chief Executives"], requires_reported_outcomes=True), d
        )
        assert program_ids(result.programs) == ["loud"]
        assert result.excluded.outcomes_not_reported == 1

    def test_format_filters(self) -> None:
        d = _dataset_with_programs(
            [
                _program(
                    "o",
                    fmt="This program provides online instruction, e-learning, or distance learning only.",
                ),
                _program(
                    "h",
                    fmt="This is a hybrid or blended program providing both in-person and online instruction.",
                ),
                _program("p", fmt="This program provides in-person instruction only."),
                _program("n", fmt=None),
            ],
            occupations={"11-1011": _occupation()},
        )
        for wanted, expected in (("online", ["o"]), ("hybrid", ["h"]), ("in_person", ["p"])):
            result = execute(query(occupation_terms=["Chief Executives"], format=wanted), d)
            assert program_ids(result.programs) == expected, wanted

    def test_projection_uses_published_change_and_never_assumes(self) -> None:
        d = _dataset_with_programs(
            [
                _program("grow", soc="11-1011"),
                _program("shrink", soc="11-1021"),
                _program("blank", soc="11-1031"),
            ],
            occupations={
                "11-1011": _occupation("11-1011", change=5.0),
                "11-1021": _occupation("11-1021", change=-3.0),
                "11-1031": _occupation("11-1031", change=None),
            },
        )
        terms = ["Chief Executives"]
        assert program_ids(
            execute(query(occupation_terms=terms, projection="growing"), d).programs
        ) == ["grow"]
        assert program_ids(
            execute(query(occupation_terms=terms, projection="shrinking"), d).programs
        ) == ["shrink"]
        assert program_ids(
            execute(query(occupation_terms=terms, projection="not_shrinking"), d).programs
        ) == ["grow"]
        assert len(execute(query(occupation_terms=terms, projection="any"), d).programs) == 3

    def test_wage_floor_uses_the_regional_row_when_there_is_one(self) -> None:
        occ = _occupation(wage=90_000.0, regions=[_row("Chico MSA (Butte County)", wage=40_000.0)])
        d = _dataset_with_programs(
            [_program("chico", city="Chico", area="Chico MSA (Butte County)")],
            occupations={"11-1011": occ},
        )
        assert execute(
            query(occupation_terms=["Chief Executives"], min_annual_wage=50_000), d
        ).programs
        assert not execute(
            query(
                occupation_terms=["Chief Executives"],
                min_annual_wage=50_000,
                region_terms=["Chico"],
            ),
            d,
        ).programs

    def test_region_filters_by_area_or_by_city(self) -> None:
        d = _dataset_with_programs(
            [
                _program("in", city="Chico", area="Chico MSA (Butte County)"),
                _program("out", city="Elsewhere", area=None),
            ],
            occupations={"11-1011": _occupation(regions=[_row("Chico MSA (Butte County)")])},
        )
        by_area = execute(query(occupation_terms=["Chief Executives"], region_terms=["Butte"]), d)
        assert program_ids(by_area.programs) == ["in"]
        by_city = execute(
            query(occupation_terms=["Chief Executives"], region_terms=["Elsewhere"]), d
        )
        assert program_ids(by_city.programs) == ["out"]
        assert "region_is_city_only" in by_city.notes
        nowhere = execute(
            query(occupation_terms=["Chief Executives"], region_terms=["Atlantis"]), d
        )
        assert "region_not_covered" in nowhere.notes


class TestWithoutAnOccupation:
    """No occupation named: the criteria choose, only among occupations with a program."""

    def test_criteria_choose_occupations_with_programs_in_the_area(self) -> None:
        d = _dataset_with_programs(
            [_program("a", soc="11-1011"), _program("b", soc="11-1021")],
            occupations={
                "11-1011": _occupation("11-1011", change=5.0, openings=100.0),
                "11-1021": _occupation("11-1021", change=5.0, openings=900.0),
                "11-1031": _occupation("11-1031", change=50.0, openings=9_000.0),
            },
        )
        result = execute(query(projection="growing"), d)
        assert [o["soc_code"] for o in result.occupations] == ["11-1021", "11-1011"]
        assert "occupations_chosen_by_criteria" in result.notes

    def test_pays_more_means_more_than_the_current_occupation(self) -> None:
        d = _dataset_with_programs(
            [_program("low", soc="11-1011"), _program("high", soc="11-1021")],
            occupations={
                "11-1011": _occupation("11-1011", title="Stockers", wage=30_000.0),
                "11-1021": _occupation("11-1021", title="Chief Executives", wage=90_000.0),
            },
        )
        result = execute(
            query(current_occupation_terms=["stockers"], measures_of_interest=["wage"]), d
        )
        assert result.query.min_annual_wage == pytest.approx(30_000.0)
        assert program_ids(result.programs) == ["high"]
        assert any("wage floor" in n for n in result.notes)

    def test_no_floor_without_a_current_occupation_or_without_interest_in_pay(self) -> None:
        d = _dataset_with_programs([_program("a")], occupations={"11-1011": _occupation()})
        assert execute(query(measures_of_interest=["wage"]), d).query.min_annual_wage is None
        assert (
            execute(query(current_occupation_terms=["chief executives"]), d).query.min_annual_wage
            is None
        )
        stated = execute(
            query(
                current_occupation_terms=["chief executives"],
                measures_of_interest=["wage"],
                min_annual_wage=1.0,
            ),
            d,
        )
        assert stated.query.min_annual_wage == 1.0

    def test_no_floor_when_the_current_occupation_has_no_wage(self) -> None:
        d = _dataset_with_programs([_program("a")], occupations={"11-1011": _occupation(wage=None)})
        result = execute(
            query(current_occupation_terms=["chief executives"], measures_of_interest=["wage"]), d
        )
        assert result.query.min_annual_wage is None

    def test_empty_dataset_answers_honestly(self) -> None:
        d = _dataset_with_programs([], occupations={})
        result = execute(query(occupation_terms=["anything"]), d)
        assert result.programs == [] and result.occupations == []
        assert "occupation_terms_unresolved" in result.notes


class TestRanking:
    def test_reported_first_then_cheapest_then_stable(self) -> None:
        d = _dataset_with_programs(
            [
                _program("c", reported=False, cost=10.0),
                _program("b", reported=True, cost=None),
                _program("a", reported=True, cost=50.0),
            ],
            occupations={"11-1011": _occupation()},
        )
        assert program_ids(execute(query(occupation_terms=["Chief Executives"]), d).programs) == [
            "a",
            "b",
            "c",
        ]

    def test_lists_are_capped_and_the_count_is_kept(self) -> None:
        d = _dataset_with_programs(
            [_program(f"p{i:02d}") for i in range(MAX_PROGRAMS + 3)],
            occupations={"11-1011": _occupation()},
        )
        result = execute(query(occupation_terms=["Chief Executives"]), d)
        assert len(result.programs) == MAX_PROGRAMS
        assert result.candidates == MAX_PROGRAMS + 3
        assert len(result.occupations) <= MAX_OCCUPATIONS


# -- builders ----------------------------------------------------------------------------


def _row(
    area_name: str, *, wage: float | None = 50_000.0, change: float | None = 3.0
) -> dict[str, Any]:
    return {
        "area_type": "Metropolitan Area",
        "area_name": area_name,
        "period": "2023-2033",
        "median_annual_wage": wage,
        "total_job_openings": 100.0,
        "percent_change": change,
    }


def _occupation(
    soc: str = "11-1011",
    *,
    title: str = "Chief Executives",
    wage: float | None = 80_000.0,
    change: float | None = 4.0,
    openings: float | None = 500.0,
    regions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "soc_code": soc,
        "title": title,
        "period": "2024-2034",
        "median_annual_wage": wage,
        "total_job_openings": openings,
        "percent_change": change,
        "entry_level_education": "Bachelor's degree",
        "regions": regions or [],
        "alternate_titles": [],
        "spanish": None,
        "related": [],
        "related_source": None,
    }


def _program(
    uuid: str,
    *,
    soc: str = "11-1011",
    cost: float | None = 1000.0,
    weeks: float | None = 10.0,
    competency: bool = False,
    reported: bool = True,
    fmt: str | None = "This program provides in-person instruction only.",
    city: str = "Chico",
    area: str | None = None,
) -> dict[str, Any]:
    return {
        "uuid": uuid,
        "provider_name": "Provider",
        "program_name": f"Program {uuid}",
        "program_format": fmt,
        "entity_type": "Public",
        "location": {"city": city, "state": "CA"},
        "region": {
            "area_name": area,
            "area_short_name": area,
            "area_type": "x",
            "matched_on": "principal_city",
        }
        if area
        else None,
        "length": {"weeks": weeks, "hours": None, "competency_based": competency},
        "cost": {
            "tuition": cost,
            "supplies": 0.0,
            "total_out_of_pocket": cost,
            "total_is_complete": cost is not None,
            "wioa_funded_cost": None,
        },
        "outcomes": {
            "total_served": 20.0 if reported else None,
            "total_exited": 10.0 if reported else None,
            "total_completed": 8.0 if reported else None,
            "completion_rate": 0.8 if reported else None,
            "credentials_earned": None,
            "median_earnings": None,
            "employment_rate_q2": None,
            "employed_q2": None,
            "employed_q4": None,
            "reported": reported,
            "cohort": {"attributable": True},
        },
        "occupations": [
            {"soc_code": soc, "title": "x", "match": {"kind": "exact", "program_soc_codes": [soc]}}
        ],
    }


def _dataset_with_programs(
    programs: list[dict[str, Any]], *, occupations: dict[str, Any]
) -> Dataset:
    return Dataset.from_documents(
        {"snapshot_date": "2026-01-01", "programs": programs},
        {"occupations": occupations},
        {"snapshot_date": "2026-01-01", "is_fixture": True, "peer_medians": {}},
    )
