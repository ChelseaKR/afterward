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
 * It also prints. `@media print` in `globals.css` hides the navigation, unfolds every
 * `<details>` so nothing a disclosure was holding is silently absent from the paper, and
 * keeps the non-affiliation notice on the page -- and no gate had ever rendered it. jsdom
 * resolves no media query and every other pass here runs in screen media, so the sheet a
 * reader takes to a job-center appointment (#111) was shipping unread. This emulates print
 * media on a program page whose source filed no number for at least one outcome, proves the
 * stylesheet actually reached the page before trusting the audit, and checks that "Not
 * reported" is still words rather than a blank -- on paper there is no title attribute to
 * hover and a blank is a zero.
 *
 * The assistant panel is the exception this file used to make and no longer does. It exists
 * in a build only when `NEXT_PUBLIC_ASK_URL` was set, which no build sets, so the panel's
 * branch never ran -- and the verdict printed underneath said "no violations in the rendered
 * search results, comparison table, or assistant panel". A gate claiming a surface it
 * skipped is the failure `a11y-audit.mjs` refuses one file over, in words already in this
 * tree: a page it is told to read and cannot is unaudited, not passing. So the same variable
 * that decides whether the build carries a panel now decides whether this gate demands one,
 * a disagreement in either direction is a failure, and the verdict names only what it read.
 * The panel's own axe coverage, for builds that have none, is
 * `web/components/AskPanel.a11y.test.tsx`.
 *
 * Two WCAG 2.2 AA checks no axe rule makes were added with the conformance report
 * (docs/accessibility/ACR.md, 2026-11). **Reflow (1.4.10)**: every per-language page template
 * is loaded at 320 CSS px and fails if the page scrolls sideways; a wide data table inside its
 * own scroll container is allowed, a page that is wider than the screen is not. The search
 * page failed this at 403px, and the CTDL page at 411px, before anyone looked. **Focus Not
 * Obscured (2.4.11)**: with four programs in the sticky comparison tray, focus is tabbed
 * through the search page on a desktop and on a phone, and any control that lands entirely
 * behind the tray fails. At 320px it also asks axe's `scrollable-region-focusable`, which
 * cannot fire on a desktop where no table overflows. Three filter selects did, on a desktop, and most of the result list
 * did on a phone.
 *
 * Usage: node scripts/a11y-rendered.mjs [outDir]
 */

import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { readdirSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

import { chromium } from "playwright";

import { askServiceConfigured, verdict } from "./a11y-verdict.mjs";
import { isPerLanguage, routeTemplates } from "./routes.mjs";

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
      res.writeHead(200, {
        "Content-Type": MIME[path.extname(file)] ?? "application/octet-stream",
      });
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
    const rules = Object.fromEntries(
      window.axe.getRules().map((r) => [r.ruleId, { enabled: true }]),
    );
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

/**
 * The program page this run prints, and the measure that makes printing it worth checking.
 *
 * `@media print` in `globals.css` is a published surface no gate has ever read: `npm run
 * a11y` parses the static export with jsdom, which resolves no media query, and every pass
 * below this one runs in screen media. So the rules that hide the navigation, unfold every
 * `<details>` and keep the non-affiliation notice on the paper have been shipping unaudited
 * (#111).
 *
 * The page is chosen by its data rather than hardcoded: the first program, by uuid, that has
 * an outcome its source never filed. On paper an absent measure has to be the words "Not
 * reported" / "No reportado" -- there is no title attribute to hover and no color to read --
 * so a print pass over a program whose every measure is present would prove nothing about the
 * one rule this site is built around. If the fixture has no such program, that is a failure
 * here rather than a pass over a page where the failure is impossible.
 */
function programWithAnUnreportedMeasure(outDir) {
  const document = JSON.parse(
    readFileSync(path.join(outDir, "data", "programs.json"), "utf-8"),
  );
  const programs = [...document.programs].sort((a, b) =>
    String(a.uuid).localeCompare(String(b.uuid)),
  );
  const chosen = programs.find((program) =>
    Object.values(program.outcomes ?? {}).some((value) => value === null),
  );
  if (!chosen) {
    throw new Error(
      "no program in this build has an unreported outcome, so a print audit of one would " +
        "read as a pass over a page where the defect it looks for cannot appear",
    );
  }
  return String(chosen.uuid);
}

/**
 * What the print stylesheet must have done to the page, read off the live computed styles.
 *
 * Emulating print media and auditing is not enough on its own: if the stylesheet had failed
 * to load, or its rules had been renamed out from under this pass, axe would audit the screen
 * layout and print `pass`, and the verdict underneath would claim a print sheet nobody read.
 * So the pass first proves the medium changed, then proves the medium changed *this page* --
 * a control the gate carries with it rather than one somebody has to remember to run.
 */
async function printRulesAreInForce(page) {
  return page.evaluate(() => {
    const shown = (selector) => {
      const element = document.querySelector(selector);
      return element ? getComputedStyle(element).display : null;
    };
    return {
      mediaIsPrint: window.matchMedia("print").matches,
      nav: shown(".site-nav"),
      summary: shown("details > summary"),
    };
  });
}

/**
 * One exported page per per-language template, for the reflow pass. Dynamic segments take
 * the first page the export holds, so a template added later is covered without anyone
 * remembering to list it; a template with nothing exported fails rather than leaving the
 * sample, for the reason `a11y-audit.mjs` gives.
 */
function reflowSample(outDir, lang) {
  return routeTemplates()
    .filter(isPerLanguage)
    .map((template) => {
      let dir = outDir;
      const parts = [];
      for (const segment of template.split("/").filter(Boolean)) {
        let name = segment === "[lang]" ? lang : segment;
        if (segment !== "[lang]" && segment.startsWith("[")) {
          let entries = [];
          try {
            entries = readdirSync(dir, { withFileTypes: true });
          } catch {
            entries = [];
          }
          name = entries.filter((e) => e.isDirectory()).map((e) => e.name).sort()[0] ?? null;
          if (name === null) return { template, path: null };
        }
        parts.push(name);
        dir = path.join(dir, name);
      }
      return { template, path: `/${parts.join("/")}/` };
    });
}

/** Elements wider than the viewport that are not inside their own horizontal scroller. */
async function reflowOverflow(page) {
  return page.evaluate(() => {
    const width = document.documentElement.clientWidth;
    if (document.documentElement.scrollWidth <= width + 1) return [];
    const inScroller = (element) => {
      for (let a = element.parentElement; a; a = a.parentElement) {
        const overflow = getComputedStyle(a).overflowX;
        if (overflow === "auto" || overflow === "scroll") return true;
      }
      return false;
    };
    return [...document.querySelectorAll("body *")]
      .filter((element) => {
        const box = element.getBoundingClientRect();
        if (box.width === 0 || box.right <= width + 1 || inScroller(element)) return false;
        return ![...element.children].some((c) => c.getBoundingClientRect().right > width + 1);
      })
      .slice(0, 3)
      .map((e) => `<${e.tagName.toLowerCase()}> ${(e.textContent ?? "").trim().slice(0, 50)}`);
  });
}

/**
 * Tab through the page and name every control that ends up entirely behind the sticky tray.
 * "Entirely" is the 2.4.11 test: partly covered passes AA, wholly covered does not.
 */
async function focusHiddenByTray(page) {
  await page.evaluate(() => {
    if (document.activeElement && "blur" in document.activeElement) document.activeElement.blur();
    window.scrollTo(0, 0);
  });
  const hidden = [];
  let first = null;
  for (let step = 0; step < 250; step += 1) {
    await page.keyboard.press("Tab");
    const result = await page.evaluate(() => {
      const element = document.activeElement;
      if (!element || element === document.body) return null;
      const tray = document.querySelector(".compare-tray");
      const box = element.getBoundingClientRect();
      const key = `${element.tagName}|${element.id}|${(element.textContent ?? "").trim().slice(0, 40)}|${Math.round(box.top + window.scrollY)}`;
      if (!tray || tray.contains(element) || box.width === 0 || box.height === 0) {
        return { key, covered: false };
      }
      const points = [
        [0.5, 0.5],
        [0.1, 0.1],
        [0.9, 0.1],
        [0.1, 0.9],
        [0.9, 0.9],
      ];
      const covered = points.every(([fx, fy]) => {
        const x = box.left + box.width * fx;
        const y = box.top + box.height * fy;
        if (y > window.innerHeight || y < 0) return true;
        const top = document.elementFromPoint(x, y);
        return top !== null && tray.contains(top);
      });
      return { key, covered, label: key.split("|").slice(0, 3).join(" ") };
    });
    if (result === null) continue;
    if (result.key === first) break;
    first ??= result.key;
    if (result.covered) hidden.push(result.label);
  }
  return hidden;
}

const ASSISTANT_EXPECTED = askServiceConfigured(
  process.env.NEXT_PUBLIC_ASK_URL,
);

const PRINT_PROGRAM = programWithAnUnreportedMeasure(OUT_DIR);

const server = serveExport(OUT_DIR);
const port = await listen(server);
const base = `http://127.0.0.1:${port}`;

const browser = await chromium.launch();
let failures = 0;
/** What this run actually read, in the order it read it. The verdict is built from this. */
const audited = [];

try {
  for (const [lang, label] of [
    ["en", "English"],
    ["es", "Spanish"],
  ]) {
    const page = await browser.newPage({
      viewport: { width: 1280, height: 900 },
    });
    // Every request the browser makes while this page is driven, so the no-off-origin rule
    // (SECURITY.md; ADR 0003) is checked in a real browser and not only in a unit test: the
    // static site makes no request beyond its own origin, and opening the assistant panel
    // must not change that. Submitting a question would, and this audit never submits one.
    const offOrigin = [];
    page.on("request", (request) => {
      if (!request.url().startsWith(base)) offOrigin.push(request.url());
    });
    await page.goto(`${base}/${lang}/`, { waitUntil: "networkidle" });

    // The chrome is server-rendered and present immediately; the result list is fetched
    // from search-index.json and rendered after hydration. Waiting for a card is waiting
    // for the page this audit exists to cover, not the shell around it.
    await page.waitForSelector(".card-list .card", { timeout: 15000 });
    failures += await auditPage(page, `Search results (${label})`);
    audited.push(`the rendered search results (${label})`);

    // Two programs selected, same as a reader comparing options, so the comparison table
    // — never audited before #29 — is actually in the DOM for this pass.
    const checkboxes = page.locator(
      ".card .compare-check input[type=checkbox]",
    );
    await checkboxes.nth(0).check();
    await checkboxes.nth(1).check();
    await page.locator("button.compare-open").click();
    await page.waitForSelector(".compare-table", { timeout: 15000 });
    failures += await auditPage(page, `Comparison table (${label})`);
    audited.push(`the comparison table (${label})`);

    // The assistant's open state (ADR 0003) exists only after a click, so no static gate
    // sees its form, its notice or its live region. It is on the page only in a build with
    // NEXT_PUBLIC_ASK_URL set; opening it makes no request, so this is safe offline.
    //
    // Both directions are failures. A build configured with a service and no panel in it is
    // an export that does not match the environment it is being audited against, which is
    // the stale-artifact shape this repository keeps meeting. A panel in a build that
    // declared no service is a page carrying an interface nobody meant to ship.
    const present = (await page.locator("button.ask-open").count()) > 0;
    if (present !== ASSISTANT_EXPECTED) {
      console.log(`FAIL  Assistant panel (${label})`);
      console.log(
        present
          ? "        NEXT_PUBLIC_ASK_URL configures no service and the build has a panel anyway."
          : "        NEXT_PUBLIC_ASK_URL configures a service and the build has no panel.\n" +
              "        Rebuild the export in the environment it is audited in.",
      );
      failures += 1;
    } else if (present) {
      await page.locator("button.ask-open").click();
      await page.waitForSelector(".ask-form textarea", { timeout: 15000 });
      failures += await auditPage(page, `Assistant panel, open (${label})`);
      audited.push(`the assistant panel (${label})`);
    } else {
      // Not a skip that the verdict then forgets: this build has no panel to read, the
      // verdict will not claim one, and the component's own axe pass lives in
      // components/AskPanel.a11y.test.tsx.
      console.log(
        `none  Assistant panel (${label}): this build configures no service, so there is no ` +
          "panel to audit (covered by components/AskPanel.a11y.test.tsx)",
      );
    }

    if (offOrigin.length > 0) {
      console.log(`FAIL  Off-origin requests (${label})`);
      for (const url of offOrigin) console.log(`          ${url}`);
      failures += offOrigin.length;
    } else {
      console.log(`pass  No off-origin requests (${label})`);
      audited.push(`off-origin requests (${label})`);
    }

    await page.close();

    // The print sheet. A separate page, because `emulateMedia` is a property of the page and
    // leaving it set would silently print-audit whatever ran next.
    const sheet = await browser.newPage({
      viewport: { width: 1280, height: 900 },
    });
    await sheet.goto(`${base}/${lang}/programs/${PRINT_PROGRAM}/`, {
      waitUntil: "networkidle",
    });

    // Presence before absence, and before print: the words this pass exists to find have to
    // be on the screen page first, or every assertion below holds over a page that never
    // carried them.
    const unreportedOnScreen = await sheet.locator(".unreported").count();
    if (unreportedOnScreen === 0) {
      console.log(`FAIL  Program sheet (${label})`);
      console.log(
        `        /${lang}/programs/${PRINT_PROGRAM}/ shows no unreported measure on screen, ` +
          "so printing it proves nothing about how an absence reads on paper.",
      );
      failures += 1;
    } else {
      const onScreen = await printRulesAreInForce(sheet);
      await sheet.emulateMedia({ media: "print" });
      const onPaper = await printRulesAreInForce(sheet);

      const brokenControls = [];
      if (!onPaper.mediaIsPrint)
        brokenControls.push("print media did not take effect");
      if (onScreen.nav === null)
        brokenControls.push(".site-nav is not on this page");
      else if (onScreen.nav === "none")
        brokenControls.push(".site-nav is hidden on screen too");
      else if (onPaper.nav !== "none")
        brokenControls.push(`.site-nav prints as ${onPaper.nav}`);
      if (onScreen.summary !== null && onPaper.summary !== "none") {
        brokenControls.push(`a <details> toggle prints as ${onPaper.summary}`);
      }

      if (brokenControls.length > 0) {
        // Not "no violations": a print audit of a page the print stylesheet did not reach is
        // an audit of the screen, and reporting it as a pass is the failure this whole file
        // was rewritten to stop making.
        console.log(`FAIL  Print stylesheet not in force (${label})`);
        for (const reason of brokenControls) console.log(`          ${reason}`);
        failures += brokenControls.length;
      } else {
        const words = await sheet.evaluate(() =>
          [...document.querySelectorAll(".unreported")].map((element) => ({
            text: (element.textContent ?? "").trim(),
            display: getComputedStyle(element).display,
            visibility: getComputedStyle(element).visibility,
          })),
        );
        const lost = words.filter(
          (w) =>
            w.text === "" || w.display === "none" || w.visibility === "hidden",
        );
        if (lost.length > 0) {
          console.log(`FAIL  Unreported measures on paper (${label})`);
          console.log(
            `        ${lost.length} of ${words.length} "not reported" labels print blank or ` +
              "hidden. On paper a blank is a zero to whoever is holding it.",
          );
          failures += lost.length;
        } else {
          console.log(
            `pass  Unreported measures print as words (${label}): ${words[0].text}`,
          );
        }

        failures += await auditPage(
          sheet,
          `Program sheet, print media (${label})`,
        );
        audited.push(`the program sheet under print media (${label})`);
      }
    }
    await sheet.close();

    // Reflow at 320 CSS px (1.4.10): 1280px at 400% zoom.
    const reflowFailures = [];
    const narrow = await browser.newPage({ viewport: { width: 320, height: 640 } });
    for (const { template, path: route } of reflowSample(OUT_DIR, lang)) {
      if (route === null) {
        reflowFailures.push(`${template}: no exported page to load`);
        continue;
      }
      await narrow.goto(`${base}${route}`, { waitUntil: "networkidle" });
      if (route === `/${lang}/`) await narrow.waitForSelector(".card-list .card", { timeout: 15000 });
      const wide = await reflowOverflow(narrow);
      if (wide.length > 0) reflowFailures.push(`${route}: ${wide.join(" · ")}`);
      // A table that reflow sends into its own scroller has to be scrollable from the
      // keyboard too (2.1.1). axe's rule only fires once the table overflows, which on a
      // desktop it never does, so it is asked here, at the width where it matters.
      await narrow.addScriptTag({ content: AXE });
      const stuck = await narrow.evaluate(async () => {
        const { violations } = await window.axe.run(document, {
          runOnly: { type: "rule", values: ["scrollable-region-focusable"] },
          resultTypes: ["violations"],
        });
        return violations.flatMap((v) => v.nodes.map((n) => n.target.join(" ")));
      });
      for (const target of stuck) {
        reflowFailures.push(`${route}: ${target} scrolls sideways and cannot be reached by keyboard`);
      }
    }
    await narrow.close();
    if (reflowFailures.length > 0) {
      console.log(`FAIL  Reflow at 320 CSS px (${label})`);
      for (const line of reflowFailures) console.log(`          ${line}`);
      failures += reflowFailures.length;
    } else {
      console.log(`pass  Reflow at 320 CSS px, every page template (${label})`);
      audited.push(`reflow at 320 CSS px on every page template (${label})`);
    }

    // Focus Not Obscured (2.4.11), with the tray as tall as it gets: four programs picked.
    for (const [width, height] of [
      [1280, 900],
      [320, 640],
    ]) {
      const tray = await browser.newPage({ viewport: { width, height } });
      await tray.goto(`${base}/${lang}/`, { waitUntil: "networkidle" });
      await tray.waitForSelector(".card-list .card", { timeout: 15000 });
      const boxes = tray.locator(".card .compare-check input[type=checkbox]");
      for (let n = 0; n < 4; n += 1) await boxes.nth(n).check();
      const hidden = await focusHiddenByTray(tray);
      await tray.close();
      const where = `${width}px, four programs in the tray (${label})`;
      if (hidden.length > 0) {
        console.log(`FAIL  Focus hidden behind the comparison tray, ${where}`);
        for (const name of hidden.slice(0, 5)) console.log(`          ${name}`);
        failures += hidden.length;
      } else {
        console.log(`pass  Focus never hidden behind the comparison tray, ${where}`);
        audited.push(`focus against the comparison tray at ${width}px (${label})`);
      }
    }
  }
} finally {
  await browser.close();
  server.close();
}

console.log(`\n${verdict({ failures, audited })}`);
process.exit(failures === 0 ? 0 : 1);
