"""Tests for the two gates that stand between a rejected address and a reader.

Both exist because of the shape of #34 and #28: a repair can sit in the repository, correct
and tested, while the artifact in production was built by an older pipeline and nothing about
the file says so. A gate that reads the *code* cannot see that. These read the artifacts --
the dataset that gets packaged, and the pages that get uploaded -- and they are tested here
against datasets and pages built to be wrong, because a guard nobody has watched fail is a
guard nobody has tested.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from textwrap import dedent
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"


def _script(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


provider_link_check = _script("provider_link_check")
publish_preflight = _script("publish_preflight")

HIJACKED = "http://www.giligiacollege.com"


def _link(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "url": HIJACKED,
        "href": HIJACKED,
        "linked": True,
        "label": "program_page",
        "verdict": "alive",
        "reason": "redirected_offsite",
        "checked_on": "2026-08-04",
        "notice": None,
        "substitution": None,
        "redirect": "same_provider",
    }
    return {**base, **over}


def _dataset(tmp_path: Path, *links: dict[str, Any] | None) -> Path:
    programs = [
        {"provider_name": f"Provider {i}", "provider_link": link} for i, link in enumerate(links)
    ]
    (tmp_path / "programs.json").write_text(
        json.dumps({"snapshot_date": "2026-08-07", "programs": programs}), encoding="utf-8"
    )
    return tmp_path


class TestTheDatasetGate:
    def test_a_dataset_built_before_the_review_is_refused(self, tmp_path: Path) -> None:
        """The exact shape production was serving on 2026-08-15: an off-site redirect,
        linked, with nothing recorded about who is at the other end. Indistinguishable from a
        reviewed one without this field, which is why the field exists."""
        found = provider_link_check.problems(_dataset(tmp_path, _link(redirect=None)))
        assert found
        assert "built before the review" in found[0]

    def test_an_unresolved_redirect_may_not_be_linked(self, tmp_path: Path) -> None:
        assert provider_link_check.problems(_dataset(tmp_path, _link(redirect="unresolved")))

    def test_a_rejected_destination_may_not_be_linked_under_any_reason(
        self, tmp_path: Path
    ) -> None:
        """Belt and braces: even if the shape check were weakened, a link to a reviewed
        address is refused on the strength of the ledger alone."""
        found = provider_link_check.problems(_dataset(tmp_path, _link(reason="ok", redirect=None)))
        assert any("giligiacollege.com" in line for line in found)

    def test_a_confirmed_rebrand_passes(self, tmp_path: Path) -> None:
        good = _link(url="https://moler.org/x", href="https://moler.org/x")
        assert provider_link_check.problems(_dataset(tmp_path, good)) == []

    def test_a_suppressed_link_passes(self, tmp_path: Path) -> None:
        """Not linking it is the fix, so the fixed shape must not trip the gate that asked
        for it."""
        suppressed = _link(href=None, linked=False, redirect="unrelated")
        assert provider_link_check.problems(_dataset(tmp_path, suppressed)) == []

    def test_a_program_with_no_link_block_is_not_a_finding(self, tmp_path: Path) -> None:
        assert provider_link_check.problems(_dataset(tmp_path, None)) == []

    def test_a_missing_dataset_fails_rather_than_passing_quietly(self, tmp_path: Path) -> None:
        assert provider_link_check.main([str(tmp_path / "nowhere")]) == 1

    def test_the_gate_reports_success_only_after_reading_something(self, tmp_path: Path) -> None:
        clean = _link(url="https://a.edu/", href="https://a.edu/")
        assert provider_link_check.main([str(_dataset(tmp_path, clean))]) == 0

    def test_a_dataset_with_no_programs_is_refused_rather_than_cleared(
        self, tmp_path: Path
    ) -> None:
        """Both checks here are searches, and a search over nothing finds nothing. Until
        this refusal existed the gate printed "every published provider link is vouched for"
        over a file with no links in it -- the same sentence it prints for a real dataset,
        with only a count to tell them apart, and the count was not printed either."""
        assert provider_link_check.main([str(_dataset(tmp_path))]) == 1

    def test_the_success_line_says_how_many_records_it_read(self, tmp_path: Path) -> None:
        """So the difference between a pass and a pass over nothing is visible in the log
        rather than only in the exit code."""
        clean = _link(url="https://a.edu/", href="https://a.edu/")
        assert provider_link_check.read_programs(_dataset(tmp_path, clean, clean)) == [
            {"provider_name": "Provider 0", "provider_link": clean},
            {"provider_name": "Provider 1", "provider_link": clean},
        ]


class TestTheGuardInTheDeployWorkflow:
    """GUARD 1b, extracted from the YAML and actually run.

    It is the last thing standing between a rejected address and a reader on the publishing
    path, it is thirty lines of Python inside a workflow file, and until now nothing
    exercised it at all -- the only test touching `deploy.yml` asserts that a string appears
    in it. A guard nobody has watched fail is a guard nobody has tested, and this one had
    diverged from the script it is written to agree with: it took the host from
    `urlsplit(...).netloc`, which keeps userinfo and a port, where
    `afterward.sources.link_review.host_of` strips both. `http://giligiacollege.com:8080/`
    passed the workflow and failed the script.
    """

    GUARD = "Refuse to publish a link nobody vouched for"

    def _inline_guard(self) -> str:
        """The workflow step's heredoc, as a runnable program."""
        workflow = (REPO_ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
        step = workflow.index(self.GUARD)
        body = workflow[step : workflow.index("python3 - <<'PY'", step)]
        assert "GUARD 1b" in body
        start = workflow.index("python3 - <<'PY'", step) + len("python3 - <<'PY'\n")
        end = workflow.index("\n          PY\n", start)
        return dedent(workflow[start:end])

    def _run_guard(self, tmp_path: Path, *links: dict[str, Any] | None) -> int:
        """The guard, run where it runs: a checkout with a dataset extracted into it."""
        (tmp_path / "src" / "afterward" / "sources").mkdir(parents=True)
        shutil.copy(
            REPO_ROOT / "src" / "afterward" / "sources" / "provider-link-review.json",
            tmp_path / "src" / "afterward" / "sources" / "provider-link-review.json",
        )
        data = tmp_path / "web" / "public" / "data"
        data.mkdir(parents=True)
        _dataset(data, *links)
        guard = tmp_path / "guard.py"
        guard.write_text(self._inline_guard(), encoding="utf-8")
        return subprocess.run(  # noqa: S603 - a file this test just wrote
            [sys.executable, str(guard)], cwd=tmp_path, capture_output=True, text=True, check=False
        ).returncode

    def test_it_refuses_the_dataset_that_was_live(self, tmp_path: Path) -> None:
        assert self._run_guard(tmp_path, _link(redirect=None)) != 0

    def test_it_refuses_a_rejected_host_carrying_a_port(self, tmp_path: Path) -> None:
        """The divergence. `netloc` on this URL is `giligiacollege.com:8080`, which is in no
        review, so the workflow published it while `scripts/provider_link_check.py` refused
        the same record."""
        ported = _link(
            url="http://giligiacollege.com:8080/",
            href="http://giligiacollege.com:8080/",
            redirect="same_provider",
        )
        assert self._run_guard(tmp_path, ported) != 0
        assert provider_link_check.problems_in(
            [{"provider_name": "Giligia College", "provider_link": ported}]
        )

    def test_it_refuses_a_rejected_host_behind_userinfo(self, tmp_path: Path) -> None:
        credentialed = _link(
            url="http://someone@giligiacollege.com/",
            href="http://someone@giligiacollege.com/",
            redirect="same_provider",
        )
        assert self._run_guard(tmp_path, credentialed) != 0

    def test_it_accepts_a_confirmed_rebrand(self, tmp_path: Path) -> None:
        """The other direction, without which this is a gate that cannot pass."""
        clean = _link(url="https://a.edu/", href="https://a.edu/")
        assert self._run_guard(tmp_path, clean) == 0


class TestThePageGate:
    def _page(self, out: Path, lang: str, name: str, body: str) -> Path:
        page = out / lang / "programs" / name / "index.html"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(f"<!doctype html><html><body>{body}</body></html>", encoding="utf-8")
        return page

    def test_a_page_linking_a_hijacked_address_is_found(self, tmp_path: Path) -> None:
        self._page(tmp_path, "en", "p1", '<a href="http://www.giligiacollege.com">Website</a>')
        found = publish_preflight.rejected_links(tmp_path, publish_preflight.load_review())
        assert found and "giligiacollege.com" in found[0]

    def test_the_spanish_tree_is_read_too(self, tmp_path: Path) -> None:
        self._page(tmp_path, "es", "p1", '<a href="https://dronitek.com/x">Sitio</a>')
        assert publish_preflight.rejected_links(tmp_path, publish_preflight.load_review())

    def test_the_address_printed_as_text_is_not_a_link(self, tmp_path: Path) -> None:
        """What a fixed page looks like: the URL still shown, as text, with the sentence.
        A substring search alone would fail this page, and failing it would teach an operator
        to ignore the gate."""
        self._page(
            tmp_path,
            "en",
            "p1",
            "<p>http://www.giligiacollege.com</p><p>When we checked on 2026-08-04, "
            "this web address led to a different website, unrelated to this provider.</p>",
        )
        assert publish_preflight.rejected_links(tmp_path, publish_preflight.load_review()) == []

    def test_an_ordinary_page_is_not_a_finding(self, tmp_path: Path) -> None:
        self._page(tmp_path, "en", "p1", '<a href="https://moler.edu/">Website</a>')
        assert publish_preflight.rejected_links(tmp_path, publish_preflight.load_review()) == []
