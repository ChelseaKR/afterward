import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Measure } from "@/components/Measure";
import { getSearchIndex } from "@/lib/data";
import { isOwnCohort } from "@/lib/compare";
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
 * site's own name appears nowhere — a result reading "… | Afterward" spends its most valuable
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

  /*
   * The published prices, lowest and highest. Programs with no figure are left out rather
   * than counted as free: a missing cost is a cost nobody published, and folding it in as
   * zero would advertise this provider as cheaper than anyone knows it to be.
   */
  const costs = programs.map((p) => p.$).filter((value): value is number => value !== null);
  const lowest = costs.length > 0 ? Math.min(...costs) : null;
  const highest = costs.length > 0 ? Math.max(...costs) : null;

  /*
   * The occupations across every program here, each named once. A provider running six
   * medical assisting courses trains for one job, not six, and the reason to read this list
   * is to find out what the place is for.
   */
  const trainsFor = new Map<string, string>();
  for (const program of programs) {
    program.o.forEach((title, index) => {
      const soc = program.s[index];
      if (soc !== undefined && !trainsFor.has(soc)) trainsFor.set(soc, title);
    });
  }
  const occupations = [...trainsFor.entries()].sort((a, b) => a[1].localeCompare(b[1]));

  return (
    <div className="shell detail">
      <p>
        {/* Unprefetched. This sits at the top of every page in the site, and the route it
            points at carries the whole search index, so prefetching it costs 229 KB of a
            reader's data on the chance they press it. Reasoning in app/[lang]/layout.tsx. */}
        <Link href={`/${lang}/`} prefetch={false}>
          ← {t.backToSearch}
        </Link>
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
        <Measure
          label={lowest === highest ? t.providerCostOne : t.providerCostRange}
          value={
            lowest === null || highest === null
              ? null
              : lowest === highest
                ? money(lowest, lang)
                : `${money(lowest, lang)} – ${money(highest, lang)}`
          }
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

      {/*
        Said once, at provider level, in the same voice a program page uses. Someone looking
        at a school where every course reports nothing should be told what that does and does
        not mean before they read a table of blanks.
      */}
      {reported === 0 && (
        <div className="panel panel-quiet">
          <p>
            <strong>{t.providerNoneReportedTitle}</strong>
          </p>
          <p style={{ marginBottom: 0 }}>{t.providerNoneReportedBody}</p>
        </div>
      )}

      {occupations.length > 0 && (
        <>
          <h2>{t.providerTrainsFor}</h2>
          <ul className="provider-occupations">
            {occupations.map(([soc, title]) => (
              <li key={soc}>
                <Link href={`/${lang}/occupations/${soc}/`}>{title}</Link>
              </li>
            ))}
          </ul>
        </>
      )}

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
            {programs.map((program) => {
              // The dagger marks a row whose outcome figures the provider filed against more
              // than this program. It is the one thing this table cannot leave unsaid: 32 of
              // De Anza's 35 rows are such rows, and a table exists to be read across.
              const widerCohort = program.r === true && !isOwnCohort(program);
              return (
              <tr key={program.i}>
                <th scope="row" style={{ fontWeight: 400 }}>
                  <Link href={`/${lang}/programs/${program.i}/`}>{program.n ?? "—"}</Link>
                  {widerCohort && (
                    <>
                      {" "}
                      <abbr className="cohort-marker" title={t.cohortMarkerLabel}>
                        †
                      </abbr>
                    </>
                  )}
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
              );
            })}
          </tbody>
        </table>
      </div>
      {/*
        Once, beneath the table it qualifies, rather than on every affected row. Rendered only
        when such a row is present, so a provider that filed every cohort honestly is not given
        a caution about something that is not on its page.
      */}
      {programs.some((program) => program.r === true && !isOwnCohort(program)) && (
        <p className="cohort-note">{t.cohortTableNote}</p>
      )}
    </div>
  );
}
