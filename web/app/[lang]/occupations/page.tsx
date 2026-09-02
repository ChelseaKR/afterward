import Link from "next/link";
import { notFound } from "next/navigation";

import { Measure } from "@/components/Measure";
import { TableFilter } from "@/components/TableFilter";
import {
  type OccupationRow,
  type OutlookBand,
  groupOccupations,
  programCount,
  programCountsBySoc,
  summariseOccupations,
} from "@/lib/browse";
import {
  allOccupationCodes,
  getOccupation,
  getSearchIndex,
  occupationTitleIn,
  occupationTitleLang,
} from "@/lib/data";
import { count, money, signedPercent } from "@/lib/format";
import { LANGUAGES, type Lang, dict, isLang } from "@/lib/i18n";
import { shareMetadata } from "@/lib/site";
import { translateTerm } from "@/lib/vocabulary";

type Dictionary = ReturnType<typeof dict>;

export function generateStaticParams() {
  return LANGUAGES.map((lang) => ({ lang }));
}

export async function generateMetadata({ params }: { params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  if (!isLang(lang)) return {};
  const t = dict(lang);
  return shareMetadata(
    lang,
    `${t.browseOccupationsTitle} | ${t.siteName}`,
    t.browseOccupationsIntro,
  );
}

/** Section heading and standfirst for each outlook band. */
function bandText(band: OutlookBand, t: Dictionary): { heading: string; note: string } {
  switch (band) {
    case "shrinking":
      return { heading: t.bandShrinking, note: t.bandShrinkingNote };
    case "steady":
      return { heading: t.bandSteady, note: t.bandSteadyNote };
    case "growing":
      return { heading: t.bandGrowing, note: t.bandGrowingNote };
    case "unknown":
      return { heading: t.bandUnknown, note: t.bandUnknownNote };
  }
}

/**
 * A withheld or never-published measure, rendered visibly rather than as a blank cell.
 * Every null on this page goes through here, so none of them can become a zero.
 */
function Unreported({ lang }: { lang: Lang }) {
  const t = dict(lang);
  return (
    <span className="unreported" title={t.notReportedLong}>
      {t.notReported}
    </span>
  );
}

/**
 * Browse index for every occupation California projects.
 *
 * Not an alphabetical dump. The state's ten-year projection is the one thing this dataset
 * knows that a course catalog does not, so the page is organized around it: occupations
 * California expects less of come first, then those it expects to hold steady, then those it
 * expects to grow, and within each the ones with the most projected openings lead. An
 * occupation the state left unmeasured gets its own section at the end rather than being
 * quietly filed with the ones projected at zero change.
 */
export default async function OccupationsIndexPage({
  params,
}: {
  params: Promise<{ lang: string }>;
}) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();

  const t = dict(lang);
  const counts = programCountsBySoc(getSearchIndex().programs);

  const rows: OccupationRow[] = [];
  for (const soc of allOccupationCodes()) {
    const occupation = getOccupation(soc);
    if (!occupation) continue;
    rows.push({
      soc,
      title: occupationTitleIn(lang, soc, occupation.title),
      openings: occupation.total_job_openings,
      wage: occupation.median_annual_wage,
      change: occupation.percent_change,
      education: occupation.entry_level_education,
      programs: programCount(counts, soc),
    });
  }

  const bands = groupOccupations(rows);
  const tally = summariseOccupations(rows);

  return (
    <div className="shell browse">
      <p>
        {/* Unprefetched. This sits at the top of every page in the site, and the route it
            points at carries the whole search index, so prefetching it costs 229 KB of a
            reader's data on the chance they press it. Reasoning in app/[lang]/layout.tsx. */}
        <Link href={`/${lang}/`} prefetch={false}>
          ← {t.backToSearch}
        </Link>
      </p>

      <h1>{t.browseOccupationsTitle}</h1>
      <p className="lede">{t.browseOccupationsIntro}</p>
      <p className="lede">{t.titlesEnglishOnly}</p>

      <dl className="measure-grid panel">
        <Measure label={t.occupationsListed} value={count(tally.total, lang)} lang={lang} />
        <Measure label={t.bandShrinking} value={count(tally.shrinking, lang)} lang={lang} />
        <Measure label={t.bandGrowing} value={count(tally.growing, lang)} lang={lang} />
      </dl>

      <h2 id="on-this-page">{t.onThisPage}</h2>
      <nav className="jump-nav" aria-label={t.jumpToOutlook}>
        <ul>
          {bands.map(({ band, rows: banded }) => (
            <li key={band}>
              <a href={`#band-${band}`}>
                {bandText(band, t).heading} ({count(banded.length, lang)})
              </a>
            </li>
          ))}
        </ul>
      </nav>
      <p className="compare-note">{t.sortedByOpenings}</p>

      <TableFilter lang={lang} scope=".browse" />

      {bands.map(({ band, rows: banded }) => {
        const { heading, note } = bandText(band, t);
        return (
          <section key={band}>
            <h2 id={`band-${band}`}>
              {heading} — {count(banded.length, lang)}
            </h2>
            {/*
              The shrinking band gets the same callout treatment as the warning on an
              individual occupation page, so the two say the same thing in the same voice.
            */}
            <p className={band === "shrinking" ? "callout" : "compare-note"}>{note}</p>

            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th scope="col">{t.occupationColumn}</th>
                    <th scope="col" style={{ textAlign: "right" }}>
                      {t.jobOpenings}
                    </th>
                    <th scope="col" style={{ textAlign: "right" }}>
                      {t.medianWage}
                    </th>
                    <th scope="col" style={{ textAlign: "right" }}>
                      {t.growth}
                    </th>
                    <th scope="col">{t.entryEducation}</th>
                    <th scope="col" style={{ textAlign: "right" }}>
                      {t.programsHere}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {banded.map((row) => (
                    <tr key={row.soc}>
                      <th scope="row" style={{ fontWeight: 400 }}>
                        <Link
                          href={`/${lang}/occupations/${row.soc}/`}
                          lang={occupationTitleLang(lang, row.soc)}
                        >
                          {row.title ?? row.soc}
                        </Link>
                      </th>
                      <td className="num">
                        {count(row.openings, lang) ?? <Unreported lang={lang} />}
                      </td>
                      <td className="num">{money(row.wage, lang) ?? <Unreported lang={lang} />}</td>
                      <td className="num">
                        {signedPercent(row.change, lang) ?? <Unreported lang={lang} />}
                      </td>
                      <td>{translateTerm(row.education, lang) ?? <Unreported lang={lang} />}</td>
                      {/*
                        The one honest zero on this page: a count of programs this dataset
                        holds, not a measure anyone could have withheld.
                      */}
                      <td className="num">{count(row.programs, lang)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        );
      })}

      <p className="browse-more">
        <Link href={`/${lang}/providers/`}>{t.browseAllProviders} →</Link>
      </p>
    </div>
  );
}
