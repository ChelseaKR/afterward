import { readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { generateMetadata as langLayoutMetadata } from "@/app/[lang]/layout";
import { generateMetadata as occupationMetadata } from "@/app/[lang]/occupations/[soc]/page";
import { generateMetadata as programMetadata } from "@/app/[lang]/programs/[id]/page";
import { generateMetadata as providerMetadata } from "@/app/[lang]/providers/[slug]/page";

import { allOccupationCodes, allProgramIds, getSearchIndex } from "./data";
import { LANGUAGES, type Lang } from "./i18n";
import { groupByProvider } from "./providers";
import { SITE_URL, langCard, rootCard, shareMetadata } from "./site";

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

/**
 * What a shared link to one page actually says it is.
 *
 * The cards above are the picture. This is the words, and the words were the half that was
 * wrong: every page under `/[lang]/` set a specific `<title>` and a specific description and
 * then unfurled under the layout's site-wide pair, because Next builds `og:title` from
 * `openGraph.title` and never from `title`. Sharing one of 3,266 programs produced the same
 * card as sharing the home page.
 *
 * Asserted against the real `generateMetadata` of the real routes, with real ids out of the
 * dataset, rather than against `shareMetadata` alone. A helper that returns the right object
 * and a page that does not call it is exactly the bug this file exists to catch, and it is
 * invisible to any test that only imports the helper.
 */

/** One real id per detail route, taken from the dataset the build will run over. */
const FIRST_PROGRAM = allProgramIds()[0];
const FIRST_PROVIDER = groupByProvider(getSearchIndex().programs)[0]?.slug;
const FIRST_OCCUPATION = allOccupationCodes()[0];

const DETAIL_ROUTES = [
  {
    what: "a program page",
    metadata: (lang: Lang) =>
      programMetadata({ params: Promise.resolve({ lang, id: FIRST_PROGRAM ?? "" }) }),
  },
  {
    what: "a provider page",
    metadata: (lang: Lang) =>
      providerMetadata({ params: Promise.resolve({ lang, slug: FIRST_PROVIDER ?? "" }) }),
  },
  {
    what: "an occupation page",
    metadata: (lang: Lang) =>
      occupationMetadata({ params: Promise.resolve({ lang, soc: FIRST_OCCUPATION ?? "" }) }),
  },
] as const;

const CASES = LANGUAGES.flatMap((lang) =>
  DETAIL_ROUTES.map((route) => ({ ...route, lang, name: `${route.what} in ${lang}` })),
);

describe("the dataset offers one of each to test against", () => {
  it("has a program, a provider and an occupation", () => {
    expect(FIRST_PROGRAM).toBeTruthy();
    expect(FIRST_PROVIDER).toBeTruthy();
    expect(FIRST_OCCUPATION).toBeTruthy();
  });
});

describe.each(CASES)("$name", ({ lang, metadata }) => {
  it("puts its own title on the card, not the site's", async () => {
    const page = await metadata(lang);
    const site = await langLayoutMetadata({ params: Promise.resolve({ lang }) });

    // The whole defect, in one line: this was the layout's title on every detail page.
    expect(page.openGraph?.title).not.toBe(site.openGraph?.title);
    // And the fix has to be the page's own title rather than some third string written for
    // the card, or the two drift the first time either is edited.
    expect(page.openGraph?.title).toBe(page.title);
  });

  it("puts its own description on the card, not the site's", async () => {
    const page = await metadata(lang);
    const site = await langLayoutMetadata({ params: Promise.resolve({ lang }) });

    expect(page.openGraph?.description).not.toBe(site.openGraph?.description);
    expect(page.openGraph?.description).toBe(page.description);
  });

  it("says the same thing to X as to everyone else", async () => {
    const page = await metadata(lang);

    // Next fills `twitter` from `openGraph` only where the resolved `twitter` is empty, and
    // after the layout it never is. A page that set `openGraph` alone would publish its own
    // `og:title` beside a `twitter:title` still reading the site's name.
    expect(page.twitter?.title).toBe(page.title);
    expect(page.twitter?.description).toBe(page.description);
  });

  it("keeps every field the layout's card had", async () => {
    const page = await metadata(lang);
    const site = await langLayoutMetadata({ params: Promise.resolve({ lang }) });

    // Next assigns a child's `openGraph` over its parent's rather than merging into it, so
    // adding the two missing fields on their own would have deleted the six that were right.
    // A key here that the layout has and the page does not is a tag that stopped being
    // emitted -- silently, and only on the ~9,000 pages nobody opens in review.
    for (const key of Object.keys(site.openGraph ?? {})) {
      expect(page.openGraph).toHaveProperty(key);
    }
    expect(page.twitter).toHaveProperty("card", "summary_large_image");
  });

  it("still carries this language's card image", async () => {
    const page = await metadata(lang);

    // Deliberately the site card and not a per-program one. What changed is the words.
    expect(page.openGraph?.images).toEqual([langCard(lang, expect.any(String))]);
    expect(page.twitter?.images).toEqual([langCard(lang, expect.any(String))]);
  });

  it("is written in the language of the page it describes", async () => {
    const page = await metadata(lang);
    const other = await metadata(lang === "en" ? "es" : "en");

    // Both trees emitted the same English pair for months. A card in a language its reader
    // does not speak is the one surface where that cannot be skimmed past.
    expect(page.openGraph?.description).not.toBe(other.openGraph?.description);
  });
});

describe("shareMetadata", () => {
  it("says the same thing in all three places", () => {
    const { title, description, openGraph, twitter } = shareMetadata(
      "en",
      "A title",
      "A description",
    );

    expect([title, openGraph?.title, twitter?.title]).toEqual(["A title", "A title", "A title"]);
    expect([description, openGraph?.description, twitter?.description]).toEqual([
      "A description",
      "A description",
      "A description",
    ]);
  });

  it("declares the locale of the language it was given", () => {
    expect(shareMetadata("en", "t", "d").openGraph?.locale).toBe("en_US");
    expect(shareMetadata("es", "t", "d").openGraph?.locale).toBe("es_US");
  });

  it("names the site, which is the one thing the page title deliberately does not", () => {
    // The detail titles leave "Afterward" out to spend the characters on the provider's name.
    // `og:site_name` is where an unfurler expects to read it, and it costs the title nothing.
    expect(shareMetadata("en", "t", "d").openGraph?.siteName).toBe("Afterward");
  });
});
