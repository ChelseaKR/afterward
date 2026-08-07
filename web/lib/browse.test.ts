import { describe, expect, it } from "vitest";

import {
  CITY_PREVIEW,
  OTHER_LETTER,
  type OccupationRow,
  type ProviderRow,
  cityPreview,
  descendingUnknownLast,
  groupOccupations,
  groupProvidersByLetter,
  outlookBand,
  programCount,
  programCountsBySoc,
  providerLetter,
  summariseOccupations,
  summariseProviders,
  toProviderRow,
} from "./browse";
import type { SearchEntry } from "./types";

function occupation(partial: Partial<OccupationRow> & { soc: string }): OccupationRow {
  return {
    title: `Occupation ${partial.soc}`,
    openings: 100,
    wage: 50000,
    change: 5,
    education: "High school diploma or equivalent",
    programs: 0,
    ...partial,
  };
}

function entry(partial: Partial<SearchEntry> & { i: string }): SearchEntry {
  return {
    n: "A program",
    p: "A provider",
    c: "Fresno",
    a: "Fresno MSA",
    $: 1000,
    $partial: false,
    at: true,
    w: null,
    s: [],
    o: [],
    g: null,
    op: null,
    cr: null,
    er: null,
    me: null,
    r: false,
    ...partial,
  };
}

function provider(partial: Partial<ProviderRow> & { name: string }): ProviderRow {
  return {
    slug: "slug",
    cities: [],
    programs: 1,
    reporting: 0,
    ...partial,
  };
}

describe("outlook banding", () => {
  it("separates a projection of no change from no projection at all", () => {
    // The whole reason there are four bands rather than three. A zero is California saying
    // it expects the same number of these jobs; a null is California saying nothing.
    expect(outlookBand(0)).toBe("steady");
    expect(outlookBand(null)).toBe("unknown");
  });

  it("reads the sign of a real projection", () => {
    expect(outlookBand(-0.1)).toBe("shrinking");
    expect(outlookBand(12.4)).toBe("growing");
  });
});

describe("descendingUnknownLast", () => {
  it("orders known values largest first", () => {
    expect(descendingUnknownLast(10, 90)).toBeGreaterThan(0);
    expect(descendingUnknownLast(90, 10)).toBeLessThan(0);
  });

  it("puts an unknown after any known value, including a negative one", () => {
    expect(descendingUnknownLast(null, -5000)).toBeGreaterThan(0);
    expect(descendingUnknownLast(-5000, null)).toBeLessThan(0);
  });

  it("never treats an unknown as zero", () => {
    // With `(b ?? 0) - (a ?? 0)` this pair would tie. Tying is the bug: it would let an
    // occupation nobody measured sort as though it had been measured at zero.
    expect(descendingUnknownLast(null, 0)).toBeGreaterThan(0);
    expect(descendingUnknownLast(0, null)).toBeLessThan(0);
  });

  it("leaves two unknowns tied so the next comparison decides", () => {
    expect(descendingUnknownLast(null, null)).toBe(0);
  });
});

describe("grouping occupations", () => {
  const rows = [
    occupation({ soc: "11-0000", change: 4, openings: 50 }),
    occupation({ soc: "12-0000", change: -3, openings: 900 }),
    occupation({ soc: "13-0000", change: 0, openings: 20 }),
    occupation({ soc: "14-0000", change: null, openings: 10 }),
    occupation({ soc: "15-0000", change: 9, openings: 4000 }),
  ];

  it("leads with the shrinking band", () => {
    expect(groupOccupations(rows).map((group) => group.band)).toEqual([
      "shrinking",
      "steady",
      "growing",
      "unknown",
    ]);
  });

  it("orders each band by projected openings, largest first", () => {
    const growing = groupOccupations(rows).find((group) => group.band === "growing");
    expect(growing?.rows.map((row) => row.soc)).toEqual(["15-0000", "11-0000"]);
  });

  it("drops empty bands rather than heading a table with no rows", () => {
    const onlyGrowing = groupOccupations([occupation({ soc: "11-0000", change: 4 })]);
    expect(onlyGrowing.map((group) => group.band)).toEqual(["growing"]);
  });

  it("sorts occupations with no projected openings to the end of their band", () => {
    const mixed = [
      occupation({ soc: "21-0000", change: 3, openings: null, title: "Aaa" }),
      occupation({ soc: "22-0000", change: 3, openings: 1, title: "Zzz" }),
    ];
    const growing = groupOccupations(mixed).find((group) => group.band === "growing");
    expect(growing?.rows.map((row) => row.soc)).toEqual(["22-0000", "21-0000"]);
  });

  it("falls back to the title when openings tie", () => {
    const tied = [
      occupation({ soc: "31-0000", change: 3, openings: 7, title: "Welders" }),
      occupation({ soc: "32-0000", change: 3, openings: 7, title: "Bakers" }),
    ];
    const growing = groupOccupations(tied).find((group) => group.band === "growing");
    expect(growing?.rows.map((row) => row.title)).toEqual(["Bakers", "Welders"]);
  });

  it("does not lose or duplicate a row", () => {
    const grouped = groupOccupations(rows).flatMap((group) => group.rows);
    expect(grouped).toHaveLength(rows.length);
    expect(new Set(grouped.map((row) => row.soc)).size).toBe(rows.length);
  });

  it("counts each band for the summary", () => {
    expect(summariseOccupations(rows)).toEqual({
      total: 5,
      shrinking: 1,
      steady: 1,
      growing: 2,
      unknown: 1,
    });
  });
});

describe("program counts by occupation", () => {
  const programs = [
    entry({ i: "a", s: ["29-2052", "31-9095"] }),
    entry({ i: "b", s: ["29-2052"] }),
    entry({ i: "c", s: [] }),
  ];

  it("counts every program that names the occupation", () => {
    const counts = programCountsBySoc(programs);
    expect(programCount(counts, "29-2052")).toBe(2);
    expect(programCount(counts, "31-9095")).toBe(1);
  });

  it("counts a repeated code on one program once", () => {
    const counts = programCountsBySoc([entry({ i: "d", s: ["11-1011", "11-1011"] })]);
    expect(programCount(counts, "11-1011")).toBe(1);
  });

  it("reports a genuine zero for an occupation with no programs", () => {
    // Unlike every other number on these pages, this zero is a fact about the dataset
    // rather than a missing measure, so it is rendered as a number and not as "not reported".
    expect(programCount(programCountsBySoc(programs), "53-3032")).toBe(0);
  });
});

describe("provider index letters", () => {
  it("files a name under its first letter", () => {
    expect(providerLetter("Fresno City College")).toBe("F");
  });

  it("folds accents so a Spanish name is not stranded", () => {
    expect(providerLetter("Ávila Adult School")).toBe("A");
  });

  it("skips leading punctuation", () => {
    expect(providerLetter('"Best" Trucking Academy')).toBe("B");
  });

  it("gives digits and symbols their own bucket", () => {
    expect(providerLetter("360 Training Institute")).toBe(OTHER_LETTER);
    expect(providerLetter("!!!")).toBe(OTHER_LETTER);
    expect(providerLetter("")).toBe(OTHER_LETTER);
  });

  it("is case-insensitive, which the shouting federal feed requires", () => {
    expect(providerLetter("MERCED COLLEGE")).toBe("M");
  });
});

describe("grouping providers", () => {
  const rows = [
    provider({ name: "Merced College", slug: "merced-college" }),
    provider({ name: "1st Choice Training", slug: "1st-choice-training" }),
    provider({ name: "Allan Hancock College", slug: "allan-hancock-college" }),
    provider({ name: "ABC Adult School", slug: "abc-adult-school" }),
  ];

  it("orders sections A–Z with the leftovers bucket last", () => {
    expect(groupProvidersByLetter(rows).map((group) => group.letter)).toEqual([
      "A",
      "M",
      OTHER_LETTER,
    ]);
  });

  it("sorts alphabetically inside a section", () => {
    const a = groupProvidersByLetter(rows).find((group) => group.letter === "A");
    expect(a?.providers.map((row) => row.name)).toEqual(["ABC Adult School", "Allan Hancock College"]);
  });

  it("keeps every provider", () => {
    const grouped = groupProvidersByLetter(rows).flatMap((group) => group.providers);
    expect(grouped).toHaveLength(rows.length);
  });
});

describe("provider rows", () => {
  it("counts only the programs that reported an outcome", () => {
    const row = toProviderRow({
      slug: "x",
      name: "X College",
      cities: ["Fresno"],
      programs: [entry({ i: "a", r: true }), entry({ i: "b", r: false }), entry({ i: "c", r: true })],
    });
    expect(row).toMatchObject({ programs: 3, reporting: 2 });
  });

  it("reports zero for a provider that published nothing at all", () => {
    // Not "not reported": every program is present and every one of them filed nothing,
    // which is a finding about the provider rather than a gap in the data.
    const row = toProviderRow({
      slug: "y",
      name: "Y Institute",
      cities: [],
      programs: [entry({ i: "a", r: false })],
    });
    expect(row.reporting).toBe(0);
  });

  it("summarises the roster", () => {
    expect(
      summariseProviders([
        provider({ name: "A", programs: 3, reporting: 1 }),
        provider({ name: "B", programs: 2, reporting: 0 }),
      ]),
    ).toEqual({ providers: 2, programs: 5, reportingSome: 1 });
  });
});

describe("city preview", () => {
  it("shows the first few and counts the rest", () => {
    const cities = ["Bakersfield", "Chico", "Fresno", "Merced", "Visalia"];
    expect(cityPreview(cities)).toEqual({
      shown: ["Bakersfield", "Chico", "Fresno"],
      more: cities.length - CITY_PREVIEW,
    });
  });

  it("does not report more when everything fits", () => {
    expect(cityPreview(["Fresno"])).toEqual({ shown: ["Fresno"], more: 0 });
  });

  it("leaves an empty list empty for the caller to mark as unreported", () => {
    expect(cityPreview([])).toEqual({ shown: [], more: 0 });
  });
});
