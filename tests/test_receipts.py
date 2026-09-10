"""The per-program receipt, and the verb that replays it.

Two rules carry this feature and both are pinned below rather than described.

**A measure that is not reported carries no number.** A receipt is read by machines that
never saw the page's caveats, so a suppressed cell leaking in as a zero would be worse here
than anywhere else on the site. `TestASuppressedMeasureCarriesNoNumber` asserts the absence
structurally *and* over the receipt's own bytes, because "the key is missing" and "no digit
for that measure reached the file" are different claims and only the second is what a naive
reader is exposed to.

**Nothing was compared is not a pass.** `verify-record` has three exit codes and the third
covers four states -- no such record, no receipt beside it, a dataset that cannot say which
snapshot it is, a schema this build does not know. Every one of them prints a reason and
none of them prints "verified". `TestTheThirdExitCodeIsNotAPass` holds that.

The verdicts here are proved against a **whole build** rather than against a hand-made
record: `built` runs `build_offline` over the committed fixture, which is the same
`emit_site_bundle` a real build calls. A receipt schema is exactly the kind of thing that
passes every unit test over a two-field dict and disagrees with the pipeline.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from afterward import receipts, tabular
from afterward.build import build_offline, emit_site_bundle
from afterward.cli import app
from afterward.sources import link_check

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "fixtures" / "data"

runner = CliRunner()


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A whole dataset, emitted by the build path CI runs."""
    output = tmp_path_factory.mktemp("dataset")
    build_offline(FIXTURE_DIR, output_dir=output)
    return output


@pytest.fixture(scope="module")
def uuids(built: Path) -> list[str]:
    return sorted(path.stem for path in (built / "programs").glob("*.json"))


def _receipt(built: Path, uuid: str) -> dict[str, Any]:
    document: dict[str, Any] = json.loads(
        (built / receipts.RECEIPT_DIRNAME / f"{uuid}.json").read_text(encoding="utf-8")
    )
    return document


def _record(built: Path, uuid: str) -> dict[str, Any]:
    document: dict[str, Any] = json.loads(
        (built / "programs" / f"{uuid}.json").read_text(encoding="utf-8")
    )
    return document


def _copy(built: Path, into: Path) -> Path:
    destination = into / "dataset"
    shutil.copytree(built, destination)
    return destination


def _rewrite_record(dataset: Path, uuid: str, record: dict[str, Any]) -> None:
    """Write a record back exactly as the build writes one, so only the edit differs."""
    (dataset / "programs" / f"{uuid}.json").write_bytes(
        json.dumps(record, separators=(",", ":")).encode("utf-8")
    )


class TestTheFloor:
    """Assertions that fail if the fixtures below stopped describing anything.

    Every other test here says "the receipt agrees with the record", which is also what a
    receipt of two constant fields would say. These are what make the rest non-vacuous.
    """

    def test_the_build_emits_one_receipt_per_program(self, built: Path, uuids: list[str]) -> None:
        emitted = sorted(path.stem for path in (built / receipts.RECEIPT_DIRNAME).glob("*.json"))
        assert emitted == uuids
        assert len(emitted) == 60

    def test_a_receipt_states_every_measure_the_flat_table_states(
        self, built: Path, uuids: list[str]
    ) -> None:
        """Derived from ``tabular.COLUMNS``, not listed, so a measure cannot exist in one and
        not the other. This is the whole reason the receipt does not own a measure list."""
        expected = {column.name for column in tabular.COLUMNS if column.measured}
        assert expected  # a receipt over no measures would satisfy everything below
        assert set(_receipt(built, uuids[0])["measures"]) == expected
        assert len(expected) == 15

    def test_the_fixture_carries_all_three_state_words(self, built: Path, uuids: list[str]) -> None:
        """Otherwise the state assertions below are about one branch of a three-way rule."""
        seen = {
            entry["state"] for uuid in uuids for entry in _receipt(built, uuid)["measures"].values()
        }
        assert seen == set(tabular.STATES)


class TestTheReceiptDescribesTheRecordBesideIt:
    def test_the_digest_is_of_the_record_file_a_reader_can_hash(
        self, built: Path, uuids: list[str]
    ) -> None:
        """Not of a re-serialisation. A reader runs `shasum -a 256 programs/<uuid>.json` and
        gets this string, with no canonicalisation rule to reimplement."""
        for uuid in uuids:
            record_bytes = (built / "programs" / f"{uuid}.json").read_bytes()
            expected = f"sha256:{hashlib.sha256(record_bytes).hexdigest()}"
            assert _receipt(built, uuid)["record_sha256"] == expected

    def test_every_measure_state_agrees_with_the_record_a_page_renders_from(
        self, built: Path, uuids: list[str]
    ) -> None:
        """The receipt's state word and the page's rendering key on the same thing.

        `Measure.tsx` renders "Not reported" for exactly `value === null`, and the receipt
        says `reported` for exactly a non-null value -- except on the two length columns,
        where a competency-based programme's absent length is a design decision rather than a
        gap and both the CSV and the page say so with their own word. Holding the receipt to
        the record is what holds it to the page, because the record is what the page reads.
        """
        for uuid in uuids:
            record = _record(built, uuid)
            for column in receipts.MEASURE_COLUMNS:
                entry = _receipt(built, uuid)["measures"][column.name]
                value = tabular.value_of(record, column)
                if entry["state"] == tabular.REPORTED:
                    assert value is not None
                    assert entry["value"] == value
                else:
                    assert "value" not in entry
                    if entry["state"] == tabular.NOT_REPORTED:
                        assert value is None

    def test_the_occupation_join_is_reported_as_the_record_made_it(
        self, built: Path, uuids: list[str]
    ) -> None:
        matched = 0
        for uuid in uuids:
            record = _record(built, uuid)
            receipt = _receipt(built, uuid)
            assert receipt["program_soc_codes"] == record["soc_codes"]
            assert len(receipt["occupations"]) == len(record["occupations"])
            for stated, joined in zip(receipt["occupations"], record["occupations"], strict=True):
                matched += 1
                assert stated["soc_code"] == joined["soc_code"]
                assert stated["match_kind"] == joined["match"]["kind"]
                assert (
                    stated["entry_level_education_withheld"]
                    == joined["match"]["entry_level_education_withheld"]
                )
        assert matched > 0, "no occupation was joined, so the loop above claimed nothing"

    def test_a_program_that_filed_no_address_is_not_a_link_nobody_checked(self) -> None:
        """Two absences that would otherwise be the same null. `None` means the provider gave
        no website; a block whose verdict is null means nobody read the one they gave."""
        assert receipts._provider_link_entry({"provider_link": None}) is None
        unchecked = receipts._provider_link_entry(
            {"provider_link": {"url": "https://x.example", "verdict": None}}
        )
        assert unchecked == {
            "verdict": None,
            "reason": None,
            "checked_on": None,
            "classifier_version": None,
        }

    def test_a_link_verdict_carries_the_classifier_that_reached_it(self) -> None:
        """Deliberately not the current version: a receipt that hard-coded
        ``CLASSIFIER_VERSION`` would satisfy an assertion written against it, and a stale
        verdict published as current is the whole reason the field exists."""
        older = link_check.CLASSIFIER_VERSION - 1
        entry = receipts._provider_link_entry(
            {"provider_link": {"verdict": "alive", "reason": "ok", "classifier_version": older}}
        )
        assert entry is not None
        assert entry["classifier_version"] == older

    def test_a_record_built_before_the_field_existed_names_no_classifier(self) -> None:
        """The three published dataset releases carry link blocks with no such key. Reading
        that as version zero, or as the current version, would both be inventions."""
        entry = receipts._provider_link_entry(
            {"provider_link": {"verdict": "alive", "reason": "ok"}}
        )
        assert entry is not None
        assert entry["classifier_version"] is None


class TestASuppressedMeasureCarriesNoNumber:
    def test_a_not_reported_entry_is_exactly_one_key(self, built: Path, uuids: list[str]) -> None:
        withheld = 0
        for uuid in uuids:
            for entry in _receipt(built, uuid)["measures"].values():
                if entry["state"] != tabular.REPORTED:
                    withheld += 1
                    assert entry == {"state": entry["state"]}
        assert withheld > 0, "no measure in this build is withheld, so nothing was asserted"

    def test_no_digit_reaches_the_bytes_of_a_withheld_measure(
        self, built: Path, uuids: list[str]
    ) -> None:
        """The structural assertion above is about a dict. This is about the file, which is
        what a consumer that was not paying attention actually parses."""
        checked = 0
        for uuid in uuids:
            raw = (built / receipts.RECEIPT_DIRNAME / f"{uuid}.json").read_text(encoding="utf-8")
            for column in receipts.MEASURE_COLUMNS:
                entry = _receipt(built, uuid)["measures"][column.name]
                if entry["state"] == tabular.REPORTED:
                    continue
                checked += 1
                rendered = re.search(rf'"{column.name}":(\{{[^}}]*\}})', raw)
                assert rendered is not None, f"{column.name} is not in the receipt at all"
                assert not re.search(r"\d", rendered.group(1)), rendered.group(1)
        assert checked > 0

    def test_a_measure_the_source_filed_as_minus_one_is_never_a_number_here(self) -> None:
        """`-1` is the ETP scorecard's sentinel and `dol_etp.clean_measure` maps it to None
        before a record is built. This is the end of that chain: whatever the cause, the
        receipt states an absence and states no figure."""
        record = {
            "uuid": "u",
            "outcomes": {"median_earnings": None},
            "cost": {},
            "length": {},
            "soc_codes": [],
            "occupations": [],
        }
        column = next(c for c in receipts.MEASURE_COLUMNS if c.name == "median_earnings")
        assert receipts.measure_entry(record, column) == {"state": "not_reported"}


class TestTheReleaseTag:
    def test_a_real_build_names_the_tag_the_publisher_would_create(self) -> None:
        assert receipts.release_tag_for("2026-08-17", is_fixture=False) == "dataset-2026-08-17"

    def test_a_fixture_build_names_no_release(self, built: Path, uuids: list[str]) -> None:
        """The load-bearing half. The 60-program fixture carries a real snapshot date, so the
        naive derivation would point every fixture receipt at a genuine published release
        holding 3,266 different programs."""
        receipt = _receipt(built, uuids[0])
        assert receipt["is_fixture"] is True
        assert receipt["release_tag"] is None
        assert receipt["snapshot_date"] == "2026-08-07"
        assert receipts.release_tag_for("2026-08-07", is_fixture=True) is None

    def test_the_emitter_takes_the_answer_rather_than_guessing_it(
        self, tmp_path: Path, uuids: list[str], built: Path
    ) -> None:
        """`emit_site_bundle` has no default for `is_fixture`: rebuilding a site bundle from
        an unpacked release is the same code path as building from the fixture, and only the
        caller knows which it is."""
        payloads = [_record(built, uuid) for uuid in uuids]
        output = tmp_path / "real"
        output.mkdir()
        emit_site_bundle(
            payloads, {}, output_dir=output, snapshot="2026-08-17", state="CA", is_fixture=False
        )
        receipt = json.loads(
            (output / receipts.RECEIPT_DIRNAME / f"{uuids[0]}.json").read_text(encoding="utf-8")
        )
        assert receipt["release_tag"] == "dataset-2026-08-17"
        assert receipt["is_fixture"] is False


class TestVerifyRecordAgrees:
    def test_a_build_agrees_with_every_one_of_its_own_receipts(
        self, built: Path, uuids: list[str]
    ) -> None:
        """The consumer that keeps this from being a declared-but-unread field. Run over the
        whole build, not one record: a verifier that agrees with a single hand-made receipt
        and disagrees with the pipeline is exactly the failure this shape invites."""
        for uuid in uuids:
            result = receipts.verify_record(built, uuid)
            assert result.status == "agrees", (uuid, [str(f) for f in result.fields])
            assert result.fields_compared >= receipts.MINIMUM_FIELDS

    def test_the_verb_exits_zero_and_prints_what_it_compared(
        self, built: Path, uuids: list[str]
    ) -> None:
        result = runner.invoke(app, ["verify-record", uuids[0], "--dataset", str(built)])
        assert result.exit_code == 0, result.output
        assert "The receipt and this dataset agree." in result.output
        # The denominator, so an agreement over nothing cannot read like an agreement over
        # everything.
        assert re.search(r"fields\s+(\d+) of \1 agree", result.output), result.output

    def test_a_release_tarball_is_read_the_same_way_as_a_directory(
        self, built: Path, uuids: list[str], tmp_path: Path
    ) -> None:
        """`verify-record --dataset afterward-dataset-<date>.tar.gz` is the form a reader who
        downloaded a release actually has."""
        tarball = tmp_path / "afterward-dataset-2026-08-07.tar.gz"
        with tarfile.open(tarball, "w:gz") as archive:
            archive.add(built, arcname=".")
        result = runner.invoke(app, ["verify-record", uuids[0], "--dataset", str(tarball)])
        assert result.exit_code == 0, result.output


class TestVerifyRecordDisagrees:
    def test_changing_one_measure_names_exactly_that_field(
        self, built: Path, uuids: list[str], tmp_path: Path
    ) -> None:
        uuid = next(u for u in uuids if _record(built, u)["outcomes"]["total_served"] is not None)
        dataset = _copy(built, tmp_path)
        record = _record(built, uuid)
        record["outcomes"]["total_served"] = 99999.0
        _rewrite_record(dataset, uuid, record)

        result = receipts.verify_record(dataset, uuid)
        assert result.status == "disagrees"
        assert [f.path for f in result.fields] == ["measures.total_served.value"]
        assert not result.digest_agrees

    def test_a_withheld_measure_that_gains_a_zero_is_named_in_both_directions(
        self, built: Path, uuids: list[str], tmp_path: Path
    ) -> None:
        """The failure this whole project is written against, arriving after the receipt was
        written. The state flips and a number appears where the receipt has none, and both
        are reported -- a report of only the value would read as a correction."""
        uuid = next(u for u in uuids if _record(built, u)["outcomes"]["median_earnings"] is None)
        dataset = _copy(built, tmp_path)
        record = _record(built, uuid)
        record["outcomes"]["median_earnings"] = 0.0
        _rewrite_record(dataset, uuid, record)

        result = receipts.verify_record(dataset, uuid)
        assert result.status == "disagrees"
        assert [f.path for f in result.fields] == [
            "measures.median_earnings.state",
            "measures.median_earnings.value",
        ]

    def test_a_field_no_receipt_describes_still_fails_the_digest(
        self, built: Path, uuids: list[str], tmp_path: Path
    ) -> None:
        """The receipt states fifteen measures and a join. The digest is over the whole
        record, so editing a provider's name -- which no field above mentions -- is caught,
        and caught as what it is: this is not the record the receipt was written for."""
        uuid = uuids[0]
        dataset = _copy(built, tmp_path)
        record = _record(built, uuid)
        record["provider_name"] = "Somebody Else"
        _rewrite_record(dataset, uuid, record)

        result = receipts.verify_record(dataset, uuid)
        assert result.status == "disagrees"
        assert result.fields == ()
        assert not result.digest_agrees

    def test_the_verb_exits_one_and_never_says_the_two_agree(
        self, built: Path, uuids: list[str], tmp_path: Path
    ) -> None:
        uuid = uuids[0]
        dataset = _copy(built, tmp_path)
        record = _record(built, uuid)
        record["provider_name"] = "Somebody Else"
        _rewrite_record(dataset, uuid, record)
        result = runner.invoke(app, ["verify-record", uuid, "--dataset", str(dataset)])
        assert result.exit_code == 1
        assert "DISAGREE" in result.output
        assert "agree." not in result.output

    def test_a_receipt_from_another_record_is_refused_rather_than_matched(
        self, built: Path, uuids: list[str], tmp_path: Path
    ) -> None:
        """The reader's own case: a page served me this receipt, is it about the record in
        the release? A verifier that only ever reads the receipt beside the record could
        never be asked."""
        other = built / receipts.RECEIPT_DIRNAME / f"{uuids[1]}.json"
        result = receipts.verify_record(built, uuids[0], receipt_path=other)
        assert result.status == "disagrees"
        assert "uuid" in [f.path for f in result.fields]


class TestTheThirdExitCodeIsNotAPass:
    def test_a_record_the_dataset_does_not_hold(self, built: Path) -> None:
        absent = "00000000-0000-0000-0000-000000000000"
        result = receipts.verify_record(built, absent)
        assert result.status == "cannot_check"
        assert result.exit_code == 2
        assert result.reason is not None and absent in result.reason

    def test_the_verb_exits_two_and_prints_no_verdict(self, built: Path) -> None:
        result = runner.invoke(
            app, ["verify-record", "00000000-0000-0000-0000-000000000000", "--dataset", str(built)]
        )
        assert result.exit_code == 2
        assert "cannot check" in result.output
        assert "verified" not in result.output.lower()
        assert "agree" not in result.output

    def test_a_dataset_built_before_receipts_existed(
        self, built: Path, uuids: list[str], tmp_path: Path
    ) -> None:
        dataset = _copy(built, tmp_path)
        shutil.rmtree(dataset / receipts.RECEIPT_DIRNAME)
        result = receipts.verify_record(dataset, uuids[0])
        assert result.status == "cannot_check"
        assert result.reason is not None and "no receipt" in result.reason

    def test_a_schema_version_this_build_does_not_know(
        self, built: Path, uuids: list[str], tmp_path: Path
    ) -> None:
        dataset = _copy(built, tmp_path)
        path = dataset / receipts.RECEIPT_DIRNAME / f"{uuids[0]}.json"
        receipt = json.loads(path.read_text(encoding="utf-8"))
        receipt["schema"] = "afterward.receipt/99"
        path.write_text(json.dumps(receipt, separators=(",", ":")), encoding="utf-8")
        result = receipts.verify_record(dataset, uuids[0])
        assert result.status == "cannot_check"
        assert result.reason is not None and "afterward.receipt/99" in result.reason

    def test_a_dataset_that_cannot_say_which_snapshot_it_is(
        self, built: Path, uuids: list[str], tmp_path: Path
    ) -> None:
        """Recomputation needs the snapshot date and the state, and both come from the
        dataset rather than from the receipt -- a receipt may not vouch for the facts it is
        being checked against."""
        dataset = _copy(built, tmp_path)
        document = json.loads((dataset / "programs.json").read_text(encoding="utf-8"))
        del document["snapshot_date"]
        (dataset / "programs.json").write_text(json.dumps(document), encoding="utf-8")
        with pytest.raises(receipts.ReceiptError, match="snapshot_date"):
            receipts.verify_record(dataset, uuids[0])


class TestDeterminism:
    def test_the_same_record_writes_the_same_bytes(self, built: Path, uuids: list[str]) -> None:
        record_bytes = (built / "programs" / f"{uuids[0]}.json").read_bytes()
        record = json.loads(record_bytes.decode("utf-8"))
        first = receipts.receipt_bytes(
            receipts.receipt_for(
                record, record_bytes, snapshot_date="2026-08-07", state="CA", is_fixture=True
            )
        )
        second = receipts.receipt_bytes(
            receipts.receipt_for(
                record, record_bytes, snapshot_date="2026-08-07", state="CA", is_fixture=True
            )
        )
        assert first == second

    def test_measure_order_follows_the_table_rather_than_the_record(
        self, built: Path, uuids: list[str]
    ) -> None:
        """Two calls in one interpreter cannot see a dropped ordering -- a dict built from
        the same source in the same process comes out the same way twice whatever it is
        keyed on. This asserts the order itself."""
        stated = list(_receipt(built, uuids[0])["measures"])
        assert stated == [column.name for column in receipts.MEASURE_COLUMNS]

    def test_no_clock_is_read(self) -> None:
        source = (REPO_ROOT / "src" / "afterward" / "receipts.py").read_text(encoding="utf-8")
        for forbidden in ("datetime", "time.time", "date.today", "utcnow"):
            assert forbidden not in source, forbidden


class TestTheStandaloneCheck:
    """`scripts/receipt_check.py`, which may not import this package."""

    def _run(self, dataset: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603
            [sys.executable, str(REPO_ROOT / "scripts" / "receipt_check.py"), str(dataset)],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_its_copy_of_the_schema_version_is_the_real_one(self) -> None:
        """It duplicates the constant because it may not import `afterward`. That is only
        safe while something compares the two."""
        source = (REPO_ROOT / "scripts" / "receipt_check.py").read_text(encoding="utf-8")
        assert f'SCHEMA_VERSION = "{receipts.SCHEMA_VERSION}"' in source

    def test_it_does_not_import_the_package_it_checks(self) -> None:
        """The deploy job installs Node and no Python toolchain. A check the publishing path
        cannot run guards only the packaging path, which was never the one a stale dataset
        arrives by."""
        source = (REPO_ROOT / "scripts" / "receipt_check.py").read_text(encoding="utf-8")
        assert "import afterward" not in source
        assert "from afterward" not in source

    def test_a_whole_build_pairs(self, built: Path) -> None:
        done = self._run(built)
        assert done.returncode == 0, done.stdout + done.stderr
        assert "60 of 60 records pair" in done.stdout

    def test_records_and_receipts_from_two_builds_are_refused(
        self, built: Path, uuids: list[str], tmp_path: Path
    ) -> None:
        dataset = _copy(built, tmp_path)
        record = _record(built, uuids[0])
        record["outcomes"]["total_served"] = 12345.0
        _rewrite_record(dataset, uuids[0], record)
        done = self._run(dataset)
        assert done.returncode == 1
        assert "REFUSING" in done.stdout
        assert uuids[0] in done.stdout

    def test_a_missing_receipt_is_refused_not_skipped(
        self, built: Path, uuids: list[str], tmp_path: Path
    ) -> None:
        dataset = _copy(built, tmp_path)
        (dataset / receipts.RECEIPT_DIRNAME / f"{uuids[0]}.json").unlink()
        done = self._run(dataset)
        assert done.returncode == 1
        assert "a record with no receipt beside it" in done.stdout

    def test_a_dataset_predating_receipts_says_so_and_passes(
        self, built: Path, tmp_path: Path
    ) -> None:
        """The three published releases carry none, and `deploy.yml` can be asked to publish
        any of them by tag. Passing is right; passing quietly is not, because "nothing was
        compared" and "everything checked out" would then print the same way."""
        dataset = _copy(built, tmp_path)
        shutil.rmtree(dataset / receipts.RECEIPT_DIRNAME)
        done = self._run(dataset)
        assert done.returncode == 0
        assert "0 of 60 records carry a receipt" in done.stdout
        assert "Nothing was compared; that is not agreement." in done.stdout

    def test_an_empty_dataset_is_refused(self, tmp_path: Path) -> None:
        (tmp_path / "programs").mkdir()
        done = self._run(tmp_path)
        assert done.returncode == 1
        assert "nothing to pair" in done.stdout


class TestTheRefusals:
    """Every branch that declines to answer, driven rather than described.

    These were the module's uncovered lines after the suite above passed, and a refusal
    nothing exercises is a refusal nobody has read: the failure mode is not that it fires
    wrongly, it is that it raises the wrong exception type and a caller that meant to
    report "cannot check" reports a stack trace instead.
    """

    def test_a_record_with_no_uuid_cannot_be_receipted(self) -> None:
        with pytest.raises(receipts.ReceiptError, match="no uuid"):
            receipts.receipt_for(
                {"outcomes": {}}, b"{}", snapshot_date="d", state="CA", is_fixture=True
            )

    def test_a_path_that_is_neither_a_directory_nor_a_file(self, tmp_path: Path) -> None:
        missing = tmp_path / "nothing-here.tar.gz"
        with (
            pytest.raises(receipts.ReceiptError, match="neither a dataset directory nor a file"),
            receipts.open_dataset(missing),
        ):
            pass

    def test_a_file_that_is_not_an_archive(self, tmp_path: Path) -> None:
        plain = tmp_path / "not-a-tarball.tar.gz"
        plain.write_bytes(b"this is not a gzip stream")
        with (
            pytest.raises(receipts.ReceiptError, match="could not be read as a dataset archive"),
            receipts.open_dataset(plain),
        ):
            pass

    def test_an_archive_that_escapes_its_root_is_refused(self, tmp_path: Path) -> None:
        """A release asset is untrusted input: `gh release download` fetches whatever the
        release holds, and a reader may point this at any tarball at all."""
        payload = tmp_path / "payload.json"
        payload.write_text("{}", encoding="utf-8")
        tarball = tmp_path / "escaping.tar.gz"
        with tarfile.open(tarball, "w:gz") as archive:
            archive.add(payload, arcname="../escaped.json")
        with (
            pytest.raises(receipts.ReceiptError, match="unsafe member"),
            receipts.open_dataset(tarball),
        ):
            pass

    def test_an_archive_carrying_a_symlink_is_refused(self, tmp_path: Path) -> None:
        link = tmp_path / "link"
        link.symlink_to("/etc/passwd")
        tarball = tmp_path / "linked.tar.gz"
        with tarfile.open(tarball, "w:gz") as archive:
            archive.add(link, arcname="programs/link")
        with (
            pytest.raises(receipts.ReceiptError, match="unsafe member"),
            receipts.open_dataset(tarball),
        ):
            pass

    def test_an_oversized_archive_is_refused_before_it_is_opened(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tarball = tmp_path / "big.tar.gz"
        tarball.write_bytes(b"0" * 64)
        monkeypatch.setattr(receipts, "MAXIMUM_TARBALL_BYTES", 8)
        with (
            pytest.raises(receipts.ReceiptError, match="exceeds the tarball size limit"),
            receipts.open_dataset(tarball),
        ):
            pass

    def test_an_unreadable_aggregate(self, built: Path, uuids: list[str], tmp_path: Path) -> None:
        dataset = _copy(built, tmp_path)
        (dataset / "programs.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(receipts.ReceiptError, match="could not be read"):
            receipts.verify_record(dataset, uuids[0])

    def test_an_aggregate_that_is_not_an_object(
        self, built: Path, uuids: list[str], tmp_path: Path
    ) -> None:
        dataset = _copy(built, tmp_path)
        (dataset / "coverage.json").write_text("[]", encoding="utf-8")
        with pytest.raises(receipts.ReceiptError, match="must each be a JSON object"):
            receipts.verify_record(dataset, uuids[0])

    def test_a_dataset_that_cannot_say_which_state_it_is(
        self, built: Path, uuids: list[str], tmp_path: Path
    ) -> None:
        dataset = _copy(built, tmp_path)
        document = json.loads((dataset / "programs.json").read_text(encoding="utf-8"))
        del document["state"]
        (dataset / "programs.json").write_text(json.dumps(document), encoding="utf-8")
        with pytest.raises(receipts.ReceiptError, match="carries no state"):
            receipts.verify_record(dataset, uuids[0])

    def test_a_receipt_that_is_not_an_object(
        self, built: Path, uuids: list[str], tmp_path: Path
    ) -> None:
        dataset = _copy(built, tmp_path)
        (dataset / receipts.RECEIPT_DIRNAME / f"{uuids[0]}.json").write_text("[]", encoding="utf-8")
        result = receipts.verify_record(dataset, uuids[0])
        assert result.status == "cannot_check"
        assert result.reason == "the receipt is not an object"

    def test_the_floor_is_the_thinnest_honest_receipt_rather_than_a_number(self) -> None:
        """`MINIMUM_FIELDS` has to describe the schema, or it stops meaning anything the day
        the schema changes. The thinnest receipt version 1 can produce is a program that
        filed no SOC codes, joined no occupation and gave no website, with every measure
        withheld -- and the floor must sit at or below exactly that, never above it, or a
        real record becomes unverifiable."""
        thinnest = receipts.receipt_for(
            {
                "uuid": "u",
                "cost": {},
                "length": {},
                "outcomes": {},
                "soc_codes": [],
                "occupations": [],
                "provider_link": None,
            },
            b"{}",
            snapshot_date="2026-08-17",
            state="CA",
            is_fixture=False,
        )
        leaves = receipts._leaf_count(
            {k: v for k, v in thinnest.items() if k != receipts.DIGEST_FIELD}
        )
        assert leaves == 23
        assert leaves == receipts.MINIMUM_FIELDS

    def test_a_comparison_below_the_floor_is_refused_rather_than_agreed_with(
        self, built: Path, uuids: list[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The branch itself, driven. A comparison of almost nothing agrees with almost
        nothing and disagrees with almost nothing, which is indistinguishable from a
        comparison of everything unless something refuses it."""
        monkeypatch.setattr(receipts, "MINIMUM_FIELDS", 10_000)
        result = receipts.verify_record(built, uuids[0])
        assert result.status == "cannot_check"
        assert result.reason is not None
        assert "below the floor of 10000" in result.reason
        assert "not a pass" in result.reason

    def test_a_disagreement_prints_both_sides_and_names_an_absence(
        self, built: Path, uuids: list[str], tmp_path: Path
    ) -> None:
        """The line a reader actually sees. An absent value has to render as an absence
        rather than as `None`, or a receipt that withheld a figure and a record that filed a
        null read identically in the one place the difference is being explained."""
        uuid = next(u for u in uuids if _record(built, u)["outcomes"]["median_earnings"] is None)
        dataset = _copy(built, tmp_path)
        record = _record(built, uuid)
        record["outcomes"]["median_earnings"] = 41000.0
        _rewrite_record(dataset, uuid, record)
        result = runner.invoke(app, ["verify-record", uuid, "--dataset", str(dataset)])
        assert result.exit_code == 1
        assert "measures.median_earnings.value: receipt <absent>, dataset 41000.0" in result.output
        assert (
            "measures.median_earnings.state: receipt 'not_reported', dataset 'reported'"
            in result.output
        )
