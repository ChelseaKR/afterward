import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { getCoverage } from "@/lib/data";
import { LANGUAGES, LANG_NAME, OTHER_LANG, dict, isLang } from "@/lib/i18n";

export function generateStaticParams() {
  return LANGUAGES.map((lang) => ({ lang }));
}

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL?.replace(/\/$/, "") ?? "";

/**
 * Metadata for the preview card a shared link produces.
 *
 * Without this a link posted anywhere renders as a bare URL, which for this site is worse
 * than merely plain: the pages are built with California's official design system, and a
 * preview with no context is a preview with no room to say this is not a state website. The
 * description therefore leads with the non-affiliation notice rather than the tagline.
 *
 * Per-language, because the notice is only useful in a language its reader speaks. Built
 * from the existing dictionary, so there is nothing here to translate separately and
 * nothing that can drift out of step with the page it describes.
 *
 * Deliberately NO `alternates` and no `openGraph.url` here. Next merges layout metadata into
 * every descendant that does not override the same key, and a page-level `generateMetadata`
 * that sets only title and description inherits the rest — so a canonical of `/en/` declared
 * once here became a canonical of `/en/` on all ~9,000 pages, telling search engines that
 * every program, provider and occupation page is a duplicate of the home page. For a site
 * whose whole purpose is being findable when someone searches a provider's name, that is the
 * most expensive line of code it could contain. A per-URL canonical belongs in each page's
 * own metadata or nowhere; absent, engines self-canonicalise, which is correct here.
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ lang: string }>;
}): Promise<Metadata> {
  const { lang } = await params;
  if (!isLang(lang)) return {};

  const t = dict(lang);
  const title = `${t.siteName} — ${t.tagline}`;
  const description = `${t.notAffiliated} ${t.siteSummary}`;

  return {
    title,
    description,
    openGraph: {
      type: "website",
      siteName: t.siteName,
      locale: lang === "es" ? "es_US" : "en_US",
      title,
      description,
    },
    // Summary rather than a large image card: there is no image, and the large variant
    // renders as an empty banner above the text when none is supplied.
    twitter: { card: "summary", title, description },
  };
}

/**
 * Marks the section link for wherever the visitor currently is.
 *
 * This has to run in the browser, for two reasons that both rule out doing it at build
 * time. A layout is a server component and is never told the path being rendered. More
 * decisively, a layout is rendered once and then *kept* across client-side navigations —
 * only the page segment is re-fetched — so a value baked in at build time would be right
 * on first load and wrong from the first link onwards, which is worse than absent. The
 * marking therefore follows the router: `pushState` is what the App Router calls on every
 * client navigation, and `popstate` covers back and forward.
 *
 * Ten lines of inline script rather than making the whole masthead a client component,
 * which would pull the coverage figures and both dictionaries into the bundle to decorate
 * two links. Without JavaScript the nav still works and still reads correctly; what is lost
 * is the announcement of which section you are already in, not the ability to get there.
 */
const MARK_CURRENT_SECTION = `(function () {
  function mark() {
    var here = location.pathname;
    document.querySelectorAll(".site-nav a").forEach(function (link) {
      var section = new URL(link.href).pathname;
      if (here === section) link.setAttribute("aria-current", "page");
      else if (here.indexOf(section) === 0) link.setAttribute("aria-current", "true");
      else link.removeAttribute("aria-current");
    });
  }
  var push = history.pushState;
  history.pushState = function () {
    push.apply(this, arguments);
    mark();
  };
  addEventListener("popstate", mark);
  mark();
})();`;

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

            {/*
              The two browse indexes were reachable only by typing the URL. They are the
              site's other two ways in — by the job you want or by the school you were
              about to enrol in — so they belong in the chrome rather than in a link at the
              bottom of one page. Their own row under the wordmark: dropping them into the
              masthead row would either crowd the tagline or push the language toggle off a
              narrow screen, and the language toggle is not something to make harder to find.
            */}
            <nav className="shell site-nav" aria-label={t.navLabel}>
              <ul>
                <li>
                  <Link href={`/${lang}/occupations/`}>{t.navOccupations}</Link>
                </li>
                <li>
                  <Link href={`/${lang}/providers/`}>{t.navProviders}</Link>
                </li>
              </ul>
            </nav>

            {/* Inline and immediately after the nav, so the links exist when it runs. */}
            <script dangerouslySetInnerHTML={{ __html: MARK_CURRENT_SECTION }} />
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
