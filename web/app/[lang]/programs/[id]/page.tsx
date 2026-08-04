import Link from "next/link";
import { notFound } from "next/navigation";

import { Measure } from "@/components/Measure";
import { allProgramIds, getCoverage, getProgram } from "@/lib/data";
import { count, isSmallSample, money, percent, signedPercent, tidyName } from "@/lib/format";
import { LANGUAGES, dict, isLang, type Lang } from "@/lib/i18n";
import { translateTerm } from "@/lib/vocabulary";
import { slugify } from "@/lib/providers";

export function generateStaticParams() {
  return LANGUAGES.flatMap((lang) => allProgramIds().map((id) => ({ lang, id })));
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const program = getProgram(id);
  if (!program) return {};
  return {
    title: `${program.program_name} — ${tidyName(program.provider_name)} | Camino`,
    description: `Cost, length, and reported outcomes for ${program.program_name} at ${tidyName(
      program.provider_name,
    )} in ${program.location.city}, California.`,
  };
}

/*
 * TODO(i18n): these five strings belong in `web/lib/i18n.ts` alongside every other piece of
 * user-facing copy. They are defined here only because that file was owned by a concurrent
 * change when this landed, and shipping the regional figures with no explanation at all
 * would have been worse than shipping the explanation in the wrong file. Lift the block
 * across verbatim as `regionIntro` / `regionFigureNote` / `regionNoRow` / `regionUnplaced` /
 * `regionUnplacedBody` and delete it from here.
 *
 * Both languages are present so that no page ships half-translated, which is the one failure
 * mode a temporary home like this could otherwise cause.
 */
interface RegionCopy {
  /** Said once, where a program's city was placed in a published area. */
  intro: (area: string) => string;
  /** Title attribute on each regional figure. */
  figureNote: (area: string) => string;
  /** The row exists but this one measure is blank inside it. Not a zero, and not the
   * provider's omission, so it cannot borrow the page's usual not-reported explanation. */
  figureBlank: string;
  /** The area is known, but this occupation has no published row in it. */
  noRow: (area: string) => string;
  /** The city could not be placed in a published area at all. */
  unplacedTitle: string;
  unplacedBody: (city: string | null) => string;
}

const REGION_COPY: Record<Lang, RegionCopy> = {
  en: {
    intro: (area) =>
      `Where California publishes a separate figure for ${area}, it appears beneath the ` +
      `statewide one. Statewide stays the headline: people who train here do not ` +
      `necessarily work here.`,
    figureNote: (area) =>
      `California's published figure for ${area}, the area this program's city sits in. ` +
      `Shown alongside the statewide figure, not instead of it.`,
    figureBlank:
      "California publishes figures for this area but not this one. That is missing " +
      "information, not a zero.",
    noRow: (area) =>
      `California publishes no separate figure for this job in ${area}. The statewide ` +
      `figures above are the only ones there are.`,
    unplacedTitle: "No regional figures for this program's city",
    unplacedBody: (city) =>
      `${city ?? "This program's city"} is not one of the metropolitan or rural areas ` +
      `California names when it publishes wages and openings. A neighbouring area's ` +
      `figures would look exactly like a correct answer, so none are shown and the ` +
      `statewide figures stand alone. About half of California's programs are in this ` +
      `position.`,
  },
  es: {
    intro: (area) =>
      `Donde California publica una cifra aparte para ${area}, aparece debajo de la cifra ` +
      `estatal. La cifra estatal sigue siendo la principal: quienes se capacitan aquí no ` +
      `necesariamente trabajan aquí.`,
    figureNote: (area) =>
      `Cifra publicada por California para ${area}, el área donde está la ciudad de este ` +
      `programa. Se muestra junto a la cifra estatal, no en su lugar.`,
    figureBlank:
      "California publica cifras para esta área, pero no esta. Es información que falta, " +
      "no un cero.",
    noRow: (area) =>
      `California no publica una cifra aparte para esta ocupación en ${area}. Las cifras ` +
      `estatales de arriba son las únicas que existen.`,
    unplacedTitle: "Sin cifras regionales para la ciudad de este programa",
    unplacedBody: (city) =>
      `${city ?? "La ciudad de este programa"} no es una de las áreas metropolitanas o ` +
      `rurales que California nombra al publicar salarios y vacantes. Las cifras de un ` +
      `área vecina se verían igual que una respuesta correcta, así que no se muestra ` +
      `ninguna y las cifras estatales quedan solas. Cerca de la mitad de los programas de ` +
      `California están en esta situación.`,
  },
};

/**
 * Build the statewide comparison for one measure, or undefined when either side is missing.
 * Never invents a comparison out of a null: an unreported program value has nothing to
 * compare, and saying "below average" about it would be an accusation, not a fact.
 */
function compare(
  programValue: number | null,
  peer: { median: number | null; reporting: number } | undefined,
  format: (value: number) => string | null,
  lang: Lang,
): { formatted: string; programBeatsState: boolean | null } | undefined {
  if (programValue === null || !peer || peer.median === null) return undefined;
  const formatted = format(peer.median);
  if (formatted === null) return undefined;
  return {
    formatted: `${formatted} ${dict(lang).ofReporting(peer.reporting)}`,
    // Equal to the median is neither better nor worse, so it gets no verdict.
    programBeatsState: programValue === peer.median ? null : programValue > peer.median,
  };
}

export default async function ProgramPage({
  params,
}: {
  params: Promise<{ lang: string; id: string }>;
}) {
  const { lang, id } = await params;
  if (!isLang(lang)) notFound();

  const program = getProgram(id);
  if (!program) notFound();

  const t = dict(lang);
  const region = REGION_COPY[lang];
  const peers = getCoverage().peer_medians;
  const { outcomes, cost, length, location } = program;
  // Every occupation this program feeds. Showing only the first named the wrong job on
  // hundreds of pages and hid the shrinking one whenever it was not listed first.
  const occupations = program.occupations;

  /*
   * The EDD area this program's city was placed in, if any. Null for 1,741 of California's
   * 3,266 programs, which makes it the common case rather than an edge one, and it gets a
   * stated explanation below rather than silence.
   *
   * `area_name` carries the county gloss and reads correctly in a sentence; `area_short_name`
   * is what fits next to a number. Either could in principle be null, and a nameless area is
   * one nothing truthful can be said about, so `placed` requires both.
   */
  const area = program.region;
  const areaName = area?.area_name ?? area?.area_short_name ?? null;
  const areaShort = area?.area_short_name ?? area?.area_name ?? null;
  const placed = areaName !== null && areaShort !== null;
  const worstChange = occupations
    .map((o) => o.percent_change)
    .filter((c): c is number => c !== null)
    .reduce<number | null>((worst, c) => (worst === null || c < worst ? c : worst), null);
  const shrinking = worstChange !== null && worstChange < 0;
  const smallSample = isSmallSample(outcomes.total_exited);

  return (
    <div className="shell detail">
      <p>
        <Link href={`/${lang}/`}>← {t.backToSearch}</Link>
      </p>

      <h1>{program.program_name}</h1>
      <p style={{ color: "var(--gray-90)", fontSize: "1.0625rem" }}>
        {program.provider_name ? (
          <Link href={`/${lang}/providers/${slugify(program.provider_name)}/`}>
            {tidyName(program.provider_name)}
          </Link>
        ) : null}
        {location.city ? ` · ${location.city}, CA` : ""}
      </p>

      <dl className="measure-grid panel">
        <Measure
          label={t.cost}
          value={
            cost.total_out_of_pocket === null
              ? null
              : cost.total_is_complete
                ? money(cost.total_out_of_pocket, lang)
                : t.costAtLeast(money(cost.total_out_of_pocket, lang) ?? "")
          }
          note={cost.total_is_complete ? undefined : t.costPartial}
          lang={lang}
        />
        <Measure
          label={t.length}
          value={length.weeks === null ? null : t.weeks(length.weeks)}
          lang={lang}
        />
        <Measure label={t.peopleServed} value={count(outcomes.total_served, lang)} lang={lang} />
      </dl>

      {program.program_format && <p>{program.program_format}</p>}

      <h2>{t.outcomes}</h2>

      {outcomes.reported ? (
        <>
          {smallSample && (
            <p>
              <span className="badge badge-small">{t.smallSample}</span>
            </p>
          )}
          <dl className="measure-grid panel">
            <Measure
              label={t.completionRate}
              value={percent(outcomes.completion_rate, lang)}
              note={outcomes.total_exited !== null ? t.basedOn(outcomes.total_exited) : undefined}
              lang={lang}
              benchmark={compare(outcomes.completion_rate, peers?.completion_rate, (v) => percent(v, lang), lang)}
            />
            <Measure
              label={t.employmentRate}
              value={percent(outcomes.employment_rate_q2, lang)}
              lang={lang}
              benchmark={compare(outcomes.employment_rate_q2, peers?.employment_rate_q2, (v) => percent(v, lang), lang)}
            />
            <Measure
              label={t.medianEarnings}
              value={money(outcomes.median_earnings, lang)}
              note={t.medianEarningsNote}
              lang={lang}
              benchmark={compare(outcomes.median_earnings, peers?.median_earnings, (v) => money(v, lang), lang)}
            />
          </dl>
        </>
      ) : (
        /*
         * Not an error state and not an empty state. A program reporting nothing is a real,
         * useful signal, so it gets a full explanation rather than a blank panel.
         */
        <div className="panel panel-quiet">
          <p>
            <strong>{t.outcomesUnreported}</strong>
          </p>
          <p style={{ marginBottom: 0 }}>{t.outcomesUnreportedBody}</p>
        </div>
      )}

      {occupations.length > 0 && (
        <>
          <h2>{t.occupation}</h2>
          {shrinking && (
            <p className="callout">
              <strong>
                {t.shrinking} {signedPercent(worstChange, lang)}
              </strong>
              <br />
              {t.shrinkingWarning}
            </p>
          )}
          {occupations.length > 1 && <p>{t.leadsToSeveral}</p>}

          {/*
            * Two different absences, told apart before a single number is shown.
            *
            * No area at all is a fact about this program's city and is true of every
            * occupation below it, so it is stated once, in the same panel treatment the page
            * already uses for a program that reported no outcomes. A known area with no row
            * for one particular job is a fact about that job, and is stated inside that job's
            * own section instead. Rendering them the same way would tell a reader in Fresno
            * that California is silent about Fresno.
            */}
          {placed ? (
            <p className="compare-note">{region.intro(areaName)}</p>
          ) : (
            <div className="panel panel-quiet">
              <p>
                <strong>{region.unplacedTitle}</strong>
              </p>
              <p style={{ marginBottom: 0 }}>{region.unplacedBody(location.city)}</p>
            </div>
          )}

          {occupations.map((occupation) => {
            // Only claimed when the city was placed: without an area there is no row to
            // read, and nothing here ever substitutes a nearby area's figures for it.
            const local = placed ? occupation.region : null;
            const figure = (value: string | null) =>
              local === null || areaShort === null
                ? undefined
                : {
                    area: areaShort,
                    value,
                    title: region.figureNote(areaName ?? areaShort),
                    unreportedTitle: region.figureBlank,
                  };

            return (
              <section key={occupation.soc_code} style={{ marginBottom: "1.5rem" }}>
                <h3 style={{ fontSize: "1.0625rem", marginBottom: "0.5rem" }}>
                  {occupation.soc_code ? (
                    <Link href={`/${lang}/occupations/${occupation.soc_code}/`}>
                      {occupation.title}
                    </Link>
                  ) : (
                    occupation.title
                  )}
                </h3>
                <dl className="measure-grid panel">
                  <Measure
                    label={t.medianWage}
                    value={money(occupation.median_annual_wage, lang)}
                    note={t.perYear}
                    lang={lang}
                    // A null inside a row that exists is a third state again: the area is
                    // known, EDD published a row for it, and left this cell empty. It says
                    // so, in its own words, and under no circumstances as $0.
                    regional={figure(local === null ? null : money(local.median_annual_wage, lang))}
                  />
                  <Measure
                    label={t.jobOpenings}
                    value={count(occupation.total_job_openings, lang)}
                    lang={lang}
                    regional={figure(local === null ? null : count(local.total_job_openings, lang))}
                  />
                  <Measure
                    label={t.growth}
                    value={signedPercent(occupation.percent_change, lang)}
                    lang={lang}
                  />
                  <Measure
                    label={t.entryEducation}
                    value={translateTerm(occupation.entry_level_education, lang)}
                    lang={lang}
                  />
                </dl>
                {placed && occupation.region === null && (
                  <p className="compare-note" style={{ marginTop: "0.5rem" }}>
                    {region.noRow(areaShort)}
                  </p>
                )}
              </section>
            );
          })}
        </>
      )}

      {program.description && (
        <>
          <h2>{t.viewProgram}</h2>
          <p>{program.description.replace(/^\d+\|/, "")}</p>
        </>
      )}

      {program.program_url && (
        <p>
          <a href={program.program_url} rel="nofollow noopener noreferrer" target="_blank">
            {t.providerSite} →
          </a>
        </p>
      )}
    </div>
  );
}
