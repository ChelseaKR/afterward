import type { Metadata } from "next";
import Link from "next/link";

import { DEFAULT_LANG, LANGUAGES, LANG_NAME, dict } from "@/lib/i18n";

/**
 * The page every mistyped, stale or guessed URL lands on.
 *
 * Until now this was Next's stock error screen: a bare "404: This page could not be found."
 * with no `<html lang>`, no masthead, no navigation, no Spanish, and — the part that actually
 * matters — no non-affiliation notice, on a site whose README and DISCLAIMER both say that
 * notice appears on every page. Someone who followed a broken link from a search result would
 * see a page in California's official design system, wearing California's colours, saying
 * nothing about who runs it. That is the one page on the site where being mistaken for a state
 * website is most likely, because it is the page that arrives with the least context.
 *
 * Written in both languages, like the site root and for the same reason: this URL belongs to
 * no language. A 404 is served for `/es/programs/typo/` exactly as for `/en/programs/typo/`,
 * and the visitor who most needs to be told this is not a state website is the one who cannot
 * read the language it would otherwise be told in. Nothing here privileges English beyond the
 * document's own `lang`, which has to be something; each block carries its own `lang` so a
 * screen reader switches voice rather than reading Spanish with English phonemes.
 *
 * Rendering `<html>` and `<body>` itself, because `app/layout.tsx` returns `children`
 * unwrapped — the same arrangement `app/page.tsx` uses at the site root.
 */
/*
 * The tab and the search result, said in both languages for the same reason the page is.
 *
 * Next reads a `metadata` export from this file and applies it last, after the root layout's,
 * so this replaces rather than joins "Camino — California training programs and their
 * outcomes" — which on a page that does not exist would be a third wrong thing about it.
 *
 * No `robots` key: Next marks the not-found route `noindex` on its own, and declaring it here
 * as well emits the tag twice.
 */
export const metadata: Metadata = {
  title: `${dict("en").notFoundTitle} · ${dict("es").notFoundTitle} — Camino`,
};

export default function NotFound() {
  return (
    <html lang={DEFAULT_LANG}>
      <body>
        {/*
          Above everything, in both languages, in the same banner treatment it has on every
          other page. This is the whole reason the stock screen was not acceptable.
        */}
        <header>
          <div className="disclaimer">
            <div className="shell">
              {LANGUAGES.map((lang) => (
                <p key={lang} lang={lang}>
                  {dict(lang).notAffiliated}
                </p>
              ))}
            </div>
          </div>

          {/*
            The masthead, minus the tagline and the section nav. Both are language-specific,
            and this page has no language to choose; the wordmark points at the site root,
            which is the chooser. The real navigation is the per-language link list below,
            where each route can be named in the language it leads to.
          */}
          <div className="masthead">
            <div className="shell masthead-row">
              <Link href="/" className="wordmark">
                Camino<span> · CA</span>
              </Link>
            </div>
          </div>
        </header>

        <main id="main" className="shell detail">
          {/*
            One heading, said twice, rather than an English `<h1>` with a Spanish `<h2>` under
            it. "404" would be language-neutral and is what the file is called, but it is jargon
            read aloud as a number, and this is the page least able to afford being cryptic.
          */}
          <h1>
            <span lang="en">{dict("en").notFoundTitle}</span>
            {" · "}
            <span lang="es">{dict("es").notFoundTitle}</span>
          </h1>

          <ul className="lang-choice">
            {LANGUAGES.map((lang) => {
              const t = dict(lang);
              return (
                <li key={lang} lang={lang}>
                  <h2>{LANG_NAME[lang]}</h2>
                  <p>{t.notFoundBody}</p>
                  {/*
                    Three real routes, not a single "go home". A broken program URL is most
                    often reached while looking for a provider or a job, and both of those have
                    a complete index a page away.
                  */}
                  <ul>
                    <li>
                      <Link href={`/${lang}/`} hrefLang={lang}>
                        {t.notFoundSearch}
                      </Link>
                    </li>
                    <li>
                      <Link href={`/${lang}/providers/`} hrefLang={lang}>
                        {t.browseAllProviders}
                      </Link>
                    </li>
                    <li>
                      <Link href={`/${lang}/occupations/`} hrefLang={lang}>
                        {t.browseAllOccupations}
                      </Link>
                    </li>
                  </ul>
                </li>
              );
            })}
          </ul>
        </main>
      </body>
    </html>
  );
}
