/**
 * Build-time data access. Runs only in server components during the static export, so the
 * pipeline's JSON never has to be served as a whole to anyone.
 */

import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join } from "node:path";

import type { Coverage, Occupation, Program, SearchIndex } from "./types";

const DATA_DIR = join(process.cwd(), "public", "data");

function readJson<T>(...segments: string[]): T {
  return JSON.parse(readFileSync(join(DATA_DIR, ...segments), "utf-8")) as T;
}

export function getSearchIndex(): SearchIndex {
  return readJson<SearchIndex>("search-index.json");
}

export function getCoverage(): Coverage {
  return readJson<Coverage>("coverage.json");
}

export function getProgram(id: string): Program | null {
  const path = join(DATA_DIR, "programs", `${id}.json`);
  return existsSync(path) ? (JSON.parse(readFileSync(path, "utf-8")) as Program) : null;
}

export function getOccupation(soc: string): Occupation | null {
  const path = join(DATA_DIR, "occupations", `${soc}.json`);
  return existsSync(path) ? (JSON.parse(readFileSync(path, "utf-8")) as Occupation) : null;
}

function idsIn(dir: string): string[] {
  const path = join(DATA_DIR, dir);
  if (!existsSync(path)) return [];
  return readdirSync(path)
    .filter((f) => f.endsWith(".json"))
    .map((f) => f.slice(0, -".json".length));
}

export const allProgramIds = (): string[] => idsIn("programs");
export const allOccupationCodes = (): string[] => idsIn("occupations");

/** Programs that train for a given occupation, for the occupation page. */
export function programsForOccupation(soc: string): SearchIndex["programs"] {
  return getSearchIndex().programs.filter((p) => p.s.includes(soc));
}
