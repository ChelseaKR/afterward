/**
 * The accessibility checks a DOM without layout cannot make.
 *
 * jsdom has no layout engine, so two rules can never run there: `color-contrast-enhanced`
 * (WCAG 2.2 AAA 1.4.6) needs resolved colours and font sizes, and `target-size` (WCAG 2.2 AA
 * 2.5.8) needs the rendered box of every control. Enabling them in the jsdom pass makes them
 * report as incomplete, which is honest but is not a check. This runs them in Chromium
 * against the built pages, where both are answerable.
 *
 * Both colour schemes, because the palette is theme-aware and a ratio that clears AAA in
 * light can fail in dark. Every disclosure is expanded first, for the same reason the jsdom
 * pass does it: a collapsed <details> is outside the accessibility tree, and a gate that
 * stops looking is worse than one that fails.
 *
 * Usage: node scripts/a11y-browser.mjs [baseUrl]
 */

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

import { chromium } from "playwright";

const require = createRequire(import.meta.url);
const AXE = readFileSync(require.resolve("axe-core/axe.min.js"), "utf-8");

const BASE = process.argv[2] ?? "http://localhost:8899";
const RULES = ["color-contrast-enhanced", "target-size"];

const PAGES = [
  ["Site root", "/"],
  ["Search (English)", "/en/"],
  ["Search (Spanish)", "/es/"],
  ["Occupation index", "/en/occupations/"],
  ["Provider index", "/en/providers/"],
  ["Paying for training", "/en/paying-for-training/"],
  ["About", "/en/about/"],
];

/** The first link to a `prefix` detail page found on the page at `from`. */
async function firstUnder(page, from, prefix) {
  await page.goto(`${BASE}${from}`, { waitUntil: "networkidle" });
  return page.evaluate(
    (p) =>
      [...document.querySelectorAll(`a[href*="${p}"]`)]
        .map((a) => a.getAttribute("href"))
        .find((h) => h && h.split("/").filter(Boolean).length > 2) ?? null,
    prefix,
  );
}

const browser = await chromium.launch();
let failures = 0;
/** Templates this pass was supposed to audit and could not reach. Kept apart from
 * `failures` so the summary line stays literally true: one counts failing nodes, the other
 * counts pages nobody looked at, and reporting them as the same number would be the
 * softer-sounding version of the fault this whole change is about. */
let missing = 0;

try {
  const scout = await browser.newPage();
  const found = {};
  /*
   * Each detail template, and a page that actually links to one.
   *
   * The program page is scouted from a provider page, not from `/en/programs/`, because
   * there is no `/en/programs/` index: programs are reached from the search results, which
   * are client-rendered, and from provider and occupation pages. Asking for `/en/programs/`
   * returns the 404 template, which links to no program, so the lookup returned null on
   * every run this script has ever made — and `if (href) PAGES.push(...)` dropped the site's
   * densest template from the sample and printed a clean pass anyway. Both halves of that
   * are fixed here: the source is a page with the links on it, and a template this pass
   * cannot reach now fails the run instead of leaving the sample.
   *
   * The provider page must be found before the program page can be scouted from it, so the
   * order below is a dependency and not a preference.
   */
  for (const [label, from, prefix] of [
    ["Occupation detail", "/en/occupations/", "/en/occupations/"],
    ["Provider detail", "/en/providers/", "/en/providers/"],
    ["Program detail", () => found["Provider detail"], "/en/programs/"],
  ]) {
    const source = typeof from === "function" ? from() : from;
    const href = source ? await firstUnder(scout, source, prefix) : null;
    if (!href) {
      console.error(
        `a11y-browser: no ${label} page found` +
          (source ? ` from ${BASE}${source}` : " — the page it is scouted from was not found"),
      );
      console.error("  A template this pass cannot reach is unaudited, not passing.");
      missing += 1;
      continue;
    }
    found[label] = href;
    PAGES.push([label, href]);
  }
  await scout.close();

  for (const scheme of ["light", "dark"]) {
    for (const [label, path] of PAGES) {
      const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, colorScheme: scheme });
      await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
      await page.waitForTimeout(400);
      await page.evaluate(() => {
        for (const d of document.querySelectorAll("details")) d.open = true;
      });
      await page.addScriptTag({ content: AXE });
      const result = await page.evaluate(
        async (rules) =>
          window.axe
            .run(document, { runOnly: { type: "rule", values: rules }, resultTypes: ["violations"] })
            .then((r) =>
              r.violations.map((v) => ({
                id: v.id,
                impact: v.impact,
                help: v.help,
                nodes: v.nodes.slice(0, 3).map((n) => n.html.slice(0, 110)),
              })),
            ),
        RULES,
      );
      await page.close();

      if (result.length === 0) {
        console.log(`pass  ${scheme.padEnd(5)} ${label}`);
      } else {
        failures += result.reduce((n, v) => n + v.nodes.length, 0);
        console.log(`FAIL  ${scheme.padEnd(5)} ${label}`);
        for (const v of result) {
          console.log(`        [${v.impact}] ${v.id}: ${v.help}`);
          for (const node of v.nodes) console.log(`          ${node}`);
        }
      }
    }
  }
} finally {
  await browser.close();
}

if (missing > 0) {
  console.error(`\na11y-browser: ${missing} template(s) never reached, so never audited.`);
}
console.log(
  failures === 0
    ? `\na11y-browser: ${RULES.join(" and ")} pass in light and dark on ${PAGES.length} pages`
    : `\na11y-browser: ${failures} node(s) failing ${RULES.join(" / ")}`,
);
process.exit(failures === 0 && missing === 0 ? 0 : 1);
