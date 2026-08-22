"""A runtime translation is labelled, is never asked for where Spanish is published, and is
withheld whole if it touches a number.

"160 hours" must still say 160 in Spanish. A translation that adds a figure, drops one, or
renders an empty English field as Spanish prose is not shown; the English stays the record.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from afterward.ask.api import Assistant, TranslateRequest
from afterward.ask.dataset import Dataset
from afterward.ask.fakes import structured_query
from afterward.ask.limits import Limits, Meter
from afterward.ask.provider import FakeProvider, ProviderError
from afterward.ask.service import create_app
from afterward.ask.translate import LABEL, Translator, numbers_in, verify_translation

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "data"


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(FIXTURE_DIR)


def _faithful(route: str, user: str) -> dict[str, Any]:
    if route == "structure":
        return structured_query()
    title = user.split("title: ", 1)[1].split("\n", 1)[0]
    description = user.split("description: ", 1)[1]
    return {"title": f"[es] {title}", "description": f"[es] {description}" if description else ""}


def _occupation_without_spanish(dataset: Dataset) -> str:
    return next(
        soc for soc, o in dataset.occupations.items() if not (o.get("spanish") or {}).get("title")
    )


def _occupation_with_spanish(dataset: Dataset) -> str:
    return next(
        soc for soc, o in dataset.occupations.items() if (o.get("spanish") or {}).get("title")
    )


class TestVerification:
    def test_numbers_are_a_multiset(self) -> None:
        assert numbers_in("160 hours, 2 days, $1,200.50") == ["120050", "160", "2"]
        assert numbers_in(None) == []

    def test_faithful_rendering_passes(self) -> None:
        assert (
            verify_translation(
                "A 160 hour course for 2 people.", "Un curso de 160 horas para 2 personas."
            )
            == []
        )

    def test_changed_dropped_or_added_numbers_are_refused(self) -> None:
        assert verify_translation("160 hours", "150 horas") == ["numbers_changed"]
        assert verify_translation("160 hours", "muchas horas") == ["numbers_changed"]
        assert "numbers_changed" in verify_translation("Short course", "Curso de 3 semanas")

    def test_empty_cases(self) -> None:
        assert verify_translation("", "") == []
        assert verify_translation(None, "Texto inventado") == ["text_added_where_source_is_empty"]
        assert verify_translation("Something", "   ") == ["translation_empty"]

    def test_implausible_length(self) -> None:
        assert "length_implausible" in verify_translation("A course.", "Un curso " * 20)
        assert "length_implausible" in verify_translation(
            "A very long English description of things.", "Ok"
        )


class TestTranslator:
    def test_published_spanish_is_used_and_the_model_is_not_asked(self, dataset: Dataset) -> None:
        provider = FakeProvider(_faithful)
        translator = Translator(dataset, provider)
        soc = _occupation_with_spanish(dataset)
        assert translator.already_in_spanish("occupation", soc) is not None
        assert translator.already_in_spanish("program", next(iter(dataset.programs))) is None
        assert provider.calls == []

    def test_translation_is_labelled_verified_and_cached(self, dataset: Dataset) -> None:
        provider = FakeProvider(_faithful)
        translator = Translator(dataset, provider)
        soc = _occupation_without_spanish(dataset)
        first = translator.translate("occupation", soc)
        again = translator.translate("occupation", soc)
        assert first is not None and first is again
        assert first.title and first.title.startswith("[es] ")
        assert first.ai_translated and not first.reviewed and first.label == LABEL["es"]
        assert first.withheld == [] and first.source_title == dataset.occupations[soc]["title"]
        assert len(provider.calls) == 1 and provider.calls[0]["route"] == "translate"
        assert first.as_dict()["source"]["title"] == first.source_title

    def test_a_translation_that_changes_a_number_is_withheld_whole(self, dataset: Dataset) -> None:
        def liar(route: str, user: str) -> dict[str, Any]:
            return {"title": "Título 99", "description": "Descripción"}

        uuid = next(iter(dataset.programs))
        translated = Translator(dataset, FakeProvider(liar)).translate("program", uuid)
        assert translated is not None
        assert translated.title is None and translated.description is None
        assert "numbers_changed" in translated.withheld

    def test_unknown_record_and_no_provider(self, dataset: Dataset) -> None:
        assert Translator(dataset, FakeProvider(_faithful)).translate("program", "nope") is None
        assert Translator(dataset, None).translate("program", next(iter(dataset.programs))) is None
        assert Translator(dataset, None).source("occupation", "00-0000") is None

    def test_schema_violation_is_a_provider_error(self, dataset: Dataset) -> None:
        translator = Translator(dataset, FakeProvider(lambda r, u: {"title": 1}))
        with pytest.raises(ProviderError):
            translator.translate("program", next(iter(dataset.programs)))

    def test_cache_is_bounded(self, dataset: Dataset, monkeypatch: pytest.MonkeyPatch) -> None:
        from afterward.ask import translate as module

        monkeypatch.setattr(module, "MAX_CACHE", 2)
        translator = Translator(dataset, FakeProvider(_faithful))
        ids = list(dataset.programs)[:3]
        for uuid in ids:
            translator.translate("program", uuid)
        assert len(translator._cache) == 2 and ("program", ids[0]) not in translator._cache


class TestAssistantAndService:
    def test_statuses(self, dataset: Dataset) -> None:
        assistant = Assistant(dataset, FakeProvider(_faithful))
        published = assistant.translate(
            TranslateRequest(kind="occupation", id=_occupation_with_spanish(dataset))
        )
        assert published.status == "published" and published.title and not published.ai_translated
        ok = assistant.translate(
            TranslateRequest(kind="occupation", id=_occupation_without_spanish(dataset))
        )
        assert ok.status == "ok" and ok.ai_translated and ok.provenance is not None
        assert ok.provenance.provider == "fake"
        assert (
            assistant.translate(TranslateRequest(kind="program", id="nope")).status == "not_found"
        )
        off = Assistant(dataset, None).translate(
            TranslateRequest(kind="program", id=next(iter(dataset.programs)))
        )
        assert off.status == "unavailable"

    def test_withheld_and_provider_failure(self, dataset: Dataset) -> None:
        uuid = next(iter(dataset.programs))
        liar = Assistant(dataset, FakeProvider(lambda r, u: {"title": "x 7", "description": "y"}))
        withheld = liar.translate(TranslateRequest(kind="program", id=uuid))
        assert withheld.status == "withheld" and withheld.title is None and withheld.withheld

        def boom(route: str, user: str) -> dict[str, Any]:
            raise ProviderError("down")

        assert (
            Assistant(dataset, FakeProvider(boom))
            .translate(TranslateRequest(kind="program", id=uuid))
            .status
            == "unavailable"
        )

    def test_metered_like_a_question(self, dataset: Dataset) -> None:
        assistant = Assistant(
            dataset, FakeProvider(_faithful), meter=Meter(limits=Limits(client_per_hour=1))
        )
        app = create_app(assistant)
        uuid = next(iter(dataset.programs))
        with TestClient(app) as client:
            first = client.post("/translate", json={"kind": "program", "id": uuid})
            second = client.post("/translate", json={"kind": "program", "id": uuid})
            bad = client.post("/translate", json={"kind": "thing", "id": uuid})
        assert first.status_code == 200 and first.json()["status"] == "ok"
        assert first.json()["label"] == LABEL["es"]
        assert second.status_code == 429
        assert bad.status_code == 422
