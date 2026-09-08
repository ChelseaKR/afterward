"""The clock on the gap between what has been published and what is served.

`live-integrity.yml` asks whether the site serves the dataset it *names*; a site six weeks
behind answers that correctly every day. `deploy-staleness.yml` asks how far behind `main`
the deployed commit is; a data refresh moves no commit. `release-integrity.yml` asks whether
every release is intact; it checks artifacts, not currency. So a `make dataset-publish` that
is never followed by a Deploy produces no event anywhere, and the reader gets withdrawn
programs and revised outcome figures under an honestly-reported, simply old snapshot date.

These tests are written from both directions, because the risk here is not that the detector
misses a gap -- it is that it reports a comfortable word over something it never measured.
So alongside the drift it must report, every arrangement that means nothing has to end in a
refusal: an empty release list, a listing that failed, a site that cannot be read, and a live
snapshot *newer* than anything published, which is not "current" and is not "ahead".

Everything here runs offline. The two network-shaped calls are substituted, because what
needs testing is not that `gh` works but what this file concludes from what it is handed.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"


def _script(name: str) -> Any:
    """Load a gate script by path, the way the sibling gate tests do.

    `scripts/` is not a package. It is put on `sys.path` first because
    `dataset_currency.py` imports `release_integrity` and `verify_live_site` as siblings --
    which is what it means for it to be a join of them rather than a second copy.
    """
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Registered before execution: `@dataclass` resolves annotations through
    # `sys.modules[cls.__module__]`, so a module that is not there yet raises on the
    # decorator rather than on anything to do with this repository.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


currency = _script("dataset_currency")

NOW = dt.datetime(2026, 9, 8, 12, 0, tzinfo=dt.UTC)


def _release(snapshot: str, *, published: str | None = None, **over: Any) -> dict[str, Any]:
    """One release as the API reports it, defaulting to published on its snapshot date."""
    entry: dict[str, Any] = {
        "tag_name": f"dataset-{snapshot}",
        "draft": False,
        "prerelease": False,
        "published_at": published or f"{snapshot}T18:00:00Z",
        "created_at": published or f"{snapshot}T18:00:00Z",
        "html_url": f"https://example.test/releases/dataset-{snapshot}",
        "assets": [f"afterward-dataset-{snapshot}.tar.gz"],
    }
    entry.update(over)
    return entry


def _compare(live: str, entries: list[dict[str, Any]], *, max_age_days: int = 7) -> Any:
    return currency.compare(
        dt.date.fromisoformat(live),
        currency.published_releases(entries),
        now=NOW,
        max_age_days=max_age_days,
    )


class TestTheGapItExistsToFind:
    """The failure mode in the issue: published on the workstation, never deployed."""

    def test_a_published_release_the_site_never_got_is_reported(self) -> None:
        state = _compare("2026-08-04", [_release("2026-08-17"), _release("2026-08-04")])
        assert state.verdict == "behind"
        assert [r.tag for r in state.waiting] == ["dataset-2026-08-17"]
        assert state.data_age_days == 13

    def test_the_operator_clock_and_the_data_clock_are_different_numbers(self) -> None:
        """A release cut long after the snapshot it carries has two ages, not one.

        `data_age_days` is how much staler the reader's data is; it does not move when
        nobody is looking. `undeployed_for_days` is how long the operator has been sitting
        on it. Collapsing them into one figure would answer neither question.
        """
        state = _compare(
            "2026-08-04",
            [_release("2026-08-17", published="2026-09-06T09:00:00Z"), _release("2026-08-04")],
        )
        assert state.data_age_days == 13
        waited = state.undeployed_for_days
        assert waited is not None
        assert round(waited, 1) == 2.1

    def test_several_undeployed_releases_are_all_named_oldest_first(self) -> None:
        state = _compare(
            "2026-08-04",
            [_release("2026-08-17"), _release("2026-08-07"), _release("2026-08-04")],
        )
        assert [r.tag for r in state.waiting] == ["dataset-2026-08-17", "dataset-2026-08-07"]
        report = currency.render(state)
        assert "dataset-2026-08-07, dataset-2026-08-17" in report
        # The threshold reads the OLDEST wait, not the newest release's.
        waited = state.undeployed_for_days
        assert waited is not None
        assert waited > 30

    def test_the_threshold_holds_until_it_is_crossed(self) -> None:
        recent = (NOW - dt.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        entries = [_release("2026-09-07", published=recent), _release("2026-08-17")]
        assert _compare("2026-08-17", entries, max_age_days=7).verdict == "current"
        assert _compare("2026-08-17", entries, max_age_days=2).verdict == "behind"


class TestCurrent:
    def test_serving_the_newest_release_is_current_and_reports_no_number(self) -> None:
        state = _compare("2026-08-17", [_release("2026-08-17"), _release("2026-08-04")])
        assert state.verdict == "current"
        assert state.waiting == ()
        assert state.undeployed_for_days is None
        assert state.data_age_days == 0

    def test_nothing_waiting_renders_as_a_sentence_not_as_zero_days(self) -> None:
        """`None` and `0.0` are different facts and only one of them is true here."""
        report = currency.render(_compare("2026-08-17", [_release("2026-08-17")]))
        assert "serving the newest dataset" in report
        assert "0.0 days" not in report
        assert as_json_value(_compare("2026-08-17", [_release("2026-08-17")])) is None


def as_json_value(state: Any) -> Any:
    return currency.as_json(state)["undeployed_for_days"]


class TestRefusingRatherThanReportingNothing:
    """Every arrangement in which a verdict would be a word over an unmeasured thing."""

    def test_an_empty_release_list_is_a_refusal(self) -> None:
        with pytest.raises(currency.CurrencyUnknown) as caught:
            _compare("2026-08-17", [])
        assert "not 'up to date'" in str(caught.value)

    def test_a_list_holding_only_other_projects_tags_is_a_refusal(self) -> None:
        """`v0.1.0` is not a dataset release, and neither is anything else off-shape."""
        with pytest.raises(currency.CurrencyUnknown):
            _compare("2026-08-17", [_release("2026-08-17", tag_name="v0.1.0")])

    def test_a_list_holding_only_drafts_is_a_refusal(self) -> None:
        """A draft is reachable by an authorised `gh release download` and is not published.

        Counting one as published would let an unfinished release make the site look
        behind; excluding it and then reporting "current" over an otherwise-empty list
        would be worse. The empty set refuses.
        """
        with pytest.raises(currency.CurrencyUnknown):
            _compare("2026-08-17", [_release("2026-09-07", draft=True)])

    def test_a_prerelease_does_not_count_as_published(self) -> None:
        state = _compare(
            "2026-08-17", [_release("2026-09-07", prerelease=True), _release("2026-08-17")]
        )
        assert state.verdict == "current"

    def test_a_live_snapshot_newer_than_every_release_is_a_refusal(self) -> None:
        """The case the issue names: not current, not ahead, unmeasurable.

        A site serving a snapshot that was never released is a different and worse finding
        than being behind, and rounding it into "current" would hide it permanently.
        """
        with pytest.raises(currency.CurrencyUnknown) as caught:
            _compare("2026-09-07", [_release("2026-08-17")])
        assert "never released" in str(caught.value)

    def test_a_release_with_no_timestamp_is_dropped_rather_than_dated(self) -> None:
        """A fabricated day inside this arithmetic is the defect this file exists against."""
        entries = [
            _release("2026-09-07", published_at=None, created_at=None),
            _release("2026-08-17"),
        ]
        assert [r.tag for r in currency.published_releases(entries)] == ["dataset-2026-08-17"]

    def test_a_release_with_an_unparseable_timestamp_is_dropped(self) -> None:
        entries = [_release("2026-09-07", published_at="not a date", created_at="also not")]
        assert currency.published_releases(entries) == []

    def test_a_failed_listing_is_a_refusal_and_not_an_empty_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def explode(_repo: str) -> list[dict[str, object]]:
            raise RuntimeError("`gh api repos/x/releases` failed (1): HTTP 403")

        monkeypatch.setattr(currency.release_integrity, "list_releases", explode)
        with pytest.raises(currency.CurrencyUnknown) as caught:
            currency.fetch_releases("ChelseaKR/afterward")
        assert "403" in str(caught.value)

    def test_a_site_that_cannot_be_read_is_a_refusal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Every refusal `verify_live_site` already makes is a reason not to compare.

        It refuses a non-200, a body that is not JSON, the CI fixture, a malformed or
        future snapshot date and a program count below the floor. This re-raises rather
        than softening any of them.
        """

        def explode(_origin: Any, _nonce: str) -> tuple[str, int]:
            raise currency.verify_live_site.LiveSiteError(
                "the live site is serving the CI fixture dataset, not production data."
            )

        monkeypatch.setattr(currency.verify_live_site, "live_coverage", explode)
        monkeypatch.setattr(
            currency.verify_live_site, "prove_the_origin_discriminates", lambda *_: None
        )
        with pytest.raises(currency.CurrencyUnknown) as caught:
            currency.live_snapshot_date("https://afterward.chelseakr.com", timeout_seconds=5.0)
        assert "CI fixture" in str(caught.value)


class TestTheDeletedReleaseIsACaveatAndNotARefusal:
    """A missing tag is a different sentinel's finding, and must not suppress this one."""

    def test_a_live_snapshot_matching_no_release_still_reports_the_gap(self) -> None:
        state = _compare("2026-08-04", [_release("2026-08-17")])
        assert state.verdict == "behind"
        assert state.live_release_missing is True
        assert state.data_age_days == 13
        assert "live-integrity.yml" in currency.render(state)

    def test_a_live_snapshot_that_matches_is_not_flagged(self) -> None:
        state = _compare("2026-08-04", [_release("2026-08-17"), _release("2026-08-04")])
        assert state.live_release_missing is False
        assert "Caveat" not in currency.render(state)


class TestTheReportSaysWhatItMeasured:
    def test_every_figure_in_the_json_is_one_the_comparison_produced(self) -> None:
        state = _compare("2026-08-04", [_release("2026-08-17"), _release("2026-08-04")])
        payload = currency.as_json(state)
        assert payload["verdict"] == "behind"
        assert payload["live_snapshot"] == "2026-08-04"
        assert payload["newest_release_tag"] == "dataset-2026-08-17"
        assert payload["undeployed_releases"] == ["dataset-2026-08-17"]
        assert payload["data_age_days"] == 13
        assert payload["max_age_days"] == 7
        # Round-trips: the workflow puts this straight into a step output.
        assert json.loads(json.dumps(payload))["verdict"] == "behind"

    def test_the_step_output_names_the_reason_when_the_answer_is_unknown(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An `unknown` verdict must reach the workflow as `unknown`, carrying its cause.

        The workflow branches on this value; a blank or a missing one would make the
        "open an issue" step and the "close it" step both skip, and the run would look
        like a pass.
        """
        destination = tmp_path / "github-output"
        monkeypatch.setenv("GITHUB_OUTPUT", str(destination))
        currency._write_github_output(None, "no published dataset release was found.")
        written = destination.read_text(encoding="utf-8")
        assert "verdict=unknown" in written
        assert "no published dataset release was found." in written


class TestTheDefaultsAreTheOnesTheProjectUses:
    def test_the_tag_shape_is_the_release_checkers_own(self) -> None:
        """One definition of "one of ours", so the two sentinels cannot disagree."""
        assert currency.TAG_PATTERN is currency.release_integrity.TAG_PATTERN
        assert currency.TAG_PATTERN.match("dataset-2026-08-17")
        assert currency.TAG_PATTERN.match("dataset-2026-08-17-hotfix") is None

    def test_the_live_url_is_the_one_the_other_sentinel_reads(self) -> None:
        assert currency.verify_live_site.SITE_URL == "https://afterward.chelseakr.com"

    def test_the_release_listing_carries_the_fields_this_join_needs(self) -> None:
        """Pinned because the field list lives in a jq string in the other script.

        `release_integrity.py` reads none of these, so nothing there would fail if they
        were dropped -- and this file would then silently drop every release for want of a
        timestamp, and refuse. A refusal is the safe direction and still the wrong outcome.
        """
        source = (SCRIPTS / "release_integrity.py").read_text(encoding="utf-8")
        for field in ("published_at", "created_at", "html_url"):
            assert field in source, f"list_releases no longer requests {field}"

    def test_a_malformed_repo_argument_is_refused_before_any_call(self) -> None:
        assert currency.main(["--repo", "not-an-owner-name"]) == 1

    def test_a_zero_day_threshold_is_refused(self) -> None:
        assert currency.main(["--max-age-days", "0"]) == 1
