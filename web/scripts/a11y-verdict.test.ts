import { describe, expect, it } from "vitest";

import { askServiceUrl } from "@/lib/ask";

import { askServiceConfigured, verdict } from "./a11y-verdict.mjs";

/**
 * `a11y-rendered.mjs` reported this, on every build anybody has ever run it on:
 *
 *     skip  Assistant panel (English): not in this build
 *     ...
 *     a11y-rendered: no violations in the rendered search results, comparison table, or assistant panel
 *
 * The verdict was a string literal. It named a surface the run had just declined to read,
 * and it did so in the only configuration the gate is ever run in, since no build sets
 * `NEXT_PUBLIC_ASK_URL`. So the newest interface in the repository had no accessibility
 * coverage anywhere, under a sentence saying it had.
 *
 * These hold the two decisions that fix it: the verdict is built from what was read, and the
 * gate's expectation of a panel is decided by the same rule the panel itself uses.
 */
describe("the verdict names what was read and nothing else", () => {
  it("names the surfaces it was given", () => {
    expect(verdict({ failures: 0, audited: ["the comparison table (English)"] })).toBe(
      "a11y-rendered: no violations in the comparison table (English)",
    );
  });

  it("cannot name a surface that was not audited", () => {
    const line = verdict({
      failures: 0,
      audited: ["the rendered search results (English)", "the comparison table (English)"],
    });
    expect(line).not.toContain("assistant panel");
  });

  it("says so rather than passing when it read nothing at all", () => {
    expect(verdict({ failures: 0, audited: [] })).toContain("nothing was audited");
    expect(verdict({ failures: 0, audited: [] })).not.toContain("no violations");
  });

  it("reports failures ahead of anything it audited", () => {
    expect(verdict({ failures: 3, audited: ["the comparison table (English)"] })).toBe(
      "a11y-rendered: 3 node(s) failing",
    );
  });
});

describe("the gate expects a panel exactly when the build carries one", () => {
  /**
   * Both functions decide the same thing from the same variable: `askServiceUrl` decides
   * whether `AskPanel` renders anything, `askServiceConfigured` decides whether the gate
   * demands to find it. Two rules would mean the gate is wrong in whichever cases they
   * disagree on, which is why they are checked against each other rather than each against a
   * remembered list.
   */
  const ORIGINS = [
    undefined,
    "",
    "   ",
    "https://ask.example.test",
    "https://ask.example.test/",
    "https://ask.example.test///",
    "  https://ask.example.test  ",
    "http://localhost",
    "http://localhost:8765",
    "http://127.0.0.1:8765",
    "http://ask.example.test",
    "ftp://ask.example.test",
    "ask.example.test",
    "javascript:alert(1)",
  ];

  for (const origin of ORIGINS) {
    it(`agrees with askServiceUrl about ${JSON.stringify(origin)}`, () => {
      expect(askServiceConfigured(origin)).toBe(askServiceUrl(origin) !== null);
    });
  }

  it("treats an unset variable as a build with no panel", () => {
    expect(askServiceConfigured(undefined)).toBe(false);
  });
});
