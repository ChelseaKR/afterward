"""Who counts as one provider, for every figure this project publishes.

One snapshot used to yield three answers. On ``dataset-2026-09-12`` the About page said
**584** providers, the provider index listed **581**, and the pipeline's duplicate-cohort
pass keyed **583** -- all three counted from the same 3,266 records, and a reader who
followed the About page's number to the index found three fewer providers than they had
been promised, with nothing on either page explaining the gap.

The three rules were the raw filed string, :func:`afterward.sources.dol_etp.normalize_provider`
(case and internal whitespace), and the web's URL slug. This module is the third one, moved
to where a published count can reach it, because the site already *behaves* as though the
slug is the answer: it mints one provider page per slug, and ``web/lib/etplCoverage.ts``
reports provider silence over the same keys, deliberately ("one identity function, one
answer" -- its own words). A published count that disagreed with the pages it was counting
was the odd one out, not the other way round.

Why the slug rather than the raw name. Three of California's providers file under two
spellings each -- a cased and a shouting form, and one that alternates ``&`` with ``and``:

    DIALYSIS EDUCATION SERVICES LLC         /  Dialysis Education Services, LLC
    PROCAREER ACADEMY                       /  Procareer Academy
    Virtual Design & Construction Institute /  Virtual Design and Construction Institute

``normalize_provider``'s docstring already argued the case for the first two: a check keyed
on the literal string "would let a provider evade it by shouting". The same is true of a
published count, and the ampersand pair shows the argument does not stop at case.

WHAT THIS IS NOT

Not :func:`afterward.sources.dol_etp.normalize_provider`, which stays where it is. That one
is a *join key over filed text* -- ``dol_bulk`` runs program names through it too -- and it
folds only what cannot change a word. Widening it to this rule would loosen the four-key
bulk join and move figures published under D9, which is a different decision from this one.

Kept in step with ``slugify`` in ``web/lib/providers.ts``, which mints the URLs. Neither can
be derived from the other across the language boundary, so ``fixtures/provider-identity.json``
holds the cases both must agree on and both test suites read it.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

#: The combining marks NFD separates out, exactly as `web/lib/providers.ts` spells the range.
#: Deliberately the same narrow range rather than `unicodedata.combining`, which covers more:
#: a mark this stripped and the URL rule did not would turn into a hyphen on one side of the
#: boundary and vanish on the other, which is two different provider pages.
COMBINING_MARKS = re.compile(r"[\u0300-\u036f]")

#: Longest slug a provider URL carries. Matches the `.slice(0, 80)` in web/lib/providers.ts.
#: Two providers whose names differ only past the 80th character would share a page, and so
#: must share a count: the slug is the identity, truncation included.
SLUG_MAX_LENGTH = 80


def provider_slug(name: str | None) -> str | None:
    """The published identity of a provider, or ``None`` if the name carries none.

    Accents are folded, ``&`` reads as ``and``, and every other run of non-alphanumerics
    becomes a single hyphen -- the rule that mints ``/providers/<slug>/``. A name that
    survives none of that (``"!!!"``, ``"   "``) has no identity here and is excluded from
    counts rather than pooled under a shared blank, which would merge two anonymous filers
    into one provider.
    """
    if name is None:
        return None
    stripped = COMBINING_MARKS.sub("", unicodedata.normalize("NFD", name))
    lowered = stripped.lower().replace("&", " and ")
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug[:SLUG_MAX_LENGTH] or None


def count_providers(names: Iterable[str | None]) -> int:
    """How many providers a set of filed names describes.

    The one expression of "how many providers" on this side of the language boundary, so a
    caller cannot accidentally write a fourth rule while counting.
    """
    return len({slug for slug in map(provider_slug, names) if slug is not None})
