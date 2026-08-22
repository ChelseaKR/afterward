"""The assistant runs one sequence and fails closed.

With a scripted model the whole path -- admit, structure, execute, evidence, narrate, verify,
respond -- is exercised against the committed fixture. The properties held here: the
response carries provenance; the system prompts are byte-identical across requests (prompt
caching needs that); a provider failure is ``unavailable`` and never a guess; and the cost
meter is consulted before any model is called.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from afterward.ask import PROMPT_VERSION
from afterward.ask.api import AskRequest, Assistant, HistoryTurn, history_from
from afterward.ask.dataset import Dataset
from afterward.ask.fakes import scripted, structured_query
from afterward.ask.limits import LimitExceeded, Limits, Meter
from afterward.ask.provider import FakeProvider, ProviderError

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "data"


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(FIXTURE_DIR)


class TestFullSequence:
    def test_a_grounded_answer_from_the_fixture(self, dataset: Dataset) -> None:
        provider = scripted(
            structured_query(occupation_terms=["veterinary assistant"], region_terms=["Valencia"])
        )
        assistant = Assistant(dataset, provider, site_root="https://example.test")
        response, trace = assistant.ask_traced(AskRequest(text="vet assistant in Valencia"))

        assert response.status == "ok" and response.lang == "en"
        assert response.claims and response.withheld.count == 0
        assert response.programs and all(
            p.path.startswith("https://example.test/en/programs/") for p in response.programs
        )
        assert response.occupations and response.occupations[0].path.startswith(
            "https://example.test/en/occupations/"
        )
        assert response.resolution is not None
        assert response.resolution["region"]["matched_on"] == "city"
        assert "region_is_city_only" in response.notes
        assert "not a recommendation" in response.notice

        provenance = response.provenance
        assert provenance is not None
        assert provenance.provider == "fake" and provenance.model == "fake-model"
        assert provenance.prompt_version == PROMPT_VERSION
        assert provenance.is_fixture is True and provenance.snapshot_date == dataset.snapshot_date
        assert provenance.usage["input_tokens"] == 2

        assert trace.query is not None and trace.pack is not None and trace.verified is not None
        assert [c["route"] for c in provider.calls] == ["structure", "narrate"]

    def test_system_prompts_are_byte_stable_across_requests(self, dataset: Dataset) -> None:
        provider = scripted(structured_query(occupation_terms=["veterinary assistant"]))
        assistant = Assistant(dataset, provider)
        assistant.ask(AskRequest(text="one"))
        assistant.ask(AskRequest(text="two", history=[HistoryTurn(role="user", text="one")]))
        by_route: dict[str, set[str]] = {}
        for call in provider.calls:
            by_route.setdefault(call["route"], set()).add(call["system"])
        assert all(len(systems) == 1 for systems in by_route.values())
        # and the per-request material went where it belongs
        assert "Earlier in this conversation" in provider.calls[2]["user"]

    def test_spanish_request_answers_in_spanish_and_links_es_pages(self, dataset: Dataset) -> None:
        provider = scripted(
            structured_query(language="es", occupation_terms=["asistente veterinario"])
        )
        response = Assistant(dataset, provider).ask(
            AskRequest(text="asistente veterinario", lang="es")
        )
        assert response.lang == "es" and "Generado por IA" in response.notice
        assert response.programs[0].path.startswith("/es/programs/")
        assert "Answer in Spanish." in provider.calls[1]["user"]

    def test_page_context_reaches_the_model_and_the_executor(self, dataset: Dataset) -> None:
        uuid = next(iter(dataset.programs))
        provider = scripted(structured_query(intent="program_detail"))
        response = Assistant(dataset, provider).ask(
            AskRequest(text="is this any good?", program_id=uuid)
        )
        assert [p.id for p in response.programs] == [uuid]
        assert "The person is reading: the program page for" in provider.calls[0]["user"]

        soc = next(iter(dataset.programs_by_soc))
        provider = scripted(structured_query(intent="occupation_detail"))
        response = Assistant(dataset, provider).ask(
            AskRequest(text="tell me about this job", soc_code=soc)
        )
        assert response.occupations[0].soc_code == soc
        assert "the occupation page for" in provider.calls[0]["user"]

    def test_unknown_page_context_is_simply_absent(self, dataset: Dataset) -> None:
        provider = scripted(structured_query(occupation_terms=["veterinary assistant"]))
        Assistant(dataset, provider).ask(
            AskRequest(text="x", program_id="nope", soc_code="00-0000")
        )
        assert "The person is reading" not in provider.calls[0]["user"]

    def test_clarifications_and_out_of_scope_are_passed_through(self, dataset: Dataset) -> None:
        provider = scripted(
            structured_query(clarifications_needed=["Which city?"], out_of_scope="Visa questions.")
        )
        response = Assistant(dataset, provider).ask(AskRequest(text="something better"))
        assert response.clarifications_needed == ["Which city?"]
        assert response.out_of_scope == "Visa questions."
        assert "underspecified" in provider.calls[1]["user"]
        assert "outside the dataset" in provider.calls[1]["user"]


class TestFailsClosed:
    def test_no_provider_means_unavailable_not_a_guess(self, dataset: Dataset) -> None:
        assistant = Assistant(dataset, None)
        assert assistant.available is False
        response = assistant.ask(AskRequest(text="anything", lang="es"))
        assert response.status == "unavailable" and response.claims == []
        assert response.message and "no está disponible" in response.message
        assert response.provenance is None

    def test_provider_error_means_unavailable(self, dataset: Dataset) -> None:
        def script(route: str, user: str) -> dict[str, Any]:
            raise ProviderError("boom")

        response = Assistant(dataset, FakeProvider(script)).ask(AskRequest(text="x"))
        assert response.status == "unavailable"

    def test_query_that_does_not_match_the_schema_is_a_provider_failure(
        self, dataset: Dataset
    ) -> None:
        provider = FakeProvider(
            lambda route, user: {"language": "en", "intent": "find_programs", "soc": "x"}
        )
        assert Assistant(dataset, provider).ask(AskRequest(text="x")).status == "unavailable"

    def test_narration_that_does_not_match_the_schema_is_a_provider_failure(
        self, dataset: Dataset
    ) -> None:
        def script(route: str, user: str) -> dict[str, Any]:
            return structured_query() if route == "structure" else {"claims": "no"}

        assert (
            Assistant(dataset, FakeProvider(script)).ask(AskRequest(text="x")).status
            == "unavailable"
        )

    def test_meter_is_consulted_before_the_model(self, dataset: Dataset) -> None:
        provider = scripted(structured_query())
        meter = Meter(limits=Limits(client_per_hour=1))
        assistant = Assistant(dataset, provider, meter=meter)
        assistant.ask(AskRequest(text="one"), client_key="k")
        with pytest.raises(LimitExceeded):
            assistant.ask(AskRequest(text="two"), client_key="k")
        assert len(provider.calls) == 2
        assert meter.snapshot()["day_output_tokens"] == 2


class TestRequestShape:
    def test_history_is_bounded_and_converted(self) -> None:
        turns = [HistoryTurn(role="user", text="a"), HistoryTurn(role="assistant", text="b")]
        assert [(t.role, t.text) for t in history_from(turns)] == [
            ("user", "a"),
            ("assistant", "b"),
        ]
        with pytest.raises(ValueError):
            AskRequest(text="x", history=[HistoryTurn(role="user", text="t")] * 7)
        with pytest.raises(ValueError):
            AskRequest(text="")
        with pytest.raises(ValueError):
            AskRequest(text="x", extra="no")  # type: ignore[call-arg]
