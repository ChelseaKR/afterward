import { describe, expect, it } from "vitest";

import { NEARBY_SHOWN, areaPlace, nearbyPrograms, statewideJob } from "./nearby";
import type { SearchEntry } from "./types";

function entry(i: string, a: string | null, s: string[], n: string | null = `Program ${i}`): SearchEntry {
  return {
    i,
    n,
    p: `Provider ${i}`,
    c: "Vallejo",
    a,
    $: null,
    $partial: false,
    at: true,
    w: null,
    s,
    o: [],
    g: null,
    op: null,
    cr: null,
    er: null,
    me: null,
    r: false,
  };
}

const VALLEJO = "Vallejo MSA";
const self = entry("self", VALLEJO, ["29-2055", "31-9093", "25-1071"], "Sterile Processing");

describe("nearbyPrograms", () => {
  it("lists only programs in the same area that share at least one job", () => {
    const programs = [
      self,
      entry("same-area-shared", VALLEJO, ["29-2055"]),
      entry("same-area-unrelated", VALLEJO, ["47-2111"]),
      entry("other-area-shared", "Napa MSA", ["29-2055"]),
      entry("unplaced-shared", null, ["29-2055"]),
    ];
    const { listed, total } = nearbyPrograms(self, programs);
    expect(listed.map((p) => p.i)).toEqual(["same-area-shared"]);
    expect(total).toBe(1);
  });

  it("never lists the program itself", () => {
    expect(nearbyPrograms(self, [self]).listed).toEqual([]);
  });

  it("orders by how many jobs are shared, then by name, and uses no figure", () => {
    const programs = [
      // Better outcomes and a lower cost must not move a program up the list.
      { ...entry("b", VALLEJO, ["29-2055"], "Beta"), er: 0.99, $: 100 },
      entry("z", VALLEJO, ["29-2055", "31-9093"], "Zeta"),
      { ...entry("a", VALLEJO, ["31-9093"], "Alpha"), er: 0.1, $: 90000 },
      entry("unnamed", VALLEJO, ["29-2055"], null),
    ];
    expect(nearbyPrograms(self, programs).listed.map((p) => p.i)).toEqual([
      "z",
      "a",
      "b",
      "unnamed",
    ]);
  });

  it("counts a job listed twice on the other program once", () => {
    const programs = [
      entry("twice", VALLEJO, ["29-2055", "29-2055"], "Twice"),
      entry("two", VALLEJO, ["29-2055", "31-9093"], "Two"),
    ];
    expect(nearbyPrograms(self, programs).listed.map((p) => p.i)).toEqual(["two", "twice"]);
  });

  it(`shows at most ${NEARBY_SHOWN} and reports how many qualified`, () => {
    const programs = Array.from({ length: 8 }, (_, k) => entry(`n${k}`, VALLEJO, ["29-2055"]));
    const { listed, total } = nearbyPrograms(self, programs);
    expect(listed).toHaveLength(NEARBY_SHOWN);
    expect(total).toBe(8);
  });

  it("gives a program with no area no list, rather than another area's programs", () => {
    const unplaced = entry("unplaced", null, ["29-2055"]);
    const programs = [entry("x", VALLEJO, ["29-2055"]), entry("y", null, ["29-2055"])];
    expect(nearbyPrograms(unplaced, programs)).toEqual({ listed: [], total: 0 });
  });

  it("gives a program with no job codes no list", () => {
    const programs = [entry("x", VALLEJO, ["29-2055"])];
    expect(nearbyPrograms(entry("none", VALLEJO, []), programs)).toEqual({ listed: [], total: 0 });
  });
});

describe("statewideJob", () => {
  const counts = new Map([
    ["25-1071", 40],
    ["29-2055", 14],
    ["31-9093", 6],
    ["47-2111", 1],
  ]);

  it("names the job the listed programs share most", () => {
    const listed = [entry("x", VALLEJO, ["29-2055"]), entry("y", VALLEJO, ["29-2055", "31-9093"])];
    expect(statewideJob(self.s, listed, counts)).toEqual({ soc: "29-2055", programs: 14 });
  });

  it("falls back to the program's own order when nothing is listed", () => {
    expect(statewideJob(self.s, [], counts)).toEqual({ soc: "29-2055", programs: 14 });
  });

  it("never offers a statewide list of one, which would be this program alone", () => {
    expect(statewideJob(["47-2111"], [], counts)).toBeNull();
    expect(statewideJob(["99-9999"], [], counts)).toBeNull();
  });
});

describe("areaPlace", () => {
  it("drops the kind of area EDD appends, and nothing else", () => {
    expect(areaPlace("Vallejo MSA")).toBe("Vallejo");
    expect(areaPlace("Los Angeles-Long Beach-Glendale MD")).toBe("Los Angeles-Long Beach-Glendale");
    expect(areaPlace("North Coast Region")).toBe("North Coast");
    expect(areaPlace("Eastern Sierra-Mother Lode Region")).toBe("Eastern Sierra-Mother Lode");
  });

  it("leaves a name with no such suffix as it is", () => {
    expect(areaPlace("Fresno")).toBe("Fresno");
  });
});
