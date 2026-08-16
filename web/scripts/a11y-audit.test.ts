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
function run(root: string) {
  return spawnSync(process.execPath, [AUDIT, root, "--list"], { encoding: "utf-8" });
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
