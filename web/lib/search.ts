/**
 * Search, filter, and sort logic for the program index.
 *
 * Lives outside the component so it can be tested directly. The dataset is ~3,300 rows, so
 * a linear scan per keystroke is well within budget and no index structure is warranted.
 */

import type { SearchEntry } from "./types";

export type Sort = "relevance" | "earnings" | "cost" | "openings";

/**
 * Three-way rather than a hide/show toggle. "Only shrinking" is the interesting one: it
 * surfaces the programs training people for work California expects to have less of, which
 * is the single clearest argument for this dataset existing.
 */
export type Outlook = "any" | "growing" | "shrinking";

export interface Filters {
  query: string;
  onlyReported: boolean;
  outlook: Outlook;
  maxCost: number | null;
  city: string | null;
  sort: Sort;
}

export const DEFAULT_FILTERS: Filters = {
  query: "",
  onlyReported: false,
  outlook: "any",
  maxCost: null,
  city: null,
  sort: "relevance",
};

/**
 * Cities with at least one program, most programs first.
 *
 * Deliberately cities rather than invented "regions": the data carries a city per program
 * and nothing that reliably rolls up to a labour market area, so grouping them would mean
 * guessing which region a town belongs to and presenting the guess as fact.
 */
export function cities(programs: SearchEntry[]): { name: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const program of programs) {
    const name = program.c?.trim();
    if (name) counts.set(name, (counts.get(name) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
}

export const isShrinking = (growth: number | null): boolean => growth !== null && growth < 0;

export function terms(query: string): string[] {
  return query.toLowerCase().split(/\s+/).filter(Boolean);
}

/**
 * Rank an entry against the search terms. Returns -1 when any term matches nothing, so
 * multi-word queries narrow rather than widen.
 */
export function score(entry: SearchEntry, searchTerms: string[]): number {
  if (searchTerms.length === 0) return 0;

  const name = (entry.n ?? "").toLowerCase();
  const provider = (entry.p ?? "").toLowerCase();
  const occupation = (entry.o ?? "").toLowerCase();
  const city = (entry.c ?? "").toLowerCase();

  let total = 0;
  for (const term of searchTerms) {
    if (name.startsWith(term)) total += 6;
    else if (name.includes(term)) total += 4;
    else if (occupation.includes(term)) total += 3;
    else if (provider.includes(term)) total += 2;
    else if (city.includes(term)) total += 2;
    else return -1;
  }
  return total;
}

export function matchesFilters(entry: SearchEntry, filters: Filters): boolean {
  if (filters.onlyReported && !entry.r) return false;

  // Unknown growth is neither growing nor shrinking, so an outlook filter excludes it from
  // both. Guessing in either direction would put a claim on the screen the data cannot back.
  if (filters.outlook === "shrinking" && !isShrinking(entry.g)) return false;
  if (filters.outlook === "growing" && (entry.g === null || entry.g <= 0)) return false;

  if (filters.maxCost !== null && (entry.$ === null || entry.$ > filters.maxCost)) return false;
  if (filters.city !== null && entry.c !== filters.city) return false;
  return true;
}

/** Headline counts for the context strip above the results. */
export function summarise(programs: SearchEntry[]) {
  return {
    total: programs.length,
    reported: programs.filter((p) => p.r).length,
    shrinking: programs.filter((p) => isShrinking(p.g)).length,
  };
}

/**
 * Comparators. Every ordering sends nulls last: a program that reported nothing has not
 * earned the top of a "highest earnings" list, and pushing it to the bottom of a "lowest
 * cost" list would be equally wrong, so unknown always trails known.
 */
const COMPARATORS: Record<Sort, (a: Ranked, b: Ranked) => number> = {
  relevance: (a, b) => b.rank - a.rank || (a.entry.n ?? "").localeCompare(b.entry.n ?? ""),
  earnings: (a, b) => (b.entry.me ?? -1) - (a.entry.me ?? -1),
  cost: (a, b) => (a.entry.$ ?? Infinity) - (b.entry.$ ?? Infinity),
  openings: (a, b) => (b.entry.op ?? -1) - (a.entry.op ?? -1),
};

interface Ranked {
  entry: SearchEntry;
  rank: number;
}

export function runSearch(programs: SearchEntry[], filters: Filters): SearchEntry[] {
  const searchTerms = terms(filters.query);

  const ranked: Ranked[] = [];
  for (const entry of programs) {
    const rank = score(entry, searchTerms);
    if (rank < 0) continue;
    if (!matchesFilters(entry, filters)) continue;
    ranked.push({ entry, rank });
  }

  return ranked.sort(COMPARATORS[filters.sort]).map(({ entry }) => entry);
}
