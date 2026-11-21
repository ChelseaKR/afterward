/**
 * Other programs for the same jobs in the same area, for a program page.
 *
 * Nearly every reader of a program page arrived on it directly and left from it, and no
 * program page linked to another program. This is the short list that answers "what else
 * trains for this near me", built at export time from the search index the site already
 * ships, so it adds no request and no URL.
 *
 * What "near" and "the same jobs" mean is fixed and stated, because the list must never read
 * as a judgment about a provider:
 *
 * - **Near** is the same EDD labor-market area the program was placed in, and nothing else.
 *   A program with no area gets no list. It is never given a neighboring area's programs,
 *   however obvious the geography looks, which is the rule the rest of the page follows.
 * - **The same jobs** is at least one SOC code in common.
 * - **The order** is how many of this program's SOC codes the other program shares, most
 *   first, then the program name, then the id so two builds can never disagree. No outcome,
 *   cost or other figure enters the order, so the order is not a ranking and the page says so.
 */

import type { SearchEntry } from "./types";

/** At most this many cards. The statewide link below them carries the rest. */
export const NEARBY_SHOWN = 5;

export interface NearbyResult {
  /** The cards to show, in display order. */
  listed: SearchEntry[];
  /** Every program that qualified, listed or not. */
  total: number;
}

const byName = (a: SearchEntry, b: SearchEntry): number => {
  // A program with no filed name sorts after every named one rather than first as "".
  if (a.n === null || b.n === null) return a.n === b.n ? 0 : a.n === null ? 1 : -1;
  return a.n.localeCompare(b.n, "en");
};

export function nearbyPrograms(
  self: Pick<SearchEntry, "i" | "a" | "s">,
  programs: readonly SearchEntry[],
  limit: number = NEARBY_SHOWN,
): NearbyResult {
  if (self.a === null) return { listed: [], total: 0 };
  const own = new Set(self.s);
  if (own.size === 0) return { listed: [], total: 0 };

  const qualified: { entry: SearchEntry; shared: number }[] = [];
  for (const entry of programs) {
    if (entry.i === self.i || entry.a !== self.a) continue;
    const shared = new Set(entry.s.filter((soc) => own.has(soc))).size;
    if (shared > 0) qualified.push({ entry, shared });
  }

  qualified.sort(
    (x, y) =>
      y.shared - x.shared || byName(x.entry, y.entry) || x.entry.i.localeCompare(y.entry.i, "en"),
  );

  return { listed: qualified.slice(0, limit).map((q) => q.entry), total: qualified.length };
}

/**
 * The one occupation the statewide link names: "All 14 programs for Surgical Technologists
 * in California".
 *
 * The program's own occupation that the most listed cards share, so the link continues the
 * list the reader has just looked at; ties, and a program with no cards, go to the program's
 * own order. Only an occupation at least one other program trains for qualifies: a link to
 * "all 1 programs" would lead back to the page it sits on. Null when none qualifies.
 */
export function statewideJob(
  ownSocs: readonly string[],
  listed: readonly SearchEntry[],
  counts: ReadonlyMap<string, number>,
): { soc: string; programs: number } | null {
  let best: { soc: string; programs: number; shared: number } | null = null;
  for (const soc of ownSocs) {
    const programs = counts.get(soc) ?? 0;
    if (programs < 2) continue;
    const shared = listed.filter((entry) => entry.s.includes(soc)).length;
    if (best === null || shared > best.shared) best = { soc, programs, shared };
  }
  return best === null ? null : { soc: best.soc, programs: best.programs };
}

/**
 * The area as a place name in a sentence: "Vallejo MSA" reads "Vallejo", so the heading says
 * "in the Vallejo area" rather than "in the Vallejo MSA area". Only the trailing kind of area
 * EDD appends (MSA, MD, Region) is dropped; the name itself is EDD's, unchanged.
 */
export function areaPlace(shortName: string): string {
  const place = shortName.replace(/\s+(MSA|MD|Region)$/, "").trim();
  return place.length > 0 ? place : shortName;
}
