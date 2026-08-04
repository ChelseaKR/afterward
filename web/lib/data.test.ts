import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import {
  allOccupationCodes,
  allProgramIds,
  getCoverage,
  getSearchIndex,
  programsForOccupation,
} from "./data";

/**
 * These exercise the cached reads against the dataset the build actually consumes, so they
 * need `make data` or `make data-offline` to have run. CI always does that before the web
 * job; a fresh clone has not, and a skipped test there is better than a failing one that
 * says nothing about the code.
 */
const DATA_DIR = join(process.cwd(), "public", "data");
const hasData = existsSync(join(DATA_DIR, "search-index.json"));

function parseFresh<T>(name: string): T {
  return JSON.parse(readFileSync(join(DATA_DIR, name), "utf-8")) as T;
}

describe.skipIf(!hasData)("cached reads", () => {
  it("parses the search index once and hands back the same object", () => {
    expect(getSearchIndex()).toBe(getSearchIndex());
  });

  it("parses coverage once and hands back the same object", () => {
    expect(getCoverage()).toBe(getCoverage());
  });

  it("returns exactly what is on disk, nulls and all", () => {
    // The whole point of the null contract: caching must not coerce, default, or drop
    // anything. A deep equality against a fresh parse is the strongest form of that check.
    expect(getSearchIndex()).toEqual(parseFresh("search-index.json"));
    expect(getCoverage()).toEqual(parseFresh("coverage.json"));
  });

  it("keeps suppressed measures as null rather than zero", () => {
    const fresh = parseFresh<{ programs: Record<string, unknown>[] }>("search-index.json");
    const suppressed = fresh.programs.filter((p) => p.me === null).length;
    expect(getSearchIndex().programs.filter((p) => p.me === null)).toHaveLength(suppressed);
  });

  it("freezes the shared records, so one page cannot corrupt another", () => {
    const index = getSearchIndex();
    expect(Object.isFrozen(index)).toBe(true);
    expect(Object.isFrozen(index.programs)).toBe(true);
    expect(Object.isFrozen(index.programs[0])).toBe(true);
    expect(Object.isFrozen(index.programs[0]?.s)).toBe(true);
    expect(Object.isFrozen(getCoverage().peer_medians)).toBe(true);
  });
});

describe.skipIf(!hasData)("id listings", () => {
  it("lists every program file", () => {
    const onDisk = readdirSync(join(DATA_DIR, "programs")).filter((f) => f.endsWith(".json"));
    expect(allProgramIds()).toHaveLength(onDisk.length);
    expect(allOccupationCodes().length).toBeGreaterThan(0);
  });

  it("hands out a fresh array each call, so a caller may sort it", () => {
    const first = allProgramIds();
    const second = allProgramIds();
    expect(first).not.toBe(second);
    expect(first).toEqual(second);
    expect(() => first.sort()).not.toThrow();
    // Sorting one copy must not have disturbed the cached listing.
    expect(allProgramIds()).toEqual(second);
  });
});

describe.skipIf(!hasData)("programsForOccupation", () => {
  it("returns only programs that list the SOC, in a fresh array", () => {
    const soc = getSearchIndex().programs.flatMap((p) => p.s)[0];
    expect(soc).toBeDefined();
    const programs = programsForOccupation(soc as string);
    expect(programs.length).toBeGreaterThan(0);
    expect(programs.every((p) => p.s.includes(soc as string))).toBe(true);
    expect(programsForOccupation(soc as string)).not.toBe(programs);
  });

  it("returns nothing for an occupation no program trains for", () => {
    expect(programsForOccupation("00-0000")).toEqual([]);
  });
});
