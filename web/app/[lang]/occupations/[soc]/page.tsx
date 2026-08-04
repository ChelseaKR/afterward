import Link from "next/link";
import { notFound } from "next/navigation";

import { Measure } from "@/components/Measure";
import { allOccupationCodes, getOccupation, programsForOccupation } from "@/lib/data";
import { count, money, signedPercent, tidyName } from "@/lib/format";
import { LANGUAGES, dict, isLang } from "@/lib/i18n";
import { translateTerm } from "@/lib/vocabulary";

export function generateStaticParams() {
  return LANGUAGES.flatMap((lang) => allOccupationCodes().map((soc) => ({ lang, soc })));
}

export default async function OccupationPage({
  params,
}: {
  params: Promise<{ lang: string; soc: string }>;
}) {
  const { lang, soc } = await params;
  if (!isLang(lang)) notFound();

  const occupation = getOccupation(soc);
  if (!occupation) notFound();

  const t = dict(lang);
  const programs = programsForOccupation(soc);
  const shrinking = occupation.percent_change !== null && occupation.percent_change < 0;
  const regions = occupation.regions
    .filter((r) => r.median_annual_wage !== null)
    .sort((a, b) => (b.median_annual_wage ?? 0) - (a.median_annual_wage ?? 0));

  return (
    <div className="shell detail">
      <p>
        <Link href={`/${lang}/`}>← {t.backToSearch}</Link>
      </p>

      <h1>{occupation.title}</h1>
      <p style={{ color: "var(--gray-90)" }}>
        SOC {occupation.soc_code}
        {occupation.period ? ` · ${occupation.period}` : ""}
      </p>

      {shrinking && (
        <p className="callout">
          <strong>
            {t.shrinking} {signedPercent(occupation.percent_change, lang)}
          </strong>
          <br />
          {t.shrinkingWarning}
        </p>
      )}

      <h2>{t.occupation}</h2>
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

      {regions.length > 0 && (
        <>
          <h2>{t.byRegion}</h2>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th scope="col">{t.region}</th>
                  <th scope="col" style={{ textAlign: "right" }}>
                    {t.medianWage}
                  </th>
                  <th scope="col" style={{ textAlign: "right" }}>
                    {t.jobOpenings}
                  </th>
                </tr>
              </thead>
              <tbody>
                {regions.map((region) => (
                  <tr key={`${region.area_name}`}>
                    <th scope="row" style={{ fontWeight: 400 }}>
                      {region.area_name}
                    </th>
                    <td className="num">{money(region.median_annual_wage, lang)}</td>
                    <td className="num">{count(region.total_job_openings, lang)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {programs.length > 0 && (
        <>
          <h2>
            {t.leadsTo} — {programs.length}
          </h2>
          <ul className="card-list">
            {programs.slice(0, 40).map((entry) => (
              <li key={entry.i} className={`card${entry.r ? "" : " is-unreported"}`}>
                <h3>
                  <Link href={`/${lang}/programs/${entry.i}/`}>{entry.n ?? "—"}</Link>
                </h3>
                <p className="card-provider" style={{ marginBottom: 0 }}>
                  {tidyName(entry.p)}
                  {entry.c ? ` · ${entry.c}` : ""}
                  {entry.$ !== null ? ` · ${money(entry.$, lang)}` : ""}
                </p>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
