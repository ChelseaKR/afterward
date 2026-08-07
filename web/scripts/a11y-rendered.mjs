/**
 * The accessibility gate audits the search page before the search has rendered (#29).
 *
 * `npm run a11y` reads the static export. On `/en/` and `/es/` that export is the chrome —
 * the filter panel, the sort control, the masthead — and none of the results: everything
 * `SearchApp.tsx` shows is fetched from `search-index.json` and rendered client-side after
 * hydration, so it is not in the document jsdom parses. The comparison table is the same
 * story one level further in: it does not exist until a reader selects two programs and
 * opens it. #21 — the comparison's best-in-row mark had no text alternative — lived in
 * exactly this unaudited region and was found by reading the code, not by any gate.
 *
 * This starts Chromium against the real static export, waits for the result list to
 * actually populate, and audits it with axe's full rule set (not just the two layout-
 * dependent rules `a11y-browser.mjs` runs) — then selects two programs, opens the
 * comparison, and audits again with the table in the DOM. It serves `out/` itself on a
 * free port for the duration, so it needs no separately-started server the way
 * `a11y-browser.mjs` does, and can run as part of `verify` without changing what a
 * developer has to remember to do first.
 *
 * Usage: node scripts/a11y-rendered.mjs [outDir]
 */

import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

import { chromium } from "playwright";

const require = createRequire(import.meta.url);
const AXE = readFileSync(require.resolve("axe-core/axe.min.js"), "utf-8");

const OUT_DIR = path.resolve(process.argv[2] ?? "out");

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".xml": "application/xml; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
};

/** Just enough of a static file server to serve a Next.js export — `/en/` is `en/index.html`. */
function serveExport(root) {
  return createServer(async (req, res) => {
    const url = new URL(req.url, "http://localhost");
    let file = path.join(root, decodeURIComponent(url.pathname));
    if (file.endsWith(path.sep)) file = path.join(file, "index.html");
    try {
      const body = await readFile(file);
      res.writeHead(200, { "Content-Type": MIME[path.extname(file)] ?? "application/octet-stream" });
      res.end(body);
    } catch {
      res.writeHead(404);
      res.end("Not found");
    }
  });
}

function listen(server) {
  return new Promise((resolve, reject) => {
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => resolve(server.address().port));
  });
}

/**
 * Every axe rule, including the sixteen it disables by default — the same enablement
 * `a11y-audit.mjs` uses, so a rule this pass finds is judged by the same bar the static
 * pass judges everything else by. Unlike that pass, this one runs in real Chromium, so
 * the layout-dependent rules (`color-contrast-enhanced`, `target-size`) are answerable
 * here rather than reported as incomplete — real coverage of the two rules
 * `a11y-browser.mjs` exists only to check, on the one region that script does not visit.
 */
async function auditPage(page, label) {
  await page.addScriptTag({ content: AXE });
  const result = await page.evaluate(async () => {
    const rules = Object.fromEntries(window.axe.getRules().map((r) => [r.ruleId, { enabled: true }]));
    const { violations } = await window.axe.run(document, {
      resultTypes: ["violations"],
      rules,
    });
    return violations.map((v) => ({
      id: v.id,
      impact: v.impact,
      help: v.help,
      nodes: v.nodes.slice(0, 3).map((n) => n.html.slice(0, 120)),
    }));
  });

  if (result.length === 0) {
    console.log(`pass  ${label}`);
    return 0;
  }
  console.log(`FAIL  ${label}`);
  for (const v of result) {
    console.log(`        [${v.impact}] ${v.id}: ${v.help}`);
    for (const node of v.nodes) console.log(`          ${node}`);
  }
  return result.reduce((n, v) => n + v.nodes.length, 0);
}

const server = serveExport(OUT_DIR);
const port = await listen(server);
const base = `http://127.0.0.1:${port}`;

const browser = await chromium.launch();
let failures = 0;

try {
  for (const [lang, label] of [
    ["en", "English"],
    ["es", "Spanish"],
  ]) {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    await page.goto(`${base}/${lang}/`, { waitUntil: "networkidle" });

    // The chrome is server-rendered and present immediately; the result list is fetched
    // from search-index.json and rendered after hydration. Waiting for a card is waiting
    // for the page this audit exists to cover, not the shell around it.
    await page.waitForSelector(".card-list .card", { timeout: 15000 });
    failures += await auditPage(page, `Search results (${label})`);

    // Two programs selected, same as a reader comparing options, so the comparison table
    // — never audited before #29 — is actually in the DOM for this pass.
    const checkboxes = page.locator(".card .compare-check input[type=checkbox]");
    await checkboxes.nth(0).check();
    await checkboxes.nth(1).check();
    await page.locator("button.compare-open").click();
    await page.waitForSelector(".compare-table", { timeout: 15000 });
    failures += await auditPage(page, `Comparison table (${label})`);

    await page.close();
  }
} finally {
  await browser.close();
  server.close();
}

console.log(
  failures === 0
    ? "\na11y-rendered: no violations in the rendered search results or comparison table"
    : `\na11y-rendered: ${failures} node(s) failing`,
);
process.exit(failures === 0 ? 0 : 1);
