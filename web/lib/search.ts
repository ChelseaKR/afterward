/**
 * Search, filter, and sort logic for the program index.
 *
 * Lives outside the component so it can be tested directly. The dataset is ~3,300 rows, so
 * a linear scan per keystroke is well within budget and no index structure is warranted.
 */

import type { SearchEntry } from "./types";

export type Sort = "relevance" | "earnings" | "cost" | "openings";

export interface Filters {
  query: string;
  onlyReported: boolean;
  hideShrinking: boolean;
  maxCost: number | null;
  sort: Sort;
}

export const DEFAULT_FILTERS: Filters = {
  query: "",
  onlyReported: false,
  hideShrinking: false,
  maxCost: null,
  sort: "relevance",
};

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
  // Unknown growth is not treated as shrinking. Filtering out what we simply do not know
  // would quietly hide programs for no stated reason.
  if (filters.hideShrinking && entry.g !== null && entry.g < 0) return false;
  if (filters.maxCost !== null && (entry.$ === null || entry.$ > filters.maxCost)) return false;
  return true;
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
