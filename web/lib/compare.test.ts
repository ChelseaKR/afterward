import { describe, expect, it } from "vitest";

import { bestOf } from "./compare";
import type { SearchEntry } from "./types";

function entry(overrides: Partial<SearchEntry> = {}): SearchEntry {
  return {
    i: "id",
    n: "Program",
    p: "Provider",
    c: "Fresno",
    a: "Fresno MSA",
    $: 4000,
    $partial: false,
    w: 30,
    s: [],
    o: ["Occupation"],
    g: 10,
    wage: 45000,
    op: 500,
    cr: 0.8,
    er: 0.7,
    me: 32000,
    r: true,
    ...overrides,
  };
}

/**
 * The comparison highlights the strongest reported figure in each row. Getting this wrong
 * would recommend a training program to someone on the strength of a number nobody filed.
 */
describe("bestOf", () => {
  it("picks the highest when higher is better", () => {
    const entries = [entry({ me: 20000 }), entry({ me: 50000 }), entry({ me: 30000 })];
    expect(bestOf(entries, (e) => e.me, "high")).toBe(1);
  });

  it("picks the lowest when lower is better", () => {
    const entries = [entry({ $: 9000 }), entry({ $: 1000 }), entry({ $: 5000 })];
    expect(bestOf(entries, (e) => e.$, "low")).toBe(1);
  });

  it("ignores unreported values rather than treating them as zero", () => {
    // A null cost is not free, and a null salary is not $0.
    const entries = [entry({ $: null }), entry({ $: 5000 }), entry({ $: 3000 })];
    expect(bestOf(entries, (e) => e.$, "low")).toBe(2);

    const earnings = [entry({ me: null }), entry({ me: 10000 }), entry({ me: 20000 })];
    expect(bestOf(earnings, (e) => e.me, "high")).toBe(2);
  });

  it("marks nothing when only one program reported the measure", () => {
    // Being the only provider willing to file a number is not the same as being the best,
    // and highlighting it would reward disclosure as if it were performance.
    const entries = [entry({ me: 50000 }), entry({ me: null }), entry({ me: null })];
    expect(bestOf(entries, (e) => e.me, "high")).toBeNull();
  });

  it("marks nothing when no program reported the measure", () => {
    const entries = [entry({ me: null }), entry({ me: null })];
    expect(bestOf(entries, (e) => e.me, "high")).toBeNull();
  });

  it("marks nothing on a tie", () => {
    const entries = [entry({ $: 5000 }), entry({ $: 5000 }), entry({ $: 9000 })];
    expect(bestOf(entries, (e) => e.$, "low")).toBeNull();
  });

  it("treats a reported zero as a real value", () => {
    // 0% employed is a devastating fact, not a missing one, and must be able to lose.
    const entries = [entry({ er: 0 }), entry({ er: 0.5 })];
    expect(bestOf(entries, (e) => e.er, "high")).toBe(1);

    // And a genuine $0 cost is the cheapest, not an absence.
    const free = [entry({ $: 0 }), entry({ $: 5000 })];
    expect(bestOf(free, (e) => e.$, "low")).toBe(0);
  });

  it("handles negative growth correctly when higher is better", () => {
    const entries = [entry({ g: -15 }), entry({ g: -2 }), entry({ g: null })];
    expect(bestOf(entries, (e) => e.g, "high")).toBe(1);
  });
});
