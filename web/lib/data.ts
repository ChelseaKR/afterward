/**
 * Build-time data access. Runs only in server components during the static export, so the
 * pipeline's JSON never has to be served as a whole to anyone.
 *
 * Everything under `public/data` is an input, not state: the Python pipeline writes those
 * files and exits, and no part of the site ever writes to them. Reading each one once and
 * holding it is therefore safe, and worth doing — the export renders roughly nine thousand
 * pages, every one of which comes back through here, and the search index alone is a
 * megabyte of JSON to re-parse each time.
 */

import { readFileSync, readdirSync, existsSync, statSync } from "node:fs";
import { join } from "node:path";

import type { Coverage, Occupation, Program, SearchIndex } from "./types";

const DATA_DIR = join(process.cwd(), "public", "data");

interface CacheEntry {
  /** Identity of the file this value was parsed from, not merely "have we read it yet". */
  stamp: string;
  value: unknown;
}

const cache = new Map<string, CacheEntry>();

/**
 * Cheap identity for a file or directory: size, last-modified time and inode.
 *
 * `next build` runs in a fresh process (several, in fact — the export is farmed out to
 * workers), so a build could never inherit an earlier build's cache regardless. The case
 * that matters is `next dev`, whose process outlives `make data` and `make data-offline`.
 * Either of those rewrites the whole of `public/data` underneath a running dev server, and
 * a cache keyed on "already loaded" would go on serving the fixture dataset after the real
 * one replaced it — or the reverse. Stamping each entry makes that impossible: the next
 * read sees a different file and re-parses. A stat costs about two microseconds against
 * roughly six milliseconds to re-parse the index, so this correctness is close to free.
 */
function stamp(path: string): string {
  const { size, mtimeMs, ino } = statSync(path);
  return `${size}:${mtimeMs}:${ino}`;
}

function cached<T>(path: string, load: () => T): T {
  const current = stamp(path);
  const hit = cache.get(path);
  if (hit !== undefined && hit.stamp === current) return hit.value as T;

  const value = load();
  cache.set(path, { stamp: current, value });
  return value;
}

/**
 * Freeze a parsed record and everything beneath it.
 *
 * A cached record is shared by every page in the export, so an in-place sort in one page
 * component would silently reorder another page's data — the kind of corruption that shows
 * up as a wrong number on a page nobody looks at again. Freezing turns that into an
 * immediate TypeError at the point of the mistake.
 *
 * Nothing here rewrites a value. A frozen null is still null: "not reported or suppressed"
 * survives caching exactly as it survived parsing.
 */
function deepFreeze<T>(value: T): T {
  if (value === null || typeof value !== "object" || Object.isFrozen(value)) return value;
  Object.freeze(value);
  for (const inner of Object.values(value)) deepFreeze(inner);
  return value;
}

function cachedJson<T>(...segments: string[]): T {
  const path = join(DATA_DIR, ...segments);
  return cached(path, () => deepFreeze(JSON.parse(readFileSync(path, "utf-8")) as T));
}

export function getSearchIndex(): SearchIndex {
  return cachedJson<SearchIndex>("search-index.json");
}

export function getCoverage(): Coverage {
  return cachedJson<Coverage>("coverage.json");
}

/**
 * One program record.
 *
 * Deliberately not cached. Each record is read exactly twice — once for the page's metadata
 * and once for the page — and holding them all would mean every export worker retaining the
 * entire program corpus for the life of the build. That is a lot of memory for a fraction of
 * a second, and unlike the search index there is no repeated work worth eliminating.
 */
export function getProgram(id: string): Program | null {
  const path = join(DATA_DIR, "programs", `${id}.json`);
  return existsSync(path) ? (JSON.parse(readFileSync(path, "utf-8")) as Program) : null;
}

/** One occupation record. Uncached, for the same reason as `getProgram`. */
export function getOccupation(soc: string): Occupation | null {
  const path = join(DATA_DIR, "occupations", `${soc}.json`);
  return existsSync(path) ? (JSON.parse(readFileSync(path, "utf-8")) as Occupation) : null;
}

function idsIn(dir: string): string[] {
  const path = join(DATA_DIR, dir);
  if (!existsSync(path)) return [];

  const ids = cached<readonly string[]>(path, () =>
    Object.freeze(
      readdirSync(path)
        .filter((f) => f.endsWith(".json"))
        .map((f) => f.slice(0, -".json".length)),
    ),
  );

  // A fresh array per call. These lists are handed to callers that may reasonably sort or
  // otherwise rearrange them, and copying a few thousand strings costs far less than
  // listing a directory of a few thousand files.
  return [...ids];
}

export const allProgramIds = (): string[] => idsIn("programs");
export const allOccupationCodes = (): string[] => idsIn("occupations");

/**
 * Programs that train for a given occupation, for the occupation page.
 *
 * Filters rather than caches per SOC: `getSearchIndex()` is now a single parse, so this is
 * one pass over an array already in memory, and the result is a fresh array the caller owns.
 */
export function programsForOccupation(soc: string): SearchIndex["programs"] {
  return getSearchIndex().programs.filter((p) => p.s.includes(soc));
}

/**
 * An occupation's title in the reader's language: O*NET's Spanish where it exists, the
 * English otherwise.
 *
 * Centralised because the alternative is worse than not translating at all. When only the
 * occupation detail page spoke Spanish, a Spanish reader met "Pharmacy Technicians" on a
 * program page, clicked it, and arrived at "Técnicos de Farmacia" — two names for one job,
 * with nothing on either page explaining that they are the same. Consistency is the point.
 *
 * Falls back rather than throwing: 70 of California's 670 occupations have no Mi Próximo
 * Paso record, and their pages carry the English name on purpose.
 */
export function occupationTitleIn(
  lang: string,
  soc: string | null | undefined,
  fallback: string | null,
): string | null {
  if (lang !== "es" || soc === null || soc === undefined) return fallback;
  return getOccupation(soc)?.spanish?.title ?? fallback;
}
