import type { Metadata } from "next";
import Link from "next/link";

import { DEFAULT_LANG, LANGUAGES, LANG_NAME, dict } from "@/lib/i18n";
import { ROOT_DESCRIPTION, ROOT_TITLE, SITE_URL, rootCard } from "@/lib/site";

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
 */
export const metadata: Metadata = {
  title: ROOT_TITLE,
  description: ROOT_DESCRIPTION,
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
        <link rel="canonical" href={`/${DEFAULT_LANG}/`} />
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
        </main>
      </body>
    </html>
  );
}
