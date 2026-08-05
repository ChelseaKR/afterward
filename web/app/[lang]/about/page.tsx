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

/*
 * TODO(i18n): replaces `aboutComparisonsSecond` in the Spanish dictionary, which is stale in a
 * way that matters. The English paragraph records that this site withdrew its "better than
 * typical" / "worse than typical" verdicts and why; the Spanish one still explains what
 * "Mejor que lo típico" means, so the Spanish methodology page currently documents a feature
 * that no longer exists anywhere on the site — and documents it as a live judgement about
 * named businesses. The English text is read straight from the dictionary and is untouched.
 *
 * Delete this constant and the branch below once the Spanish key is corrected in i18n.ts.
 */
const COMPARISONS_SECOND_ES =
  "Este sitio llegó a etiquetar programas como «mejores» o «peores» que lo típico frente a " +
  "esa mediana. Ya no lo hace. La mediana juntaba a todos los programas que reportan, sin " +
  "importar su duración, y un certificado de cuatro semanas y una carrera de dos años no son " +
  "comparables en finalización: medidos contra programas de su misma duración, ese rótulo " +
  "estaba sencillamente invertido en alrededor de uno de cada diez programas. Las cifras y la " +
  "mediana se siguen mostrando; la conclusión la saca usted, porque la comparación no podía " +
  "sostenerla. Cuando dos programas se ponen lado a lado, la celda marcada es simplemente la " +
  "cifra reportada más fuerte de esa fila; una fila donde menos de dos programas reportaron " +
  "algo se queda sin marcar, porque ser el único que presentó un número no es lo mismo que " +
  "ser el mejor.";

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

      <h2 id="quarter">{t.aboutQuarterHeading}</h2>
      <p>{t.aboutQuarterBody}</p>

      <h2 id="comparisons">{t.aboutComparisonsHeading}</h2>
      <p>{t.aboutComparisonsBody}</p>
      <p>{lang === "es" ? COMPARISONS_SECOND_ES : t.aboutComparisonsSecond}</p>
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
