"""A flat CSV of the emitted dataset, in which no blank ever carries a meaning.

The site's dataset is sharded JSON, which is right for a page that loads one program and wrong
for the reader most likely to check this project's figures: a journalist or a researcher with a
spreadsheet. This module writes that dataset as one table, beside a Frictionless Table Schema
generated from the same column definitions in the same pass, so the two cannot drift.

The whole design is one rule. **Every measure carries a state word beside it, and the state word
is never blank.** A value cell is empty only where the state cell says why it is empty. An empty
cell on its own means nothing, and a reader who does not know that is one `fillna(0)` away from
publishing that a training programme placed nobody in work.

The state vocabulary is three words, and the missing fourth is the interesting one.

``reported``
    A number the source filed, present in the value column beside it.

``not_reported``
    No number. This is the ETP scorecard's ``-1`` and its empty string, which
    :func:`afterward.sources.dol_etp.clean_measure` maps to ``None``.

``competency_based``
    Only on ``length_weeks`` and ``length_hours``, and only from ``length.competency_based``.
    The ETP data dictionary attaches ``-1`` to those two elements and to no others with a
    different meaning: the programme advances on demonstrated competency, so it has no fixed
    length. That is a positive fact about the programme, not missing data, and reporting it as
    missing would report a deliberate design decision as a gap.

**There is deliberately no ``suppressed``**, and issue #110 asked for one. The reason is that this
dataset cannot honestly produce it. WIOA does suppress small-cohort cells, and that suppression is
the reason a great many of these measures are absent -- but the ETP scorecard serves a suppressed
cell and an unreported cell as the same ``-1``, and its own data dictionary describes the sentinel
as "not reported or suppressed" without distinguishing them. By the time a measure reaches the
emitted record, the cause is gone. Writing ``suppressed`` into a cell whose cause is unknown would
be this project's own headline failure mode wearing its opposite face: not an absence published as
a number, but an absence published as a specific, defensible-sounding cause nobody measured.
``not_reported`` is what the dataset knows, so ``not_reported`` is what it says. If the source ever
separates the two, the vocabulary can grow; guessing now would put a claim in a CSV that no line
of this codebase could defend.

Determinism: rows are sorted by ``uuid``, so the same snapshot produces byte-identical output
whatever order the build emitted in.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

__all__ = [
    "COLUMNS",
    "SCHEMA_FILENAME",
    "STATES",
    "TABLE_FILENAME",
    "Column",
    "ExportReport",
    "export_csv",
    "state_column_problems",
    "to_csv",
    "to_table_schema",
]

TABLE_FILENAME: Final = "programs.csv"
SCHEMA_FILENAME: Final = "programs.schema.json"

STATE_SUFFIX: Final = "_state"

REPORTED: Final = "reported"
NOT_REPORTED: Final = "not_reported"
COMPETENCY_BASED: Final = "competency_based"

STATES: Final[tuple[str, ...]] = (REPORTED, NOT_REPORTED, COMPETENCY_BASED)
"""Every word a state column may carry. A reader may check against this and find no sixth."""

FieldKind = Literal["string", "number", "integer", "boolean"]


@dataclass(frozen=True, slots=True)
class Column:
    """One column of the flat table, and how to get its value out of a program record."""

    name: str
    kind: FieldKind
    description: str
    path: tuple[str, ...]
    """Dotted path into the program record, as a tuple of keys."""

    measured: bool = False
    """Whether this column carries a measure, and therefore gets a state column beside it.

    A measure is a number the source may or may not have filed. Identity, location and the
    provider's own text are not measures: a blank provider city is a blank provider city, and
    inventing a state word for it would say that somebody declined to report it.
    """


def _identity(name: str, kind: FieldKind, description: str, *path: str) -> Column:
    return Column(name=name, kind=kind, description=description, path=path)


def _measure(name: str, kind: FieldKind, description: str, *path: str) -> Column:
    return Column(name=name, kind=kind, description=description, path=path, measured=True)


# The table, in column order. Identity first, then the provider's own description of the
# programme, then the three families a reader compares on: cost, length, outcomes. Everything
# derived rather than filed -- the occupation join, the link verdict -- comes last, so that a
# reader scrolling right meets this project's own work only after the source's.
COLUMNS: Final[tuple[Column, ...]] = (
    _identity("uuid", "string", "Stable record id, as filed by the ETP scorecard.", "uuid"),
    _identity("provider_name", "string", "Training provider, as filed.", "provider_name"),
    _identity("program_name", "string", "Programme title, as filed.", "program_name"),
    _identity("entity_type", "string", "Provider's own entity type, as filed.", "entity_type"),
    _identity("cip_code", "string", "CIP code the provider filed for this programme.", "cip_code"),
    _identity(
        "program_format",
        "string",
        "The provider's own sentence about delivery mode, quoted rather than categorised.",
        "program_format",
    ),
    _identity("program_url", "string", "Programme page as filed by the provider.", "program_url"),
    _identity("city", "string", "Programme city.", "location", "city"),
    _identity("state", "string", "Programme state.", "location", "state"),
    _identity("zip", "string", "Programme postal code.", "location", "zip"),
    _identity(
        "area_name",
        "string",
        "EDD projection area this programme was placed in, or empty if it was placed in none.",
        "region",
        "area_name",
    ),
    _identity(
        "area_matched_on",
        "string",
        "How the area was decided. Empty where no area was matched.",
        "region",
        "matched_on",
    ),
    _measure("cost_tuition", "number", "Tuition in dollars, as filed.", "cost", "tuition"),
    _measure("cost_supplies", "number", "Supplies in dollars, as filed.", "cost", "supplies"),
    _measure(
        "cost_total_out_of_pocket",
        "number",
        (
            "Total out-of-pocket cost in dollars. Read this with cost_total_is_complete: where "
            "that is false a component was not reported, so the total is a floor and not a price."
        ),
        "cost",
        "total_out_of_pocket",
    ),
    _identity(
        "cost_total_is_complete",
        "boolean",
        (
            "Whether every component of the total was reported. False makes the total a floor. "
            "Not a measure: it is this project's statement about the cost figures, always known."
        ),
        "cost",
        "total_is_complete",
    ),
    _measure(
        "cost_wioa_funded",
        "number",
        "Cost covered by WIOA funding, in dollars, as filed.",
        "cost",
        "wioa_funded_cost",
    ),
    _measure(
        "length_weeks",
        "number",
        (
            "Programme length in weeks. State competency_based means the programme advances on "
            "demonstrated competency and has no fixed length; it is not missing data."
        ),
        "length",
        "weeks",
    ),
    _measure(
        "length_hours",
        "number",
        "Programme length in instructional hours. See length_weeks on competency_based.",
        "length",
        "hours",
    ),
    _identity(
        "outcomes_reported",
        "boolean",
        (
            "Whether the source filed any outcome data for this programme at all. Where false, "
            "every outcome measure below states not_reported."
        ),
        "outcomes",
        "reported",
    ),
    _measure("total_served", "number", "Participants served.", "outcomes", "total_served"),
    _measure("total_exited", "number", "Participants who exited.", "outcomes", "total_exited"),
    _measure(
        "total_completed", "number", "Participants who completed.", "outcomes", "total_completed"
    ),
    _measure(
        "completion_rate",
        "number",
        "Completion rate, 0 to 1 as filed.",
        "outcomes",
        "completion_rate",
    ),
    _measure(
        "credentials_earned",
        "number",
        "Credentials earned by participants.",
        "outcomes",
        "credentials_earned",
    ),
    _measure(
        "median_earnings",
        "number",
        "Median quarterly earnings after exit, in dollars, as filed.",
        "outcomes",
        "median_earnings",
    ),
    _measure(
        "employment_rate_q2",
        "number",
        "Employment rate in the second quarter after exit, 0 to 1 as filed.",
        "outcomes",
        "employment_rate_q2",
    ),
    _measure(
        "employed_q2",
        "number",
        "Participants employed in the second quarter after exit.",
        "outcomes",
        "employed_q2",
    ),
    _measure(
        "employed_q4",
        "number",
        "Participants employed in the fourth quarter after exit.",
        "outcomes",
        "employed_q4",
    ),
    _identity(
        "soc_codes",
        "string",
        "SOC codes the provider filed, space separated. Empty where the provider filed none.",
        "soc_codes",
    ),
    _identity(
        "occupation_match_kind",
        "string",
        (
            "How this project joined the programme to an occupation, for the first occupation "
            "listed. Empty where no occupation was joined. This project's work, not the source's."
        ),
        "occupations",
        "0",
        "match",
        "kind",
    ),
    _identity(
        "occupation_soc_code",
        "string",
        "SOC code of the first joined occupation. Empty where none was joined.",
        "occupations",
        "0",
        "soc_code",
    ),
    _identity(
        "occupation_title",
        "string",
        "EDD title of the first joined occupation. Empty where none was joined.",
        "occupations",
        "0",
        "title",
    ),
    _identity(
        "provider_link_verdict",
        "string",
        (
            "What this project's link checker found at the filed URL. Empty where no verdict "
            "was reached, which is not the same as a working link."
        ),
        "provider_link",
        "verdict",
    ),
)

_MEASURES: Final[tuple[Column, ...]] = tuple(c for c in COLUMNS if c.measured)
_LENGTH_MEASURES: Final[frozenset[str]] = frozenset({"length_weeks", "length_hours"})


def header() -> list[str]:
    """Column names in order, each measure immediately followed by its state column."""
    names: list[str] = []
    for column in COLUMNS:
        names.append(column.name)
        if column.measured:
            names.append(column.name + STATE_SUFFIX)
    return names


def _at(record: Mapping[str, Any], path: Sequence[str]) -> object:
    """Follow a dotted path, returning ``None`` rather than raising on any break in it.

    A numeric segment indexes a list. A missing key, a short list or a null on the way down all
    return ``None``, which the caller renders as an absence with a state word beside it -- never
    as a zero, and never as a crash that would lose the other 3,000 rows.
    """
    current: object = record
    for key in path:
        if key.isdigit():
            if not isinstance(current, list) or len(current) <= int(key):
                return None
            current = current[int(key)]
            continue
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _render(value: object) -> str:
    """One cell, with no coercion that could invent a number.

    ``None`` becomes the empty string and nothing else does. Booleans are written as ``true`` and
    ``false`` rather than Python's capitalised forms, so the file reads the same as the JSON it
    came from.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (list, tuple)):
        return " ".join(str(item) for item in value)
    return str(value)


def state_of(record: Mapping[str, Any], column: Column) -> str:
    """The state word for one measure in one record. Never empty, and never guessed.

    ``competency_based`` reaches only the two length columns, and only from the record's own
    ``length.competency_based`` flag. Everything else absent is ``not_reported``: see the module
    docstring on why ``suppressed`` is not a word this dataset may write.
    """
    if column.name in _LENGTH_MEASURES:
        length = record.get("length")
        if isinstance(length, Mapping) and length.get("competency_based") is True:
            return COMPETENCY_BASED
    return REPORTED if _at(record, column.path) is not None else NOT_REPORTED


def _row(record: Mapping[str, Any]) -> dict[str, str]:
    row: dict[str, str] = {}
    for column in COLUMNS:
        value = _at(record, column.path)
        row[column.name] = _render(value)
        if column.measured:
            state = state_of(record, column)
            row[column.name + STATE_SUFFIX] = state
            if state != REPORTED:
                # A competency-based programme may still carry a length the source filed by
                # accident; the state is the claim, so the value column is cleared to agree
                # with it rather than leaving two cells that say different things.
                row[column.name] = ""
    return row


def to_csv(programs: Sequence[Mapping[str, Any]]) -> str:
    """The flat table for these programs, sorted by ``uuid`` so the bytes are reproducible."""
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=header(), lineterminator="\n")
    writer.writeheader()
    for record in sorted(programs, key=lambda p: str(p.get("uuid", ""))):
        writer.writerow(_row(record))
    return buffer.getvalue()


def to_table_schema(snapshot_date: str, *, path: str = TABLE_FILENAME) -> dict[str, Any]:
    """A Frictionless Table Schema for exactly the columns :func:`to_csv` writes.

    Generated from :data:`COLUMNS` in the same pass as the table, so a column cannot appear in
    one and not the other. Every state column is constrained to :data:`STATES`, which is how a
    validator, rather than a reader's goodwill, enforces that there is no sixth word.
    """
    fields: list[dict[str, Any]] = []
    for column in COLUMNS:
        fields.append(
            {
                "name": column.name,
                "type": column.kind,
                "description": column.description,
            }
        )
        if column.measured:
            fields.append(
                {
                    "name": column.name + STATE_SUFFIX,
                    "type": "string",
                    "description": (
                        f"How {column.name} is present or absent. Never empty. A blank "
                        f"{column.name} is explained here and nowhere else."
                    ),
                    "constraints": {"required": True, "enum": list(STATES)},
                }
            )
    return {
        "$schema": "https://datapackage.org/profiles/2.0/tableschema.json",
        "name": "programs",
        "title": f"California ETPL programs, snapshot {snapshot_date}",
        "description": (
            "One row per state-listed training programme. Every measure carries a state word "
            "beside it and the state word is never empty; a value cell is empty only where the "
            "state cell says why. The vocabulary is reported, not_reported and competency_based. "
            "There is no 'suppressed': the ETP scorecard serves a suppressed cell and an "
            "unreported cell as the same -1, so the cause is not in this data and this file does "
            "not invent one."
        ),
        "path": path,
        "profile": "tabular-data-resource",
        "fields": fields,
        "missingValues": [""],
    }


def state_column_problems(text: str) -> list[str]:
    """Read a rendered table back and report every way it breaks the one rule.

    Deliberately parses the CSV text rather than inspecting the records it came from. A check
    that re-derives its expectation from the same function that produced the answer compares a
    value to itself and cannot fail; this reads the bytes a downloader would read.
    """
    problems: list[str] = []
    reader = csv.DictReader(io.StringIO(text))
    names = reader.fieldnames or []
    expected = header()
    if names != expected:
        return [f"header is {names}, expected {expected}"]

    state_names = [c.name + STATE_SUFFIX for c in _MEASURES]
    for line, row in enumerate(reader, start=2):
        for column in _MEASURES:
            state = row[column.name + STATE_SUFFIX]
            value = row[column.name]
            if state == "":
                problems.append(f"row {line}: {column.name + STATE_SUFFIX} is empty")
            elif state not in STATES:
                problems.append(f"row {line}: {column.name + STATE_SUFFIX} is {state!r}")
            elif state == REPORTED and value == "":
                problems.append(f"row {line}: {column.name} is blank but states {REPORTED}")
            elif state != REPORTED and value != "":
                problems.append(f"row {line}: {column.name} carries {value!r} but states {state}")
            if state == COMPETENCY_BASED and column.name not in _LENGTH_MEASURES:
                problems.append(
                    f"row {line}: {column.name} states {COMPETENCY_BASED}, which belongs only to "
                    "the two length columns"
                )
    if not state_names:  # pragma: no cover - a table with no measures has no rule to break
        problems.append("the table declares no measure columns, so its one rule checks nothing")
    return problems


def check_states(text: str) -> None:
    """Raise if a rendered table breaks the one rule this module exists to keep."""
    problems = state_column_problems(text)
    if problems:
        shown = "\n  ".join(problems[:20])
        raise ValueError(
            f"the exported table breaks its own absence rule ({len(problems)} problems):\n  {shown}"
        )


@dataclass(frozen=True, slots=True)
class ExportReport:
    """What one export wrote, for the command line to print."""

    snapshot_date: str
    rows: int
    columns: int
    measures: int
    table_path: Path
    schema_path: Path
    states: Mapping[str, int]
    """How many cells reached each state word, across every measure column."""


def export_csv(dataset_dir: Path, output_dir: Path) -> ExportReport:
    """Write the flat table and its Table Schema from the dataset at ``dataset_dir``.

    Reads the same ``programs.json`` the site serves, so the export cannot disagree with the
    site about what the data says. The rule is checked against the rendered bytes before
    anything is written: a failed check leaves no partial file to mistake for a good one.
    """
    dataset = json.loads((dataset_dir / "programs.json").read_text(encoding="utf-8"))
    coverage = json.loads((dataset_dir / "coverage.json").read_text(encoding="utf-8"))
    programs: list[dict[str, Any]] = dataset["programs"]
    snapshot_date = str(coverage["snapshot_date"])

    text = to_csv(programs)
    check_states(text)
    schema = to_table_schema(snapshot_date)

    output_dir.mkdir(parents=True, exist_ok=True)
    table_path = output_dir / TABLE_FILENAME
    schema_path = output_dir / SCHEMA_FILENAME
    table_path.write_text(text, encoding="utf-8", newline="")
    schema_path.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    counts = dict.fromkeys(STATES, 0)
    for record in programs:
        for column in _MEASURES:
            counts[state_of(record, column)] += 1

    return ExportReport(
        snapshot_date=snapshot_date,
        rows=len(programs),
        columns=len(header()),
        measures=len(_MEASURES),
        table_path=table_path,
        schema_path=schema_path,
        states=counts,
    )
