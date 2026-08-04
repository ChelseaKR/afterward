/**
 * Grouping and ordering for the two browse indexes.
 *
 * The index pages are server-rendered into static HTML, so there is no client-side sorting
 * to fall back on: whatever order this module produces is the order a visitor gets. That
 * makes the ordering an editorial decision rather than an implementation detail, and it is
 * made here, once, where it can be tested.
 *
 * The rule the whole file exists to hold: a null measure is the absence of a number, not a
 * small one. Nothing here compares a null against a real value, substitutes a zero for one,
 * or lets one sort as though it were the worst result. Unknown always trails known.
 */

import type { Provider } from "./providers";
import type { SearchEntry } from "./types";

/**
 * Outlook bands for the occupation index.
 *
 * Four, not three. "Steady" and "unknown" look the same in a naive implementation — both
 * fail a `> 0` test — but they are opposite claims: one says California projects the same
 * number of these jobs in ten years, the other says California published no projection at
 * all. Collapsing them would put a statement on screen the data does not make.
 */
export type OutlookBand = "shrinking" | "steady" | "growing" | "unknown";

/**
 * Section order on the page. Shrinking first, deliberately: the occupations California
 * expects less of are the hardest thing to find anywhere else and the clearest reason this
 * dataset is worth publishing. Burying them under 486 growing occupations would be a
 * choice too, just a quieter one.
 */
export const OUTLOOK_ORDER: readonly OutlookBand[] = [
  "shrinking",
  "steady",
  "growing",
  "unknown",
] as const;

export function outlookBand(percentChange: number | null): OutlookBand {
  if (percentChange === null) return "unknown";
  if (percentChange < 0) return "shrinking";
  if (percentChange > 0) return "growing";
  return "steady";
}

/**
 * Descending numeric comparator that sends unknown values last in every case.
 *
 * Not `(b ?? 0) - (a ?? 0)`: that treats "not reported" as the smallest possible value,
 * which is a claim about the occupation rather than about the data. Here a null simply
 * loses to any real number, in either direction of comparison.
 */
export function descendingUnknownLast(a: number | null, b: number | null): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return b - a;
}

/** One row of the occupation index, flattened from the full occupation record. */
export interface OccupationRow {
  soc: string;
  title: string | null;
  openings: number | null;
  wage: number | null;
  change: number | null;
  education: string | null;
  /** Programs in this dataset that train for the occupation. A real count, never a measure. */
  programs: number;
}

export interface OccupationBand {
  band: OutlookBand;
  rows: OccupationRow[];
}

function compareOccupations(a: OccupationRow, b: OccupationRow): number {
  const byOpenings = descendingUnknownLast(a.openings, b.openings);
  if (byOpenings !== 0) return byOpenings;
  const titleA = a.title === null ? "" : a.title;
  const titleB = b.title === null ? "" : b.title;
  return titleA.localeCompare(titleB);
}

/**
 * Split occupations into outlook bands, each ordered by projected openings.
 *
 * Empty bands are dropped rather than rendered as an empty table with a heading promising
 * rows that are not there.
 */
export function groupOccupations(rows: readonly OccupationRow[]): OccupationBand[] {
  const buckets: Record<OutlookBand, OccupationRow[]> = {
    shrinking: [],
    steady: [],
    growing: [],
    unknown: [],
  };

  for (const row of rows) buckets[outlookBand(row.change)].push(row);

  return OUTLOOK_ORDER.map((band) => ({ band, rows: buckets[band].sort(compareOccupations) })).filter(
    (group) => group.rows.length > 0,
  );
}

export interface OccupationTally {
  total: number;
  shrinking: number;
  steady: number;
  growing: number;
  unknown: number;
}

export function summariseOccupations(rows: readonly OccupationRow[]): OccupationTally {
  const tally: OccupationTally = { total: rows.length, shrinking: 0, steady: 0, growing: 0, unknown: 0 };
  for (const row of rows) tally[outlookBand(row.change)] += 1;
  return tally;
}

/**
 * How many programs train for each SOC code.
 *
 * Built once from the search index rather than by filtering it per occupation, which would
 * be 670 passes over 3,300 rows during the static export.
 */
export function programCountsBySoc(programs: readonly SearchEntry[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const program of programs) {
    // A program may list the same SOC twice across its occupation records; count it once.
    for (const soc of new Set(program.s)) {
      const seen = counts.get(soc);
      counts.set(soc, seen === undefined ? 1 : seen + 1);
    }
  }
  return counts;
}

/**
 * Programs held for one occupation.
 *
 * This is the one number on either index page where zero is the truth rather than a missing
 * measure: it counts rows this dataset actually holds, so "no entry" genuinely means none.
 * It is kept in its own function so that reading is explicit and cannot be mistaken for the
 * `?? 0` fallback that would be wrong everywhere else.
 */
export function programCount(counts: ReadonlyMap<string, number>, soc: string): number {
  const found = counts.get(soc);
  return found === undefined ? 0 : found;
}

/** Bucket for provider names that do not start with a Latin letter. */
export const OTHER_LETTER = "#";

/**
 * Index letter for a provider name.
 *
 * Accents are folded so "Ávila" files under A rather than in the leftovers bucket, and
 * leading punctuation is skipped so a name in quotation marks is not stranded either. Names
 * that genuinely begin with a digit or symbol get their own section at the end.
 */
export function providerLetter(name: string): string {
  const first = name
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, "")
    .charAt(0);
  return first >= "A" && first <= "Z" ? first : OTHER_LETTER;
}

/** One row of the provider index. */
export interface ProviderRow {
  slug: string;
  name: string;
  cities: string[];
  programs: number;
  /** Programs with at least one reported outcome. Zero means the provider published nothing. */
  reporting: number;
}

export function toProviderRow(provider: Provider): ProviderRow {
  return {
    slug: provider.slug,
    name: provider.name,
    cities: provider.cities,
    programs: provider.programs.length,
    // `r` is a boolean the pipeline always sets, so this is a count of known facts. A zero
    // here is not a suppressed measure: it means every one of this provider's programs
    // reported nothing, which is exactly what a prospective student should be able to see.
    reporting: provider.programs.filter((program) => program.r).length,
  };
}

export interface ProviderGroup {
  letter: string;
  providers: ProviderRow[];
}

/**
 * Group providers into A–Z sections.
 *
 * Alphabetical, unlike the occupation index, because the task here is different: nobody
 * browses 580 training providers looking for the interesting one, they arrive knowing the
 * name of the school they were about to enrol in. The substance goes in the columns.
 */
export function groupProvidersByLetter(providers: readonly ProviderRow[]): ProviderGroup[] {
  const byLetter = new Map<string, ProviderRow[]>();

  for (const provider of providers) {
    const letter = providerLetter(provider.name);
    const bucket = byLetter.get(letter);
    if (bucket) bucket.push(provider);
    else byLetter.set(letter, [provider]);
  }

  const rank = (letter: string): number => (letter === OTHER_LETTER ? 1 : 0);

  return [...byLetter.entries()]
    .map(([letter, rows]) => ({
      letter,
      providers: rows.sort((a, b) => a.name.localeCompare(b.name)),
    }))
    .sort((a, b) => rank(a.letter) - rank(b.letter) || a.letter.localeCompare(b.letter));
}

export interface ProviderTally {
  providers: number;
  programs: number;
  reportingSome: number;
}

export function summariseProviders(rows: readonly ProviderRow[]): ProviderTally {
  let programs = 0;
  let reportingSome = 0;
  for (const row of rows) {
    programs += row.programs;
    if (row.reporting > 0) reportingSome += 1;
  }
  return { providers: rows.length, programs, reportingSome };
}

/** How many cities to name in a table cell before summarising the rest. */
export const CITY_PREVIEW = 3;

/**
 * Cities to show for a provider, plus how many were held back.
 *
 * An empty list is left empty rather than filled with a placeholder: the caller renders it
 * as an explicit "not reported", since a provider whose programs carry no city is missing
 * that field, not operating nowhere.
 */
export function cityPreview(cities: readonly string[]): { shown: string[]; more: number } {
  return {
    shown: cities.slice(0, CITY_PREVIEW),
    more: cities.length > CITY_PREVIEW ? cities.length - CITY_PREVIEW : 0,
  };
}
