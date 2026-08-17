import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

/**
 * The gate must fail when it cannot read a page it was told to read.
 *
 * `a11y-audit.mjs` used to filter its own target list down to whatever existed on disk, so a
 * route that was renamed, removed, or failed to emit in one language quietly left the sample
 * and the gate reported "no violations" over what was left. Nothing said the sample had
 * shrunk. That is the failure this project keeps meeting in different clothes: the audit's
 * own docstring describes it one level down (a collapsed `<details>` hides its contents from
 * the accessibility tree, so opening them is what keeps the gate from passing by no longer
 * looking), and the contrast audit once reported success having resolved 0 of 17 pairings.
 *
 * Testing it needs no axe run at all: the missing-page check happens before any page is
 * audited, which is also why it is cheap enough to live in the unit suite.
 */
const AUDIT = fileURLToPath(new URL("./a11y-audit.mjs", import.meta.url));

/** The pages the audit names, as paths relative to an export root. */
const PAGES = [
  "index.html",
  "404.html",
  ...["en", "es"].flatMap((lang) => [
    `${lang}/index.html`,
    `${lang}/programs/some-program/index.html`,
    `${lang}/occupations/00-0000/index.html`,
    `${lang}/providers/some-provider/index.html`,
    `${lang}/occupations/index.html`,
    `${lang}/providers/index.html`,
    `${lang}/about/index.html`,
    `${lang}/paying-for-training/index.html`,
    `${lang}/outcomes-coverage/index.html`,
    `${lang}/ctdl/index.html`,
  ]),
];

function buildExport(omit: string[] = []): string {
  const root = mkdtempSync(join(tmpdir(), "a11y-audit-"));
  for (const page of PAGES) {
    if (omit.includes(page)) continue;
    const file = join(root, page);
    mkdirSync(join(file, ".."), { recursive: true });
    writeFileSync(file, "<!doctype html><html lang='en'><title>t</title><body></body></html>");
  }
  return root;
}

/**
 * The audit resolving its sample and stopping, which is all these tests are about.
 *
 * `--list` exists so this can be asserted without spending a minute running axe over two
 * dozen stub pages in child processes, and so a person can ask what the gate reads.
 */
function run(root: string, appDir?: string) {
  return spawnSync(process.execPath, [AUDIT, root, "--list"], {
    encoding: "utf-8",
    env: appDir === undefined ? process.env : { ...process.env, A11Y_APP_DIR: appDir },
  });
}

/**
 * An app router tree with the routes this repository has, plus whatever `extra` names.
 *
 * Stubs rather than the real `web/app`, so a test can add a route without adding a page to
 * the site — which is the event being tested, and one that must fail the gate on the day it
 * happens rather than on the day somebody notices.
 */
function buildApp(extra: string[] = []): string {
  const root = mkdtempSync(join(tmpdir(), "a11y-app-"));
  const routes = [
    "page.tsx",
    "not-found.tsx",
    "[lang]/page.tsx",
    "[lang]/about/page.tsx",
    "[lang]/ctdl/page.tsx",
    "[lang]/occupations/page.tsx",
    "[lang]/occupations/[soc]/page.tsx",
    "[lang]/outcomes-coverage/page.tsx",
    "[lang]/paying-for-training/page.tsx",
    "[lang]/programs/[id]/page.tsx",
    "[lang]/providers/page.tsx",
    "[lang]/providers/[slug]/page.tsx",
    ...extra,
  ];
  for (const route of routes) {
    const file = join(root, route);
    mkdirSync(join(file, ".."), { recursive: true });
    writeFileSync(file, "export default function Page() { return null; }\n");
  }
  return root;
}

describe("the audit's sample is a claim, not whatever happens to exist", () => {
  it("fails, naming the page, when one language's page stops being built", () => {
    const result = run(buildExport(["es/paying-for-training/index.html"]));
    expect(result.status).toBe(1);
    expect(result.stderr).toContain("Paying for training (Spanish)");
    expect(result.stderr).toContain("not in");
  });

  it("fails when a whole page type is gone rather than auditing the rest", () => {
    // `firstDirIn` returns null for a directory that is not there, which the old filter
    // dropped as silently as a missing file.
    const result = run(
      buildExport([
        "en/providers/some-provider/index.html",
        "en/providers/index.html",
        "es/providers/some-provider/index.html",
        "es/providers/index.html",
      ]),
    );
    expect(result.status).toBe(1);
    expect(result.stderr).toContain("Provider detail (English)");
    expect(result.stderr).toContain("Provider index (Spanish)");
  });

  it("says so plainly when there is no build at all", () => {
    const result = run(join(tmpdir(), "a11y-audit-nothing-here"));
    expect(result.status).toBe(1);
    expect(result.stderr).toContain("run the site build first");
  });

  it("passes the sample check, and audits every page, when all of them are present", () => {
    // The other half. A gate that always fails is as useless as one that always passes, and
    // this is also what pins the sample size: 22 pages, named, not "whatever was there".
    const result = run(buildExport());
    expect(result.status).toBe(0);
    expect(result.stdout).toContain("22 pages, all present");
    expect(result.stdout).toContain("Paying for training (Spanish)");
    expect(result.stdout).toContain("Program detail (English)");
  });
});

/**
 * The direction the check above cannot see.
 *
 * It asks whether every page the list names was built. A route added to the app is the
 * opposite shape: nothing on the list is missing, every named page is there, and the gate
 * goes on reporting "no violations" over a sample that no longer describes the site. The new
 * page is also the one most likely to be carrying a violation, because it is the page nobody
 * has looked at yet.
 */
describe("a route the list does not name is unaudited, not passing", () => {
  it("fails, naming the route and both languages, when a page is added to the app", () => {
    const result = run(buildExport(), buildApp(["[lang]/scholarships/page.tsx"]));
    expect(result.status).toBe(1);
    expect(result.stderr).toContain("/[lang]/scholarships (en)");
    expect(result.stderr).toContain("/[lang]/scholarships (es)");
    expect(result.stderr).toContain("never reads");
  });

  it("fails for a route with no [lang] segment too", () => {
    const result = run(buildExport(), buildApp(["health/page.tsx"]));
    expect(result.status).toBe(1);
    expect(result.stderr).toContain("/health");
  });

  it("passes when the app declares exactly the routes the list covers", () => {
    // The half that keeps this honest: today's list does cover today's app, so this gate
    // starts green and only a real change can turn it red.
    const result = run(buildExport(), buildApp());
    expect(result.status).toBe(0);
    expect(result.stdout).toContain("22 pages, all present");
  });

  it("reads this repository's own app when nothing overrides it", () => {
    // The override exists for the tests above; the gate that actually runs in CI must read
    // the real tree, and this is what would notice if it stopped.
    const result = run(buildExport());
    expect(result.status).toBe(0);
  });
});

/**
 * An environment variable must not be able to turn the gate into a printer.
 *
 * `A11Y_PAGE` names one page and puts the script in child mode. It used to select that mode
 * on its own: `if (process.env.A11Y_PAGE)`, checked before the missing-page check, before the
 * uncovered-route check, and before the loop. The parent hands its whole environment to each
 * child, so exporting the variable to look at a single page is an ordinary thing to do — and
 * from then on every `npm run a11y`, a step of `npm run verify`, printed one page's findings
 * as JSON on stdout and exited 0. Not "no violations". No verdict at all, and no message
 * saying the other 21 pages had been skipped.
 *
 * So the flag decides and the variable only carries the path. These two tests are the pair:
 * a stray variable no longer disables anything, and child mode still works when asked for.
 */
describe("the gate cannot be switched off from the environment", () => {
  function runWith(env: Record<string, string>, args: string[] = ["--list"]) {
    return spawnSync(process.execPath, [AUDIT, buildExport(), ...args], {
      encoding: "utf-8",
      env: { ...process.env, ...env },
    });
  }

  it("audits the whole sample even when A11Y_PAGE is set in the environment", () => {
    const result = runWith({ A11Y_PAGE: join(buildExport(), "en", "index.html") });
    expect(result.status).toBe(0);
    expect(result.stdout).toContain("22 pages, all present");
    expect(result.stderr).toContain("ignoring A11Y_PAGE");
  });

  it("still refuses a build with a page missing, with the variable set", () => {
    // The check that matters: the stray variable must not skip the sample check either.
    const root = buildExport(["es/ctdl/index.html"]);
    const result = spawnSync(process.execPath, [AUDIT, root, "--list"], {
      encoding: "utf-8",
      env: { ...process.env, A11Y_PAGE: join(root, "en", "index.html") },
    });
    expect(result.status).toBe(1);
    expect(result.stderr).toContain("CTDL export (Spanish)");
  });

  it("refuses --child with no page to audit rather than auditing nothing", () => {
    const result = runWith({}, ["--child"]);
    expect(result.status).toBe(1);
    expect(result.stderr).toContain("needs A11Y_PAGE");
  });
});
