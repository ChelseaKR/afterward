"""The gate that reads production, which is the only artifact none of the others can see.

Every dataset gate this project has runs on the way out: `make dataset-verify` before
packaging, three guards in `.github/workflows/deploy.yml` before uploading,
`scripts/publish_preflight.py` before a hand sync. Each one is a good check and none of them
runs unless somebody deploys.

So the interval between a repair landing in this repository and a person choosing to publish
is unwatched, and it is the interval the last two data faults lived in. The provider-link
review landed on 2026-08-15 and established that `giligiacollege.com` is no longer the
college's -- it answers 302 to `seinquote.com`, which serves an Indonesian slot-gambling
page. Every gate here has refused that dataset ever since. On 2026-08-17 the live site was
still serving it, on four program pages under that college's name, because the deploy path
had not been travelled and nothing else was looking.

These tests are offline: `fetch_json` is replaced, because what is being tested is the
judgement, not the network. The two directions matter equally. A site serving a dataset this
repository would still publish must pass, or the gate gets switched off. And a run that
could not measure anything must fail, or the gate becomes the thing it was written against.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _script(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


live_check = _script("live_check")

HIJACKED = "http://www.giligiacollege.com"


def _program(**over: Any) -> dict[str, Any]:
    """One record as the current pipeline emits it, with a link nothing objects to."""
    base: dict[str, Any] = {
        "uuid": "f69dffd6-31e5-11f1-ac14-00155dd2f085",
        "provider_name": "Giligia College",
        "description": "Website design and programming.",
        "length": {"weeks": 24.0, "hours": None, "competency_based": False},
        "provider_link": {
            "url": "https://example.edu/",
            "href": "https://example.edu/",
            "linked": True,
            "reason": "ok",
            "redirect": None,
        },
    }
    return {**base, **over}


def _serving(
    monkeypatch: pytest.MonkeyPatch,
    programs: list[dict[str, Any]],
    *,
    total: Any = None,
    coverage: Any = None,
) -> None:
    """Stand a site up that serves exactly these two documents."""
    site_coverage = (
        coverage
        if coverage is not None
        else {
            "snapshot_date": "2026-08-17",
            "total_programs": len(programs) if total is None else total,
        }
    )
    documents = {
        "coverage.json": site_coverage,
        "programs.json": {"snapshot_date": "2026-08-17", "programs": programs},
    }

    def fake_fetch(url: str) -> Any:
        return documents[url.rsplit("/", 1)[-1]]

    monkeypatch.setattr(live_check, "fetch_json", fake_fetch)


class TestASiteServingWhatThisRepositoryWouldPublish:
    def test_passes(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _serving(monkeypatch, [_program()])
        assert live_check.report("https://afterward.example") == 0
        assert "would accept it again today" in capsys.readouterr().out

    def test_a_trailing_slash_is_not_a_different_site(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serving(monkeypatch, [_program()])
        assert live_check.report("https://afterward.example/") == 0


class TestTheFaultThatWasActuallyLive:
    def test_a_published_hijacked_link_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """What production was serving: an off-site redirect, linked, with nothing recorded
        about who answers at the other end. Four program pages, one Van Nuys college's name
        above them, and an Indonesian gambling site at the end of the click."""
        hijacked = _program(
            provider_link={
                "url": HIJACKED,
                "href": HIJACKED,
                "linked": True,
                "reason": "redirected_offsite",
                "redirect": None,
            }
        )
        _serving(monkeypatch, [hijacked])
        assert live_check.report("https://afterward.example") == 1
        out = capsys.readouterr().out
        assert "giligiacollege.com" in out
        assert "would no longer publish" in out

    def test_a_dataset_older_than_the_code_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The other half of what production was serving: records built before
        `length.competency_based` existed, so a program with no fixed length by design is
        indistinguishable from one that reported nothing."""
        _serving(monkeypatch, [_program(length={"weeks": None, "hours": None})])
        assert live_check.report("https://afterward.example") == 1
        assert "competency_based" in capsys.readouterr().out


class TestARunThatMeasuredNothingIsNotAPass:
    """The failure this gate would otherwise become.

    It runs unattended against documents fetched over a network, and both checks it applies
    are searches. An edge serving an empty body, a redirect to something that is not the
    dataset, a bucket half way through a sync: each hands the searches an empty list, which
    they clear without objection. So the count is asked for first, and disagreement between
    the two documents the site publishes is a refusal rather than a detail.
    """

    def test_an_empty_programs_list_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _serving(monkeypatch, [], total=0)
        assert live_check.report("https://afterward.example") == 1
        assert "no programs in it" in capsys.readouterr().out

    def test_documents_that_disagree_are_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _serving(monkeypatch, [_program()], total=3266)
        assert live_check.report("https://afterward.example") == 1

    def test_a_coverage_document_of_the_wrong_shape_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serving(monkeypatch, [_program()], coverage=["not", "an", "object"])
        assert live_check.report("https://afterward.example") == 1

    def test_an_unreachable_site_is_refused_rather_than_skipped(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def unreachable(url: str) -> Any:
            raise ValueError(f"{url} answered HTTP 503")

        monkeypatch.setattr(live_check, "fetch_json", unreachable)
        assert live_check.report("https://afterward.example") == 1
        assert "established nothing" in capsys.readouterr().out


class TestTheGateReadsTheWorldAndNotThisDisk:
    def test_a_non_https_target_is_refused(self) -> None:
        """`scripts/deploy_check.py` pins the scheme for the same reason: a stray argument
        must not be able to turn a check on what the world can see into a read of a file
        here, which would then pass."""
        with pytest.raises(ValueError, match="non-https"):
            live_check.fetch_json("file:///etc/passwd")


class TestTheGateIsWiredIntoSomethingThatRunsWithoutBeingAsked:
    """A check nobody calls is documentation, and this one exists precisely because the
    checks that already existed are only called by a person deciding to publish."""

    def test_the_makefile_offers_it(self) -> None:
        makefile = (SCRIPTS.parent / "Makefile").read_text(encoding="utf-8")
        assert "scripts/live_check.py" in makefile

    def test_ci_runs_it_on_a_schedule_of_its_own(self) -> None:
        workflow = (SCRIPTS.parent / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        assert "make live-check" in workflow
        assert "23 14 * * 1" in workflow

    def test_it_is_not_part_of_verify(self) -> None:
        """Network-bound, like `link-check` and `deploy-check`. A gate that needs a third
        party to answer must not be able to fail a pull request that did not touch it."""
        makefile = (SCRIPTS.parent / "Makefile").read_text(encoding="utf-8")
        verify = next(line for line in makefile.splitlines() if line.startswith("verify:"))
        assert "live-check" not in verify


class TestTheJudgementIsTheSameJudgementTheDeployPathMakes:
    """Imported, not reimplemented. Two gates written to hold the same opinion drift, and
    the one that runs last is the one that matters."""

    def test_it_uses_the_packaging_gates_themselves(self) -> None:
        source = (SCRIPTS / "live_check.py").read_text(encoding="utf-8")
        assert "from dataset_shape_check import" in source
        assert "from provider_link_check import" in source


class TestMainDefaultsToTheSiteThisRepositoryPublishes:
    def test_no_argument_means_the_production_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        asked: list[str] = []

        def record(base: str) -> int:
            asked.append(base)
            return 0

        monkeypatch.setattr(live_check, "report", record)
        assert live_check.main([]) == 0
        assert asked == ["https://afterward.chelseakr.com"]


def test_the_review_it_enforces_is_the_committed_one() -> None:
    """Not a copy of the ledger, and not a list of hosts written here. If an entry is added
    or a status changed, this gate changes with it on the next run."""
    review = json.loads(
        (SCRIPTS.parent / "src" / "afterward" / "sources" / "provider-link-review.json").read_text(
            encoding="utf-8"
        )
    )
    assert any(entry["filed_host"] == "giligiacollege.com" for entry in review["entries"])
