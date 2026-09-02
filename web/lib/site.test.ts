import { readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { LANGUAGES } from "./i18n";
import { SITE_URL, langCard, rootCard } from "./site";

/**
 * The share cards, checked as files rather than as strings.
 *
 * A card fails in ways nothing else in this repository would notice. It is a binary nobody
 * reads in review, referenced by a URL that resolves whatever the bytes behind it are, and
 * the two ways it goes wrong are both silent: the wrong dimensions and the tags below start
 * lying about the aspect ratio, so the unfurler reserves a box the picture does not fill;
 * too many bytes and Slack and iMessage drop the image and render no card at all, which
 * looks exactly like having no card, which is the bug this file was added to fix.
 *
 * So the numbers promised to a crawler are read back out of the PNG itself, and the budget
 * is asserted against the real ceiling rather than against what these files happen to weigh.
 */

const PUBLIC = fileURLToPath(new URL("../public/", import.meta.url));

/** Width and height out of a PNG's IHDR, which is always the first chunk. */
function pngSize(bytes: Buffer): { width: number; height: number } {
  expect(bytes.subarray(1, 4).toString("ascii")).toBe("PNG");
  expect(bytes.subarray(12, 16).toString("ascii")).toBe("IHDR");
  return { width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20) };
}

/**
 * Slack and iMessage stop fetching an unfurl image somewhere near a megabyte and show
 * nothing rather than something. Flat PNGs of type come in around 50 KB, so this is a
 * ceiling with two orders of magnitude of headroom, not a target to be crept up on.
 */
const MAX_BYTES = 1_000_000;

const CARDS = [
  { what: "the bilingual root card", card: rootCard("alt") },
  ...LANGUAGES.map((lang) => ({ what: `the ${lang} card`, card: langCard(lang, "alt") })),
];

describe.each(CARDS)("$what", ({ card }) => {
  const path = `${PUBLIC}${card.url.slice(SITE_URL.length + 1)}`;

  it("is served from an absolute https URL", () => {
    // Relative would be valid HTML and useless: an unfurler resolves og:image against
    // nothing and drops it. This is also what makes the deploy guard able to catch a build
    // that never received NEXT_PUBLIC_SITE_URL.
    expect(card.url).toMatch(/^https:\/\/[^/]+\/og\/afterward(-en|-es)?\.png$/);
  });

  it("exists at the path it advertises", () => {
    expect(() => statSync(path)).not.toThrow();
  });

  it("is the size it tells crawlers it is", () => {
    expect(pngSize(readFileSync(path))).toEqual({ width: card.width, height: card.height });
  });

  it("is 1200x630, the ratio every unfurler crops from cleanly", () => {
    expect([card.width, card.height]).toEqual([1200, 630]);
  });

  it("is small enough that Slack and iMessage will fetch it", () => {
    expect(statSync(path).size).toBeLessThan(MAX_BYTES);
  });
});

describe("the site URL", () => {
  it("falls back to an obvious placeholder, never to a real domain", () => {
    // With NEXT_PUBLIC_SITE_URL unset -- which is the case here, and in CI -- every absolute
    // URL in the export has to name somewhere that cannot resolve.
    expect(SITE_URL).toBe("https://example.invalid");
  });

  it("carries no trailing slash, so callers can append a rooted path", () => {
    expect(SITE_URL.endsWith("/")).toBe(false);
  });
});

describe("card alt text", () => {
  it("describes the picture in the language of the page it is on", () => {
    expect(langCard("en", "alt").url).toContain("afterward-en");
    expect(langCard("es", "alt").url).toContain("afterward-es");
  });
});
