import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Fact, Measure } from "@/components/Measure";
import {
  allOccupationCodes,
  getOccupation,
  occupationTitleIn,
  occupationTitleLang,
  programsForOccupation,
} from "@/lib/data";
import { COHORT_NOT_OWN, isOwnCohort } from "@/lib/compare";
import { count, money, percent, signedPercent, tidyName } from "@/lib/format";
import { LANGUAGES, dict, isLang } from "@/lib/i18n";
import type { OccupationSkill, RelatedSource } from "@/lib/types";
import { translateTerm } from "@/lib/vocabulary";

type Copy = ReturnType<typeof dict>;

/** A skill the source actually rated. Kept separate so an unrated one cannot be sorted as 0. */
type RatedSkill = OccupationSkill & { importance: number };

/**
 * The skills O*NET rated, most important first, and the ones it named without rating.
 *
 * The two are returned apart rather than concatenated because they answer different
 * questions. A rated skill has a place in the order; an unrated one has no place in it at
 * all, and giving it the last place would be indistinguishable from saying the source rated
 * it lowest. The sort is stable, so skills sharing a rating keep the source's own order.
 */
function partitionSkills(skills: readonly OccupationSkill[]): {
  ranked: RatedSkill[];
  unrated: OccupationSkill[];
} {
  const ranked = skills
    .filter((skill): skill is RatedSkill => skill.importance !== null)
    .sort((a, b) => b.importance - a.importance);
  return { ranked, unrated: skills.filter((skill) => skill.importance === null) };
}

/**
 * The Bright Outlook designation, split into its parts and put in the reader's language.
 *
 * The source packs the categories into one string: "Rapid Growth", "Numerous Job Openings",
 * or both joined by a semicolon. They are descriptive phrases, so they are translated on the
 * same terms as every other controlled vocabulary in this data (see lib/vocabulary.ts).
 * "Bright Outlook" is the name of the federal designation itself and stays in English in
 * both languages, because it is what the reader will find if they go looking for it.
 *
 * A category this list does not know is shown exactly as published rather than dropped: the
 * page would otherwise silently narrow a federal designation to the parts it recognizes.
 */
function outlookCategories(value: string, t: Copy): string[] {
  return value
    .split(";")
    .map((part) => part.trim())
    .filter((part) => part.length > 0)
    .map((part) => {
      if (part === "Rapid Growth") return t.outlookRapidGrowth;
      if (part === "Numerous Job Openings") return t.outlookManyOpenings;
      return part;
    });
}

/**
 * The heading and note for the related-occupation table, chosen by how the list was built.
 *
 * The pipeline records which of two questions it answered, and they are not the same
 * question. O*NET's list says *these involve similar work* — an assessment of the job. The
 * SOC fallback says only *these are filed under the same two-digit code*, which is a fact
 * about the classification and not about the work. Wording them alike would hand the weaker
 * list the stronger claim, and the reader has no way to tell the difference from the rows.
 *
 * Null when the record does not say which it is. The pipeline only leaves `related_source`
 * null when `related` is empty, so this is unreachable today; if that ever changes, a table
 * with no caption for the relationship is a claim the record cannot support, and the page
 * declines to make it rather than guessing at the safer-sounding one.
 */
function relatedCaption(
  source: RelatedSource | null,
  t: Copy,
): { heading: string; note: string } | null {
  switch (source) {
    case "onet":
      return { heading: t.similarWork, note: t.similarWorkNote };
    case "soc_major_group":
      return { heading: t.relatedWork, note: t.relatedWorkNote };
    default:
      return null;
  }
}

export function generateStaticParams() {
  return LANGUAGES.flatMap((lang) => allOccupationCodes().map((soc) => ({ lang, soc })));
}

/**
 * The title and description a search result shows for one of the 1,340 occupation pages.
 *
 * There was no `generateMetadata` here at all, so every one of them inherited the layout's
 * and shipped under the identical title "Camino — California training programs, and what
 * (the site was called Camino until 2026-08-05)
 * happened to the people who took them". A search engine holding 1,340 pages with one title
 * has 1,340 pages it cannot tell apart, and a person scanning results has no reason to open
 * any of them.
 *
 * The occupation title is O*NET's own Spanish where Mi Próximo Paso publishes one, and
 * English where it does not. California publishes its titles in English only, which is why
 * this page said for months that the title had to stay English; that was true of the state's
 * data and false of the Department of Labor's, which publishes the same occupations in
 * Spanish. Nothing here is translated by this project — it is the Department's text or it is
 * the English, never a machine translation nobody reviewed.
 *
 * The wage goes in the description only when California published a statewide one. The other
 * thirteen occupations say plainly that none is published rather than borrowing a nearby
 * figure or, worse, formatting a null as $0 in a search result. Six of those thirteen — Actors,
 * Dancers, Musicians and Singers among them — have no published wage in any region either, and
 * they lose the word "pay" from their title too: a result promising a figure the page does not
 * contain is a wrong answer delivered before the page is even opened.
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ lang: string; soc: string }>;
}): Promise<Metadata> {
  const { lang, soc } = await params;
  if (!isLang(lang)) return {};

  const occupation = getOccupation(soc);
  if (!occupation) return {};

  const t = dict(lang);
  const wage = money(occupation.median_annual_wage, lang);
  const anyWage =
    occupation.median_annual_wage !== null ||
    occupation.regions.some((region) => region.median_annual_wage !== null);
  const spanishName = lang === "es" ? (occupation.spanish?.title ?? null) : null;
  const name = spanishName ?? occupation.title ?? `SOC ${occupation.soc_code ?? soc}`;

  return {
    title: anyWage ? t.metaOccupationTitle(name) : t.metaOccupationTitleNoPay(name),
    description: wage === null ? t.metaOccupationNoWage : t.metaOccupationWage(wage),
  };
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
  /*
   * Every region EDD publishes for this occupation, including those where it publishes
   * openings and growth but withholds the wage.
   *
   * An earlier version filtered those out, which inverted the project's own rule: a withheld
   * wage was being used to suppress other measures that were published. It discarded 518
   * region rows, among them San Diego for General and Operations Managers — 23,790 projected
   * openings, silently absent — and every one of the 24 regions for Musicians and Singers,
   * which removed the section entirely.
   *
   * Rows without a wage sort last, because the table is ordered by pay and an unknown is not
   * a low number. Their wage cell says "Not reported", which is the fact.
   */
  const regions = [...occupation.regions].sort((a, b) => {
    const [left, right] = [a.median_annual_wage, b.median_annual_wage];
    if (left === right) return (a.area_name ?? "").localeCompare(b.area_name ?? "");
    if (left === null) return 1;
    if (right === null) return -1;
    return right - left;
  });

  /*
   * Federal enrichment (PROVENANCE D6). 12 of the 670 occupations have none of it, and they
   * are meant to render as occupations without a description rather than as anything having
   * gone wrong: each section below appears only where there is something to put in it, so an
   * unenriched page is simply shorter.
   *
   * A description that exists but is blank is absence wearing a different shape, and is
   * treated as absence rather than as a heading over an empty paragraph.
   */
  const spanishTitle = lang === "es" ? (occupation.spanish?.title ?? null) : null;
  const displayTitle = spanishTitle ?? occupation.title;
  const spanishDescription = lang === "es" ? (occupation.spanish?.description ?? null) : null;
  const describedSource = spanishDescription ?? occupation.description;
  const described = describedSource === null ? "" : describedSource.trim();
  const description = described.length > 0 ? described : null;
  const { ranked, unrated } = partitionSkills(occupation.skills);
  const outlook =
    occupation.bright_outlook === null ? [] : outlookCategories(occupation.bright_outlook, t);
  const related = relatedCaption(occupation.related_source, t);

  return (
    <div className="shell detail">
      <p>
        <Link href={`/${lang}/`}>← {t.backToSearch}</Link>
      </p>

      {/*
        O*NET's Spanish title where one exists, the English where it does not. A reader who
        asked for Spanish and gets "Pharmacy Technicians" has been told the page is not
        really theirs; one who gets "Técnicos de Farmacia" has not.
      */}
      <h1 lang={occupationTitleLang(lang, occupation.soc_code)}>{displayTitle}</h1>
      {/* The English stays visible: it is the name on the certificate, the job advert and
          every state record, and a reader who only ever saw the Spanish could not search for
          the work anywhere else. */}
      {spanishTitle !== null && occupation.title !== null && (
        <p className="title-original" lang="en">
          {occupation.title}
        </p>
      )}
      <p style={{ color: "var(--gray-90)" }}>
        SOC {occupation.soc_code}
        {occupation.period ? ` · ${occupation.period}` : ""}
      </p>

      {/*
        What the work actually is, before any figure about it. The page used to open on a
        wage, which asks the reader to judge a job it had not yet described.
      */}
      {description !== null && (
        <>
          <p>{description}</p>
          {/*
            Which note depends on which text was actually rendered above it.
            
            The Spanish description shipped for a few minutes under a note reading "Solo se
            publica en inglés" — published in English only — directly contradicting the
            Spanish paragraph the reader had just finished. A caveat that describes a
            limitation the page no longer has is worse than no caveat: it tells a reader that
            what they can plainly see is not what they are getting.
          */}
          <p className="compare-note">
            {spanishDescription === null ? t.occupationDescriptionNote : t.occupationDescriptionNoteEs}
          </p>
        </>
      )}

      {shrinking && (
        <p className="callout">
          <strong>
            {t.shrinking} {signedPercent(occupation.percent_change, lang)}
          </strong>
          <br />
          {t.shrinkingWarning}
        </p>
      )}

      {/*
        Was "The job this trains for", which is program-page wording: on an occupation page
        there is no "this", the page is the job, and the heading read as though something
        above it trained for the thing below. It sits over the state's pay and openings
        projections, so it now says so. Wrong on 1,340 pages.
      */}
      <h2>{t.occupationOutlook}</h2>
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

      {/*
        The federal Bright Outlook designation, directly beneath California's own projected
        change so the reader can see both at once. They disagree more often than the label
        suggests: 11 designated occupations are ones California projects will shrink, among
        them Cashiers, carrying "Numerous Job Openings" against a projected −5.3%. Neither
        figure is wrong — one is a national count of openings, the other a state projection
        of employment — which is exactly why the designation is attributed rather than
        repeated as though the site had assessed anything.
      */}
      {outlook.length > 0 && (
        <div className="panel panel-quiet" style={{ marginTop: "1.25rem" }}>
          <p style={{ marginTop: 0 }}>
            <strong>{t.brightOutlookLabel}</strong>
            <br />
            {outlook.join(" · ")}
          </p>
          <p className="compare-note" style={{ marginBottom: 0 }}>
            {t.brightOutlookNote}
          </p>
        </div>
      )}

      {/*
        Skills as an ordered list of names, with no rating shown.

        The rating the order comes from is a bare number: the record carries `4.12` and
        nothing that says what it is out of. The raw API pairs each value with a companion
        0–100 field, and across all 20,335 cached pairs the two are related by
        (value − 1) ÷ 4 × 100, which puts the value on a 1–5 scale — but that companion field
        is not in what this page reads, and only the top six skills survive into the record,
        so the shipped numbers are the top of a scale whose bottom never appears. Printing
        "4.12" invites reading it as a score out of 5, or out of 10, or as a percentage, and
        inviting a wrong reading is not better than showing less. Rank is the part of the
        rating the data can carry on its own, so rank is what the page shows.
      */}
      {occupation.skills.length > 0 && (
        <>
          <h2>{t.skillsHeading}</h2>
          {ranked.length > 0 && (
            <>
              <p className="compare-note">{t.skillsNote}</p>
              <ol>
                {ranked.map((skill) => (
                  <li key={skill.name}>{skill.name}</li>
                ))}
              </ol>
            </>
          )}
          {unrated.length > 0 && (
            <p className="compare-note">
              {t.skillsUnrated(unrated.map((skill) => skill.name).join(", "))}
            </p>
          )}
        </>
      )}

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
                    <td className="num">
                      {money(region.median_annual_wage, lang) ?? (
                        <span className="unreported" title={t.notReportedLong}>
                          {t.notReported}
                        </span>
                      )}
                    </td>
                    <td className="num">
                      {count(region.total_job_openings, lang) ?? (
                        <span className="unreported" title={t.notReportedLong}>
                          {t.notReported}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/*
        The spread, not just the midpoint.
        
        The page showed one median, which answers "what does this pay?" and not "what would
        it pay me?" — and the distance between those is the entire question for someone
        deciding whether to spend a year training for it. Pharmacy technicians in California
        run from about $44,000 at the tenth percentile to about $83,000 at the ninetieth
        around a $57,000 median, and a reader shown only the median cannot see that.
        
        Each percentile is printed only where one was published. They are independently
        suppressible at source, so a row can carry four of five, and a missing one is left
        out rather than interpolated from its neighbours.
      */}
      {occupation.wage_spread != null && (
        <>
          <h2>{t.wageSpreadHeading}</h2>
          <dl className="wage-spread">
            {(
              [
                ["p10", t.wageP10],
                ["p25", t.wageP25],
                ["p50", t.wageP50],
                ["p75", t.wageP75],
                ["p90", t.wageP90],
              ] as const
            ).map(([key, label]) => {
              const value = occupation.wage_spread?.[key] ?? null;
              return value === null ? null : (
                <div key={key}>
                  <dt>{label}</dt>
                  <dd>{money(value, lang)}</dd>
                </div>
              );
            })}
          </dl>
          {occupation.wage_spread?.year != null && (
            <p className="compare-note">{t.wageSpreadNote(occupation.wage_spread.year)}</p>
          )}
        </>
      )}

      {occupation.related.length > 0 && related !== null && (
        <>
          <h2>{related.heading}</h2>
          <p className="compare-note">{related.note}</p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th scope="col">{t.occupationColumn}</th>
                  <th scope="col" style={{ textAlign: "right" }}>
                    {t.medianWage}
                  </th>
                  <th scope="col" style={{ textAlign: "right" }}>
                    {t.jobOpenings}
                  </th>
                  <th scope="col" style={{ textAlign: "right" }}>
                    {t.growth}
                  </th>
                </tr>
              </thead>
              <tbody>
                {occupation.related.map((sibling) => {
                  // Same name here as on the page this row opens. A related-work table in
                  // English pointing at a Spanish page is the inconsistency this resolver
                  // exists to prevent.
                  const siblingName = occupationTitleIn(lang, sibling.soc_code, sibling.title);
                  return (
                  <tr key={sibling.soc_code}>
                    <th scope="row" style={{ fontWeight: 400 }}>
                      {sibling.soc_code ? (
                        <Link
                          href={`/${lang}/occupations/${sibling.soc_code}/`}
                          lang={occupationTitleLang(lang, sibling.soc_code)}
                        >
                          {siblingName}
                        </Link>
                      ) : (
                        <span lang={occupationTitleLang(lang, sibling.soc_code)}>
                          {siblingName}
                        </span>
                      )}
                    </th>
                    <td className="num">
                      {money(sibling.median_annual_wage, lang) ?? (
                        <span className="unreported" title={t.notReportedLong}>
                          {t.notReported}
                        </span>
                      )}
                    </td>
                    <td className="num">
                      {count(sibling.total_job_openings, lang) ?? (
                        <span className="unreported" title={t.notReportedLong}>
                          {t.notReported}
                        </span>
                      )}
                    </td>
                    <td className="num">
                      {signedPercent(sibling.percent_change, lang) ?? (
                        <span className="unreported" title={t.notReportedLong}>{t.notReported}</span>
                      )}
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {programs.length > 0 && (
        <>
          {/*
            "Leads to — 66" pointed the wrong way. A program leads to an occupation, which is
            what the phrase means on a program card and in the provider table; on an
            occupation page the 66 are what lead *here*, so the heading was claiming this job
            leads to sixty-six things.
          */}
          <h2>
            {t.programsForThisJob} — {programs.length}
          </h2>
          <ul className="card-list">
            {programs.slice(0, 40).map((entry) => (
              <li key={entry.i} className={`card${entry.r ? "" : " is-unreported"}`}>
                <h3>
                  <Link href={`/${lang}/programs/${entry.i}/`}>{entry.n ?? "—"}</Link>
                </h3>
                <p className="card-provider">
                  {tidyName(entry.p)}
                  {entry.c ? ` · ${entry.c}` : ""}
                  {entry.$ !== null ? ` · ${money(entry.$, lang)}` : ""}
                </p>
                {/*
                  * The site's premise is what happened to the people who took a program, and
                  * this is the screen where someone picks among the programs for one job. It
                  * listed name, provider, city and cost, so the reader had to open each of
                  * eighteen tabs to reach the figures the search results already show on the
                  * card. Same index, same fields, so this is the search card's treatment
                  * brought to the page where the choice is actually made.
                  */}
                <dl className="facts">
                  <Fact
                    label={t.employmentRate}
                    value={percent(entry.er, lang)}
                    lang={lang}
                  />
                  <Fact label={t.medianEarnings} value={money(entry.me, lang)} lang={lang} />
                </dl>
                {/*
                  * Gated on `r` as well as the cohort flag: a caution about figures that are
                  * not on screen reads as a puzzle rather than a warning.
                  */}
                {entry.r && !isOwnCohort(entry) && (
                  <p className="cohort-note">
                    <span className="badge badge-small">{COHORT_NOT_OWN[lang].badge}</span>{" "}
                    {COHORT_NOT_OWN[lang].note}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
