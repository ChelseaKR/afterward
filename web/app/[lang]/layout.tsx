import Link from "next/link";
import { notFound } from "next/navigation";

import { getCoverage } from "@/lib/data";
import { LANGUAGES, LANG_NAME, OTHER_LANG, dict, isLang } from "@/lib/i18n";

export function generateStaticParams() {
  return LANGUAGES.map((lang) => ({ lang }));
}

export default async function LangLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ lang: string }>;
}) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();

  const t = dict(lang);
  const other = OTHER_LANG[lang];
  const coverage = getCoverage();

  return (
    <html lang={lang}>
      <body>
        <a className="skip-link" href="#main">
          {t.skipToContent}
        </a>

        <header>
          {/*
            Sits above the masthead, not in the footer. The site uses California's official
            design system, so it can read as a state website at a glance; saying otherwise
            quietly at the bottom of the page would not be good enough. It lives inside the
            banner landmark so screen reader users reach it in the same place.
          */}
          <div className="disclaimer">
            <div className="shell">{t.notAffiliated}</div>
          </div>

          <div className="masthead">
            <div className="shell masthead-row">
              <div>
                <Link href={`/${lang}/`} className="wordmark">
                  Camino<span> · CA</span>
                </Link>
                <p className="tagline">{t.tagline}</p>
              </div>
              <Link href={`/${other}/`} lang={other} hrefLang={other}>
                {LANG_NAME[other]}
              </Link>
            </div>
          </div>
        </header>

        <main id="main">{children}</main>

        <footer className="footer">
          <div className="shell">
            <p>
              {t.snapshot(coverage.snapshot_date)} · {t.coverageNote(coverage.outcome_coverage_pct)}
            </p>
            <p>
              {t.aboutData}: U.S. Department of Labor (WIOA ETA-9171) ·{" "}
              California Employment Development Department, Long-Term Occupational Employment
              Projections.
            </p>
            <p>{t.notAffiliated}</p>
          </div>
        </footer>
      </body>
    </html>
  );
}
