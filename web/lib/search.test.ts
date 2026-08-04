import { describe, expect, it } from "vitest";

import { DEFAULT_FILTERS, matchesFilters, runSearch, score, terms } from "./search";
import type { SearchEntry } from "./types";

function entry(overrides: Partial<SearchEntry> = {}): SearchEntry {
  return {
    i: "id",
    n: "Medical Assisting",
    p: "Fresno City College",
    c: "Fresno",
    $: 4000,
    w: 30,
    s: ["31-9092"],
    o: "Medical Assistants",
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
    const byOccupation = score(entry({ n: "Program", o: "Nursing Assistants" }), ["nursing"]);
    const byCity = score(entry({ n: "Program", o: "Other", c: "Nursing City" }), ["nursing"]);
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
    const sparse = entry({ n: null, p: null, o: null, c: null });
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

  it("hideShrinking removes known-negative growth only", () => {
    const filters = { ...DEFAULT_FILTERS, hideShrinking: true };
    expect(matchesFilters(entry({ g: -5 }), filters)).toBe(false);
    expect(matchesFilters(entry({ g: 5 }), filters)).toBe(true);
  });

  it("hideShrinking keeps programs whose growth is unknown", () => {
    // Unknown is not shrinking. Dropping these would hide programs for an unstated reason.
    const filters = { ...DEFAULT_FILTERS, hideShrinking: true };
    expect(matchesFilters(entry({ g: null }), filters)).toBe(true);
  });

  it("maxCost excludes programs with no reported cost", () => {
    // A cost cap is a budget promise; a program that never said what it costs cannot honour it.
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
