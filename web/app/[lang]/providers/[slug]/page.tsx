import Link from "next/link";
import { notFound } from "next/navigation";

import { Measure } from "@/components/Measure";
import { getSearchIndex } from "@/lib/data";
import { count, money, percent, signedPercent, tidyName } from "@/lib/format";
import { LANGUAGES, dict, isLang } from "@/lib/i18n";
import { findProvider, groupByProvider } from "@/lib/providers";
import { isShrinking } from "@/lib/search";

export function generateStaticParams() {
  const providers = groupByProvider(getSearchIndex().programs);
  return LANGUAGES.flatMap((lang) => providers.map((provider) => ({ lang, slug: provider.slug })));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const provider = findProvider(getSearchIndex().programs, slug);
  if (!provider) return {};
  return {
    title: `${tidyName(provider.name)} — training programs and outcomes | Camino`,
    description: `${provider.programs.length} training programs at ${tidyName(
      provider.name,
    )} in California, with cost and reported outcomes.`,
  };
}

export default async function ProviderPage({
  params,
}: {
  params: Promise<{ lang: string; slug: string }>;
}) {
  const { lang, slug } = await params;
  if (!isLang(lang)) notFound();

  const provider = findProvider(getSearchIndex().programs, slug);
  if (!provider) notFound();

  const t = dict(lang);
  const programs = [...provider.programs].sort((a, b) =>
    (a.n ?? "").localeCompare(b.n ?? ""),
  );
  const reported = programs.filter((p) => p.r).length;
  const shrinking = programs.filter((p) => isShrinking(p.g)).length;

  return (
    <div className="shell detail">
      <p>
        <Link href={`/${lang}/`}>← {t.backToSearch}</Link>
      </p>

      <h1>{tidyName(provider.name)}</h1>
      <p style={{ color: "var(--gray-90)" }}>{provider.cities.join(" · ")}</p>

      <dl className="measure-grid panel">
        <Measure
          label={t.providerPrograms}
          value={count(programs.length, lang)}
          lang={lang}
        />
        <Measure
          label={t.providerReporting}
          value={`${reported} / ${programs.length}`}
          lang={lang}
        />
        {shrinking > 0 && (
          <Measure
            label={t.providerShrinking}
            value={count(shrinking, lang)}
            lang={lang}
          />
        )}
      </dl>

      <h2>{t.providerProgramList}</h2>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">{t.viewProgram}</th>
              <th scope="col" style={{ textAlign: "right" }}>
                {t.cost}
              </th>
              <th scope="col" style={{ textAlign: "right" }}>
                {t.employmentRate}
              </th>
              <th scope="col" style={{ textAlign: "right" }}>
                {t.medianEarnings}
              </th>
              <th scope="col">{t.leadsTo}</th>
            </tr>
          </thead>
          <tbody>
            {programs.map((program) => (
              <tr key={program.i}>
                <th scope="row" style={{ fontWeight: 400 }}>
                  <Link href={`/${lang}/programs/${program.i}/`}>{program.n ?? "—"}</Link>
                </th>
                <td className="num">
                  {money(program.$, lang) ?? <span className="unreported">{t.notReported}</span>}
                </td>
                <td className="num">
                  {percent(program.er, lang) ?? (
                    <span className="unreported">{t.notReported}</span>
                  )}
                </td>
                <td className="num">
                  {money(program.me, lang) ?? <span className="unreported">{t.notReported}</span>}
                </td>
                <td>
                  {program.o}
                  {isShrinking(program.g) && (
                    <>
                      {" "}
                      <span className="badge badge-shrinking">
                        {t.shrinking} {signedPercent(program.g, lang)}
                      </span>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
