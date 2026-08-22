"""A prompt edit that does not bump PROMPT_VERSION fails the build.

Eval results are only comparable within a prompt version, and the version is stamped on every
response. The digest pinned beside it is recomputed here from the prompt texts; changing a
prompt means updating both, in the same diff, on purpose.
"""

from __future__ import annotations

import re

from afterward.ask import PROMPT_DIGEST, PROMPT_VERSION
from afterward.ask.prompts import NARRATE_SYSTEM, STRUCTURE_SYSTEM, digest
from afterward.ask.translate import TRANSLATE_SYSTEM


def test_digest_matches_the_prompts() -> None:
    assert digest() == PROMPT_DIGEST, (
        "a system prompt changed: bump PROMPT_VERSION and set PROMPT_DIGEST to "
        f"{digest()!r} in the same change"
    )


def test_version_is_dated() -> None:
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}\.\d+", PROMPT_VERSION)


def test_prompts_carry_no_per_request_material() -> None:
    # The system prompts are cached; a date, an id or a figure in them would silently miss.
    for prompt in (STRUCTURE_SYSTEM, NARRATE_SYSTEM, TRANSLATE_SYSTEM):
        assert not re.search(r"20\d\d-\d\d-\d\d", prompt)
        assert "{{" not in prompt and "}}" not in prompt  # no template placeholders
