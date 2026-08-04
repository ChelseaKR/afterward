import Link from "next/link";
import { notFound } from "next/navigation";

import { Measure } from "@/components/Measure";
import { allProgramIds, getCoverage, getProgram } from "@/lib/data";
import { count, isSmallSample, money, percent, signedPercent, tidyName } from "@/lib/format";
import { LANGUAGES, dict, isLang } from "@/lib/i18n";
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

/**
 * Build the statewide comparison for one measure, or undefined when either side is missing.
 * Never invents a comparison out of a null: an unreported program value has nothing to
 * compare, and saying "below average" about it would be an accusation, not a fact.
 */
function compare(
  programValue: number | null,
  stateValue: number | null | undefined,
  format: (value: number) => string | null,
): { formatted: string; programBeatsState: boolean | null } | undefined {
  if (programValue === null || stateValue === null || stateValue === undefined) return undefined;
  const formatted = format(stateValue);
  if (formatted === null) return undefined;
  return { formatted, programBeatsState: programValue > stateValue };
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
  const state = getCoverage().state_benchmark;
  const { outcomes, cost, length, location } = program;
  const occupation = program.occupations[0];
  const shrinking = occupation?.percent_change !== undefined && (occupation?.percent_change ?? 0) < 0;
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
        <Measure label={t.cost} value={money(cost.total_out_of_pocket, lang)} lang={lang} />
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
              benchmark={compare(outcomes.completion_rate, state?.completion_rate, (v) =>
                percent(v, lang),
              )}
            />
            <Measure
              label={t.employmentRate}
              value={percent(outcomes.employment_rate_q2, lang)}
              lang={lang}
              benchmark={compare(outcomes.employment_rate_q2, state?.employment_rate_q2, (v) =>
                percent(v, lang),
              )}
            />
            <Measure
              label={t.medianEarnings}
              value={money(outcomes.median_earnings, lang)}
              lang={lang}
              benchmark={compare(outcomes.median_earnings, state?.median_earnings, (v) =>
                money(v, lang),
              )}
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

      {occupation && (
        <>
          <h2>{t.occupation}</h2>
          {shrinking && (
            <p className="callout">
              <strong>
                {t.shrinking} {signedPercent(occupation.percent_change, lang)}
              </strong>
              <br />
              {t.shrinkingWarning}
            </p>
          )}
          <dl className="measure-grid panel">
            <Measure
              label={t.medianWage}
              value={money(occupation.median_annual_wage, lang)}
              note={t.perYear}
              lang={lang}
            />
            <Measure
              label={t.jobOpenings}
              value={count(occupation.total_job_openings, lang)}
              lang={lang}
            />
            <Measure
              label={t.entryEducation}
              value={translateTerm(occupation.entry_level_education, lang)}
              lang={lang}
            />
          </dl>
          {occupation.soc_code && (
            <p>
              <Link href={`/${lang}/occupations/${occupation.soc_code}/`}>
                {occupation.title} →
              </Link>
            </p>
          )}
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
