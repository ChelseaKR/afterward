import type { Metadata } from "next";
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

/**
 * The title and description a search result shows for one of the 1,162 provider pages.
 *
 * These are the pages people reach by searching a school's name, which makes them the most
 * consequential results on the site: this is where someone finds out what the college they
 * were about to enrol in publishes about itself. The name leads, the city follows, and the
 * site's own name appears nowhere — a result reading "… | Camino" spends its most valuable
 * characters on the one word a stranger cannot use.
 *
 * `lang` was never read here, so all 1,162 pages emitted the same English pair in both trees.
 *
 * A provider in more than one city gets a count rather than a first-city-wins guess, which
 * would name Fresno on a page listing programs in Fresno, Madera and Visalia.
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ lang: string; slug: string }>;
}): Promise<Metadata> {
  const { lang, slug } = await params;
  if (!isLang(lang)) return {};

  const provider = findProvider(getSearchIndex().programs, slug);
  if (!provider) return {};

  const t = dict(lang);
  const { cities } = provider;
  const place =
    cities.length === 1 ? `${cities[0]}, CA` : cities.length > 1 ? t.metaProviderCities(cities.length) : "California";
  // A count of rows in a list, not a measure anyone reported. Zero here would mean this
  // provider publishes nothing at all, which is a fact and is the point of showing it.
  const reporting = provider.programs.filter((program) => program.r).length;

  return {
    title: t.metaProviderTitle(tidyName(provider.name), provider.programs.length, place),
    description: t.metaProviderDescription(reporting, provider.programs.length),
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
                  {money(program.$, lang) ?? <span className="unreported" title={t.notReportedLong}>{t.notReported}</span>}
                </td>
                <td className="num">
                  {percent(program.er, lang) ?? (
                    <span className="unreported" title={t.notReportedLong}>{t.notReported}</span>
                  )}
                </td>
                <td className="num">
                  {money(program.me, lang) ?? <span className="unreported" title={t.notReportedLong}>{t.notReported}</span>}
                </td>
                <td>
                  {program.o.length > 0 ? (
                    program.o.join(" · ")
                  ) : (
                    <span className="unreported" title={t.notReportedLong}>
                      {t.notReported}
                    </span>
                  )}
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
