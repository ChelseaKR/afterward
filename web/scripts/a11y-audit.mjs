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
 * jsdom has no layout engine and cannot compute real color contrast, so contrast findings
 * are reported as needing review in a browser rather than counted as passing.
 *
 * Usage: node scripts/a11y-audit.mjs [outDir]
 */

import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join, relative } from "node:path";

import { uncovered } from "./routes.mjs";

const POSITIONAL = process.argv.slice(2).filter((arg) => !arg.startsWith("--"));
const OUT = POSITIONAL[1] ?? POSITIONAL[0] ?? "out";
/**
 * Child mode: audit the one page named in `A11Y_PAGE` and print its findings as JSON.
 *
 * Selected by the flag, never by the environment variable alone, and that distinction is the
 * whole of this. Until this flag existed the branch was chosen by `if (process.env.A11Y_PAGE)`
 * and the parent handed its entire environment down to each child, so the variable was a
 * normal thing to have exported: audit one page to look at it, forget to unset it, and every
 * later `npm run a11y` -- a step of `npm run verify` -- printed one page's findings as a JSON
 * blob and exited 0. Not "no violations": no message at all, and the missing-page check, the
 * uncovered-route check and all 22 audits skipped before they ran, because `if (SINGLE)`
 * comes before every one of them.
 *
 * An environment variable that silently turns a gate into a printer is the same shape as a
 * sample that filters itself down to whatever exists, which this file already refuses two
 * checks below. So: the flag decides, the variable only carries the path, and a variable set
 * without the flag is announced rather than obeyed.
 */
const CHILD = process.argv.includes("--child");
const SINGLE = CHILD ? process.env.A11Y_PAGE : undefined;
/** An app tree to read routes from instead of this repository's, so the gate can be tested. */
const APP_DIR_OVERRIDE = process.env.A11Y_APP_DIR;
/** Resolve the sample, check it is all there, and print it without auditing anything. */
const LIST_ONLY = process.argv.includes("--list");

if (CHILD && !SINGLE) {
  console.error("a11y-audit: --child needs A11Y_PAGE to name the page to audit");
  process.exit(1);
}
if (!CHILD && process.env.A11Y_PAGE) {
  console.error(
    `a11y-audit: ignoring A11Y_PAGE=${process.env.A11Y_PAGE} — auditing the whole sample.` +
      "\n            To audit one page, pass --child as well.",
  );
}

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

  // Expand every disclosure before auditing.
  //
  // The filter panel ships collapsed so a phone reaches results sooner, and a closed
  // <details> is hidden from the accessibility tree — so axe skips everything inside it.
  // Left alone, this audit would have gone green on the filter controls by no longer
  // looking at them, which is the most dangerous way for a gate to pass. Opening them
  // audits the state a user actually operates the controls in.
  for (const details of window.document.querySelectorAll("details")) {
    details.open = true;
  }

  const { default: axe } = await import("axe-core");

  /*
   * Every rule axe ships, including the ones it disables by default.
   *
   * Running axe with no configuration is not "all the checks". Sixteen rules are off unless
   * asked for, and four of them are the ones that matter for the level this site claims:
   * color-contrast-enhanced (AAA 1.4.6), identical-links-same-purpose (AAA 2.4.9),
   * meta-refresh-no-exceptions (AAA 2.2.4) and target-size (WCAG 2.2 AA 2.5.8). A report
   * saying "no violations" while those sat switched off was answering a narrower question
   * than the one it appeared to answer.
   *
   * Two of them need a layout engine jsdom does not have and are checked in the browser pass
   * instead; they are enabled here anyway, so they surface as incomplete rather than being
   * silently absent from the run.
   */
  const enableAll = Object.fromEntries(
    axe.getRules().map((rule) => [rule.ruleId, { enabled: true }]),
  );

  const results = await axe.run(window.document, {
    resultTypes: ["violations", "incomplete"],
    rules: enableAll,
  });

  // Contrast needs real layout; `npm run contrast` resolves the tokens analytically and the
  // browser pass measures the rendered page. Both are reported separately rather than here.
  const LAYOUT_DEPENDENT = new Set(["color-contrast", "color-contrast-enhanced", "target-size"]);
  const violations = results.violations.filter((v) => !LAYOUT_DEPENDENT.has(v.id));
  const contrast = results.incomplete.filter((v) => LAYOUT_DEPENDENT.has(v.id)).length;

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
    // Every mistyped or stale URL on the site lands here, and it is the page that arrives
    // with the least context — so it is also the page most likely to be mistaken for a state
    // website. It was Next's stock error screen: no lang attribute, no landmarks, no Spanish.
    ["Page not found", join(OUT, "404.html")],
    ["Search (English)", join(OUT, "en", "index.html")],
    ["Search (Spanish)", join(OUT, "es", "index.html")],
    ["Program detail (English)", firstDirIn("en", "programs")],
    ["Program detail (Spanish)", firstDirIn("es", "programs")],
    ["Occupation detail (English)", firstDirIn("en", "occupations")],
    ["Occupation detail (Spanish)", firstDirIn("es", "occupations")],
    // Provider detail is a distinct template with its own table, and it is the page every
    // provider named in this data is most likely to look at. It had no coverage at all.
    ["Provider detail (English)", firstDirIn("en", "providers")],
    ["Provider detail (Spanish)", firstDirIn("es", "providers")],
    // The browse indexes are the two longest pages on the site — several hundred table rows
    // each — and the ones most dependent on real table semantics to be usable at all.
    ["Occupation index (English)", join(OUT, "en", "occupations", "index.html")],
    ["Occupation index (Spanish)", join(OUT, "es", "occupations", "index.html")],
    ["Provider index (English)", join(OUT, "en", "providers", "index.html")],
    ["Provider index (Spanish)", join(OUT, "es", "providers", "index.html")],
    // The methodology page is the one page here that is mostly prose, and the only one a
    // named provider is likely to read end to end before disputing a figure. It is also the
    // only template built from headings, lists and definition lists rather than the measure
    // grid every other page reuses, so nothing else covers its structure.
    ["About (English)", join(OUT, "en", "about", "index.html")],
    ["About (Spanish)", join(OUT, "es", "about", "index.html")],
    // Every one of the 3,266 program pages links here, in both languages, and it is the page
    // this site sends somebody to before they spend money or take a morning off work. It is
    // also built from nested disclosures holding an ordered list of questions, which is a
    // structure nothing else here uses — and it had no coverage at all.
    ["Paying for training (English)", join(OUT, "en", "paying-for-training", "index.html")],
    ["Paying for training (Spanish)", join(OUT, "es", "paying-for-training", "index.html")],
    // Four data tables stacked one after another, each with row headers and a mix of counts
    // and explicitly-not-reported cells. Nothing else here puts that many tables on one
    // screen, and this is the page written to be quoted by people reading it end to end,
    // which makes correct table semantics the difference between citable and unusable.
    ["Outcomes coverage (English)", join(OUT, "en", "outcomes-coverage", "index.html")],
    ["Outcomes coverage (Spanish)", join(OUT, "es", "outcomes-coverage", "index.html")],
    // Table-heavy, like the coverage page, and for the same reason it needs auditing: a page
    // this listing does not name is unchecked rather than passing.
    ["CTDL export (English)", join(OUT, "en", "ctdl", "index.html")],
    ["CTDL export (Spanish)", join(OUT, "es", "ctdl", "index.html")],
  ];

  if (!existsSync(OUT)) {
    console.error(`a11y-audit: nothing built under ${OUT}/ — run the site build first`);
    process.exit(1);
  }

  /*
   * A page on this list that is not in the build is a failure, not a page to skip.
   *
   * This list used to end in `.filter(([, file]) => file && existsSync(file))`, so a route
   * that was renamed, removed, or failed to emit in one language simply left the sample —
   * and the gate went green over a smaller sample without saying so. That is the same way of
   * passing this file already refuses one level down, where a closed <details> hides its
   * contents from the accessibility tree and the audit opens them rather than accept the
   * silence; and the same way the contrast audit once reported success having resolved 0 of
   * 17 pairings. The sample is the claim. It has to be stated, not inferred from what
   * happens to exist.
   *
   * Every entry here is a page both the fixture build and a production build emit, so a
   * missing one is a real change and worth stopping for. If a page ever becomes genuinely
   * optional, it belongs in a separate list that says so, with the reason.
   */
  const missing = targets.filter(([, file]) => !file || !existsSync(file));
  if (missing.length > 0) {
    console.error(`a11y-audit: ${missing.length} page(s) on the audit list are not in ${OUT}/:`);
    for (const [label, file] of missing) {
      console.error(`  ${label} — ${file ?? "no page of this kind was built at all"}`);
    }
    console.error(
      "  A page this gate is told to read and cannot is unaudited, not passing.\n" +
        "  Rebuild the site, or change the list and say why in the same commit.",
    );
    process.exit(1);
  }

  /*
   * And a page the list does not name is unaudited too.
   *
   * The check above asks whether every page named here was built. It cannot ask the question
   * the other way round, and that is the direction a new route arrives from: add
   * `app/[lang]/something/page.tsx` and this gate keeps reporting "no violations" over a
   * sample that has quietly stopped describing the site. Nothing in the build fails, nothing
   * says the coverage shrank, and the new page — the one nobody has looked at yet — is the
   * single page here most likely to have a violation in it.
   *
   * `routes.mjs` reads the app router's own file tree, which is where a route is actually
   * declared and the only place it cannot be declared twice. Both languages are required
   * separately: a page that exists in English and not in Spanish is half a page.
   */
  const uncoveredRoutes = uncovered(
    targets.map(([, file]) => relative(OUT, file)),
    APP_DIR_OVERRIDE ? { appDir: APP_DIR_OVERRIDE } : undefined,
  );
  if (uncoveredRoutes.length > 0) {
    console.error(`a11y-audit: ${uncoveredRoutes.length} route(s) this gate never reads:`);
    for (const route of uncoveredRoutes) console.error(`  ${route}`);
    console.error(
      "  Every route the app declares needs a representative in the list above.\n" +
        "  A page no gate has read is unaudited, not accessible.",
    );
    process.exit(1);
  }

  if (LIST_ONLY) {
    // What this gate reads, answerable without spending a minute auditing it. Worth having
    // for its own sake -- "which pages does the a11y gate cover?" is a question the
    // conformance note answers in prose and this answers from the code.
    console.log(`a11y-audit: ${targets.length} pages, all present under ${OUT}/`);
    for (const [label, file] of targets) console.log(`  ${label} — ${file}`);
    process.exit(0);
  }

  let total = 0;
  let contrastPending = 0;

  for (const [label, file] of targets) {
    const child = spawnSync(process.execPath, [new URL(import.meta.url).pathname, "--child"], {
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
      "\nnote  color contrast is not machine-checkable here (jsdom has no layout engine)." +
        "\n      `npm run contrast` checks it separately, resolving the design system's own" +
        "\n      tokens and computing real WCAG ratios for both light and dark.",
    );
  }

  if (total > 0) {
    console.error(`\na11y-audit: ${total} violation(s)`);
    process.exit(1);
  }
  console.log("\na11y-audit: no violations");
}
