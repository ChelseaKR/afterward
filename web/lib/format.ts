/**
 * Formatting helpers.
 *
 * The single rule everything here exists to protect: a null measure renders as an explicit
 * "not reported", never as 0, "0%", "$0", or an em dash that could be mistaken for a value.
 * WIOA withholds small-cohort cells to protect participant privacy, and showing one as a
 * zero would misstate a real training provider's performance.
 */

import type { Lang } from "./i18n";

const LOCALE: Record<Lang, string> = { en: "en-US", es: "es-US" };

/** Cohorts at or below this size carry a "small group" caution in the UI. */
export const SMALL_SAMPLE_THRESHOLD = 25;

export function money(value: number | null, lang: Lang): string | null {
  if (value === null) return null;
  return new Intl.NumberFormat(LOCALE[lang], {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

/**
 * Format a rate. The value is always a fraction: the pipeline validates that at parse time
 * and refuses anything outside 0..1, so there is no unit-guessing to do here.
 *
 * An earlier version hedged with "if it is above 1, assume whole percentages". That hedge
 * was wrong per-row rather than wholesale — it read 64 as 64% while reading a genuine 1% as
 * 100% and 0.5% as 50%, silently. Checking the unit once, where the data enters, is the only
 * place the question has a real answer.
 */
export function percent(value: number | null, lang: Lang): string | null {
  if (value === null) return null;
  return new Intl.NumberFormat(LOCALE[lang], {
    style: "percent",
    maximumFractionDigits: 0,
  }).format(value);
}

export function signedPercent(value: number | null, lang: Lang): string | null {
  if (value === null) return null;
  return new Intl.NumberFormat(LOCALE[lang], {
    style: "percent",
    maximumFractionDigits: 1,
    signDisplay: "exceptZero",
  }).format(value / 100);
}

export function count(value: number | null, lang: Lang): string | null {
  if (value === null) return null;
  return new Intl.NumberFormat(LOCALE[lang]).format(value);
}

export function isSmallSample(exited: number | null): boolean {
  return exited !== null && exited > 0 && exited <= SMALL_SAMPLE_THRESHOLD;
}

/**
 * How long a program takes, as a phrase, or null when the record genuinely does not say.
 *
 * One function because three places show a program's length -- the result card, the program
 * page's summary strip and the comparison table -- and every one of them turns a null into the
 * site's "Not reported" treatment. Each used to write its own ternary on `weeks === null`, so
 * all three made the same mistake at once for as long as the pipeline handed them a null for a
 * competency-based program: a course whose provider said it finishes when the student can do
 * the work was published as a provider who never answered.
 *
 * The rule therefore lives here, and it is a rule about what null is permitted to mean. Null
 * comes back only for a record that says nothing about length at all. A competency-based
 * program always comes back with words, because there is something to say about it.
 *
 * `competencyBased` is optional and a missing value reads as false, which is all a record built
 * before the field existed can honestly support: it cannot tell the two states apart, so this
 * returns what it returned before the field was added rather than guessing.
 */
export function lengthText(
  weeks: number | null,
  competencyBased: boolean | undefined,
  t: { lengthCompetencyBased: string; weeks: (n: number) => string },
): string | null {
  if (competencyBased === true) return t.lengthCompetencyBased;
  return weeks === null ? null : t.weeks(weeks);
}

/** Title-cases the SHOUTING provider names that appear throughout the federal feed. */
export function tidyName(name: string | null): string {
  if (!name) return "";
  if (name !== name.toUpperCase()) return name;
  return name
    .toLowerCase()
    .replace(/\b([a-z])/g, (m) => m.toUpperCase())
    .replace(/\b(Of|And|The|For|In|At|To)\b/g, (m) => m.toLowerCase());
}
