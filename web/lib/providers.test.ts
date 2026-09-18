import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { findProvider, groupByProvider, providerPopulation, slugify } from "./providers";
import type { SearchEntry } from "./types";

/**
 * The identity table both languages are held to.
 *
 * `slugify` here mints the URL; `provider_slug` in `src/afterward/providers.py` counts the
 * providers `coverage.json` publishes. Neither can call the other, so the rule is written
 * twice and this file is what stops that from being two rules — `tests/test_providers.py`
 * asserts the same rows. A change to either implementation that the table does not sanction
 * turns the other language's suite red. See #155.
 */
const IDENTITY = JSON.parse(
  readFileSync(fileURLToPath(new URL("../../fixtures/provider-identity.json", import.meta.url)), "utf-8"),
) as { cases: { name: string; slug: string }[]; collisions: [string, string][] };

function entry(overrides: Partial<SearchEntry> = {}): SearchEntry {
  return {
    i: "id",
    n: "Program",
    p: "Fresno City College",
    c: "Fresno",
    a: "Fresno MSA",
    $: 4000,
    $partial: false,
    at: true,
    w: 30,
    s: [],
    o: ["Occupation"],
    g: 10,
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

describe("the shared identity table", () => {
  it("has cases in it", () => {
    // A table that emptied itself would pass every assertion below it without being read.
    expect(IDENTITY.cases.length).toBeGreaterThanOrEqual(15);
    expect(IDENTITY.collisions.length).toBeGreaterThanOrEqual(4);
  });

  it("slugs every case the way the table says, and so does the pipeline", () => {
    const wrong = IDENTITY.cases
      .filter((entry) => slugify(entry.name) !== entry.slug)
      .map((entry) => ({ name: entry.name, got: slugify(entry.name), want: entry.slug }));
    expect(wrong).toEqual([]);
  });

  it("merges every pair the table calls one provider", () => {
    for (const [first, second] of IDENTITY.collisions) {
      expect(first).not.toBe(second);
      expect(slugify(first)).toBe(slugify(second));
      expect(slugify(first)).not.toBe("");
    }
  });

  it("keeps the filings that made the About page and the index disagree", () => {
    // Named rather than counted, so an edit cannot quietly drop the evidence for #155 while
    // leaving the table the right size.
    const names = new Set(IDENTITY.cases.map((entry) => entry.name));
    for (const name of [
      "PROCAREER ACADEMY",
      "Procareer Academy",
      "DIALYSIS EDUCATION SERVICES LLC",
      "Dialysis Education Services, LLC",
      "Virtual Design & Construction Institute",
      "Virtual Design and Construction Institute",
    ]) {
      expect(names).toContain(name);
    }
  });
});

describe("providerPopulation", () => {
  /** Six filings from three providers: the shape that made one snapshot publish two numbers. */
  const sixFilings = [
    entry({ i: "a", p: "PROCAREER ACADEMY" }),
    entry({ i: "b", p: "Procareer Academy" }),
    entry({ i: "c", p: "DIALYSIS EDUCATION SERVICES LLC" }),
    entry({ i: "d", p: "Dialysis Education Services, LLC" }),
    entry({ i: "e", p: "Virtual Design & Construction Institute" }),
    entry({ i: "f", p: "Virtual Design and Construction Institute" }),
  ];

  it("counts the providers a reader can go and visit, not the names on file", () => {
    expect(new Set(sixFilings.map((e) => e.p)).size).toBe(6);
    expect(providerPopulation(sixFilings, 3)).toBe(3);
  });

  it("agrees with the roster that mints the provider pages", () => {
    expect(providerPopulation(sixFilings, 3)).toBe(groupByProvider(sixFilings).length);
  });

  it("refuses to build when coverage.json declares a different number", () => {
    // The old About-page figure, on these six filings. A static export that shipped both is
    // the defect; there is no rendering of the disagreement better than not shipping it.
    expect(() => providerPopulation(sixFilings, 6)).toThrow(/Two provider counts for one snapshot/);
    expect(() => providerPopulation(sixFilings, 6)).toThrow(/roster holds 3 and coverage.json declares 6/);
  });

  it("does not count a filing whose name carries no identity", () => {
    const withBlanks = [
      entry({ i: "a", p: "Merced College" }),
      entry({ i: "b", p: "!!!" }),
      entry({ i: "c", p: "   " }),
    ];
    expect(providerPopulation(withBlanks, 1)).toBe(1);
  });
});

describe("groupByProvider", () => {
  it("merges spellings that normalize to the same slug", () => {
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
