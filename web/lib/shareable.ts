/**
 * Search state in the URL, so a search can be sent to someone.
 *
 * Deciding on training is not something people do alone — they do it with a case manager, a
 * partner, or whoever is helping them at a job centre. A shareable URL serves that better
 * than a saved search behind an account would, because the person receiving it does not have
 * to sign up to open it. It also makes the back button work.
 *
 * Both halves are wired up in `SearchApp`: `filtersFromParams` restores a search on mount and
 * `filtersToQueryString` keeps the address bar in step with it. Until that landed only the
 * writing half was used, so "Copy link to this search" produced a link that opened on all
 * 3,266 programs — the encoding was right and nothing read it back.
 *
 * Two rules govern the encoding:
 *
 * 1. **A default is never written.** The URL carries only what the reader changed, so a bare
 *    `/en/` stays bare and a link stays short enough to paste into a text message.
 *
 * 2. **Anything unrecognised is dropped, never guessed.** A stale or hand-edited link falls
 *    back to the default for that one field rather than failing or, worse, silently selecting
 *    something adjacent. Showing the wrong region's programs because a link was old is
 *    exactly the class of quiet wrongness this project exists to avoid.
 */

import {
  ANY_AREA,
  DEFAULT_FILTERS,
  UNPLACED_AREA,
  type AreaFilter,
  type Filters,
  type Outlook,
  type Sort,
} from "./search";

/** Short keys: these end up in a URL a person may read aloud or type. */
const KEY = {
  query: "q",
  city: "city",
  area: "area",
  maxCost: "cost",
  maxWeeks: "weeks",
  outlook: "outlook",
  sort: "sort",
  onlyReported: "reported",
} as const;

/** The sentinel for "programs California places in no labour-market area". */
const UNPLACED_TOKEN = "none";

const OUTLOOKS: readonly Outlook[] = ["any", "growing", "shrinking"];
const SORTS: readonly Sort[] = ["relevance", "earnings", "cost", "length", "openings"];

function isOutlook(value: string): value is Outlook {
  return (OUTLOOKS as readonly string[]).includes(value);
}

function isSort(value: string): value is Sort {
  return (SORTS as readonly string[]).includes(value);
}

/**
 * Parse a cost or length cap. Rejects anything that is not a positive finite number.
 *
 * `Number("")` is 0 and `Number("abc")` is NaN, and either reaching a filter would silently
 * exclude every program that reported the measure — a filter nobody set, hiding results
 * nobody asked to hide. Shared by both caps because both fail the same way: a zero cap on
 * either one empties the result set while looking like it was chosen.
 */
function parseCap(raw: string): number | null {
  const value = Number(raw);
  return Number.isFinite(value) && value > 0 ? value : null;
}

function parseArea(raw: string): AreaFilter {
  if (raw === UNPLACED_TOKEN) return UNPLACED_AREA;
  const name = raw.trim();
  // An area name is validated against the dataset by the caller, which knows what California
  // publishes. Here it is only carried; `matchesArea` compares exactly, so an unknown name
  // yields an empty result set rather than an approximate one.
  return name ? { kind: "area", name } : ANY_AREA;
}

/** Encode only what differs from the defaults. */
export function filtersToParams(filters: Filters): URLSearchParams {
  const params = new URLSearchParams();

  const query = filters.query.trim();
  if (query) params.set(KEY.query, query);
  if (filters.onlyReported) params.set(KEY.onlyReported, "1");
  if (filters.outlook !== DEFAULT_FILTERS.outlook) params.set(KEY.outlook, filters.outlook);
  if (filters.sort !== DEFAULT_FILTERS.sort) params.set(KEY.sort, filters.sort);
  if (filters.maxCost !== null) params.set(KEY.maxCost, String(filters.maxCost));
  if (filters.maxWeeks !== null) params.set(KEY.maxWeeks, String(filters.maxWeeks));
  if (filters.city !== null) params.set(KEY.city, filters.city);

  if (filters.area.kind === "unplaced") params.set(KEY.area, UNPLACED_TOKEN);
  else if (filters.area.kind === "area") params.set(KEY.area, filters.area.name);

  return params;
}

/** Rebuild filters from a URL, falling back per field rather than all-or-nothing. */
export function filtersFromParams(params: URLSearchParams): Filters {
  const outlook = params.get(KEY.outlook);
  const sort = params.get(KEY.sort);
  const cost = params.get(KEY.maxCost);
  const weeks = params.get(KEY.maxWeeks);
  const city = params.get(KEY.city);
  const area = params.get(KEY.area);

  return {
    query: params.get(KEY.query) ?? DEFAULT_FILTERS.query,
    // Present-and-not-"0" is on. A checkbox has no third state, so an unreadable value is off.
    onlyReported: params.get(KEY.onlyReported) !== null && params.get(KEY.onlyReported) !== "0",
    outlook: outlook !== null && isOutlook(outlook) ? outlook : DEFAULT_FILTERS.outlook,
    sort: sort !== null && isSort(sort) ? sort : DEFAULT_FILTERS.sort,
    maxCost: cost !== null ? parseCap(cost) : DEFAULT_FILTERS.maxCost,
    maxWeeks: weeks !== null ? parseCap(weeks) : DEFAULT_FILTERS.maxWeeks,
    city: city !== null && city.trim() !== "" ? city : DEFAULT_FILTERS.city,
    area: area !== null ? parseArea(area) : DEFAULT_FILTERS.area,
  };
}

/** The query string for a search, empty when nothing has been narrowed. */
export function filtersToQueryString(filters: Filters): string {
  const params = filtersToParams(filters);
  // Stable order, so the same search always produces the same link and two people comparing
  // URLs are comparing searches rather than parameter ordering.
  params.sort();
  const encoded = params.toString();
  return encoded ? `?${encoded}` : "";
}

/** True when nothing is narrowed, so the UI can hide a share control that would share nothing. */
export function isDefaultSearch(filters: Filters): boolean {
  return filtersToParams(filters).toString() === "";
}
