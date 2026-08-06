import { describe, expect, it } from "vitest";

import { DEFAULT_FILTERS, type Filters } from "./search";
import {
  filtersFromParams,
  filtersToParams,
  filtersToQueryString,
  isDefaultSearch,
} from "./shareable";

const filters = (overrides: Partial<Filters> = {}): Filters => ({ ...DEFAULT_FILTERS, ...overrides });

describe("encoding", () => {
  it("writes nothing for a search nobody narrowed", () => {
    // A bare /en/ must stay bare, or every visit produces a URL implying a search was made.
    expect(filtersToQueryString(DEFAULT_FILTERS)).toBe("");
    expect(isDefaultSearch(DEFAULT_FILTERS)).toBe(true);
  });

  it("writes only what changed", () => {
    const params = filtersToParams(filters({ query: "welding", maxCost: 5000 }));
    expect([...params.keys()].sort()).toEqual(["cost", "q"]);
  });

  it("trims a query of whitespace rather than encoding it", () => {
    expect(filtersToQueryString(filters({ query: "   " }))).toBe("");
    expect(filtersToParams(filters({ query: "  welding  " })).get("q")).toBe("welding");
  });

  it("orders parameters stably, so the same search is the same link", () => {
    const a = filtersToQueryString(filters({ query: "nursing", maxCost: 5000, city: "Fresno" }));
    const b = filtersToQueryString(filters({ city: "Fresno", maxCost: 5000, query: "nursing" }));
    expect(a).toBe(b);
  });

  it("encodes the unplaced-area selection as its own token", () => {
    // "No region" is a choice a reader makes about 53% of programs, not an absent filter.
    expect(filtersToParams(filters({ area: { kind: "unplaced" } })).get("area")).toBe("none");
  });

  it("encodes a named area by name", () => {
    expect(filtersToParams(filters({ area: { kind: "area", name: "Fresno MSA" } })).get("area")).toBe(
      "Fresno MSA",
    );
  });
});

describe("round trip", () => {
  const cases: [string, Filters][] = [
    ["defaults", DEFAULT_FILTERS],
    ["a query", filters({ query: "medical assistant" })],
    ["a cost cap", filters({ maxCost: 5000 })],
    ["a city", filters({ city: "Fresno" })],
    ["a named area", filters({ area: { kind: "area", name: "Bakersfield MSA" } })],
    ["the unplaced area", filters({ area: { kind: "unplaced" } })],
    ["only reported", filters({ onlyReported: true })],
    ["an outlook", filters({ outlook: "shrinking" })],
    ["a sort", filters({ sort: "cost" })],
    ["a length cap", filters({ maxWeeks: 26 })],
    ["the shortest-first sort", filters({ sort: "length" })],
    [
      "everything at once",
      filters({
        query: "nursing assistant",
        onlyReported: true,
        outlook: "growing",
        sort: "earnings",
        maxCost: 10000,
        maxWeeks: 52,
        city: "Clovis",
        area: { kind: "area", name: "Fresno MSA" },
      }),
    ],
  ];

  for (const [name, original] of cases) {
    it(`survives ${name}`, () => {
      expect(filtersFromParams(filtersToParams(original))).toEqual(original);
    });
  }
});

describe("decoding a link that is stale, hand-edited, or hostile", () => {
  const parse = (qs: string) => filtersFromParams(new URLSearchParams(qs));

  it("falls back per field rather than discarding the whole link", () => {
    const result = parse("q=welding&sort=nonsense");
    expect(result.query).toBe("welding");
    expect(result.sort).toBe(DEFAULT_FILTERS.sort);
  });

  it("refuses a cost that is not a positive number", () => {
    // Number("") is 0 and Number("abc") is NaN; either reaching the filter would exclude
    // every program with a reported cost — a filter nobody set, hiding results silently.
    for (const bad of ["", "abc", "0", "-500", "NaN", "Infinity"]) {
      expect(parse(`cost=${bad}`).maxCost).toBeNull();
    }
  });

  it("accepts a genuine cost", () => {
    expect(parse("cost=5000").maxCost).toBe(5000);
  });

  it("refuses a length that is not a positive number", () => {
    // Same failure as the cost cap: a zero or unreadable cap empties the result set while
    // looking like something the reader chose.
    for (const bad of ["", "abc", "0", "-4", "NaN", "Infinity"]) {
      expect(parse(`weeks=${bad}`).maxWeeks).toBeNull();
    }
  });

  it("accepts a length the option list does not offer", () => {
    // The caps in the interface are four editorial choices, not the definition of a valid
    // link. A hand-edited or older link asking for 18 weeks is answerable, so it is answered.
    expect(parse("weeks=18").maxWeeks).toBe(18);
  });

  it("rejects an unknown outlook rather than guessing a neighbour", () => {
    expect(parse("outlook=declining").outlook).toBe("any");
  });

  it("treats a blank city as no city", () => {
    expect(parse("city=").city).toBeNull();
    expect(parse("city=%20%20").city).toBeNull();
  });

  it("treats a blank area as any area, never as unplaced", () => {
    // Defaulting to "unplaced" would hide 47% of programs on the strength of a typo.
    expect(parse("area=").area).toEqual({ kind: "any" });
    expect(parse("area=%20").area).toEqual({ kind: "any" });
  });

  it("carries an unknown area name rather than silently widening the search", () => {
    // Exact matching downstream yields an empty result set, which is honest. Falling back to
    // "any" would show a reader programs from everywhere while their link said one region.
    expect(parse("area=Atlantis+MSA").area).toEqual({ kind: "area", name: "Atlantis MSA" });
  });

  it("reads the reported flag as a checkbox, with no third state", () => {
    expect(parse("reported=1").onlyReported).toBe(true);
    expect(parse("reported=true").onlyReported).toBe(true);
    expect(parse("reported=0").onlyReported).toBe(false);
    expect(parse("").onlyReported).toBe(false);
  });

  it("ignores parameters it does not know", () => {
    expect(parse("utm_source=newsletter&q=welding").query).toBe("welding");
  });
});
