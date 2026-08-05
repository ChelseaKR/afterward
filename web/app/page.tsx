import Link from "next/link";

import { DEFAULT_LANG, LANGUAGES, LANG_NAME, dict } from "@/lib/i18n";

export const dynamic = "force-static";

export const metadata = {
  title: "Afterward — California training programs and their outcomes",
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
                    <Link href={`/${lang}/`} hrefLang={lang}>
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
