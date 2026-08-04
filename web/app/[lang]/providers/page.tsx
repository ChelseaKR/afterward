import Link from "next/link";
import { notFound } from "next/navigation";

import { Measure } from "@/components/Measure";
import {
  OTHER_LETTER,
  cityPreview,
  groupProvidersByLetter,
  summariseProviders,
  toProviderRow,
} from "@/lib/browse";
import { getSearchIndex } from "@/lib/data";
import { count, tidyName } from "@/lib/format";
import { TableFilter } from "@/components/TableFilter";
import { LANGUAGES, type Lang, dict, isLang } from "@/lib/i18n";
import { groupByProvider } from "@/lib/providers";

export function generateStaticParams() {
  return LANGUAGES.map((lang) => ({ lang }));
}

export async function generateMetadata({ params }: { params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  if (!isLang(lang)) return {};
  const t = dict(lang);
  return { title: `${t.browseProvidersTitle} | ${t.siteName}`, description: t.browseProvidersIntro };
}

/**
 * A field the provider never filled in, rendered visibly. A provider with no city is
 * missing that field, not operating nowhere, and an empty cell would read as the latter.
 */
function Unreported({ lang }: { lang: Lang }) {
  const t = dict(lang);
  return (
    <span className="unreported" title={t.notReportedLong}>
      {t.notReported}
    </span>
  );
}

/**
 * Browse index for every training provider in the dataset.
 *
 * Alphabetical, unlike the occupation index, because the task is different: people arrive
 * here knowing the name of the school they were about to enrol in. What the ordering cannot
 * carry, the columns do — how many programs a provider runs, how many of them published
 * what happened to their students, and where it operates. A provider showing "0 of 7" has
 * not been penalised by a missing-data rule; it filed nothing for any of its seven programs,
 * and that is the most useful thing this page can tell someone.
 */
export default async function ProvidersIndexPage({
  params,
}: {
  params: Promise<{ lang: string }>;
}) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();

  const t = dict(lang);
  const rows = groupByProvider(getSearchIndex().programs).map(toProviderRow);
  const groups = groupProvidersByLetter(rows);
  const tally = summariseProviders(rows);

  const sectionLabel = (letter: string): string =>
    letter === OTHER_LETTER ? t.otherLetter : letter;
  /** `#` is not a usable fragment identifier, so the leftovers section gets a name. */
  const sectionId = (letter: string): string =>
    `letter-${letter === OTHER_LETTER ? "other" : letter.toLowerCase()}`;

  return (
    <div className="shell browse">
      <p>
        <Link href={`/${lang}/`}>← {t.backToSearch}</Link>
      </p>

      <h1>{t.browseProvidersTitle}</h1>
      <p className="lede">{t.browseProvidersIntro}</p>

      <dl className="measure-grid panel">
        <Measure label={t.providersListed} value={count(tally.providers, lang)} lang={lang} />
        <Measure label={t.programsListed} value={count(tally.programs, lang)} lang={lang} />
        <Measure
          label={t.providersReportingSome}
          value={t.reportingRatio(tally.reportingSome, tally.providers)}
          lang={lang}
        />
      </dl>

      <p className="compare-note">{t.browseProvidersDerived}</p>

      <h2 id="on-this-page">{t.onThisPage}</h2>
      <nav className="jump-nav" aria-label={t.jumpToLetter}>
        <ul>
          {groups.map(({ letter }) => (
            <li key={letter}>
              <a href={`#${sectionId(letter)}`}>
                {sectionLabel(letter)}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      <TableFilter lang={lang} scope=".browse" />

      {groups.map(({ letter, providers }) => (
        <section key={letter}>
          <h2 id={sectionId(letter)}>
            {sectionLabel(letter)} — {count(providers.length, lang)}
          </h2>

          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th scope="col">{t.provider}</th>
                  <th scope="col" style={{ textAlign: "right" }}>
                    {t.providerPrograms}
                  </th>
                  <th scope="col" style={{ textAlign: "right" }}>
                    {t.providerReporting}
                  </th>
                  <th scope="col">{t.citiesColumn}</th>
                </tr>
              </thead>
              <tbody>
                {providers.map((provider) => {
                  const cities = cityPreview(provider.cities);
                  return (
                    <tr key={provider.slug}>
                      <th scope="row" style={{ fontWeight: 400 }}>
                        <Link href={`/${lang}/providers/${provider.slug}/`}>
                          {tidyName(provider.name)}
                        </Link>
                      </th>
                      <td className="num">{count(provider.programs, lang)}</td>
                      {/*
                        A ratio of known facts, not a measure: every program is present and
                        each either filed an outcome or did not. Zero on the left is a real
                        zero and is shown as one.
                      */}
                      <td className="num">
                        {t.reportingRatio(provider.reporting, provider.programs)}
                      </td>
                      <td>
                        {cities.shown.length > 0 ? (
                          <>
                            {cities.shown.join(" · ")}
                            {cities.more > 0 ? ` · ${t.moreCities(cities.more)}` : ""}
                          </>
                        ) : (
                          <Unreported lang={lang} />
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      ))}

      <p className="browse-more">
        <Link href={`/${lang}/occupations/`}>{t.browseAllOccupations} →</Link>
      </p>
    </div>
  );
}
