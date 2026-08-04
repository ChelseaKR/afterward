import Link from "next/link";

import { type Copy, type Lang, dict } from "@/lib/i18n";
import type { FundingCitation, FundingQuestion, FundingStep } from "@/lib/types";

/**
 * The localised text for each claim the pipeline publishes, keyed by the claim's stable id.
 *
 * Keyed by id rather than by position, because a step inserted upstream would otherwise
 * silently re-point every translation after it, and keyed on ids rather than on the English so
 * that a comma moving does not orphan a Spanish sentence.
 *
 * A claim with no entry here falls back to the pipeline's English. That is deliberately the
 * weakest of the three possible behaviours to leave in place — dropping the claim would silently
 * withhold something about money from exactly one language, and crashing would take down the
 * export — and it is unreachable in a passing build: a Python test fails when the module
 * publishes a string this file cannot render.
 */
const STEP_COPY: Record<string, (t: Copy) => { heading: string; detail: string }> = {
  ita: (t) => ({ heading: t.fundingHeading, detail: t.fundingIta }),
  where_to_ask: (t) => ({ heading: t.fundingCentersHeading, detail: t.fundingCenters }),
  who_can_be_served: (t) => ({
    heading: t.fundingWhoCanBeServedHeading,
    detail: t.fundingWhoCanBeServed,
  }),
  say_your_priority_status: (t) => ({
    heading: t.fundingPriorityHeading,
    detail: t.fundingPriority,
  }),
  supportive_services: (t) => ({ heading: t.fundingSupportHeading, detail: t.fundingSupport }),
  local_and_annual: (t) => ({ heading: t.fundingLocalHeading, detail: t.fundingLocal }),
};

const QUESTION_COPY: Record<string, (t: Copy) => { ask: string; because: string }> = {
  etpl_now: (t) => ({ ask: t.fundingAskEtplNow, because: t.fundingWhyEtplNow }),
  full_price: (t) => ({ ask: t.fundingAskFullPrice, because: t.fundingWhyFullPrice }),
  credential: (t) => ({ ask: t.fundingAskCredential, because: t.fundingWhyCredential }),
  withdrawal: (t) => ({ ask: t.fundingAskWithdrawal, because: t.fundingWhyWithdrawal }),
  schedule: (t) => ({ ask: t.fundingAskSchedule, because: t.fundingWhySchedule }),
  funding_stream: (t) => ({ ask: t.fundingAskFundingStream, because: t.fundingWhyFundingStream }),
  local_demand: (t) => ({ ask: t.fundingAskLocalDemand, because: t.fundingWhyLocalDemand }),
  ita_cap: (t) => ({ ask: t.fundingAskItaCap, because: t.fundingWhyItaCap }),
  self_sufficiency: (t) => ({
    ask: t.fundingAskSelfSufficiency,
    because: t.fundingWhySelfSufficiency,
  }),
  out_of_area: (t) => ({ ask: t.fundingAskOutOfArea, because: t.fundingWhyOutOfArea }),
  funds_left: (t) => ({ ask: t.fundingAskFundsLeft, because: t.fundingWhyFundsLeft }),
  other_grants_first: (t) => ({
    ask: t.fundingAskOtherGrantsFirst,
    because: t.fundingWhyOtherGrantsFirst,
  }),
  support_costs: (t) => ({ ask: t.fundingAskSupportCosts, because: t.fundingWhySupportCosts }),
  what_to_bring: (t) => ({ ask: t.fundingAskWhatToBring, because: t.fundingWhyWhatToBring }),
};

/** The step whose heading opens the block, so it is not printed twice. */
export const LEAD_STEP = "ita";

/** The step the offices belong under: it is the one that says what an office is. */
export const CENTERS_STEP = "where_to_ask";

export function stepCopy(step: FundingStep, t: Copy): { heading: string; detail: string } {
  return STEP_COPY[step.id]?.(t) ?? { heading: step.heading, detail: step.detail };
}

export function questionCopy(question: FundingQuestion, t: Copy): { ask: string; because: string } {
  return QUESTION_COPY[question.id]?.(t) ?? { ask: question.ask, because: question.because };
}

/**
 * The rules a claim rests on, as links a reader can open.
 *
 * Every claim on this block is about somebody else's money and somebody else's rules, so none of
 * it is published without the citation the pipeline attached to it. The labels are the official
 * titles of federal regulations and state pages, which exist in English only; the note at the
 * foot of the block says so rather than leaving a Spanish reader to wonder.
 */
export function Citations({ citations, label }: { citations: FundingCitation[]; label: string }) {
  if (citations.length === 0) return null;
  return (
    <p className="funding-cite">
      <span className="funding-cite-label">{label}</span>{" "}
      {citations.map((citation, index) => (
        <span key={citation.url}>
          {index > 0 ? " · " : ""}
          <a href={citation.url} rel="nofollow noopener noreferrer" target="_blank">
            {citation.label}
          </a>
        </span>
      ))}
    </p>
  );
}

export function Questions({
  questions,
  heading,
  lang,
}: {
  questions: FundingQuestion[];
  heading: string;
  lang: Lang;
}) {
  const t = dict(lang);
  if (questions.length === 0) return null;

  return (
    <details className="funding-questions">
      <summary>
        {heading} ({questions.length})
      </summary>
      <ol>
        {questions.map((question) => {
          const copy = questionCopy(question, t);
          return (
            <li key={question.id}>
              <p className="funding-ask">
                <strong>{copy.ask}</strong>
              </p>
              <p>{copy.because}</p>
              <Citations citations={question.citations} label={t.fundingRuleLabel} />
            </li>
          );
        })}
      </ol>
    </details>
  );
}
