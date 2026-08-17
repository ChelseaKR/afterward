/**
 * Every page this site serves, read off the app rather than remembered.
 *
 * Two gates walk a hand-written list of pages: the accessibility audit and the first-visit
 * transfer budget. A hand-written list is a claim about the site, and the site is the thing
 * that changes -- so the list is right until somebody adds a route, at which point both gates
 * go on passing over a sample that no longer describes what is published. Nothing says so.
 * That is the same failure `a11y-audit.mjs` already refuses one step later, where a page it
 * is told to read and cannot is treated as unaudited rather than as passing: a sample has to
 * be stated, and then checked against reality, or it is not a sample but a habit.
 *
 * So the app router's own file tree is the authority here. `app/[lang]/about/page.tsx` is
 * `/[lang]/about` and there is no second place to declare it. A new `page.tsx` therefore
 * fails every gate that consumes this until its list names the page -- which is the whole
 * point, and the reason this returns templates rather than URLs: 3,266 program pages are one
 * route and one representative audits them all, while a route with no representative at all
 * is not covered by anything.
 *
 * `LANGUAGES` is parsed out of `lib/i18n.ts` for the same reason: it is where the array that
 * drives `generateStaticParams` actually lives, and a third language must not be able to
 * arrive with half the site unaudited.
 */

import { existsSync, readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";

export const APP_DIR = fileURLToPath(new URL("../app", import.meta.url));
export const I18N_FILE = fileURLToPath(new URL("../lib/i18n.ts", import.meta.url));

/** Next's route groups: a directory in parentheses organises files and is not a URL segment. */
const ROUTE_GROUP = /^\(.*\)$/;

/**
 * The languages `generateStaticParams` builds, from the one array that decides it.
 *
 * Read as text because this is an `.mjs` script and that is a `.ts` module; `tests/
 * test_site_copy.py` reads the same file the same way and for the same reason. A parse
 * failure throws rather than defaulting to `["en", "es"]`: a silent default here would let
 * this file quietly stop noticing a language, which is the class of bug it exists to catch.
 */
export function languages(i18nFile = I18N_FILE) {
  const source = readFileSync(i18nFile, "utf-8");
  const match = source.match(/export const LANGUAGES = \[([^\]]*)\]/);
  if (!match) {
    throw new Error(`${i18nFile}: no 'export const LANGUAGES = [...]' to read the locales from`);
  }
  const found = [...match[1].matchAll(/["'`]([a-z-]+)["'`]/g)].map((m) => m[1]);
  if (found.length === 0) throw new Error(`${i18nFile}: LANGUAGES is empty`);
  return found;
}

/**
 * Every route template the app router will emit a page for, as `/`-joined segments.
 *
 * Dynamic segments keep their brackets (`/[lang]/programs/[id]`), because that is what makes
 * this a list of page *kinds*. `not-found.tsx` is included as `/404`: it is exported as
 * `404.html`, it is a page a reader lands on, and it is not declared by a `page.tsx`.
 */
export function routeTemplates(appDir = APP_DIR) {
  const found = [];

  const walk = (dir, segments) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        const segment = ROUTE_GROUP.test(entry.name) ? null : entry.name;
        walk(join(dir, entry.name), segment === null ? segments : [...segments, segment]);
      } else if (entry.name === "page.tsx" || entry.name === "page.jsx") {
        found.push(`/${segments.join("/")}`);
      } else if (entry.name === "not-found.tsx" || entry.name === "not-found.jsx") {
        found.push("/404");
      }
    }
  };

  if (!existsSync(appDir)) throw new Error(`${appDir}: no app directory to read routes from`);
  walk(appDir, []);
  return [...new Set(found)].sort();
}

/**
 * A route template as a matcher over an exported file's path, relative to the export root.
 *
 * `/[lang]/programs/[id]` matches `en/programs/anything/index.html`. `lang` is substituted
 * rather than wildcarded so a caller can ask about one language at a time, which is what
 * lets a gate insist on both instead of accepting whichever it happens to have.
 */
export function exportedPagePattern(template, lang) {
  if (template === "/404") return /^404\.html$/;
  const segments = template
    .split("/")
    .filter(Boolean)
    .map((segment) => {
      if (segment === "[lang]") return lang;
      return segment.startsWith("[") ? "[^/]+" : segment.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    });
  return new RegExp(`^${[...segments, "index\\.html"].join("/")}$`);
}

/** True when `template` has a `[lang]` segment and so is built once per language. */
export function isPerLanguage(template) {
  return template.split("/").includes("[lang]");
}

/**
 * Which route templates no path in `paths` covers, and in which language.
 *
 * The returned strings are what a gate prints, so they name the template and the language
 * rather than a file: the operator's next move is to add a page to a list, not to look for a
 * file that was never built.
 *
 * `langs` is which languages the calling gate insists on seeing, defaulting to all of them.
 * The accessibility audit takes the default, because a page that exists in English and not in
 * Spanish is half a page and its markup differs. The transfer budget passes `["en"]`: it is
 * measuring the weight of a template, the two locales of one template weigh the same to
 * within a rounding error, and measuring both would double a slow pass for no signal.
 */
export function uncovered(paths, { appDir = APP_DIR, i18nFile = I18N_FILE, langs } = {}) {
  const normalised = paths.filter(Boolean).map((path) => path.split("\\").join("/"));
  const wanted = langs ?? languages(i18nFile);
  const missing = [];
  for (const template of routeTemplates(appDir)) {
    for (const lang of isPerLanguage(template) ? wanted : [null]) {
      const pattern = exportedPagePattern(template, lang);
      if (!normalised.some((path) => pattern.test(path))) {
        missing.push(lang === null ? template : `${template} (${lang})`);
      }
    }
  }
  return missing;
}
