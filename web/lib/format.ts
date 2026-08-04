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

export function percent(value: number | null, lang: Lang): string | null {
  if (value === null) return null;
  // The feed expresses rates as fractions (0.64), but occasionally as whole percentages.
  const fraction = value > 1 ? value / 100 : value;
  return new Intl.NumberFormat(LOCALE[lang], {
    style: "percent",
    maximumFractionDigits: 0,
  }).format(fraction);
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

/** Title-cases the SHOUTING provider names that appear throughout the federal feed. */
export function tidyName(name: string | null): string {
  if (!name) return "";
  if (name !== name.toUpperCase()) return name;
  return name
    .toLowerCase()
    .replace(/\b([a-z])/g, (m) => m.toUpperCase())
    .replace(/\b(Of|And|The|For|In|At|To)\b/g, (m) => m.toLowerCase());
}
