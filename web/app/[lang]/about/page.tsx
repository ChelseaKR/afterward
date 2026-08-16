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
const REPO = "https://github.com/ChelseaKR/afterward";
const PROVENANCE_URL = `${REPO}/blob/main/PROVENANCE.md`;
const ISSUES_URL = `${REPO}/issues`;

/*
 * TODO(i18n): the strings in `COPY` belong in `web/lib/i18n.ts` under the keys named beside
 * them. They live here because that file was owned by a concurrent change when this landed.
 * Both languages are complete.
 *
 * Five of them are short forms of headings that are, correctly, long: this page is two and a
 * half thousand words of prose and it is read on a phone by people who do not have two and a
 * half thousand words of time. The jump list has to be scannable in one screen, and a list
 * that repeated "The outcomes are self-reported, and this site does not check them" verbatim
 * would be a second wall of text standing in front of the first. The four remaining sections
 * already have headings short enough to reuse, and are reused rather than restated so the nav
 * and the heading cannot drift apart.
 */
interface AboutCopy {
  /** i18n key: aboutOnThisPageNav */
  jumpLabel: string;
  /** i18n key: aboutShortSelfReported */
  shortSelfReported: string;
  /** i18n key: aboutShortMissing */
  shortMissing: string;
  /** i18n key: aboutShortQuarter */
  shortQuarter: string;
  /** i18n key: aboutShortAggregate */
  shortAggregate: string;
  /** i18n key: aboutShortLimits */
  shortLimits: string;
}

const COPY: Record<Lang, AboutCopy> = {
  en: {
    jumpLabel: "Jump to a section of this page",
    shortSelfReported: "Providers report their own results, and nobody audits them",
    shortMissing: "A blank means not reported — never zero",
    shortQuarter: "The earnings figure covers three months",
    shortAggregate: "When a job's figures cover more jobs than one",
    shortLimits: "What this site gets wrong",
  },
  es: {
    jumpLabel: "Ir a una sección de esta página",
    shortSelfReported: "Las instituciones reportan sus propios resultados y nadie los audita",
    shortMissing: "Un espacio en blanco significa no reportado, nunca cero",
    shortQuarter: "La cifra de ingresos cubre tres meses",
    shortAggregate: "Cuando la cifra de una ocupación abarca más de una",
    shortLimits: "Lo que este sitio hace mal",
  },
};

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
 * `withoutUrl` counts what the page actually renders — no clickable link — rather than what
 * the feed supplied. Those differ by 182: programs that filed an address the link check found
 * dead, and for which no provider home page could be substituted, render exactly like a
 * program that never filed one. Counting the feed's `program_url` alone (the counter's
 * original definition, predating the link check in commit c5d19d2) undercounted the copy's own
 * claim — "no working website link" — by that many, and would silently undercount it again the
 * next time link handling changes, since it does not read the same field the page renders.
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
  /** Programs whose page renders no clickable provider link, filed or not, dead or not. */
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
    // Mirrors the fallback in the program page: a missing `provider_link` block falls back to
    // `program_url` and renders a link whenever one was filed. So no link is rendered only
    // where a block is present and says not to — dead, or alive from a domain nothing
    // corroborated as the provider's — or where neither a block nor a URL exists at all.
    const renders = program.provider_link
      ? program.provider_link.linked && program.provider_link.href !== null
      : program.program_url !== null;
    if (!renders) withoutUrl += 1;
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
  const copy = COPY[lang];
  const coverage = getCoverage();
  const facts = corpusFacts();
  // Programs with no occupation panel at all: matched is a subset of total, so this is a
  // difference between two counted sets rather than a measure that could be missing.
  const unmatched = coverage.total_programs - coverage.programs_matched_to_occupation;

  /*
    The page's own contents, in reading order.

    A methodology page earns its length: every caveat here is one this site would be worse
    for dropping, and nothing below has been shortened to fit a phone. What a phone reader
    was owed instead is a way in — some of them arrived from a program page wanting one
    answer ("why is this blank?") and had no way to find it short of scrolling past two
    thousand words of prose they did not ask for. This list is that way in, and it doubles as
    the shortest honest summary of the page: read only these nine lines and you have been
    told the nine things that most change how a number here should be read.
  */
  const sections: { id: string; label: string }[] = [
    { id: "sources", label: t.aboutSourcesHeading },
    { id: "self-reported", label: copy.shortSelfReported },
    { id: "blank", label: copy.shortMissing },
    { id: "quarter", label: copy.shortQuarter },
    { id: "comparisons", label: t.aboutComparisonsHeading },
    { id: "wider-occupation", label: copy.shortAggregate },
    { id: "limits", label: copy.shortLimits },
    { id: "corrections", label: t.aboutCorrectionsHeading },
    { id: "advice", label: t.aboutAdviceHeading },
  ];

  return (
    <div className="shell detail about">
      <p>
        {/* Unprefetched. This sits at the top of every page in the site, and the route it
            points at carries the whole search index, so prefetching it costs 229 KB of a
            reader's data on the chance they press it. Reasoning in app/[lang]/layout.tsx. */}
        <Link href={`/${lang}/`} prefetch={false}>
          ← {t.backToSearch}
        </Link>
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

      <h2 id="on-this-page">{t.onThisPage}</h2>
      <nav className="jump-nav" aria-label={copy.jumpLabel}>
        <ul>
          {sections.map((section) => (
            <li key={section.id}>
              <a href={`#${section.id}`}>{section.label}</a>
            </li>
          ))}
        </ul>
      </nav>

      <h2 id="sources">{t.aboutSourcesHeading}</h2>
      <p>{t.aboutSourcesBody}</p>

      <dl className="source-list">
        <dt>{t.aboutSourceProgramsLabel}</dt>
        <dd>{t.aboutSourceProgramsBody}</dd>
        <dt>{t.aboutSourceOccupationsLabel}</dt>
        <dd>{t.aboutSourceOccupationsBody}</dd>
        <dt>{t.aboutSourceFederalLabel}</dt>
        <dd>{t.aboutSourceFederalBody}</dd>
        <dt>{t.aboutSourceWagesLabel}</dt>
        <dd>{t.aboutSourceWagesBody}</dd>
      </dl>

      <p>{t.aboutSourcesDates}</p>
      <p>
        <a href={PROVENANCE_URL} rel="noopener noreferrer">
          {t.aboutProvenanceLink} →
        </a>
      </p>

      <h2 id="self-reported">{t.aboutSelfReportedHeading}</h2>
      <p>{t.aboutSelfReportedBody}</p>
      <p>{t.aboutSelfReportedSecond}</p>

      <h2 id="blank">{t.aboutMissingHeading}</h2>
      <p>{t.aboutMissingBody}</p>
      <p>
        {t.aboutMissingSecond(
          tally(coverage.programs_with_any_outcome, lang),
          tally(coverage.total_programs, lang),
        )}
      </p>
      {/*
        This paragraph states the size of the gap in one sentence. The page it now links to
        takes that sentence apart: which measure, which kind of provider, and against how
        large a group. Someone who arrives here asking "why is this blank?" is exactly the
        reader that page was written for.
      */}
      <p>
        <Link href={`/${lang}/outcomes-coverage/`} prefetch={false}>
          {t.coverageTitle} →
        </Link>
      </p>
      {/*
        The other page written for somebody checking rather than choosing: the same data as
        CTDL, with what the mapping carries, what it drops, and what an outside validator made
        of it. Linked from here because it is otherwise reachable only from a search result.
      */}
      <p>
        <Link href={`/${lang}/ctdl/`} prefetch={false}>
          {t.ctdlTitle} →
        </Link>
      </p>

      <h2 id="quarter">{t.aboutQuarterHeading}</h2>
      <p>{t.aboutQuarterBody}</p>

      <h2 id="comparisons">{t.aboutComparisonsHeading}</h2>
      <p>{t.aboutComparisonsBody}</p>
      <p>{t.aboutComparisonsSecond}</p>
      <p>{t.aboutComparisonsThird}</p>

      <h2 id="wider-occupation">{t.aboutAggregateHeading}</h2>
      <p>{t.aboutAggregateBody(tally(facts.aggregateMatched, lang))}</p>
      <p>{t.aboutAggregateSecond}</p>

      <h2 id="limits">{t.aboutLimitsHeading}</h2>
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

      <h2 id="corrections">{t.aboutCorrectionsHeading}</h2>
      <p>{t.aboutCorrectionsBody}</p>
      <p>{t.aboutCorrectionsSecond}</p>
      <p>
        <a href={ISSUES_URL} rel="noopener noreferrer">
          {t.aboutCorrectionsLink} →
        </a>
      </p>

      <h2 id="advice">{t.aboutAdviceHeading}</h2>
      <p>{t.aboutAdviceBody}</p>

      <p className="browse-more">
        <Link href={`/${lang}/occupations/`}>{t.browseAllOccupations} →</Link>
        {" · "}
        <Link href={`/${lang}/providers/`}>{t.browseAllProviders} →</Link>
      </p>
    </div>
  );
}
