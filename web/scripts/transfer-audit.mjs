/**
 * What a real browser actually pulls down for one page, prefetches included.
 *
 * ---------------------------------------------------------------------------------------
 * Why this exists next to size-report.mjs
 * ---------------------------------------------------------------------------------------
 * `size-report.mjs` answers two questions from files alone: how big the export is on disk,
 * and what one route's document plus its scripts and stylesheets weigh compressed. Both are
 * worth knowing and neither can see the thing that actually dominated this site's traffic.
 *
 * Next prefetches a `<Link>` when it scrolls into view, and a prefetch is a runtime decision
 * that leaves no trace in any built file. So a static reading of `/en/about/` said 180 KiB
 * while a browser opening the same page fetched 538 KiB — the difference being the masthead
 * and back-links quietly pulling down the search route, the two browse indexes, and their
 * JavaScript, none of which the reader asked for. Nothing in the build could have caught
 * that, because nothing in the build ran a router.
 *
 * Hence: a real Chromium, against the real export, recording every request. Sizes are the
 * brotli-compressed bytes of the file each request resolves to, which is what CloudFront
 * serves — not the bytes this throwaway server happens to send uncompressed.
 *
 * Not part of `npm run verify`, deliberately, and for the same reason `a11y:browser` is not:
 * CI installs the playwright package but no browsers, so wiring this into the gate would
 * fail every CI run on a missing binary rather than on anything true about the site. It is a
 * tool for a person changing how the site loads. Run it when you touch prefetching, add a
 * client component, or move data across the server/client boundary.
 *
 * Usage:
 *   npm run build
 *   node scripts/transfer-audit.mjs out /en/ /en/about/
 *   node scripts/transfer-audit.mjs out              # a representative page of each shape
 */

import { createServer } from "node:http";
import { readFileSync, existsSync, statSync, readdirSync } from "node:fs";
import { join, extname } from "node:path";
import { brotliCompressSync, constants } from "node:zlib";

import { chromium } from "playwright";

const args = process.argv.slice(2);
const OUT = args[0] ?? "out";
const PORT = 8951;

const CONTENT_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".txt": "text/plain",
  ".xml": "application/xml",
};

/**
 * Map a URL to a file the way a static host does: a trailing-slash path is a directory with
 * an index.html in it. Query strings are dropped — the router appends a `_rsc` cache-buster
 * to every prefetch, and it addresses the same file.
 */
function resolveFile(urlPath) {
  const path = decodeURIComponent(urlPath.split("?")[0]);
  let file = join(OUT, path);
  if (existsSync(file) && statSync(file).isDirectory()) file = join(file, "index.html");
  return existsSync(file) && statSync(file).isFile() ? file : null;
}

const brotliCache = new Map();

/** Brotli at quality 11, matching what a CDN serves for a cacheable static object. */
function brotliSize(file) {
  if (!brotliCache.has(file)) {
    brotliCache.set(
      file,
      brotliCompressSync(readFileSync(file), {
        params: { [constants.BROTLI_PARAM_QUALITY]: 11 },
      }).length,
    );
  }
  return brotliCache.get(file);
}

/** The first page directory under `dir`, so the defaults follow the dataset. */
function firstPageUnder(dir) {
  const path = join(OUT, dir);
  if (!existsSync(path)) return null;
  for (const entry of readdirSync(path, { withFileTypes: true })) {
    if (entry.isDirectory() && existsSync(join(path, entry.name, "index.html"))) {
      return `/${dir}/${entry.name}/`;
    }
  }
  return null;
}

function defaultPaths() {
  return [
    "/en/",
    "/en/occupations/",
    "/en/providers/",
    "/en/about/",
    firstPageUnder("en/programs"),
    firstPageUnder("en/occupations"),
    firstPageUnder("en/providers"),
  ].filter((p) => p !== null);
}

if (!existsSync(OUT)) {
  console.error(`No such directory: ${OUT}. Run \`npm run build\` first.`);
  process.exit(1);
}

const paths = args.length > 1 ? args.slice(1) : defaultPaths();

const server = createServer((request, response) => {
  const file = resolveFile(request.url);
  if (file === null) {
    response.writeHead(404);
    response.end();
    return;
  }
  response.writeHead(200, {
    "content-type": CONTENT_TYPES[extname(file)] ?? "application/octet-stream",
  });
  response.end(readFileSync(file));
});

await new Promise((resolve) => server.listen(PORT, resolve));
const browser = await chromium.launch();

console.log(`Transfer per first visit, brotli, cold cache — measured in Chromium\n`);

for (const path of paths) {
  // A fresh context per page: a shared cache would report the second page as nearly free and
  // hide exactly the cost being measured.
  const context = await browser.newContext();
  const page = await context.newPage();

  const requested = new Map();
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (!requested.has(url.pathname)) {
      requested.set(url.pathname, Boolean(request.headers()["next-router-prefetch"]));
    }
  });

  await page.goto(`http://localhost:${PORT}${path}`, { waitUntil: "networkidle" });
  // Prefetches are scheduled off the main thread after load; without this pause they land
  // after the measurement and the page looks half its real weight.
  await page.waitForTimeout(3000);

  const rows = [];
  for (const [urlPath, prefetched] of requested) {
    const file = resolveFile(urlPath);
    if (file === null) continue;
    rows.push({ urlPath, prefetched, bytes: brotliSize(file) });
  }
  rows.sort((a, b) => b.bytes - a.bytes);

  const total = rows.reduce((sum, row) => sum + row.bytes, 0);
  const speculative = rows.filter((r) => r.prefetched).reduce((sum, row) => sum + row.bytes, 0);

  console.log(`${path}`);
  console.log(
    `  ${(total / 1024).toFixed(1)} KiB over ${rows.length} requests, ` +
      `of which ${(speculative / 1024).toFixed(1)} KiB was prefetched rather than asked for`,
  );
  for (const row of rows) {
    console.log(
      `  ${String(row.bytes).padStart(9)}  ${row.prefetched ? "prefetch" : "        "}  ${row.urlPath}`,
    );
  }
  console.log();

  await context.close();
}

await browser.close();
server.close();
