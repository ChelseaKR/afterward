/**
 * Accessibility audit over the static export.
 *
 * Runs axe-core against representative built pages in both languages. This is a real gate,
 * not a formality: the people most likely to need this tool are the least likely to be on a
 * new device with a big screen, and some of them are using a screen reader.
 *
 * axe-core binds to whichever globals exist when its module is first evaluated, so each page
 * is audited in its own child process rather than fighting the module cache.
 *
 * jsdom has no layout engine and cannot compute real colour contrast, so contrast findings
 * are reported as needing review in a browser rather than counted as passing.
 *
 * Usage: node scripts/a11y-audit.mjs [outDir]
 */

import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const OUT = process.argv[3] ?? process.argv[2] ?? "out";
const SINGLE = process.env.A11Y_PAGE;

async function auditOnePage(file) {
  const { JSDOM } = await import("jsdom");
  const dom = new JSDOM(readFileSync(file, "utf-8"), {
    url: "https://example.org/",
    pretendToBeVisual: true,
  });

  const { window } = dom;
  globalThis.window = window;
  globalThis.document = window.document;
  globalThis.Node = window.Node;
  globalThis.Element = window.Element;
  globalThis.HTMLElement = window.HTMLElement;
  globalThis.NodeList = window.NodeList;
  globalThis.getComputedStyle = window.getComputedStyle.bind(window);

  const { default: axe } = await import("axe-core");
  const results = await axe.run(window.document, {
    resultTypes: ["violations", "incomplete"],
  });

  const violations = results.violations.filter((v) => v.id !== "color-contrast");
  const contrast = results.incomplete.filter((v) => v.id === "color-contrast").length;

  process.stdout.write(
    JSON.stringify({
      contrast,
      violations: violations.map((v) => ({
        id: v.id,
        impact: v.impact,
        help: v.help,
        nodes: v.nodes.slice(0, 3).map((n) => n.html.slice(0, 120)),
      })),
    }),
  );
}

if (SINGLE) {
  await auditOnePage(SINGLE);
} else {
  const firstDirIn = (...segments) => {
    const dir = join(OUT, ...segments);
    if (!existsSync(dir)) return null;
    const entry = readdirSync(dir).find((n) => existsSync(join(dir, n, "index.html")));
    return entry ? join(OUT, ...segments, entry, "index.html") : null;
  };

  const targets = [
    // The site root is the most-linked URL and was previously an error shell with no lang
    // attribute. It was also the one page this audit did not look at, so CI reported no
    // violations while shipping a serious one.
    ["Site root", join(OUT, "index.html")],
    ["Search (English)", join(OUT, "en", "index.html")],
    ["Search (Spanish)", join(OUT, "es", "index.html")],
    ["Program detail (English)", firstDirIn("en", "programs")],
    ["Program detail (Spanish)", firstDirIn("es", "programs")],
    ["Occupation detail (English)", firstDirIn("en", "occupations")],
  ].filter(([, file]) => file && existsSync(file));

  if (targets.length === 0) {
    console.error(`a11y-audit: nothing built under ${OUT}/ — run the site build first`);
    process.exit(1);
  }

  let total = 0;
  let contrastPending = 0;

  for (const [label, file] of targets) {
    const child = spawnSync(process.execPath, [new URL(import.meta.url).pathname], {
      env: { ...process.env, A11Y_PAGE: file },
      encoding: "utf-8",
    });

    if (child.status !== 0) {
      console.error(`ERROR ${label}\n${child.stderr}`);
      total += 1;
      continue;
    }

    const { violations, contrast } = JSON.parse(child.stdout);
    contrastPending += contrast;

    if (violations.length === 0) {
      console.log(`pass  ${label}`);
    } else {
      total += violations.length;
      console.log(`FAIL  ${label}`);
      for (const v of violations) {
        console.log(`        [${v.impact}] ${v.id}: ${v.help}`);
        for (const node of v.nodes) console.log(`          ${node}`);
      }
    }
  }

  if (contrastPending > 0) {
    console.log(
      "\nnote  colour contrast is not machine-checkable here (jsdom has no layout engine)." +
        "\n      The palette comes from the California Design System, which ships AA-conformant" +
        "\n      pairings, but verify in a browser before any public launch.",
    );
  }

  if (total > 0) {
    console.error(`\na11y-audit: ${total} violation(s)`);
    process.exit(1);
  }
  console.log("\na11y-audit: no violations");
}
