"""The verifier is the only thing between the model and the reader, so every rule is tested
from both directions: a faithful claim passes, and each way a claim can be unfaithful is
withheld with the reason named.

The rules that matter most are the suppression rules, because this portfolio's dominant
defect is absence rendered as a value, and a model is a fluent new way to commit it.
"""

from __future__ import annotations

from afterward.ask.evidence import PEERS_ID, EvidencePack, Fact, Record
from afterward.ask.narrate import Claim, DeclaredNumber, Narration
from afterward.ask.verify import matches, renderings, verify, verify_claim


def _pack() -> EvidencePack:
    pack = EvidencePack(language="en", notes=["12 programs matched; the first 8 are listed"])
    program = Record(
        id="P:a", kind="program", name="CDL 160 Hour", names=["CDL 160 Hour", "Fresno Adult School"]
    )
    program.facts = {
        "cost.total_out_of_pocket": Fact("cost.total_out_of_pocket", 3900.0, "money"),
        "length.weeks": Fact("length.weeks", 5.0, "weeks"),
        "outcomes.total_exited": Fact("outcomes.total_exited", 381.0, "count"),
        "outcomes.completion_rate": Fact("outcomes.completion_rate", 0.97, "rate"),
        "outcomes.employment_rate_q2": Fact(
            "outcomes.employment_rate_q2", None, "rate", suppressed=True
        ),
        "outcomes.median_earnings": Fact(
            "outcomes.median_earnings", None, "money", period="quarter", suppressed=True
        ),
        "outcomes.cohort.attributable": Fact("outcomes.cohort.attributable", True, "flag"),
    }
    reported = Record(id="P:b", kind="program", name="RN", names=["RN"])
    reported.facts = {
        "outcomes.completion_rate": Fact("outcomes.completion_rate", 0.98, "rate"),
        "outcomes.employment_rate_q2": Fact("outcomes.employment_rate_q2", 1.0, "rate"),
        "outcomes.median_earnings": Fact(
            "outcomes.median_earnings", 22953.0, "money", period="quarter"
        ),
        "outcomes.cohort.attributable": Fact("outcomes.cohort.attributable", False, "flag"),
    }
    occupation = Record(id="O:53-3032", kind="occupation", name="Truck Drivers")
    occupation.facts = {
        "period": Fact("period", "2024-2034", "text"),
        "median_annual_wage": Fact("median_annual_wage", 61548.0, "money", period="annual"),
        "percent_change": Fact("percent_change", -15.8, "percent"),
        "total_job_openings": Fact("total_job_openings", 1190.0, "count"),
        "region.period": Fact("region.period", "2023-2033", "text"),
    }
    peers = Record(id=PEERS_ID, kind="peers", name="peers")
    peers.facts = {
        "completion_rate": Fact("completion_rate", 0.85, "rate"),
        "completion_rate.reporting": Fact("completion_rate.reporting", 1951, "count"),
        "median_earnings": Fact("median_earnings", 10900.0, "money", period="quarter"),
        "median_earnings.reporting": Fact("median_earnings.reporting", 1339, "count"),
    }
    for record in (program, reported, occupation, peers):
        pack.records[record.id] = record
    return pack


def claim(
    text: str, *cites: str, kind: str = "data", numbers: list[tuple[str, str, float]] | None = None
) -> Claim:
    return Claim(
        text=text,
        kind=kind,  # type: ignore[arg-type]
        cites=list(cites),
        numbers=[DeclaredNumber(record=r, field=f, value=v) for r, f, v in (numbers or [])],
    )


def reasons(c: Claim) -> list[str]:
    return verify_claim(c, _pack()).reasons


class TestFaithfulClaimsPass:
    def test_declared_numbers_on_cited_records(self) -> None:
        c = claim(
            "The CDL program costs $3,900, runs 5 weeks, and 97% of the 381 who exited completed it.",
            "P:a",
            numbers=[
                ("P:a", "cost.total_out_of_pocket", 3900),
                ("P:a", "length.weeks", 5),
                ("P:a", "outcomes.completion_rate", 0.97),
                ("P:a", "outcomes.total_exited", 381),
            ],
        )
        assert reasons(c) == []

    def test_undeclared_but_published_figures_are_traceable(self) -> None:
        c = claim(
            "Its 97% completion is above the 85% median of the 1,951 programs reporting it.",
            "P:a",
            PEERS_ID,
            numbers=[("PEERS", "completion_rate", 0.85)],
        )
        assert reasons(c) == []

    def test_years_trace_to_the_cited_record_s_period(self) -> None:
        c = claim(
            "The state projects a 15.8% decline over 2024-2034.",
            "O:53-3032",
            numbers=[("O:53-3032", "percent_change", 15.8)],
        )
        assert reasons(c) == []
        c = claim("Regionally, the row covers 2023 to 2033.", "O:53-3032")  # an en dash in the
        # real text is what the claim tokenizer sees; a hyphen would glue the years together
        assert reasons(c) == []

    def test_numbers_in_a_record_s_name_and_in_the_notes_are_allowed(self) -> None:
        assert reasons(claim("CDL 160 Hour is one of 12 programs that matched.", "P:a")) == []

    def test_small_integers_are_enumerations(self) -> None:
        assert reasons(claim("Here are 3 programs; the first 2 reported.", "P:a")) == []

    def test_guidance_without_figures_passes(self) -> None:
        assert reasons(claim("Ask an America's Job Center before deciding.", kind="guidance")) == []

    def test_suppressed_measure_named_as_not_reported_passes(self) -> None:
        c = claim(
            "97% completed. The employment rate two quarters after leaving was not reported.",
            "P:a",
            numbers=[("P:a", "outcomes.completion_rate", 0.97)],
        )
        assert reasons(c) == []

    def test_spanish_not_reported_phrases_pass(self) -> None:
        c = claim("La tasa de empleo no se reportó; los ingresos tampoco se publicaron.", "P:a")
        assert reasons(c) == []


class TestCitations:
    def test_uncited_data_claim(self) -> None:
        assert "uncited" in reasons(claim("Something about a program."))

    def test_unknown_record(self) -> None:
        assert "unknown_record:P:nope" in reasons(claim("x", "P:nope"))

    def test_number_on_uncited_record(self) -> None:
        c = claim("Costs $3,900.", "O:53-3032", numbers=[("P:a", "cost.total_out_of_pocket", 3900)])
        assert "number_on_uncited_record:P:a" in reasons(c)

    def test_unknown_field(self) -> None:
        c = claim("x", "P:a", numbers=[("P:a", "outcomes.magic", 1)])
        assert "unknown_field:P:a.outcomes.magic" in reasons(c)


class TestNumbers:
    def test_mismatch_is_withheld(self) -> None:
        c = claim("Costs $4,900.", "P:a", numbers=[("P:a", "cost.total_out_of_pocket", 4900)])
        assert "number_mismatch:cost.total_out_of_pocket" in reasons(c)

    def test_untraceable_token_is_withheld(self) -> None:
        c = claim("About 27% of programs beat it.", "P:a")
        assert "number_untraceable:27" in reasons(c)

    def test_the_state_benchmark_figures_cannot_be_declared(self) -> None:
        # 27% employed and $16,978.95 are DOL's statewide aggregate, which the pack never carries.
        c = claim(
            "Compared with 27% statewide.",
            "P:a",
            PEERS_ID,
            numbers=[("PEERS", "completion_rate", 0.85)],
        )
        assert "number_untraceable:27" in reasons(c)

    def test_tolerances_by_kind(self) -> None:
        assert matches(Fact("r", 0.97, "rate"), 0.97) and matches(Fact("r", 0.97, "rate"), 97)
        assert not matches(Fact("r", 0.97, "rate"), 0.9)
        assert matches(Fact("m", 61548.0, "money"), 61500) and not matches(
            Fact("m", 61548.0, "money"), 60000
        )
        assert matches(Fact("p", -15.8, "percent"), 16) and matches(
            Fact("p", -15.8, "percent"), -15.8
        )
        assert not matches(Fact("p", -15.8, "percent"), 12)
        assert matches(Fact("c", 1190.0, "count"), 1190) and not matches(
            Fact("c", 1190.0, "count"), 1300
        )
        assert not matches(Fact("t", "text", "text"), 1) and not matches(Fact("f", True, "flag"), 1)

    def test_renderings_cover_rounding_and_percent(self) -> None:
        assert {97, 0.97} <= renderings(Fact("r", 0.97, "rate"))
        assert {61548.0, 61500.0, 62000.0, 61550.0} <= renderings(Fact("m", 61548.0, "money"))
        assert {15.8, 16} <= renderings(Fact("p", -15.8, "percent"))


class TestSuppression:
    """The eval that matters most: a suppressed cell must never read as a value."""

    def test_declaring_a_number_for_a_suppressed_field(self) -> None:
        c = claim("0% were employed.", "P:a", numbers=[("P:a", "outcomes.employment_rate_q2", 0)])
        assert "suppressed_as_value:outcomes.employment_rate_q2" in reasons(c)

    def test_zero_phrases_about_a_suppressed_measure(self) -> None:
        for text in (
            "Nobody was employed after this program.",
            "No one earned anything.",
            "The employment rate was 0%.",
            "Earnings were $0.",
            "Nadie consiguió empleo.",
            "Los ingresos fueron cero.",
        ):
            r = reasons(claim(text, "P:a"))
            assert any(x.startswith("suppressed_as_value") for x in r), text

    def test_mentioning_a_suppressed_measure_without_saying_so(self) -> None:
        c = claim("Graduates were employed at a strong rate.", "P:a")
        assert "suppressed_unlabelled:outcomes.employment_rate_q2" in reasons(c)

    def test_the_absence_of_results_is_not_a_result(self) -> None:
        assert any(
            x.startswith("suppressed_as_value")
            for x in reasons(claim("This program has no results to show for employment.", "P:a"))
        )

    def test_sentence_level_so_one_labelled_sentence_does_not_excuse_another(self) -> None:
        c = claim("Earnings were not reported. Nobody was employed.", "P:a")
        assert "suppressed_as_value:outcomes.employment_rate_q2" in reasons(c)

    def test_annual_pay_of_an_occupation_is_not_the_program_s_earnings(self) -> None:
        c = claim(
            "Truck drivers earn $61,548 a year statewide.",
            "P:a",
            "O:53-3032",
            numbers=[("O:53-3032", "median_annual_wage", 61548)],
        )
        assert reasons(c) == []

    def test_reported_record_is_free_to_state_its_figures(self) -> None:
        c = claim(
            "100% were employed and earned $22,953 in one quarter.",
            "P:b",
            numbers=[
                ("P:b", "outcomes.employment_rate_q2", 1.0),
                ("P:b", "outcomes.median_earnings", 22953),
            ],
        )
        assert reasons(c) == []


class TestPeriods:
    def test_quarterly_earnings_need_a_quarter_label(self) -> None:
        c = claim(
            "Median earnings were $22,953.",
            "P:b",
            numbers=[("P:b", "outcomes.median_earnings", 22953)],
        )
        assert "period_unlabelled:quarter" in reasons(c)

    def test_annual_wage_needs_a_year_label(self) -> None:
        c = claim(
            "Truck drivers make $61,548.",
            "O:53-3032",
            numbers=[("O:53-3032", "median_annual_wage", 61548)],
        )
        assert "period_unlabelled:annual" in reasons(c)

    def test_both_side_by_side_need_both_labels(self) -> None:
        both: list[tuple[str, str, float]] = [
            ("P:b", "outcomes.median_earnings", 22953),
            ("O:53-3032", "median_annual_wage", 61548),
        ]
        c = claim(
            "$22,953 in one quarter against $61,548 a year.", "P:b", "O:53-3032", numbers=both
        )
        assert reasons(c) == []
        c = claim("$22,953 in one quarter against $61,548.", "P:b", "O:53-3032", numbers=both)
        assert "period_unlabelled:annual" in reasons(c)


class TestComparisons:
    def test_peer_comparison_needs_the_peer_figure(self) -> None:
        c = claim("Above the typical program.", "P:a", PEERS_ID)
        assert "comparison_without_peer_figure" in reasons(c)

    def test_peer_comparison_needs_its_basis_stated(self) -> None:
        c = claim(
            "97% against 85%.",
            "P:a",
            PEERS_ID,
            numbers=[("P:a", "outcomes.completion_rate", 0.97), ("PEERS", "completion_rate", 0.85)],
        )
        assert "comparison_basis_unstated" in reasons(c)

    def test_no_comparison_on_a_measure_the_program_did_not_report(self) -> None:
        c = claim(
            "Earnings were not reported, against a $10,900 one-quarter median among 1,339 reporting.",
            "P:a",
            PEERS_ID,
            numbers=[("PEERS", "median_earnings", 10900)],
        )
        assert "comparison_on_unreported:median_earnings" in reasons(c)

    def test_no_comparison_on_a_cohort_that_is_not_the_program_s_own(self) -> None:
        c = claim(
            "98% completed, above the 85% median of 1,951 reporting.",
            "P:b",
            PEERS_ID,
            numbers=[("P:b", "outcomes.completion_rate", 0.98), ("PEERS", "completion_rate", 0.85)],
        )
        assert "comparison_on_unattributable_cohort" in reasons(c)

    def test_no_benchmark_the_site_does_not_use(self) -> None:
        for text in (
            "Above the state average.",
            "Better than most programs.",
            "Por encima del promedio.",
        ):
            assert "benchmark_not_peers" in reasons(claim(text, "P:a")), text


class TestGuidance:
    def test_guidance_with_figures_or_outcome_talk_is_withheld(self) -> None:
        assert "guidance_has_figures" in reasons(
            claim("Ask about the 33% employment rate.", kind="guidance")
        )
        assert "guidance_has_figures" in reasons(
            claim("Ask why earnings are low.", kind="guidance")
        )


class TestVerifyNarration:
    def test_accepted_and_withheld_are_separated_and_counted(self) -> None:
        narration = Narration(
            claims=[
                claim("97% completed.", "P:a", numbers=[("P:a", "outcomes.completion_rate", 0.97)]),
                claim("Nobody was employed.", "P:a"),
                claim("x", "P:zz"),
                claim("Talk to the provider.", kind="guidance"),
            ],
            follow_up_questions=["Which region?"],
        )
        verified = verify(narration, _pack())
        assert [c.text for c in verified.accepted] == ["97% completed.", "Talk to the provider."]
        assert verified.withheld_count == 2 and verified.total == 4
        assert verified.reasons == {"suppressed_as_value": 1, "unknown_record": 1}
        assert verified.follow_up_questions == ["Which region?"]
