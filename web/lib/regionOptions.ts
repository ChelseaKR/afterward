/**
 * The choices for an occupation page's "Show programs in" filter (`components/RegionFilter`).
 *
 * Here rather than beside the component because the component is a client module, and a
 * function exported from one cannot be called by the server component that builds the page.
 */

export interface RegionOption {
  /** The area's short name exactly as the search index carries it, which is also its key. */
  area: string;
  count: number;
}

/**
 * The areas a list of programs was placed in, each with how many of them it holds, in
 * alphabetical order: a reader looks for their own area by name, and an order by count would
 * be one more list on this site that reads as a ranking. A program with no area adds to no
 * option. It is still in "All of California", and is never counted under a nearby area.
 */
export function regionOptions(areas: readonly (string | null)[]): RegionOption[] {
  const counts = new Map<string, number>();
  for (const area of areas) {
    if (area === null || area === "") continue;
    counts.set(area, (counts.get(area) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([area, count]) => ({ area, count }))
    .sort((a, b) => a.area.localeCompare(b.area, "en"));
}
