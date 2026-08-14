"""Tests for the independent validation pass over the CTDL export.

The export already checks itself. What this layer adds is a second opinion from a tool that
does not share the export's reading of the schema, plus two disciplines around it that are
easy to state and easy to lose: an accepted finding stays counted and published rather than
filtered away, and an unaccepted one stops the run. Both are pinned here.

The end-to-end tests run the real ctdl-validate over the real committed fixture. That is the
point -- a mocked validator would only ever confirm this project's own opinion of itself.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from afterward.ctdl.export import COVERAGE_FILENAME, GRAPH_FILENAME, export_ctdl
from afterward.ctdl.validate import (
    ACCEPTED_CODES,
    VALIDATION_FILENAME,
    check_validation,
    emitted_terms,
    term_scope,
    validate_export,
    validation_problems,
)

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "data"


def statement(**overrides: Any) -> dict[str, Any]:
    """A clean validation statement, overridable per test."""
    base: dict[str, Any] = {
        "findings": {"ERROR": 0, "WARNING": 3, "INFO": 0, "UNVERIFIABLE": 0},
        "codes": {
            "CTID_NOT_UUIDV4": {
                "severity": "WARNING",
                "count": 3,
                "entities": 3,
                "accepted": True,
                "reason": ACCEPTED_CODES["CTID_NOT_UUIDV4"],
            }
        },
    }
    base.update(overrides)
    return base


@pytest.fixture(scope="module")
def validated_fixture(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The committed fixture, exported and validated once for the whole module.

    Module-scoped because loading the validator's vendored schema encoding is the expensive
    part and it is identical every time.
    """
    export_dir = tmp_path_factory.mktemp("ctdl")
    export_ctdl(FIXTURE_DIR, export_dir)
    validate_export(export_dir)
    return export_dir


class TestAcceptedCodes:
    """An accepted finding is a decision on the record, not a silenced one."""

    def test_every_accepted_code_carries_a_reason(self) -> None:
        for code, reason in ACCEPTED_CODES.items():
            assert len(reason) > 80, f"{code} is accepted without an explanation worth reading"

    def test_the_ctid_acceptance_names_the_tradeoff_it_rests_on(self) -> None:
        # If this reason ever stops mentioning both halves -- what the grammar says, and why
        # this export does something else -- the acceptance has become a suppression.
        reason = ACCEPTED_CODES["CTID_NOT_UUIDV4"]
        assert "UUID v4" in reason
        assert "UUIDv5" in reason
        assert "demonstration" in reason

    def test_an_accepted_finding_is_still_counted(self, validated_fixture: Path) -> None:
        published = json.loads(
            (validated_fixture / VALIDATION_FILENAME).read_text(encoding="utf-8")
        )
        assert published["codes"]["CTID_NOT_UUIDV4"]["count"] > 0
        assert published["findings"]["WARNING"] == published["codes"]["CTID_NOT_UUIDV4"]["count"]


class TestValidationProblems:
    """What stops the build, and what does not."""

    def test_a_clean_statement_has_no_problems(self) -> None:
        assert validation_problems(statement()) == []

    def test_any_error_is_a_problem(self) -> None:
        problems = validation_problems(
            statement(findings={"ERROR": 2, "WARNING": 0, "INFO": 0, "UNVERIFIABLE": 0})
        )
        assert problems == ["2 ERROR finding(s) from ctdl-validate"]

    def test_an_unaccepted_code_is_a_problem_even_at_warning(self) -> None:
        # The failure this guard exists for: a new finding class arriving on a refresh and
        # being read as "still only warnings, same as last time".
        problems = validation_problems(
            statement(
                codes={
                    "REF_OUTSIDE_PAYLOAD": {
                        "severity": "UNVERIFIABLE",
                        "count": 4,
                        "accepted": False,
                    }
                }
            )
        )
        assert len(problems) == 1
        assert "REF_OUTSIDE_PAYLOAD" in problems[0]
        assert "ACCEPTED_CODES" in problems[0]

    def test_check_validation_raises_on_a_problem(self) -> None:
        with pytest.raises(ValueError, match="failed independent validation"):
            check_validation(
                statement(findings={"ERROR": 1, "WARNING": 0, "INFO": 0, "UNVERIFIABLE": 0})
            )

    def test_check_validation_passes_a_clean_statement(self) -> None:
        check_validation(statement())


class TestEmittedTerms:
    """The scope statement describes what was emitted, not what was intended."""

    def test_walks_nested_objects_and_lists(self) -> None:
        document = {
            "@graph": [
                {
                    "@type": "ceterms:LearningProgram",
                    "@id": "https://example.invalid/a",
                    "ceterms:estimatedCost": [
                        {"@type": "ceterms:CostProfile", "ceterms:price": 1.0}
                    ],
                }
            ]
        }
        classes, properties = emitted_terms(document)
        assert classes == ["ceterms:CostProfile", "ceterms:LearningProgram"]
        assert properties == ["ceterms:estimatedCost", "ceterms:price"]

    def test_ignores_json_ld_keywords(self) -> None:
        _, properties = emitted_terms({"@graph": [{"@id": "x", "@type": "ceterms:Credential"}]})
        assert properties == []


class TestValidatorScope:
    """A term the validator cannot judge is not a term that passed."""

    def test_the_qdata_layer_is_reported_as_outside_the_validator_schema(
        self, validated_fixture: Path
    ) -> None:
        # ctdl-validate vendors the core CTDL and CTDL-ASN schema encodings. The QData layer
        # publishes its own at credreg.net/qdata/schema/encoding/json, which neither
        # contains, so the classes this export's outcome statistics use are terms the
        # validator has never heard of. Publishing that is the difference between a clean run
        # and a clean run over the parts somebody checked.
        document = json.loads((validated_fixture / GRAPH_FILENAME).read_text(encoding="utf-8"))
        scope = term_scope(document)
        assert "qdata:DataSetProfile" in scope["classes_not_in_validator_schema"]
        assert "qdata:hasObservation" in scope["properties_not_in_validator_schema"]

    def test_the_core_ctdl_classes_are_reported_as_inside_it(self, validated_fixture: Path) -> None:
        document = json.loads((validated_fixture / GRAPH_FILENAME).read_text(encoding="utf-8"))
        scope = term_scope(document)
        assert "ceterms:LearningProgram" not in scope["classes_not_in_validator_schema"]
        assert scope["classes_in_validator_schema"] > 0

    def test_counts_agree_with_the_lists_beside_them(self, validated_fixture: Path) -> None:
        document = json.loads((validated_fixture / GRAPH_FILENAME).read_text(encoding="utf-8"))
        scope = term_scope(document)
        assert scope["classes_emitted"] - scope["classes_in_validator_schema"] == len(
            scope["classes_not_in_validator_schema"]
        )
        assert scope["properties_emitted"] - scope["properties_in_validator_schema"] == len(
            scope["properties_not_in_validator_schema"]
        )


class TestFixtureValidation:
    """The real validator over the real fixture export."""

    def test_the_fixture_export_produces_no_errors(self, validated_fixture: Path) -> None:
        published = json.loads(
            (validated_fixture / VALIDATION_FILENAME).read_text(encoding="utf-8")
        )
        assert published["findings"]["ERROR"] == 0

    def test_the_only_findings_are_the_documented_ctid_warning(
        self, validated_fixture: Path
    ) -> None:
        published = json.loads(
            (validated_fixture / VALIDATION_FILENAME).read_text(encoding="utf-8")
        )
        assert set(published["codes"]) == {"CTID_NOT_UUIDV4"}

    def test_every_entity_carrying_a_ctid_is_counted_once(self, validated_fixture: Path) -> None:
        # The warning count is not a mystery number: it is exactly the entities that carry a
        # locally derived CTID, which is every entity in the graph.
        document = json.loads((validated_fixture / GRAPH_FILENAME).read_text(encoding="utf-8"))
        published = json.loads(
            (validated_fixture / VALIDATION_FILENAME).read_text(encoding="utf-8")
        )
        with_ctid = [e for e in document["@graph"] if "ceterms:ctid" in e]
        assert published["codes"]["CTID_NOT_UUIDV4"]["entities"] == len(with_ctid)
        assert published["entities_validated"] == len(document["@graph"])

    def test_the_statement_names_the_tool_and_its_version(self, validated_fixture: Path) -> None:
        published = json.loads(
            (validated_fixture / VALIDATION_FILENAME).read_text(encoding="utf-8")
        )
        assert published["tool"]["name"] == "ctdl-validate"
        assert published["tool"]["version"]

    def test_the_statement_claims_nothing_about_a_registry(self, validated_fixture: Path) -> None:
        published = json.loads(
            (validated_fixture / VALIDATION_FILENAME).read_text(encoding="utf-8")
        )
        assert "has been published to the Credential Registry" in published["note"]
        assert published["note"].startswith("Structural validation only")

    def test_the_statement_carries_the_snapshot_it_validated(self, validated_fixture: Path) -> None:
        coverage = json.loads((validated_fixture / COVERAGE_FILENAME).read_text(encoding="utf-8"))
        published = json.loads(
            (validated_fixture / VALIDATION_FILENAME).read_text(encoding="utf-8")
        )
        assert published["snapshot_date"] == coverage["snapshot_date"]

    def test_revalidating_writes_the_same_statement(self, tmp_path: Path) -> None:
        export_ctdl(FIXTURE_DIR, tmp_path)
        validate_export(tmp_path)
        first = (tmp_path / VALIDATION_FILENAME).read_bytes()
        validate_export(tmp_path)
        assert (tmp_path / VALIDATION_FILENAME).read_bytes() == first
