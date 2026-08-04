/**
 * Provider grouping.
 *
 * Derived from the program records rather than from a separate feed: the federal providers
 * index carries no California rows at all, but every program names its provider, so the
 * roster is reconstructed from those.
 *
 * This module is reachable from a client component (`SearchApp` imports `slugify`), so it
 * stays free of `node:` imports and of anything that only exists during the build.
 */

import type { SearchEntry } from "./types";

export interface Provider {
  slug: string;
  name: string;
  cities: string[];
  programs: SearchEntry[];
}

/**
 * URL-safe slug for a provider name.
 *
 * Accents are stripped for the URL only — the displayed name keeps them. A Spanish-named
 * college should not have its name mangled on screen just because a URL cannot carry an
 * accent.
 */
export function slugify(name: string): string {
  return name
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
}

interface Roster {
  providers: Provider[];
  bySlug: Map<string, Provider>;
}

/**
 * Rosters already built, keyed by the exact program array they were built from.
 *
 * The static export asks for the roster once per provider page, again for that page's
 * metadata, and again for each browse index and the sitemap — some 2,300 times over a
 * 3,266-row index, all of them producing the identical answer. Keying on the array itself
 * rather than on a "loaded" flag means invalidation needs no bookkeeping here: `data.ts`
 * hands back a new array whenever the file on disk changes, and a new array simply misses.
 * A WeakMap also keeps this module from retaining one-off arrays built by callers or tests.
 */
const rosters = new WeakMap<SearchEntry[], Roster>();

function roster(programs: SearchEntry[]): Roster {
  const hit = rosters.get(programs);
  if (hit !== undefined) return hit;

  const built = buildRoster(programs);
  rosters.set(programs, built);
  return built;
}

/**
 * Group programs by provider.
 *
 * Providers are keyed by slug, so two spellings that normalize identically ("FRESNO CITY
 * COLLEGE" and "Fresno City College") become one provider rather than two near-duplicates.
 * The longest spelling wins as the display name, since it is the least likely to be
 * truncated.
 *
 * The result is frozen because it is shared between pages. Callers that need to reorder a
 * provider's programs copy first (`[...provider.programs].sort(...)`); freezing is what
 * stops a future caller from forgetting to.
 */
function buildRoster(programs: SearchEntry[]): Roster {
  const groups = new Map<string, { names: string[]; programs: SearchEntry[] }>();

  for (const program of programs) {
    const name = program.p?.trim();
    if (!name) continue;
    const slug = slugify(name);
    if (!slug) continue;

    const existing = groups.get(slug);
    if (existing) {
      existing.names.push(name);
      existing.programs.push(program);
    } else {
      groups.set(slug, { names: [name], programs: [program] });
    }
  }

  const providers = [...groups.entries()]
    .map(([slug, { names, programs: owned }]) => {
      const provider: Provider = {
        slug,
        name: names.reduce((a, b) => (b.length > a.length ? b : a)),
        cities: [...new Set(owned.map((p) => p.c).filter((c): c is string => Boolean(c)))].sort(),
        programs: owned,
      };
      Object.freeze(provider.cities);
      Object.freeze(provider.programs);
      Object.freeze(provider);
      return provider;
    })
    .sort((a, b) => b.programs.length - a.programs.length || a.name.localeCompare(b.name));

  Object.freeze(providers);
  return { providers, bySlug: new Map(providers.map((p) => [p.slug, p])) };
}

export function groupByProvider(programs: SearchEntry[]): Provider[] {
  return roster(programs).providers;
}

/** One provider by slug. A lookup rather than a scan, off the same cached roster. */
export function findProvider(programs: SearchEntry[], slug: string): Provider | null {
  return roster(programs).bySlug.get(slug) ?? null;
}
