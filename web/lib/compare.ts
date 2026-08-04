/**
 * Logic for the side-by-side comparison.
 *
 * Separate from the component so the "which of these is best" decision can be tested
 * directly. That decision is the one place in the UI where the tool comes closest to giving
 * advice, so it has to be conservative about what it claims.
 */

import type { SearchEntry } from "./types";

export const MAX_COMPARE = 4;

/**
 * Index of the strongest reported value among the entries, or null when highlighting one
 * would mislead.
 *
 * Returns null in three cases, each deliberate:
 *   - fewer than two programs reported the measure, because being the only provider willing
 *     to file a number is not the same as being the best one;
 *   - nobody reported it;
 *   - the best value is tied, because there is no single winner to mark.
 *
 * Unreported values are skipped, never coerced. A null cost is not free and a null salary
 * is not zero.
 */
export function bestOf(
  entries: SearchEntry[],
  read: (entry: SearchEntry) => number | null,
  direction: "high" | "low",
): number | null {
  const reported = entries
    .map((entry, index) => ({ index, value: read(entry) }))
    .filter((candidate): candidate is { index: number; value: number } => candidate.value !== null);

  if (reported.length < 2) return null;

  const winner = reported.reduce((a, b) =>
    direction === "high" ? (b.value > a.value ? b : a) : b.value < a.value ? b : a,
  );

  if (reported.filter((candidate) => candidate.value === winner.value).length > 1) return null;
  return winner.index;
}
