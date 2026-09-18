/**
 * Canonical and hreflang audit over the static export.
 *
 * Every other check on this is a statement about the source. This one reads the bytes that
 * get uploaded, which is the only place a `<link rel="canonical">` either exists or does not.
 * `lib/alternates.test.ts` asserts that each page's `generateMetadata` returns the right
 * object; between that object and the published head sits Next's metadata resolver, which
 * merges layout metadata into descendants, replaces rather than merges some keys, and has
 * already cost this project ~9,000 pages' worth of wrong canonical once. A green unit suite
 * over a head nobody read is how that happened.
 *
 * ---- What is compared against what ----
 *
 * The export's own `sitemap.xml` is the authority, and both sides of every comparison are
 * generated. `app/sitemap.ts` writes the URLs and their language alternates; each page writes
 * its own canonical; this reads both out of the same build and refuses any disagreement.
 * Nothing here holds a list of pages, so there is no list to go stale.
 *
 * The two annotations are checked in the two different places they live, which is the point:
 *
 * - **The canonical is a claim each page makes about itself**, so it is checked in each
 *   page's head. Before this work no page in the site made it; the only canonical anywhere
 *   in the export was on `/`, and it was the relative string `/en/`.
 * - **hreflang is declared by the sitemap**, completely -- 18,092 reciprocal `<xhtml:link>`
 *   entries over 9,046 URLs -- and it always was. What was missing was any gate on it. A
 *   sitemap that quietly stopped emitting alternates, or emitted a one-way set, would have
 *   broken the site's entire bilingual-search story with a green build and no symptom, since
 *   a one-way `hreflang` is discarded by search engines and looks exactly like none.
 *
 * What fails the gate:
 *
 *   1. a URL in the sitemap with no page in the export -- a 404 advertised to crawlers;
 *   2. a page whose canonical is missing, relative, duplicated, or names a different URL;
 *   3. a sitemap entry whose alternates are not reciprocal: a URL that names its twin
 *      without the twin naming it back, or that leaves itself out of its own set;
 *   4. a page whose head carries hreflang alternates that contradict the sitemap. The head
 *      deliberately carries none, so that two declarations of one relationship cannot
 *      disagree; this is what keeps that decision from being undone by accident;
 *   5. an exported page that is neither in the sitemap nor `noindex` and carries no canonical
 *      of its own. `/[lang]/about/` is in this class deliberately -- it is indexable and has
 *      never been in the sitemap -- and it still has to say which URL it is.
 *
 * And, before any of it, the gate refuses to report a pass over nothing: an empty sitemap, an
 * export with no pages, or a route template the export never built are all failures rather
 * than a short run that prints "0 problems".
 *
 * Usage: node scripts/seo-audit.mjs [outDir]
 */

import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join, relative, sep } from "node:path";

import { uncovered } from "./routes.mjs";

const OUT = process.argv.slice(2).find((arg) => !arg.startsWith("--")) ?? "out";

/**
 * The floor under the sweep.
 *
 * Not a target. The production dataset publishes 4,523 pairs and CI's 60-program fixture
 * publishes far fewer, so this sits below both and above anything a collapse would leave:
 * a sitemap that failed to render its detail routes, a data file that arrived empty, an
 * `outDir` pointed at the wrong directory. Every one of those would otherwise pass silently,
 * because a loop over nothing finds nothing wrong.
 */
const MIN_PAIRS = 20;

/** Every `.html` file in the export, as paths relative to it. */
function exportedPages(dir) {
  const found = [];
  const walk = (current) => {
    for (const entry of readdirSync(current, { withFileTypes: true })) {
      const path = join(current, entry.name);
      if (entry.isDirectory()) walk(path);
      else if (entry.name.endsWith(".html")) found.push(relative(dir, path).split(sep).join("/"));
    }
  };
  walk(dir);
  return found.sort();
}

/**
 * The sitemap's URLs and the alternates it declares for each.
 *
 * Parsed with regular expressions rather than an XML library, deliberately: this file is
 * checking that two generated documents agree, and pulling in a parser to read one of them
 * would add a dependency to a gate whose whole job is to need nothing. The shape is Next's
 * own `MetadataRoute.Sitemap` output and is stable.
 */
function sitemapEntries(xml) {
  const entries = [];
  for (const [, block] of xml.matchAll(/<url>([\s\S]*?)<\/url>/g)) {
    const loc = block.match(/<loc>([^<]+)<\/loc>/)?.[1];
    if (!loc) continue;
    const alternates = {};
    for (const [, lang, href] of block.matchAll(
      /<xhtml:link[^>]*\bhreflang="([^"]+)"[^>]*\bhref="([^"]+)"[^>]*\/?>/gi,
    )) {
      alternates[lang] = href;
    }
    entries.push({ loc, alternates });
  }
  return entries;
}

/**
 * Every `<link rel="canonical">` href on a page. More than one is itself a finding.
 *
 * Matched case-insensitively, and that is not defensive tidiness. React serializes the
 * property name, so the export carries `hrefLang="en"` where the sitemap carries
 * `hreflang="en"` -- HTML attribute names are case-insensitive and both are correct, but a
 * gate that pattern-matched only the lowercase form would find zero alternates on all ~9,000
 * pages and report them all broken, or, with the comparison the other way round, find zero
 * and have nothing to complain about. This gate is here to notice absence; a matcher that
 * cannot see what is present is the same defect wearing the opposite sign.
 */
function canonicals(html) {
  return [...html.matchAll(/<link[^>]+rel="canonical"[^>]*>/gi)].map(
    (tag) => tag[0].match(/\bhref="([^"]*)"/i)?.[1] ?? "",
  );
}

/** Every `<link rel="alternate" hreflang=…>` on a page, as hreflang to href. */
function alternates(html) {
  const found = {};
  for (const [tag] of html.matchAll(/<link[^>]+rel="alternate"[^>]*>/gi)) {
    const lang = tag.match(/\bhreflang="([^"]*)"/i)?.[1];
    const href = tag.match(/\bhref="([^"]*)"/i)?.[1];
    if (lang !== undefined) found[lang] = href ?? "";
  }
  return found;
}

/** A page that tells crawlers not to index it owes them no canonical and no alternates. */
function isNoindex(html) {
  return /<meta[^>]+name="robots"[^>]*content="[^"]*noindex/i.test(html);
}

/** The export file a sitemap URL should have been written to: `…/en/x/` -> `en/x/index.html`. */
function pageFor(loc, origin) {
  const path = loc.slice(origin.length).replace(/^\//, "");
  return `${path}${path.endsWith("/") || path === "" ? "" : "/"}index.html`;
}

const problems = [];
const fail = (message) => problems.push(message);

if (!existsSync(OUT)) {
  console.error(`seo-audit: ${OUT}: no export to audit. Run \`npm run build\` first.`);
  process.exit(1);
}

const sitemapPath = join(OUT, "sitemap.xml");
if (!existsSync(sitemapPath)) {
  console.error(`seo-audit: ${sitemapPath}: the export has no sitemap to check the pages against`);
  process.exit(1);
}

const entries = sitemapEntries(readFileSync(sitemapPath, "utf-8"));
const pages = exportedPages(OUT);

// ---- The sweep is a sweep, checked before anything is allowed to pass ----

const origin = entries[0]?.loc.match(/^https?:\/\/[^/]+/)?.[0];
if (!origin) {
  console.error("seo-audit: the sitemap declares no absolute URLs — nothing to audit against");
  process.exit(1);
}

const pairs = new Set(entries.map(({ loc }) => loc.slice(origin.length).replace(/^\/[^/]+/, "")));
if (pairs.size < MIN_PAIRS) {
  console.error(
    `seo-audit: the sweep collapsed — ${entries.length} sitemap URLs over ${pairs.size} ` +
      `records, below the floor of ${MIN_PAIRS}. Passing this would prove nothing.`,
  );
  process.exit(1);
}

const missingRoutes = uncovered(pages);
if (missingRoutes.length > 0) {
  console.error("seo-audit: the export is missing pages the app router declares:");
  for (const route of missingRoutes) console.error(`  ${route}`);
  process.exit(1);
}

// ---- Every URL the sitemap publishes ----

/** Each URL's declared alternates, by URL, so reciprocity can be checked in both directions. */
const byLoc = new Map(entries.map(({ loc, alternates: declared }) => [loc, declared]));

const inSitemap = new Set();

for (const { loc, alternates: declared } of entries) {
  const file = pageFor(loc, origin);
  inSitemap.add(file);

  if (!pages.includes(file)) {
    fail(`${loc}: in the sitemap, but ${file} was never built`);
    continue;
  }

  const html = readFileSync(join(OUT, file), "utf-8");
  const found = canonicals(html);

  if (found.length === 0) fail(`${file}: no <link rel="canonical">`);
  else if (found.length > 1) fail(`${file}: ${found.length} canonicals, which names none of them`);
  else if (found[0] !== loc) fail(`${file}: canonical is ${found[0]}, sitemap says ${loc}`);

  // hreflang lives in the sitemap, deliberately and solely. A head that also declared it
  // would be a second copy of a working annotation, and two descriptions of one relationship
  // are two things that can disagree with nothing to say which a crawler believed. This is
  // the check that keeps that decision deliberate: a page may carry no alternates, or ones
  // that agree with the sitemap, but never ones that contradict it.
  for (const [lang, href] of Object.entries(alternates(html))) {
    if (declared[lang] !== undefined && declared[lang] !== href) {
      fail(`${file}: head says hreflang="${lang}" is ${href}, sitemap says ${declared[lang]}`);
    }
  }

  // Reciprocity, which is the whole of hreflang. A set that names the other language without
  // naming itself, or whose twin does not name it back, is one-way -- and a one-way
  // annotation is discarded by search engines, which looks exactly like publishing none.
  // Never gated before this; the sitemap has emitted it correctly for months with nothing
  // that would have noticed if it stopped.
  if (Object.keys(declared).length === 0) fail(`${loc}: the sitemap declares no alternates`);
  else if (!Object.values(declared).includes(loc)) {
    fail(`${loc}: its own alternate set does not name it, so every alternate on it is one-way`);
  } else {
    for (const href of Object.values(declared)) {
      const twin = byLoc.get(href);
      if (twin === undefined) fail(`${loc}: names ${href} as an alternate, which is not in the sitemap`);
      else if (!Object.values(twin).includes(loc)) {
        fail(`${loc}: names ${href} as an alternate, and ${href} does not name it back`);
      }
    }
  }
}

// ---- Every page the export built, whether or not the sitemap advertises it ----

for (const file of pages) {
  if (inSitemap.has(file)) continue;

  const html = readFileSync(join(OUT, file), "utf-8");
  if (isNoindex(html)) continue;

  const found = canonicals(html);
  if (found.length !== 1) {
    fail(
      `${file}: indexable, absent from the sitemap, and carries ${found.length} canonicals. ` +
        "An indexable page has to say which URL it is.",
    );
  } else if (!found[0].startsWith("https://")) {
    fail(`${file}: canonical "${found[0]}" is relative; a reader resolves it against itself`);
  }
}

// ---- Verdict, naming what was read ----

if (problems.length > 0) {
  console.error(`seo-audit: ${problems.length} problems over ${pages.length} exported pages`);
  for (const problem of problems.slice(0, 40)) console.error(`  ${problem}`);
  if (problems.length > 40) console.error(`  … and ${problems.length - 40} more`);
  process.exit(1);
}

const hreflangs = entries.reduce((total, { alternates: a }) => total + Object.keys(a).length, 0);

console.log(
  `seo-audit: ${entries.length} sitemap URLs over ${pairs.size} records, ` +
    `${pages.length} exported pages — every one self-canonical against the sitemap, ` +
    `and ${hreflangs} hreflang alternates all reciprocal`,
);
