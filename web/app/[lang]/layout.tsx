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
 * The two pieces of masthead that depend on which page is being shown: the current-section
 * marking on the nav, and where the language toggle points.
 *
 * Both have to run in the browser, for two reasons that each rule out doing it at build
 * time. A layout is a server component and is never told the path being rendered. More
 * decisively, a layout is rendered once and then *kept* across client-side navigations —
 * only the page segment is re-fetched — so a value baked in at build time would be right
 * on first load and wrong from the first link onwards, which is worse than absent. Both
 * therefore follow the router: `pushState` is what the App Router calls on every client
 * navigation, `popstate` covers back and forward, and `hashchange` covers the jump links on
 * the browse indexes.
 *
 * Inline script rather than making the whole masthead a client component, which would pull
 * the coverage figures and both dictionaries into the bundle to decorate three links.
 *
 * Everything here is an *attribute* mutation. React hydration reconciles element structure
 * and text, not attributes, so setting `href`, `aria-current` and `hidden` on server-rendered
 * markup survives hydration; removing or inserting a node would not.
 *
 * ---- The language toggle ----
 *
 * `/es/programs/<id>/` and `/en/programs/<id>/` differ in exactly one path segment, and the
 * static export generates every route in both languages, so the equivalent URL is always
 * derivable from `location.pathname` and always exists. Swapping the first segment is the
 * whole trick.
 *
 * The fallback matters as much as the rewrite. Without JavaScript the href stays at
 * `/es/` — the other language's home page, which is the only URL this layout can honestly
 * name — and the qualifier rendered beside the language name says so, in that language:
 * "Español (inicio)". The script hides the qualifier at the same moment it makes the link
 * true, so the link never claims to preserve your place and then fails to.
 */
const SYNC_MASTHEAD_TO_LOCATION = `(function () {
  var toggle = document.getElementById("lang-switch");
  var qualifier = document.getElementById("lang-switch-home");
  var from = toggle ? "/" + toggle.getAttribute("data-lang-from") + "/" : "";
  var to = toggle ? "/" + toggle.getAttribute("data-lang-to") : "";

  function markSection(here) {
    document.querySelectorAll(".site-nav a").forEach(function (link) {
      var section = new URL(link.href).pathname;
      if (here === section) link.setAttribute("aria-current", "page");
      else if (here.indexOf(section) === 0) link.setAttribute("aria-current", "true");
      else link.removeAttribute("aria-current");
    });
  }

  function aimToggle(here) {
    if (!toggle || here.slice(0, from.length) !== from) return;
    var rest = here.slice(from.length - 1);
    toggle.setAttribute("href", to + rest + location.search + location.hash);
    if (qualifier) qualifier.setAttribute("hidden", "");
  }

  function sync() {
    var here = location.pathname;
    markSection(here);
    aimToggle(here);
  }

  var push = history.pushState;
  history.pushState = function () {
    push.apply(this, arguments);
    sync();
  };
  addEventListener("popstate", sync);
  addEventListener("hashchange", sync);
  sync();
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
                  Afterward<span> · CA</span>
                </Link>
                <p className="tagline">{t.tagline}</p>
              </div>
              {/*
                Deliberately a plain `<a>` and not a `<Link>`. `Link` navigates to its href
                *prop*, so the script's rewritten DOM attribute would be read by the browser
                and ignored by the router — every click would still land on the language home.
                A full document load is also the honest thing for a language switch: it is
                `<html lang>` and the entire chrome that change, not a page segment.

                `data-lang-from`/`data-lang-to` rather than the script interpolating the
                languages: the script is a constant, identical on all ~9,000 pages, and the
                two facts it needs are already in the markup it operates on.
              */}
              <a
                id="lang-switch"
                href={`/${other}/`}
                lang={other}
                hrefLang={other}
                data-lang-from={lang}
                data-lang-to={other}
              >
                {LANG_NAME[other]}
                {/* Hidden by the script once the href points at this page rather than home. */}
                <span id="lang-switch-home"> ({dict(other).langSwitchHome})</span>
              </a>
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
                <li>
                  {/* Reachable without first finding a program: someone who wants to know
                      whether any of this can be paid for should not have to pick a course
                      before the answer is offered to them. */}
                  <Link href={`/${lang}/paying-for-training/`}>{t.navPaying}</Link>
                </li>
              </ul>
            </nav>

            {/*
              Inline and immediately after the nav, so both the nav links and the language
              toggle exist when it runs — and so the toggle is corrected before first paint
              rather than after it.
            */}
            <script dangerouslySetInnerHTML={{ __html: SYNC_MASTHEAD_TO_LOCATION }} />
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
            {/*
              Required by the O*NET Web Services Data License: any product using the
              Services must credit and link to O*NET. This is owed for the skill ratings,
              descriptions and related occupations the site publishes, which are O*NET
              content. It is not optional decoration — do not remove it while any
              O*NET-derived field is displayed.
            */}
            <p>
              {t.onetCredit}{" "}
              <a href="https://services.onetcenter.org/" rel="noopener noreferrer">
                O*NET Web Services
              </a>
            </p>

            <p>{t.notAffiliated}</p>
          </div>
        </footer>
      </body>
    </html>
  );
}
