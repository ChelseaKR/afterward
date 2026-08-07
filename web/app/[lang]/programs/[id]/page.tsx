import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { CENTERS_STEP, LEAD_STEP, SEQUENCE_STEP, stepCopy } from "@/components/funding";
import { Measure } from "@/components/Measure";
import { WageRangeChart } from "@/components/WageRangeChart";
import { programCount, programCountsBySoc } from "@/lib/browse";
import { nearestCenters, phoneParts } from "@/lib/centers";
import {
  allProgramIds,
  getCoverage,
  getOccupation,
  getProgram,
  getSearchIndex,
  occupationTitleIn,
  occupationTitleLang,
} from "@/lib/data";
import { count, isSmallSample, money, percent, signedPercent, tidyName } from "@/lib/format";
import { LANGUAGES, dict, feedTextLang, isLang, type Lang } from "@/lib/i18n";
import { linkNotice } from "@/lib/links";
import type {
  AmericanJobCenter,
  FundingCitation,
  FundingQuestion,
  FundingStep,
  LocalHelp,
  OccupationEducation,
  OccupationTask,
  Program,
  ProgramOccupation,
} from "@/lib/types";
import { translateTerm } from "@/lib/vocabulary";
import { slugify } from "@/lib/providers";

export function generateStaticParams() {
  return LANGUAGES.flatMap((lang) => allProgramIds().map((id) => ({ lang, id })));
}

/**
 * Where this program is, as a phrase: "Palo Verde College, Blythe, CA".
 *
 * Both parts are nullable in the type even though neither is null in the current file, and a
 * phrase built by interpolating a missing one reads "at , CA" or "at undefined" — which is how
 * a page ends up telling a search engine that a real training provider is called undefined.
 * Parts that are not there are simply not joined.
 */
function placeOf(program: Program): string {
  return [
    program.provider_name ? tidyName(program.provider_name) : null,
    program.location.city ? `${program.location.city}, CA` : null,
  ]
    .filter((part): part is string => part !== null)
    .join(", ");
}

/**
 * The title and description a search result shows for one of the 6,532 program pages.
 *
 * This used to destructure `{ id }` alone and never read `lang`, so both language trees
 * emitted the same English title and the same English description: a Spanish result for a
 * Lemoore College program was entirely in English, and the two trees were duplicates of each
 * other in everything a crawler compares.
 *
 * The site's own name is not in either string. A stranger scanning ten results cannot use it,
 * and the ~30 characters it costs are characters the provider's name and city need. What the
 * description adds beyond the title is the one thing worth knowing before clicking: whether
 * this program reported anything about the people who took it. Roughly a third did not, and
 * saying so in the result saves a click and cannot be read as a poor result.
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ lang: string; id: string }>;
}): Promise<Metadata> {
  const { lang, id } = await params;
  if (!isLang(lang)) return {};

  const program = getProgram(id);
  if (!program) return {};

  const t = dict(lang);
  const place = placeOf(program);
  const name = program.program_name ?? place;

  return {
    title: t.metaProgramTitle(name, place),
    description: program.outcomes.reported
      ? t.metaProgramReported(place)
      : t.metaProgramUnreported(place),
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
 * The occupation this program's figures actually describe, in words a reader can check.
 *
 * Falls back to the SOC code and then to a generic phrase, because every sentence built from
 * this reads "…reports that work inside X", and an empty X would turn a specific claim into a
 * vague one at exactly the moment the page is trying to be precise.
 */
function occupationName(occupation: ProgramOccupation, lang: Lang): string {
  const titled = occupationTitleIn(lang, occupation.soc_code, occupation.title);
  return titled ?? occupation.soc_code ?? dict(lang).unnamedOccupation;
}

/** SOC codes as prose: "31-1121 and 31-1122" in English, "31-1121 y 31-1122" in Spanish. */
function socList(codes: readonly string[], lang: Lang): string {
  return new Intl.ListFormat(lang, { style: "long", type: "conjunction" }).format(codes);
}

/**
 * Said above the figures whenever they belong to a wider occupation than the program teaches.
 *
 * This sits before the numbers rather than after them on purpose. Read afterwards it is a
 * footnote to a wage the reader has already taken as their own; read first it changes what
 * the wage is. It names the wider occupation, because "these numbers are broader" without
 * saying broader than what leaves the reader with a doubt they cannot act on, and it names
 * the program's own SOC codes so the claim can be checked against the published
 * classification rather than taken on trust.
 *
 * The two aggregate kinds get different sentences because they have different causes, and
 * the cause is the part that tells a reader whether a narrower figure exists anywhere: a
 * broad group is the category the classification files this occupation under, while a hybrid
 * is a federal publication bucket for occupations that cannot be measured apart. Neither is
 * hedged as an approximation — the figures are exactly right about a bigger population.
 */
function AggregateNote({ occupation, lang }: { occupation: ProgramOccupation; lang: Lang }) {
  const t = dict(lang);
  const { match } = occupation;
  if (match.kind === "exact") return null;

  const group = occupationName(occupation, lang);
  const codes = socList(match.program_soc_codes, lang);

  return (
    <p className="match-note">
      <strong>{t.aggregateHeading}</strong>
      <br />
      {match.kind === "soc_broad_group"
        ? t.aggregateBroadGroup(group, codes)
        : t.aggregateHybrid(group, codes)}
    </p>
  );
}

/**
 * The usual-entry credential, in the one case where it is missing because this site removed it.
 *
 * Deliberately not a `<Measure value={null}>`. That renders the page's standard not-reported
 * treatment, whose explanation says the provider did not report this — which here is a false
 * statement about a named organisation, repeated on 135 pages. The provider reported its
 * program faithfully; California published a credential for a group of occupations; this
 * project declined to put the second next to the first. The sentence saying so is visible
 * rather than a `title` attribute, since a tooltip is exactly where the wrong explanation was
 * hiding, and since it is unreachable on a phone.
 */
function WithheldEducation({ occupation, lang }: { occupation: ProgramOccupation; lang: Lang }) {
  const t = dict(lang);
  return (
    <div className="measure">
      <dt>{t.entryEducation}</dt>
      <dd className="withheld">
        {t.entryEducationWithheld}
        <small>{t.entryEducationWithheldNote(occupationName(occupation, lang))}</small>
      </dd>
    </div>
  );
}

type Copy = ReturnType<typeof dict>;

/* ============================================================================================
 * What the work is
 *
 * This page used to open on cost, length and an enrolment count: three numbers about a
 * purchase, before a word about what the purchase is for. The only thing on it describing the
 * actual work was the federal course-catalogue paragraph at the very bottom. Someone landing
 * here from a search engine is asking "what is this, and is it for me" — and the page answered
 * a question they had not got to yet.
 *
 * The federal occupation records carry the answer: what people in the job do, what else the
 * job is called, what education the people doing it actually have, and what employers expect
 * before and after they hire. All of it is read from `getOccupation`, which the program record
 * only points at by SOC code.
 * ========================================================================================== */

/** The parts of an occupation record this page needs, and nothing else. */
interface WorkProfile {
  /** Other names the same job is advertised under. Empty for 79 of the 670 occupations. */
  alternateTitles: string[];
  /** Distinct tasks, most important first. Empty for the 89 with no O*NET profile. */
  tasks: OccupationTask[];
  /** The federal one-paragraph account of the work, used only where there are no tasks. */
  description: string | null;
  education: OccupationEducation | null;
}

/*
 * `getOccupation` is deliberately uncached — a program page reads its record twice and holding
 * every program would cost an export worker the whole corpus. Occupations are the opposite
 * case: there are only 670 of them, all 3,266 program pages draw from that same small set in
 * two languages, and what is kept here is a few hundred bytes per occupation rather than the
 * 14 KB record it came from. Nothing in the map is ever mutated; every array below is built
 * fresh from the parsed record rather than sorted in place.
 */
const profiles = new Map<string, WorkProfile | null>();

function trimmedOrNull(value: string | null): string | null {
  if (value === null) return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

/**
 * Other names for the job, shortest first, at most four.
 *
 * The source publishes up to ten, alphabetically, which is a relevance order for nothing.
 * Taking the first four alphabetically would be an arbitrary sample presented as the common
 * names; the shortest are, in practice, the ones people actually say — "Charge Nurse",
 * "School Nurse", "Staff Nurse" rather than "Certified Operating Room Nurse (CNOR)". Four,
 * because this is a line that helps a reader recognise the job, and ten near-synonyms under a
 * heading is a keyword dump.
 *
 * A title identical to the occupation's own is dropped: "also called Roofer" under the heading
 * "Roofers" tells nobody anything.
 */
const ALTERNATE_TITLES_SHOWN = 4;

function pickAlternateTitles(titles: readonly string[], occupationTitle: string | null): string[] {
  const own = (occupationTitle ?? "").trim().toLowerCase();
  const seen = new Set<string>();
  const kept: string[] = [];

  for (const title of titles) {
    const trimmed = title.trim();
    const key = trimmed.toLowerCase();
    if (trimmed.length === 0 || key === own || seen.has(key)) continue;
    seen.add(key);
    kept.push(trimmed);
  }

  return kept
    .sort((a, b) => a.length - b.length || a.localeCompare(b))
    .slice(0, ALTERNATE_TITLES_SHOWN);
}

/**
 * Tasks in the order the source rates them, with the repeats removed.
 *
 * Two things the raw list needs before it can be shown. First, **it repeats itself**: 473 of
 * the 581 rated occupations return at least one sentence more than once, and Registered Nurses
 * returns eight tasks that are five distinct sentences. Rendering the array as published would
 * put "Monitor, record, and report symptoms or changes in patients' conditions." on the page
 * three times in a row, which reads as a bug in the site rather than a repeat in the feed.
 * De-duplication happens *after* the sort, so the copy that survives is the highest-rated one.
 * `_parse_tasks` in the pipeline drops the repeats too, as of 2026-08-05, so a freshly built
 * dataset arrives clean. This stays because the deployed 2026-08-04 snapshot does not, and a
 * page that only reads correctly against data newer than itself is a page waiting to break.
 *
 * Second, an unrated task has no place in the order at all. It sorts last, and is never
 * treated as a zero, which would file a task the source never judged below every task it
 * judged genuinely unimportant. No occupation has one today; the rule is not conditional on
 * that staying true.
 */
function rankTasks(tasks: readonly OccupationTask[]): OccupationTask[] {
  const ordered = [...tasks].sort((a, b) => {
    if (a.importance === null) return b.importance === null ? 0 : 1;
    if (b.importance === null) return -1;
    return b.importance - a.importance;
  });

  const seen = new Set<string>();
  const distinct: OccupationTask[] = [];
  for (const task of ordered) {
    const description = task.description.trim();
    const key = description.toLowerCase();
    if (description.length === 0 || seen.has(key)) continue;
    seen.add(key);
    distinct.push({ description, importance: task.importance });
  }
  return distinct;
}

function workProfile(soc: string | null): WorkProfile | null {
  if (soc === null) return null;

  const hit = profiles.get(soc);
  if (hit !== undefined) return hit;

  const occupation = getOccupation(soc);
  // `Array.isArray` rather than a type assertion: these three fields were appended to the
  // pipeline's occupation record, and a dataset built before they existed would arrive with
  // them missing rather than empty. A page reading `undefined.length` is a broken page; a page
  // reading an empty list is a page with one fewer section, which is the intended behaviour.
  const profile: WorkProfile | null =
    occupation === null
      ? null
      : {
          alternateTitles: pickAlternateTitles(
            Array.isArray(occupation.alternate_titles) ? occupation.alternate_titles : [],
            occupation.title,
          ),
          tasks: rankTasks(Array.isArray(occupation.tasks) ? occupation.tasks : []),
          description: trimmedOrNull(occupation.description),
          education: occupation.education ?? null,
        };

  profiles.set(soc, profile);
  return profile;
}

/**
 * How many tasks lead, and when the rest go behind a disclosure.
 *
 * Four is enough for a reader to recognise the work or rule it out, and eight sentences at the
 * top of a page is a wall rather than an explanation. The rest are one click away rather than
 * cut: the source published them and the page has no business deciding the reader has seen
 * enough. Below six, everything shows — a disclosure hiding a single sentence is worse than
 * the sentence.
 */
const TASKS_SHOWN = 4;
const TASKS_WITHOUT_DISCLOSURE = 5;

/**
 * Renders children bare when `open`, and behind a disclosure otherwise.
 *
 * The jobs section ran 4,481 pixels — 54 per cent of the page — because a program training
 * for three occupations printed three near-identical blocks of pay, hiring and education
 * tables. The first is the one most readers want; the others are worth having and are not
 * worth four screens of scrolling past. Native <details>, so it works without JavaScript in
 * a static export and keeps document order intact.
 */
function Collapsible({
  open,
  label,
  children,
}: {
  open: boolean;
  label: string;
  children: React.ReactNode;
}) {
  if (open) return <>{children}</>;
  return (
    <details className="occ-detail">
      <summary>{label}</summary>
      {children}
    </details>
  );
}

function WorkForOccupation({
  occupation,
  profile,
  lang,
  first,
  showHeading = true,
}: {
  occupation: ProgramOccupation;
  profile: WorkProfile;
  lang: Lang;
  /* False when this sits inside a section that has already named the occupation. */
  showHeading?: boolean;
  /*
   * Prints the shared source sentence once. A program training for three jobs printed it
   * three times, word for word — and a caveat a reader has learned to skip has stopped
   * being a caveat. It stays beside the first task list rather than moving to the top of
   * the section, because it describes the list it sits above.
   */
  first: boolean;
}) {
  const t = dict(lang);
  const { alternateTitles, tasks, description } = profile;
  const lead = tasks.length <= TASKS_WITHOUT_DISCLOSURE ? tasks : tasks.slice(0, TASKS_SHOWN);
  const rest = tasks.slice(lead.length);
  const name = occupationName(occupation, lang);

  return (
    <section style={{ marginBottom: "1.75rem" }}>
      {showHeading && (
        <h3 style={{ fontSize: "1.0625rem", marginBottom: "0.5rem" }}>
          {occupation.soc_code ? (
            <Link href={`/${lang}/occupations/${occupation.soc_code}/`}>{name}</Link>
          ) : (
            name
          )}
        </h3>
      )}

      {/*
        * Before the tasks, because for a great many people this line is the whole answer. A
        * reader who has worked as a school nurse does not need eight sentences to know whether
        * "Registered Nurses" is their job — they need to see "School Nurse" once.
        */}
      {alternateTitles.length > 0 && (
        <p className="also-called">
          <strong>{t.alsoCalled}</strong> {alternateTitles.join(" · ")}
        </p>
      )}

      {tasks.length > 0 ? (
        <>
          {first && <p className="compare-note">{t.tasksNote}</p>}
          <ul className="task-list">
            {lead.map((task) => (
              <li key={task.description}>{task.description}</li>
            ))}
          </ul>
          {rest.length > 0 && (
            <details className="more-tasks">
              <summary>{t.moreTasks(rest.length)}</summary>
              <ul className="task-list">
                {rest.map((task) => (
                  <li key={task.description}>{task.description}</li>
                ))}
              </ul>
            </details>
          )}
        </>
      ) : description !== null ? (
        /*
         * 89 occupations have no task list, and 77 of them still have the Department's
         * one-paragraph account of the work. A definition is weaker than a task list, so the
         * page says which of the two it is showing rather than letting the shorter section
         * pass for the same thing.
         */
        <>
          <p className="compare-note">{t.workDescriptionOnly}</p>
          <p>{description}</p>
        </>
      ) : (
        /*
         * The remaining 12: the federal publication buckets, which are not O*NET occupations
         * and have nothing behind them to read. Named rather than silently dropped, so a
         * reader looking at a program that trains for three jobs is not left wondering what
         * happened to the third.
         */
        <p className="compare-note">{t.workNothing}</p>
      )}
    </section>
  );
}

/* ============================================================================================
 * Getting in
 * ========================================================================================== */

/*
 * The two entry requirements, in words rather than in the federal vocabulary.
 *
 * "Moderate-term on-the-job training" is what California publishes; "1 to 12 months" is the
 * same answer said in a way a reader can act on. The two vocabularies agree one for one across
 * all 670 occupations — 280/165/148/44/21/12 on both sides — so this is a choice of phrasing
 * and not a second, differing source. An unrecognised value shows exactly as published rather
 * than disappearing, so a gap here is visible and fixable.
 */
function experienceLabel(value: string | null, t: Copy): string | null {
  switch (value) {
    case "No work experience":
      return t.expNone;
    case "Less than 5 years work experience":
      return t.expUnder5;
    case "5 years or more work experience":
      return t.expOver5;
    default:
      return trimmedOrNull(value);
  }
}

function trainingLabel(value: string | null, t: Copy): string | null {
  switch (value) {
    case "No on-the-job training":
      return t.ojtNone;
    case "Less than 1 month on-the-job training":
      return t.ojtUnderMonth;
    case "1 to 12 months on-the-job training":
      return t.ojtToYear;
    case "More than 1 year on-the-job training":
      return t.ojtOverYear;
    case "Internship/residency":
      return t.ojtInternship;
    case "Apprenticeship":
      return t.ojtApprenticeship;
    default:
      return trimmedOrNull(value);
  }
}

/**
 * What those two requirements mean for someone about to pay for this program.
 *
 * Ordered by how badly the reader needs it before they hand over money. Five years of prior
 * work in a related job — true of 25 California occupations — is the one fact on this page a
 * person should meet before enrolling rather than after, so it is the only one given the
 * page's warning treatment. An apprenticeship or a residency is the next: a classroom
 * certificate for an occupation people enter through an apprenticeship is a materially
 * different purchase, and nothing on this site said so.
 *
 * The last case is the reassuring one and is stated for the same reason as the rest: for 572
 * occupations no prior experience is expected, and a reader deciding whether a certificate can
 * be their route in deserves to be told plainly that it can.
 *
 * Silence where the pair is anything else — no sentence is better than a guessed one.
 */
function entryConsequence(
  education: OccupationEducation,
  t: Copy,
): { text: string; warn: boolean } | null {
  const experience = education.typical_experience;
  const training = education.typical_on_the_job_training;

  if (experience === "5 years or more work experience") {
    return { text: t.entryWarnExperience, warn: true };
  }
  if (experience === "Less than 5 years work experience") {
    return { text: t.entryNoteExperience, warn: false };
  }
  if (training === "Apprenticeship") return { text: t.entryNoteApprenticeship, warn: false };
  if (training === "Internship/residency") return { text: t.entryNoteInternship, warn: false };
  if (training === "More than 1 year on-the-job training") {
    return { text: t.entryNoteLongTraining, warn: false };
  }
  if (
    experience === "No work experience" &&
    (training === "No on-the-job training" ||
      training === "Less than 1 month on-the-job training")
  ) {
    return { text: t.entryNoteDirect, warn: false };
  }
  return null;
}

function EntryRequirements({ education, lang, first }: { education: OccupationEducation; lang: Lang; first: boolean }) {
  const t = dict(lang);
  const experience = experienceLabel(education.typical_experience, t);
  const training = trainingLabel(education.typical_on_the_job_training, t);
  if (experience === null && training === null) return null;

  const consequence = entryConsequence(education, t);

  return (
    <>
      <h4 style={{ fontSize: "1rem", margin: "1.25rem 0 0.5rem" }}>{t.entryHeading}</h4>
      <dl className="entry-facts">
        {experience !== null && (
          <div>
            <dt>{t.entryExperience}</dt>
            <dd>{experience}</dd>
          </div>
        )}
        {training !== null && (
          <div>
            <dt>{t.entryTraining}</dt>
            <dd>{training}</dd>
          </div>
        )}
      </dl>
      {consequence !== null && (
        <p
          className={consequence.warn ? "callout" : "compare-note"}
          style={{ marginTop: "0.75rem" }}
        >
          {consequence.warn ? <strong>{consequence.text}</strong> : consequence.text}
        </p>
      )}
      {first && <p className="compare-note">{t.entrySource}</p>}
    </>
  );
}

/* ============================================================================================
 * Someone else may be able to pay for this
 *
 * Every program on this site was on California's Eligible Training Provider List when the state
 * last reported it, and under 20 CFR 680.410 that listing is the precondition for an Individual
 * Training Account paying for it. Until now the page said nothing about it: a reader who could
 * have had this program funded left with a price and, for 334 of these pages, a dead link.
 *
 * Three things this block must never become.
 *
 * It must never read as a promise. Eligibility is determined by a one-stop centre after an
 * interview and assessment (20 CFR 680.220), priority is fixed at that first appointment, WIOA
 * money is the last money in (680.230), and a local area that has spent its year's training
 * funds is not obliged to refer anybody (680.340(c)). The words that stay on the right side of
 * that line are not written in this file — they come from `afterward.sources.local_help` through
 * `lib/i18n.ts`, where a test scans them for phrasing that turns a description of a public
 * program into a promise to one reader.
 *
 * It must never say a program *is* funded. `fundingLede` is stamped with the snapshot date and
 * says "was on the list", because listings are annual and can lapse.
 *
 * And `who_decides` must run underneath all of it, uncollapsed. It is a required field of the
 * object that carries the steps rather than a constant beside them, precisely so that a template
 * cannot render the steps and forget it — the failure this feature has is somebody taking a
 * morning off work for a "no", and the difference between that being a disappointment and being
 * this site's fault is whether it was clear from the start who decides. It is a plain paragraph
 * below, never a <details>, and never in the footer.
 * ========================================================================================== */

/**
 * The published phone field, with the numbers inside it dialable and the rest left as words.
 *
 * This used to strip every non-digit from the whole field and call the result a phone number.
 * For 163 of the 183 centres that is right, because the field holds one ten-digit number. For
 * the other 20 it is not: "619-319-9675 and 619-266-4253" became a `tel:` link for a twenty-digit
 * number, "916-746-7722 Ext. 102" one for a thirteen-digit number, and so on down to a field
 * carrying a switchboard and an EDD line. 778 of the 3,234 program pages that name an office
 * carried at least one of them, in both languages, and every one of those links dialled nothing.
 *
 * `phoneParts` finds the numbers rather than assuming the field is one; see `lib/centers.ts` for
 * what it declines to parse and why.
 *
 * The accessible name says which office is being called. Three offices on a page publish three
 * bare numbers, and "link, 619-319-9675" spoken three times identifies none of them — WCAG 2.2
 * AAA 2.4.9 asks that a link's purpose be clear from the link alone. The visible number stays
 * inside the spoken name, so the name still contains the label.
 */
function CenterPhone({ center, t }: { center: AmericanJobCenter; t: Copy }) {
  if (center.phone === null) return null;
  return (
    <p className="center-phone">
      <span>{t.fundingPhone}: </span>
      {phoneParts(center.phone).map((part, index) =>
        part.tel === null ? (
          <span key={index}>{part.text}</span>
        ) : (
          <a key={index} href={part.tel} aria-label={t.fundingCallLabel(center.name, part.text)}>
            {part.text}
          </a>
        ),
      )}
    </p>
  );
}

/**
 * One office, phone first.
 *
 * Phone before address because it is the only channel populated for all 183 California centres,
 * and because the state's own advice is to ring before travelling — its staff are not physically
 * present at every location. Everything else is rendered only where the directory published it:
 * a blank here is an unfilled field, and a rendered blank beside a label reads as a claim that
 * the office does not have one.
 *
 * `veterans_representative` is shown only when it is true. False and null both render as nothing,
 * because "no veterans' representative" would be a claim about an office that a missing box does
 * not support, and it is a claim that stops a veteran from going.
 */
function CenterCard({
  center,
  miles,
  lang,
}: {
  center: AmericanJobCenter;
  miles: number | null;
  lang: Lang;
}) {
  const t = dict(lang);
  const place = [center.city, center.state].filter((part) => part !== null).join(", ");
  const label =
    center.is_comprehensive === true
      ? t.fundingComprehensive
      : center.is_comprehensive === false
        ? t.fundingAffiliate
        : null;

  return (
    <li className="center">
      <p className="center-name">
        <strong>{center.name}</strong>
        {label !== null && <span className="center-type">{label}</span>}
      </p>

      <CenterPhone center={center} t={t} />

      <p className="center-address">
        {center.address.map((line) => (
          <span key={line}>{line}</span>
        ))}
        {place.length > 0 && (
          <span>
            {place}
            {center.postal_code === null ? "" : ` ${center.postal_code}`}
          </span>
        )}
        {miles !== null && <span className="center-miles">{t.fundingMilesAway(miles)}</span>}
      </p>

      {center.hours !== null && (
        <p className="center-hours">
          {t.fundingHours}: {center.hours}
        </p>
      )}
      {center.temporarily_closed === true && (
        <p className="center-closed">
          <strong>{t.fundingClosed}</strong>
          {center.closure_note === null ? "" : ` ${center.closure_note}`}
        </p>
      )}
      {center.veterans_representative === true && (
        <p className="center-veterans">{t.fundingVeteransRep}</p>
      )}
    </li>
  );
}

/*
 * The centre directory, indexed once per export worker rather than once per page.
 *
 * `getCoverage()` returns the same frozen object to all 6,532 program pages, so the index is
 * keyed on that array's identity: a dev server that rebuilds `public/data` underneath itself
 * hands back a different array and gets a fresh index, rather than resolving ids against the
 * previous dataset's offices.
 */
let centerIndex: { source: AmericanJobCenter[]; byId: Map<string, AmericanJobCenter> } | null = null;

function centersById(centers: AmericanJobCenter[]): Map<string, AmericanJobCenter> {
  if (centerIndex === null || centerIndex.source !== centers) {
    centerIndex = { source: centers, byId: new Map(centers.map((c) => [c.id, c])) };
  }
  return centerIndex.byId;
}

/**
 * How far out to look on the pages where the pipeline found nothing, and how many to show.
 *
 * 50 miles because that is the measured band in which every one of the 227 cities this dataset
 * publishes a program in has a centre. Beyond it there is nothing left to find, and an office
 * 120 miles away offered as "the nearest one" would be worse than the finder.
 *
 * Two rather than three: at this distance a second option is worth having and a third is a
 * directory. Measured against the current data, the three cities affected get two offices, two
 * offices and one — Lemoore's nearest are 26.7 and 27.0 miles, Coalinga's 38.7 and 39.0, and
 * South Lake Tahoe has one at 36.5 and nothing else inside 50.
 */
const BEYOND_RADIUS_MILES = 50;
const BEYOND_RADIUS_SHOWN = 2;

/**
 * The offices nearest this program, or an honest account of why there are none listed.
 *
 * Three states, and they are not two. A null list means nothing was established — no directory
 * was read, or this program's record carries no coordinates to search from. An empty list means
 * the search ran and there is no centre within the published radius, which is true of 32 of
 * California's 3,266 programs. A populated list is the nearest three.
 *
 * Those 32 pages used to end at "no centre within 25 miles" and a link to a statewide finder,
 * which is a search box rather than an office — offered to the readers with the furthest to go
 * and, for someone on a phone with no car, the least able to use one. Nothing further was
 * fetched to fix it: `coverage.json` already publishes all 183 centres with their coordinates
 * and this program's record already carries its own, so the nearest office beyond the radius is
 * arithmetic over data the page has in hand. It is shown with its distance and with the plain
 * statement that it is further out than this site calls nearby, because the point is to let a
 * reader judge the journey rather than to make 27 miles sound close.
 */
function NearestCenters({
  program,
  localHelp,
  lang,
}: {
  program: Program;
  localHelp: LocalHelp;
  lang: Lang;
}) {
  const t = dict(lang);
  const nearby = program.local_help?.centers ?? null;
  const radius = program.local_help?.radius_miles ?? localHelp.radius_miles;
  const directory = localHelp.centers === null ? null : centersById(localHelp.centers);

  const found =
    nearby === null || directory === null
      ? null
      : nearby
          .map((row) => ({ center: directory.get(row.id), miles: row.miles }))
          .filter((row): row is { center: AmericanJobCenter; miles: number | null } =>
            Boolean(row.center),
          );

  /*
   * Only reached when the pipeline searched and found nothing inside its radius, and only
   * useful where both the directory and this program's own coordinates exist. Distances are
   * rounded to a tenth for display for the same reason the pipeline rounds its own: this is a
   * great-circle figure offered to somebody deciding whether to travel, and more precision
   * would be a claim about roads nobody has measured.
   */
  const { lat, lon } = program.location;
  const searchBeyond =
    found !== null &&
    found.length === 0 &&
    localHelp.centers !== null &&
    lat !== null &&
    lon !== null;
  const beyond = searchBeyond
    ? nearestCenters(localHelp.centers ?? [], lat, lon, {
        limit: BEYOND_RADIUS_SHOWN,
        withinMiles: BEYOND_RADIUS_MILES,
      }).map((row) => ({ center: row.center, miles: Math.round(row.miles * 10) / 10 }))
    : [];

  const listed = found !== null && found.length > 0 ? found : beyond;

  return (
    <>
      {found === null ? (
        <p>{t.fundingCentersNotChecked}</p>
      ) : found.length === 0 && beyond.length === 0 ? (
        <p>{t.fundingCentersNone(radius)}</p>
      ) : (
        <>
          {found.length === 0 && <p>{t.fundingCentersBeyondIntro(radius)}</p>}
          <ul className="center-list">
            {listed.map((row) => (
              <CenterCard
                key={row.center.id}
                center={row.center}
                miles={row.miles}
                lang={lang}
              />
            ))}
          </ul>
          {/*
            The two labels on the cards above are federal terms of art, and until now they sat
            on the page with nothing saying what they mean. One clause is what that costs; the
            regulations behind it are on the guide this block links to.
          */}
          <p className="compare-note">
            {t.fundingCenterTypes} {t.fundingDistanceNote}
          </p>
        </>
      )}

      <p className="funding-finders">
        {t.fundingFindersIntro}
        <br />
        {localHelp.guidance.finders.map((finder, index) => (
          <span key={finder.url}>
            {index > 0 ? " · " : ""}
            <a href={finder.url} rel="nofollow noopener noreferrer" target="_blank">
              {finder.label}
            </a>
          </span>
        ))}
      </p>
    </>
  );
}

/** The questions worth asking, split by who can answer them, collapsed but never omitted. */

function FundingBlock({
  program,
  localHelp,
  snapshot,
  lang,
}: {
  program: Program;
  localHelp: LocalHelp;
  snapshot: string;
  lang: Lang;
}) {
  const t = dict(lang);
  const steps = localHelp.guidance.steps.filter((step) => step.on_program_page);
  const lead = steps.find((step) => step.id === LEAD_STEP);
  const rest = steps.filter((step) => step.id !== LEAD_STEP);
  const centersStep = rest.find((step) => step.id === CENTERS_STEP);
  const sequenceStep = rest.find((step) => step.id === SEQUENCE_STEP);
  /*
   * Falls back to the dictionary rather than to silence, the same way the heading above falls
   * back when `lead` is missing. `guidance` is baked into `coverage.json` by a pipeline run,
   * so a dataset built before this claim existed does not carry it — and this is the one
   * sentence in the block whose value is entirely in arriving before the reader enrols. A page
   * that waits for a data refresh to say it has said it too late.
   *
   * Not a second copy of the copy: `fundingBefore` is asserted byte for byte against
   * `local_help.STEPS` by `tests/test_site_copy.py`, so both branches render the sentence that
   * sits beside its citations and under the wording check.
   */
  const sequence =
    sequenceStep === undefined
      ? { heading: t.fundingBeforeHeading, detail: t.fundingBefore }
      : stepCopy(sequenceStep, t);

  return (
    <section className="funding">
      <h2>{lead === undefined ? t.fundingHeading : stepCopy(lead, t).heading}</h2>

      {/*
        Spanish only, and above everything rather than under it. This section is about money
        and eligibility, its readers are the ones an error hurts most, and it has not had a
        native reviewer. A reader is entitled to know that before they read it, not after.
        The English page needs no such note because English is the text being referred to.
      */}
      {lang === "es" && <p className="funding-translation-note">{t.fundingTranslationNote}</p>}

      {/*
        * The program-specific sentence, and the only one carrying a date. "Was on the list when
        * the state last reported" is the claim the data supports; "is eligible for funding" is
        * not, and listings lapse.
        */}
      <p className="funding-lede">{t.fundingLede(snapshot)}</p>

      {/*
        The one rule on this block that stops being useful if it is read late.

        Everything else here can be read after enrolling and still be worth something. This
        cannot: 20 CFR 680.220 puts the interview or assessment before the eligibility finding
        and 680.340 puts the referral and the account after it, so the order runs centre first
        and school second — and the reader this block is written for is someone who has just
        decided they want a program and is about to go and sign up for it. It is the second
        thing in the block for that reason, above the offices rather than behind the link to
        the guide, and it stays a plain paragraph: a disclosure is where a sentence goes when
        its timing does not matter.

        It says what the order is. It does not say what happens to somebody who has already
        paid, because no regulation read for this feature says, and the honest instruction is
        the one in the sentence itself — ask.
      */}
      <section className="funding-step funding-sequence">
        <h3>{sequence.heading}</h3>
        <p>{sequence.detail}</p>
      </section>

      {/*
        The offices come before the explanation of them.

        This block was 1,071 words and 3,796 pixels — 46 per cent of the words on a program
        page and a third of its height — and every word of it except the sentence above and
        the offices below is identical on all 6,532 program pages. Someone who has decided to
        ask for help needs an address and a phone number; the rules that make the help exist
        are what they read second, if at all.
      */}
      {centersStep !== undefined && (
        <section className="funding-step">
          {/*
            The heading names the offices; the paragraph explaining what a comprehensive
            one-stop centre is, and the regulation it rests on, are the last generic passage
            that was still being printed on all 6,532 program pages. Both are on the guide
            this block links to, so what stays here is the offices themselves.
          */}
          <h3>{stepCopy(centersStep, t).heading}</h3>
          <NearestCenters program={program} localHelp={localHelp} lang={lang} />
        </section>
      )}

      {/*
        The rules live on one page now, not on 6,532 copies of themselves.

        This block held about 1,071 words, every one of them identical on every program page,
        because it describes a federal program rather than a course. What is left here is the
        two things that are actually about this program: the dated sentence saying it was on
        the state's list, and the offices nearest to it.
      */}
      <p>
        <Link href={`/${lang}/paying-for-training/`}>{t.fundingGuideLink} →</Link>
      </p>

      {/*
        * Never inside a <details>, never moved to the footer, and never conditional on anything
        * above it having rendered. Everything in this block is a description of a public program;
        * this is the sentence that says it is not an offer, and it is the last thing read.
        */}
      <p className="who-decides">{t.fundingWhoDecides}</p>
      <p className="compare-note">{t.fundingEnglishSources}</p>
    </section>
  );
}

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
  ownCohort: boolean,
): { formatted: string; programBeatsState: boolean | null; ownCohort: boolean } | undefined {
  if (programValue === null || !peer || peer.median === null) return undefined;
  const formatted = format(peer.median);
  if (formatted === null) return undefined;
  return {
    // A program whose figures describe its whole college has nothing to compare. Inviting
    // the comparison is itself the assessment, so the median line is withheld rather than
    // shown beside a number that is not this program's.
    ownCohort,
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
  const coverage = getCoverage();
  const peers = coverage.peer_medians;
  /*
   * The funding route, the questions, and the sentence saying who decides. Absent only from a
   * dataset built before any of it existed, in which case the page is the page it always was.
   */
  const localHelp = coverage.local_help;
  const { outcomes, cost, length, location } = program;
  // False when the filing describes the provider's whole institution rather than this program.
  const attributable = outcomes.cohort.attributable;
  /*
   * Falls back to the filed URL when the dataset predates link checking. Unchecked is not
   * dead, so the fallback links exactly as the page always did rather than withholding.
   */
  const link =
    program.provider_link ??
    (program.program_url
      ? {
          url: program.program_url,
          href: program.program_url,
          linked: true,
          label: "program_page" as const,
          verdict: null,
          reason: null,
          checked_on: null,
          notice: null,
          substitution: null,
        }
      : null);
  const linkNote = link === null ? null : linkNotice(t, link);
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

  /*
   * Delivery format: a closed list of exactly three federal sentences, and so translated like
   * every other controlled vocabulary in this data (lib/vocabulary.ts) rather than passed
   * through. It did not look like a vocabulary because it is published as prose, which is how
   * it survived as the one English sentence in the middle of every Spanish program page.
   *
   * `translateTerm` maps both a null and a blank to null, so an all-whitespace value cannot
   * render as an empty paragraph.
   */
  const format = translateTerm(program.program_format, lang);

  /*
   * The federal record for each occupation this program leads to, in the same order the
   * figures below use, so a reader on a three-occupation page meets the three jobs in one
   * order and only one order.
   *
   * The opening section renders only where at least one of them has something to say about the
   * work. 61 of the 3,266 programs train for occupations O*NET has never profiled — residual
   * "All Other" codes and federal publication buckets — and those pages are meant to be the
   * page they already were, one section shorter, rather than a heading over an apology.
   */
  /*
   * Growing work adjacent to this program's shrinking occupations.
   *
   * Built only when something is actually shrinking, so the ordinary page does no extra work
   * and no reader is offered an alternative to a job the state expects to hold up fine.
   */
  const ownSocs = new Set(occupations.map((o) => o.soc_code).filter((c): c is string => c !== null));
  const socCounts = programCountsBySoc(getSearchIndex().programs);
  const alternativeIndex = new Map<
    string,
    { soc_code: string; title: string; median_annual_wage: number | null; percent_change: number | null; programs: number }
  >();
  if (shrinking) {
    for (const own of occupations) {
      if (own.soc_code === null) continue;
      if (own.percent_change === null || own.percent_change >= 0) continue;
      const record = getOccupation(own.soc_code);
      for (const rel of record?.related ?? []) {
        if (rel.soc_code === null || ownSocs.has(rel.soc_code)) continue;
        // Growing only. A related job the state also expects to shrink is not an alternative.
        if (rel.percent_change === null || rel.percent_change <= 0) continue;
        if (alternativeIndex.has(rel.soc_code)) continue;
        alternativeIndex.set(rel.soc_code, {
          soc_code: rel.soc_code,
          title: occupationTitleIn(lang, rel.soc_code, rel.title) ?? rel.soc_code,
          median_annual_wage: rel.median_annual_wage ?? null,
          percent_change: rel.percent_change,
          programs: programCount(socCounts, rel.soc_code),
        });
      }
    }
  }
  const alternatives = [...alternativeIndex.values()]
    .sort((a, b) => b.programs - a.programs || (b.percent_change ?? 0) - (a.percent_change ?? 0))
    .slice(0, 6);

  const profiled = occupations.map((occupation) => ({
    occupation,
    profile: workProfile(occupation.soc_code),
  }));
  const explainsWork = profiled.some(
    ({ profile }) =>
      profile !== null &&
      (profile.tasks.length > 0 ||
        profile.description !== null ||
        profile.alternateTitles.length > 0),
  );

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

      <h1 lang={feedTextLang(lang)}>{program.program_name}</h1>
      <p style={{ color: "var(--gray-90)", fontSize: "1.0625rem" }}>
        {program.provider_name ? (
          <Link href={`/${lang}/providers/${slugify(program.provider_name)}/`} lang={feedTextLang(lang)}>
            {tidyName(program.provider_name)}
          </Link>
        ) : null}
        {location.city ? ` · ${location.city}, CA` : ""}
      </p>

      {/*
        Said before the first English word rather than after the last one. The heading above
        is the program's own name, filed in English, and a Spanish reader has already met it;
        what they cannot tell without this is whether the English is the source data or the
        translation giving out. The occupations index and the occupation page each carry the
        same admission about their own untranslated text, and this page carried none.
      */}
      {/*
        The four facts a reader came for, before any prose about any of them.
        Measured before this existed: 900 pixels of desktop and 2.7 phone screens went by
        carrying the program's name, two caveats and a residual occupation title, and not one
        number. The narrative below is unchanged and still explains each of these properly —
        this only stops the page making someone scroll to find out whether it is even
        relevant to them. Every value routes through the same null handling as the detail
        below it, so "not reported" still reads as not reported.
      */}
      <dl className="at-a-glance">
        <div>
          <dt>{t.cost}</dt>
          <dd>
            {cost.total_out_of_pocket === null ? (
              <span className="unreported">{t.notReported}</span>
            ) : cost.total_is_complete ? (
              money(cost.total_out_of_pocket, lang)
            ) : (
              t.costAtLeast(money(cost.total_out_of_pocket, lang) ?? "")
            )}
          </dd>
        </div>
        <div>
          <dt>{t.length}</dt>
          <dd>
            {length.weeks === null ? (
              <span className="unreported">{t.notReported}</span>
            ) : (
              t.weeks(length.weeks)
            )}
          </dd>
        </div>
        <div>
          <dt>{t.employmentRate}</dt>
          <dd>
            {outcomes.employment_rate_q2 === null || !attributable ? (
              <span className="unreported">{t.notReported}</span>
            ) : (
              percent(outcomes.employment_rate_q2, lang)
            )}
          </dd>
        </div>
      </dl>

      <p className="compare-note">{t.programTextEnglishOnly}</p>

      {/*
        * What the work is, before what it costs.
        *
        * This section is first because the question it answers is first. Someone arriving here
        * wants to know what this job is and whether it is theirs; the price and the length are
        * the second question and the outcome measures are the third, and both are still on the
        * page, a screen further down. Nothing was removed to make room.
        */}
      {/*
        * The cost and length panel is gone, not moved.
        *
        * It printed "$7,500 / 12 weeks" 267 pixels below the summary strip that had just
        * printed "$7,500 / 12 weeks", under its own heading, as though the second pair were
        * additional information. What the panel held that the strip does not is the
        * enrolment count and the partial-cost caveat, and both are kept below.
        */}
      {cost.total_out_of_pocket !== null && !cost.total_is_complete && (
        <p className="compare-note">{t.costPartial}</p>
      )}

      <h2>{t.outcomes}</h2>

      {/*
        Only when there is a number.

        A program that reported nothing opened this section with "People enrolled — Not
        reported" and then, immediately below, a panel explaining that no outcomes were
        reported. The panel is the better sentence and it says the same thing, so the
        measure is not printed to say it first and worse.
      */}
      {outcomes.total_served !== null && (
        <dl className="measure-grid panel">
          <Measure label={t.peopleServed} value={count(outcomes.total_served, lang)} lang={lang} />
        </dl>
      )}

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
              benchmark={compare(outcomes.completion_rate, peers?.completion_rate, (v) => percent(v, lang), lang, attributable)}
            />
            <Measure
              label={t.employmentRate}
              value={percent(outcomes.employment_rate_q2, lang)}
              lang={lang}
              benchmark={compare(outcomes.employment_rate_q2, peers?.employment_rate_q2, (v) => percent(v, lang), lang, attributable)}
            />
            <Measure
              label={t.medianEarnings}
              value={money(outcomes.median_earnings, lang)}
              note={t.medianEarningsNote}
              lang={lang}
              benchmark={compare(outcomes.median_earnings, peers?.median_earnings, (v) => money(v, lang), lang, attributable)}
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
          {/*
            * Renamed from "The job this trains for", which the section above now answers. What
            * is left here is the two things a reader asks once they know what the work is:
            * what it pays, and what stands between them and being hired.
            */}
          {/*
            * One section per occupation, not two.
            *
            * What the work is and what it pays were separate sections, so each occupation
            * appeared twice about two thousand pixels apart — its task list near the top of
            * the page and its wages far below, with the program's own cost and outcomes
            * wedged between them. A reader following one job had to hold it in mind across
            * the whole page, and a reader comparing two could not. Everything known about an
            * occupation now sits under that occupation's name, once.
            */}
          <h2>{t.jobsHeading(occupations.length)}</h2>
          <p className="compare-note">{t.workNote}</p>
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
            * A warning with somewhere to go.
            *
            * 538 programs on this site train for work California projects will shrink, and
            * until now the page said so and stopped. Telling someone the trade they were
            * about to spend a year and several thousand dollars on is contracting, and then
            * offering nothing, is the least useful true thing this dataset can say.
            *
            * These come from the Department of Labor's own related-occupation list, filtered
            * to the ones California projects upward, with the jobs this program already
            * trains for removed — suggesting the shrinking occupation back to the reader as
            * an alternative to itself would be absurd. Sorted by projected openings, because
            * where the openings are is the one thing that makes a related job reachable
            * rather than merely adjacent.
            *
            * Deliberately not a recommendation, and the note says so. This project publishes
            * no verdicts about programs and will not start publishing them about careers: the
            * page can say what the state expects and how many programs here train for it, and
            * the reader decides whether any of it is theirs.
            */}
          {alternatives.length > 0 && (
            <section className="alternatives">
              <h3>{t.alternativesHeading}</h3>
              <p className="compare-note">{t.alternativesNote}</p>
              <ul className="alternatives-list">
                {alternatives.map((alt) => (
                  <li key={alt.soc_code}>
                    <Link href={`/${lang}/occupations/${alt.soc_code}/`}>{alt.title}</Link>
                    <span className="alternatives-facts">
                      {money(alt.median_annual_wage, lang) ?? t.notReported}
                      {alt.percent_change === null
                        ? ""
                        : ` · ${signedPercent(alt.percent_change, lang)}`}
                      {" · "}
                      {alt.programs === 0
                        ? t.alternativesNoPrograms
                        : t.alternativesPrograms(alt.programs)}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}

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

          {profiled.map(({ occupation, profile }, occIndex) => {
            // Only claimed when the city was placed: without an area there is no row to
            // read, and nothing here ever substitutes a nearby area's figures for it.
            const local = placed ? occupation.region : null;
            const education = profile?.education ?? null;
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
              <section key={occupation.soc_code} className="occ-block">
                <h3 style={{ fontSize: "1.0625rem", marginBottom: "0.5rem" }}>
                  {occupation.soc_code ? (
                    <Link
                      href={`/${lang}/occupations/${occupation.soc_code}/`}
                      lang={occupationTitleLang(lang, occupation.soc_code)}
                    >
                      {occupationName(occupation, lang)}
                    </Link>
                  ) : (
                    <span lang={occupationTitleLang(lang, occupation.soc_code)}>
                      {occupationName(occupation, lang)}
                    </span>
                  )}
                </h3>
                <Collapsible open={occIndex === 0} label={t.jobDetail}>
                {profile !== null && (
                  <WorkForOccupation
                    occupation={occupation}
                    profile={profile}
                    lang={lang}
                    first={occIndex === 0}
                    showHeading={false}
                  />
                )}
                {/*
                  * Before the panel, not after it: by the time someone has read a wage they
                  * have already decided whose wage it is.
                  */}
                <AggregateNote occupation={occupation} lang={lang} />
                {/*
                  * The local pay range, where California published one for this area.
                  *
                  * The panel below carries a statewide median and a local median. Two
                  * midpoints do not show that pharmacy technicians in Bakersfield run about
                  * $40,000 to $74,000 against $44,000 to $83,000 across the state — the
                  * region is not uniformly lower, it is differently shaped, and someone
                  * deciding where to train cannot see that from medians alone.
                  *
                  * Only for a program whose city California's own area titles name. The 1,741
                  * unplaced programs get nothing here rather than the nearest area's figures,
                  * which is the same rule the rest of this page follows.
                  */}
                {(() => {
                  // Guarded first so the area label below is a string, not a maybe-string.
                  if (!placed || areaShort === null) return null;
                  const record = occupation.soc_code === null ? null : getOccupation(occupation.soc_code);
                  const spread = record?.wage_spread ?? null;
                  const localSpread = spread?.regions?.[areaShort] ?? null;
                  if (spread === null || localSpread === null) return null;
                  const cells = ["p10", "p50", "p90"] as const;
                  // Every cell must be present on both rows: a comparison with a hole in it
                  // invites the reader to fill it in, and the value they would guess is the
                  // one the Bureau declined to publish.
                  if (cells.some((k) => localSpread[k] === null || spread[k] === null)) return null;
                  const areaLabel: string = areaName ?? areaShort;
                  return (
                    <div className="local-range">
                      <h4>{t.localRangeHeading(areaLabel)}</h4>
                      {/*
                        The picture first, the figures under it. The finding here is that a
                        region is differently shaped rather than uniformly lower, and that is
                        a comparison of two intervals — which is the one thing six numbers in
                        a table are genuinely bad at showing.
                      */}
                      <WageRangeChart
                        rows={[
                          { label: areaShort, percentiles: localSpread, emphasis: true },
                          { label: t.localRangeStatewide, percentiles: spread },
                        ]}
                      />
                      <p className="wage-chart-key">{t.wageChartKey}</p>
                      <table>
                        <thead>
                          <tr>
                            {/*
                              Named, not empty. The corner cell labels the row headers
                              beneath it, and a screen reader announcing a blank there gives
                              no clue what "Los Angeles-Long Beach-Glendale MD" is the name
                              of. Hidden visually because the rows read as their own labels
                              on screen, which is exactly what a visually-hidden label is for.
                            */}
                            <th scope="col">
                              <span className="visually-hidden">{t.localRangeAreaColumn}</span>
                            </th>
                            <th scope="col">{t.wageP10}</th>
                            <th scope="col">{t.wageP50}</th>
                            <th scope="col">{t.wageP90}</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr>
                            <th scope="row">{areaLabel}</th>
                            {cells.map((k) => (
                              <td key={k} className="num">{money(localSpread[k], lang)}</td>
                            ))}
                          </tr>
                          <tr>
                            <th scope="row">{t.localRangeStatewide}</th>
                            {cells.map((k) => (
                              <td key={k} className="num">{money(spread[k], lang)}</td>
                            ))}
                          </tr>
                        </tbody>
                      </table>
                      {spread.year !== null && (
                        <p className="compare-note">
                          {t.localRangeNote(areaLabel, spread.year)}
                        </p>
                      )}
                    </div>
                  );
                })()}

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
                  {/*
                    * Two nulls that mean opposite things, told apart before either is drawn.
                    * `entry_level_education_withheld` is the pipeline saying it had a value
                    * and removed it; a plain null is the absence the rest of the page's
                    * not-reported treatment correctly describes.
                    */}
                  {occupation.match.entry_level_education_withheld ? (
                    <WithheldEducation occupation={occupation} lang={lang} />
                  ) : (
                    <Measure
                      label={t.entryEducation}
                      value={translateTerm(occupation.entry_level_education, lang)}
                      lang={lang}
                    />
                  )}
                </dl>
                {placed && occupation.region === null && (
                  <p className="compare-note" style={{ marginTop: "0.5rem" }}>
                    {region.noRow(areaShort)}
                  </p>
                )}

                {/*
                  * Both of these sit *below* the grid, never inside it.
                  *
                  * "Usually needs" is one federal answer about what a person needs to enter.
                  * What people in the job actually studied is a count of a population and makes
                  * no claim about any individual, so it cannot be wrong about a reader in the
                  * way the category can — but dropped into the same row with a new label it
                  * would be read as a requirement, which is the exact false inference the
                  * withheld category exists to prevent. It is a second fact, not a replacement
                  * fact, and it is placed like one.
                  */}
                {education !== null && (
                  <EntryRequirements education={education} lang={lang} first={occIndex === 0} />
                )}
                </Collapsible>
              </section>
            );
          })}
        </>
      )}

      {program.description && (
        <>
          <h2>{t.viewProgram}</h2>
          {format !== null && <p>{format}</p>}
          <p lang={feedTextLang(lang)}>{program.description}</p>
        </>
      )}

      {/*
        Where this link goes is the last thing between a reader and enrolling, and 333 of
        these pages pointed somewhere that no longer answers. Four rules, all deliberate:

        - Link `href`, not `url`. They differ where a page was upgraded to https or the
          filed page was gone and the provider's home page stood in.
        - Show the notice on `notice`, never on `verdict`. 177 links are "indeterminate" —
          mostly hosts that dislike automated requests — and those must render exactly as
          an unchecked link does. Telling a reader a working college page is unreachable,
          beside that college's performance figures, would be a false claim about a real
          institution.
        - When there is nothing to link to, show the URL as text rather than dropping it,
          so a reader can still try it or look it up in an archive.
        - Switch on the notice exhaustively, and render nothing for one this build does not
          recognise. A dataset written by a newer builder must degrade to silence rather
          than to a sentence chosen by a fallback that never saw the evidence.
      */}
      {link && (
        <div className="provider-link">
          {link.linked && link.href !== null ? (
            <p>
              <a href={link.href} rel="nofollow noopener noreferrer" target="_blank">
                {link.label === "provider_home_page" ? t.providerHomePage : t.providerSite} →
              </a>
            </p>
          ) : (
            <p className="provider-link-plain">{link.url}</p>
          )}

          {linkNote && <p className="compare-note">{linkNote}</p>}
        </div>
      )}

      {/*
        * Last, after the reader has formed a view.
        *
        * The price, the outcomes and the provider's own link are all above it: this is not a
        * pitch to be met on the way in, it is what to do about the decision once it has been
        * made. It sits before the methodology link for the same reason — the methodology is
        * about the numbers, and this is about the next morning.
        */}
      {localHelp !== undefined && (
        <FundingBlock
          program={program}
          localHelp={localHelp}
          snapshot={coverage.snapshot_date}
          lang={lang}
        />
      )}

      {/*
        * Every figure above is somebody else's, filed by this provider or published by the
        * state, and this page is where a reader has just formed an opinion about a named
        * organisation from them. The route to the methodology belongs here rather than only
        * in the site chrome. It is a link on the page and not in the footer because the
        * footer lives in the shared layout, which this change does not own.
        */}
      <p className="browse-more">
        <Link href={`/${lang}/about/`}>{t.methodologyLink} →</Link>
      </p>
    </div>
  );
}
