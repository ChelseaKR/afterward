import { describe, expect, it } from "vitest";

import { findProvider, groupByProvider, slugify } from "./providers";
import type { SearchEntry } from "./types";

function entry(overrides: Partial<SearchEntry> = {}): SearchEntry {
  return {
    i: "id",
    n: "Program",
    p: "Fresno City College",
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

describe("slugify", () => {
  it("makes a URL-safe slug", () => {
    expect(slugify("Fresno City College")).toBe("fresno-city-college");
  });

  it("collapses case differences, so one provider is not two", () => {
    expect(slugify("FRESNO CITY COLLEGE")).toBe(slugify("Fresno City College"));
  });

  it("strips accents for the URL", () => {
    expect(slugify("Colegio Español")).toBe("colegio-espanol");
  });

  it("spells out ampersands rather than dropping them", () => {
    // "Health & Safety" and "Health Safety" should not collide silently.
    expect(slugify("Health & Safety Institute")).toBe("health-and-safety-institute");
  });

  it("trims punctuation from the ends", () => {
    expect(slugify("  ...Adult Education!  ")).toBe("adult-education");
  });

  it("returns an empty slug for a name with nothing usable", () => {
    expect(slugify("!!!")).toBe("");
  });
});

describe("groupByProvider", () => {
  it("merges spellings that normalise to the same slug", () => {
    const providers = groupByProvider([
      entry({ i: "a", p: "FRESNO CITY COLLEGE" }),
      entry({ i: "b", p: "Fresno City College" }),
    ]);
    expect(providers).toHaveLength(1);
    expect(providers[0]?.programs).toHaveLength(2);
  });

  it("keeps the longest spelling as the display name", () => {
    const providers = groupByProvider([
      entry({ i: "a", p: "Fresno City College" }),
      entry({ i: "b", p: "Fresno City College" }),
    ]);
    expect(providers[0]?.name).toBe("Fresno City College");
  });

  it("collects every city a provider operates in", () => {
    const providers = groupByProvider([
      entry({ i: "a", c: "Fresno" }),
      entry({ i: "b", c: "Clovis" }),
      entry({ i: "c", c: "Fresno" }),
    ]);
    expect(providers[0]?.cities).toEqual(["Clovis", "Fresno"]);
  });

  it("orders providers by how many programs they run", () => {
    const providers = groupByProvider([
      entry({ i: "a", p: "Small School" }),
      entry({ i: "b", p: "Big School" }),
      entry({ i: "c", p: "Big School" }),
    ]);
    expect(providers.map((p) => p.name)).toEqual(["Big School", "Small School"]);
  });

  it("skips programs with no provider rather than inventing one", () => {
    const providers = groupByProvider([entry({ p: null }), entry({ p: "   " })]);
    expect(providers).toEqual([]);
  });

  it("produces unique slugs, since each becomes a page", () => {
    const providers = groupByProvider([
      entry({ i: "a", p: "Alpha College" }),
      entry({ i: "b", p: "Beta College" }),
      entry({ i: "c", p: "alpha college" }),
    ]);
    const slugs = providers.map((p) => p.slug);
    expect(new Set(slugs).size).toBe(slugs.length);
  });

  it("reuses the roster it already built for the same programs", () => {
    const programs = [entry({ i: "a" })];
    expect(groupByProvider(programs)).toBe(groupByProvider(programs));
  });

  it("regroups when handed a different array, so new data is never stale", () => {
    const first = groupByProvider([entry({ i: "a", p: "Alpha College" })]);
    const second = groupByProvider([entry({ i: "b", p: "Beta College" })]);
    expect(first).not.toBe(second);
    expect(second.map((p) => p.name)).toEqual(["Beta College"]);
  });

  it("freezes what it returns, since pages share it", () => {
    const providers = groupByProvider([entry({ i: "a" })]);
    const provider = providers[0];
    expect(Object.isFrozen(providers)).toBe(true);
    expect(Object.isFrozen(provider)).toBe(true);
    expect(Object.isFrozen(provider?.programs)).toBe(true);
    expect(Object.isFrozen(provider?.cities)).toBe(true);
    // A page that wants a different order or an extra row has to copy first, which is what
    // the pages do. Mutating the shared roster in place fails loudly instead.
    expect(() => provider?.programs.push(entry({ i: "z" }))).toThrow(TypeError);
  });
});

describe("findProvider", () => {
  it("finds a provider by slug", () => {
    const found = findProvider([entry()], "fresno-city-college");
    expect(found?.name).toBe("Fresno City College");
  });

  it("returns null for an unknown slug", () => {
    expect(findProvider([entry()], "no-such-school")).toBeNull();
  });

  it("returns the same provider object the grouping returned", () => {
    const programs = [entry()];
    expect(findProvider(programs, "fresno-city-college")).toBe(groupByProvider(programs)[0]);
  });
});
