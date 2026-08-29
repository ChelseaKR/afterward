"""The two committed CTDL statements must still be what the current code produces.

``web/public/ctdl/ctdl-coverage.json`` and ``web/public/ctdl/ctdl-validation.json`` are
committed artifacts that stand in for a computation. ``/en/ctdl/`` renders every figure on
it from them, and ``tests/test_readme_figures.py`` pins eighteen numbers in the README to
them. They are written by ``make ctdl-statements``, which needs the production dataset,
which is gitignored and which CI cannot build because DOL answers GitHub Actions runners
with 403.

So nothing regenerated them and compared. ``tests/test_readme_figures.py`` said in its own
docstring that checking them against a fresh build was "``make ctdl-export`` and
``scripts/ci_artifact_check.py``'s job"; measured 2026-08-29, ``make ctdl-export`` is in no
``verify`` target and ``ci_artifact_check.py`` mentions neither file. The chain was: README
figures pinned to a statement, statement pinned to nothing. Edit ``export.py`` or
``validate.py``, ship it, and every gate stays green while the published figures describe
an exporter that no longer exists.

What this file does instead: it runs the real exporter and the real validator over the
committed 60-program fixture, into ``tmp_path``, and requires the committed statements to
agree with the result everywhere the answer is decided by code rather than by data.

The comparison, precisely
-------------------------

Every key, every list, every string, and every boolean is compared exactly. Two things are
excluded, and only two:

* **Numbers.** Every count in these statements is a measurement of 3,266 real programs;
  the fixture holds 60. A count cannot agree and must not be made to.
* **``snapshot_date``.** It is read off the dataset, so it names when the data was fetched,
  not what the code does. ``tests/test_readme_figures.py`` already requires the two
  committed statements to name the same snapshot as each other and as the README.

Everything else in both files is code: the notes, the CTDL term names, the per-field
reasons for not projecting a source field, the source-field key lists, the validator's
accepted-code table with its citation and retrieval date, the tool block with the
``ctdl-validate`` version, and the class and property vocabulary the export emits. All of
it is compared byte for byte, which is the point: a reason reworded, a term added, a
version bumped or a field dropped turns this red until the committed statements are
regenerated.

One coupling worth naming: the emitted-vocabulary lists in ``validator_scope`` describe
what the export actually produced, so they depend on the fixture exercising the same CTDL
classes and properties the full corpus does. It does today. If ``make fixture`` ever
produces a fixture that exercises less, this goes red for a data reason rather than a code
one, and the fix is to widen the fixture, never to narrow this.

This runs inside ``make verify`` because ``verify`` runs ``pytest``. It writes only into
``tmp_path``: a gate that regenerates an artifact into the working tree heals the drift it
exists to report, and then reports nothing.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from afterward.ctdl.export import COVERAGE_FILENAME, export_ctdl
from afterward.ctdl.validate import VALIDATION_FILENAME, validate_export

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DATASET = REPO_ROOT / "fixtures" / "data"
COMMITTED = REPO_ROOT / "web" / "public" / "ctdl"
VENDORED_CONTEXT = REPO_ROOT / "src" / "afterward" / "ctdl" / "ctdl-context.json"
CONTEXT_PROVENANCE = REPO_ROOT / "src" / "afterward" / "ctdl" / "ctdl-context.source.json"

NUMBER = "<count: measured, not compared>"
"""What every integer and float is replaced by before the comparison."""

DATASET_DERIVED_KEYS = frozenset({"snapshot_date"})
"""Keys whose value names the dataset rather than the code. See the module docstring."""


def shape(value: Any) -> Any:
    """``value`` with every number blanked and every dataset-derived key dropped.

    ``bool`` is checked before ``int`` deliberately: ``isinstance(True, int)`` is true in
    Python, so a plain number test would blank ``"accepted": true`` and stop noticing if
    the validator ever stopped accepting the one warning code it accepts.
    """
    if isinstance(value, dict):
        return {key: shape(item) for key, item in value.items() if key not in DATASET_DERIVED_KEYS}
    if isinstance(value, list):
        return [shape(item) for item in value]
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return NUMBER
    return value


def rendered(value: Any) -> str:
    """One canonical text for a diff a reader can act on."""
    return json.dumps(shape(value), indent=2, sort_keys=True, ensure_ascii=False)


@pytest.fixture(scope="module")
def regenerated(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Both statements, rebuilt from the committed fixture into a temporary directory.

    Never into the working tree. A regeneration that writes where the committed copy lives
    repairs the drift silently and leaves the gate with nothing to find, which is the exact
    failure this file was written against.
    """
    out = tmp_path_factory.mktemp("ctdl-statements")
    export_ctdl(FIXTURE_DATASET, out)
    validate_export(out)
    return {
        COVERAGE_FILENAME: json.loads((out / COVERAGE_FILENAME).read_text(encoding="utf-8")),
        VALIDATION_FILENAME: json.loads((out / VALIDATION_FILENAME).read_text(encoding="utf-8")),
    }


@pytest.mark.parametrize("name", [COVERAGE_FILENAME, VALIDATION_FILENAME])
def test_the_committed_statement_is_what_the_current_code_writes(
    name: str, regenerated: dict[str, Any]
) -> None:
    committed = json.loads((COMMITTED / name).read_text(encoding="utf-8"))
    assert rendered(committed) == rendered(regenerated[name]), (
        f"web/public/ctdl/{name} is not what the current exporter and validator produce.\n"
        "Everything but the counts and the snapshot date is decided by code, so this is a\n"
        "stale committed artifact, not a data difference. Regenerate it on a machine with\n"
        "the production dataset:\n"
        "    make data && make ctdl-statements\n"
        "and commit the diff. Do not edit the committed statement by hand."
    )


def test_both_committed_statements_are_still_present_and_parse() -> None:
    """A missing file must fail here, not make the comparison above vacuous."""
    for name in (COVERAGE_FILENAME, VALIDATION_FILENAME):
        path = COMMITTED / name
        assert path.is_file(), f"{path} is missing; the /ctdl/ page renders from it"
        assert json.loads(path.read_text(encoding="utf-8")), f"{path} is empty"


def test_the_vendored_ctdl_context_is_the_file_its_provenance_describes() -> None:
    """``ctdl-context.source.json`` records a sha256 that nothing recomputed.

    The vendored context is what ``export.py`` refuses unknown terms against, and the
    recorded hash is the only statement that the vendored bytes are the ones retrieved
    from credreg.net on the recorded date. A hash nobody recomputes is a claim, not a
    check: any edit to the vendored copy would leave the provenance describing a file that
    no longer exists, and the export would keep validating against the edited copy.
    """
    provenance = json.loads(CONTEXT_PROVENANCE.read_text(encoding="utf-8"))
    assert provenance["file"] == VENDORED_CONTEXT.name
    actual = hashlib.sha256(VENDORED_CONTEXT.read_bytes()).hexdigest()
    assert actual == provenance["sha256"], (
        f"{VENDORED_CONTEXT.name} hashes to {actual}, but "
        f"{CONTEXT_PROVENANCE.name} records {provenance['sha256']}. Either the vendored "
        "context was edited, in which case it is no longer the retrieved file and the "
        "edit must be undone, or it was deliberately re-retrieved, in which case "
        "re-record the retrieval date and the new hash together."
    )
