"""Tests for the CTDL JSON-LD demonstration export.

Two properties matter more than the rest and both are the point of the export existing:
determinism (same dataset, byte-identical output, every time) and honesty (a measure the
source did not report is absent from the CTDL entity -- never zero, never a placeholder --
and no property is emitted on inference). The remainder pins each projection to the CTDL
terms it was verified against.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest

from afterward.ctdl.export import (
    COVERAGE_FILENAME,
    GRAPH_FILENAME,
    MEASURES,
    UNPROJECTED_SOURCE_FIELDS,
    check_ctdl_coverage,
    check_ctdl_terms,
    check_projection,
    ctdl_coverage,
    ctdl_coverage_problems,
    dataset_profile,
    dataset_profile_ctid,
    entity_ctid,
    export_ctdl,
    load_vendored_context,
    organization_ctid,
    program_ctid,
    project_graph,
    project_program,
    projection_problems,
    source_expectations,
    unknown_term_problems,
    unprojected_field_counts,
)

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "data"


def make_payload(**overrides: Any) -> dict[str, Any]:
    """A minimal but shape-complete program payload, overridable per test."""
    payload: dict[str, Any] = {
        "uuid": "11111111-2222-3333-4444-555555555555",
        "provider_name": "Example Adult School",
        "program_name": "Welding Certificate",
        "description": "A welding program.",
        "provider_link": {
            "url": "http://example.edu/welding",
            "href": "https://example.edu/welding",
            "linked": True,
        },
        "soc_codes": ["51-4121"],
        "cost": {"total_out_of_pocket": 4500.0, "total_is_complete": True},
        "outcomes": {
            "median_earnings": 41000.0,
            "credentials_earned": 12.0,
            "employed_q2": 10.0,
            "completion_rate": 0.8,
            "employment_rate_q2": 0.75,
            "reported": True,
        },
        "occupations": [
            {
                "soc_code": "51-4121",
                "title": "Welders, Cutters, Solderers, and Brazers",
                "match": {"kind": "exact"},
            }
        ],
    }
    payload.update(overrides)
    return payload


class TestCtids:
    """CTIDs are derived, deterministic, and never invented."""

    def test_same_identifier_same_ctid(self) -> None:
        assert program_ctid("abc") == program_ctid("abc")

    def test_is_a_ce_prefixed_uuidv5(self) -> None:
        ctid = program_ctid("abc")
        assert ctid.startswith("ce-")
        assert uuid.UUID(ctid.removeprefix("ce-")).version == 5

    def test_kinds_partition_the_namespace(self) -> None:
        # A program and a provider sharing an identifier string must not collide.
        assert program_ctid("abc") != organization_ctid("abc")

    def test_refuses_an_empty_identifier(self) -> None:
        with pytest.raises(ValueError, match="no identifier"):
            entity_ctid("learning-program", "")

    def test_duplicate_program_identity_refuses(self) -> None:
        payloads = [make_payload(), make_payload(program_name="Same uuid, other program")]
        with pytest.raises(ValueError, match="same CTID"):
            project_graph(payloads)


class TestDeterminism:
    """Same input, byte-identical output, twice."""

    def test_two_exports_of_the_fixture_are_byte_identical(self, tmp_path: Path) -> None:
        first = tmp_path / "first"
        second = tmp_path / "second"
        export_ctdl(FIXTURE_DIR, first)
        export_ctdl(FIXTURE_DIR, second)
        for name in (GRAPH_FILENAME, COVERAGE_FILENAME):
            assert (first / name).read_bytes() == (second / name).read_bytes()

    def test_reexport_over_itself_is_idempotent(self, tmp_path: Path) -> None:
        export_ctdl(FIXTURE_DIR, tmp_path)
        before = (tmp_path / GRAPH_FILENAME).read_bytes()
        export_ctdl(FIXTURE_DIR, tmp_path)
        assert (tmp_path / GRAPH_FILENAME).read_bytes() == before

    def test_no_wall_clock_date_in_the_output(self, tmp_path: Path) -> None:
        # The only date the export may carry is the dataset's own snapshot_date; anything
        # else would make two runs on different days differ.
        export_ctdl(FIXTURE_DIR, tmp_path)
        coverage = json.loads((tmp_path / COVERAGE_FILENAME).read_text(encoding="utf-8"))
        fixture_snapshot = json.loads((FIXTURE_DIR / "coverage.json").read_text(encoding="utf-8"))[
            "snapshot_date"
        ]
        assert coverage["snapshot_date"] == fixture_snapshot


class TestProgramProjection:
    """Each property carries exactly what the source asserted, in CTDL's shape."""

    def test_name_and_description_are_language_maps(self) -> None:
        entity = project_program(make_payload())
        assert entity["ceterms:name"] == {"en": "Welding Certificate"}
        assert entity["ceterms:description"] == {"en": "A welding program."}

    def test_subject_webpage_is_the_link_the_site_publishes(self) -> None:
        entity = project_program(make_payload())
        assert entity["ceterms:subjectWebpage"] == "https://example.edu/welding"

    def test_a_link_the_site_withholds_is_withheld_here_too(self) -> None:
        payload = make_payload(
            provider_link={"url": "http://example.edu", "href": None, "linked": False}
        )
        assert "ceterms:subjectWebpage" not in project_program(payload)

    def test_no_filed_url_means_no_webpage_property(self) -> None:
        assert "ceterms:subjectWebpage" not in project_program(make_payload(provider_link=None))

    def test_offered_by_points_at_an_emitted_organization(self) -> None:
        document = project_graph([make_payload()])
        program = next(e for e in document["@graph"] if e["@type"] == "ceterms:LearningProgram")
        organization = next(
            e for e in document["@graph"] if e["@type"] == "ceterms:CredentialOrganization"
        )
        assert program["ceterms:offeredBy"] == [organization["@id"]]
        assert organization["ceterms:name"] == {"en": "Example Adult School"}

    def test_occupation_alignment_carries_the_filed_soc_code(self) -> None:
        alignment = project_program(make_payload())["ceterms:occupationType"][0]
        assert alignment["@type"] == "ceterms:CredentialAlignmentObject"
        assert alignment["ceterms:codedNotation"] == "51-4121"
        assert alignment["ceterms:targetNodeName"] == {
            "en": "Welders, Cutters, Solderers, and Brazers"
        }

    def test_an_aggregate_match_title_never_names_the_filed_code(self) -> None:
        # The joined title names a broader BLS group, not the code the program filed, so
        # the alignment keeps the code and stays silent on the name.
        payload = make_payload(
            occupations=[
                {
                    "soc_code": "51-4120",
                    "title": "Welding Workers, Broad Group",
                    "match": {"kind": "soc_broad_group"},
                }
            ]
        )
        alignment = project_program(payload)["ceterms:occupationType"][0]
        assert alignment["ceterms:codedNotation"] == "51-4121"
        assert "ceterms:targetNodeName" not in alignment

    def test_cost_projects_price_and_currency(self) -> None:
        cost = project_program(make_payload())["ceterms:estimatedCost"][0]
        assert cost["ceterms:price"] == 4500.0
        assert cost["ceterms:currency"] == "USD"

    def test_an_incomplete_total_is_not_published_as_a_price(self) -> None:
        # A suppressed component makes the total a floor, and ceterms:price cannot say
        # "at least", so no cost profile is emitted at all.
        payload = make_payload(cost={"total_out_of_pocket": 900.0, "total_is_complete": False})
        assert "ceterms:estimatedCost" not in project_program(payload)

    def test_a_fractional_headcount_refuses_rather_than_rounds(self) -> None:
        payload = make_payload(outcomes=make_payload()["outcomes"] | {"credentials_earned": 9.5})
        with pytest.raises(ValueError, match="refusing to round"):
            project_program(payload)


def observations_by_slug(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Metric slug -> its Observation, resolved through qdata:isObservationOf."""
    metric_slugs = {
        str(m["@id"]): str(m["@id"]).rsplit("#metric-", 1)[1]
        for m in profile.get("qdata:hasMetric", [])
    }
    return {
        metric_slugs[str(o["qdata:isObservationOf"])]: o
        for o in profile.get("qdata:hasObservation", [])
    }


class TestSuppressionTransfers:
    """The dataset's core honesty rule survives projection: null is absent, never zero."""

    def test_a_suppressed_measure_has_no_metric_and_no_observation(self) -> None:
        payload = make_payload(outcomes=make_payload()["outcomes"] | {"median_earnings": None})
        profile = dataset_profile(payload)
        assert profile is not None
        observed = observations_by_slug(profile)
        assert "median-earnings-q2" not in observed
        # The reported measures still project.
        assert observed["credentials-earned"]["schema:value"] == 12

    def test_fully_suppressed_outcomes_mean_no_dataset_profile_at_all(self) -> None:
        payload = make_payload(
            outcomes={
                "median_earnings": None,
                "credentials_earned": None,
                "employed_q2": None,
                "completion_rate": None,
                "employment_rate_q2": None,
                "reported": False,
            }
        )
        assert dataset_profile(payload) is None
        assert "qdata:relevantDataSet" not in project_program(payload)

    def test_rates_project_as_percentages_of_the_source_fraction(self) -> None:
        profile = dataset_profile(make_payload())
        assert profile is not None
        observed = observations_by_slug(profile)
        assert observed["completion-rate"]["qdata:percentage"] == 80.0
        assert observed["employment-rate-q2"]["qdata:percentage"] == 75.0
        assert observed["median-earnings-q2"]["qdata:median"] == 41000.0
        assert observed["median-earnings-q2"]["schema:currency"] == "USD"

    def test_program_and_profile_link_both_ways(self) -> None:
        payload = make_payload()
        document = project_graph([payload])
        program = next(e for e in document["@graph"] if e["@type"] == "ceterms:LearningProgram")
        profile = next(e for e in document["@graph"] if e["@type"] == "qdata:DataSetProfile")
        assert program["qdata:relevantDataSet"] == [profile["@id"]]
        assert profile["qdata:relevantDataSetFor"] == [program["@id"]]

    def test_projection_guard_catches_a_zero_where_the_source_is_silent(self) -> None:
        payload = make_payload(outcomes=make_payload()["outcomes"] | {"median_earnings": None})
        document = project_graph([payload])
        profile = next(e for e in document["@graph"] if e["@type"] == "qdata:DataSetProfile")
        profile["qdata:hasObservation"].append(
            {
                "@type": "qdata:Observation",
                "qdata:isObservationOf": profile["@id"] + "#metric-median-earnings-q2",
                "qdata:median": 0,
            }
        )
        problems = projection_problems([payload], document)
        assert any("source reports nothing" in p for p in problems)
        with pytest.raises(ValueError, match="diverges from the source"):
            check_projection([payload], document)

    def test_projection_guard_catches_a_dropped_observation(self) -> None:
        payload = make_payload()
        document = project_graph([payload])
        profile = next(e for e in document["@graph"] if e["@type"] == "qdata:DataSetProfile")
        profile["qdata:hasObservation"] = [
            o
            for o in profile["qdata:hasObservation"]
            if not str(o["qdata:isObservationOf"]).endswith("#metric-median-earnings-q2")
        ]
        with pytest.raises(ValueError, match="no observation where the source reports"):
            check_projection([payload], document)

    def test_projection_guard_catches_a_broken_back_link(self) -> None:
        payload = make_payload()
        document = project_graph([payload])
        profile = next(e for e in document["@graph"] if e["@type"] == "qdata:DataSetProfile")
        profile["qdata:relevantDataSetFor"] = ["https://example.org/not-the-program"]
        with pytest.raises(ValueError, match="diverges from the source"):
            check_projection([payload], document)

    def test_fixture_export_carries_no_zero_outcome_value(self, tmp_path: Path) -> None:
        # Mirrors the verified fact about the real dataset: suppression maps to null, so no
        # outcome-derived value in the export is an exact zero.
        export_ctdl(FIXTURE_DIR, tmp_path)
        document = json.loads((tmp_path / GRAPH_FILENAME).read_text(encoding="utf-8"))
        for entity in document["@graph"]:
            if entity.get("@type") != "qdata:DataSetProfile":
                continue
            for observation in entity.get("qdata:hasObservation", []):
                for term in ("schema:value", "qdata:median", "qdata:percentage"):
                    assert observation.get(term) != 0

    def test_fixture_suppressed_earnings_stay_absent(self, tmp_path: Path) -> None:
        # The committed fixture carries programs that report an outcome while earnings are
        # suppressed; each must yield a DataSetProfile without an earnings observation.
        payloads = json.loads((FIXTURE_DIR / "programs.json").read_text(encoding="utf-8"))[
            "programs"
        ]
        suppressed = {
            dataset_profile_ctid(p["uuid"])
            for p in payloads
            if p["outcomes"]["median_earnings"] is None
        }
        assert suppressed, "fixture no longer covers the suppressed-earnings case"
        export_ctdl(FIXTURE_DIR, tmp_path)
        document = json.loads((tmp_path / GRAPH_FILENAME).read_text(encoding="utf-8"))
        for entity in document["@graph"]:
            if entity.get("ceterms:ctid") in suppressed:
                assert "median-earnings-q2" not in observations_by_slug(entity)


class TestTermGuard:
    """Every emitted term must exist in the vendored CTDL context; no term from memory."""

    def test_fixture_export_uses_only_defined_terms(self, tmp_path: Path) -> None:
        export_ctdl(FIXTURE_DIR, tmp_path)
        document = json.loads((tmp_path / GRAPH_FILENAME).read_text(encoding="utf-8"))
        assert unknown_term_problems(document, load_vendored_context()) == []

    def test_an_invented_property_refuses(self) -> None:
        document = project_graph([make_payload()])
        document["@graph"][0]["ceterms:madeUpTerm"] = "x"
        with pytest.raises(ValueError, match="not defined in the CTDL context"):
            check_ctdl_terms(document, load_vendored_context())

    def test_an_unvetted_class_refuses(self) -> None:
        document = project_graph([make_payload()])
        document["@graph"][0]["@type"] = "ceterms:Badge"
        with pytest.raises(ValueError, match="not a class this export vetted"):
            check_ctdl_terms(document, load_vendored_context())


class TestCoverageStatement:
    """The coverage statement is counted from the export and cannot contradict it."""

    def test_written_coverage_matches_the_written_graph(self, tmp_path: Path) -> None:
        export_ctdl(FIXTURE_DIR, tmp_path)
        document = json.loads((tmp_path / GRAPH_FILENAME).read_text(encoding="utf-8"))
        coverage = json.loads((tmp_path / COVERAGE_FILENAME).read_text(encoding="utf-8"))
        payloads = json.loads((FIXTURE_DIR / "programs.json").read_text(encoding="utf-8"))[
            "programs"
        ]
        assert ctdl_coverage_problems(coverage, document, payloads) == []

    def test_a_tampered_count_refuses(self) -> None:
        payloads = [make_payload()]
        document = project_graph(payloads)
        coverage = ctdl_coverage(document, payloads, "2026-08-04")
        coverage["learning_program_properties"]["qdata:relevantDataSet"] += 1
        with pytest.raises(ValueError, match="does not describe the export"):
            check_ctdl_coverage(coverage, document, payloads)

    def test_every_reported_measure_is_counted_as_an_observation(self) -> None:
        payloads = [make_payload()]
        coverage = ctdl_coverage(project_graph(payloads), payloads, "2026-08-04")
        assert coverage["observation_measures"] == {
            "median_earnings": 1,
            "credentials_earned": 1,
            "employed_q2": 1,
            "completion_rate": 1,
            "employment_rate_q2": 1,
        }
        assert coverage["entities"]["qdata:DataSetProfile"] == 1

    def test_a_graph_missing_every_organization_refuses(self) -> None:
        """The check this class is named for could not fail where it actually runs.

        ``export_ctdl`` writes ``coverage = ctdl_coverage(document, payloads, snapshot)`` and
        then hands the same three arguments to ``check_ctdl_coverage``, which calls the same
        pure function again and compares the answer to itself. Measured on the fixture before
        this test existed: delete every ``ceterms:CredentialOrganization``, recount, and the
        statement published ``CredentialOrganization: 0`` beside 60 programs whose
        ``ceterms:offeredBy`` resolved to nothing -- and every guard passed. The recomputation
        is still worth keeping for a statement that arrived from elsewhere; what makes this a
        gate is the second derivation, from the source records, which cannot agree by
        construction.
        """
        payloads = [make_payload(), make_payload(uuid=str(uuid.uuid4()))]
        document = project_graph(payloads)
        document["@graph"] = [
            entity
            for entity in document["@graph"]
            if entity.get("@type") != "ceterms:CredentialOrganization"
        ]
        coverage = ctdl_coverage(document, payloads, "2026-08-04")
        assert coverage["entities"]["ceterms:CredentialOrganization"] == 0
        with pytest.raises(ValueError, match="source records call for"):
            check_ctdl_coverage(coverage, document, payloads)

    def test_an_empty_graph_refuses(self) -> None:
        """The same shape at its limit, and the one a coverage statement makes look tidy:
        every entity count zero, every measure zero, nothing to contradict."""
        payloads = [make_payload()]
        document = project_graph(payloads)
        document["@graph"] = []
        coverage = ctdl_coverage(document, payloads, "2026-08-04")
        with pytest.raises(ValueError, match="source records call for"):
            check_ctdl_coverage(coverage, document, payloads)

    def test_a_missing_statistics_profile_refuses(self) -> None:
        """One program's outcomes dropped out of the graph. The recomputation agrees with
        itself that there are no profiles; the source says there is one to be had."""
        payloads = [make_payload()]
        document = project_graph(payloads)
        document["@graph"] = [
            entity for entity in document["@graph"] if entity.get("@type") != "qdata:DataSetProfile"
        ]
        coverage = ctdl_coverage(document, payloads, "2026-08-04")
        with pytest.raises(ValueError, match="source records call for"):
            check_ctdl_coverage(coverage, document, payloads)

    def test_the_source_expectation_is_read_from_the_records_alone(self) -> None:
        """No graph anywhere in it. That is the whole reason it can disagree with one."""
        payloads = [make_payload(), make_payload(uuid=str(uuid.uuid4()))]
        expected = source_expectations(payloads)
        assert expected["source_programs"] == 2
        assert expected["entities"]["ceterms:LearningProgram"] == 2
        assert expected["entities"]["ceterms:CredentialOrganization"] == 1
        assert expected["entities"]["qdata:DataSetProfile"] == 2

    def test_a_program_reporting_nothing_expects_no_profile(self) -> None:
        """The rule stated in the source's own terms: all measures suppressed means no
        statistics entity, because an empty one would read as "measured, and empty"."""
        silent = make_payload(
            outcomes={
                "median_earnings": None,
                "credentials_earned": None,
                "employed_q2": None,
                "completion_rate": None,
                "employment_rate_q2": None,
            }
        )
        expected = source_expectations([silent])
        assert expected["entities"]["qdata:DataSetProfile"] == 0
        assert set(expected["observation_measures"].values()) == {0}

    def test_the_note_claims_nothing_about_a_registry_holding_these(self, tmp_path: Path) -> None:
        export_ctdl(FIXTURE_DIR, tmp_path)
        coverage = json.loads((tmp_path / COVERAGE_FILENAME).read_text(encoding="utf-8"))
        assert "not published to any registry" in coverage["note"]
        assert "not Registry-assigned" in coverage["note"]


class TestUnprojectedSourceFields:
    """The half of coverage that is about what the projection dropped."""

    def test_every_dropped_field_is_counted_and_explained(self) -> None:
        counts = unprojected_field_counts([make_payload()])
        assert set(counts) == {field.key for field in UNPROJECTED_SOURCE_FIELDS}
        for key, entry in counts.items():
            assert entry["reason"], f"{key} is dropped without a reason"
            assert entry["source_fields"], f"{key} names no source field"

    def test_a_field_the_source_does_not_report_counts_zero(self) -> None:
        # The distinction the block exists to make: a gap nobody hits and a gap on every
        # record must not read the same way.
        counts = unprojected_field_counts([make_payload(cip_code=None)])
        assert counts["instructional_program_code"]["reported_in_source"] == 0

    def test_a_field_the_source_reports_counts_it(self) -> None:
        counts = unprojected_field_counts([make_payload(cip_code="51.0801")])
        assert counts["instructional_program_code"]["reported_in_source"] == 1

    def test_a_group_counts_a_program_reporting_any_of_its_fields(self) -> None:
        payload = make_payload(
            outcomes={
                "total_served": None,
                "total_exited": None,
                "total_completed": None,
                "employed_q4": 7.0,
                "reported": True,
            }
        )
        entry = unprojected_field_counts([payload])["outcome_measures"]
        assert entry["reported_in_source"] == 1
        assert entry["source_fields"]["outcomes.employed_q4"] == 1
        assert entry["source_fields"]["outcomes.total_served"] == 0

    def test_an_empty_value_is_not_a_report(self) -> None:
        # Same rule as everywhere else here: a key present and empty is not a fact.
        counts = unprojected_field_counts([make_payload(occupations=[], location="")])
        assert counts["occupation_projections"]["reported_in_source"] == 0
        assert counts["program_location"]["source_fields"]["location"] == 0

    def test_a_dropped_field_names_the_ctdl_term_that_would_carry_it(self) -> None:
        # The uncomfortable case, and the one worth publishing: the vocabulary has somewhere
        # to put this and the export does not use it.
        counts = unprojected_field_counts([make_payload()])
        assert counts["program_length"]["ctdl_term"] == "ceterms:estimatedDuration"
        assert counts["instructional_program_code"]["ctdl_term"] == (
            "ceterms:instructionalProgramType"
        )

    def test_the_coverage_statement_carries_the_block(self) -> None:
        payloads = [make_payload()]
        coverage = ctdl_coverage(project_graph(payloads), payloads, "2026-08-07")
        assert coverage["not_projected"]["source_fields"] == unprojected_field_counts(payloads)

    def test_a_wrong_dropped_field_count_refuses_to_publish(self) -> None:
        payloads = [make_payload()]
        document = project_graph(payloads)
        coverage = ctdl_coverage(document, payloads, "2026-08-07")
        entry = coverage["not_projected"]["source_fields"]["occupation_projections"]
        assert entry["reported_in_source"] == 1
        entry["reported_in_source"] = 0
        with pytest.raises(ValueError, match="does not describe the export"):
            check_ctdl_coverage(coverage, document, payloads)

    def test_the_five_projected_measures_and_the_four_dropped_ones_are_disjoint(self) -> None:
        # Nine source measures, split with nothing counted twice and nothing lost between
        # the two blocks -- which is the only way the pair can be read as a whole.
        projected = {measure.field for measure in MEASURES}
        dropped = {
            path.removeprefix("outcomes.")
            for field in UNPROJECTED_SOURCE_FIELDS
            if field.key == "outcome_measures"
            for path in field.source_fields
        }
        assert projected & dropped == set()
        assert len(projected) + len(dropped) == 9


class TestFixtureExportShape:
    """The end-to-end export over the committed fixture."""

    def test_every_fixture_program_exports(self, tmp_path: Path) -> None:
        report = export_ctdl(FIXTURE_DIR, tmp_path)
        payloads = json.loads((FIXTURE_DIR / "programs.json").read_text(encoding="utf-8"))[
            "programs"
        ]
        assert report.programs == len(payloads)
        assert report.organizations == len({p["provider_name"] for p in payloads})

    def test_graph_references_the_canonical_context_url(self, tmp_path: Path) -> None:
        export_ctdl(FIXTURE_DIR, tmp_path)
        document = json.loads((tmp_path / GRAPH_FILENAME).read_text(encoding="utf-8"))
        assert document["@context"] == "https://credreg.net/ctdl/schema/context/json"

    def test_no_id_pretends_to_live_in_the_registry(self, tmp_path: Path) -> None:
        export_ctdl(FIXTURE_DIR, tmp_path)
        raw = (tmp_path / GRAPH_FILENAME).read_text(encoding="utf-8")
        assert "credentialengineregistry.org" not in raw
