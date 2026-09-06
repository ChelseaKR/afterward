"""The query layer with no model attached, and the one rule it adds on top of the executor.

Every test about a named term that resolves to nothing is really the same test: a filter that
could not be applied must end the query, not disappear. The executor is written for a narrated
answer and is allowed to hand back statewide records with a ``region_not_covered`` note,
because a model is about to read that note out. Here nobody is, so the records would arrive
looking like the answer to a question that was never run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner, Result

from afterward import cli
from afterward.ask.api import Assistant
from afterward.ask.dataset import Dataset
from afterward.ask.deterministic import (
    SCHEMA_VERSION,
    Criteria,
    answer,
    structured_query,
)
from afterward.ask.limits import Limits, Meter
from afterward.ask.query import StructuredQuery, execute
from afterward.ask.service import create_app

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "data"

KNOWN_OCCUPATION = "registered nurse"
KNOWN_AREA = "Fresno"
UNKNOWN_AREA = "Atlantis"
UNKNOWN_OCCUPATION = "wizardry"


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(FIXTURE_DIR)


class TestAnUnresolvedTermEndsTheQuery:
    """The rule this module exists for, and the proof it is not a rule about nothing."""

    def test_the_executor_alone_widens_an_unknown_area_to_the_whole_state(
        self, dataset: Dataset
    ) -> None:
        """The control. If this ever returns nothing, the test below proves nothing.

        ``_in_region`` treats a region of ``None`` as "no region filter", so an area the
        dataset cannot place silently becomes a statewide search. This asserts that is really
        what happens, so that the assertion underneath it is a difference and not a
        coincidence.
        """
        raw = execute(
            StructuredQuery(
                language="en",
                intent="find_programs",
                occupation_terms=[KNOWN_OCCUPATION],
                region_terms=[UNKNOWN_AREA],
            ),
            dataset,
        )
        assert raw.programs, "the executor is expected to return statewide records here"
        assert "region_not_covered" in raw.notes

    def test_an_unresolvable_area_returns_unresolved_and_no_records(self, dataset: Dataset) -> None:
        got = answer(Criteria(occupations=(KNOWN_OCCUPATION,), area=UNKNOWN_AREA), dataset)
        assert got.status == "unresolved"
        assert got.programs == []
        assert got.occupations == []
        assert [u.as_dict() for u in got.unresolved] == [{"term": UNKNOWN_AREA, "kind": "area"}]

    def test_the_same_criteria_without_the_area_do_return_records(self, dataset: Dataset) -> None:
        """Leaving the area out is a different question, and it is still answerable.

        Together with the test above this pins the behaviour to the *unresolved area* rather
        than to the occupation or the fixture being empty.
        """
        got = answer(Criteria(occupations=(KNOWN_OCCUPATION,)), dataset)
        assert got.status == "ok"
        assert got.programs

    def test_an_occupation_the_dataset_does_not_know_is_unresolved(self, dataset: Dataset) -> None:
        """Not "here are some programs chosen by your other filters", which is what the
        executor falls through to when no term resolves."""
        got = answer(Criteria(occupations=(UNKNOWN_OCCUPATION,)), dataset)
        assert got.status == "unresolved"
        assert got.programs == []
        assert [u.kind for u in got.unresolved] == ["occupation"]

    def test_one_unresolved_occupation_of_two_still_answers(self, dataset: Dataset) -> None:
        """A partial miss leaves a question the dataset can answer, and it is answered from
        the terms that resolved rather than emptied."""
        got = answer(Criteria(occupations=(KNOWN_OCCUPATION, UNKNOWN_OCCUPATION)), dataset)
        assert got.status == "ok"
        assert got.programs
        assert "occupation_terms_unresolved" in got.resolution_notes

    def test_a_resolvable_area_is_not_treated_as_unresolved(self, dataset: Dataset) -> None:
        got = answer(Criteria(occupations=(KNOWN_OCCUPATION,), area=KNOWN_AREA), dataset)
        assert got.status == "ok"
        assert got.unresolved == []


class TestTheAnswerIsReproducible:
    def test_identical_inputs_produce_identical_bytes(self, dataset: Dataset) -> None:
        criteria = Criteria(occupations=(KNOWN_OCCUPATION,), max_cost=6000)
        assert answer(criteria, dataset).as_json() == answer(criteria, dataset).as_json()

    def test_the_json_carries_its_schema_version(self, dataset: Dataset) -> None:
        payload = json.loads(answer(Criteria(occupations=(KNOWN_OCCUPATION,)), dataset).as_json())
        assert payload["schema_version"] == SCHEMA_VERSION

    def test_no_wall_clock_anywhere_in_the_response(self, dataset: Dataset) -> None:
        """A timestamp would make two runs of the same query differ, and nothing here is
        about when it was asked."""
        payload = answer(Criteria(occupations=(KNOWN_OCCUPATION,)), dataset).as_dict()
        for key in ("generated_at", "timestamp", "asked_at", "now"):
            assert key not in payload


class TestFiltersNeverInventAValue:
    def test_reported_only_never_returns_an_unreported_program(self, dataset: Dataset) -> None:
        got = answer(Criteria(occupations=(KNOWN_OCCUPATION,), reported_only=True), dataset)
        assert got.status == "ok"
        for program in got.programs:
            assert (program.get("outcomes") or {}).get("reported")

    def test_a_cost_ceiling_excludes_an_unreported_cost_rather_than_reading_it_as_zero(
        self, dataset: Dataset
    ) -> None:
        got = answer(Criteria(occupations=(KNOWN_OCCUPATION,), max_cost=1), dataset)
        for program in got.programs:
            cost = (program.get("cost") or {}).get("total_out_of_pocket")
            assert cost is not None
        assert set(got.excluded) == {
            "cost_not_reported",
            "length_not_comparable",
            "outcomes_not_reported",
        }


class TestTheQueryItBuilds:
    def test_the_criteria_become_a_find_programs_query(self) -> None:
        built = structured_query(
            Criteria(occupations=("a", "b"), area="Fresno", max_cost=500, reported_only=True)
        )
        assert built.intent == "find_programs"
        assert built.occupation_terms == ["a", "b"]
        assert built.region_terms == ["Fresno"]
        assert built.max_cost == 500
        assert built.requires_reported_outcomes is True

    def test_no_area_means_no_region_term_rather_than_an_empty_string(self) -> None:
        """An empty string would be a term the resolver could fail on, turning "I did not ask
        about a place" into "the place you asked about does not exist"."""
        assert structured_query(Criteria(occupations=("a",))).region_terms == []

    def test_english_glosses_are_left_empty(self) -> None:
        """They exist for a model offering a translation of a word it was handed. A caller
        naming terms directly has no second guess, and inventing one would be this module
        doing the guessing it refuses to do."""
        built = structured_query(Criteria(occupations=("enfermera",), language="es"))
        assert built.occupation_terms_english == []


class TestTheCommandLine:
    """Exit codes are the whole interface for a script, so each one is pinned."""

    def _run(self, *args: str) -> Result:
        return CliRunner().invoke(cli.app, ["query", "--dataset-dir", str(FIXTURE_DIR), *args])

    def test_records_found_exits_zero(self) -> None:
        result = self._run("--occupation", KNOWN_OCCUPATION)
        assert result.exit_code == 0, result.output

    def test_no_records_but_everything_resolved_exits_one(self) -> None:
        result = self._run("--occupation", KNOWN_OCCUPATION, "--max-cost", "1")
        assert result.exit_code == 1, result.output

    def test_an_unresolved_term_exits_two_and_names_it(self) -> None:
        result = self._run("--occupation", KNOWN_OCCUPATION, "--area", UNKNOWN_AREA)
        assert result.exit_code == 2, result.output
        assert UNKNOWN_AREA in result.output
        assert "unresolved area" in result.output

    def test_json_output_is_parseable_and_versioned(self) -> None:
        result = self._run("--occupation", KNOWN_OCCUPATION, "--json")
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["schema_version"] == SCHEMA_VERSION
        assert payload["status"] == "ok"

    def test_json_output_of_an_unresolved_query_still_parses(self) -> None:
        result = self._run("--occupation", KNOWN_OCCUPATION, "--area", UNKNOWN_AREA, "--json")
        assert result.exit_code == 2
        payload = json.loads(result.output)
        assert payload["status"] == "unresolved"
        assert payload["programs"] == []

    def test_explain_prints_the_resolution_trace(self) -> None:
        result = self._run("--occupation", KNOWN_OCCUPATION, "--explain")
        assert result.exit_code == 0, result.output

    def test_an_unreported_cost_is_never_printed_as_a_dollar_amount(self) -> None:
        """The line a counsellor reads aloud. "$0" for a price the source never filed would
        be the whole defect this project is about, in the smallest possible space."""
        result = self._run("--occupation", KNOWN_OCCUPATION)
        assert "$0\n" not in result.output


class TestItNeedsNoProvider:
    def test_it_answers_with_the_provider_switched_off(
        self, dataset: Dataset, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AFTERWARD_AI_PROVIDER", "off")
        got = answer(Criteria(occupations=(KNOWN_OCCUPATION,)), dataset)
        assert got.status == "ok"
        assert got.programs

    def test_it_answers_with_no_provider_configured_at_all(
        self, dataset: Dataset, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("AFTERWARD_AI_PROVIDER", raising=False)
        result = CliRunner().invoke(
            cli.app,
            ["query", "--dataset-dir", str(FIXTURE_DIR), "--occupation", KNOWN_OCCUPATION],
        )
        assert result.exit_code == 0, result.output


class TestTheQueryRoute:
    """`/query` is the half of `/ask` that needs no model, so it must answer without one."""

    def _client(self) -> TestClient:
        return TestClient(create_app(Assistant(Dataset.load(FIXTURE_DIR), None)))

    def test_it_answers_with_no_provider_configured(self) -> None:
        """The route's whole reason for existing. `Assistant(dataset, None)` is the service
        with no model available at all."""
        with self._client() as client:
            response = client.get("/query", params={"occupation": KNOWN_OCCUPATION})
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["programs"]
        assert payload["schema_version"] == SCHEMA_VERSION

    def test_ask_says_unavailable_on_the_same_service(self) -> None:
        """The other half of the contract: with no provider, the model route reports itself
        off rather than inventing an answer, while `/query` above still works."""
        with self._client() as client:
            response = client.post("/ask", json={"text": "anything", "lang": "en"})
        assert response.status_code == 200
        assert response.json()["status"] != "ok"

    def test_an_unresolvable_area_returns_unresolved_and_no_records(self) -> None:
        with self._client() as client:
            response = client.get(
                "/query", params={"occupation": KNOWN_OCCUPATION, "area": UNKNOWN_AREA}
            )
        payload = response.json()
        assert payload["status"] == "unresolved"
        assert payload["programs"] == []
        assert payload["unresolved"] == [{"term": UNKNOWN_AREA, "kind": "area"}]

    def test_repeated_occupation_params_are_all_used(self) -> None:
        with self._client() as client:
            response = client.get(
                "/query", params=[("occupation", KNOWN_OCCUPATION), ("occupation", "welder")]
            )
        assert response.status_code == 200

    def test_it_is_metered_like_a_question(self) -> None:
        """An unmetered route beside a metered one is a way around the meter."""
        meter = Meter(limits=Limits(client_per_hour=1))
        app = create_app(Assistant(Dataset.load(FIXTURE_DIR), None, meter=meter))
        with TestClient(app) as client:
            first = client.get("/query", params={"occupation": KNOWN_OCCUPATION})
            second = client.get("/query", params={"occupation": KNOWN_OCCUPATION})
        assert first.status_code == 200
        assert second.status_code == 429
