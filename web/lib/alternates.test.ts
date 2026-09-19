import { describe, expect, it } from "vitest";

import { metadata as rootMetadata } from "@/app/page";
import { generateMetadata as aboutMetadata } from "@/app/[lang]/about/page";
import { generateMetadata as ctdlMetadata } from "@/app/[lang]/ctdl/page";
import { generateMetadata as langLayoutMetadata } from "@/app/[lang]/layout";
import { generateMetadata as occupationMetadata } from "@/app/[lang]/occupations/[soc]/page";
import { generateMetadata as occupationsMetadata } from "@/app/[lang]/occupations/page";
import { generateMetadata as coverageMetadata } from "@/app/[lang]/outcomes-coverage/page";
import { generateMetadata as homeMetadata } from "@/app/[lang]/page";
import { generateMetadata as fundingMetadata } from "@/app/[lang]/paying-for-training/page";
import { generateMetadata as programMetadata } from "@/app/[lang]/programs/[id]/page";
import { generateMetadata as providerMetadata } from "@/app/[lang]/providers/[slug]/page";
import { generateMetadata as providersMetadata } from "@/app/[lang]/providers/page";
import sitemap from "@/app/sitemap";
import { exportedPagePattern, isPerLanguage, routeTemplates } from "@/scripts/routes.mjs";

import { allOccupationCodes, allProgramIds, getSearchIndex } from "./data";
import { DEFAULT_LANG, LANGUAGES, type Lang } from "./i18n";
import { groupByProvider } from "./providers";
import { sitePaths } from "./routes";
import { SITE_URL, languageAlternates, pageAlternates, urlFor } from "./site";

/**
 * Which URL each page says it is, and which URL is the same record in the other language.
 *
 * ---- What was published before this file existed ----
 *
 * No canonical. Measured on the live site on 2026-09-13 over 27 URLs sampled from a
 * `sitemap.xml` holding 9,046 of them: **not one page emitted `<link rel="canonical">`**, and
 * there was no `Link:` header carrying one. The only canonical anywhere in the export was on
 * `/`, and it was the relative string `/en/` -- valid HTML, and the one form of the tag worth
 * less than none, since a reader handed it out of context resolves it against itself.
 *
 * ---- What was half there, and is now in both halves ----
 *
 * hreflang. A first reading called it absent everywhere; that was true of the head and false
 * of the site. `app/sitemap.ts` has published the pairs all along -- 18,092 reciprocal
 * `<xhtml:link rel="alternate" hreflang>` entries over those 9,046 URLs -- and sitemap-level
 * hreflang is a first-class declaration, not a lesser one.
 *
 * It is now declared in each page's head as well, which is what `chelseakr.com` does on the
 * other bilingual site in this portfolio, and both sets gain an `x-default` neither carried.
 * The two are not alternatives to pick between: the sitemap is the declaration a crawler can
 * read before fetching anything, the head is the one that survives the page being reached
 * from a link, a share, or a search result for the other language.
 *
 * The objection to publishing both -- two descriptions of one relationship are two things
 * that can disagree, with nothing to say which a crawler believed -- is answered by
 * construction rather than by care. `languageAlternates` in `lib/site.ts` is the only
 * expression of the relationship; the sitemap and every page call it with the same `rest`.
 * This file asserts that they still do, entry by entry, and `scripts/seo-audit.mjs` asserts
 * the same thing again over the built HTML.
 *
 * That none of it was ever gated is the finding that survives. A sitemap that stopped
 * emitting alternates, or emitted a one-way set, would take the site's entire bilingual-search
 * story with it through a green build and show no symptom, because search engines discard a
 * one-way annotation and that is indistinguishable from publishing none.
 *
 * ---- Why this test derives its list instead of holding one ----
 *
 * A gate that walks a list somebody typed is a gate that stays green over the pages nobody
 * added to the list. This project has met that shape repeatedly and `scripts/routes.mjs`
 * exists because of it. So nothing here is enumerated by hand:
 *
 * - the URLs come from `lib/routes.ts`, which is also where `app/sitemap.ts` gets them, so
 *   the pairs checked are exactly the pairs published;
 * - the pages come from `scripts/routes.mjs`, which walks the app router's own file tree, so
 *   a new `page.tsx` fails this file until it is named in `ROUTES` below;
 * - the two are then checked against each other, so a URL the sitemap publishes with no page
 *   to answer for it -- and a page with no URL -- are both findings rather than silence.
 *
 * And the sweep is asserted to be a sweep. Every one of those derivations can return an empty
 * list if something upstream breaks, and an empty list passes every `for` loop ever written.
 */

/** One real id per dynamic route, taken from the dataset the export will actually run over. */
const FIRST_PROGRAM = allProgramIds()[0] ?? "";
const FIRST_PROVIDER = groupByProvider(getSearchIndex().programs)[0]?.slug ?? "";
const FIRST_OCCUPATION = allOccupationCodes()[0] ?? "";

/**
 * Every page under `/[lang]/`, with the path it should be claiming and the real
 * `generateMetadata` that has to claim it.
 *
 * The templates are checked against the app router's file tree below, so this table cannot
 * silently fall behind the site. What it adds that the file tree cannot is the pairing: which
 * exported function answers for which template, and with what parameters. Calling the real
 * exported function is the point -- a helper that returns the right object and a page that
 * never calls it is precisely the bug this file exists to catch, and it is invisible to any
 * test that imports the helper alone.
 */
const ROUTES = [
  {
    template: "/[lang]",
    rest: "",
    metadata: (lang: Lang) => homeMetadata({ params: Promise.resolve({ lang }) }),
  },
  {
    template: "/[lang]/about",
    rest: "about/",
    metadata: (lang: Lang) => aboutMetadata({ params: Promise.resolve({ lang }) }),
  },
  {
    template: "/[lang]/ctdl",
    rest: "ctdl/",
    metadata: (lang: Lang) => ctdlMetadata({ params: Promise.resolve({ lang }) }),
  },
  {
    template: "/[lang]/occupations",
    rest: "occupations/",
    metadata: (lang: Lang) => occupationsMetadata({ params: Promise.resolve({ lang }) }),
  },
  {
    template: "/[lang]/outcomes-coverage",
    rest: "outcomes-coverage/",
    metadata: (lang: Lang) => coverageMetadata({ params: Promise.resolve({ lang }) }),
  },
  {
    template: "/[lang]/paying-for-training",
    rest: "paying-for-training/",
    metadata: (lang: Lang) => fundingMetadata({ params: Promise.resolve({ lang }) }),
  },
  {
    template: "/[lang]/providers",
    rest: "providers/",
    metadata: (lang: Lang) => providersMetadata({ params: Promise.resolve({ lang }) }),
  },
  {
    template: "/[lang]/occupations/[soc]",
    rest: `occupations/${FIRST_OCCUPATION}/`,
    metadata: (lang: Lang) =>
      occupationMetadata({ params: Promise.resolve({ lang, soc: FIRST_OCCUPATION }) }),
  },
  {
    template: "/[lang]/programs/[id]",
    rest: `programs/${FIRST_PROGRAM}/`,
    metadata: (lang: Lang) =>
      programMetadata({ params: Promise.resolve({ lang, id: FIRST_PROGRAM }) }),
  },
  {
    template: "/[lang]/providers/[slug]",
    rest: `providers/${FIRST_PROVIDER}/`,
    metadata: (lang: Lang) =>
      providerMetadata({ params: Promise.resolve({ lang, slug: FIRST_PROVIDER }) }),
  },
] as const;

describe("the sample this file checks is the whole site", () => {
  it("found a real program, provider and occupation to address the dynamic routes with", () => {
    // Without these the three dynamic templates would be checked at `programs//`, which is a
    // URL the site does not publish, and every assertion below them would pass over nothing.
    expect(FIRST_PROGRAM).toBeTruthy();
    expect(FIRST_PROVIDER).toBeTruthy();
    expect(FIRST_OCCUPATION).toBeTruthy();
  });

  it("names every page the app router will build in both languages", () => {
    // Read off `app/`, not remembered. Add `app/[lang]/anything/page.tsx` and this fails
    // until `ROUTES` names it -- which is the only way the checks below can be a statement
    // about the site rather than about whoever last edited this file.
    const built = routeTemplates().filter(isPerLanguage).sort();
    expect(built).toEqual([...ROUTES.map((route) => route.template)].sort());
  });
});

/**
 * The pairs, grouped by the language-independent half of the path.
 *
 * `sitePaths()` is what `app/sitemap.ts` publishes, so this is the published site and not a
 * description of it.
 */
const PAIRS = new Map<string, Lang[]>();
for (const { lang, rest } of sitePaths()) {
  PAIRS.set(rest, [...(PAIRS.get(rest) ?? []), lang]);
}

describe("every URL the sitemap publishes", () => {
  it("is a sweep of thousands of pages, not a handful", () => {
    // The guard on every derivation above. `sitePaths()` reads three dataset files through
    // `lib/data.ts`; any of them arriving empty -- a fixture build, a path that moved, a
    // parse that failed -- would leave this file iterating over nothing and reporting a pass.
    // 100 is far below the real figure (4,523 pairs against the production dataset, 9,046
    // URLs) and far above anything a collapse would leave behind.
    expect(PAIRS.size, "the sweep collapsed; it would prove nothing").toBeGreaterThan(100);
  });

  it("exists in both languages, so there is a pair to be reciprocal about", () => {
    const lopsided = [...PAIRS].filter(([, langs]) => langs.length !== LANGUAGES.length);
    expect(lopsided).toEqual([]);
  });

  it("has a page that answers for it", () => {
    // Both sides derived: the URLs from `lib/routes.ts`, the matchers from the app router's
    // file tree. A URL in the sitemap that no `page.tsx` renders is a 404 advertised to
    // crawlers; a URL rendered by a page this file does not know about would be checked by
    // nothing below.
    const unmatched = sitePaths().filter(
      ({ lang, rest }) =>
        !ROUTES.some((route) =>
          exportedPagePattern(route.template, lang).test(`${lang}/${rest}index.html`),
        ),
    );
    expect(unmatched).toEqual([]);
  });
});

describe("every page the site builds", () => {
  it("is in the sitemap, except `/about/`, which has never been", () => {
    // Recorded rather than fixed. `about/` was absent from `app/sitemap.ts`'s list before
    // this work and is absent from `lib/routes.ts` after it, because adding it changes what
    // the site advertises to crawlers and that is a publication decision, not a refactor.
    // The page still emits its own canonical and its own alternates -- being absent from a
    // sitemap is not being unindexable -- so what this asserts is that the gap is this one
    // page and has not quietly grown.
    const absent = ROUTES.filter((route) => !PAIRS.has(route.rest)).map((route) => route.template);
    expect(absent).toEqual(["/[lang]/about"]);
  });
});

describe.each(ROUTES)("$template", ({ rest, metadata }) => {
  it.each(LANGUAGES)("declares itself canonical, absolutely, in %s", async (lang) => {
    const page = await metadata(lang);

    // Absolute, because a relative canonical is resolved by the reader against whatever it
    // believes the base to be -- which for a syndicated copy, a scraper or an unfurler
    // working from a cached body is not this site. `/` shipped exactly that for months.
    expect(page.alternates?.canonical).toBe(`${SITE_URL}/${lang}/${rest}`);
    expect(String(page.alternates?.canonical)).toMatch(/^https:\/\//);
  });

  it("names every language version of itself, and an x-default", async () => {
    // The measured defect in the head: zero `hreflang` across 9,046 pages, 4,523 of them
    // Spanish. Every version has to name every version *including itself* -- a set that is
    // not reciprocal is discarded, and a discarded annotation is indistinguishable from one
    // that was never published.
    for (const lang of LANGUAGES) {
      const page = await metadata(lang);
      expect(page.alternates?.languages).toEqual(languageAlternates(rest));
      for (const other of LANGUAGES) {
        expect(page.alternates?.languages?.[other]).toBe(urlFor(other, rest));
      }
      expect(page.alternates?.languages?.["x-default"]).toBe(urlFor(DEFAULT_LANG, rest));
    }
  });

  it("says the same thing in its head as the sitemap says about it", async () => {
    // The whole answer to "why is it safe to declare this twice". Both sides are read from
    // the build rather than described: this is the page's real `generateMetadata`, and the
    // entry is `app/sitemap.ts`'s real output for the same URL.
    for (const lang of LANGUAGES) {
      const page = await metadata(lang);
      const entry = sitemap().find((candidate) => candidate.url === urlFor(lang, rest));
      // `/[lang]/about` is deliberately not in the sitemap; there is nothing to agree with.
      if (entry === undefined) continue;
      expect(entry.alternates?.languages).toEqual(page.alternates?.languages);
    }
  });

  it("keeps the share card it already had", async () => {
    // Next assigns a child's `openGraph` over its parent's rather than merging into it, so
    // adding `alternates` by way of a different helper is one careless line away from
    // dropping `og:image`, `og:site_name`, `og:locale` and `og:type` from ~9,000 pages. That
    // is invisible in review and visible only in the built head.
    const page = await metadata(DEFAULT_LANG);
    const layout = await langLayoutMetadata({ params: Promise.resolve({ lang: DEFAULT_LANG }) });

    for (const key of Object.keys(layout.openGraph ?? {})) {
      expect(page.openGraph).toHaveProperty(key);
    }
    expect(page.twitter).toHaveProperty("card", "summary_large_image");
  });

  it("tells an unfurler the same URL it tells a crawler", async () => {
    const page = await metadata(DEFAULT_LANG);
    expect(page.openGraph).toHaveProperty("url", page.alternates?.canonical);
  });
});

describe("the language layout", () => {
  it("still declares no URL of its own", async () => {
    // The one file here that must not. Next merges layout metadata into every descendant
    // that does not override the same key, so a canonical written once here would become the
    // canonical of all ~9,000 pages beneath it -- which is what happened in August 2026, and
    // is why `shareMetadata` and `pageMetadata` are two functions.
    const layout = await langLayoutMetadata({ params: Promise.resolve({ lang: DEFAULT_LANG }) });

    expect(layout.alternates).toBeUndefined();
    expect(layout.openGraph).not.toHaveProperty("url");
  });
});

describe("the language chooser at the site root", () => {
  it("declares an absolute canonical, not the relative one it used to hand-write", () => {
    // `<link rel="canonical" href="/en/">`, written into the page's own `<head>` element,
    // was the only canonical anywhere in the export.
    expect(rootMetadata.alternates?.canonical).toBe(`${SITE_URL}/${DEFAULT_LANG}/`);
  });

  it("points at `/en/`, which is where it sends a reader and is a page that names itself", () => {
    // Deliberately not `/`. This page is a `<meta http-equiv="refresh">` shim with no content
    // of its own; the page a search result should land on is the one it forwards to.
    expect(rootMetadata.alternates?.canonical).toBe(`${SITE_URL}/${DEFAULT_LANG}/`);
    expect(rootMetadata.alternates?.languages).toBeUndefined();
  });
});

describe("pageAlternates", () => {
  it("names the page it was asked about, absolutely, in every language", () => {
    for (const lang of LANGUAGES) {
      expect(pageAlternates(lang, "programs/1234/")?.canonical).toBe(
        `${SITE_URL}/${lang}/programs/1234/`,
      );
    }
  });

  it("declares one entry per language plus an x-default, all absolute", () => {
    const languages = pageAlternates(DEFAULT_LANG, "occupations/29-1141/")?.languages ?? {};

    expect(Object.keys(languages).sort()).toEqual([...LANGUAGES, "x-default"].sort());
    for (const href of Object.values(languages)) expect(String(href)).toMatch(/^https:\/\//);
  });

  it("points x-default at the default language, the same URL as `en`", () => {
    // `x-default` names where a reader whose language matches no version should be sent. The
    // site root would be the better answer -- it is a language chooser -- except that
    // `app/page.tsx` canonicalizes `/` to `/en/`, so naming it here would put a URL in the
    // set that the set's own members disown.
    const languages = pageAlternates("es", "programs/1234/")?.languages ?? {};
    expect(languages["x-default"]).toBe(languages[DEFAULT_LANG]);
    expect(languages["x-default"]).toBe(`${SITE_URL}/${DEFAULT_LANG}/programs/1234/`);
  });
});

/**
 * The hreflang annotations themselves, checked against the function that publishes them.
 *
 * `app/sitemap.ts` is imported and run rather than described: this is the only thing in the
 * repository that makes the en/es pairing legible to a search engine, it has never had a
 * gate, and a one-way or missing alternate set is invisible from the outside -- engines
 * discard it, which looks exactly like it never existing.
 */
describe("the sitemap's language alternates", () => {
  const entries = sitemap();
  const byUrl = new Map(entries.map((entry) => [entry.url, entry.alternates?.languages ?? {}]));

  it("covers every URL the site publishes, and is a sweep of thousands", () => {
    expect(entries.length, "the sitemap collapsed; it would prove nothing").toBeGreaterThan(200);
    expect(entries.length).toBe(sitePaths().length);
  });

  it("names every URL in its own alternate set, so no annotation is one-way", () => {
    // "A names B" is worth nothing unless B names A back and both name themselves. Checked
    // over all 9,046 rather than a sample, because the cost is a map lookup and the failure
    // being guarded against is one page in a pair silently dropping out.
    // `x-default` is deliberately a second name for the English URL rather than a URL of its
    // own, so reciprocity is asked of the language entries only. Including it would compare a
    // URL against itself and pass for the wrong reason.
    const urls = (languages: Record<string, string | URL | undefined>) =>
      LANGUAGES.map((lang) => languages[lang])
        .filter((href) => href !== undefined)
        .map(String);

    const oneWay: string[] = [];
    for (const [url, languages] of byUrl) {
      const targets = urls(languages);
      if (!targets.includes(url)) oneWay.push(`${url}: does not name itself`);
      for (const target of targets) {
        const twin = byUrl.get(target);
        if (twin === undefined) oneWay.push(`${url}: names ${target}, which is not published`);
        else if (!urls(twin).includes(url)) {
          oneWay.push(`${url}: names ${target}, which does not name it back`);
        }
      }
    }
    expect(oneWay.slice(0, 10)).toEqual([]);
  });

  it("offers every language the site is published in, and an x-default", () => {
    for (const [url, languages] of byUrl) {
      expect(Object.keys(languages).sort(), url).toEqual([...LANGUAGES, "x-default"].sort());
    }
  });
});
