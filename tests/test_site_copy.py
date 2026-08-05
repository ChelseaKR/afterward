"""The funding wording the site publishes is the wording this project checked.

`tests/test_local_help.py::TestWording` scans every sentence in
:mod:`afterward.sources.local_help` for phrasing that turns a description of a public program
into a promise to one reader -- "you qualify", "guarantee", "free training", "at no cost to
you". That check is worth nothing if the sentences a visitor actually reads are a second copy
of the text, edited in the web app where no such check runs.

The site is bilingual, and the English and the Spanish get there by different routes. The
English is copied from the module, so this asserts it is still the same bytes: change it in
`web/lib/i18n.ts` alone and this fails, which is the point -- the fix is to change the module,
where the sentence sits beside the regulation it rests on and under the wording check. The
Spanish is written in the web app, because there is nowhere else for it to be written, so it
gets its own tripwire here rather than none at all.

The Spanish tripwire is not a translation review and cannot be one. It catches the specific
failure that this feature can cause: a hedge that survives in English and evaporates in
Spanish, turning "may be able to" into "will". A human reviewer is still required, and the
comment above the block in `i18n.ts` says what they must check.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from afterward.sources.local_help import etpl_listing_note, funding_guidance

REPO_ROOT = Path(__file__).resolve().parent.parent
I18N = REPO_ROOT / "web" / "lib" / "i18n.ts"

FIRST_KEY = "fundingLede:"
LAST_KEY = "fundingRuleLabel:"
"""The first and last funding keys in each dictionary, used to slice the block out.

Sliced by key rather than by a marker comment because a comment is decoration and can be
moved or removed by anyone tidying the file, whereas these keys are load-bearing: the page
does not render without them.
"""


def _normalise(text: str) -> str:
    """Compare meaning-preserving text, not TypeScript formatting.

    Three things differ between a Python string and the same string in a `.ts` file and none
    of them are the wording: a long string may be split across lines with `+`, indentation
    turns into whitespace runs, and a double quote arrives escaped.
    """
    joined = re.sub(r'[`"]\s*\+\s*[`"]', "", text)
    return re.sub(r"\s+", " ", joined.replace('\\"', '"'))


def _source() -> str:
    return I18N.read_text(encoding="utf-8")


def _block(source: str, *, spanish: bool) -> str:
    """The funding keys of one dictionary.

    The two dictionaries are the two halves of the file either side of `const es`, and each
    holds the same keys, so a naive search finds the English copy of a Spanish string and vice
    versa. Splitting first is what keeps the two apart.
    """
    english, marker, spanish_side = source.partition("const es: Dictionary = {")
    assert marker, "i18n.ts no longer declares the Spanish dictionary as expected"
    half = spanish_side if spanish else english

    start = half.index(FIRST_KEY)
    end = half.index(LAST_KEY, start)
    return half[start : half.index("\n", end)]


def _published_strings() -> dict[str, str]:
    """Every sentence the program page publishes, keyed by where it comes from."""
    guidance = funding_guidance()
    # The one string carrying a date. The web app interpolates the snapshot with a template
    # literal, so the module is asked for the same sentence with the same hole in it.
    strings = {
        "etpl_listing_note": etpl_listing_note("${date}"),
        "who_decides": guidance.who_decides,
    }
    for step in guidance.steps_for_program_page():
        strings[f"step.{step.step_id}.heading"] = step.heading
        strings[f"step.{step.step_id}.detail"] = step.detail
    for question in guidance.questions:
        strings[f"question.{question.question_id}.ask"] = question.ask
        strings[f"question.{question.question_id}.because"] = question.because
    return strings


class TestEnglishIsTheCheckedWording:
    def test_the_i18n_file_exists_where_this_test_expects_it(self) -> None:
        # A moved file must fail loudly rather than turn every assertion below into a pass.
        assert I18N.exists(), f"no {I18N}"

    @pytest.mark.parametrize("origin", sorted(_published_strings()))
    def test_every_published_sentence_is_the_modules_own(self, origin: str) -> None:
        english = _normalise(_block(_source(), spanish=False))
        expected = _normalise(_published_strings()[origin])
        assert expected in english, (
            f"{origin} is not in web/lib/i18n.ts as this module writes it. The English on the "
            "site must be the English the wording check scans: edit "
            "src/afterward/sources/local_help.py and copy the sentence across, rather than "
            "editing it in the web app where nothing checks it."
        )

    def test_the_english_block_still_carries_no_promise(self) -> None:
        """The same tripwire, over what actually ships rather than over the module.

        Belt and braces with the test above: if the comparison ever loosens, the phrasing
        check still runs on the published bytes.
        """
        from tests.test_local_help import PROMISES

        english = _normalise(_block(_source(), spanish=False)).casefold()
        assert [phrase for phrase in PROMISES if phrase in english] == []


PROMISES_ES = (
    "garantiz",
    "gratis",
    "gratuit",
    "sin costo",
    "sin ningún costo",
    "usted califica",
    "usted es elegible",
    "le pagaremos",
    "vamos a pagar",
    "solicite aquí",
    "recibirá",
    "obtendrá",
    "tiene derecho a",
)
"""Spanish phrasings that would promise a reader something this site cannot promise.

The counterpart of `PROMISES`, and matched inside negations for the same reason: "no se
garantiza" is read by a hurried eye as "garantiza". "garantiz" catches the whole family --
garantiza, garantía, garantizado -- and California's own guidance uses exactly that word,
which is why the module paraphrases rather than quotes it.

"tiene derecho a" is here because it is the natural Spanish for a right or an entitlement, and
WIOA is explicitly not an entitlement program. "recibirá" and "obtendrá" are the future tense
doing the damage: the future indicative states what will happen, where every sentence here is
about what the rules allow.
"""


class TestSpanishCarriesTheSameHedges:
    def test_the_spanish_block_promises_nothing(self) -> None:
        spanish = _normalise(_block(_source(), spanish=True)).casefold()
        offences = [phrase for phrase in PROMISES_ES if phrase in spanish]
        assert offences == [], (
            f"Spanish funding copy contains {offences}. Paraphrase rather than negate: a "
            "reader skimming official-looking prose takes the word and drops the 'no'."
        )

    def test_the_snapshot_claim_stays_in_the_past_tense(self) -> None:
        """The single most dangerous word in the translation.

        "Estaba en la lista" is the claim the data supports -- the program was on California's
        list when the state last reported. "Está en la lista" is a claim about today that
        nothing here can support, and one letter separates them.
        """
        spanish = _normalise(_block(_source(), spanish=True))
        assert "estaba en la Lista de Instituciones de Capacitación Elegibles" in spanish

    def test_the_spanish_says_who_decides_and_that_this_site_does_not(self) -> None:
        spanish = _normalise(_block(_source(), spanish=True)).casefold()
        assert "junta local de desarrollo laboral" in spanish
        assert "no lo decide este sitio" in spanish
        assert "nada de lo que dice esta página es una promesa de financiamiento" in spanish

    def test_no_spanish_string_is_left_as_its_english(self) -> None:
        """`web/lib/i18n.test.ts` proves this for the dictionary as a whole.

        Repeated here for this block alone, because it is the block where an untranslated
        string does the most harm and the one most likely to be added to in a hurry.
        """
        spanish = _normalise(_block(_source(), spanish=True))
        for origin, english in _published_strings().items():
            assert _normalise(english) not in spanish, f"{origin} is still in English in `es`"
