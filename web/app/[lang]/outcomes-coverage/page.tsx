import Link from "next/link";
import { notFound } from "next/navigation";

import { Measure } from "@/components/Measure";
import { allProgramIds, getCoverage, getProgram } from "@/lib/data";
import {
  HEADLINE_MEASURES,
  MIN_RATE_DENOMINATOR,
  UNSTATED_ENTITY_TYPE,
  etplCoverageReport,
  mostlySilentCategories,
  type EtplCoverageReport,
  type MeasureKey,
} from "@/lib/etplCoverage";
import { count, percent } from "@/lib/format";
import {
  LANGUAGES,
  type Copy,
  type Lang,
  dict,
  entityTypeLabel,
  feedTextLang,
  isLang,
} from "@/lib/i18n";
import type { Program } from "@/lib/types";

export function generateStaticParams() {
  return LANGUAGES.map((lang) => ({ lang }));
}

export async function generateMetadata({ params }: { params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  if (!isLang(lang)) return {};
  const t = dict(lang);
  return { title: `${t.coverageTitle} | ${t.siteName}`, description: t.coverageLede };
}

/** Where a reader can check the sources, and where someone can say this got something wrong. */
const REPO = "https://github.com/ChelseaKR/afterward";
const PROVENANCE_URL = `${REPO}/blob/main/PROVENANCE.md`;
const ISSUES_URL = `${REPO}/issues`;

/**
 * The regulation and guidance the "different obligations" section rests on.
 *
 * Published as links rather than paraphrased into the prose, because that section is the one
 * part of this page that is not visible in the data and therefore the one part a reader has
 * to be able to check for themselves. Each is the primary text, not a summary of it.
 */
const OBLIGATION_CITATIONS: { id: string; label: string; url: string }[] = [
  {
    id: "apprenticeship-performance",
    label:
      "20 CFR 677.230(b): registered apprenticeship programs are not required to submit ETP " +
      "performance information, and (e)(1): the State facilitates the wage-record match",
    url: "https://www.ecfr.gov/current/title-20/section-677.230",
  },
  {
    id: "initial-eligibility",
    label: "20 CFR 680.450(b): apprenticeship programs are exempt from initial eligibility",
    url: "https://www.ecfr.gov/current/title-20/section-680.450",
  },
  {
    id: "performance-information",
    label:
      "20 CFR 680.490: what providers other than registered apprenticeship programs must provide",
    url: "https://www.ecfr.gov/current/title-20/section-680.490",
  },
  {
    id: "wioa-116-d-4",
    label: "WIOA sec. 116(d)(4), 29 U.S.C. 3141(d)(4): all individuals engaging in the program",
    url: "https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title29-section3141",
  },
  {
    id: "california-directive",
    label:
      "California EDD Workforce Services Directive WSD25-02: California Eligible Training " +
      "Provider List",
    url: "https://edd.ca.gov/siteassets/files/jobs_and_training/pubs/wsd25-02.docx",
  },
];

/**
 * The reporting period the scorecard covers, and the date that sentence was read.
 *
 * The one fact on this page that is not counted from the data, because it cannot be: no
 * record on either of the scorecard's indexes carries a program-year or reporting-period
 * field, and its machine-readable bulk file has no such column either. The window is stated
 * only in prose on the scorecard's own About page, and the data dictionary published beside
 * the same data still names an earlier program year, so the source does not agree with
 * itself.
 *
 * It is therefore quoted with the date it was read, beside every block of figures. A refresh
 * upstream can move this window with nothing here noticing, and an undated coverage figure
 * invites a correction from somebody who knows the scorecard lags. Recorded in PROVENANCE.md;
 * update both together.
 */
const SCORECARD_PERIOD = {
  firstProgramYear: "2021",
  lastProgramYear: "2024",
  statedOn: "2026-08-07",
} as const;

/**
 * A count of records, formatted for prose.
 *
 * Same helper and the same reasoning as the methodology page: everything passed here is the
 * size of a set this build just walked, so it is a number that is always present. `count()`
 * returns null for a measure nobody reported, which is a state none of these can be in, and
 * collapsing the two would be the beginning of treating a suppressed figure as a zero.
 */
function tally(value: number, lang: Lang): string {
  return count(value, lang) ?? String(value);
}

/**
 * A share, or the site's explicit "not reported" treatment when it was withheld.
 *
 * A withheld share is withheld because the denominator was too small to carry one, not
 * because it is zero, so it renders like every other absent figure on this site rather than
 * as "0%" or a dash.
 */
function Share({ value, lang }: { value: number | null; lang: Lang }) {
  const t = dict(lang);
  const formatted = percent(value, lang);
  if (formatted === null) {
    return (
      <span className="unreported" title={t.notReportedLong}>
        {t.notReported}
      </span>
    );
  }
  return <>{formatted}</>;
}

const MEASURE_LABELS: Record<MeasureKey, keyof Copy> = {
  total_served: "coverageMeasureTotalServed",
  total_exited: "coverageMeasureTotalExited",
  total_completed: "coverageMeasureTotalCompleted",
  completion_rate: "coverageMeasureCompletionRate",
  credentials_earned: "coverageMeasureCredentials",
  employed_q2: "coverageMeasureEmployedQ2",
  employment_rate_q2: "coverageMeasureEmploymentRate",
  employed_q4: "coverageMeasureEmployedQ4",
  median_earnings: "coverageMeasureEarnings",
};

function measureLabel(t: Copy, key: MeasureKey): string {
  return t[MEASURE_LABELS[key]] as string;
}

/**
 * A provider category as prose, for a sentence rather than a table cell.
 *
 * Same lookup the table uses, so the sentence naming the two categories with the most empty
 * rows cannot name them differently from the rows it is about. An untranslated fallback is
 * accepted here without a `lang` marking: it sits inside a translated sentence, where
 * breaking the flow to mark two words costs a reader more than it gains them.
 */
function categoryName(t: Copy, lang: Lang, filed: string): string {
  if (filed === UNSTATED_ENTITY_TYPE) return t.coverageEntityUnstated;
  return entityTypeLabel(lang, filed).text;
}

/**
 * Every program record, walked once, and the counts that fall out of it.
 *
 * Memoised at module scope so the English and Spanish pages share a single pass, exactly as
 * `corpusFacts` does on the methodology page. The cost is roughly 3,300 file reads, which is
 * negligible beside an export that renders about nine thousand pages out of the same
 * directory, and it is the only way to reach `entity_type` and the cohort counts: the search
 * index carries neither.
 */
let cachedReport: EtplCoverageReport | null = null;

function corpusReport(): EtplCoverageReport {
  if (cachedReport !== null) return cachedReport;

  const programs: Program[] = [];
  for (const id of allProgramIds()) {
    const program = getProgram(id);
    if (program !== null) programs.push(program);
  }

  cachedReport = etplCoverageReport(programs);
  return cachedReport;
}

/**
 * How much of California's training outcomes data is published, and where the gaps sit.
 *
 * California's Eligible Training Provider List is published as a CalJOBS search screen and
 * nothing else. There is no export, so there is no public count of how many of the state's
 * listed programs carry evidence of what happened to the people who took them. The federal
 * ETP Scorecard holds the same programs, this project already ingests it, and counting it is
 * therefore the only way that number can currently be produced by anybody.
 *
 * That makes the page useful and also makes it dangerous, in a specific way. A table of who
 * publishes least, sorted, on a site that already names hundreds of real California
 * organisations, would read as an accusation whatever the surrounding prose said. Three
 * things hold it to being a measurement instead:
 *
 * 1. Every figure is a count over the dataset taken at build time. Nothing is typed into the
 *    copy, so the page cannot drift into sounding precise about something that has changed.
 * 2. Provider categories are ordered by size, never by how much they leave blank, and the
 *    reporting obligations that legitimately differ between them are stated beside the table
 *    rather than in a footnote below it.
 * 3. Nothing is rendered as a zero that was not measured as one, and no share is published
 *    over a denominator too small to carry it.
 */
export default async function OutcomesCoveragePage({
  params,
}: {
  params: Promise<{ lang: string }>;
}) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();

  const t = dict(lang);
  const snapshot = getCoverage().snapshot_date;
  const report = corpusReport();
  const { headline, measures, routes, byEntityType, byCohortSize, providers } = report;
  // The two categories leaving the most rows empty. Destructured rather than indexed so the
  // sentence about a pair is rendered only when there is a pair: a dataset holding one
  // rankable category must not produce half a comparison.
  const [firstSilent, secondSilent] = mostlySilentCategories(byEntityType, 2);

  /** Program-year window and read date, beside every block of figures rather than stated once. */
  const stamp = (
    <p className="compare-note">
      {t.coverageStamp(
        SCORECARD_PERIOD.firstProgramYear,
        SCORECARD_PERIOD.lastProgramYear,
        snapshot,
      )}
    </p>
  );

  const sections: { id: string; label: string }[] = [
    { id: "measures", label: t.coverageMeasuresHeading },
    { id: "provider-type", label: t.coverageByTypeHeading },
    { id: "obligations", label: t.coverageObligationsHeading },
    { id: "cohort-size", label: t.coverageCohortHeading },
    { id: "providers", label: t.coverageProvidersHeading },
    { id: "method", label: t.coverageMethodHeading },
    { id: "cite", label: t.coverageCiteHeading },
  ];

  return (
    <div className="shell detail about">
      <p>
        {/* Unprefetched, like every other link back to search: that route carries the whole
            index. Reasoning in app/[lang]/layout.tsx. */}
        <Link href={`/${lang}/`} prefetch={false}>
          ← {t.backToSearch}
        </Link>
      </p>

      <h1>{t.coverageTitle}</h1>
      <p className="lede">{t.coverageLede}</p>
      <p>{t.coverageWhy}</p>
      <p>{t.coverageFraming}</p>

      <dl className="measure-grid panel">
        <Measure
          label={t.coverageProgramsCounted}
          value={tally(headline.programs, lang)}
          lang={lang}
        />
        <Measure
          label={t.coverageSilentLabel}
          value={t.reportingRatio(headline.silent, headline.programs)}
          lang={lang}
        />
        <Measure
          label={t.coverageSilentNoRecordLabel}
          value={t.reportingRatio(headline.silentWithNoRecord, headline.silent)}
          lang={lang}
        />
      </dl>
      {stamp}

      <p>
        {t.coverageHeadlineBody(
          tally(headline.silent, lang),
          tally(headline.programs, lang),
          tally(headline.silentWithACohort, lang),
          tally(headline.silentWithNoRecord, lang),
        )}
      </p>
      <p>{t.coverageHeadlineSecond}</p>
      <p className="compare-note">{t.coverageStampNote(SCORECARD_PERIOD.statedOn)}</p>

      <h2 id="on-this-page">{t.onThisPage}</h2>
      <nav className="jump-nav" aria-label={t.coverageJumpLabel}>
        <ul>
          {sections.map((section) => (
            <li key={section.id}>
              <a href={`#${section.id}`}>{section.label}</a>
            </li>
          ))}
        </ul>
      </nav>

      <h2 id="measures">{t.coverageMeasuresHeading}</h2>
      <p>{t.coverageMeasuresIntro}</p>

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">{t.coverageMeasureColumn}</th>
              <th scope="col" style={{ textAlign: "right" }}>
                {t.coverageReportedColumn}
              </th>
              <th scope="col" style={{ textAlign: "right" }}>
                {t.coverageBlankColumn}
              </th>
              <th scope="col" style={{ textAlign: "right" }}>
                {t.coverageUnfiledColumn}
              </th>
              <th scope="col" style={{ textAlign: "right" }}>
                {t.coverageMissingColumn}
              </th>
            </tr>
          </thead>
          <tbody>
            {measures.map((measure) => (
              <tr key={measure.key}>
                <th scope="row" style={{ fontWeight: 400 }}>
                  {measureLabel(t, measure.key)}
                </th>
                {/* Counts, not measures: every program is present and each is in exactly one
                    of the three states, so a zero in any of these columns is a real zero. */}
                <td className="num">{tally(measure.reported, lang)}</td>
                <td className="num">{tally(measure.blank, lang)}</td>
                <td className="num">{tally(measure.unfiled, lang)}</td>
                <td className="num">
                  {t.reportingRatio(measure.blank + measure.unfiled, measure.programs)}{" "}
                  (<Share value={measure.missingShare} lang={lang} />)
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {stamp}
      <p>{t.coverageMeasureNote}</p>
      {/*
        Rendered only while the two groups genuinely do not overlap. If a refresh softens the
        pattern the sentence disappears rather than staying on a page whose entire subject is
        figures quietly going stale.
      */}
      {routes.separated && routes.providerFloor !== null && routes.wageMatchCeiling !== null ? (
        <>
          <p>
            {t.coverageRouteSplit(
              measureLabel(t, routes.providerFloor.key),
              tally(routes.providerFloor.reported, lang),
              measureLabel(t, routes.wageMatchCeiling.key),
              tally(routes.wageMatchCeiling.reported, lang),
            )}
          </p>
          <p>{t.coverageRouteSplitCaveat}</p>
        </>
      ) : null}

      <h2 id="provider-type">{t.coverageByTypeHeading}</h2>
      <p>{t.coverageByTypeIntro}</p>

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">{t.coverageCategoryColumn}</th>
              <th scope="col" style={{ textAlign: "right" }}>
                {t.coverageProgramsColumn}
              </th>
              <th scope="col" style={{ textAlign: "right" }}>
                {t.coveragePublishSomeColumn}
              </th>
              <th scope="col" style={{ textAlign: "right" }}>
                {t.coveragePublishNoneColumn}
              </th>
              <th scope="col" style={{ textAlign: "right" }}>
                {t.coverageShareNoneColumn}
              </th>
            </tr>
          </thead>
          <tbody>
            {byEntityType.map((row) => {
              const unstated = row.entityType === UNSTATED_ENTITY_TYPE;
              const label = entityTypeLabel(lang, row.entityType);
              return (
                <tr key={row.entityType}>
                  <th scope="row" style={{ fontWeight: 400 }}>
                    {/* The category is the filer's own English classification. Where this
                        project publishes a Spanish name for one it is used; where it does
                        not, the filed English is marked as English so a screen reader does
                        not read it with Spanish phonetics. */}
                    {unstated ? (
                      t.coverageEntityUnstated
                    ) : (
                      <span lang={label.translated ? undefined : feedTextLang(lang)}>
                        {label.text}
                      </span>
                    )}
                  </th>
                  <td className="num">{tally(row.programs, lang)}</td>
                  <td className="num">{tally(row.reporting, lang)}</td>
                  <td className="num">{tally(row.silent, lang)}</td>
                  <td className="num">
                    <Share value={row.silentShare} lang={lang} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {stamp}
      <p>{t.coverageByTypeCaveat}</p>

      <h2 id="obligations">{t.coverageObligationsHeading}</h2>
      <p>{t.coverageObligationsIntro}</p>
      <ul className="limits">
        <li>{t.coverageObligationRegisteredApprenticeship}</li>
        <li>{t.coverageObligationCalifornia}</li>
        <li>{t.coverageObligationAllStudents}</li>
        <li>{t.coverageObligationSuppression}</li>
      </ul>
      {firstSilent !== undefined && secondSilent !== undefined ? (
        <p>
          {t.coverageObligationsClosing(
            categoryName(t, lang, firstSilent.entityType),
            categoryName(t, lang, secondSilent.entityType),
          )}
        </p>
      ) : null}
      <p className="compare-note">{t.coverageCitationsNote}</p>
      <ul className="limits">
        {OBLIGATION_CITATIONS.map((citation) => (
          <li key={citation.id}>
            {/* Federal legal texts, published in English only. Marked as English on the
                Spanish page for the same reason every other English-only string is. */}
            <a href={citation.url} rel="noopener noreferrer" lang={feedTextLang(lang)}>
              {citation.label}
            </a>
          </li>
        ))}
      </ul>

      <h2 id="cohort-size">{t.coverageCohortHeading}</h2>
      <p>{t.coverageCohortIntro}</p>

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">{t.coverageCohortColumn}</th>
              <th scope="col" style={{ textAlign: "right" }}>
                {t.coverageProgramsColumn}
              </th>
              {HEADLINE_MEASURES.map((key) => (
                <th key={key} scope="col" style={{ textAlign: "right" }}>
                  {measureLabel(t, key)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {byCohortSize.map((band) => (
              <tr key={`${band.lower}`}>
                <th scope="row" style={{ fontWeight: 400 }}>
                  {band.upper === null
                    ? t.coverageCohortAtLeast(tally(band.lower, lang))
                    : t.coverageCohortRange(tally(band.lower, lang), tally(band.upper, lang))}
                </th>
                <td className="num">{tally(band.programs, lang)}</td>
                {HEADLINE_MEASURES.map((key) => (
                  <td className="num" key={key}>
                    {t.coverageCohortOf(
                      tally(band.missingCount[key], lang),
                      tally(band.programs, lang),
                    )}{" "}
                    (<Share value={band.missingShare[key]} lang={lang} />)
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {stamp}
      <p>{t.coverageCohortReading}</p>
      <p>{t.coverageCohortCaveat}</p>

      <h2 id="providers">{t.coverageProvidersHeading}</h2>
      <p>
        {t.coverageProvidersBody(
          tally(providers.silentProviders, lang),
          tally(providers.providers, lang),
          tally(providers.programsAtSilentProviders, lang),
        )}
      </p>
      {stamp}
      <p className="browse-more">
        <Link href={`/${lang}/providers/`} prefetch={false}>
          {t.browseAllProviders} →
        </Link>
      </p>

      <h2 id="method">{t.coverageMethodHeading}</h2>
      <p>{t.coverageMethodSource}</p>

      <h3>{t.coverageMethodBlankHeading}</h3>
      <p>{t.coverageMethodBlank}</p>
      <p>{t.coverageMethodStates}</p>
      <p>{t.coverageMethodThreshold}</p>

      <h3>{t.coverageMethodZeroHeading}</h3>
      <p>{t.coverageMethodZero}</p>

      <h3>{t.coverageMethodFloorHeading}</h3>
      <p>{t.coverageMethodFloor(tally(MIN_RATE_DENOMINATOR, lang))}</p>

      <h3>{t.coverageMethodLimitsHeading}</h3>
      <p>{t.coverageMethodLimits}</p>
      <p>{t.coverageMethodRebuild}</p>
      <p>
        <a href={PROVENANCE_URL} rel="noopener noreferrer">
          {t.aboutProvenanceLink} →
        </a>
      </p>

      <h2 id="cite">{t.coverageCiteHeading}</h2>
      <p>{t.coverageCiteBody(snapshot)}</p>
      <p>{t.coverageCiteCorrections}</p>
      <p>
        <a href={ISSUES_URL} rel="noopener noreferrer">
          {t.aboutCorrectionsLink} →
        </a>
      </p>

      <p className="browse-more">
        <Link href={`/${lang}/about/`} prefetch={false}>
          {t.methodologyLink} →
        </Link>
      </p>
    </div>
  );
}
