import { describe, expect, it } from "vitest";

import { milesBetween, nearestCenters, phoneParts } from "./centers";

function center(name: string, lat: number | null, lon: number | null) {
  return { name, lat, lon };
}

/**
 * This is a second implementation of arithmetic the Python pipeline already does, so what is
 * worth testing is that it agrees with it, not that it runs.
 *
 * The pair is the one `tests/test_local_help.py` cross-checks with: Coalinga to the Mendota
 * center, which CareerOneStop's own finder reports as 42.3 miles. Both implementations return
 * 42.4463183127371 for it — identical to the last digit of a float, and within a fifth of a mile
 * of the figure the endpoint published. That agreement is what licenses ranking offices here
 * instead of asking a federal endpoint again.
 */
describe("distance", () => {
  it("returns exactly what the Python pipeline returns for the same pair", () => {
    expect(milesBetween(36.1397, -120.3603, 36.7538, -120.3813)).toBeCloseTo(
      42.4463183127371,
      10,
    );
  });

  it("stays within a mile of the distance the federal finder published for that pair", () => {
    expect(milesBetween(36.1397, -120.3603, 36.7538, -120.3813)).toBeCloseTo(42.3, 0);
  });

  it("is zero for the same point", () => {
    expect(milesBetween(38.5, -121.4, 38.5, -121.4)).toBeCloseTo(0, 6);
  });
});

describe("ranking offices", () => {
  const centers = [
    center("far", 38.0, -121.0),
    center("near", 38.55, -121.47),
    center("middling", 38.3, -121.2),
  ];

  it("orders by distance and respects the limit", () => {
    const found = nearestCenters(centers, 38.556, -121.472, { limit: 2, withinMiles: 100 });
    expect(found.map((f) => f.center.name)).toEqual(["near", "middling"]);
  });

  it("returns nothing rather than something far away when nothing is inside the radius", () => {
    expect(nearestCenters(centers, 38.556, -121.472, { limit: 2, withinMiles: 0.1 })).toEqual([]);
  });

  /*
   * The failure this guards against puts an office nobody could place at the top of the list.
   * A missing coordinate read as 0 makes it the nearest thing to everywhere — the same
   * unknown-as-zero error the outcome figures on this site are protected from.
   */
  it("drops an office with no coordinates instead of ranking it as zero miles", () => {
    const withUnplaceable = [...centers, center("unplaceable", null, null)];
    const found = nearestCenters(withUnplaceable, 38.556, -121.472, {
      limit: 10,
      withinMiles: 500,
    });
    expect(found.map((f) => f.center.name)).not.toContain("unplaceable");
  });
});

/**
 * Every case below is a real phone field from the federal directory. 20 of the 183 California
 * centres publish something other than one ten-digit number, and the previous rendering stripped
 * non-digits from the whole field — so "619-319-9675 and 619-266-4253" became a `tel:` link for
 * a twenty-digit number, on every page that named that office.
 */
describe("published phone fields", () => {
  it("links a plain number", () => {
    expect(phoneParts("916-324-6202")).toEqual([
      { text: "916-324-6202", tel: "tel:+19163246202" },
    ]);
  });

  it("links two numbers separately instead of concatenating them", () => {
    expect(phoneParts("619-319-9675 and  619-266-4253")).toEqual([
      { text: "619-319-9675", tel: "tel:+16193199675" },
      { text: " and  ", tel: null },
      { text: "619-266-4253", tel: "tel:+16192664253" },
    ]);
  });

  /*
   * The extension is left as text on purpose. `tel:` extension syntax is honoured
   * inconsistently across phones, and dialling the switchboard and reading the extension off
   * the page always works.
   */
  it("dials the switchboard and leaves the extension readable", () => {
    expect(phoneParts("916-746-7722 Ext. 102")).toEqual([
      { text: "916-746-7722", tel: "tel:+19167467722" },
      { text: " Ext. 102", tel: null },
    ]);
  });

  it("keeps a toll-free number's leading 1", () => {
    const parts = phoneParts("530-865-6165 or 1-800-287-8711");
    expect(parts.map((p) => p.tel)).toEqual(["tel:+15308656165", null, "tel:+18002878711"]);
  });

  /*
   * "831-637-JOBS (5627) (Partner) 831-638-3306 (EDD)". The vanity number cannot be assembled
   * without guessing which bracketed digits belong to it, so it stays as text a person can read
   * and dial themselves. The number that can be read exactly is the only one linked.
   */
  it("leaves a vanity number as text rather than guessing at it", () => {
    const parts = phoneParts("831-637-JOBS (5627) (Partner) 831-638-3306 (EDD)");
    expect(parts.filter((p) => p.tel !== null)).toEqual([
      { text: "831-638-3306", tel: "tel:+18316383306" },
    ]);
    expect(parts.map((p) => p.text).join("")).toBe(
      "831-637-JOBS (5627) (Partner) 831-638-3306 (EDD)",
    );
  });

  it("never loses or rewrites a character of what the directory published", () => {
    for (const published of [
      "760-552-6550 or 6552",
      "916-395-5802, ext. 701060",
      "209-724-2100/Merced EDD WSB -209-728-5407",
      "805-648-WORK (9675) or toll-free at 833-810-9675",
      "424-419-4343  Ext: 7",
    ]) {
      expect(
        phoneParts(published)
          .map((p) => p.text)
          .join(""),
      ).toBe(published);
    }
  });

  it("links nothing in a field with no dialable number in it", () => {
    expect(phoneParts("call the college")).toEqual([{ text: "call the college", tel: null }]);
  });
});
