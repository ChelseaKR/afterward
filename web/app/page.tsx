import type { Metadata } from "next";
import Link from "next/link";

import { DEFAULT_LANG, LANGUAGES, LANG_NAME, dict } from "@/lib/i18n";
import {
  REPO_URL,
  ROOT_DESCRIPTION,
  ROOT_TITLE,
  SITE_URL,
  urlFor,
  rootCard,
} from "@/lib/site";

export const dynamic = "force-static";

/** Both languages, because this URL is in both. */
const CARD_ALT =
  "The Afterward wordmark over the site's tagline in English and Spanish, above the notice " +
  "that this is not a California state website.";

/**
 * Share metadata on the root, which is the URL most likely to be pasted and was the one page
 * in the site that had none.
 *
 * This page redirects, and that is exactly why the tags have to be here. A link unfurler --
 * Slack, LinkedIn, X, Mastodon, iMessage -- fetches the URL it was given, reads that
 * document's `<head>`, and stops. It runs no JavaScript and does not follow a
 * `<meta http-equiv="refresh">`, so everything the language chooser knows about itself has
 * to be in this head or it is not read at all. Before this, sharing the bare domain produced
 * a bare title and nothing else: no description, no image, no card. The redirect below is
 * untouched -- a browser still lands on `/en/` -- and only the crawler's view changes.
 *
 * `openGraph.url` is safe here in a way `app/[lang]/layout.tsx` explains it is not there:
 * this is a page, not a layout, so nothing inherits it. It names the canonical root, so a
 * share of `camino.chelseakr.com` -- which 301s here -- and a share of a URL with tracking
 * parameters both resolve to one card rather than several.
 *
 * `summary_large_image` rather than `summary`, and unlike the language pages this one has
 * always had the room for it: the card is the bilingual one, because this URL belongs to no
 * language.
 *
 * ---- The canonical, which was written into the JSX below and was relative ----
 *
 * `<link rel="canonical" href="/en/">` in the `<head>` element this page renders: valid
 * HTML, and the one form of the tag that is worth less than none. A canonical is a claim
 * about an address, so a resolver that is handed it out of context -- a syndicated copy, a
 * scraper, an unfurler working from a cached body -- resolves it against whatever it thinks
 * the base is. It is declared through `alternates` now, which is what makes Next emit it
 * absolute against `SITE_URL` and what puts it under the same gate as every other page's.
 *
 * The value is unchanged and is deliberately not `/`: this page is a `<meta http-equiv=
 * "refresh">` shim with no content of its own, and the page a search result should land on
 * is `/en/`.
 *
 * And deliberately no `hreflang` set here, unlike every page under `/[lang]/`. A page that
 * canonicalises somewhere else is not a member of an alternate set: naming it in one would
 * put a URL in the set that the set's own members disown, and search engines resolve that
 * contradiction by discarding the annotation. The chooser's job is to forward a reader, and
 * the two pages it forwards to name each other.
 */
export const metadata: Metadata = {
  title: ROOT_TITLE,
  description: ROOT_DESCRIPTION,
  alternates: { canonical: urlFor(DEFAULT_LANG, "") },
  openGraph: {
    type: "website",
    siteName: "Afterward",
    title: ROOT_TITLE,
    description: ROOT_DESCRIPTION,
    url: `${SITE_URL}/`,
    images: [rootCard(CARD_ALT)],
  },
  twitter: {
    card: "summary_large_image",
    title: ROOT_TITLE,
    description: ROOT_DESCRIPTION,
    images: [rootCard(CARD_ALT)],
  },
};

/**
 * Language chooser at the site root.
 *
 * This was previously `redirect()`, which under `output: "export"` does not produce a
 * redirect at all: Next emits an error shell with an empty body and no `lang` attribute.
 * Visitors without JavaScript got a blank page at the most-linked URL in the site, and
 * everyone else got a blank flash. A real page with a real `<meta http-equiv="refresh">`
 * works without JavaScript, and the visible links work even if the refresh is blocked.
 *
 * It is written in both languages rather than in the site default. This is the one URL that
 * belongs to no language, and it is the URL a search engine is most likely to hold, so the
 * page that has to tell a Spanish speaker where to go should not be the page that tells them
 * so in English. That applies first to the non-affiliation notice, which is here in the same
 * banner landmark and the same treatment it has on every other page: a visitor mistaking
 * this for a state website would be doing so before they ever pick a language.
 */
export default function Index() {
  return (
    <html lang={DEFAULT_LANG}>
      <head>
        <meta httpEquiv="refresh" content={`0; url=/${DEFAULT_LANG}/`} />
      </head>
      <body>
        <header className="disclaimer">
          <div className="shell">
            {LANGUAGES.map((lang) => (
              <p key={lang} lang={lang}>
                {dict(lang).notAffiliated}
              </p>
            ))}
          </div>
        </header>

        <main className="shell detail">
          <h1>{dict(DEFAULT_LANG).siteName}</h1>
          {/*
            Two sentences per language, then the way in. Someone arriving from a search
            engine had a wordmark and two links to go on, which says nothing about whether
            this is worth their time or who is behind it.
          */}
          <ul className="lang-choice">
            {LANGUAGES.map((lang) => {
              const t = dict(lang);
              return (
                <li key={lang} lang={lang}>
                  <h2>
                    {/* Unprefetched, and this page is the strongest case for it: both
                        entries are on screen at once, so prefetching would fetch the search
                        index twice over — 459 KB, English and Spanish — to save one click of
                        a choice only one of which will be taken. See app/[lang]/layout.tsx. */}
                    <Link href={`/${lang}/`} hrefLang={lang} prefetch={false}>
                      {LANG_NAME[lang]}
                    </Link>
                  </h2>
                  <p>{t.tagline}</p>
                  <p>{t.siteSummary}</p>
                </li>
              );
            })}
          </ul>

          {/*
            The link back to the source, here as well as in every language page's footer.
            This URL is the one a conformance check fetches -- it is what the repository's
            GitHub About names as the homepage -- and it serves this document rather than
            following the refresh, so a backlink that existed only under `/[lang]/` would be
            a backlink the check could not see. It is also the right thing on its own terms:
            this page tells a stranger that an unofficial site holds California's training
            data, and the sentence beside it is where they can go to check that.
          */}
          <p>
            {LANGUAGES.map((lang) => (
              <span key={lang} lang={lang}>
                {dict(lang).sourceCode}{" "}
              </span>
            ))}
            <a href={REPO_URL} rel="noopener noreferrer">
              {REPO_URL.replace("https://", "")}
            </a>
          </p>
        </main>
      </body>
    </html>
  );
}
