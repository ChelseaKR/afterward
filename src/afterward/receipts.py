"""A per-program receipt: what this project published about one record, in a form a reader
can check without cloning anything.

`scripts/verify_live_site.py` already asks whether the bytes the site serves are the bytes of
the dataset release the site names. That check is the operator's: it needs `gh`, it downloads
a 40 MB tarball, and it runs on a schedule nobody outside this repository sees. A receipt
hands the same question to the reader, one record at a time.

WHAT A RECEIPT IS

A small JSON document written beside every program record, saying:

* which record it is (``uuid``) and which snapshot it came from;
* the sha256 of **the exact bytes of the record file beside it** -- so a reader with the
  released tarball can run ``shasum -a 256 programs/<uuid>.json`` and compare, with no
  canonicalisation rule to reimplement and nothing to trust;
* the state of every measure, in the vocabulary
  :mod:`afterward.tabular` already publishes in the flat CSV -- ``reported``,
  ``not_reported``, ``competency_based`` and no fourth word;
* how the occupation join reached each occupation, and the program's own SOC codes;
* what the link checker found, and which classifier version found it.

**A measure that is not reported carries no number.** Its entry is exactly
``{"state": "not_reported"}`` -- no ``value`` key, no null, no zero. A receipt is consumed by
machines that never saw the page's caveats, so an absence leaking into one as a zero would be
worse here than anywhere else on the site. :func:`measure_entry` is the only place that
decides it, and it reads :func:`afterward.tabular.state_of`, so the receipt and the CSV cannot
disagree about what a measure's state is.

WHAT A RECEIPT DELIBERATELY DOES NOT SAY

**The dataset tarball's sha256.** Issue #113 asks for it, and a receipt cannot honestly carry
it: ``make dataset-package`` tars the whole dataset directory, receipts included, so a digest
of the tarball inside the tarball is a fixed point that does not exist. ``record_sha256`` is
the checkable thing in its place, and it is the more useful one -- it is about the record the
reader is reading rather than about the archive it arrived in.

**The D1 source row's hash.** Also asked for, and it fails the issue's own first scope
bullet: it is available only in :func:`afterward.build.build`, because ``build_offline`` reads
this pipeline's own emitted records and never sees an upstream row. A field that is null on
every CI build and on the committed fixture is not "emitted by both build paths". It is also
unverifiable by the reader the receipt is for: nobody downstream holds DOL's row, so the hash
would be a token no one can check. Recorded as a follow-up rather than shipped as a null.

**Anything signed.** ADR 0001 records that this repository does not sign releases. A receipt
proves that a record and its receipt were written by one build; it proves nothing about who
ran that build, and it says so rather than implying otherwise.

DETERMINISM

No clock is read. Key order is fixed by this module, measure order follows
:data:`afterward.tabular.COLUMNS`, and occupation order follows the record's own -- so the
same record produces byte-identical receipt bytes, and nothing here iterates a set.
"""

from __future__ import annotations

import hashlib
import json
import tarfile
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from afterward.tabular import COLUMNS, REPORTED, Column, state_of, value_of

__all__ = [
    "MEASURE_COLUMNS",
    "RECEIPT_DIRNAME",
    "SCHEMA_VERSION",
    "Disagreement",
    "ReceiptError",
    "VerifyResult",
    "disagreements",
    "measure_entry",
    "open_dataset",
    "receipt_for",
    "record_digest",
    "release_tag_for",
    "verify_record",
]

SCHEMA_VERSION: Final = "afterward.receipt/1"
"""Bumped when the shape below changes in a way a reader's script would notice.

A consumer should refuse a version it does not know rather than guess at it, which is what
:func:`verify_record` does.
"""

RECEIPT_DIRNAME: Final = "receipts"
"""Sibling of ``programs/`` in the emitted dataset, sharded the same way."""

PROGRAM_DIRNAME: Final = "programs"

MEASURE_COLUMNS: Final[tuple[Column, ...]] = tuple(c for c in COLUMNS if c.measured)
"""Every measure the receipt states, taken from the flat table's own column list.

Derived rather than listed, so a measure added to the CSV enters the receipt in the same
commit and a measure dropped from one cannot survive in the other.
"""

MAXIMUM_TARBALL_BYTES: Final = 256 * 1024 * 1024


class ReceiptError(RuntimeError):
    """A receipt could not be built or a dataset could not be read."""


def record_digest(record_bytes: bytes) -> str:
    """``sha256:`` plus the hex digest of the record file's exact bytes.

    Prefixed so a reader can tell at a glance what the string is, and so a future digest
    algorithm arrives as a different prefix rather than as a hex string of another length
    that a naive comparison would simply call unequal.
    """
    return f"sha256:{hashlib.sha256(record_bytes).hexdigest()}"


def release_tag_for(snapshot_date: str, *, is_fixture: bool) -> str | None:
    """The release tag this snapshot would be published under, or ``None``.

    ``make dataset-publish`` tags a release ``dataset-<snapshot_date>``, so the tag is
    derivable and is worth carrying: it is how a reader gets from a page to the archive the
    page was built from. It is a **pointer, not an attestation** -- this build cannot know
    whether that release exists, and :func:`verify_record` never treats it as evidence.

    ``None`` for a fixture build, and that is the load-bearing half. The 60-program CI
    fixture carries a real snapshot date, so the naive derivation would point every fixture
    receipt at a genuine published release holding 3,266 quite different programs. A reader
    following it would find a well-formed dataset that disagrees with the receipt everywhere,
    and would have no way to tell that from drift.
    """
    return None if is_fixture else f"dataset-{snapshot_date}"


def measure_entry(record: Mapping[str, Any], column: Column) -> dict[str, Any]:
    """One measure's entry: its state word, and its value only where there is one.

    The value key is **absent** rather than null when the state is anything but ``reported``.
    Absent is the only rendering that cannot be read as a number by something that was not
    paying attention: ``null`` invites ``or 0``, and a zero is the failure this whole project
    is written against.
    """
    state = state_of(record, column)
    if state != REPORTED:
        return {"state": state}
    return {"state": state, "value": value_of(record, column)}


def _occupation_entry(occupation: Mapping[str, Any]) -> dict[str, Any]:
    match = occupation.get("match")
    match = match if isinstance(match, Mapping) else {}
    return {
        "soc_code": occupation.get("soc_code"),
        "match_kind": match.get("kind"),
        "entry_level_education_withheld": match.get("entry_level_education_withheld"),
    }


def _provider_link_entry(record: Mapping[str, Any]) -> dict[str, Any] | None:
    """What the link checker found, or ``None`` when the program filed no address at all.

    ``None`` and a block whose ``verdict`` is null are different answers and are kept apart:
    the first is a program that gave no website, the second is a website nobody has read.
    Neither is "the link is broken".
    """
    link = record.get("provider_link")
    if not isinstance(link, Mapping):
        return None
    return {
        "verdict": link.get("verdict"),
        "reason": link.get("reason"),
        "checked_on": link.get("checked_on"),
        # Null wherever the verdict is null: no classifier ran, so naming one would claim a
        # judgement nobody made. See link_check.CLASSIFIER_VERSION.
        "classifier_version": link.get("classifier_version"),
    }


def receipt_for(
    record: Mapping[str, Any],
    record_bytes: bytes,
    *,
    snapshot_date: str,
    state: str,
    is_fixture: bool,
) -> dict[str, Any]:
    """The receipt for one emitted program record.

    ``record_bytes`` is the exact bytes written to ``programs/<uuid>.json``, not a
    re-serialisation of ``record``. Hashing a re-serialisation would attest to a document
    nobody is served, and would go on agreeing with itself after the writer's separators
    changed underneath it.
    """
    uuid = record.get("uuid")
    if not isinstance(uuid, str) or not uuid:
        raise ReceiptError("a record with no uuid cannot be receipted")
    occupations = record.get("occupations")
    occupations = occupations if isinstance(occupations, Sequence) else ()
    soc_codes = record.get("soc_codes")
    return {
        "schema": SCHEMA_VERSION,
        "uuid": uuid,
        "snapshot_date": snapshot_date,
        "state": state,
        "is_fixture": is_fixture,
        "release_tag": release_tag_for(snapshot_date, is_fixture=is_fixture),
        "record_path": f"{PROGRAM_DIRNAME}/{uuid}.json",
        "record_sha256": record_digest(record_bytes),
        "measures": {column.name: measure_entry(record, column) for column in MEASURE_COLUMNS},
        # The codes the provider filed, kept beside the join so the join can be audited
        # against them rather than taken on trust.
        "program_soc_codes": list(soc_codes) if isinstance(soc_codes, list) else [],
        "occupations": [
            _occupation_entry(occupation)
            for occupation in occupations
            if isinstance(occupation, Mapping)
        ],
        "provider_link": _provider_link_entry(record),
    }


def receipt_bytes(receipt: Mapping[str, Any]) -> bytes:
    """The receipt as it is written to disk. Compact, and in this module's own key order."""
    return json.dumps(receipt, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


# --------------------------------------------------------------------------------------
# Comparing a receipt with the record it describes
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Disagreement:
    """One field on which the attested receipt and the dataset do not agree."""

    path: str
    attested: object
    actual: object

    def __str__(self) -> str:
        return f"{self.path}: receipt {self.attested!r}, dataset {self.actual!r}"


def _walk(attested: object, actual: object, prefix: str, found: list[Disagreement]) -> None:
    if isinstance(attested, Mapping) and isinstance(actual, Mapping):
        # Sorted so the report is deterministic and so a key present on one side only is
        # named rather than skipped.
        for key in sorted(set(attested) | set(actual)):
            path = f"{prefix}.{key}" if prefix else str(key)
            if key not in attested:
                found.append(Disagreement(path, _ABSENT, actual[key]))
            elif key not in actual:
                found.append(Disagreement(path, attested[key], _ABSENT))
            else:
                _walk(attested[key], actual[key], path, found)
        return
    if isinstance(attested, list) and isinstance(actual, list):
        if len(attested) != len(actual):
            found.append(Disagreement(f"{prefix}[]", len(attested), len(actual)))
            return
        for index, (left, right) in enumerate(zip(attested, actual, strict=True)):
            _walk(left, right, f"{prefix}[{index}]", found)
        return
    if attested != actual:
        found.append(Disagreement(prefix, attested, actual))


class _Absent:
    def __repr__(self) -> str:
        return "<absent>"


_ABSENT: Final = _Absent()

DIGEST_FIELD: Final = "record_sha256"


def disagreements(attested: Mapping[str, Any], recomputed: Mapping[str, Any]) -> list[Disagreement]:
    """Every field on which the two receipts differ, ``record_sha256`` excluded.

    The digest is reported separately by :func:`verify_record` because it is a different
    statement: it says the record is not the one this receipt was written for, which is true
    whenever *any* byte moved -- including bytes no field of the receipt describes. Folding
    it in would mean a single changed measure named two things, and the point of the field
    list is to say which one measure it was.
    """
    found: list[Disagreement] = []
    _walk(
        {k: v for k, v in attested.items() if k != DIGEST_FIELD},
        {k: v for k, v in recomputed.items() if k != DIGEST_FIELD},
        "",
        found,
    )
    return found


def _leaf_count(value: object) -> int:
    """How many scalar comparisons a document is worth.

    Printed as the denominator of the verdict. An agreement over nothing reads exactly like
    an agreement over everything, and this is what tells them apart.
    """
    if isinstance(value, Mapping):
        return sum(_leaf_count(item) for item in value.values())
    if isinstance(value, list):
        return sum(_leaf_count(item) for item in value)
    return 1


MINIMUM_FIELDS: Final = 23
"""Floor on the number of scalar fields a comparison must reach to count as one.

Derived from the shape rather than chosen: the thinnest honest version-1 receipt describes a
program that filed no SOC codes, joined no occupation and gave no website, with every measure
withheld. That is seven identity fields, fifteen one-key measure entries and a null provider
link -- **23**, and `tests/test_receipts.py` recomputes that arithmetic so the constant cannot
outlive the schema it describes.

An agreement over nothing reads exactly like an agreement over everything, which is why the
verdict prints its denominator and why this refuses rather than passing beneath it.
"""


@dataclass(frozen=True, slots=True)
class VerifyResult:
    """The verdict on one record, and the numbers behind it."""

    uuid: str
    status: Literal["agrees", "disagrees", "cannot_check"]
    fields: tuple[Disagreement, ...] = ()
    fields_compared: int = 0
    attested_digest: str | None = None
    actual_digest: str | None = None
    reason: str | None = None

    @property
    def exit_code(self) -> int:
        """0 the receipt and the dataset agree, 1 they do not, 2 nothing was checked."""
        return {"agrees": 0, "disagrees": 1, "cannot_check": 2}[self.status]

    @property
    def digest_agrees(self) -> bool:
        return self.attested_digest is not None and self.attested_digest == self.actual_digest


@contextmanager
def open_dataset(path: Path) -> Iterator[Path]:
    """Yield a directory holding the dataset at ``path``, which may be a tarball.

    A ``.tar.gz`` is extracted into a temporary directory that is removed on the way out.
    Members are refused on the same terms as ``scripts/verify_live_site.py``: no absolute
    path, no ``..``, no link of either kind. A downloaded release asset is untrusted input.
    """
    if path.is_dir():
        yield path
        return
    if not path.is_file():
        raise ReceiptError(f"{path} is neither a dataset directory nor a file")
    if path.stat().st_size > MAXIMUM_TARBALL_BYTES:
        raise ReceiptError(f"{path.name} exceeds the tarball size limit")
    with tempfile.TemporaryDirectory(prefix="afterward-receipt-") as directory:
        into = Path(directory)
        try:
            with tarfile.open(path, "r:*") as archive:
                for member in archive.getmembers():
                    name = Path(member.name)
                    if member.issym() or member.islnk() or name.is_absolute():
                        raise ReceiptError(f"{path.name} contains an unsafe member: {member.name}")
                    if ".." in name.parts:
                        raise ReceiptError(f"{path.name} contains an unsafe member: {member.name}")
                archive.extractall(into, filter="data")
        except tarfile.TarError as exc:
            raise ReceiptError(
                f"{path.name} could not be read as a dataset archive: {exc}"
            ) from exc
        yield into


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReceiptError(f"{path.name} could not be read: {exc}") from exc


def _dataset_identity(dataset_dir: Path) -> tuple[str, str, bool]:
    """``(snapshot_date, state, is_fixture)`` for a dataset, or a refusal.

    Read from the two aggregates rather than from any receipt, so a receipt cannot vouch for
    the facts it is being checked against.
    """
    programs_doc = _read_json(dataset_dir / "programs.json")
    coverage = _read_json(dataset_dir / "coverage.json")
    if not isinstance(programs_doc, Mapping) or not isinstance(coverage, Mapping):
        raise ReceiptError("programs.json and coverage.json must each be a JSON object")
    snapshot = programs_doc.get("snapshot_date")
    if not isinstance(snapshot, str) or not snapshot:
        raise ReceiptError("programs.json carries no snapshot_date, so nothing can be recomputed")
    state = programs_doc.get("state")
    if not isinstance(state, str) or not state:
        raise ReceiptError("programs.json carries no state, so nothing can be recomputed")
    # Absent means a real build, which is this repository's settled convention and not a
    # fourth reading of the question: `scripts/verify_live_site.py`, `scripts/release_
    # integrity.py` and `afterward.ask.dataset.Dataset.load` all read it exactly this way,
    # and `scripts/make_fixture.py` is the only writer -- it sets the key to true, and
    # `scripts/ci_artifact_check.py` refuses a CI artifact that does not carry it. A fifth
    # spelling here would be the drift, not the safeguard.
    return snapshot, state, bool(coverage.get("is_fixture", False))


def verify_record(
    dataset_dir: Path, uuid: str, *, receipt_path: Path | None = None
) -> VerifyResult:
    """Recompute one record's receipt from the dataset and compare it with the attested one.

    ``receipt_path`` defaults to the receipt inside the dataset, which answers "was this
    archive written by one build?" -- the state a half-synced bucket or a directory assembled
    from two snapshots produces, and one no digest of the archive alone can see. Pass the
    receipt a page served instead, and the same call answers the reader's question: is the
    page I am reading describing the record in the release?

    Three outcomes, and the third is not a pass. ``cannot_check`` covers a record the dataset
    does not hold, a record it holds with no receipt beside it, a dataset that cannot say
    which snapshot it is, and a receipt written to a schema version this build does not know.
    Every one of them is a state in which nothing was compared, and reporting any of them as
    agreement is the failure this verb exists to make impossible.
    """
    record_file = dataset_dir / PROGRAM_DIRNAME / f"{uuid}.json"
    if not record_file.is_file():
        return VerifyResult(
            uuid=uuid,
            status="cannot_check",
            reason=f"no record {uuid} in this dataset ({record_file.parent} holds no such file)",
        )
    attested_file = receipt_path or (dataset_dir / RECEIPT_DIRNAME / f"{uuid}.json")
    if not attested_file.is_file():
        return VerifyResult(
            uuid=uuid,
            status="cannot_check",
            reason=(
                f"no receipt for {uuid} at {attested_file}. A dataset built before receipts "
                f"existed carries none; that is not agreement."
            ),
        )
    attested = _read_json(attested_file)
    if not isinstance(attested, Mapping):
        return VerifyResult(uuid=uuid, status="cannot_check", reason="the receipt is not an object")
    if attested.get("schema") != SCHEMA_VERSION:
        return VerifyResult(
            uuid=uuid,
            status="cannot_check",
            reason=(
                f"receipt schema {attested.get('schema')!r} is not {SCHEMA_VERSION!r}; this "
                f"build will not guess at a shape it does not know"
            ),
        )

    snapshot, state, is_fixture = _dataset_identity(dataset_dir)
    record_bytes = record_file.read_bytes()
    record = json.loads(record_bytes.decode("utf-8"))
    recomputed = receipt_for(
        record, record_bytes, snapshot_date=snapshot, state=state, is_fixture=is_fixture
    )
    fields = disagreements(attested, recomputed)
    compared = _leaf_count({k: v for k, v in recomputed.items() if k != DIGEST_FIELD})
    if compared < MINIMUM_FIELDS:
        return VerifyResult(
            uuid=uuid,
            status="cannot_check",
            reason=(
                f"only {compared} field(s) could be compared, below the floor of "
                f"{MINIMUM_FIELDS}. A comparison of almost nothing is not a pass."
            ),
        )
    attested_digest = attested.get(DIGEST_FIELD)
    actual_digest = recomputed[DIGEST_FIELD]
    agrees = not fields and attested_digest == actual_digest
    return VerifyResult(
        uuid=uuid,
        status="agrees" if agrees else "disagrees",
        fields=tuple(fields),
        fields_compared=compared,
        attested_digest=attested_digest if isinstance(attested_digest, str) else None,
        actual_digest=actual_digest,
    )
