import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

/**
 * A gate nobody runs.
 *
 * `package.json` mapped `lint` to `next lint`, which Next 16 removed: it parsed `lint` as a
 * directory and exited 1 with `Invalid project directory provided, no such directory:
 * web/lint`. That went unnoticed for as long as it did because `verify` never called it. The
 * front end had never been linted, and two devDependencies were being kept current by
 * Dependabot for a command that could not run.
 *
 * Two separate failures, and this file is about the second one. A broken script announces
 * itself the moment someone runs it. A script missing from `verify` announces nothing ever,
 * and every other gate here is one line away from the same fate: drop `a11y:rendered` from
 * the chain and the build stays green over a site nobody looked at.
 *
 * So the chain is asserted rather than assumed. This is a string check, not a run -- whether
 * each gate passes is `npm run verify`'s question; whether it is still being asked is this
 * one.
 */
const PACKAGE = JSON.parse(
  readFileSync(fileURLToPath(new URL("../package.json", import.meta.url)), "utf-8"),
) as { scripts: Record<string, string> };

/** Every gate `verify` has to call, with what it is there to catch. */
const GATES: ReadonlyArray<readonly [string, string]> = [
  ["typecheck", "types, under strict and noUncheckedIndexedAccess"],
  ["lint", "the .mjs gate scripts, which tsc does not read"],
  ["test", "the unit suite, including the assistant panel's axe pass"],
  ["contrast", "34 token pairings at WCAG 2.2 AAA, light and dark"],
  ["build", "the static export, and the first-visit page-weight budget"],
  ["a11y", "axe over 22 built pages in both languages"],
  ["a11y:rendered", "axe in Chromium over what only exists after hydration"],
];

describe("every gate is still in the verify chain", () => {
  const verify = PACKAGE.scripts.verify ?? "";

  for (const [gate, what] of GATES) {
    it(`runs ${gate}: ${what}`, () => {
      expect(verify).toContain(`npm run ${gate}`);
    });
  }

  it("chains with && so the first failure stops the run", () => {
    expect(verify).not.toContain(";");
    expect(verify).not.toContain("||");
  });

  it("names a script for every gate it calls", () => {
    for (const [gate] of GATES) expect(PACKAGE.scripts[gate]).toBeTruthy();
  });
});

describe("the lint script is one that can run", () => {
  it("does not call `next lint`, which Next 16 removed", () => {
    expect(PACKAGE.scripts.lint).not.toContain("next lint");
  });

  it("calls eslint", () => {
    expect(PACKAGE.scripts.lint).toContain("eslint");
  });
});
