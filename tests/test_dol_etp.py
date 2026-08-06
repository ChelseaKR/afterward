"""Tests for the DOL ETP client.

The suppression-sentinel behaviour is the highest-stakes logic in this codebase: showing a
suppressed cell as 0% would misrepresent a real training provider's performance.
"""

from __future__ import annotations

import pytest

from afterward.sources.dol_etp import (
    OVERSIZED_COHORT_MIN_PROGRAMS,
    OVERSIZED_COHORT_SERVED,
    CohortFiling,
    Program,
    clean_cip_code,
    clean_description,
    clean_earnings,
    clean_measure,
    clean_rate,
    clean_url,
    cohort_integrity,
    normalise_provider,
    parse_program,
    parse_state_benchmark,
    reconcile_rate,
)


class TestCleanMeasure:
    @pytest.mark.parametrize("value", [-1, -1.0, "-1", "", None])
    def test_not_reported_becomes_none(self, value: object) -> None:
        assert clean_measure(value) is None

    def test_genuine_zero_is_preserved(self) -> None:
        """A reported 0% is a real finding and must survive."""
        assert clean_measure(0) == 0.0
        assert clean_measure("0") == 0.0

    def test_ordinary_values_pass_through(self) -> None:
        assert clean_measure(0.64) == 0.64
        assert clean_measure("10200.01") == 10200.01

    def test_unparseable_becomes_none(self) -> None:
        assert clean_measure("not a number") is None


class TestSocNormalisation:
    def _program(self, **soc: str) -> Program:
        return parse_program({"_id": "x", "_source": {"field_uuid": "u", **soc}})

    def test_eight_digit_codes_truncate_to_standard_six(self) -> None:
        program = self._program(field_program_soc_occ_1="15-125200")
        assert program.soc_codes == ("15-1252",)

    def test_multiple_codes_are_collected_in_order(self) -> None:
        program = self._program(
            field_program_soc_occ_1="15-125200",
            field_program_soc_occ_2="29-114100",
        )
        assert program.soc_codes == ("15-1252", "29-1141")

    def test_blank_and_duplicate_codes_are_dropped(self) -> None:
        program = self._program(
            field_program_soc_occ_1="15-125200",
            field_program_soc_occ_2="",
            field_program_soc_occ_3="15-125200",
        )
        assert program.soc_codes == ("15-1252",)

    def test_malformed_code_is_ignored(self) -> None:
        assert self._program(field_program_soc_occ_1="abc").soc_codes == ()


class TestProgramParsing:
    def test_suppressed_outcomes_do_not_count_as_reported(self) -> None:
        program = parse_program(
            {
                "_source": {
                    "field_uuid": "u",
                    "field_c_median_earnings": -1,
                    "field_c_q2_employment_percent": -1,
                    "field_c_completed_percent": -1,
                }
            }
        )
        assert program.has_outcomes is False
        assert program.median_earnings is None

    def test_any_reported_measure_counts_as_outcomes(self) -> None:
        program = parse_program(
            {"_source": {"field_uuid": "u", "field_c_median_earnings": 10200.0}}
        )
        assert program.has_outcomes is True

    def test_total_cost_with_a_suppressed_component_is_marked_incomplete(self) -> None:
        """The sum is a floor, not a total, and callers must be able to tell."""
        program = parse_program(
            {
                "_source": {
                    "field_uuid": "u",
                    "field_non_wioa_tuition_cost": 5568,
                    "field_non_wioa_supplies_cost": -1,
                }
            }
        )
        assert program.total_cost == 5568.0
        assert program.cost_is_complete is False

    def test_total_cost_with_every_component_reported_is_complete(self) -> None:
        program = parse_program(
            {
                "_source": {
                    "field_uuid": "u",
                    "field_non_wioa_tuition_cost": 5568,
                    "field_non_wioa_supplies_cost": 2450,
                }
            }
        )
        assert program.total_cost == 8018.0
        assert program.cost_is_complete is True

    def test_total_cost_is_none_when_nothing_reported(self) -> None:
        program = parse_program(
            {
                "_source": {
                    "field_uuid": "u",
                    "field_non_wioa_tuition_cost": -1,
                    "field_non_wioa_supplies_cost": "",
                }
            }
        )
        assert program.total_cost is None


class TestStateBenchmark:
    """The statewide aggregate gives a bare program rate something to be read against."""

    def _source(self, **overrides: object) -> dict[str, object]:
        return {
            "field_c_completed_percent": 0.71,
            "field_c_q2_employment_percent": 0.27,
            "field_c_median_earnings": 16978.95,
            "field_c_cred_attainment_percent": 0.37,
            "field_c_total_exited": 664260,
            "field_c_total_completed": 469808,
            **overrides,
        }

    def test_parses_the_published_measures(self) -> None:
        benchmark = parse_state_benchmark("CA", self._source())
        assert benchmark.completion_rate == 0.71
        assert benchmark.q2_employment_rate == 0.27
        assert benchmark.median_earnings == 16978.95
        assert benchmark.total_exited == 664260

    def test_suppressed_state_measures_stay_none(self) -> None:
        benchmark = parse_state_benchmark("CA", self._source(field_c_median_earnings=-1))
        assert benchmark.median_earnings is None

    def test_missing_fields_do_not_raise(self) -> None:
        benchmark = parse_state_benchmark("CA", {})
        assert benchmark.state == "CA"
        assert benchmark.completion_rate is None

    def test_as_dict_uses_the_same_keys_as_program_outcomes(self) -> None:
        """The UI compares these side by side, so the names must line up."""
        payload = parse_state_benchmark("CA", self._source()).as_dict()
        assert payload["employment_rate_q2"] == 0.27
        assert payload["median_earnings"] == 16978.95
        assert payload["state"] == "CA"


class TestCleanUrl:
    """`field_program_url` is free text from third parties and lands in an href."""

    def test_keeps_absolute_http_urls(self) -> None:
        assert clean_url("https://example.org/program") == "https://example.org/program"
        assert clean_url("http://example.org") == "http://example.org"

    def test_repairs_a_bare_domain(self) -> None:
        # Unambiguous, and discarding it would lose a working provider link.
        assert clean_url("www.amanet.org") == "https://www.amanet.org"
        assert clean_url("www.example.com/path/") == "https://www.example.com/path/"

    def test_repairs_a_protocol_relative_url(self) -> None:
        assert clean_url("//example.org/x") == "https://example.org/x"

    def test_drops_text_that_is_not_a_url(self) -> None:
        # Five California records hold a course title where a URL belongs. Rendered raw,
        # these made "Provider's website" navigate to a path inside this site.
        assert clean_url("Data Science Career Track") is None
        assert clean_url("Supply Management") is None

    def test_drops_dangerous_schemes(self) -> None:
        # React does not block javascript: in an href, so this is a script-injection sink.
        for hostile in (
            "javascript:alert(1)",
            "JavaScript:alert(1)",
            "data:text/html;base64,PHNjcmlwdD4=",
            "vbscript:msgbox(1)",
            "file:///etc/passwd",
        ):
            assert clean_url(hostile) is None, hostile

    def test_drops_empty_and_null(self) -> None:
        assert clean_url(None) is None
        assert clean_url("   ") is None


class TestCleanDescription:
    """The feed prefixes its own row id to 3,223 of California's 3,266 descriptions."""

    def test_strips_the_row_id_prefix(self) -> None:
        assert clean_description("6091|Covers understanding user needs.") == (
            "Covers understanding user needs."
        )

    def test_leaves_an_untagged_description_alone(self) -> None:
        # 43 of 3,266 arrive without the artifact and must come through unchanged.
        assert clean_description("A program that focuses on advanced manufacturing.") == (
            "A program that focuses on advanced manufacturing."
        )

    def test_strips_only_the_leading_id(self) -> None:
        # A pipe later in the prose is somebody's punctuation, not a second artifact.
        assert clean_description("6091|Track A|Track B") == "Track A|Track B"

    def test_does_not_eat_a_number_that_is_part_of_the_sentence(self) -> None:
        assert clean_description("120 hours of instruction.") == "120 hours of instruction."

    def test_a_description_that_is_only_an_id_is_not_reported(self) -> None:
        # Stripping to nothing means the field held no description, not an empty one.
        assert clean_description("6091|") is None

    def test_empty_and_null_stay_none(self) -> None:
        assert clean_description(None) is None
        assert clean_description("   ") is None

    def test_the_artifact_never_reaches_a_parsed_program(self) -> None:
        program = parse_program(
            {"_source": {"field_uuid": "u", "field_program_description": "6091|Covers needs."}}
        )
        assert program.description == "Covers needs."

    def test_other_text_fields_are_not_put_through_it(self) -> None:
        """No name field carries the artifact (0 of 3,266 each), so none is stripped.

        A provider legitimately named with a leading number would otherwise lose it.
        """
        program = parse_program(
            {
                "_source": {
                    "field_uuid": "u",
                    "field_etp": "160|Driving Academy",
                    "field_program_name": "101|Intro to Welding",
                }
            }
        )
        assert program.provider_name == "160|Driving Academy"
        assert program.program_name == "101|Intro to Welding"


class TestCleanCipCode:
    """308 of 3,266 CIP codes have been through a float and lost their zero padding."""

    def test_restores_a_lost_leading_zero(self) -> None:
        # There is no CIP series 1, so this can only be 01.0505 (Animal Training).
        assert clean_cip_code("1.0505") == "01.0505"

    def test_restores_a_lost_trailing_zero(self) -> None:
        # A CIP detail is two or four digits, never three: 51.0710 is Medical Office
        # Assistant/Specialist.
        assert clean_cip_code("51.071") == "51.0710"

    def test_restores_both_at_once(self) -> None:
        assert clean_cip_code("9.096") == "09.0960"

    def test_a_well_formed_code_is_untouched(self) -> None:
        assert clean_cip_code("51.0710") == "51.0710"

    def test_a_bare_series_is_left_as_filed(self) -> None:
        """Padding 46 to 46.0000 swaps a series for one member of it. 45 programs file one."""
        assert clean_cip_code("46") == "46"

    def test_a_four_digit_family_is_left_as_filed(self) -> None:
        """12.05 is a width CIP publishes, and 12.0500 is a different, narrower claim."""
        assert clean_cip_code("12.05") == "12.05"

    def test_a_one_digit_series_on_a_family_gains_only_its_zero(self) -> None:
        # 09.09 is the family; padding on to 09.0900 would pick a member of it.
        assert clean_cip_code("9.09") == "09.09"

    def test_a_one_digit_detail_is_left_alone(self) -> None:
        # 51.7 lost trailing zeros to 51.70 and to 51.7000 equally. Neither is chosen here.
        assert clean_cip_code("51.7") == "51.7"

    def test_anything_that_is_not_a_cip_number_passes_through_unchanged(self) -> None:
        assert clean_cip_code("51.0710.1") == "51.0710.1"
        assert clean_cip_code("Welding") == "Welding"

    def test_empty_and_null_stay_none(self) -> None:
        assert clean_cip_code(None) is None
        assert clean_cip_code("  ") is None

    def test_a_parsed_program_carries_the_padded_code(self) -> None:
        program = parse_program({"_source": {"field_uuid": "u", "field_cip_code": "1.0505"}})
        assert program.cip_code == "01.0505"


class TestCleanRate:
    """Rates are fractions. The unit is checked here so nothing downstream has to guess."""

    def test_accepts_a_fraction(self) -> None:
        assert clean_rate(0.64) == 0.64

    def test_accepts_the_boundaries(self) -> None:
        assert clean_rate(0) == 0.0
        assert clean_rate(1) == 1.0

    def test_rejects_a_whole_percentage(self, capsys: pytest.CaptureFixture[str]) -> None:
        # 64 could only mean 64%, but accepting it would mean the reader can no longer trust
        # that 1 means 100% rather than 1%. Refuse and say so.
        assert clean_rate(64, field="completion rate") is None
        assert "outside 0..1" in capsys.readouterr().err

    def test_rejects_a_negative_rate(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert clean_rate(-0.5) is None
        assert "outside 0..1" in capsys.readouterr().err

    def test_suppressed_stays_none_without_a_warning(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # -1 is the ordinary "not reported" sentinel, not a unit problem.
        assert clean_rate(-1) is None
        assert capsys.readouterr().err == ""

    def test_parsed_program_rates_go_through_the_check(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        program = parse_program(
            {
                "_source": {
                    "field_uuid": "u",
                    "field_c_completed_percent": 250,
                    "field_c_q2_employment_percent": 0.7,
                }
            }
        )
        assert program.completed_percent is None
        assert program.q2_employment_percent == 0.7
        assert "outside 0..1" in capsys.readouterr().err


class TestCleanEarnings:
    """A quarter's earnings, not an hourly rate filed in the wrong box."""

    def test_accepts_a_plausible_quarter(self) -> None:
        assert clean_earnings(10787.21) == 10787.21

    def test_rejects_an_hourly_rate(self, capsys: pytest.CaptureFixture[str]) -> None:
        # $16 is a wage per hour. Published as a quarter's earnings beside "Worse than
        # typical", against a named business, it is a defamatory claim from a unit error.
        assert clean_earnings(16.0, context="median earnings") is None
        assert "too small" in capsys.readouterr().err

    def test_keeps_a_genuine_zero(self) -> None:
        # Nobody earning anything is a real and serious finding, not a unit error.
        assert clean_earnings(0) == 0.0

    def test_suppressed_stays_none(self) -> None:
        assert clean_earnings(-1) is None


class TestReconcileRate:
    """DOL rounds to two decimals, so 0.00 means "under 0.5%", not "nobody"."""

    def test_drops_a_zero_the_counts_contradict(self) -> None:
        # 86 people working out of 15,335 is 0.56%, which rounds to 0.00.
        assert reconcile_rate(0.0, 86, 15335) is None

    def test_keeps_a_zero_the_counts_support(self) -> None:
        assert reconcile_rate(0.0, 0, 500) == 0.0

    def test_leaves_a_non_zero_rate_alone(self) -> None:
        assert reconcile_rate(0.64, 320, 500) == 0.64

    def test_leaves_an_unreported_rate_alone(self) -> None:
        assert reconcile_rate(None, 86, 15335) is None

    def test_keeps_a_zero_when_the_counts_are_unknown(self) -> None:
        # Without counts there is nothing to contradict it, so the reported value stands.
        assert reconcile_rate(0.0, None, 15335) == 0.0
        assert reconcile_rate(0.0, 86, None) == 0.0

    def test_parsed_program_drops_the_contradicted_zero(self) -> None:
        program = parse_program(
            {
                "_source": {
                    "field_uuid": "u",
                    "field_c_q2_employment_percent": 0,
                    "field_total_employed_q2": 86,
                    "field_c_total_exited": 15335,
                }
            }
        )
        assert program.q2_employment_percent is None


def _filing(
    provider: str | None,
    served: float | None = None,
    exited: float | None = None,
    completed: float | None = None,
) -> CohortFiling:
    return CohortFiling(
        provider_name=provider,
        total_served=served,
        total_exited=exited,
        total_completed=completed,
    )


class TestSharedCohorts:
    """One filing stamped on many programs is not many facts about many programs.

    College of the Desert files served 8,692 / exited 1,837 / completed 1,618 against eleven
    of its sixteen programs, from an accounting degree to a fire academy. Published as
    eleven independent facts with a verdict attached, it tells a reader that 96% of the
    people who finished an architecture degree there are not working six months later.
    """

    def test_a_cohort_filed_against_several_programs_names_its_siblings(self) -> None:
        verdicts = cohort_integrity([_filing("COD", 8692, 1837, 1618) for _ in range(11)])
        assert [v.shared_with_sibling_programs for v in verdicts] == [10] * 11

    def test_a_shared_cohort_is_not_this_programs_to_be_judged_on(self) -> None:
        verdicts = cohort_integrity([_filing("COD", 8692, 1837, 1618) for _ in range(2)])
        assert [v.attributable for v in verdicts] == [False, False]

    def test_a_cohort_of_its_own_is_attributable_and_names_no_siblings(self) -> None:
        verdicts = cohort_integrity([_filing("COD", 8692, 1837, 1618), _filing("COD", 22, 22, 19)])
        assert verdicts[1].shared_with_sibling_programs is None
        assert verdicts[1].attributable is True

    def test_the_absence_of_siblings_is_null_rather_than_zero(self) -> None:
        # A 0 here would read as a count, and this is not a measurement of anything.
        assert cohort_integrity([_filing("p", 10, 9, 9)])[0].shared_with_sibling_programs is None

    def test_two_providers_filing_the_same_numbers_are_not_sharing_a_cohort(self) -> None:
        verdicts = cohort_integrity([_filing("A", 40, 30, 30), _filing("B", 40, 30, 30)])
        assert all(v.shared_with_sibling_programs is None for v in verdicts)

    def test_a_provider_cannot_evade_the_check_by_shouting(self) -> None:
        verdicts = cohort_integrity(
            [_filing("Procareer Academy", 40, 30, 30), _filing("PROCAREER ACADEMY", 40, 30, 30)]
        )
        assert [v.shared_with_sibling_programs for v in verdicts] == [1, 1]

    def test_programs_reporting_nothing_do_not_all_share_one_cohort(self) -> None:
        """Otherwise the commonest state in this dataset -- silence -- becomes a warning."""
        verdicts = cohort_integrity([_filing("COD") for _ in range(3)])
        assert all(v.shared_with_sibling_programs is None for v in verdicts)
        assert all(v.attributable for v in verdicts)

    def test_a_partly_suppressed_cohort_still_counts_as_shared(self) -> None:
        # Served and exited filed identically, completions withheld on both, is still one
        # population claim made twice.
        verdicts = cohort_integrity([_filing("CCSF", 11, 11, None) for _ in range(3)])
        assert [v.shared_with_sibling_programs for v in verdicts] == [2, 2, 2]

    def test_grouping_keys_on_the_population_not_the_rates(self) -> None:
        """The eleventh College of the Desert row also carries an earnings figure.

        Keying on the whole outcome tuple would call that row unique and publish it as the
        one trustworthy fact in the group, which is exactly backwards.
        """
        verdicts = cohort_integrity([_filing("COD", 8692, 1837, 1618) for _ in range(11)])
        assert all(v.shared_with_sibling_programs == 10 for v in verdicts)

    def test_an_anonymous_filer_is_not_grouped_with_another(self) -> None:
        verdicts = cohort_integrity([_filing(None, 40, 30, 30), _filing(None, 40, 30, 30)])
        assert all(v.shared_with_sibling_programs is None for v in verdicts)


class TestContradictoryCohorts:
    """Two counts from different reporting windows are not one population.

    Lemoore College's Health Science record reads "People enrolled 1,796" directly above
    "Based on 5,214 people". Both numbers are real; the claim that they describe the same
    group of people is the page's, not the provider's.
    """

    def test_more_exiters_than_entrants_is_recorded(self) -> None:
        verdict = cohort_integrity([_filing("Lemoore", 1796, 5214, 1500)])[0]
        assert verdict.exited_exceeds_served is True
        assert verdict.internally_consistent is False

    def test_more_completers_than_entrants_is_recorded(self) -> None:
        verdict = cohort_integrity([_filing("BAVC", 13, 15, 15)])[0]
        assert verdict.completed_exceeds_served is True
        assert verdict.internally_consistent is False

    def test_an_ordinary_record_is_consistent(self) -> None:
        verdict = cohort_integrity([_filing("p", 374, 300, 280)])[0]
        assert verdict.internally_consistent is True

    def test_equal_counts_are_not_a_contradiction(self) -> None:
        # Everyone served exiting and completing is common and entirely possible.
        verdict = cohort_integrity([_filing("p", 69, 69, 69)])[0]
        assert verdict.internally_consistent is True

    def test_a_suppressed_count_cannot_contradict_a_reported_one(self) -> None:
        verdict = cohort_integrity([_filing("p", None, 5214, None)])[0]
        assert verdict.exited_exceeds_served is False
        assert verdict.internally_consistent is True

    def test_a_reported_zero_is_compared_rather_than_treated_as_missing(self) -> None:
        verdict = cohort_integrity([_filing("p", 0, 5, 0)])[0]
        assert verdict.exited_exceeds_served is True

    def test_a_contradiction_alone_does_not_disown_the_figures(self) -> None:
        """The published rates reconcile against completed/exited, so the rate is sound.

        What is wrong is the "people enrolled" label above it, and that is a repair to the
        page rather than a reason to stop comparing the program.
        """
        verdict = cohort_integrity([_filing("Lemoore", 1796, 5214, 1500)])[0]
        assert verdict.attributable is True


class TestOversizedCohorts:
    """A big community college is real. Nine 25,000-person programs at one is not."""

    def test_one_very_large_program_is_left_alone(self) -> None:
        """Project Heartbeat's Basic Life Support renewal really does run at that scale.

        Its next-largest program is 1,043. Suppressing this to make the site tidier would
        be exactly the error this project exists to avoid, in the opposite direction.
        """
        verdicts = cohort_integrity(
            [_filing("Heartbeat", 5896, 5896, 5896), _filing("Heartbeat", 1043, 1043, 1043)]
        )
        assert all(v.oversized_for_one_program is False for v in verdicts)
        assert all(v.attributable for v in verdicts)

    def test_many_very_large_programs_at_one_provider_are_marked(self) -> None:
        verdicts = cohort_integrity(
            [_filing("De Anza", n, n - 10000, n - 15000) for n in (31439, 26359, 25890)]
        )
        assert all(v.oversized_for_one_program for v in verdicts)
        assert not any(v.attributable for v in verdicts)

    def test_only_the_large_rows_at_such_a_provider_are_marked(self) -> None:
        """The rule marks what it can prove about each row, not the provider wholesale."""
        verdicts = cohort_integrity(
            [*(_filing("De Anza", n) for n in (31439, 26359, 25890)), _filing("De Anza", 361)]
        )
        assert verdicts[-1].oversized_for_one_program is False
        assert verdicts[-1].attributable is True

    def test_the_threshold_is_inclusive_at_both_ends(self) -> None:
        verdicts = cohort_integrity(
            [_filing("p", OVERSIZED_COHORT_SERVED)] * OVERSIZED_COHORT_MIN_PROGRAMS
        )
        assert all(v.oversized_for_one_program for v in verdicts)

    def test_one_short_of_the_count_is_not_enough(self) -> None:
        verdicts = cohort_integrity(
            [_filing("p", OVERSIZED_COHORT_SERVED)] * (OVERSIZED_COHORT_MIN_PROGRAMS - 1)
        )
        assert not any(v.oversized_for_one_program for v in verdicts)

    def test_a_cohort_just_under_the_threshold_is_not_counted_toward_it(self) -> None:
        verdicts = cohort_integrity(
            [
                *([_filing("p", OVERSIZED_COHORT_SERVED)] * (OVERSIZED_COHORT_MIN_PROGRAMS - 1)),
                _filing("p", OVERSIZED_COHORT_SERVED - 1),
            ]
        )
        assert not any(v.oversized_for_one_program for v in verdicts)

    def test_a_suppressed_cohort_is_never_oversized(self) -> None:
        verdicts = cohort_integrity([_filing("p", None)] * 5)
        assert not any(v.oversized_for_one_program for v in verdicts)


class TestCohortIntegrityContract:
    def test_a_verdict_is_returned_for_every_filing_in_order(self) -> None:
        filings = [_filing("a", 10), _filing("b", 20), _filing("a", 10)]
        assert len(cohort_integrity(filings)) == len(filings)

    def test_a_lone_filing_asserts_nothing_about_sharing_or_scale(self) -> None:
        verdict = cohort_integrity([_filing("De Anza", 31439, 21209, 14685)])[0]
        assert verdict.shared_with_sibling_programs is None
        assert verdict.oversized_for_one_program is False

    def test_every_key_is_always_written(self) -> None:
        # So "checked and sound" stays distinguishable from "built before the check existed".
        assert set(cohort_integrity([_filing("p")])[0].as_dict()) == {
            "attributable",
            "internally_consistent",
            "shared_with_sibling_programs",
            "exited_exceeds_served",
            "completed_exceeds_served",
            "oversized_for_one_program",
        }

    def test_it_reads_the_same_counts_the_parser_produced(self) -> None:
        program = parse_program(
            {
                "_source": {
                    "field_uuid": "u",
                    "field_etp": "COLLEGE OF THE DESERT",
                    "field_c_total_served": 8692,
                    "field_c_total_exited": 1837,
                    "field_c_total_completed": 1618,
                }
            }
        )
        filing = CohortFiling.of(program)
        assert filing == _filing("COLLEGE OF THE DESERT", 8692.0, 1837.0, 1618.0)

    def test_a_suppression_sentinel_never_reaches_the_check_as_a_count(self) -> None:
        program = parse_program(
            {"_source": {"field_uuid": "u", "field_etp": "p", "field_c_total_served": -1}}
        )
        assert CohortFiling.of(program).total_served is None


class TestNormaliseProvider:
    def test_case_and_whitespace_are_folded(self) -> None:
        assert normalise_provider("  Procareer   Academy ") == normalise_provider(
            "PROCAREER ACADEMY"
        )

    def test_a_missing_name_stays_missing(self) -> None:
        assert normalise_provider(None) is None
        assert normalise_provider("   ") is None

    def test_different_names_are_not_guessed_to_be_one_provider(self) -> None:
        assert normalise_provider("Merced College") != normalise_provider("Merced Adult School")
