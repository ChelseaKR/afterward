import { describe, expect, it } from "vitest";

import {
  ANY_AREA,
  UNPLACED_AREA,
  areaFromOptionValue,
  areaOf,
  areaOptionValue,
  areas,
  cities,
  DEFAULT_FILTERS,
  isShrinking,
  matchesArea,
  matchesFilters,
  runSearch,
  score,
  summarise,
  terms,
  unplacedMatches,
  unplacedTotal,
} from "./search";
import type { SearchEntry } from "./types";

function entry(overrides: Partial<SearchEntry> = {}): SearchEntry {
  return {
    i: "id",
    n: "Medical Assisting",
    p: "Fresno City College",
    c: "Fresno",
    a: "Fresno MSA",
    $: 4000,
    $partial: false,
    at: true,
    w: 30,
    s: ["31-9092"],
    o: ["Medical Assistants"],
    g: 12.5,
    wage: 45000,
    op: 5000,
    cr: 0.8,
    er: 0.7,
    me: 32000,
    r: true,
    ...overrides,
  };
}

describe("score", () => {
  it("ranks a name prefix above a name substring", () => {
    const prefix = score(entry({ n: "Welding Technology" }), ["weld"]);
    const substring = score(entry({ n: "Advanced Welding" }), ["weld"]);
    expect(prefix).toBeGreaterThan(substring);
  });

  it("ranks name matches above occupation, provider, and city matches", () => {
    const byName = score(entry({ n: "Nursing" }), ["nursing"]);
    const byOccupation = score(entry({ n: "Program", o: ["Nursing Assistants"] }), ["nursing"]);
    const byCity = score(entry({ n: "Program", o: ["Other"], c: "Nursing City" }), ["nursing"]);
    expect(byName).toBeGreaterThan(byOccupation);
    expect(byOccupation).toBeGreaterThan(byCity);
  });

  it("requires every term to match something", () => {
    expect(score(entry(), ["medical", "fresno"])).toBeGreaterThan(0);
    expect(score(entry(), ["medical", "nonexistent"])).toBe(-1);
  });

  it("treats an empty query as neutral rather than unmatched", () => {
    expect(score(entry(), [])).toBe(0);
  });

  it("survives entries with null text fields", () => {
    const sparse = entry({ n: null, p: null, o: [], c: null });
    expect(score(sparse, ["anything"])).toBe(-1);
    expect(score(sparse, [])).toBe(0);
  });

  it("is case insensitive", () => {
    expect(score(entry({ n: "WELDING" }), ["welding"])).toBeGreaterThan(0);
  });
});

describe("terms", () => {
  it("splits on whitespace and drops empties", () => {
    expect(terms("  medical   assistant ")).toEqual(["medical", "assistant"]);
    expect(terms("   ")).toEqual([]);
  });
});

describe("matchesFilters", () => {
  it("onlyReported excludes programs that reported nothing", () => {
    const filters = { ...DEFAULT_FILTERS, onlyReported: true };
    expect(matchesFilters(entry({ r: true }), filters)).toBe(true);
    expect(matchesFilters(entry({ r: false }), filters)).toBe(false);
  });

  it("outlook 'shrinking' keeps only known declines", () => {
    const filters = { ...DEFAULT_FILTERS, outlook: "shrinking" as const };
    expect(matchesFilters(entry({ g: -5 }), filters)).toBe(true);
    expect(matchesFilters(entry({ g: 5 }), filters)).toBe(false);
  });

  it("outlook 'growing' keeps only known growth", () => {
    const filters = { ...DEFAULT_FILTERS, outlook: "growing" as const };
    expect(matchesFilters(entry({ g: 5 }), filters)).toBe(true);
    expect(matchesFilters(entry({ g: -5 }), filters)).toBe(false);
    expect(matchesFilters(entry({ g: 0 }), filters)).toBe(false);
  });

  it("excludes unknown growth from both outlook filters", () => {
    // Unknown is neither growing nor shrinking. Guessing either way would put a claim on
    // screen the data cannot support.
    expect(matchesFilters(entry({ g: null }), { ...DEFAULT_FILTERS, outlook: "shrinking" })).toBe(false);
    expect(matchesFilters(entry({ g: null }), { ...DEFAULT_FILTERS, outlook: "growing" })).toBe(false);
    expect(matchesFilters(entry({ g: null }), DEFAULT_FILTERS)).toBe(true);
  });

  it("maxCost excludes programs with no reported cost", () => {
    // A cost cap is a budget promise; a program that never said what it costs cannot honor it.
    const filters = { ...DEFAULT_FILTERS, maxCost: 5000 };
    expect(matchesFilters(entry({ $: 4000 }), filters)).toBe(true);
    expect(matchesFilters(entry({ $: 9000 }), filters)).toBe(false);
    expect(matchesFilters(entry({ $: null }), filters)).toBe(false);
  });

  it("maxCost is inclusive at the boundary", () => {
    expect(matchesFilters(entry({ $: 5000 }), { ...DEFAULT_FILTERS, maxCost: 5000 })).toBe(true);
  });
});

describe("runSearch sorting", () => {
  const reported = entry({ i: "high", me: 50000, $: 9000, op: 100 });
  const modest = entry({ i: "low", me: 20000, $: 1000, op: 900 });
  const unreported = entry({ i: "none", me: null, $: null, op: null, r: false });
  const all = [unreported, modest, reported];

  it("sorts unreported earnings last", () => {
    const ids = runSearch(all, { ...DEFAULT_FILTERS, sort: "earnings" }).map((e) => e.i);
    expect(ids).toEqual(["high", "low", "none"]);
  });

  it("sorts unreported cost last rather than treating it as free", () => {
    const ids = runSearch(all, { ...DEFAULT_FILTERS, sort: "cost" }).map((e) => e.i);
    expect(ids).toEqual(["low", "high", "none"]);
  });

  it("sorts by job openings, not wage", () => {
    // Regression: the openings comparator previously read the wage field.
    const ids = runSearch(all, { ...DEFAULT_FILTERS, sort: "openings" }).map((e) => e.i);
    expect(ids).toEqual(["low", "high", "none"]);
  });

  it("returns everything when no query or filters are set", () => {
    expect(runSearch(all, DEFAULT_FILTERS)).toHaveLength(3);
  });

  it("combines query and filters", () => {
    const results = runSearch(
      [entry({ i: "a", n: "Welding", r: true }), entry({ i: "b", n: "Welding", r: false })],
      { ...DEFAULT_FILTERS, query: "welding", onlyReported: true },
    );
    expect(results.map((e) => e.i)).toEqual(["a"]);
  });

  it("does not mutate the input array", () => {
    const input = [...all];
    runSearch(input, { ...DEFAULT_FILTERS, sort: "earnings" });
    expect(input.map((e) => e.i)).toEqual(["none", "low", "high"]);
  });
});

describe("summarise", () => {
  it("counts reported and shrinking programs for the context strip", () => {
    const stats = summarise([
      entry({ r: true, g: -5 }),
      entry({ r: false, g: 10 }),
      entry({ r: true, g: null }),
    ]);
    expect(stats).toEqual({ total: 3, reported: 2, shrinking: 1, unplaced: 0 });
  });

  it("counts unplaced programs, so the headline can say the geography is partial", () => {
    const stats = summarise([entry({ a: "Fresno MSA" }), entry({ a: null }), entry({ a: null })]);
    expect(stats.unplaced).toBe(2);
  });
});

describe("isShrinking", () => {
  it("is false for unknown and flat growth", () => {
    expect(isShrinking(null)).toBe(false);
    expect(isShrinking(0)).toBe(false);
    expect(isShrinking(-0.1)).toBe(true);
  });
});

describe("cities", () => {
  it("lists cities by program count, then alphabetically", () => {
    const list = cities([
      entry({ c: "Fresno" }),
      entry({ c: "Bakersfield" }),
      entry({ c: "Fresno" }),
      entry({ c: "Anaheim" }),
    ]);
    expect(list).toEqual([
      { name: "Fresno", count: 2 },
      { name: "Anaheim", count: 1 },
      { name: "Bakersfield", count: 1 },
    ]);
  });

  it("ignores programs with no city rather than inventing one", () => {
    const list = cities([entry({ c: null }), entry({ c: "   " }), entry({ c: "Fresno" })]);
    expect(list).toEqual([{ name: "Fresno", count: 1 }]);
  });
});

describe("city filter", () => {
  it("matches exactly, so one city cannot stand in for another", () => {
    const filters = { ...DEFAULT_FILTERS, city: "Fresno" };
    expect(matchesFilters(entry({ c: "Fresno" }), filters)).toBe(true);
    expect(matchesFilters(entry({ c: "Fresno County" }), filters)).toBe(false);
    expect(matchesFilters(entry({ c: null }), filters)).toBe(false);
  });

  it("is inert when unset", () => {
    expect(matchesFilters(entry({ c: null }), DEFAULT_FILTERS)).toBe(true);
  });
});

describe("areaOf", () => {
  it("reads a placed program's area", () => {
    expect(areaOf(entry({ a: "Bakersfield-Delano MSA" }))).toBe("Bakersfield-Delano MSA");
  });

  it("reads an unplaced program as unplaced", () => {
    expect(areaOf(entry({ a: null }))).toBeNull();
  });

  it("reads a row from an index built before the field as unplaced, never as a member", () => {
    // The alternative — letting a missing key satisfy whichever area is selected — would put
    // a program under a labor market on no evidence whatsoever.
    // The field is required on SearchEntry, so a row without it cannot be built normally.
    // That is the point: this simulates JSON from an index emitted before the field existed,
    // which the type system cannot police because it arrives as parsed JSON at runtime.
    const { a: _dropped, ...withoutArea } = entry();
    const legacy = withoutArea as SearchEntry;
    expect(areaOf(legacy)).toBeNull();
    expect(matchesArea(legacy, { kind: "area", name: "Fresno MSA" })).toBe(false);
    expect(matchesArea(legacy, UNPLACED_AREA)).toBe(true);
  });
});

describe("areas", () => {
  it("lists areas by program count, then alphabetically", () => {
    const list = areas([
      entry({ a: "Fresno MSA" }),
      entry({ a: "Visalia MSA" }),
      entry({ a: "Fresno MSA" }),
      entry({ a: "Chico MSA" }),
    ]);
    expect(list).toEqual([
      { name: "Fresno MSA", count: 2 },
      { name: "Chico MSA", count: 1 },
      { name: "Visalia MSA", count: 1 },
    ]);
  });

  it("never invents an area for the unplaced, nor a bucket to hold them", () => {
    const list = areas([entry({ a: null }), entry({ a: null }), entry({ a: "Fresno MSA" })]);
    expect(list).toEqual([{ name: "Fresno MSA", count: 1 }]);
  });
});

describe("unplacedTotal", () => {
  it("counts the programs the state's geography does not reach", () => {
    expect(unplacedTotal([entry({ a: null }), entry({ a: "Fresno MSA" }), entry({ a: null })])).toBe(
      2,
    );
  });
});

describe("area filter", () => {
  const placed = entry({ i: "placed", c: "Fresno", a: "Fresno MSA" });
  const elsewhere = entry({ i: "elsewhere", c: "Visalia", a: "Visalia MSA" });
  // Clovis is minutes from Fresno and in the same county. EDD does not name it, so it is
  // unplaced, and no amount of proximity may be allowed to file it under Fresno MSA.
  const clovis = entry({ i: "clovis", c: "Clovis", a: null });
  const all = [placed, elsewhere, clovis];

  it("keeps only the programs the state placed in that exact area", () => {
    const filters = { ...DEFAULT_FILTERS, area: { kind: "area" as const, name: "Fresno MSA" } };
    expect(runSearch(all, filters).map((e) => e.i)).toEqual(["placed"]);
  });

  it("never attributes an unplaced program to a nearby area", () => {
    expect(matchesArea(clovis, { kind: "area", name: "Fresno MSA" })).toBe(false);
  });

  it("selects the unplaced as a group of their own", () => {
    expect(runSearch(all, { ...DEFAULT_FILTERS, area: UNPLACED_AREA }).map((e) => e.i)).toEqual([
      "clovis",
    ]);
  });

  it("returns everything when set to any, including the unplaced", () => {
    expect(runSearch(all, { ...DEFAULT_FILTERS, area: ANY_AREA })).toHaveLength(3);
  });

  it("is inert by default", () => {
    expect(matchesFilters(clovis, DEFAULT_FILTERS)).toBe(true);
  });

  it("combines with the city filter rather than contradicting it", () => {
    const filters = {
      ...DEFAULT_FILTERS,
      area: { kind: "area" as const, name: "Fresno MSA" },
      city: "Visalia",
    };
    expect(runSearch(all, filters)).toEqual([]);
  });
});

describe("unplacedMatches", () => {
  const programs = [
    entry({ i: "a", n: "Welding", a: "Fresno MSA", r: true }),
    entry({ i: "b", n: "Welding", a: null, r: true }),
    entry({ i: "c", n: "Welding", a: null, r: false }),
    entry({ i: "d", n: "Nursing", a: null, r: true }),
  ];

  it("counts what an area selection is hiding, not the whole unplaced population", () => {
    const filters = {
      ...DEFAULT_FILTERS,
      query: "welding",
      area: { kind: "area" as const, name: "Fresno MSA" },
    };
    expect(unplacedMatches(programs, filters)).toBe(2);
  });

  it("still honors every non-geographic filter the reader set", () => {
    const filters = { ...DEFAULT_FILTERS, query: "welding", onlyReported: true };
    expect(unplacedMatches(programs, filters)).toBe(1);
  });

  it("ignores a city selection, which is geography too", () => {
    const filters = { ...DEFAULT_FILTERS, city: "Fresno" };
    expect(unplacedMatches(programs, filters)).toBe(3);
  });

  it("is zero when the state placed everything the search found", () => {
    expect(unplacedMatches([programs[0]!], DEFAULT_FILTERS)).toBe(0);
  });
});

describe("area option values", () => {
  it("round-trips all three states", () => {
    const cases = [ANY_AREA, UNPLACED_AREA, { kind: "area" as const, name: "Fresno MSA" }];
    for (const area of cases) {
      expect(areaFromOptionValue(areaOptionValue(area))).toEqual(area);
    }
  });

  it("keeps an area named like the sentinel distinct from the sentinel", () => {
    const decoy = { kind: "area" as const, name: "unplaced" };
    expect(areaOptionValue(decoy)).not.toBe(areaOptionValue(UNPLACED_AREA));
    expect(areaFromOptionValue(areaOptionValue(decoy))).toEqual(decoy);
  });

  it("falls back to any for an unrecognised value, hiding nothing", () => {
    expect(areaFromOptionValue("")).toEqual(ANY_AREA);
    expect(areaFromOptionValue("garbage")).toEqual(ANY_AREA);
  });
});
