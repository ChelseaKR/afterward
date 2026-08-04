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
  area: AreaFilter;
  city: string | null;
  sort: Sort;
}

export const DEFAULT_FILTERS: Filters = {
  query: "",
  onlyReported: false,
  outlook: "any",
  maxCost: null,
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
