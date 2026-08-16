"""Tests for telling a provider's rebrand from somebody else holding their old address.

The property defended here is the opposite of the one :mod:`tests.test_link_check` defends,
and deliberately so. There, the harm to avoid is calling a working school dead. Here, the
filed address does not reach the school either way -- it goes somewhere else -- so the reader
loses nothing by being told that, and stands to lose a great deal by being handed a link to a
domain somebody else now controls. Every ambiguous case must therefore fail towards
*unresolved*, and the tests below spend most of their time proving that nothing plausible,
similar-looking, or merely convenient can talk its way into a link.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from afterward.sources.link_review import (
    REVIEW_PATH,
    UNRESOLVED,
    OffsiteReviewer,
    ReviewEntry,
    filed_hosts,
    host_of,
    load_review,
    name_continues,
    normalise_name,
    registrable_domain,
)

# The three addresses the 2026-08-05 hand review found in somebody else's hands, with the
# destinations the checker recorded on 2026-08-04. Named here rather than paraphrased: these
# exact pairs are what six California program pages linked to, and a test that does not name
# them cannot fail when one comes back.
HIJACKED: list[tuple[str, str, str]] = [
    ("http://www.giligiacollege.com", "https://seinquote.com", "Giligia College"),
    (
        "http://www.eastvalleycollege.com",
        "https://mechanicaljungle.com/",
        "East Valley College, Inc.",
    ),
    (
        "http://www.hollywoodculturalcollege.com",
        "https://www.stopglaucomajhu.org/",
        "Hollywood Cultural College",
    ),
]


def entry(**over: Any) -> ReviewEntry:
    base: dict[str, Any] = {
        "filed_host": "old.example",
        "destination": "new.example",
        "status": "same_provider",
        "provider_name": "Example College",
        "evidence": "checked by hand",
        "reviewed_on": "2026-08-15",
    }
    return ReviewEntry.from_dict({**base, **over})


class TestRegistrableDomain:
    """What was registered, or nothing. Never a guess."""

    @pytest.mark.parametrize(
        ("host", "expected"),
        [
            ("moler.edu", "moler.edu"),
            ("globalcampus.sdsu.edu", "sdsu.edu"),
            ("a.b.c.example.com", "example.com"),
            ("rcoe.us", "rcoe.us"),
        ],
    )
    def test_reads_the_registration_out_of_a_host(self, host: str, expected: str) -> None:
        assert registrable_domain(host) == expected

    @pytest.mark.parametrize("host", ["localhost", "", None, "sanjuan.k12.ca.us", "x.co.uk"])
    def test_refuses_to_answer_where_the_answer_would_be_a_public_suffix(
        self, host: str | None
    ) -> None:
        """A wrong registrable domain would make two unrelated districts look like one
        organisation. Returning nothing costs a confirmation; returning ``ca.us`` would
        manufacture one."""
        assert registrable_domain(host) is None

    def test_www_is_not_part_of_a_host(self) -> None:
        assert host_of("http://www.moler.org/programs/") == "moler.org"
        assert host_of(None) is None


class TestNameContinuity:
    def test_the_same_name_in_another_zone_continues_it(self) -> None:
        assert name_continues("moler.edu", filed="moler.org", provider_name="Moler Barber College")

    def test_a_longer_name_the_filing_already_carried_continues_it(self) -> None:
        assert name_continues(
            "airstreamsrenewables.edu",
            filed="air-streams.com",
            provider_name="Airstreams Renewables, Inc.",
        )

    def test_a_shared_word_is_not_continuity(self) -> None:
        """``Angeles College`` to ``angelesuniversity.edu`` is a real rename and this must
        still refuse it: a shared word is something a hijack can arrange, and a rename is
        something a person can confirm in a minute. It is in the ledger, not in this rule."""
        assert not name_continues(
            "angelesuniversity.edu", filed="angelescollege.edu", provider_name="Angeles College"
        )

    def test_a_generic_word_out_of_the_provider_name_is_not_continuity(self) -> None:
        assert not name_continues(
            "college.edu", filed="giligiacollege.com", provider_name="Giligia College"
        )

    def test_organisation_noise_does_not_block_a_match(self) -> None:
        assert normalise_name("Airstreams Renewables, Inc.") == "airstreamsrenewables"

    def test_a_name_that_is_only_noise_keeps_its_words(self) -> None:
        """Stripping every word would leave an empty key that matches nothing, or worse,
        everything."""
        assert normalise_name("The Co") == "theco"


class TestTheThreeHijackedDomains:
    """The reason this module exists, tested against the real committed review."""

    @pytest.fixture
    def reviewer(self) -> OffsiteReviewer:
        return OffsiteReviewer(entries=load_review(), hosts={})

    @pytest.mark.parametrize(("url", "destination", "provider"), HIJACKED)
    def test_is_not_the_provider(
        self, reviewer: OffsiteReviewer, url: str, destination: str, provider: str
    ) -> None:
        verdict = reviewer.resolve(url=url, final_url=destination, provider_name=provider)
        assert verdict.resolution == "unrelated"
        assert verdict.publishable is False

    @pytest.mark.parametrize(("url", "destination", "provider"), HIJACKED)
    def test_carries_the_evidence_and_the_date(
        self, reviewer: OffsiteReviewer, url: str, destination: str, provider: str
    ) -> None:
        verdict = reviewer.resolve(url=url, final_url=destination, provider_name=provider)
        assert "2026-08-05" in verdict.evidence

    @pytest.mark.parametrize(("url", "destination", "provider"), HIJACKED)
    def test_a_new_destination_at_the_same_address_is_unreviewed_again(
        self, reviewer: OffsiteReviewer, url: str, destination: str, provider: str
    ) -> None:
        """The review is about a pair, not about an address. If the squatter repoints it, the
        entry stops matching rather than vouching for a page nobody has seen."""
        verdict = reviewer.resolve(
            url=url, final_url="https://something-new.example/", provider_name=provider
        )
        assert verdict.resolution == "unresolved"


class TestCorroboration:
    """The three rules a machine may apply, and what each of them refuses."""

    def test_a_redirect_inside_one_institutions_edu_domain_is_that_institution(self) -> None:
        verdict = OffsiteReviewer().resolve(
            url="https://ces.sdsu.edu/program/x/",
            final_url="https://globalcampus.sdsu.edu/program/x/",
            provider_name="SDSU Global Campus",
        )
        assert verdict.resolution == "same_provider"
        assert verdict.rule == "registry"

    def test_the_same_trick_on_a_shared_host_is_not_evidence(self) -> None:
        """Two schools on one website builder share a registrable domain and nothing else.
        Restricting this rule to ``.edu`` and ``.gov`` is what keeps a redirect between two
        strangers' pages from reading as one organisation's."""
        verdict = OffsiteReviewer().resolve(
            url="https://a-school.wixsite.com/site",
            final_url="https://someone-else.wixsite.com/site",
            provider_name="A School",
        )
        assert verdict.resolution == "unresolved"

    def test_a_destination_the_feed_files_for_the_same_provider_is_corroborated(self) -> None:
        reviewer = OffsiteReviewer(
            hosts=filed_hosts(
                [
                    {
                        "program_url": "https://aaa-institute.com/programs/1",
                        "provider_name": "AAA Institute",
                    }
                ]
            )
        )
        verdict = reviewer.resolve(
            url="http://www.aaa-u.com",
            final_url="https://aaa-institute.com/",
            provider_name="AAA Institute",
        )
        assert verdict.resolution == "same_provider"
        assert verdict.rule == "feed"

    def test_another_providers_filing_does_not_vouch_for_this_one(self) -> None:
        reviewer = OffsiteReviewer(
            hosts=filed_hosts(
                [{"program_url": "https://vendor.example/x", "provider_name": "Some Other School"}]
            )
        )
        verdict = reviewer.resolve(
            url="http://www.aaa-u.com",
            final_url="https://vendor.example/x",
            provider_name="AAA Institute",
        )
        assert verdict.resolution == "unresolved"

    def test_one_colleges_subdomain_on_a_vendor_does_not_vouch_for_another(self) -> None:
        """The feed index is keyed on hosts rather than registrable domains for this: Butte
        College filing ``butte.curriqunet.com`` says nothing about ``cuesta.curriqunet.com``,
        and a domain-level index would have let it."""
        reviewer = OffsiteReviewer(
            hosts=filed_hosts(
                [
                    {
                        "program_url": "https://butte.curriqunet.com/Catalog/iq/1",
                        "provider_name": "Butte College",
                    }
                ]
            )
        )
        verdict = reviewer.resolve(
            url="http://www.curricunet.com/Cuesta/reports/x",
            final_url="https://cuesta.curriqunet.com",
            provider_name="Butte College",
        )
        assert verdict.resolution == "unresolved"

    def test_the_same_name_in_the_accredited_zone_is_corroborated(self) -> None:
        verdict = OffsiteReviewer().resolve(
            url="https://moler.org/programs/cosmetology-program/",
            final_url="https://moler.edu/programs/cosmetology/",
            provider_name="Moler Barber College - OAKLAND main campus",
        )
        assert verdict.resolution == "same_provider"
        assert verdict.rule == "accredited_name"

    def test_the_same_name_in_an_open_zone_is_not(self) -> None:
        """``nevadahelpdesk.tech`` to ``nevadahelpdesk.ai`` looks exactly like a rebrand and
        may well be one. Anyone can register the matching name in an open zone, including
        whoever took the old one, so this stays unresolved until a person checks."""
        verdict = OffsiteReviewer().resolve(
            url="https://nevadahelpdesk.tech",
            final_url="https://nevadahelpdesk.ai/",
            provider_name="Nevada Help Desk",
        )
        assert verdict.resolution == "unresolved"

    def test_a_destination_with_no_registration_to_read_is_unresolved(self) -> None:
        verdict = OffsiteReviewer().resolve(
            url="https://example.edu/x", final_url=None, provider_name="Example"
        )
        assert verdict == UNRESOLVED


class TestTheLedgerItself:
    def test_a_review_can_confirm_as_well_as_condemn(self) -> None:
        reviewer = OffsiteReviewer(
            entries=(entry(filed_host="old.example", destination="new.example"),)
        )
        verdict = reviewer.resolve(
            url="http://www.old.example/page", final_url="https://new.example/", provider_name="X"
        )
        assert verdict.resolution == "same_provider"
        assert verdict.rule == "review"

    def test_an_entry_for_another_pair_does_not_leak(self) -> None:
        reviewer = OffsiteReviewer(entries=(entry(status="unrelated"),))
        verdict = reviewer.resolve(
            url="http://elsewhere.example/", final_url="https://new.example/", provider_name="X"
        )
        assert verdict.resolution == "unresolved"

    def test_an_unknown_status_is_refused_rather_than_read_as_permission(self) -> None:
        with pytest.raises(ValueError, match="unknown review status"):
            entry(status="probably_fine")

    def test_a_ledger_from_another_shape_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "review.json"
        path.write_text(json.dumps({"version": 99, "entries": []}), encoding="utf-8")
        with pytest.raises(ValueError, match="unsupported provider-link-review version"):
            load_review(path)

    def test_the_committed_ledger_loads_and_every_entry_carries_its_evidence(self) -> None:
        entries = load_review(REVIEW_PATH)
        assert entries
        for record in entries:
            assert record.evidence.strip(), record.filed_host
            assert record.reviewed_on.startswith("2026-"), record.filed_host
            assert host_of(f"https://{record.destination}/") == record.destination

    def test_no_entry_confirms_a_domain_marketplace(self) -> None:
        """A blunt guard on the ledger's own content: the three marketplaces this corpus
        redirects into must never be recorded as a provider, whatever else is added."""
        marketplaces = {"hugedomains.com", "expireddomains.com", "unstoppabledomains.com"}
        for record in load_review(REVIEW_PATH):
            if record.destination in marketplaces:
                assert record.status != "same_provider", record.filed_host
