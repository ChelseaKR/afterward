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

async function firstUnder(page, prefix) {
  await page.goto(`${BASE}${prefix}`, { waitUntil: "networkidle" });
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

try {
  const scout = await browser.newPage();
  for (const [label, prefix] of [
    ["Program detail", "/en/programs/"],
    ["Occupation detail", "/en/occupations/"],
    ["Provider detail", "/en/providers/"],
  ]) {
    const href = await firstUnder(scout, prefix);
    if (href) PAGES.push([label, href]);
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

console.log(
  failures === 0
    ? `\na11y-browser: ${RULES.join(" and ")} pass in light and dark`
    : `\na11y-browser: ${failures} node(s) failing ${RULES.join(" / ")}`,
);
process.exit(failures === 0 ? 0 : 1);
