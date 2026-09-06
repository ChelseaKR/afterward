"""What changed between two emitted datasets, with each kind of change kept apart from the others.

Every refresh replaces the dataset wholesale, and the only review it gets is the shape floors in
``dataset_check.py``: a count that did not collapse. That review cannot see the events this
project exists to notice.

Three things happen when a programme's number disappears, and they are not the same event.

* The programme **left the list**. Nobody is publishing anything about it, because it is gone.
* The programme is still listed and the measure **stopped being reported**. Somebody who used to
  answer no longer does, and the reader who saw a figure last month now sees an absence.
* The programme was **never on the list**, so no measure ever moved at all.

Collapsing those into "the number is gone" is the same error, one level up, that this codebase
spends its whole life avoiding on a single value. A diff that keeps them apart is how absence
stays absence across time.

So this module classifies, and does not aggregate away the classification. A measure that went
from a number to ``null`` is a ``stopped_reporting`` event on that measure, on that programme,
counted per measure; a measure that went the other way is ``started_reporting``. A programme that
disappeared is ``program_removed`` and produces no measure events at all, because the measures did
not move -- the programme did.

**An empty diff means "compared, and nothing moved". It never means "could not compare."** If a
dataset directory is missing or unreadable, this refuses and writes nothing. The alternative --
returning zero counts because there was nothing to read -- is a statement that the refresh changed
nothing, published on the strength of never having looked, and it is exactly the failure mode the
rest of this repository is built to prevent.

Deterministic: events sort by kind then by programme, no wall-clock is recorded anywhere, and the
only dates in the output are the two snapshots' own. Identical directories produce zero counts and
byte-identical output.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

__all__ = [
    "DIFF_FORMAT_VERSION",
    "MEASURES",
    "STATEMENT_FILENAME",
    "SUMMARY_FILENAME",
    "Change",
    "DatasetDiff",
    "DatasetUnreadable",
    "compare",
    "diff_datasets",
    "load_dataset",
    "to_markdown",
]

DIFF_FORMAT_VERSION: Final[int] = 1

STATEMENT_FILENAME: Final = "changes.json"
SUMMARY_FILENAME: Final = "changes.md"

MEASURES: Final[tuple[str, ...]] = (
    "total_served",
    "total_exited",
    "total_completed",
    "completion_rate",
    "credentials_earned",
    "median_earnings",
    "employment_rate_q2",
    "employed_q2",
    "employed_q4",
)
"""The outcome measures whose reporting state is tracked, one count per measure.

Every measure the emitted record carries, not only the three the site benchmarks. A measure the
site does not render can still stop being reported, and the point of this diff is to see that
happen rather than to see the subset somebody already decided to look at.
"""

_LENGTH_FIELDS: Final[tuple[str, ...]] = ("weeks", "hours")
_COST_FIELDS: Final[tuple[str, ...]] = (
    "tuition",
    "supplies",
    "total_out_of_pocket",
    "wioa_funded_cost",
)

# Event kinds, in the order they are reported. Programme membership first, because a measure event
# on a programme that left the list is a category error and this order makes that obvious to a
# reader scanning the summary.
KINDS: Final[tuple[str, ...]] = (
    "program_added",
    "program_removed",
    "program_retitled",
    "provider_gone",
    "provider_new",
    "stopped_reporting",
    "started_reporting",
    "length_changed",
    "cost_changed",
    "occupation_match_changed",
    "link_verdict_changed",
)


class DatasetUnreadable(Exception):
    """A dataset directory this build will not compare, with the reason in the message.

    Raised rather than returning an empty diff. See the module docstring: zero counts must mean
    "nothing moved", and a caller that cannot tell that apart from "nothing was read" will
    eventually publish the second as the first.
    """


@dataclass(frozen=True, slots=True)
class Change:
    """One classified event, addressed to the programme it happened to."""

    kind: str
    uuid: str
    subject: str = ""
    """The measure, field or provider the event is about. Empty where the event is the programme."""

    before: str = ""
    after: str = ""

    def as_payload(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "uuid": self.uuid,
            "subject": self.subject,
            "before": self.before,
            "after": self.after,
        }

    @property
    def _order(self) -> tuple[int, str, str]:
        return (KINDS.index(self.kind), self.uuid, self.subject)


@dataclass(frozen=True, slots=True)
class Dataset:
    """One emitted dataset, reduced to what a diff reads."""

    snapshot_date: str
    programs: Mapping[str, Mapping[str, Any]]
    occupations: int
    total_programs: int

    @property
    def providers(self) -> frozenset[str]:
        return frozenset(
            str(p.get("provider_name", ""))
            for p in self.programs.values()
            if p.get("provider_name")
        )


@dataclass(frozen=True, slots=True)
class DatasetDiff:
    """The comparison of two datasets, and the counts a summary is written from."""

    earlier: str
    later: str
    earlier_programs: int
    later_programs: int
    earlier_occupations: int
    later_occupations: int
    changes: tuple[Change, ...]

    @property
    def counts(self) -> dict[str, Any]:
        """Counts by kind, with the measure events broken out per measure.

        A total of stopped-reporting events across all measures is nearly useless -- nine
        measures moving once each and one measure moving nine times are different events -- so
        the measure counts are never summed into a single number here.
        """
        by_kind = {kind: 0 for kind in KINDS}
        measures: dict[str, dict[str, int]] = {
            measure: {"stopped_reporting": 0, "started_reporting": 0} for measure in MEASURES
        }
        for change in self.changes:
            by_kind[change.kind] += 1
            if change.kind in ("stopped_reporting", "started_reporting"):
                measures[change.subject][change.kind] += 1
        return {"by_kind": by_kind, "by_measure": measures}

    @property
    def total(self) -> int:
        return len(self.changes)

    def as_payload(self) -> dict[str, Any]:
        """The committed statement. Nothing in it is derived from the clock."""
        return {
            "version": DIFF_FORMAT_VERSION,
            "compared": True,
            "earlier": {
                "snapshot_date": self.earlier,
                "programs": self.earlier_programs,
                "occupations": self.earlier_occupations,
            },
            "later": {
                "snapshot_date": self.later,
                "programs": self.later_programs,
                "occupations": self.later_occupations,
            },
            "measures": list(MEASURES),
            "kinds": list(KINDS),
            "counts": self.counts,
            "total_changes": self.total,
            "changes": [change.as_payload() for change in self.changes],
        }


def load_dataset(dataset_dir: Path) -> Dataset:
    """Read one emitted dataset, refusing anything it cannot read rather than reading it as empty.

    Raises:
        DatasetUnreadable: If the directory, either file, or the keys this reads are absent or
            malformed. Every one of those would otherwise produce a dataset of zero programmes,
            which compares as "everything was removed" or "nothing changed" depending on which
            side it lands on. Both are fabrications.
    """
    programs_path = dataset_dir / "programs.json"
    coverage_path = dataset_dir / "coverage.json"
    for path in (programs_path, coverage_path):
        if not path.is_file():
            raise DatasetUnreadable(
                f"{path} does not exist, so this dataset cannot be compared. Refusing rather than "
                "reading it as a dataset with nothing in it, which would report every programme "
                "as added or removed."
            )
    try:
        document = json.loads(programs_path.read_text(encoding="utf-8"))
        coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasetUnreadable(f"{dataset_dir} contains invalid JSON: {exc}") from exc

    records = document.get("programs")
    if not isinstance(records, list):
        raise DatasetUnreadable(f"{programs_path} has no 'programs' list")
    snapshot_date = coverage.get("snapshot_date")
    if not isinstance(snapshot_date, str) or not snapshot_date:
        raise DatasetUnreadable(
            f"{coverage_path} states no snapshot_date, so a comparison could not say which two "
            "days it is about"
        )

    by_uuid: dict[str, Mapping[str, Any]] = {}
    for record in records:
        uuid = record.get("uuid")
        if not isinstance(uuid, str) or not uuid:
            raise DatasetUnreadable(f"{programs_path} carries a record with no uuid to compare on")
        by_uuid[uuid] = record
    return Dataset(
        snapshot_date=snapshot_date,
        programs=by_uuid,
        occupations=int(coverage.get("distinct_occupations_matched") or 0),
        total_programs=len(by_uuid),
    )


def _measure(record: Mapping[str, Any], name: str) -> object:
    outcomes = record.get("outcomes")
    return outcomes.get(name) if isinstance(outcomes, Mapping) else None


def _number(value: object) -> str:
    """One value as a string for the statement, with ``None`` written as the empty string."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _section(record: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    section = record.get(name)
    return section if isinstance(section, Mapping) else {}


def _first_match_kind(record: Mapping[str, Any]) -> str:
    occupations = record.get("occupations")
    if not isinstance(occupations, list) or not occupations:
        return ""
    first = occupations[0]
    if not isinstance(first, Mapping):
        return ""
    match = first.get("match")
    return str(match.get("kind", "")) if isinstance(match, Mapping) else ""


def _link_verdict(record: Mapping[str, Any]) -> str:
    return str(_section(record, "provider_link").get("verdict", ""))


def _measure_changes(
    uuid: str, before: Mapping[str, Any], after: Mapping[str, Any]
) -> list[Change]:
    """One event per measure whose reporting state moved, in either direction.

    A value that changed from one number to another is not here on purpose: this tracks whether
    a measure is reported, not what it says. Those are different questions and folding them
    together would bury the first under a churn of the second.
    """
    changes: list[Change] = []
    for measure in MEASURES:
        was = _measure(before, measure)
        now = _measure(after, measure)
        if was is not None and now is None:
            changes.append(
                Change(kind="stopped_reporting", uuid=uuid, subject=measure, before=_number(was))
            )
        elif was is None and now is not None:
            changes.append(
                Change(kind="started_reporting", uuid=uuid, subject=measure, after=_number(now))
            )
    return changes


def _length_changes(uuid: str, before: Mapping[str, Any], after: Mapping[str, Any]) -> list[Change]:
    old, new = _section(before, "length"), _section(after, "length")
    return [
        Change(
            kind="length_changed",
            uuid=uuid,
            subject=field,
            before=_number(old.get(field)),
            after=_number(new.get(field)),
        )
        for field in (*_LENGTH_FIELDS, "competency_based")
        if old.get(field) != new.get(field)
    ]


def _cost_changes(uuid: str, before: Mapping[str, Any], after: Mapping[str, Any]) -> list[Change]:
    old, new = _section(before, "cost"), _section(after, "cost")
    return [
        Change(
            kind="cost_changed",
            uuid=uuid,
            subject=field,
            before=_number(old.get(field)),
            after=_number(new.get(field)),
        )
        for field in _COST_FIELDS
        if old.get(field) != new.get(field)
    ]


def _derived_changes(
    uuid: str, before: Mapping[str, Any], after: Mapping[str, Any]
) -> list[Change]:
    """Events about this project's own work rather than the source's: the join and the link."""
    changes: list[Change] = []
    old_kind, new_kind = _first_match_kind(before), _first_match_kind(after)
    if old_kind != new_kind:
        changes.append(
            Change(kind="occupation_match_changed", uuid=uuid, before=old_kind, after=new_kind)
        )
    old_verdict, new_verdict = _link_verdict(before), _link_verdict(after)
    if old_verdict != new_verdict:
        changes.append(
            Change(kind="link_verdict_changed", uuid=uuid, before=old_verdict, after=new_verdict)
        )
    return changes


def _compare_one(uuid: str, before: Mapping[str, Any], after: Mapping[str, Any]) -> list[Change]:
    """Every event for a programme present in both datasets."""
    changes: list[Change] = []
    old_title = str(before.get("program_name", ""))
    new_title = str(after.get("program_name", ""))
    if old_title != new_title:
        changes.append(
            Change(kind="program_retitled", uuid=uuid, before=old_title, after=new_title)
        )
    changes += _measure_changes(uuid, before, after)
    changes += _length_changes(uuid, before, after)
    changes += _cost_changes(uuid, before, after)
    changes += _derived_changes(uuid, before, after)
    return changes


def compare(earlier: Dataset, later: Dataset) -> DatasetDiff:
    """Classify every difference between two datasets, keeping the classes apart.

    A programme present on one side only produces exactly one event -- ``program_added`` or
    ``program_removed`` -- and no measure events. Its measures did not stop being reported; the
    programme stopped being listed, which is a different fact about a different thing.
    """
    changes: list[Change] = []

    gone = set(earlier.programs) - set(later.programs)
    arrived = set(later.programs) - set(earlier.programs)
    shared = set(earlier.programs) & set(later.programs)

    for uuid in gone:
        changes.append(
            Change(
                kind="program_removed",
                uuid=uuid,
                before=str(earlier.programs[uuid].get("program_name", "")),
            )
        )
    for uuid in arrived:
        changes.append(
            Change(
                kind="program_added",
                uuid=uuid,
                after=str(later.programs[uuid].get("program_name", "")),
            )
        )
    for uuid in shared:
        changes.extend(_compare_one(uuid, earlier.programs[uuid], later.programs[uuid]))

    for provider in sorted(earlier.providers - later.providers):
        changes.append(Change(kind="provider_gone", uuid="", subject=provider))
    for provider in sorted(later.providers - earlier.providers):
        changes.append(Change(kind="provider_new", uuid="", subject=provider))

    return DatasetDiff(
        earlier=earlier.snapshot_date,
        later=later.snapshot_date,
        earlier_programs=earlier.total_programs,
        later_programs=later.total_programs,
        earlier_occupations=earlier.occupations,
        later_occupations=later.occupations,
        changes=tuple(sorted(changes, key=lambda c: c._order)),
    )


def _row(label: str, count: int) -> str:
    return f"| {label} | {count} |"


def to_markdown(diff: DatasetDiff) -> str:
    """A summary an operator reads before publishing, written only from the statement's counts.

    Every figure here comes out of :meth:`DatasetDiff.counts`. Nothing is recounted from the
    changes a second time, because a summary that recomputes its own numbers can disagree with
    the statement it summarises and there would be no way to tell which one was wrong.
    """
    counts = diff.counts
    by_kind: dict[str, int] = counts["by_kind"]
    lines = [
        f"# What changed between {diff.earlier} and {diff.later}",
        "",
        (
            f"{diff.earlier_programs} programmes on {diff.earlier}, "
            f"{diff.later_programs} on {diff.later}. "
            f"{diff.total} classified "
            f"{'change' if diff.total == 1 else 'changes'}."
        ),
        "",
    ]
    if diff.total == 0:
        lines += [
            (
                "The two datasets were compared and nothing moved. This is not the same as "
                "there being nothing to compare: a dataset that could not be read is a refusal, "
                "never an empty diff."
            ),
            "",
        ]

    lines += ["## Changes by kind", "", "| Kind | Count |", "| --- | --- |"]
    lines += [_row(kind, by_kind[kind]) for kind in KINDS]
    lines += [
        "",
        "## Outcome reporting, by measure",
        "",
        (
            "Counted per measure and never summed. Nine measures moving once each and one "
            "measure moving nine times are different events."
        ),
        "",
        "| Measure | Stopped reporting | Started reporting |",
        "| --- | --- | --- |",
    ]
    by_measure: dict[str, dict[str, int]] = counts["by_measure"]
    for measure in MEASURES:
        row = by_measure[measure]
        lines.append(f"| {measure} | {row['stopped_reporting']} | {row['started_reporting']} |")
    lines += [
        "",
        (
            "A programme that left the list produces `program_removed` and no measure events: "
            "its measures did not stop being reported, it stopped being listed."
        ),
        "",
    ]
    return "\n".join(lines)


def _serialize(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def diff_datasets(earlier_dir: Path, later_dir: Path, output_dir: Path) -> DatasetDiff:
    """Compare two emitted datasets and write the statement and its summary.

    Raises:
        DatasetUnreadable: If either directory cannot be read. Nothing is written in that case,
            so a refusal can never leave behind a statement saying nothing changed.
    """
    earlier = load_dataset(earlier_dir)
    later = load_dataset(later_dir)
    diff = compare(earlier, later)

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / STATEMENT_FILENAME).write_text(_serialize(diff.as_payload()), encoding="utf-8")
    (output_dir / SUMMARY_FILENAME).write_text(to_markdown(diff), encoding="utf-8")
    return diff
