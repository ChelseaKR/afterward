"""The site must have a sentence for every reason the pipeline can refuse to place a program.

:data:`afterward.build.AREA_UNPLACED_REASONS` is the pipeline's closed vocabulary for *why* a
program has no EDD area, and ``region_unplaced_reason`` carries one of those five words onto
every unplaced record. ``web/lib/i18n.ts`` turns that word into the sentence a reader gets.

The two can drift silently and in the worse direction. Adding a sixth reason in Python is a
one-line change; the site's ``switch`` would keep compiling, keep passing its own tests, and
send every program carrying the new reason to the default branch -- which says, correctly but
uselessly, that this record does not say which rule declined. The reader would be told the
site does not know something the dataset does know.

This is the tripwire for that. It is a Python test rather than a TypeScript one because the
vocabulary lives in Python: only here can the assertion read the real constant instead of a
copy of it, and a test that compared two hand-maintained lists would pass while both were
wrong together.

Both dictionaries are checked separately. An English sentence added without its Spanish
counterpart is the exact shape of half-translated page this project's i18n tests exist to
catch, and the completeness test in ``web/lib/i18n.test.ts`` cannot see inside a function
body: it compares whole values, and both dictionaries hold a function here either way.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from afterward.build import AREA_UNPLACED_REASONS

REPO_ROOT = Path(__file__).resolve().parent.parent
I18N = REPO_ROOT / "web" / "lib" / "i18n.ts"

SPANISH_MARKER = "const es: Dictionary = {"
"""Where the English dictionary ends and the Spanish one begins.

The same split ``tests/test_site_copy.py`` uses, and for the same reason: the two dictionaries
carry the same keys, so a search over the whole file finds the English copy of a Spanish
string and reports both halves present when only one is.
"""


def _halves() -> tuple[str, str]:
    source = I18N.read_text(encoding="utf-8")
    english, marker, spanish = source.partition(SPANISH_MARKER)
    assert marker, f"{I18N} no longer declares the Spanish dictionary as {SPANISH_MARKER!r}"
    return english, spanish


FUNCTION = "regionUnplacedBody:"
END_OF_FUNCTION = "\n  },\n"
"""The two-space closing brace of a dictionary entry, which its body cannot contain.

Sliced rather than scanned whole, so an unrelated ``switch`` added anywhere else in
``i18n.ts`` cannot make this test either pass or fail. The end marker is indentation-bound to
the dictionary's own nesting level: every ``case`` inside this function returns from a deeper
one.
"""


def _cases(half: str) -> set[str]:
    """The reason literals ``regionUnplacedBody`` switches on, in one dictionary."""
    start = half.index(FUNCTION)
    end = half.index(END_OF_FUNCTION, start)
    return set(re.findall(r'case\s+"([a-z_]+)":', half[start:end]))


class TestEveryRefusalHasASentence:
    def test_the_i18n_file_exists_where_this_test_expects_it(self) -> None:
        # A moved file would turn every assertion below into a pass over an empty string.
        assert I18N.exists(), f"no {I18N}"

    def test_the_vocabulary_is_not_empty(self) -> None:
        # Guards the guard: an empty constant would satisfy every parametrised case below
        # by never generating one, which is a green run that measured nothing.
        assert len(AREA_UNPLACED_REASONS) >= 5

    @pytest.mark.parametrize("reason", AREA_UNPLACED_REASONS)
    @pytest.mark.parametrize("lang", ["en", "es"])
    def test_each_reason_is_answered_in_each_language(self, reason: str, lang: str) -> None:
        english, spanish = _halves()
        half = english if lang == "en" else spanish
        assert reason in _cases(half), (
            f"web/lib/i18n.ts has no {lang} sentence for region_unplaced_reason "
            f"{reason!r}. Every program carrying it would fall to the default branch, which "
            "tells the reader the record does not say why -- when it does say why. Add a "
            "case to regionUnplacedBody in both dictionaries."
        )

    @pytest.mark.parametrize("lang", ["en", "es"])
    def test_no_sentence_answers_a_reason_the_pipeline_cannot_emit(self, lang: str) -> None:
        """A case for a word nothing produces is dead copy that reads as coverage.

        It is also how a renamed reason hides: the old case stays, the new one is never
        added, and the file looks like it handles five things.
        """
        english, spanish = _halves()
        half = english if lang == "en" else spanish
        assert _cases(half) <= set(AREA_UNPLACED_REASONS)
