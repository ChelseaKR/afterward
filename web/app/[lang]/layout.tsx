import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { getCoverage } from "@/lib/data";
import { LANGUAGES, LANG_NAME, OTHER_LANG, dict, isLang } from "@/lib/i18n";
import { shareMetadata } from "@/lib/site";

export function generateStaticParams() {
  return LANGUAGES.map((lang) => ({ lang }));
}

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
 *
 * `openGraph.images` IS declared here, and the distinction is the point of the paragraph
 * above rather than an exception to it. What made a canonical URL unsafe to inherit is that
 * it is a claim about *which page this is*, so it is wrong on every page that inherits it.
 * The card is a claim about which site this is, and it is equally true on all of them: a
 * shared program page gets the site's card, which is the right answer and was previously no
 * card at all. Per language, for the same reason the description is.
 *
 * The tags themselves are now built by `shareMetadata` in `lib/site.ts`, which every page
 * under this layout also calls with its own title and description. What was inherited from
 * here is the *shape* of the card rather than its words -- and only because Next replaces a
 * child's `openGraph` wholesale rather than merging it, so a page cannot add the two fields
 * it was missing without restating the six it was not. One function, so restating them is
 * not something anyone has to remember to do correctly nine times.
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ lang: string }>;
}): Promise<Metadata> {
  const { lang } = await params;
  if (!isLang(lang)) return {};

  const t = dict(lang);

  // `summary_large_image`, chosen inside `shareMetadata`. This read `summary` because the
  // large variant renders as an empty banner above the text when no image is supplied; with
  // a card to show, the reason for the small variant is gone and the large one is what the
  // 1200x630 card is cut for.
  return shareMetadata(
    lang,
    `${t.siteName} — ${t.tagline}`,
    `${t.notAffiliated} ${t.siteSummary}`,
  );
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
                {/*
                  `prefetch={false}` here and on the three nav links below, and it is the
                  single largest thing this site does to a phone. See the block comment above
                  `CHROME_ROUTES` in scripts/size-report.mjs for the measurements.

                  Next prefetches a `<Link>` when it scrolls into view. These four are in the
                  masthead of all ~9,000 pages, so they are in view immediately on every one
                  of them, and they happen to point at four of the five heaviest routes the
                  site has. Measured in Chromium against the built export, a visitor landing
                  on `/en/about/` — a page whose own document is 7.7 KB compressed — pulled
                  551 KB, of which 401 KB was these four routes being fetched in the
                  background: their documents, their RSC segment payloads, and their JS.
                  `npm run transfer` reproduces the measurement.

                  The wordmark is the worst of them on its own. It points at the search page,
                  whose document carries the whole 3,266-program index inline, so it costs
                  229 KB to prefetch — and on the search page itself the wordmark points at
                  the page already open, so that 229 KB is spent fetching a second copy of an
                  index the browser has already parsed.

                  None of it is a click anyone made. This site is for people deciding whether
                  to spend a year and several thousand dollars on training, a fair number of
                  whom arrive on a phone, on a metered connection, or on library wifi;
                  spending their data speculatively on the chance they might press "home" is
                  not a trade we get to make for them. A prefetch is a guess, and the cost of
                  guessing wrong here is measured in megabytes per session.

                  Deliberately not `prefetch={false}` everywhere. Search result cards still
                  prefetch, because someone reading a list of programs is being shown exactly
                  the thing they came to open, and those pages are ~8 KB each rather than 229.
                */}
                <Link href={`/${lang}/`} className="wordmark" prefetch={false}>
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
                {/* All three unprefetched, for the reason set out on the wordmark above:
                    they are in the viewport on every page in the site, and the two browse
                    indexes are 65 KB and 55 KB to fetch. */}
                <li>
                  <Link href={`/${lang}/occupations/`} prefetch={false}>
                    {t.navOccupations}
                  </Link>
                </li>
                <li>
                  <Link href={`/${lang}/providers/`} prefetch={false}>
                    {t.navProviders}
                  </Link>
                </li>
                <li>
                  {/* Reachable without first finding a program: someone who wants to know
                      whether any of this can be paid for should not have to pick a course
                      before the answer is offered to them. */}
                  <Link href={`/${lang}/paying-for-training/`} prefetch={false}>
                    {t.navPaying}
                  </Link>
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
              {t.snapshot(coverage.snapshot_date)} · {t.coverageNote(coverage.outcome_coverage_pct)}{" "}
              {/*
                The footer states a coverage figure on every page in the site and, until now,
                offered nowhere to go and read what it is made of. The page it points at is
                meant to be cited by people who work on this data, and the footer is the one
                place every visitor already meets the number it explains.

                `prefetch={false}` for the reason set out on the masthead links above: this is
                in the document of all ~9,000 pages, so a prefetch here is a route fetched on
                every visit for the small share of readers who press it.
              */}
              <Link href={`/${lang}/outcomes-coverage/`} prefetch={false}>
                {t.coverageNavShort}
              </Link>
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
