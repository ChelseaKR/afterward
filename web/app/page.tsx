import Link from "next/link";

import { DEFAULT_LANG, LANGUAGES, LANG_NAME, dict } from "@/lib/i18n";

export const dynamic = "force-static";

export const metadata = {
  title: "Camino — California training programs and their outcomes",
};

/**
 * Language chooser at the site root.
 *
 * This was previously `redirect()`, which under `output: "export"` does not produce a
 * redirect at all: Next emits an error shell with an empty body and no `lang` attribute.
 * Visitors without JavaScript got a blank page at the most-linked URL in the site, and
 * everyone else got a blank flash. A real page with a real `<meta http-equiv="refresh">`
 * works without JavaScript, and the visible links work even if the refresh is blocked.
 */
export default function Index() {
  const t = dict(DEFAULT_LANG);
  return (
    <html lang={DEFAULT_LANG}>
      <head>
        <meta httpEquiv="refresh" content={`0; url=/${DEFAULT_LANG}/`} />
        <link rel="canonical" href={`/${DEFAULT_LANG}/`} />
      </head>
      <body>
        <main className="shell detail">
          <h1>{t.siteName}</h1>
          <p>{t.tagline}</p>
          <ul>
            {LANGUAGES.map((lang) => (
              <li key={lang}>
                <Link href={`/${lang}/`} lang={lang} hrefLang={lang}>
                  {LANG_NAME[lang]}
                </Link>
              </li>
            ))}
          </ul>
          <p>{t.notAffiliated}</p>
        </main>
      </body>
    </html>
  );
}
