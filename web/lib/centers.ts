/**
 * Two things a program page has to work out about an America's Job Center for itself.
 *
 * Both are here rather than in the pipeline because both are answered from data the pipeline
 * has already published. `coverage.json` carries the whole California directory — 183 offices,
 * every one of them with coordinates, a phone number and opening hours — and each program
 * record carries its own coordinates. Nothing below asks a network for anything.
 */

/** Statute miles, the same figure `afterward.sources.local_help.EARTH_RADIUS_MILES` uses. */
const EARTH_RADIUS_MILES = 3958.7613;

/**
 * Great-circle distance in statute miles.
 *
 * A deliberate second implementation of `local_help.distance_miles`, kept honest by the test
 * beside it using the same cross-check the Python test uses: CareerOneStop's own finder puts
 * Coalinga's nearest office at 42.3 miles and this arithmetic puts it at 42.2.
 *
 * Straight-line, not driving distance, and the gap is widest exactly where the nearest office
 * is furthest away. Anything showing this to a reader says "about" and says the drive is longer.
 */
export function milesBetween(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const phi1 = (lat1 * Math.PI) / 180;
  const phi2 = (lat2 * Math.PI) / 180;
  const deltaPhi = phi2 - phi1;
  const deltaLambda = ((lon2 - lon1) * Math.PI) / 180;
  const haversine =
    Math.sin(deltaPhi / 2) ** 2 +
    Math.cos(phi1) * Math.cos(phi2) * Math.sin(deltaLambda / 2) ** 2;
  return 2 * EARTH_RADIUS_MILES * Math.asin(Math.sqrt(haversine));
}

/** The minimum a centre record needs before it can be ranked by distance. */
interface Placeable {
  lat: number | null;
  lon: number | null;
  name: string;
}

/**
 * The closest centres to a point, nearest first, with the distance to each.
 *
 * Same two rules as `local_help.nearest_centers`, for the same reasons. A centre with no
 * published coordinates is dropped rather than sorted last: this function's entire output is a
 * distance claim, and a missing coordinate read as 0 would make an unplaceable office the
 * nearest thing to everywhere. And `withinMiles` is a filter, not a fallback — an empty result
 * is the honest answer when there is nothing inside it.
 *
 * All 183 California centres carry coordinates today. The rule does not depend on that holding.
 */
export function nearestCenters<T extends Placeable>(
  centers: readonly T[],
  lat: number,
  lon: number,
  { limit, withinMiles }: { limit: number; withinMiles: number },
): { center: T; miles: number }[] {
  return centers
    .flatMap((center) =>
      center.lat === null || center.lon === null
        ? []
        : [{ center, miles: milesBetween(lat, lon, center.lat, center.lon) }],
    )
    .filter((found) => found.miles <= withinMiles)
    .sort((a, b) => a.miles - b.miles || a.center.name.localeCompare(b.center.name))
    .slice(0, limit);
}

/**
 * One run of a published phone field: either dialable, or text around the dialable bits.
 *
 * `tel` is null for everything that is not a phone number — "or", "Ext. 102", "(EDD)" — so a
 * renderer can wrap only the parts a phone can actually dial and leave the rest as words.
 */
export interface PhonePart {
  text: string;
  tel: string | null;
}

/**
 * A phone number as the federal directory publishes it, which is not always one number.
 *
 * 20 of the 183 California centres publish something other than a single ten-digit number in
 * this field: two numbers ("619-319-9675 and 619-266-4253"), a number and an extension
 * ("916-746-7722 Ext. 102"), a vanity number with its digits in brackets, a switchboard and an
 * EDD line labelled separately. Stripping every non-digit and calling the result a phone number
 * turned all 20 into a `tel:` link for a twenty-digit number that dials nothing — on 778 of the
 * 3,234 program pages that name an office, in both languages.
 *
 * So the published string is kept exactly as filed and the numbers inside it are found rather
 * than assumed. What this cannot parse stays as readable text: a vanity number whose digits are
 * spelled in letters is still on the page for a person to read, it simply is not a link. That is
 * the safe direction to fail in — a number a reader can see and dial themselves beats a link
 * that dials the wrong thing.
 *
 * Ten digits are assumed North American and given a country code so the link works from a
 * mobile abroad; an eleven-digit number already starting with 1 keeps it.
 */
const PHONE_NUMBER = /(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}/g;

export function phoneParts(phone: string): PhonePart[] {
  const parts: PhonePart[] = [];
  let cursor = 0;

  for (const match of phone.matchAll(PHONE_NUMBER)) {
    const start = match.index;
    if (start > cursor) parts.push({ text: phone.slice(cursor, start), tel: null });
    parts.push({ text: match[0], tel: telHref(match[0]) });
    cursor = start + match[0].length;
  }
  if (cursor < phone.length) parts.push({ text: phone.slice(cursor), tel: null });

  return parts;
}

/**
 * A dialable `tel:` URL for one matched number, or null.
 *
 * Only digits and a leading `+` reach the href. The field is a third-party string from a
 * federal API and a URL is not somewhere a stray character belongs.
 */
function telHref(number: string): string | null {
  const digits = number.replace(/[^0-9]/g, "");
  if (digits.length === 10) return `tel:+1${digits}`;
  if (digits.length === 11 && digits.startsWith("1")) return `tel:+${digits}`;
  return null;
}
