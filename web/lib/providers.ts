/**
 * Provider grouping.
 *
 * Derived from the program records rather than from a separate feed: the federal providers
 * index carries no California rows at all, but every program names its provider, so the
 * roster is reconstructed from those.
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

/**
 * Group programs by provider.
 *
 * Providers are keyed by slug, so two spellings that normalise identically ("FRESNO CITY
 * COLLEGE" and "Fresno City College") become one provider rather than two near-duplicates.
 * The longest spelling wins as the display name, since it is the least likely to be
 * truncated.
 */
export function groupByProvider(programs: SearchEntry[]): Provider[] {
  const bySlug = new Map<string, { names: string[]; programs: SearchEntry[] }>();

  for (const program of programs) {
    const name = program.p?.trim();
    if (!name) continue;
    const slug = slugify(name);
    if (!slug) continue;

    const existing = bySlug.get(slug);
    if (existing) {
      existing.names.push(name);
      existing.programs.push(program);
    } else {
      bySlug.set(slug, { names: [name], programs: [program] });
    }
  }

  return [...bySlug.entries()]
    .map(([slug, { names, programs: owned }]) => ({
      slug,
      name: names.reduce((a, b) => (b.length > a.length ? b : a)),
      cities: [...new Set(owned.map((p) => p.c).filter((c): c is string => Boolean(c)))].sort(),
      programs: owned,
    }))
    .sort((a, b) => b.programs.length - a.programs.length || a.name.localeCompare(b.name));
}

export function findProvider(programs: SearchEntry[], slug: string): Provider | null {
  return groupByProvider(programs).find((provider) => provider.slug === slug) ?? null;
}
