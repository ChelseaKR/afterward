"""The release checker's own refusals, and the arithmetic it does before it refuses.

Everything here runs offline against directories and tarballs built in a temp dir. The one
network-shaped function -- listing releases -- is substituted, because what needs testing is
not that `gh` works but that this script cannot report a comfortable verdict over an empty set.

The important case in this file is :class:`TestRefusingRatherThanReportingNothing`. A checker
whose answer to "no releases found" is "0 problems" is the exact defect this repository grades
other people's datasets on, committed inside the thing that checks for it.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import tarfile
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"


def _script(name: str) -> Any:
    """Load a gate script by path, the way `tests/test_deploy_staleness.py` does.

    Not `from scripts import ...`. `scripts/` is not a package, so importing it that way makes
    mypy see the same file under two module names (`release_integrity` and
    `scripts.release_integrity`) and refuse to check anything at all -- which a warm local mypy
    cache hides and a clean CI run does not.
    """
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Registered before execution: `@dataclass` resolves annotations through
    # `sys.modules[cls.__module__]`.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ri = _script("release_integrity")

CLEAN_COVERAGE = {"snapshot_date": "2026-08-17", "total_programs": 3, "state": "CA"}


def _dataset(root: Path, coverage: dict[str, object], *, programs: int) -> Path:
    """A directory shaped like an unpacked release tarball."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "coverage.json").write_text(json.dumps(coverage), encoding="utf-8")
    (root / "programs").mkdir(exist_ok=True)
    for index in range(programs):
        (root / "programs" / f"{index}.json").write_text("{}", encoding="utf-8")
    return root


class TestTheDatasetInsideAgainstTheTagOutside:
    def test_a_release_that_is_what_it_says_raises_nothing(self, tmp_path: Path) -> None:
        root = _dataset(tmp_path / "d", CLEAN_COVERAGE, programs=3)
        problems, snapshot, total = ri.check_extracted_dataset(
            root, expected_snapshot="2026-08-17", min_programs=2
        )
        assert problems == []
        assert (snapshot, total) == ("2026-08-17", 3)

    def test_a_tag_naming_a_different_snapshot_than_the_dataset_inside_it(
        self, tmp_path: Path
    ) -> None:
        """The check nothing else in this repository makes.

        `deploy.yml` verifies the tarball's digest and refuses a fixture, and would deploy a
        three-week-old snapshot under today's tag without a murmur, because it never compares
        the two. `make dataset-publish` derives both from the same file so they agree by
        construction -- which is why a disagreement means something went wrong outside it.
        """
        root = _dataset(tmp_path / "d", CLEAN_COVERAGE, programs=3)
        problems, _, _ = ri.check_extracted_dataset(
            root, expected_snapshot="2026-09-07", min_programs=2
        )
        assert len(problems) == 1
        assert "2026-09-07" in problems[0] and "2026-08-17" in problems[0]

    def test_the_fixture_published_as_a_release(self, tmp_path: Path) -> None:
        root = _dataset(tmp_path / "d", {**CLEAN_COVERAGE, "is_fixture": True}, programs=3)
        problems, _, _ = ri.check_extracted_dataset(
            root, expected_snapshot="2026-08-17", min_programs=2
        )
        assert any("is_fixture" in problem for problem in problems)

    def test_a_program_count_below_the_floor(self, tmp_path: Path) -> None:
        root = _dataset(tmp_path / "d", CLEAN_COVERAGE, programs=3)
        problems, _, _ = ri.check_extracted_dataset(
            root, expected_snapshot="2026-08-17", min_programs=2000
        )
        assert any("below the 2000 floor" in problem for problem in problems)

    def test_a_manifest_that_disagrees_with_what_is_in_the_tarball(self, tmp_path: Path) -> None:
        # A truncated upload looks exactly like this and nothing else would notice.
        root = _dataset(tmp_path / "d", CLEAN_COVERAGE, programs=2)
        problems, _, _ = ri.check_extracted_dataset(
            root, expected_snapshot="2026-08-17", min_programs=2
        )
        assert any("claims 3" in problem for problem in problems)

    @pytest.mark.parametrize(
        ("coverage", "expected"),
        [
            ({"total_programs": 3}, "no snapshot_date"),
            ({"snapshot_date": "2026-08-17"}, "no integer total_programs"),
            ({"snapshot_date": "2026-08-17", "total_programs": "3"}, "no integer"),
        ],
    )
    def test_a_coverage_file_that_states_nothing_usable(
        self, tmp_path: Path, coverage: dict[str, object], expected: str
    ) -> None:
        root = _dataset(tmp_path / "d", coverage, programs=3)
        problems, _, _ = ri.check_extracted_dataset(
            root, expected_snapshot="2026-08-17", min_programs=2
        )
        assert any(expected in problem for problem in problems)

    def test_no_coverage_file_at_all(self, tmp_path: Path) -> None:
        (tmp_path / "d").mkdir()
        problems, snapshot, total = ri.check_extracted_dataset(
            tmp_path / "d", expected_snapshot="2026-08-17", min_programs=2
        )
        assert problems == ["no coverage.json in the tarball"]
        assert snapshot is None and total is None


class TestTheSidecarDigest:
    def test_reads_both_formats_the_makefile_can_produce(self) -> None:
        digest = hashlib.sha256(b"x").hexdigest()
        # `sha256sum` writes two spaces; BSD `shasum -a 256` writes the same shape.
        assert ri.digest_from_sidecar(f"{digest}  file.tar.gz\n") == digest
        assert ri.digest_from_sidecar(f"{digest} *file.tar.gz\n") == digest
        assert ri.digest_from_sidecar(f"{digest.upper()}  file.tar.gz\n") == digest

    def test_returns_none_rather_than_a_partial_read(self) -> None:
        # A sidecar this cannot read must not produce a digest that happens to compare equal
        # to nothing; the caller records "unreadable" and the release fails.
        for text in ["", "not a digest at all\n", "deadbeef  file.tar.gz\n"]:
            assert ri.digest_from_sidecar(text) is None


class TestArchiveMembersThatWouldEscape:
    """`deploy.yml` extracts one of these into the runner workspace."""

    def _archive(self, path: Path, names: list[str]) -> tarfile.TarFile:
        with tarfile.open(path, "w:gz") as writing:
            for name in names:
                info = tarfile.TarInfo(name)
                info.size = 1
                writing.addfile(info, io.BytesIO(b"x"))
        return tarfile.open(path, "r:gz")

    def test_an_ordinary_dataset_tarball_is_clean(self, tmp_path: Path) -> None:
        with self._archive(tmp_path / "a.tar.gz", ["./coverage.json", "./programs/1.json"]) as a:
            assert ri.unsafe_members(a) == []

    @pytest.mark.parametrize("name", ["/etc/passwd", "../outside.json", "a/../../outside.json"])
    def test_a_path_that_leaves_the_extraction_directory(self, tmp_path: Path, name: str) -> None:
        with self._archive(tmp_path / "a.tar.gz", [name]) as archive:
            assert ri.unsafe_members(archive) == [name]

    def test_a_symlink_pointing_out_of_the_tree(self, tmp_path: Path) -> None:
        path = tmp_path / "a.tar.gz"
        with tarfile.open(path, "w:gz") as writing:
            info = tarfile.TarInfo("link")
            info.type = tarfile.SYMTYPE
            info.linkname = "../../etc/passwd"
            writing.addfile(info)
        with tarfile.open(path, "r:gz") as archive:
            assert ri.unsafe_members(archive) == ["link -> ../../etc/passwd"]


class TestWhatTheApiSaysBeforeAnythingIsDownloaded:
    def test_a_well_formed_release_yields_its_snapshot_and_asset_pair(self) -> None:
        shape = ri.check_release_shape(
            {
                "tag_name": "dataset-2026-08-17",
                "draft": False,
                "prerelease": False,
                "assets": ["x.tar.gz", "x.tar.gz.sha256"],
            }
        )
        assert shape.problems == []
        assert shape.snapshot == "2026-08-17"
        assert shape.asset_names == ("x.tar.gz", "x.tar.gz.sha256")

    def test_the_pre_rename_asset_name_is_still_a_valid_release(self) -> None:
        # dataset-2026-08-04 really does carry `camino-dataset-...`, from before the rename.
        # Matching on the suffix rather than on a name keeps that release checkable.
        shape = ri.check_release_shape(
            {
                "tag_name": "dataset-2026-08-04",
                "assets": [
                    "camino-dataset-2026-08-04.tar.gz",
                    "camino-dataset-2026-08-04.tar.gz.sha256",
                ],
            }
        )
        assert shape.problems == []
        assert shape.asset_names is not None

    def test_a_tag_that_is_not_a_dataset_release(self) -> None:
        shape = ri.check_release_shape({"tag_name": "v0.1.0", "assets": []})
        assert shape.snapshot is None
        assert shape.asset_names is None
        assert "dataset-YYYY-MM-DD" in shape.problems[0]

    @pytest.mark.parametrize("flag", ["draft", "prerelease"])
    def test_a_draft_or_prerelease_sitting_where_a_dispatch_can_reach_it(self, flag: str) -> None:
        shape = ri.check_release_shape(
            {
                "tag_name": "dataset-2026-08-17",
                flag: True,
                "assets": ["x.tar.gz", "x.tar.gz.sha256"],
            }
        )
        assert any(flag[:5] in problem for problem in shape.problems)

    @pytest.mark.parametrize(
        "assets",
        [
            [],
            ["x.tar.gz"],
            ["x.tar.gz.sha256"],
            ["x.tar.gz", "y.tar.gz", "x.tar.gz.sha256"],
        ],
    )
    def test_assets_that_are_not_exactly_one_pair_stop_before_downloading(
        self, assets: list[str]
    ) -> None:
        shape = ri.check_release_shape({"tag_name": "dataset-2026-08-17", "assets": assets})
        assert shape.problems
        assert shape.asset_names is None


class TestRefusingRatherThanReportingNothing:
    """The guard this whole script exists to not violate.

    Every one of these paths could return "0 problems" and be technically accurate. Each of
    them means nothing was measured, and this project's whole argument is that those are
    different facts.
    """

    def test_no_releases_at_all_is_a_refusal_not_a_clean_bill(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(ri, "list_releases", lambda repo: [])
        code, result = ri.run(repo="o/r", tag=None, min_programs=2, work_dir=tmp_path)
        assert code == 2
        assert result["verdict"] == "cannot-check"

    def test_releases_that_are_none_of_them_dataset_releases_is_a_refusal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A repo holding only `v0.1.0` has published no dataset, which is this project's
        # delivery. Counting zero dataset releases as zero problems would say the opposite.
        monkeypatch.setattr(ri, "list_releases", lambda repo: [{"tag_name": "v0.1.0"}])
        code, result = ri.run(repo="o/r", tag=None, min_programs=2, work_dir=tmp_path)
        assert code == 2
        assert result["verdict"] == "cannot-check"

    def test_a_listing_that_failed_is_a_refusal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def explode(repo: str) -> list[dict[str, object]]:
            raise RuntimeError("gh: 503")

        monkeypatch.setattr(ri, "list_releases", explode)
        code, result = ri.run(repo="o/r", tag=None, min_programs=2, work_dir=tmp_path)
        assert code == 2
        assert "503" in str(result["reason"])

    def test_a_named_tag_that_does_not_exist_is_a_refusal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(ri, "list_releases", lambda repo: [{"tag_name": "dataset-2026-08-17"}])
        code, result = ri.run(
            repo="o/r", tag="dataset-2026-01-01", min_programs=2, work_dir=tmp_path
        )
        assert code == 2
        assert result["verdict"] == "cannot-check"

    def test_a_release_with_a_problem_exits_one_not_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Exit 1 for "checked, and something is wrong"; exit 2 for "could not check". A caller
        # that cannot tell those apart cannot act on either.
        monkeypatch.setattr(
            ri,
            "list_releases",
            lambda repo: [{"tag_name": "dataset-2026-08-17", "draft": True, "assets": []}],
        )
        code, result = ri.run(repo="o/r", tag=None, min_programs=2, work_dir=tmp_path)
        assert code == 1
        assert result["verdict"] == "problems"
        assert result["checked"] == 1
