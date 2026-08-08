/**
 * Search, filter, and sort logic for the program index.
 *
 * Lives outside the component so it can be tested directly. The dataset is ~3,300 rows, so
 * a linear scan per keystroke is well within budget and no index structure is warranted.
 */

import type { SearchEntry } from "./types";


export type Sort = "relevance" | "earnings" | "cost" | "length" | "openings";

/**
 * Three-way rather than a hide/show toggle. "Only shrinking" is the interesting one: it
 * surfaces the programs training people for work California expects to have less of, which
 * is the single clearest argument for this dataset existing.
 */
export type Outlook = "any" | "growing" | "shrinking";

/**
 * The geography filter, over the labor-market areas California itself publishes.
 *
 * Three states rather than "an area or nothing", because the dataset has three. A program is
 * placed in an area only when its city is one EDD names in that area's own title, and 1,741
 * of California's 3,266 programs are in cities EDD names nowhere — including cities that sit
 * squarely inside these areas' counties (Van Nuys, Pleasant Hill, Clovis). Those programs are
 * not "somewhere else" and they are not "region unknown": they are unplaced, and nothing here
 * may quietly file them under an area or under a residual bucket that reads like one.
 *
 * `"unplaced"` is therefore a selection a reader can make, not merely a state they fall into.
 * Without it the 53% would be reachable only by never touching this filter, which is the same
 * as hiding them.
 */
export type AreaFilter =
  | { kind: "any" }
  | { kind: "area"; name: string }
  | { kind: "unplaced" };

export const ANY_AREA: AreaFilter = Object.freeze({ kind: "any" });
export const UNPLACED_AREA: AreaFilter = Object.freeze({ kind: "unplaced" });

export interface Filters {
  query: string;
  onlyReported: boolean;
  outlook: Outlook;
  maxCost: number | null;
  /**
   * The longest a program may run, in weeks, or null for no limit.
   *
   * The second half of what someone out of work is actually spending. Cost has had a control
   * since the first release and time has not, although the dataset carries a length for 3,254
   * of California's 3,266 programs and they run from one week to 260 — so "can I be earning
   * again by March" was a question the index could answer and the interface could not ask.
   */
  maxWeeks: number | null;
  area: AreaFilter;
  city: string | null;
  sort: Sort;
}

export const DEFAULT_FILTERS: Filters = {
  query: "",
  onlyReported: false,
  outlook: "any",
  maxCost: null,
  maxWeeks: null,
  area: ANY_AREA,
  city: null,
  sort: "relevance",
};

/**
 * The area a row was placed in, or null when it was not placed in one.
 *
 * The `undefined` case is an index built before the field existed. It is read as unplaced,
 * never as membership: a row that cannot say where it is must not be attributed to an area,
 * and the alternative — treating a missing key as "matches whatever is selected" — would put
 * a program under a labor market on no evidence at all.
 */
export function areaOf(entry: SearchEntry): string | null {
  return entry.a === undefined ? null : entry.a;
}

export interface Tally {
  name: string;
  count: number;
}

/**
 * Published areas with at least one program, most programs first.
 *
 * Only areas that actually received programs appear. EDD publishes 31 areas and four of them
 * hold nothing — three rural Consortium regions whose names are region coinages rather than
 * city-titled CBSAs, so no program city can ever match one. Offering them as filter options
 * would advertise 31 choices, four of which silently return nothing.
 */
export function areas(programs: SearchEntry[]): Tally[] {
  const counts = new Map<string, number>();
  for (const program of programs) {
    const name = areaOf(program);
    if (name !== null) counts.set(name, (counts.get(name) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
}

/**
 * How many rows carry no area at all.
 *
 * Its own count rather than `total - placed`, because it is a finding about the data — the
 * state's own geography does not reach these programs — and not an arithmetic leftover.
 */
export function unplacedTotal(programs: SearchEntry[]): number {
  return programs.filter((program) => areaOf(program) === null).length;
}

/**
 * Cities with at least one program, most programs first.
 *
 * Cities are kept alongside areas rather than replaced by them. An area only ever contains
 * the two or three cities EDD names in its title, so the city list is the *only* geographic
 * handle the 1,741 unplaced programs have; dropping it would leave someone in Clovis unable
 * to narrow to anything at all. Pass a list already narrowed by `matchesArea` to get the
 * cities inside one area — the caller does the narrowing so this stays a plain tally.
 */
export function cities(programs: SearchEntry[]): Tally[] {
  const counts = new Map<string, number>();
  for (const program of programs) {
    const name = program.c?.trim();
    if (name) counts.set(name, (counts.get(name) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
}

/** Whether one row satisfies the area selection. Exact names only; no nearest-area guess. */
export function matchesArea(entry: SearchEntry, area: AreaFilter): boolean {
  const placed = areaOf(entry);
  switch (area.kind) {
    case "any":
      return true;
    case "unplaced":
      return placed === null;
    case "area":
      return placed === area.name;
  }
}

/**
 * Whether the provider filed this program as competency-based.
 *
 * A missing key is read as "no", and that is the safe direction here rather than the
 * convenient one: an index built before this field existed cannot distinguish the two, and
 * "no" leaves such a row behaving exactly as it did before the field was added. It is the
 * *presence* of the flag that changes anything, and only a current build sets it.
 */
export function isCompetencyBased(entry: SearchEntry): boolean {
  return entry.cb === true;
}

/**
 * The program's length in weeks of clock time, or null when it has none to compare.
 *
 * The single place the site decides what "how long is this" means, because three different
 * pieces of the interface ask it and they must not answer differently: the length filter, the
 * "shortest first" ordering, and the comparison's length band.
 *
 * Null for a competency-based program even if a week count was somehow filed alongside the
 * sentinel. "Ends when you can do the work" is a statement about the course that one filed
 * duration does not override, and a control that placed such a program on a scale of weeks
 * would be publishing a fixed length its provider explicitly declined to claim. No California
 * record does this today (0 of 3,266 on 2026-08-07; all 12 competency-based programs carry the
 * sentinel in both units), so this defines the case rather than reacting to one.
 */
export function clockWeeks(entry: SearchEntry): number | null {
  return isCompetencyBased(entry) ? null : entry.w;
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
  const occupations = entry.o.join(" ").toLowerCase();
  const city = (entry.c ?? "").toLowerCase();

  let total = 0;
  for (const term of searchTerms) {
    if (name.startsWith(term)) total += 6;
    else if (name.includes(term)) total += 4;
    else if (occupations.includes(term)) total += 3;
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

  // The null test is load-bearing and cannot be folded into the comparison. `null > 12` is
  // false in JavaScript, so `weeks > filters.maxWeeks` alone would pass every program with no
  // length to test, presenting them as ones that fit inside a month. A length nobody reported
  // is not a length of zero, so it fails the test instead.
  //
  // Two different populations fail it, and the interface has to say which is which:
  // `unmeasuredLength` counts the programs nobody filed a length for, and
  // `competencyBasedLength` counts the ones that have no fixed length by design. Both fail
  // the cap, for reasons that are not the same. "Six months or less" is a question about
  // clock time, and a competency-based program cannot be shown to fit inside it: how long it
  // takes is the student's answer, not the provider's. Including it would put a duration on
  // screen its provider declined to claim; dropping it silently would say it is too long,
  // which the record does not say. So it is excluded and counted, and the count is disclosed
  // in words of its own.
  const weeks = clockWeeks(entry);
  if (filters.maxWeeks !== null && (weeks === null || weeks > filters.maxWeeks)) return false;

  if (!matchesArea(entry, filters.area)) return false;
  if (filters.city !== null && entry.c !== filters.city) return false;
  return true;
}

/**
 * Programs the search found that no area selection can ever include.
 *
 * The exact cost of narrowing by area, measured against everything else the reader asked
 * for: query, outcomes, outlook and cost still apply, geography does not. That is the number
 * to put on screen beside a filtered result set — the blanket 1,741 would overstate what any
 * particular search is losing, and stating nothing would let the filter read as "everywhere
 * near here" when it means "in the two or three cities EDD names".
 */
export function unplacedMatches(programs: SearchEntry[], filters: Filters): number {
  const searchTerms = terms(filters.query);
  const ignoringGeography: Filters = { ...filters, area: ANY_AREA, city: null };

  let found = 0;
  for (const entry of programs) {
    if (areaOf(entry) !== null) continue;
    if (score(entry, searchTerms) < 0) continue;
    if (!matchesFilters(entry, ignoringGeography)) continue;
    found += 1;
  }
  return found;
}

/**
 * Programs the length limit removes, counted against the rest of the reader's search.
 *
 * The exact counterpart of `unplacedMatches`, for the same reason and against the same
 * measure: everything else the reader asked for still applies, only the length limit is
 * lifted. Two separate calls rather than one total, because the two populations are excluded
 * for two different reasons and a reader deciding whether to widen the search needs to know
 * which one they are being offered.
 */
function excludedByLength(
  programs: SearchEntry[],
  filters: Filters,
  qualifies: (entry: SearchEntry) => boolean,
): number {
  if (filters.maxWeeks === null) return 0;

  const searchTerms = terms(filters.query);
  const ignoringLength: Filters = { ...filters, maxWeeks: null };

  let found = 0;
  for (const entry of programs) {
    if (!qualifies(entry)) continue;
    if (score(entry, searchTerms) < 0) continue;
    if (!matchesFilters(entry, ignoringLength)) continue;
    found += 1;
  }
  return found;
}

/**
 * Programs this search found whose provider filed no length at all.
 *
 * A program nobody measured cannot be shown to fit inside a limit, so it is excluded, and a
 * filter that quietly drops programs on the grounds that nobody said how long they take reads
 * as "these are too long", which is a claim the data does not make.
 *
 * This was 12 programs until 2026-08-07, and those 12 were never in this state: they carry the
 * scorecard's competency-based sentinel, which the pipeline was reading as "not reported".
 * With that fixed, **no California program is in this state**: every one either files a clock
 * length or says it has none by design. The count stays, computed rather than assumed, because
 * a later snapshot can bring one back and the interface must not be silent when it does.
 */
export function unmeasuredLength(programs: SearchEntry[], filters: Filters): number {
  return excludedByLength(
    programs,
    filters,
    (entry) => !isCompetencyBased(entry) && entry.w === null,
  );
}

/**
 * Programs this search found that are competency-based, and so have no length to test.
 *
 * The other half of what a length cap removes, and the half that until 2026-08-07 was
 * misreported as the first. These programs end when the student can do the work; their
 * providers said so, on the record. 12 of California's 3,266 are in this state.
 *
 * Counted separately and disclosed in its own words so a reader can act on it: "no fixed
 * length" is a fact about how a course is run and may be exactly what somebody wants, whereas
 * "nobody said" is a gap in the record. Rolling them into one number would put the design
 * decision back inside the missing-data bucket this count exists to take it out of.
 */
export function competencyBasedLength(programs: SearchEntry[], filters: Filters): number {
  return excludedByLength(programs, filters, isCompetencyBased);
}

/** Headline counts for the context strip above the results. */
export function summarise(programs: SearchEntry[]) {
  return {
    total: programs.length,
    reported: programs.filter((p) => p.r).length,
    shrinking: programs.filter((p) => isShrinking(p.g)).length,
    // Carried in the headline rather than left to the filter, because "the state's geography
    // does not reach half of this dataset" is a fact about the data a reader is owed before
    // they touch a region control, not a footnote to one.
    unplaced: unplacedTotal(programs),
  };
}

/**
 * Comparators. Every ordering sends nulls last: a program that reported nothing has not
 * earned the top of a "highest earnings" list, and pushing it to the bottom of a "lowest
 * cost" list would be equally wrong, so unknown always trails known.
 */
const COMPARATORS: Record<Sort, (a: Ranked, b: Ranked) => number> = {
  relevance: (a, b) => b.rank - a.rank || (a.entry.n ?? "").localeCompare(b.entry.n ?? ""),
  // `at === false` means the filing describes the provider's whole institution, so the
  // earnings figure is real but is not this program's. Ranking on it would let an
  // institution-wide number win a list of programs.
  earnings: (a, b) => ownEarnings(b.entry) - ownEarnings(a.entry),
  cost: (a, b) => (a.entry.$ ?? Infinity) - (b.entry.$ ?? Infinity),
  // Length is a property of the course, not of the cohort, so unlike the three outcome
  // measures it stays comparable however the provider filed its outcome rows — the same
  // distinction `ownCohortOnly` in lib/compare.ts is built on. Infinity for a program with no
  // clock length rather than a large number, so both "nobody said" and "no fixed length by
  // design" trail every real length instead of landing among the two-year pathways. Through
  // `clockWeeks`, so a competency-based program cannot win "shortest first" on a week count
  // its provider declined to claim.
  length: (a, b) => (clockWeeks(a.entry) ?? Infinity) - (clockWeeks(b.entry) ?? Infinity),
  openings: (a, b) => (b.entry.op ?? -1) - (a.entry.op ?? -1),
};

function ownEarnings(entry: SearchEntry): number {
  return entry.at && entry.me !== null ? entry.me : -1;
}

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

/**
 * `AreaFilter` as a `<select>` option value, and back.
 *
 * A `<select>` can only carry strings, so the three states have to survive a round trip
 * through one. Areas are prefixed rather than passed bare so no area name can ever collide
 * with the sentinel for "unplaced" — an area called "unplaced" would otherwise silently
 * select the opposite of itself.
 */
const AREA_OPTION_PREFIX = "area:";
const UNPLACED_OPTION = "unplaced";

export function areaOptionValue(area: AreaFilter): string {
  switch (area.kind) {
    case "any":
      return "";
    case "unplaced":
      return UNPLACED_OPTION;
    case "area":
      return `${AREA_OPTION_PREFIX}${area.name}`;
  }
}

/** Anything unrecognised falls back to "any", which hides nothing and claims nothing. */
export function areaFromOptionValue(value: string): AreaFilter {
  if (value === UNPLACED_OPTION) return UNPLACED_AREA;
  if (value.startsWith(AREA_OPTION_PREFIX)) {
    return { kind: "area", name: value.slice(AREA_OPTION_PREFIX.length) };
  }
  return ANY_AREA;
}
