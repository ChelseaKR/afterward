"""Whether an address that now redirects somewhere else is still the provider's.

:mod:`afterward.sources.link_check` establishes that a provider URL answered. When the
answer arrives from a *different* domain it records ``redirected_offsite`` and stops, because
the two things that produce that record are indistinguishable from the redirect alone:

* a **rebrand or migration** -- ``moler.org`` to ``moler.edu``, a college's catalogue moving
  onto a vendor's platform, an adult school folded into its district's site; and
* a **hijack** -- the school's domain lapsed, somebody else registered it, and it now points
  at whatever they are monetising. Three are in this dataset:
  ``giligiacollege.com`` and ``eastvalleycollege.com`` serve Indonesian gambling and lottery
  sites, ``hollywoodculturalcollege.com`` serves an unrelated Baltimore charity.

Both are live, well-formed pages that answer 200 from another host. Until this module existed
the pipeline published all of them as a confident "Provider's website" link, which meant six
program pages handed a Californian a link to a domain somebody else controls.

**What actually separates them.** Not the redirect, and not how alike the two names look --
whoever holds a lapsed domain can point it anywhere and can register a similar-looking one.
The separator is *corroboration from a source the holder of the old domain does not control*:

``REGISTRY``
    The destination sits under an ``.edu`` or ``.gov`` registrable domain that the filed URL
    already sat under. Those two zones are not open registrations: ``.edu`` is restricted to
    accredited United States postsecondary institutions, so one registrable domain there is
    one institution, and a redirect within it cannot have changed hands without the
    institution.

``FEED``
    The destination's registrable domain is filed as a program URL by another record in the
    federal ETPL feed naming the same provider. The feed is filed by providers to the state
    and published by the U.S. Department of Labor; a squatter who bought a lapsed domain has
    no way to put a line in it.

``ACCREDITED_NAME``
    The destination is an ``.edu`` registrable domain whose name continues the filed one --
    ``moler.org`` to ``moler.edu``, ``air-streams.com`` to ``airstreamsrenewables.edu``.
    Name continuity is worth nothing on its own, and everything in combination with a zone
    the destination had to be an accredited institution to enter.

``REVIEW``
    A person opened it and wrote down what they found, in ``provider-link-review.json``,
    with the evidence and the date. This is the only rule that can conclude ``unrelated``,
    because "this is somebody else's website now" is a judgement about content and no
    mechanical signal available here makes it.

Anything none of those reaches is **unresolved**, and unresolved is published as unresolved:
the URL as filed, as plain text, with a sentence saying the address now redirects somewhere
this project could not confirm belongs to the provider. Not linked. The asymmetry is
deliberate and is the opposite of the one everywhere else in :mod:`link_check`, where the
harm to avoid is calling a working school dead. Here the reader is not being denied a school
they could otherwise reach -- the filed address does not reach the school either way -- and
the cost of guessing wrong is handing somebody a link to a page the school does not control.

Every review entry is keyed on the destination it was written about. If the redirect target
changes, the entry stops matching and the link falls back to unresolved rather than carrying
a stale blessing onto a destination nobody looked at.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal

import httpx

REVIEW_PATH: Final = Path(__file__).with_name("provider-link-review.json")
"""The hand-review ledger, committed beside this module.

Beside the code rather than under ``data/`` because ``data/`` is gitignored and rebuilt: this
file is a record of what a person established, it must survive a rebuild, and it must arrive
as a reviewable diff.
"""

REVIEW_VERSION: Final = 1
"""On-disk shape of the ledger. A file that says anything else is refused, not guessed at."""

ReviewStatus = Literal["same_provider", "unrelated", "for_sale"]
"""What a reviewer concluded.

``for_sale`` is separated from ``unrelated`` because the two want different sentences on the
page: an address being advertised for sale is never coming back and a reader must be told to
look the school up by name instead, where an address serving somebody else's live site is a
different situation with the same conclusion. Both are "not the provider".

There is no "unsure" member: an entry that is not written is already unresolved, and a value
meaning "we looked and could not tell" would only add a second spelling of the default.
"""

Resolution = Literal["same_provider", "unrelated", "for_sale", "unresolved"]
"""What this module concludes about one off-site redirect.

``unresolved`` is a real answer and the most common one. It is not an error state and not a
verdict about the provider -- it says only that nothing here can establish who is at the
other end.
"""

RULE_REGISTRY: Final = "registry"
RULE_FEED: Final = "feed"
RULE_ACCREDITED_NAME: Final = "accredited_name"
RULE_REVIEW: Final = "review"
RULE_NONE: Final = "none"

INSTITUTIONAL_ZONES: Final[frozenset[str]] = frozenset({"edu", "gov"})
"""Top-level domains whose registrations are not open to anyone with a card.

``.edu`` is administered under a U.S. Department of Education contract and is limited to
accredited postsecondary institutions; ``.gov`` to United States government bodies. That is
what makes them evidence rather than decoration: a squatter can buy ``giligiacollege.com``
the day it lapses and cannot obtain ``giligia.edu`` at all.
"""

AMBIGUOUS_SUFFIXES: Final[frozenset[str]] = frozenset(
    {
        # Two-label suffixes under which the *third* label is the registrable one. Vendored
        # rather than imported: this project takes no new dependency for a list of five, and
        # anything not on it is handled by refusing to answer rather than by answering wrong.
        "ca.us",
        "k12.ca.us",
        "co.uk",
        "org.uk",
        "ac.uk",
        "com.mx",
        "edu.mx",
    }
)
"""Public suffixes with a dot in them, where "the last two labels" is not the registrable
domain. A host under one of these gets ``None`` from :func:`registrable_domain` -- no
registrable domain means no registry or feed evidence, which fails towards unresolved."""

_NOT_ALPHANUMERIC: Final = re.compile(r"[^a-z0-9]+")

_ORGANISATION_NOISE: Final[frozenset[str]] = frozenset(
    {"inc", "incorporated", "llc", "lp", "ltd", "corp", "corporation", "co", "the"}
)
"""Words a filing carries that a domain never does. Stripped before comparing a provider's
filed name with a domain label, so ``Airstreams Renewables, Inc.`` can match
``airstreamsrenewables.edu``."""


@dataclass(frozen=True)
class ReviewEntry:
    """One hand review of one redirect, as the ledger records it."""

    filed_host: str
    """Host of the URL the federal record filed, lowercased, without ``www.``."""
    destination: str
    """Host the redirect ended at when it was reviewed. The entry applies to this destination
    and no other: a redirect that moves somewhere new is unreviewed again, which is what
    keeps a review from blessing a page nobody looked at."""
    status: ReviewStatus
    provider_name: str
    """The provider as the feed names it, so the entry can be read without the dataset."""
    evidence: str
    """What was found, in a sentence, so the entry can be argued with rather than trusted."""
    reviewed_on: str
    """ISO date. A review has a shelf life and the site prints the date it acted on."""

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ReviewEntry:
        status = payload["status"]
        if status not in ("same_provider", "unrelated", "for_sale"):
            raise ValueError(f"unknown review status {status!r}")
        return cls(
            filed_host=str(payload["filed_host"]).lower(),
            destination=str(payload["destination"]).lower(),
            status=status,
            provider_name=str(payload["provider_name"]),
            evidence=str(payload["evidence"]),
            reviewed_on=str(payload["reviewed_on"]),
        )


@dataclass(frozen=True)
class RedirectVerdict:
    """What was concluded about one off-site redirect, and on what grounds."""

    resolution: Resolution
    rule: str
    """Which of the rules above answered, or :data:`RULE_NONE`."""
    evidence: str
    """Why, in a sentence. Empty only for :data:`RULE_NONE`."""

    @property
    def publishable(self) -> bool:
        """Whether a reader may be sent to this destination.

        Only an affirmative resolution earns a link. ``unresolved`` and ``unrelated`` both
        do not, and they differ in what the page says rather than in what it links.
        """
        return self.resolution == "same_provider"


UNRESOLVED: Final = RedirectVerdict("unresolved", RULE_NONE, "")
"""The answer when no rule reached it. Deliberately the default in every code path."""


def host_of(url: str | None) -> str | None:
    """The lowercased host of ``url`` without ``www.``, or ``None`` if it has none."""
    if not url:
        return None
    host = (httpx.URL(url).host or "").lower()
    return host.removeprefix("www.") or None


def registrable_domain(host: str | None) -> str | None:
    """The domain somebody registered, or ``None`` when that cannot be said.

    ``globalcampus.sdsu.edu`` gives ``sdsu.edu``. A host under one of
    :data:`AMBIGUOUS_SUFFIXES` gives ``None``, because the answer would be a public suffix
    rather than a registration and every rule that reads this treats ``None`` as no evidence.
    """
    if not host:
        return None
    labels = host.strip(".").split(".")
    if len(labels) < 2:
        return None
    if ".".join(labels[-2:]) in AMBIGUOUS_SUFFIXES or ".".join(labels[-3:]) in AMBIGUOUS_SUFFIXES:
        return None
    return ".".join(labels[-2:])


def _zone(domain: str | None) -> str:
    return domain.rsplit(".", 1)[-1] if domain else ""


def normalise_name(text: str | None) -> str:
    """A name reduced to what a domain label could carry: lowercase letters and digits.

    ``Airstreams Renewables, Inc.`` becomes ``airstreamsrenewables``; ``AAA Institute``
    becomes ``aaainstitute``. Organisation noise is dropped whole rather than as a substring,
    so ``Colton`` keeps its ``co``.
    """
    if not text:
        return ""
    words = [word for word in _NOT_ALPHANUMERIC.split(text.lower()) if word]
    kept = [word for word in words if word not in _ORGANISATION_NOISE]
    return "".join(kept or words)


def _label(domain: str | None) -> str:
    """The registrable label of a domain, normalised. ``moler.edu`` gives ``moler``."""
    return normalise_name(domain.rsplit(".", 1)[0]) if domain else ""


def name_continues(destination: str, *, filed: str | None, provider_name: str | None) -> bool:
    """Whether a destination domain carries the same name the record already carried.

    True when the destination's label equals the filed URL's label -- the same name in a
    different zone, which is what ``moler.org`` to ``moler.edu`` is -- or when it is the
    front of the provider's filed name, which is what ``air-streams.com`` to
    ``airstreamsrenewables.edu`` is.

    Deliberately not a similarity score. ``angelescollege.edu`` to ``angelesuniversity.edu``
    shares a word and fails this, which is correct: a shared word is a coincidence a hijack
    can arrange and a rename is a fact a person can check in a minute.
    """
    label = _label(destination)
    if not label:
        return False
    if label == _label(filed):
        return True
    name = normalise_name(provider_name)
    return bool(name) and name.startswith(label)


def load_review(path: Path = REVIEW_PATH) -> tuple[ReviewEntry, ...]:
    """Read the hand-review ledger.

    Strict, like :func:`afterward.sources.link_check.checks_from_document` and for the same
    reason: this file is the only thing standing between three hijacked domains and a
    published link, and a version of it this code does not understand must stop a build
    rather than be read as an empty review.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    version = payload.get("version")
    if version != REVIEW_VERSION:
        raise ValueError(f"unsupported provider-link-review version {version!r}")
    return tuple(ReviewEntry.from_dict(entry) for entry in payload["entries"])


def rejected_hosts(entries: Iterable[ReviewEntry]) -> dict[str, ReviewEntry]:
    """Every host a review found is not a provider's, by host.

    Both ends of each rejected pair. The destination is the site somebody else is running;
    the filed host is the address that carries a reader there, and it is the one a page would
    actually print in an ``href``. A gate that checked only destinations would pass a page
    linking ``giligiacollege.com`` -- which is exactly the page this is here to stop.
    """
    both: dict[str, ReviewEntry] = {}
    for entry in entries:
        if entry.status == "same_provider":
            continue
        both.setdefault(entry.destination, entry)
        both.setdefault(entry.filed_host, entry)
    return both


def filed_hosts(payloads: Iterable[Mapping[str, Any]]) -> dict[str, frozenset[str]]:
    """Every host the feed files a program URL on, and which providers filed it.

    This is the corroboration source for :data:`RULE_FEED`. It is built from the dataset the
    build is emitting, so it says what the federal record says today rather than what a
    destination says about itself.

    Hosts rather than registrable domains, deliberately. ``butte.curriqunet.com`` is filed by
    Butte College, and that is evidence about *that* host and not about every college's
    catalogue on the same vendor -- indexing by ``curriqunet.com`` would let one provider's
    filing vouch for a redirect to another subdomain nobody filed.
    """
    found: dict[str, set[str]] = {}
    for payload in payloads:
        host = host_of(payload.get("program_url"))
        name = normalise_name(payload.get("provider_name"))
        if host and name:
            found.setdefault(host, set()).add(name)
    return {host: frozenset(names) for host, names in found.items()}


@dataclass(frozen=True)
class OffsiteReviewer:
    """Resolves one off-site redirect against the ledger and the feed.

    Built once per build. ``resolve`` is pure: same inputs, same answer, no network -- the
    destination is never fetched here, and for the hijacked domains that is not an
    optimisation but the point.
    """

    entries: tuple[ReviewEntry, ...] = ()
    hosts: Mapping[str, frozenset[str]] = field(default_factory=dict)

    @classmethod
    def from_feed(
        cls,
        payloads: Iterable[Mapping[str, Any]],
        *,
        path: Path = REVIEW_PATH,
    ) -> OffsiteReviewer:
        return cls(entries=load_review(path), hosts=filed_hosts(payloads))

    def _reviewed(self, filed: str | None, destination: str | None) -> RedirectVerdict | None:
        """A hand review of exactly this pair of hosts, if one was written."""
        if filed is None or destination is None:
            return None
        for entry in self.entries:
            if entry.filed_host == filed and entry.destination == destination:
                return RedirectVerdict(
                    entry.status,
                    RULE_REVIEW,
                    f"{entry.evidence} (reviewed {entry.reviewed_on})",
                )
        return None

    def _corroborated(
        self, *, filed: str | None, destination: str | None, provider_name: str | None
    ) -> RedirectVerdict | None:
        """The three rules a machine can apply, in order of how little they assume."""
        filed_domain = registrable_domain(filed)
        domain = registrable_domain(destination)
        if destination is None or domain is None:
            return None

        if domain == filed_domain and _zone(domain) in INSTITUTIONAL_ZONES:
            return RedirectVerdict(
                "same_provider",
                RULE_REGISTRY,
                f"stays inside {domain}, a registration restricted to the institution",
            )

        if normalise_name(provider_name) in self.hosts.get(destination, frozenset()):
            return RedirectVerdict(
                "same_provider",
                RULE_FEED,
                f"the federal feed files {destination} for this same provider",
            )

        if _zone(domain) == "edu" and name_continues(
            domain, filed=filed_domain, provider_name=provider_name
        ):
            return RedirectVerdict(
                "same_provider",
                RULE_ACCREDITED_NAME,
                f"{domain} continues the filed name in a zone limited to accredited institutions",
            )
        return None

    def resolve(
        self, *, url: str, final_url: str | None, provider_name: str | None
    ) -> RedirectVerdict:
        """What is at the other end of this redirect, as far as anything here can say.

        The ledger is asked first, because it is the only rule with eyes: it is what can say
        a destination is somebody else's, and it is what can confirm a rebrand no automatic
        rule reaches. Everything after it can only *confirm*, and anything none of them
        reaches is :data:`UNRESOLVED`.
        """
        filed = host_of(url)
        destination = host_of(final_url)
        reviewed = self._reviewed(filed, destination)
        if reviewed is not None:
            return reviewed
        corroborated = self._corroborated(
            filed=filed, destination=destination, provider_name=provider_name
        )
        return corroborated if corroborated is not None else UNRESOLVED
