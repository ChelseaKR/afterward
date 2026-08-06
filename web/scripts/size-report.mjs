/**
 * Size report for the static export, and the one prune that is provably safe.
 *
 * ---------------------------------------------------------------------------------------
 * What the export is actually made of
 * ---------------------------------------------------------------------------------------
 * `output: "export"` with ~9,000 pages produces roughly 715 MiB across ~49,000 files, and
 * almost none of that is markup. Every page directory holds the same RSC payload up to four
 * times:
 *
 *   index.html                     the rendered markup, plus the payload again inline in
 *                                  `self.__next_f.push(...)` so React can hydrate
 *   index.txt                      the payload, fetched by the client router when it
 *                                  navigates to a route it has not prefetched
 *   __next._full.txt               the payload again, byte for byte identical to index.txt
 *   __next.<segment>.__PAGE__.txt  the page segment alone, fetched by the segment cache
 *                                  when a <Link> prefetches
 *   __next._tree.txt               the route tree for that URL, ~600 bytes
 *
 * Three of those five are load-bearing and this script does not touch them:
 *
 *   - `index.html` carries the inline payload React hydrates from. Stripping it would turn
 *     every page into unhydratable markup.
 *   - `index.txt` is what `fetchServerResponse` requests: the router appends `index.txt` to
 *     any path ending in `/`. That is the navigation path taken whenever the route cache has
 *     no fulfilled entry — a `router.push`, a link clicked before its prefetch landed, a
 *     prefetch suppressed by Data Saver, or an entry past its 300s stale time.
 *   - `__next.<segment>.__PAGE__.txt` and `__next._tree.txt` are what the client segment
 *     cache requests when a `<Link>` enters the viewport.
 *
 * ---------------------------------------------------------------------------------------
 * Why `__next._full.txt` is different
 * ---------------------------------------------------------------------------------------
 * `_full` is written by the server renderer (`collect-segment-data.js` does
 * `resultMap.set('/_full', fullPageDataBuffer)`) so that a *running Next server* can answer
 * a segment-prefetch request for the whole page out of the same map. The static exporter
 * copies every entry in that map to disk, `_full` included.
 *
 * A browser never asks for it. `convertSegmentPathToStaticExportFilename` is the only thing
 * that turns a segment path into a `__next.*.txt` URL, and the only segment paths the client
 * ever hands it are the route-tree key, `/_tree`, `/_head` and `/_index`. The string
 * `_full` appears nowhere in Next's client bundle, and nowhere in a single byte this site
 * serves — it survives only as a filename. Meanwhile its contents are byte-for-byte the
 * same as the `index.txt` sitting beside it, which the client *does* request.
 *
 * So it is ~20% of the export, ~18% of the objects in the bucket, and dead. `--prune`
 * removes it, behind two interlocks that make the deletion self-checking rather than a
 * belief about a Next version:
 *
 *   1. no shipped chunk under `_next/static` may mention `_full` — if a future release
 *      starts requesting it, that string appears and pruning is refused outright;
 *   2. each file must be byte-identical to the `index.txt` beside it, so the bytes are
 *      demonstrably still reachable at another URL before this one is removed.
 *
 * A refusal is a warning, never an error. The worst case is a larger upload, and failing a
 * deploy over a size optimization would be a far more expensive mistake than shipping one
 * duplicate file per page.
 *
 * ---------------------------------------------------------------------------------------
 * The second report, and why the first one is not enough
 * ---------------------------------------------------------------------------------------
 * Everything above measures the export *on disk*, uncompressed: a hosting bill, and a real
 * one. It is not what any visitor pays. CloudFront serves this site brotli-compressed, and a
 * visitor fetches one route, not 40,000 files — so the disk report can look healthy while
 * the page a person actually opens has quietly become a megabyte, and it can look alarming
 * over duplication that costs a reader nothing.
 *
 * The two numbers diverge by more than an order of magnitude here. `/en/` is 1.38 MiB of
 * HTML on disk and 118 KB on the wire. Nothing in this build measured the second one, which
 * is the only one an equity argument can be made from: this site is for people deciding
 * whether to spend a year and several thousand dollars on training, and a fair share of them
 * arrive on a phone, on a metered connection, or on library wifi. So `reportTransfer` below
 * measures what a first visit costs — document plus every script and stylesheet it
 * references, brotli-compressed — and `MAX_ROUTE_TRANSFER` is a ceiling on it.
 *
 * The budget is an error rather than a warning, unlike the prune refusal above. The two are
 * not the same kind of failure: refusing to prune wastes our money, and blowing this budget
 * spends the reader's. Set with real headroom, so it catches a dataset being inlined into a
 * page and not a paragraph of copy being added.
 *
 * Usage:
 *   node scripts/size-report.mjs [outDir]            # measure only
 *   node scripts/size-report.mjs [outDir] --prune    # measure, prune, measure again
 */

import { readdirSync, readFileSync, statSync, unlinkSync, existsSync } from "node:fs";
import { join } from "node:path";
import { brotliCompressSync, constants } from "node:zlib";

const args = process.argv.slice(2);
const PRUNE = args.includes("--prune");
const OUT = args.find((a) => !a.startsWith("--")) ?? "out";

const DUPLICATE = "__next._full.txt";
/** The sibling whose bytes must match before a duplicate is removed. */
const CANONICAL = "index.txt";
/** `public/` is copied verbatim into the export; this is where it lands. */
const DATA_DIR = join(OUT, "data");

/** Every file, once, with its size. One walk feeds both the report and the prune. */
function walk(dir, files = []) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) walk(path, files);
    else if (entry.isFile()) files.push({ path, name: entry.name, size: statSync(path).size });
  }
  return files;
}

/**
 * Categories chosen to answer "where is the bulk", not to mirror file extensions. The four
 * RSC families are separated because they are the whole question: collapsing them into
 * "text files" is how 435 MiB of near-duplicate payload stays invisible.
 */
function categorize({ path, name }) {
  if (name === DUPLICATE) return "RSC __next._full.txt (duplicate of index.txt)";
  if (name === "__next._tree.txt") return "RSC __next._tree.txt (route tree)";
  if (name.startsWith("__next.") && name.endsWith("__PAGE__.txt")) {
    return "RSC __next.<segment>.__PAGE__.txt (segment prefetch)";
  }
  if (name === CANONICAL) return "RSC index.txt (client navigation)";
  if (name.endsWith(".html")) return "HTML (markup + inline hydration payload)";
  if (name.endsWith(".json")) {
    return path.startsWith(DATA_DIR) ? "JSON (public/data, copied verbatim)" : "JSON (other)";
  }
  if (name.endsWith(".js")) return "JS";
  if (name.endsWith(".css")) return "CSS";
  if (name.endsWith(".xml")) return "XML (sitemap)";
  return "other";
}

const MiB = 1024 * 1024;
const mib = (bytes) => (bytes / MiB).toFixed(2).padStart(9);

function report(files, heading) {
  const totals = new Map();
  for (const file of files) {
    const key = categorize(file);
    const row = totals.get(key) ?? { bytes: 0, count: 0 };
    row.bytes += file.size;
    row.count += 1;
    totals.set(key, row);
  }

  const bytes = files.reduce((sum, f) => sum + f.size, 0);
  console.log(`\n${heading}`);
  console.log("      MiB      %    files  category");
  for (const [key, row] of [...totals].sort((a, b) => b[1].bytes - a[1].bytes)) {
    const pct = ((100 * row.bytes) / bytes).toFixed(1).padStart(5);
    console.log(`${mib(row.bytes)} ${pct}  ${String(row.count).padStart(7)}  ${key}`);
  }
  console.log(`${mib(bytes)} 100.0  ${String(files.length).padStart(7)}  TOTAL`);
  return { bytes, count: files.length };
}

/**
 * Interlock 1. Not a version check: the question is whether *this* bundle can construct a
 * `_full` URL, and the bundle is right there to be read.
 */
function clientMentionsDuplicate() {
  const staticDir = join(OUT, "_next", "static");
  if (!existsSync(staticDir)) return true; // No bundle to clear it: assume the worst.
  return walk(staticDir)
    .filter((f) => f.name.endsWith(".js"))
    .some((f) => readFileSync(f.path, "utf-8").includes("_full"));
}

function prune(files) {
  const candidates = files.filter((f) => f.name === DUPLICATE);
  if (candidates.length === 0) {
    console.log("\nNothing to prune.");
    return files;
  }

  if (clientMentionsDuplicate()) {
    console.log(
      `\n::warning::Refusing to prune: a shipped chunk references "_full", so this ` +
        `build may request ${DUPLICATE}. Left ${candidates.length} file(s) in place.`,
    );
    return files;
  }

  let removed = 0;
  let bytes = 0;
  const kept = [];
  for (const file of candidates) {
    const canonical = join(file.path.slice(0, -DUPLICATE.length), CANONICAL);
    if (!existsSync(canonical) || !readFileSync(canonical).equals(readFileSync(file.path))) {
      kept.push(file.path);
      continue;
    }
    unlinkSync(file.path);
    removed += 1;
    bytes += file.size;
  }

  console.log(
    `\nPruned ${removed} x ${DUPLICATE} (${(bytes / MiB).toFixed(2)} MiB), ` +
      `each byte-identical to the ${CANONICAL} beside it.`,
  );
  if (kept.length > 0) {
    console.log(
      `::warning::${kept.length} ${DUPLICATE} file(s) did not match their ${CANONICAL} ` +
        `and were left alone, starting with ${kept[0]}.`,
    );
  }
  return files.filter((f) => f.name !== DUPLICATE || kept.includes(f.path));
}

/* ==========================================================================================
 * Transfer size: what a first visit actually costs
 * ======================================================================================== */

const KiB = 1024;
const kib = (bytes) => (bytes / KiB).toFixed(1).padStart(8);

/**
 * Ceiling on one route's first visit, brotli-compressed. `/en/` measures ~332 KiB against
 * this, essentially all of it the search index inlined in the document plus the framework.
 *
 * Chosen as a ceiling with meaning rather than a ratchet one byte above today: a budget that
 * trips on ordinary work gets raised without being read, which is worse than no budget. This
 * one has room for a page to grow and none for a second copy of the dataset.
 */
const MAX_ROUTE_TRANSFER = 420 * KiB;

/**
 * Routes to measure. One per shape the site has, not one per page: 9,000 pages come out of
 * seven templates, so seven representatives describe all of them, and the two indexes and
 * the search page are where the weight has ever actually been.
 *
 * `sample` picks the first page under a directory, so the program and occupation rows follow
 * the dataset instead of naming a UUID that a rebuild can retire.
 */
const ROUTES = [
  { label: "/en/ (search)", path: "en" },
  { label: "/en/occupations/", path: "en/occupations" },
  { label: "/en/providers/", path: "en/providers" },
  { label: "/en/paying-for-training/", path: "en/paying-for-training" },
  { label: "/en/about/", path: "en/about" },
  { label: "/en/programs/<id>/", sample: "en/programs" },
  { label: "/en/occupations/<soc>/", sample: "en/occupations" },
];

const brotliCache = new Map();

/** Brotli at quality 11, which is what CloudFront serves for a cacheable static object. */
function brotli(path) {
  if (!brotliCache.has(path)) {
    const bytes = brotliCompressSync(readFileSync(path), {
      params: { [constants.BROTLI_PARAM_QUALITY]: 11 },
    }).length;
    brotliCache.set(path, bytes);
  }
  return brotliCache.get(path);
}

/** The first page directory under `dir`, or null when the dataset produced none. */
function firstPageUnder(dir) {
  const path = join(OUT, dir);
  if (!existsSync(path)) return null;
  for (const entry of readdirSync(path, { withFileTypes: true })) {
    if (entry.isDirectory() && existsSync(join(path, entry.name, "index.html"))) {
      return join(dir, entry.name);
    }
  }
  return null;
}

/**
 * What a browser must download to render and hydrate one route, cold.
 *
 * Read out of the built HTML rather than from a manifest, because the question is what *this
 * document* references — a manifest describes what the router might need, and the two have
 * disagreed before. Scripts and stylesheets are counted once each even where the document
 * names them twice (as a preload and again as a tag), which is what the browser does too.
 *
 * Deliberately NOT counted: anything a `<Link>` prefetches. Prefetch is a runtime decision
 * and cannot be read off a static file — which is exactly how ~400 KiB of speculative
 * fetching per page went unnoticed until someone put a browser in front of the built site.
 * `chromeWeight` below is the standing reminder of what that traffic would cost if it were
 * ever switched back on.
 */
function transferOf(route) {
  const dir = route.sample ? firstPageUnder(route.sample) : route.path;
  if (dir === null) return null;

  const document = join(OUT, dir, "index.html");
  if (!existsSync(document)) return null;

  const html = readFileSync(document, "utf-8");
  const assets = new Set(html.match(/\/_next\/static\/[A-Za-z0-9_\-./]+\.(?:js|css)/g) ?? []);

  let js = 0;
  let css = 0;
  for (const asset of assets) {
    const path = join(OUT, asset.replace(/^\//, ""));
    if (!existsSync(path)) continue;
    if (asset.endsWith(".css")) css += brotli(path);
    else js += brotli(path);
  }

  const documentBytes = brotli(document);
  return { document: documentBytes, js, css, total: documentBytes + js + css };
}

/**
 * What prefetching the masthead routes from every page would cost, per page.
 *
 * The masthead links to the search page and the two browse indexes on all ~9,000 pages, so
 * whenever those links prefetch, every visitor pays this on top of the page they asked for,
 * whether or not they ever press one. Measured in Chromium on 2026-08-05 it was ~402 KiB per
 * page — five times the weight of an actual program page — so the links carry
 * `prefetch={false}` (see app/[lang]/layout.tsx). This line exists so that the number is in
 * front of anyone who reconsiders that, rather than in a commit message they will not read.
 *
 * Counted as the router fetches it: the route's `__PAGE__.txt` segment payload and its route
 * tree. The document itself is fetched too, and is not added here — the point is the order
 * of magnitude, and the segment payload alone makes it.
 */
function chromeWeight() {
  let bytes = 0;
  for (const dir of ["en", "en/occupations", "en/providers", "en/paying-for-training"]) {
    const base = join(OUT, dir);
    if (!existsSync(base)) continue;
    for (const name of readdirSync(base)) {
      if (name.startsWith("__next.") && name.endsWith("__PAGE__.txt")) {
        bytes += brotli(join(base, name));
      } else if (name === "__next._tree.txt") {
        bytes += brotli(join(base, name));
      }
    }
  }
  return bytes;
}

/** Returns the number of routes over budget, having reported all of them. */
function reportTransfer() {
  console.log(`\nTransfer size of a first visit, brotli (what CloudFront serves): ${OUT}`);
  console.log("     KiB      doc       js      css  route");

  let over = 0;
  for (const route of ROUTES) {
    const measured = transferOf(route);
    if (measured === null) {
      console.log(`${"—".padStart(8)}                             ${route.label} (not built)`);
      continue;
    }
    const flag = measured.total > MAX_ROUTE_TRANSFER ? "  << OVER BUDGET" : "";
    if (measured.total > MAX_ROUTE_TRANSFER) over += 1;
    console.log(
      `${kib(measured.total)} ${kib(measured.document)} ${kib(measured.js)} ${kib(measured.css)}  ` +
        `${route.label}${flag}`,
    );
  }

  console.log(
    `\nBudget ${(MAX_ROUTE_TRANSFER / KiB).toFixed(0)} KiB per route. ` +
      `Masthead routes would add ${(chromeWeight() / KiB).toFixed(1)} KiB per page if their ` +
      `links prefetched; they do not.`,
  );
  return over;
}

if (!existsSync(OUT)) {
  console.error(`No such directory: ${OUT}. Run \`next build\` first.`);
  process.exit(1);
}

const files = walk(OUT);
const before = report(files, `Static export size: ${OUT}`);
if (PRUNE) {
  const after = report(prune(files), `After prune: ${OUT}`);
  const saved = before.bytes - after.bytes;
  console.log(
    `\nReclaimed ${(saved / MiB).toFixed(2)} MiB ` +
      `(${((100 * saved) / before.bytes).toFixed(1)}%) and ` +
      `${before.count - after.count} objects.`,
  );
}

// Last, and the only thing here that can fail a build. Everything above is a bill we pay;
// this is one a reader pays, on a connection they may be metering.
const over = reportTransfer();
if (over > 0) {
  console.error(
    `\n${over} route(s) exceed the ${(MAX_ROUTE_TRANSFER / KiB).toFixed(0)} KiB first-visit ` +
      `budget. Find what grew before raising it: the usual cause is data being inlined into ` +
      `a page instead of fetched from it.`,
  );
  process.exit(1);
}
