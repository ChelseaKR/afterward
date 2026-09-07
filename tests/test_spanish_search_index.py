"""The Spanish title table the search index carries, and the one guarantee it makes.

`_attach_spanish` has written O*NET Mi Proximo Paso titles onto every occupation record since
the enrichment expansion, and nothing indexed them, so a Spanish reader typing "enfermera" got
an empty result set on a site that promises Spanish from the first release. An empty result set
reads as "California trains nobody for this". It was "this search cannot hear you".

The guarantee under test here is narrow and load-bearing: **a SOC a program feeds is present in
this table exactly when the Department publishes a Spanish record for it.** The front end
counts absences to tell a reader that a job has no Spanish name on record rather than that no
programs train for it (`spanishTitleGap` in web/lib/search.ts), and that sentence is only true
if a missing key cannot also mean "had a record but nothing worth indexing" -- which is exactly
what a missing key means in the alternate-title table beside it.
"""

from __future__ import annotations

from typing import Any

from afterward.build import fold_accents, spanish_title_index


def _occupation(soc: str, spanish: dict[str, Any] | None) -> dict[str, Any]:
    return {"soc_code": soc, "title": f"Occupation {soc}", "spanish": spanish}


def _payload(*socs: str) -> dict[str, Any]:
    return {"uuid": "u", "soc_codes": list(socs)}


NURSE_ES = {
    "title": "Enfermeras Registradas",
    "description": "…",
    "also_called": ["Enfermera de Piso", "Enfermera Jefa"],
}


class TestWhatReachesTheTable:
    def test_the_title_comes_first_and_the_also_called_terms_follow(self) -> None:
        table = spanish_title_index(
            [_payload("29-1141")], {"29-1141": _occupation("29-1141", NURSE_ES)}
        )
        assert table == {
            "29-1141": ["Enfermeras Registradas", "Enfermera de Piso", "Enfermera Jefa"]
        }

    def test_only_socs_a_program_actually_feeds(self) -> None:
        # The table travels to every visitor. An occupation nothing trains for is weight with
        # no reader, exactly as `alternate_title_index` already decided.
        occupations = {
            "29-1141": _occupation("29-1141", NURSE_ES),
            "51-4121": _occupation("51-4121", {"title": "Soldadores", "also_called": []}),
        }
        table = spanish_title_index([_payload("29-1141")], occupations)
        assert list(table) == ["29-1141"]

    def test_terms_that_differ_only_in_accent_or_case_are_indexed_once(self) -> None:
        # Mi Proximo Paso's `also_called` does repeat a title with different accenting. Two
        # spellings of one term buy nothing: the front end folds both sides before comparing.
        table = spanish_title_index(
            [_payload("29-2052")],
            {
                "29-2052": _occupation(
                    "29-2052",
                    {
                        "title": "Técnico de Farmacia",
                        "also_called": ["Tecnico de Farmacia", "TÉCNICO DE FARMACIA", "Auxiliar"],
                    },
                )
            },
        )
        assert table == {"29-2052": ["Técnico de Farmacia", "Auxiliar"]}

    def test_a_term_that_matches_an_english_string_is_kept(self) -> None:
        """The two tables are scored separately, so an overlap costs nothing.

        Dropping "Auditores" because "Auditors" exists would make the Spanish table depend on
        the English one, and a reader typing the Spanish word would lose the match.
        """
        table = spanish_title_index(
            [_payload("13-2011")],
            {
                "13-2011": {
                    "soc_code": "13-2011",
                    "title": "Auditores",
                    "spanish": {"title": "Auditores", "also_called": []},
                }
            },
        )
        assert table == {"13-2011": ["Auditores"]}

    def test_ordering_does_not_depend_on_the_order_programs_arrive_in(self) -> None:
        occupations = {
            "29-1141": _occupation("29-1141", NURSE_ES),
            "51-4121": _occupation("51-4121", {"title": "Soldadores", "also_called": []}),
        }
        forwards = spanish_title_index([_payload("29-1141"), _payload("51-4121")], occupations)
        backwards = spanish_title_index([_payload("51-4121"), _payload("29-1141")], occupations)
        assert list(forwards) == list(backwards) == ["29-1141", "51-4121"]


class TestAMissingKeyMeansExactlyOneThing:
    """The guarantee the interface's sentence rests on."""

    def test_an_occupation_with_no_spanish_record_is_absent(self) -> None:
        table = spanish_title_index(
            [_payload("27-3091")], {"27-3091": _occupation("27-3091", None)}
        )
        assert table == {}

    def test_an_occupation_the_build_never_saw_is_absent(self) -> None:
        assert spanish_title_index([_payload("99-9999")], {}) == {}

    def test_a_record_can_never_produce_an_empty_list(self) -> None:
        """The other half of the guarantee: present-but-empty must be impossible.

        If a Spanish record could yield `[]`, a present key would stop meaning "has a Spanish
        name" and the count the search page publishes would be measuring something else.
        """
        empty_titles: list[dict[str, Any]] = [
            {"title": "", "also_called": []},
            {"title": "   ", "also_called": ["algo"]},
            {"title": None, "also_called": ["algo"]},
            {"also_called": ["algo"]},
        ]
        for spanish in empty_titles:
            table = spanish_title_index(
                [_payload("29-1141")], {"29-1141": _occupation("29-1141", spanish)}
            )
            assert table == {}, spanish
        for soc, terms in spanish_title_index(
            [_payload("29-1141")], {"29-1141": _occupation("29-1141", NURSE_ES)}
        ).items():
            assert terms, soc

    def test_a_malformed_spanish_block_is_absent_rather_than_half_indexed(self) -> None:
        # A record that is not an object at all: absent, never a partial entry that would read
        # as "this occupation has a Spanish name".
        for spanish in ["Enfermeras", 42, []]:
            table = spanish_title_index(
                [_payload("29-1141")],
                {"29-1141": {"soc_code": "29-1141", "title": "x", "spanish": spanish}},
            )
            assert table == {}, spanish

    def test_a_non_string_among_the_also_called_terms_is_skipped_not_indexed(self) -> None:
        table = spanish_title_index(
            [_payload("29-1141")],
            {
                "29-1141": _occupation(
                    "29-1141", {"title": "Enfermeras", "also_called": [None, 7, "Enfermera"]}
                )
            },
        )
        assert table == {"29-1141": ["Enfermeras", "Enfermera"]}


class TestFoldAccents:
    def test_drops_the_marks_spanish_actually_uses(self) -> None:
        assert fold_accents("Enfermería") == "Enfermeria"
        assert fold_accents("Diseñador Gráfico") == "Disenador Grafico"

    def test_leaves_text_with_nothing_to_fold_exactly_as_it_was(self) -> None:
        for text in ["Registered Nurses", "CDL", "", "29-1141"]:
            assert fold_accents(text) == text

    def test_the_emitted_terms_keep_their_accents(self) -> None:
        """Folding is for de-duplication here, and for matching in the browser.

        The Department's own spelling is what ships. If this ever emitted folded text, the
        table would stop being O*NET's words and start being this project's edit of them.
        """
        table = spanish_title_index(
            [_payload("29-2052")],
            {
                "29-2052": _occupation(
                    "29-2052", {"title": "Técnico de Farmacia", "also_called": []}
                )
            },
        )
        assert table["29-2052"] == ["Técnico de Farmacia"]
