"""Check every claim against the evidence pack, and withhold what does not verify.

No model runs here. Each rule is a function of the claim's text, its declared citations and
numbers, and the typed facts in the pack. The rules, in the order they are applied:

- A guidance claim carries no figures and says nothing about outcomes.
- A data claim cites at least one record, and every record it cites is in the pack.
- Every number it declares names a cited record and a field that exists, that is not
  suppressed, and whose published value the declared value matches on its own basis.
- Every numeric token in its text traces to a declared number, to a year, to a small
  enumeration, or to a figure in the pack's own notes or record names.
- No sentence mentions a suppressed measure without saying it is not reported, and no
  sentence about a record with a suppressed measure renders the absence as a zero or a
  nobody.
- A quarterly earnings figure is labelled as a quarter; an annual wage is labelled as a year.
- A comparison cites PEERS, declares the peer figure, says what the peer figure is, and is
  not made against a value the program did not report or a cohort that is not its own.
- No benchmark the site does not use.

A claim that fails any rule is withheld whole. The verdict carries the reason codes, and the
service publishes the count. Nothing is repaired: a corrected number would be a number the
model did not say and the dataset did not publish in that sentence.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

from afterward.ask.evidence import ANNUAL, PEERS_ID, QUARTER, EvidencePack, Fact, Record
from afterward.ask.narrate import Claim, DeclaredNumber, Narration

NOT_REPORTED = re.compile(
    r"not reported|not published|withheld|suppressed|no data|not available|isn't available|"
    r"did not report|didn't report|no figure|no reportad|no se report|no se public|"
    r"se omiti|omitid|retenid|suprimid|no disponible|no hay dato|sin dato|no publicad|"
    r"no inform|tampoco se (report|public|inform)|no fue(ron)? reportad|sin reportar",
    re.I,
)

ZERO_PHRASE = re.compile(
    r"(?<![\d.,])0\s?%|\$\s?0(?![\d,]|\.\d)|\bzero\b|\bno one\b|\bnobody\b|\bnone of\b|"
    r"\bnadie\b|\bningun[oa]s?\b|\bcero\b|\b0 percent\b|\bno results\b|\bsin resultados\b",
    re.I,
)

BENCHMARK_NOT_PEERS = re.compile(
    r"\baverage\b|\bpromedio\b|\bmost programs\b|\bla mayor[ií]a de los programas\b|"
    r"\bstatewide (rate|figure|benchmark)\b|\bstate benchmark\b|\bnational(ly)?\b",
    re.I,
)

PEERS_BASIS = re.compile(r"report|inform", re.I)
QUARTER_LABEL = re.compile(r"quarter|trimestre|three months|3 months|tres meses|3 meses", re.I)
ANNUAL_LABEL = re.compile(r"\byear|annual|anual|al a[nñ]o|por a[nñ]o|yearly|anuales", re.I)

SENTENCE_SPLIT = re.compile(r"(?<=[.;!?])\s+|\n+")
NUMBER_TOKEN = re.compile(r"(?<![\w-])\d[\d,]*(?:\.\d+)?(?![\w-])")
SOC_CODE = re.compile(r"\b\d{2}-\d{4}\b")

ALLOWED_SMALL = frozenset(range(0, 21))
"""0..20: enumerations ("the first three"), ages, months. A bare 0 is caught by the
suppression rules when it is about a measure; as an enumeration it is harmless. Years are
not on this list: a year must come from a cited record's own period, because a regional row
and a statewide row carry different periods and the model has confused them."""

MEASURE_KEYWORDS: dict[str, re.Pattern[str]] = {
    "outcomes.completion_rate": re.compile(r"complet|finish|graduat|termin|finaliz|conclu", re.I),
    "outcomes.employment_rate_q2": re.compile(r"employ|working|emple|trabaj|colocad", re.I),
    "outcomes.median_earnings": re.compile(r"\bearn|ingreso|ganan|ganar|ganaba", re.I),
    "outcomes.total_served": re.compile(r"enroll|served|inscri|atendi", re.I),
    "outcomes.total_exited": re.compile(r"exit|left the program|salieron|egres", re.I),
    "outcomes.total_completed": re.compile(r"\bcompleted\b|completaron|terminaron", re.I),
    "outcomes.credentials_earned": re.compile(r"credential|credencial", re.I),
    "cost.total_out_of_pocket": re.compile(
        r"\bcost|tuition|price|cuest|costo|matr[ií]cula|precio", re.I
    ),
    "length.weeks": re.compile(r"\bweek|\blong\b|duration|semana|dura", re.I),
    "length.hours": re.compile(r"\bhour|\bhora", re.I),
    "median_annual_wage": re.compile(r"wage|\bpay|salar|pago|sueldo", re.I),
    "region.median_annual_wage": re.compile(r"wage|\bpay|salar|pago|sueldo", re.I),
    "total_job_openings": re.compile(r"opening|vacan|puesto", re.I),
    "region.total_job_openings": re.compile(r"opening|vacan|puesto", re.I),
    "percent_change": re.compile(
        r"grow|shrink|declin|expand|crec|disminu|reduc|change|cambio", re.I
    ),
    "region.percent_change": re.compile(
        r"grow|shrink|declin|expand|crec|disminu|reduc|change|cambio", re.I
    ),
}
"""Which words in a sentence mean it is talking about this measure. Used only for suppressed
measures, where the question is whether the sentence said "not reported"."""

OUTCOME_WORDS = re.compile(
    r"complet|employ|earn|wage|salar|cost|tuition|opening|grow|shrink|percent|rate|"
    r"emple|ingreso|salario|costo|vacan|crec|disminu|tasa|\d",
    re.I,
)
"""A guidance claim may not contain any of these. Guidance is about what to do next."""


@dataclass
class Verdict:
    claim: Claim
    accepted: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class Verified:
    accepted: list[Claim]
    withheld: list[Verdict]
    reasons: Counter[str]
    follow_up_questions: list[str]

    @property
    def withheld_count(self) -> int:
        return len(self.withheld)

    @property
    def total(self) -> int:
        return len(self.accepted) + len(self.withheld)


def verify(narration: Narration, pack: EvidencePack) -> Verified:
    accepted: list[Claim] = []
    withheld: list[Verdict] = []
    reasons: Counter[str] = Counter()
    for claim in narration.claims:
        verdict = verify_claim(claim, pack)
        if verdict.accepted:
            accepted.append(claim)
        else:
            withheld.append(verdict)
            reasons.update(_code(r) for r in verdict.reasons)
    return Verified(accepted, withheld, reasons, list(narration.follow_up_questions))


def _code(reason: str) -> str:
    return reason.split(":", 1)[0]


def verify_claim(claim: Claim, pack: EvidencePack) -> Verdict:
    reasons: list[str] = []
    if claim.kind == "guidance":
        if OUTCOME_WORDS.search(claim.text):
            reasons.append("guidance_has_figures")
        return Verdict(claim, not reasons, reasons)

    cited = _cited_records(claim, pack, reasons)
    verified_numbers = _check_numbers(claim, cited, reasons)
    _check_tokens(claim, cited, verified_numbers, pack, reasons)
    _check_suppression(claim, cited, reasons)
    _check_periods(claim, verified_numbers, reasons)
    _check_comparison(claim, cited, verified_numbers, reasons)
    if BENCHMARK_NOT_PEERS.search(claim.text):
        reasons.append("benchmark_not_peers")
    return Verdict(claim, not reasons, reasons)


def _cited_records(claim: Claim, pack: EvidencePack, reasons: list[str]) -> dict[str, Record]:
    if not claim.cites:
        reasons.append("uncited")
    cited: dict[str, Record] = {}
    for record_id in claim.cites:
        record = pack.record(record_id)
        if record is None:
            reasons.append(f"unknown_record:{record_id}")
        else:
            cited[record_id] = record
    return cited


def _check_numbers(
    claim: Claim, cited: dict[str, Record], reasons: list[str]
) -> list[tuple[DeclaredNumber, Fact]]:
    verified: list[tuple[DeclaredNumber, Fact]] = []
    for number in claim.numbers:
        record = cited.get(number.record)
        if record is None:
            reasons.append(f"number_on_uncited_record:{number.record}")
            continue
        fact = record.fact(number.field)
        if fact is None:
            reasons.append(f"unknown_field:{number.record}.{number.field}")
            continue
        if fact.value is None:
            reasons.append(f"suppressed_as_value:{number.field}")
            continue
        if not matches(fact, number.value):
            reasons.append(f"number_mismatch:{number.field}")
            continue
        verified.append((number, fact))
    return verified


def matches(fact: Fact, declared: float) -> bool:
    """Whether a declared value is the published value, on the published basis."""
    if not isinstance(fact.value, int | float) or isinstance(fact.value, bool):
        return False
    v = float(fact.value)
    if fact.kind == "rate":
        return abs(declared - v) <= 0.005 or abs(declared - v * 100) <= 0.5
    if fact.kind == "money":
        return abs(declared - v) <= max(1.0, 0.005 * abs(v))
    if fact.kind == "percent":
        return abs(abs(declared) - abs(v)) <= 0.5
    return abs(declared - v) <= max(0.5, 0.01 * abs(v))


def _check_tokens(
    claim: Claim,
    cited: dict[str, Record],
    verified: Iterable[tuple[DeclaredNumber, Fact]],
    pack: EvidencePack,
    reasons: list[str],
) -> None:
    allowed = set[float]()
    for _, fact in verified:
        allowed.update(renderings(fact))
    for record in cited.values():
        allowed.update(_published_figures(record))
    for note in pack.notes:
        allowed.update(_digits(note))
    for token in _tokens(SOC_CODE.sub(" ", claim.text)):
        if token in ALLOWED_SMALL:
            continue
        if not any(abs(token - a) < 1e-6 for a in allowed):
            reasons.append(f"number_untraceable:{token:g}")


def _published_figures(record: Record) -> set[float]:
    """Every figure a cited record publishes, declared or not.

    The count a peer median rests on, the other program's cost, the two halves of a period
    like ``2023-2033``: a number the record itself carries is traceable. A declared number
    is checked against its field; an undeclared one is allowed only if the record has it.
    """
    out: set[float] = set()
    for fact in record.facts.values():
        if fact.kind == "text" and isinstance(fact.value, str):
            out.update(_digits(fact.value))
        elif fact.value is not None and not isinstance(fact.value, bool | str):
            out.update(renderings(fact))
    for name in record.names:
        out.update(_digits(name))
    return out


def renderings(fact: Fact) -> set[float]:
    """Every way a verified figure may appear in text: rounded, as a percent, to the hundred."""
    v = float(fact.value)
    out = {v, round(v), round(v, 1), round(v, 2)}
    if fact.kind == "rate":
        out.update({v * 100, round(v * 100), round(v * 100, 1)})
    if fact.kind == "percent":
        out.update({abs(v), round(abs(v)), round(abs(v), 1)})
    if fact.kind in {"money", "count"} and abs(v) >= 1000:
        out.update({round(v, -2), round(v, -3)})
    if fact.kind in {"money", "count"} and abs(v) >= 100:
        out.add(round(v, -1))
    return out


def _tokens(text: str) -> set[float]:
    return _floats(NUMBER_TOKEN.findall(text))


def _digits(text: str) -> set[float]:
    """Every number in a record's own text, including the two halves of "2023-2033"."""
    return _floats(re.findall(r"\d[\d,]*(?:\.\d+)?", text))


def _floats(raw: Iterable[str]) -> set[float]:
    out: set[float] = set()
    for item in raw:
        try:
            out.add(float(item.replace(",", "")))
        except ValueError:
            continue
    return out


def _check_suppression(claim: Claim, cited: dict[str, Record], reasons: list[str]) -> None:
    sentences = [s for s in SENTENCE_SPLIT.split(claim.text) if s.strip()]
    for record in cited.values():
        suppressed = record.suppressed_fields()
        if not suppressed:
            continue
        for sentence in sentences:
            _check_sentence(sentence, suppressed, reasons)


def _check_sentence(sentence: str, suppressed: list[str], reasons: list[str]) -> None:
    says_not_reported = bool(NOT_REPORTED.search(sentence))
    about_annual_pay = bool(ANNUAL_LABEL.search(sentence)) and not QUARTER_LABEL.search(sentence)
    for field_name in suppressed:
        pattern = MEASURE_KEYWORDS.get(field_name)
        if pattern is None or not pattern.search(sentence):
            continue
        if field_name == "outcomes.median_earnings" and about_annual_pay:
            # "earn $40,358 a year" is the occupation's annual wage, not the program's
            # quarterly earnings; the period label is what tells them apart.
            continue
        if ZERO_PHRASE.search(sentence):
            reasons.append(f"suppressed_as_value:{field_name}")
        elif not says_not_reported:
            reasons.append(f"suppressed_unlabelled:{field_name}")


def _check_periods(
    claim: Claim, verified: Iterable[tuple[DeclaredNumber, Fact]], reasons: list[str]
) -> None:
    periods = {fact.period for _, fact in verified if fact.period}
    if QUARTER in periods and not QUARTER_LABEL.search(claim.text):
        reasons.append("period_unlabelled:quarter")
    if ANNUAL in periods and not ANNUAL_LABEL.search(claim.text):
        reasons.append("period_unlabelled:annual")


def _check_comparison(
    claim: Claim,
    cited: dict[str, Record],
    verified: Iterable[tuple[DeclaredNumber, Fact]],
    reasons: list[str],
) -> None:
    if PEERS_ID not in cited:
        return
    peer_fields = [n.field for n, _ in verified if n.record == PEERS_ID]
    if not peer_fields:
        reasons.append("comparison_without_peer_figure")
        return
    if not PEERS_BASIS.search(claim.text):
        reasons.append("comparison_basis_unstated")
    for record in cited.values():
        if record.kind != "program":
            continue
        own = record.fact("outcomes.cohort.attributable")
        if own is not None and own.value is False:
            reasons.append("comparison_on_unattributable_cohort")
        for measure in peer_fields:
            fact = record.fact(f"outcomes.{measure}")
            if fact is not None and fact.suppressed:
                reasons.append(f"comparison_on_unreported:{measure}")
