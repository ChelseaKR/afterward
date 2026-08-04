import Link from "next/link";
import { notFound } from "next/navigation";

import { Measure } from "@/components/Measure";
import { allProgramIds, getCoverage, getProgram } from "@/lib/data";
import { count } from "@/lib/format";
import { LANGUAGES, dict, isLang, type Lang } from "@/lib/i18n";

export function generateStaticParams() {
  return LANGUAGES.map((lang) => ({ lang }));
}

export async function generateMetadata({ params }: { params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  if (!isLang(lang)) return {};
  const t = dict(lang);
  return { title: `${t.aboutTitle} | ${t.siteName}`, description: t.aboutLede };
}

/** Where a reader can read the sources for themselves, and where a provider can object. */
const REPO = "https://github.com/ChelseaKR/camino";
const PROVENANCE_URL = `${REPO}/blob/main/PROVENANCE.md`;
const ISSUES_URL = `${REPO}/issues`;

/**
 * A count of records, formatted for prose.
 *
 * Separate from `count()` on purpose. Everything passed here is the size of a set this build
 * just walked — how many programs exist, how many carry a link — so it is a number that is
 * always present. `count()` returns null for a *measure* nobody reported, which is a state
 * none of these can be in, and collapsing the two would be the beginning of treating a
 * suppressed figure as a countable zero.
 */
function tally(value: number, lang: Lang): string {
  return count(value, lang) ?? String(value);
}

/**
 * Facts about the corpus that only a pass over every program record can answer.
 *
 * `coverage.json` carries the headline figures, but not these three, and this page states
 * limitations by number rather than by adjective — "1,430 programs have no working link" is
 * something a reader can check and a maintainer must keep true, where "some programs" is
 * neither. Deriving them at build time rather than typing them into the copy means the two
 * cannot drift apart, and means a quarterly refresh corrects this page for free.
 *
 * The cost is ~3,300 file reads. Memoised at module scope so the English and Spanish pages
 * share one pass, and negligible beside an export that already renders roughly nine thousand
 * pages from the same directory.
 */
interface CorpusFacts {
  /** Programs where at least one occupation's figures belong to a wider published group. */
  aggregateMatched: number;
  /** Programs whose city is not one of the areas EDD names, so no regional figure is shown. */
  withoutArea: number;
  /** Programs that filed no usable website address. */
  withoutUrl: number;
}

let cachedFacts: CorpusFacts | null = null;

function corpusFacts(): CorpusFacts {
  if (cachedFacts !== null) return cachedFacts;

  let aggregateMatched = 0;
  let withoutArea = 0;
  let withoutUrl = 0;

  for (const id of allProgramIds()) {
    const program = getProgram(id);
    if (program === null) continue;
    if (program.occupations.some((occupation) => occupation.match.kind !== "exact")) {
      aggregateMatched += 1;
    }
    if (program.region === null) withoutArea += 1;
    if (program.program_url === null) withoutUrl += 1;
  }

  cachedFacts = { aggregateMatched, withoutArea, withoutUrl };
  return cachedFacts;
}

/**
 * The methodology page.
 *
 * This site publishes outcome figures about several hundred named California organisations,
 * in public, and puts them side by side in a way that reads as a verdict whether or not one
 * is intended. A page like this is the price of doing that. It is written as prose because a
 * bulleted list of caveats is a way of publishing a disclosure without anyone reading it, and
 * the people it is most owed to — a small provider that finds itself described as "worse than
 * typical" on the strength of one self-reported number — deserve to be able to read, in a few
 * minutes, exactly what was claimed about them, on whose authority, and how to contest it.
 *
 * Every number in the copy comes from the build rather than from the writing, so the page
 * cannot quietly go stale while continuing to sound precise.
 */
export default async function AboutPage({ params }: { params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();

  const t = dict(lang);
  const coverage = getCoverage();
  const facts = corpusFacts();
  // Programs with no occupation panel at all: matched is a subset of total, so this is a
  // difference between two counted sets rather than a measure that could be missing.
  const unmatched = coverage.total_programs - coverage.programs_matched_to_occupation;

  return (
    <div className="shell detail about">
      <p>
        <Link href={`/${lang}/`}>← {t.backToSearch}</Link>
      </p>

      <h1>{t.aboutTitle}</h1>
      <p className="lede">{t.aboutLede}</p>
      <p>{t.aboutIndependence}</p>

      <dl className="measure-grid panel">
        <Measure
          label={t.aboutProgramsCounted}
          value={tally(coverage.total_programs, lang)}
          lang={lang}
        />
        <Measure
          label={t.aboutProvidersNamed}
          value={tally(coverage.distinct_providers, lang)}
          lang={lang}
        />
        <Measure
          label={t.aboutProgramsReporting}
          value={t.reportingRatio(coverage.programs_with_any_outcome, coverage.total_programs)}
          lang={lang}
        />
      </dl>
      <p className="compare-note">{t.snapshot(coverage.snapshot_date)}</p>

      <h2>{t.aboutSourcesHeading}</h2>
      <p>{t.aboutSourcesBody}</p>

      <dl className="source-list">
        <dt>{t.aboutSourceProgramsLabel}</dt>
        <dd>{t.aboutSourceProgramsBody}</dd>
        <dt>{t.aboutSourceOccupationsLabel}</dt>
        <dd>{t.aboutSourceOccupationsBody}</dd>
        <dt>{t.aboutSourceFederalLabel}</dt>
        <dd>{t.aboutSourceFederalBody}</dd>
      </dl>

      <p>{t.aboutSourcesDates}</p>
      <p>
        <a href={PROVENANCE_URL} rel="noopener noreferrer">
          {t.aboutProvenanceLink} →
        </a>
      </p>

      <h2>{t.aboutSelfReportedHeading}</h2>
      <p>{t.aboutSelfReportedBody}</p>
      <p>{t.aboutSelfReportedSecond}</p>

      <h2>{t.aboutMissingHeading}</h2>
      <p>{t.aboutMissingBody}</p>
      <p>
        {t.aboutMissingSecond(
          tally(coverage.programs_with_any_outcome, lang),
          tally(coverage.total_programs, lang),
        )}
      </p>

      <h2>{t.aboutQuarterHeading}</h2>
      <p>{t.aboutQuarterBody}</p>

      <h2>{t.aboutComparisonsHeading}</h2>
      <p>{t.aboutComparisonsBody}</p>
      <p>{t.aboutComparisonsSecond}</p>
      <p>{t.aboutComparisonsThird}</p>

      <h2>{t.aboutAggregateHeading}</h2>
      <p>{t.aboutAggregateBody(tally(facts.aggregateMatched, lang))}</p>
      <p>{t.aboutAggregateSecond}</p>

      <h2>{t.aboutLimitsHeading}</h2>
      <p>{t.aboutLimitsBody}</p>
      <ul className="limits">
        <li>{t.aboutLimitTranslation}</li>
        <li>{t.aboutLimitEtpl}</li>
        <li>{t.aboutLimitUnmatched(tally(unmatched, lang))}</li>
        <li>{t.aboutLimitArea(tally(facts.withoutArea, lang))}</li>
        <li>{t.aboutLimitUrl(tally(facts.withoutUrl, lang))}</li>
        <li>{t.aboutLimitProjections}</li>
        <li>{t.aboutLimitSnapshot(coverage.snapshot_date)}</li>
      </ul>

      <h2>{t.aboutCorrectionsHeading}</h2>
      <p>{t.aboutCorrectionsBody}</p>
      <p>{t.aboutCorrectionsSecond}</p>
      <p>
        <a href={ISSUES_URL} rel="noopener noreferrer">
          {t.aboutCorrectionsLink} →
        </a>
      </p>

      <h2>{t.aboutAdviceHeading}</h2>
      <p>{t.aboutAdviceBody}</p>

      <p className="browse-more">
        <Link href={`/${lang}/occupations/`}>{t.browseAllOccupations} →</Link>
        {" · "}
        <Link href={`/${lang}/providers/`}>{t.browseAllProviders} →</Link>
      </p>
    </div>
  );
}
