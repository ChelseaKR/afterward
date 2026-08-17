/**
 * English and Spanish ship together from the first release.
 *
 * About 28% of Californians speak Spanish at home, and the people most likely to need this
 * tool are among the least well served by English-only government software. Translation is
 * therefore a launch requirement, not a later phase, and the type below makes an untranslated
 * string a compile error rather than a silent fallback to English.
 */

export const LANGUAGES = ["en", "es"] as const;
export type Lang = (typeof LANGUAGES)[number];

export const DEFAULT_LANG: Lang = "en";

export function isLang(value: string): value is Lang {
  return (LANGUAGES as readonly string[]).includes(value);
}

/**
 * `lang` for text the federal and state feeds publish in English only, unconditionally.
 *
 * Unlike `occupationTitleLang` in `data.ts`, which checks a per-occupation Spanish name
 * because O*NET publishes one for 600 of 670, this has nothing to check: `program_name`,
 * `description` and `provider_name` have no Spanish counterpart in the feed at all, for any
 * program. Returns `undefined` on an English page so the attribute is never emitted where it
 * would be redundant.
 */
export function feedTextLang(lang: Lang): "en" | undefined {
  return lang === "es" ? "en" : undefined;
}

/**
 * How each length cap reads to someone planning around it, in each language.
 *
 * Months lead and weeks follow in brackets, because nobody budgets rent, childcare or an
 * unemployment claim in weeks, and weeks are what the state publishes. Both have to be on the
 * option: dropping the weeks would put a number on screen this dataset did not measure, and
 * dropping the months would make the reader do the arithmetic that decides whether they can
 * afford the program at all.
 *
 * A cap with no gloss falls back to a plain weeks phrase in `lengthAtMost`, so a link carrying
 * `weeks=18` still labels itself rather than rendering an empty option.
 */
const LENGTH_GLOSS: Record<Lang, Record<number, string>> = {
  en: {
    4: "About a month or less",
    12: "About 3 months or less",
    26: "About 6 months or less",
    52: "About a year or less",
  },
  es: {
    4: "Un mes o menos",
    12: "Unos 3 meses o menos",
    26: "Unos 6 meses o menos",
    52: "Un año o menos",
  },
};

const en = {
  siteName: "Afterward",
  tagline: "California training programs, and what happened to the people who took them",
  notAffiliated:
    "Not a California state website. An independent project built from public data.",
  skipToContent: "Skip to main content",

  searchLabel: "Search programs, providers, or jobs",
  searchPlaceholder: "medical assistant, welding, Fresno…",
  filters: "Filters",
  clearFilters: "Clear filters",
  resultsCount: (n: number, total: number) => `${fmt(n)} of ${fmt(total)} programs`,
  noResults: "No programs match these filters.",
  noResultsHint: "Try removing a filter or searching for a broader term.",

  filterOutcomes: "Only programs with reported outcomes",
  filterOutlook: "Job outlook",
  outlookAny: "Any outlook",
  outlookGrowing: "Only growing jobs",
  outlookShrinking: "Only shrinking jobs",
  statShrinking: (n: number) => `${fmt(n)} train for jobs California expects to shrink`,
  statReported: (n: number, total: number) =>
    `${fmt(n)} of ${fmt(total)} report what happened to their students`,
  showThese: "Show these",
  filterCity: "City",
  filterAnyCity: "Anywhere in California",
  filterMaxCost: "Maximum out-of-pocket cost",
  filterAnyCost: "Any cost",

  /* ---- How long you can give it ----
   *
   * The other half of what a person out of work is spending, and until now the half the
   * interface never asked about. These programs run from one week to 260, and the difference
   * between a 12-week course and a 72-week pathway is the difference between two decisions.
   */
  filterLength: "Longest you can spend on it",
  filterAnyLength: "Any length",
  lengthAtMost: (weeks: number): string => {
    const gloss = LENGTH_GLOSS.en[weeks];
    return gloss ? `${gloss} (${fmt(weeks)} weeks)` : `${fmt(weeks)} weeks or less`;
  },
  filterLengthNote:
    "Weeks as the provider reported them. Length is also what makes two completion rates " +
    "comparable: among California programs whose figures describe that program alone, the " +
    "median share who finished is 97% at four weeks or less, and falls at every step up in " +
    "length to 78% beyond a year. A long program and a short one are not being measured on " +
    "the same scale.",
  filterLengthUnmeasured: (n: number): string =>
    n === 1
      ? "This filter also leaves out 1 program that matches the rest of your search: its " +
        "provider reported no length, so there is nothing here for the filter to test. A " +
        "program that never said how long it takes is not a program that takes no time."
      : `This filter also leaves out ${fmt(n)} of the programs that match the rest of your ` +
        `search: their providers reported no length, so there is nothing here for the ` +
        `filter to test. A program that never said how long it takes is not a program that ` +
        `takes no time.`,
  /* ---- Competency-based programs ----
   *
   * Its own disclosure, in its own words, beside the one above. Until 2026-08-07 these
   * programs were inside that one, because the pipeline read the scorecard's competency-based
   * marker as "not reported": the site told a reader that six providers had failed to say
   * how long their courses run, when what those providers had said is that the course runs
   * until the student can do the work. The two sentences stay apart because one describes a
   * gap in the record and the other describes how a course is taught, and the second may be
   * the thing the reader was looking for.
   */
  filterLengthCompetency: (n: number): string =>
    n === 1
      ? "This filter also leaves out 1 competency-based program that matches the rest of " +
        "your search. It finishes when the student can do the work, so it has no fixed " +
        "length to compare against a time limit. That is how the provider built it, not " +
        "something missing from the record."
      : `This filter also leaves out ${fmt(n)} competency-based programs that match the rest ` +
        `of your search. They finish when the student can do the work, so they have no fixed ` +
        `length to compare against a time limit. That is how their providers built them, not ` +
        `something missing from the record.`,
  /** The length cell itself, everywhere a program's length is shown. Never "Not reported". */
  lengthCompetencyBased: "Competency-based: no fixed length",
  lengthCompetencyBasedLong:
    "The provider reported this program as competency-based: it finishes when the student can " +
    "do the work, so there is no set number of weeks. That is what the provider filed, not a " +
    "gap in the record.",
  /**
   * The length cap named as something a sentence can remove, for the empty state's list of
   * filters worth dropping. Belongs with the `nameQuery`/`nameCost` family that `SearchApp`
   * still holds in its local `COPY` block under a standing TODO to move here; new strings go
   * to the documented home rather than growing the block that is on its way out.
   */
  filterNameLength: (label: string): string => `the time limit “${label}”`,

  sortBy: "Sort by",
  sortRelevance: "Best match",
  sortEarnings: "Highest reported earnings",
  sortCost: "Lowest cost",
  sortLength: "Shortest first",
  sortOpenings: "Most job openings",

  cost: "Cost",
  costAtLeast: (v: string) => `At least ${v}`,
  costPartial:
    "One cost component was not reported, so the real total is higher than this.",
  leadsToSeveral: "Trains for more than one job. The outlook shown is the weakest of them.",
  length: "Length",
  weeks: (n: number) => `${fmt(n)} weeks`,
  provider: "Provider",
  providerPrograms: "Programs offered",
  providerReporting: "Report outcomes",
  providerShrinking: "Train for shrinking jobs",
  providerProgramList: "All programs here",
  allPrograms: "See all programs from this provider",
  leadsTo: "Leads to",
  programsForThisJob: "Programs that train for this job",
  notReported: "Not reported",
  notReportedLong: "The provider did not report this, or it was withheld to protect the privacy of a small group.",

  outcomes: "What happened to people who took this",
  completionRate: "Finished the program",
  employmentRate: "Working 6 months later",
  medianEarnings: "Earnings in one quarter after",
  medianEarningsNote:
    "A single quarter of earnings, roughly three months, not a yearly salary. Do not compare it directly with the yearly pay shown for the occupation.",
  peopleServed: "People enrolled",
  peopleExited: "People who left or finished",
  outcomesUnreported: "No outcomes reported for this program",
  outcomesUnreportedBody:
    "About a third of California programs report nothing. That is a fact about the program's reporting, not evidence that it works or does not.",
  /*
   * The other absence, and the reason there are two.
   *
   * 42 of the 1,209 silent California programs filed a count of the people they served. Their
   * pages printed that count and then said "No outcomes reported for this program" directly
   * beneath it, which the number above it contradicts. This says what is actually missing --
   * the three measures, named -- over a record that does exist.
   */
  outcomesNoFigures: "No completion rate, employment rate or earnings figure for this program",
  outcomesNoFiguresBody:
    "The federal record for this program carries a count of people and no figures beside it. That is a fact about the program's reporting, not evidence that it works or does not.",
  basedOn: (n: number) => `Based on ${fmt(n)} people`,
  smallSample: "Small group — treat with caution",

  occupationOutlook: "What California expects of this job",
  medianWage: "Typical pay in California",
  jobOpenings: "Projected openings",
  growth: "Projected change",
  growing: "Growing",
  shrinking: "Shrinking",
  shrinkingWarning:
    "California projects this job will shrink over the next ten years. Fewer openings may mean a harder search.",
  entryEducation: "Usually needs",
  perYear: "per year",
  relatedWork: "Related work",
  relatedWorkNote:
    "Occupations in the same family as this one, ordered by projected openings. Related by how the job classification groups them, not by a claim that the skills transfer.",
  byRegion: "Pay by region",
  region: "Region",

  compareTitle: "Side by side",
  /**
   * Accessible name for the sticky tray, distinct from `compareTitle`. Both used to say
   * "Side by side" — the tray as `role="region"`, the table's `<section>` the same, through
   * `aria-label` — which gave two landmarks on the same page the same accessible name and
   * failed axe's `landmark-unique` once the tray was actually in the DOM to audit (#29; nothing
   * before that rendered the tray and the table together).
   */
  compareTrayLabel: "Programs selected to compare",
  compareMeasure: "Measure",
  compareAdd: "Compare",
  compareCount: (n: number, max: number) => `${n} of ${max} selected to compare`,
  compareOpen: "Compare these",
  compareHide: "Hide comparison",
  compareClear: "Clear all",
  compareRemove: (name: string) => `Remove ${name} from comparison`,
  compareFull: "Comparison is full. Remove one to add another.",
  compareNote:
    "A highlighted cell is the strongest reported figure in that row. Rows where fewer than two programs reported anything are not marked, because being the only one to file a number is not the same as being the best.",
  /**
   * Text alternatives for the `.is-best` mark, read alongside the cell's value rather than
   * relying on font weight and a rule that never reach a screen reader. One per row, because
   * what "best" means differs by row: cost and length compare every program that reported;
   * completion, employment and earnings compare only programs whose outcomes describe
   * themselves, and completion further restricts to programs of comparable length.
   */
  compareBestCost: "Lowest reported cost in this comparison",
  compareBestLength: "Shortest reported length in this comparison",
  compareBestCompletion:
    "Highest reported completion rate in this comparison, among programs of comparable " +
    "length whose outcomes describe themselves",
  compareBestEmployment:
    "Highest reported employment rate in this comparison, among programs whose outcomes " +
    "describe themselves",
  compareBestEarnings:
    "Highest reported earnings in this comparison, among programs whose outcomes describe " +
    "themselves",
  /**
   * Said in the row header when real figures are on screen but none is marked — a tie, or
   * every reporting program disqualified from the ranking. Silence here reads the same as
   * "nobody won"; this says the actual reason is "nothing here stood out."
   */
  compareNoStandout: "No figure in this row stands out as the strongest reported one",
  /**
   * Shown only when the completion row had a mark and length took it away — never over a row
   * nobody reported. The lengths named are the site's own length filter caps, so a reader who
   * has met one has met the other.
   */
  compareCompletionLength:
    "Completion is not marked here: these programs are not the same length. Among California " +
    "programs whose figures describe that program alone, the median share who finished falls " +
    "at every step up in length — 97% at four weeks or less, 91% up to three months, 85% up " +
    "to six, 80% up to a year, and 78% beyond it. A mark would be reporting which of these is " +
    "shortest, not which is best. The rates themselves are unchanged, and completion is still " +
    "marked when the programs being compared run for the same sort of time.",

  vsState: "Typical California program",
  vsStateAbove: "Better than typical",
  vsStateBelow: "Worse than typical",
  ofReporting: (n: number) => `of ${fmt(n)} reporting`,
  benchmarkNote:
    "Compared with the median California program that reported this same measure. Programs reporting nothing are not in the comparison, so this is a comparison among those willing to publish.",

areaNote: (unplaced: number, total: number) =>
      `Regions are California's own labour-market areas. A program joins one only when its ` +
      `city is named in that region's title, so ${fmt(unplaced)} of ${fmt(total)} programs — ` +
      `some of them inside these regions' own counties — belong to no region here. Picking a ` +
      `region hides those programs; it does not place them somewhere else.`,
    unplacedOption: (n: number) => `Not placed in a region (${fmt(n)})`,
    anyCityInArea: "Any city in this region",
    anyCityUnplaced: "Any city with no region",
    areaHidesUnplaced: (n: number) =>
      `${fmt(n)} more programs match this search but are in cities California places in no ` +
      `region. They are not shown here, and they are not somewhere else.`,
    unplacedHeading: "Programs California places in no region",
    unplacedBody:
      "Their cities are not named in any published labour-market area, so no region's pay " +
      "figures are claimed for them. That is a gap in the state's geography rather than a " +
      "judgement about the programs, and it covers cities inside the regions listed above as " +
      "well as cities far from any of them.",
    statUnplaced: (n: number, total: number) =>
      `${fmt(n)} of ${fmt(total)} are in cities California places in no region`,

  onetCredit:
    "This site incorporates information from O*NET Web Services by the U.S. Department of Labor, Employment and Training Administration (USDOL/ETA). O*NET\u00ae is a trademark of USDOL/ETA.",
  aboutData: "Where this comes from",
  snapshot: (d: string) => `Data snapshot: ${d}`,
  viewProgram: "Program details",
  providerSite: "Provider's website",
  providerHomePage: "Provider's home page",
  // Always about what we saw, on a date. Never "this provider's website is down".
  linkUnreachable: (date: string) => `We could not reach this page when we checked on ${date}.`,
  linkSubstituted: (date: string) =>
    `We could not reach the page in the federal record when we checked on ${date}, so this links to the provider's home page instead.`,
  // A lapsed domain is not a closed school — the adult centres behind the largest dead domain
  // in this dataset are open and teaching at a different address. So this says what the
  // address did, tells the reader the one thing that actually helps, and accuses nobody.
  linkForSale: (date: string) =>
    `When we checked on ${date}, this web address served a page offering the domain for sale rather than the provider's site. Searching for the provider by name, or telephoning it, is more likely to reach it.`,
  // Somebody else's live site now answers at the filed address. Three of this dataset's
  // addresses do. The sentence says what the address did and stops there: the school is not
  // accused of anything, and "unrelated" is a statement about the destination, not about them.
  linkRedirectUnrelated: (date: string) =>
    `When we checked on ${date}, this web address led to a different website, unrelated to this provider. Searching for the provider by name, or telephoning it, is more likely to reach it.`,
  // The honest majority case. It admits what we do not know rather than implying the school
  // has gone: an address that now answers from somewhere else is not evidence about a school.
  linkRedirectUnconfirmed: (date: string) =>
    `When we checked on ${date}, this web address sent visitors to a different website, and we could not confirm it is this provider's. Searching for the provider by name, or telephoning it, is more likely to reach it.`,
  backToSearch: "Back to search",
  coverageNote: (pct: number) =>
    `${pct}% of California programs report at least one outcome. The rest are listed with what is known.`,

  // ---- Browse indexes ----
  browseOccupationsTitle: "Every occupation California projects",
  browseOccupationsIntro:
    "California publishes a ten-year projection for every occupation it tracks. All of them are here, grouped by whether the state expects the work to grow or shrink and ordered by the openings it projects.",
  occupationsListed: "Occupations listed",
  // Search runs in the browser, so without JavaScript the box is an affordance that does
  // nothing: the form has no action, and submitting it reloads the page. Browsing does not
  // need JavaScript at all -- every one of the 670 occupation pages and 581 provider pages
  // is a static link in the shipped HTML -- so the honest thing is to say which half works
  // and point at it, rather than leave a reader poking an inert box.
  noScriptSearch:
    "Search needs JavaScript, which is not running here. Browsing does not: every occupation " +
    "and every provider is a plain link on the pages below.",
  noScriptBrowseOccupations: "Browse all occupations",
  noScriptBrowseProviders: "Browse all providers",
  titlesEnglishOnly:
    "Occupation titles use O*NET's published Spanish name where there is one, and stay in " +
    "English where there is not.",
  // The same admission, on the page where a Spanish reader meets the most untranslated text:
  // the program's own name, the description its provider filed, and the occupation titles.
  // The occupation page and the occupations index each say why their English is English; the
  // program page said nothing at all, which left the reader to conclude the translation had
  // simply run out.
  programTextEnglishOnly:
    "Program names and program descriptions appear here in English, because that is the " +
    "only language the federal and state records publish them in. Occupation titles are " +
    "translated where O*NET publishes a Spanish name. Everything else on this page is " +
    "translated.",
  occupationColumn: "Occupation",
  programsHere: "Programs listed here",
  onThisPage: "On this page",
  jumpToOutlook: "Jump to a section of this list",
  sortedByOpenings:
    "Ordered by projected openings, most first. An occupation with no published figure goes last rather than being counted as none.",
  bandShrinking: "Work California expects less of",
  bandShrinkingNote:
    "The state projects fewer of these jobs over the next ten years. Training for one is not a mistake, but it is a decision worth making with the number in front of you.",
  bandSteady: "Work with no projected change",
  bandSteadyNote:
    "The state projects the same number of these jobs in ten years as there are today.",
  bandGrowing: "Work California expects more of",
  bandGrowingNote:
    "The state projects growth here. That says nothing about the pay, and nothing about whether any particular program prepares you for the work.",
  bandUnknown: "Work with no projection published",
  bandUnknownNote:
    "The state published no projected change for these. That is missing information, not a projection of zero.",

  browseProvidersTitle: "Every training provider",
  browseProvidersIntro:
    "Every school, college, and training organisation with at least one California program in this dataset, listed alphabetically with how much of its own record it publishes.",
  browseProvidersDerived:
    "The federal providers index carries no California rows, so this roster is rebuilt from the programs themselves. Spellings that differ only in capitalisation or punctuation are merged into one entry.",
  jumpToLetter: "Jump to providers by first letter",
  otherLetter: "0–9 and other",
  citiesColumn: "Cities",
  moreCities: (n: number) => `+${fmt(n)} more`,
  reportingRatio: (n: number, total: number) => `${fmt(n)} of ${fmt(total)}`,
  providersListed: "Providers listed",
  programsListed: "Programs across them",
  providersReportingSome: "Publish at least one outcome",

  browseAllOccupations: "Browse all occupations",
  browseAllProviders: "Browse all providers",

  // ---- Site chrome ----
  navLabel: "Main navigation",
  navOccupations: "Occupations",
  navProviders: "Providers",

  /*
   * Qualifier on the language toggle, shown only while the toggle still points at the other
   * language's home page rather than at this page in the other language.
   *
   * A layout is never told the path it is rendering, so the server-rendered href can only be
   * `/es/`. With JavaScript an inline script rewrites it to the equivalent URL and hides this
   * word. Without JavaScript the word stays, and the link says where it actually goes.
   * Written in the language of the link it qualifies, which is the language it is attached to.
   */
  langSwitchHome: "home",

  // Shown at the site root, where a visitor arriving from a search engine has been told
  // nothing yet. Two sentences: what it costs them, and what the numbers are.
  siteSummary:
    "Free to use, with no account. Every figure comes from public federal and state records, and a program that reported nothing is shown as having reported nothing.",

  // ---- What a search engine shows ----
  //
  // Titles and descriptions for the roughly nine thousand pages a search engine can reach.
  // For most people this is the first thing they read and often the only thing, so it is
  // written to be scanned in the second it gets: the provider's name, the city, and what the
  // page will actually tell them. "Afterward" appears in none of them — the site's own name is
  // the one piece of information a stranger scanning results cannot use.
  //
  // Per-language for the same reason every other string here is. A Spanish result that reads
  // in English tells a Spanish speaker the page is not for them, before they can find out
  // that it is.
  metaProgramTitle: (program: string, place: string) =>
    place ? `${program} at ${place}` : program,
  metaProgramReported: (place: string) =>
    `${place}. Cost, length, and the outcomes this program reported: completion, employment six months on, and earnings.`,
  // A program that filed nothing is a real finding, and putting it in the search result saves
  // a click. It is worded so it cannot be read as a bad result: nothing was filed.
  metaProgramUnreported: (place: string) =>
    `${place}. Cost and length. This program reported no outcomes, which is not evidence that it performs badly.`,

  metaProviderTitle: (name: string, programs: number, place: string) =>
    `${name} — ${programs === 1 ? "1 training program" : `${fmt(programs)} training programs`} in ${place}`,
  metaProviderCities: (n: number) => `${fmt(n)} California cities`,
  metaProviderDescription: (reporting: number, total: number) =>
    `${fmt(reporting)} of ${fmt(total)} programs here report what happened to their students. Cost, length and reported outcomes for every one, from public records.`,

  metaOccupationTitle: (title: string) =>
    `${title} in California — pay, job outlook and training programs`,
  // Six occupations — Actors, Dancers, Musicians and Singers among them — have no published
  // wage statewide and none in any region either. Promising "pay" in their title would be a
  // wrong result before the page even loads, so the word is dropped rather than qualified.
  metaOccupationTitleNoPay: (title: string) =>
    `${title} in California — job outlook and training programs`,
  metaOccupationWage: (wage: string) =>
    `California projects this work over ten years and publishes a median of ${wage} a year. Every training program here that trains for it is listed.`,
  // Never "$0", and never silence either: the absence of a published wage is itself the fact,
  // and it is stated as the statewide absence it is — several of these occupations do have a
  // published wage in some of their regions.
  metaOccupationNoWage:
    "California publishes no statewide median pay for this work. Its ten-year projection, the regions it does publish figures for, and every program here that trains for it are listed.",

  // ---- Page not found ----
  notFoundTitle: "This page does not exist",
  notFoundBody:
    "The address may be mistyped, or it may point at a program or a provider that is not in the federal file this site is built from. Nothing here sits behind an account, so everything the site has is reachable from these three pages.",
  notFoundSearch: "Search every California training program",

  // ---- Federal occupation detail (CareerOneStop / O*NET, PROVENANCE D6) ----
  // The data behind these sections is English only at the source, so each note says whose
  // words they are and which language they were published in, rather than leaving a Spanish
  // reader to guess why a paragraph is in English.
  occupationDescriptionNote:
    "How the U.S. Department of Labor describes this work. Published in English only.",
  occupationDescriptionNoteEs:
    "How the U.S. Department of Labor describes this work, in the Department's own Spanish.",
  wageSpreadHeading: "What the pay actually ranges across",
  wageSpreadNote: (year: number): string =>
    `A median is one point. These are the federal Bureau of Labor Statistics' ${year} figures for California, and they say how far apart the people doing this job actually are. Read them as the spread across everyone already in the work — not as a starting wage and not as a promise about where anyone lands.`,
  localRangeHeading: (area: string): string => `What this pays in ${area}`,
  localRangeStatewide: "Across California",
  localRangeAreaColumn: "Area",
  wageChartKey:
    "Each bar runs from the lowest-paid tenth to the highest-paid tenth. The darker middle is where half the people are, and the line is the median.",
  localRangeNote: (area: string, year: number): string =>
    `The federal Bureau of Labor Statistics' ${year} figures for ${area} beside the same figures for the whole state. A region can sit well below or above the statewide spread, and the statewide number is the one most often quoted — so where they differ, the local row is the one that describes the work near this program.`,
  wageP10: "The lowest-paid tenth earn under",
  wageP25: "A quarter earn under",
  wageP50: "Half earn under",
  wageP75: "Three quarters earn under",
  wageP90: "The highest-paid tenth earn over",

  skillsHeading: "Skills this work uses most",
  skillsNote:
    "O*NET, the U.S. Department of Labor's occupation database, rates how important each of these is to this work, and they are listed in that order, most important first. The ratings themselves are not shown, because the data carries the number without the scale it was measured on. The names are as published, in English.",
  skillsUnrated: (names: string) =>
    `O*NET lists these as well but rated none of them, so they are left out of the order rather than placed at the bottom of it: ${names}.`,

  brightOutlookLabel: "Bright Outlook — a U.S. Department of Labor designation",
  brightOutlookNote:
    "The Department's own designation, made from its national projections. It is not this project's assessment and it is not California's: every other figure on this page comes from California's projection, which can point the other way and for some occupations does.",
  // The designation's categories are descriptive phrases and are translated on the same
  // terms as every other controlled vocabulary in the data. "Bright Outlook" is the name of
  // the federal designation itself and stays in English in both languages.
  outlookRapidGrowth: "Rapid Growth",
  outlookManyOpenings: "Numerous Job Openings",

  similarWork: "Similar work",
  similarWorkNote:
    "O*NET, the U.S. Department of Labor's occupation database, names these as occupations involving work similar to this one — its own reading of the job, not a grouping by code. They keep O*NET's order, and only those California publishes a projection for are shown.",

  // ---- Figures borrowed from a wider occupation ----
  // California publishes no estimate for some occupations and reports that work only inside a
  // larger one. Those programs used to show the larger occupation's numbers with nothing said
  // about it. These strings say it, in the reader's own terms: the numbers are real, they are
  // California's, and they are about more jobs than the one this program teaches.
  aggregateHeading: "These figures describe a wider group of jobs",
  // A table puts one program's outcome figures directly beside another's, which is exactly
  // the reading the cohort flag exists to prevent for the rows that did not file their own.
  // Marked per row, because which rows are affected is the whole point, and explained once
  // beneath the table rather than repeated down thirty-two of thirty-five rows.
  cohortMarkerLabel: "Covers more than this program",
  cohortTableNote:
    "Rows marked \u2020 carry figures the provider filed against more than the program named \u2014 " +
    "several of its programs, or the whole institution. They are shown because they are real. " +
    "They cannot be read against the rows beside them, because they do not describe one course.",
  aggregateBroadGroup: (group: string, codes: string) =>
    `California publishes no separate pay or openings figures for the occupation this program trains for (${codes}). It reports that work only inside ${group}, the larger category the occupation classification files it under, so the pay, openings and projected change below belong to that whole category. Read them as the range this job sits inside, not as a figure for the job itself.`,
  aggregateHybrid: (group: string, codes: string) =>
    `California publishes no separate pay or openings figures for the occupation this program trains for (${codes}). The federal classification it follows counts that work together with several related jobs under ${group}, because they cannot be measured apart, so the pay, openings and projected change below belong to the combined group. Read them as the range this job sits inside, not as a figure for the job itself.`,
  unnamedOccupation: "the occupation California reports it under",
  entryEducationWithheld: "Not shown for this program",
  entryEducationWithheldNote: (group: string) =>
    `California does publish a usual entry requirement for ${group}, but it is one answer for the whole group and can name a degree this program's own occupation never asks for. It is left out here rather than shown beside a program it may not describe. That is this site's decision, not something the provider failed to report.`,

  // ---- Methodology ----
  methodologyLink: "How this site gets its figures, and what they do not tell you",
  aboutTitle: "About these figures",
  aboutLede:
    "This site publishes performance figures about named California training providers, in public, and puts them side by side. That is worth doing, and it is worth being exact about what the numbers are. Everything below describes where each figure comes from, who produced it, what it leaves out, and what to do if you think it misrepresents you.",
  aboutIndependence:
    "Afterward is an independent, non-commercial project. It is not affiliated with, endorsed by, or operated by the State of California, the California Employment Development Department, any California workforce development board, or the U.S. Department of Labor. It uses California's open-source design system, which is why these pages resemble official state websites. They are not official ones.",
  aboutProgramsCounted: "Programs described here",
  aboutProvidersNamed: "Providers named here",
  aboutProgramsReporting: "Programs that report any outcome",

  aboutSourcesHeading: "Where every figure comes from",
  aboutSourcesBody:
    "Nothing here is original research, nothing is estimated by this project, and nothing is a prediction of its own. Every number on the site is copied from one of three public records and can be traced back to it.",
  aboutSourceProgramsLabel: "Programs, providers, cost, length and outcomes",
  aboutSourceProgramsBody:
    "The U.S. Department of Labor's Eligible Training Provider performance report (ETA-9171), which states file under the Workforce Innovation and Opportunity Act and the Department is required to publish. It is the source of every provider name, price, length, and every measure of what happened to the people who enrolled.",
  aboutSourceOccupationsLabel: "Pay, projected openings and job outlook",
  aboutSourceOccupationsBody:
    "California's Employment Development Department: its long-term occupational employment projections for 2024 to 2034, and its wage statistics where the projections carry no wage. These are the state's own ten-year estimates for an occupation, statewide and for the areas it names.",
  aboutSourceFederalLabel: "Job descriptions and skills",
  aboutSourceFederalBody:
    "CareerOneStop, the U.S. Department of Labor service that publishes O*NET's occupation content, in English. Where the Department also publishes the occupation in Spanish through its Mi Próximo Paso service — 600 of California's 670 — the Spanish page uses the Department's own Spanish name and description. The other 70 keep the English name, and nothing on this site is machine-translated.",
  aboutSourceWagesLabel: "What an occupation pays across its range",
  aboutSourceWagesBody:
    "The Bureau of Labor Statistics' Occupational Employment and Wage Statistics for California, published by EDD. It gives the 10th, 25th, 50th, 75th and 90th percentiles, which is how an occupation page can show the spread rather than the median alone. Each percentile can be withheld separately, and a withheld one is left blank rather than estimated from the ones on either side of it.",
  aboutSourcesDates:
    "Each source, its licence, and the date it was read are recorded in the project's public provenance file, and the whole dataset can be rebuilt from those sources by anyone.",
  aboutProvenanceLink: "Read the provenance file",

  aboutSelfReportedHeading: "The outcomes are self-reported, and this site does not check them",
  aboutSelfReportedBody:
    "Completion, employment and earnings are reported by each training provider to California, and by California to the federal government. This project reproduces what was filed. It does not audit it, cannot confirm it, and has no way to tell a carefully compiled figure from a careless one. A number here is evidence of what a provider reported, not proof of what happened.",
  aboutSelfReportedSecond:
    "This matters most in the direction people do not expect. The measures are not adjusted for who a program enrols. A program that takes people furthest from work will tend to report lower employment and lower earnings than one that enrols people already close to a job, and nothing in this data separates the two.",

  aboutMissingHeading: "What a blank means",
  aboutMissingBody:
    "A missing value here means not reported or withheld. It never means zero, and it is never rendered as one. Under federal rules, results for small groups are suppressed so that individual participants cannot be identified, so a blank can equally be a program too small to publish safely as one that filed nothing at all.",
  aboutMissingSecond: (reporting: string, total: string) =>
    `Roughly a third of California's programs report nothing whatsoever: ${reporting} of ${total} publish at least one measure. That is a large enough share that hiding it would distort the whole site, so a program that reported nothing is listed with everything else and says so plainly. Absence of data is not evidence that a program performs badly, and this interface is built to keep those two ideas apart.`,

  aboutQuarterHeading: "The earnings figure covers three months, not a year",
  aboutQuarterBody:
    "Median earnings under this federal measure are earnings in the second quarter after someone left the program — a single quarter, roughly three months. It is not an annual salary and it is not a starting wage. It sits on the same page as an occupation's typical yearly pay, which is a different measure from a different source over a different period, and the two must not be read against each other.",

  aboutComparisonsHeading: "What the comparisons claim, and what they do not",
  aboutComparisonsBody:
    "A rate on its own is unreadable: nobody knows whether 45% employed is good. So where a program reports a measure, it is shown against the median California program that reported the same measure. Programs that reported nothing are not in that median, which makes it a comparison among those willing to publish rather than a comparison against the state as a whole.",
  aboutComparisonsSecond:
    "This site once labelled programs “better” or “worse” than typical against that median. It no longer does. The median pooled every reporting program regardless of length, and a four-week certificate and a two-year pathway are not comparable on completion — measured against programs of their own length, that label was simply inverted for about one program in ten. The figures and the median are still shown; the conclusion is yours to draw, because the comparison could not carry it. Where two programs are placed side by side, the marked cell is the strongest reported figure in that row; a row where fewer than two programs reported anything is left unmarked, because being the only one to file a number is not the same as being the best. Completion is marked only when the programs run for the same sort of time, because the confounding that withdrew the label arrives there two programs at a time: the median share who finished falls from 97% at four weeks or less to 78% beyond a year, so a mark across lengths marks the shorter course.",
  aboutComparisonsThird:
    "No comparison is ever built out of a blank. A program that reported nothing is never called below average, because there is nothing to compare and saying so would be an accusation rather than a fact.",

  aboutAggregateHeading: "When an occupation figure describes more jobs than one",
  aboutAggregateBody: (aggregate: string) =>
    `California does not publish an estimate for every occupation. For some, the state reports the work only inside a larger occupation — the category above it, or a bucket the federal statistics use for jobs they cannot measure separately. Rather than leave those programs with no occupation figures at all, this site shows the larger occupation's and says so on the page, naming the wider occupation and the program's own occupation code. That applies to ${aggregate} of the program pages here.`,
  aboutAggregateSecond:
    "One figure is deliberately dropped in that case instead of borrowed: the usual entry requirement. A median wage over a wider population is still an approximation of something a trainee belongs to. A credential is not — it is one answer assigned to the whole group, and on a group that mixes a master's-level occupation with a community-college certificate it is not approximate, it is wrong. Telling someone they need a degree they do not need, for the job they are training for right now, is the same class of error as printing a suppressed number as zero.",

  aboutLimitsHeading: "Known limitations",
  aboutLimitsBody:
    "These are the things this site gets wrong or cannot yet do. They are listed here rather than discovered later.",
  aboutLimitTranslation:
    "Program names, descriptions and provider names appear in English on Spanish pages, because the federal and state feeds publish that text only in English. Occupation titles are different: the Department publishes a Spanish name for 600 of California's 670 occupations, and the Spanish page uses it; the other 70 keep the English title. Nothing on this site is machine-translated.",
  aboutLimitEtpl:
    "The programs here are the ones California filed federally. Whether the state's own eligible training provider list carries programs the federal file omits is unresolved, because California publishes no bulk export of it. A program missing from this site is not necessarily a program that does not exist.",
  aboutLimitUnmatched: (unmatched: string) =>
    `${unmatched} programs show no occupation figures at all. California publishes no projection for the occupation they are tagged with, and no nearby occupation is substituted, because a similar-sounding job with a different wage would look exactly like a correct answer.`,
  aboutLimitArea: (unplaced: string) =>
    `${unplaced} programs show no regional pay figure. Their city is not one of the metropolitan or rural areas California names when it publishes wages, and a neighbouring area's numbers are not borrowed to fill the gap.`,
  aboutLimitUrl: (noUrl: string) =>
    `${noUrl} programs have no working website link. Most never filed one, and a handful filed something that was not a web address at all, which is dropped rather than turned into a link.`,
  aboutLimitProjections:
    "Occupation projections are the state's ten-year estimates, not guarantees. A job California expects to grow may not, and a job it expects to shrink may still be the right choice for a particular person in a particular place.",
  aboutLimitSnapshot: (date: string) =>
    `Everything here is a snapshot taken on ${date}. The federal file is refreshed on a quarterly cadence, so a figure corrected upstream since that date is not corrected here yet.`,

  aboutCorrectionsHeading: "If a figure here misrepresents you",
  aboutCorrectionsBody:
    "This site names real organisations and publishes numbers about them, so there has to be a way to say it got something wrong. Please open an issue on the project's public repository, naming the program and the figure you are disputing.",
  aboutCorrectionsSecond:
    "Two outcomes are possible and they are worth telling apart. Where the error is this project's — a bad join, a mislabelled measure, a program attached to the wrong occupation — it will be fixed, and the correction is not conditional on who asks. Where the underlying public record is wrong, the correction has to go through the body that published it, since this site reproduces that record and cannot quietly diverge from it; the issue thread is a reasonable place to note that a correction is in progress, and that note will be honoured here.",
  aboutCorrectionsLink: "Open an issue about a figure on this site",

  aboutAdviceHeading: "This is not advice",
  aboutAdviceBody:
    "Nothing here is financial, legal, educational, or career advice. Enrolling in a training program is a serious financial and personal commitment. Use this as one input among several, and talk to the provider, to your local America's Job Center, or to a career counsellor before you decide.",

  // ---- What the work actually is (program page) ----
  //
  // A program page used to open on cost, length and enrolment counts: three numbers about a
  // purchase, before a word about what the purchase is for. Someone arriving from a search
  // engine is asking one question first — what is this job, and is it for me — and the page
  // had no answer to it beyond a paragraph of federal course-catalogue prose at the bottom.
  //
  // These strings carry that answer. They are written for someone deciding whether to spend a
  // year and several thousand dollars, and they assume no college: short sentences, ordinary
  // verbs, and every caveat stated rather than implied.
  workHeading: "What this work is",
  workNote:
    "This describes the jobs people do, not the classes this program teaches. It comes from the U.S. Department of Labor, which asks people already doing the work. The Department publishes it in English only, so the job names and the sentences below stay in English on this page.",
  alsoCalled: "Job ads may call this:",
  tasksNote:
    "Some of what people in this job do. The Department rates how important each one is, and they appear in that order.",
  moreTasks: (n: number) => `Show ${fmt(n)} more things this job involves`,
  // 89 of the 670 occupations have no task list at all, and 77 of those still have the
  // Department's one-paragraph account of the work. Falling back to it keeps the page an
  // explanation rather than a gap, and says which of the two the reader is looking at.
  workDescriptionOnly:
    "The Department publishes no list of daily tasks for this job. This is how it describes the work instead.",
  // The remaining 12. They are the federal publication buckets, which have no O*NET profile
  // to read, so the honest thing is to name the gap rather than leave a heading over nothing.
  workNothing:
    "The Department publishes no description and no task list for this job. That is a gap in the federal record, not a sign that the work is unusual.",

  costHeading: "What it costs and how long it takes",
  payHeading: "What the job pays, and who gets hired",

  // ---- Getting in ----
  //
  // "Will finishing this actually get me in?" is a different question from "what credential
  // does it award", and 25 California occupations answer it with five years of prior work.
  // Someone should meet that before they pay, not after.
  entryHeading: "Getting in",
  entryExperience: "Experience needed first",
  entryTraining: "Training after you are hired",
  expNone: "None",
  expUnder5: "Under 5 years in a related job",
  expOver5: "5 years or more in a related job",
  ojtNone: "None",
  ojtUnderMonth: "Under a month",
  ojtToYear: "1 to 12 months",
  ojtOverYear: "More than a year",
  ojtInternship: "An internship or residency",
  ojtApprenticeship: "An apprenticeship",
  entryWarnExperience:
    "Most people hired for this job have already spent 5 years or more in a related one. Finishing this program may not be enough on its own. Ask the provider who hires their graduates, and what those people did before.",
  entryNoteExperience:
    "Employers usually expect some time in a related job as well as the training. Ask the provider what their graduates did before they were hired.",
  entryNoteApprenticeship:
    "People usually enter this job through an apprenticeship rather than from a classroom course alone. Ask the provider whether this program leads to one.",
  entryNoteInternship:
    "People usually enter this job through an internship or a residency rather than from a classroom course alone. Ask the provider whether this program leads to one.",
  entryNoteLongTraining:
    "New hires are trained on the job for more than a year after they start. The classroom part is the beginning of this work, not the whole of it.",
  entryNoteDirect:
    "No earlier job experience is expected, and new hires are not put through a long training period. For work like this, a program is usually the way in.",
  entrySource:
    "These are the federal government's answers for the occupation, not rules this provider sets. California publishes the same two answers for every one of these jobs.",

  // ---- What people in this job actually studied ----
  //
  /* ---- Someone else may be able to pay for this ------------------------------------------
   *
   * Every program on this site was on California's Eligible Training Provider List when the
   * state last reported it, and under 20 CFR 680.410 that listing is what allows an Individual
   * Training Account to pay a provider for somebody's training. The site never said so, and a
   * reader who could have had a program paid for had no way to find that out here.
   *
   * The English below is not written here. Every string from `fundingLede` to the last
   * `fundingWhy…` is copied byte for byte from `afterward.sources.local_help`, where each sentence
   * sits beside the regulation it rests on and is scanned by a test that refuses promissory
   * phrasing — "you qualify", "guarantee", "free training", "at no cost to you". A Python test
   * asserts that what is published here is still what that module says, so editing one of these
   * strings in place moves it out from under the check that exists to stop this feature telling
   * somebody they will be funded. Edit the module; regenerate; translate.
   *
   * The Spanish is written here, and it is the highest-risk text on this site. A hedge that
   * survives in English and evaporates in Spanish turns a description of a public program into a
   * promise, for the readers least able to absorb the cost of a wasted trip.
   * -------------------------------------------------------------------------------------- */
  fundingLede: (date: string) =>
    `This program was on California's Eligible Training Provider List when the state last reported it to the U.S. Department of Labor (${date}). Programs on that list can be paid for through an Individual Training Account. Listings are renewed periodically and can lapse, so a program listed when the state last reported may not be listed today. Ask before you rely on it.`,
  fundingHeading: "Someone else may be able to pay for this",
  fundingIta: "Federal training money under the Workforce Innovation and Opportunity Act is paid through an Individual Training Account: an agreement between a local workforce board and a training provider, set up on behalf of one person. That money can only go to a provider on the state's Eligible Training Provider List, which is the list every program on this site comes from.",
  fundingBeforeHeading: "Ask before you enroll, not after",
  fundingBefore: "The order the rules set out starts at the center rather than at the school. Before a center can find somebody eligible for training services it has to gather enough to decide, at a minimum through an interview, evaluation or assessment and career planning. Referring a person to the provider they have chosen and setting up the account both come after that, and both are the center's to do — the account is a payment agreement with the training provider, and it is the provider that is paid through it. So the call belongs before enrolling and before paying. Anyone who has already done either should still ask, and ask what it means for them.",
  fundingCentersHeading: "The place to ask is an America's Job Center of California",
  fundingCenters: "A comprehensive center is where all the required partner programs can be reached; an affiliate site offers some of them. California's Employment Development Department directs people to CareerOneStop's finder to locate one. Contacting a center before traveling is worth it — the state notes that its own staff are not physically present at every location.",
  fundingWhoCanBeServedHeading: "Who can be served at all",
  fundingWhoCanBeServed: "California states the general criteria as three things: age, Selective Service registration where it applies, and authorization to work in the United States. Work authorization is checked when someone moves into a service that needs it, not at the door — career assessments, an employment plan, case management, basic skills and English instruction, help finishing work-authorization paperwork, and referrals for transport, childcare, food and housing are all listed as services a local area may deliver without verifying it first.",
  fundingInterviewHeading: "Expect an interview, not a form",
  fundingInterview: "Before anyone can be found eligible for training services they must receive an interview, evaluation or assessment and career planning, or something else that gives the center enough information to decide. There is no federally required waiting period, but there is no way to skip the conversation either — which is why this site cannot tell anyone whether they qualify.",
  fundingDecidesHeading: "What the center is deciding",
  fundingDecides: "Training services may be made available to adults and dislocated workers whom the center determines are unlikely or unable to obtain employment leading to self-sufficiency through career services alone, need training to get there, and have the skills and qualifications to succeed in it. The program also has to be linked to employment opportunities in the local area, or somewhere the person is willing to commute or move to.",
  fundingPriorityHeading: "Say if you receive public assistance, are low income, or need basic skills help",
  fundingPriority: "For the adult funding stream, federal law requires priority to be given to recipients of public assistance, other low-income individuals, and individuals who are basic skills deficient. California instructs job center staff to work an explicit order: veterans and eligible spouses who are also in one of those groups, then the groups themselves, then other veterans and eligible spouses, then any populations the Governor or the local board has added, then everyone else. Priority does not exclude anyone else, and it does not apply to the dislocated worker stream. It only operates if the center is told, and California fixes a person's priority status at the moment eligibility is determined — so it is the first appointment that counts.",
  fundingOtherFundingHeading: "Bring what you already have — this money fills a gap",
  fundingOtherFunding: "WIOA training funding is limited to people who cannot get grant assistance from other sources, or who need help beyond what those sources cover. Centers must consider Pell Grants, state training funds and assistance for needy families first. Someone can enrol while a Pell application is still pending, if the center arranges it with the provider in advance.",
  fundingSupportHeading: "Ask what else can be covered while you train",
  fundingSupport: "Supportive services — help with transport, child care and dependent care, and others — may be provided to people taking part in career or training services who cannot obtain them elsewhere. Adults who are unemployed, do not qualify for unemployment compensation, and are enrolled in training may be eligible for needs-related payments as well.",
  fundingLocalHeading: "The answer depends on the local area, and on the year",
  fundingLocal: "Once someone has been found eligible and has chosen a provider, the center must refer them and set up an account — unless the program has exhausted its training funds for the program year. How much an account is worth, which occupations a board will fund, what counts as employment that supports a person, and how priority is applied are all set locally, across California's 45 local workforce development areas. Meeting every rule here still does not secure a place. California's own guidance to job center staff says so plainly: WIOA is not an entitlement program, funding for it is not unlimited, and local boards offer services to eligible applicants when funding is available.",
  fundingWhoDecides: "Whether a person can have a program paid for is decided by their local workforce development board and the America's Job Center staff who interview them — not by this site, and not by the training provider. California has 45 local workforce development areas and each sets its own policies, so the answer can differ between two people in neighboring counties. Nothing here is a promise of funding or a determination of eligibility.",
  fundingAskEtplNow: "Is this program on California's Eligible Training Provider List right now?",
  fundingWhyEtplNow: "An Individual Training Account can only pay a provider on that list, and listings are granted per program rather than per school — a listed provider can have unlisted programs. Eligibility is also time-limited and renewed.",
  fundingAskFullPrice: "What does the price include, and what will I still have to buy — books, tools, uniforms, exam fees, license fees?",
  fundingWhyFullPrice: "Providers report tuition and supplies to the state as separate figures and either can be missing, so the cost shown here may be a floor rather than a total. Exam and licensing fees are often outside both.",
  fundingAskCredential: "What exactly do I hold at the end, who issues it, and does an employer or a licensing board recognize it?",
  fundingWhyCredential: "A program on the list has to lead to a credential, employment, or measurable progress toward one — but 'certificate of completion' from a school and a license a state board recognizes are very different things to be holding.",
  fundingAskWithdrawal: "If I stop partway through, what do I owe, and what happens to funding already paid?",
  fundingWhyWithdrawal: "An Individual Training Account is a payment agreement with the provider and may be paid in instalments, so who is owed what on a withdrawal is a question for the provider and the center together, before enrolling rather than after.",
  fundingAskSchedule: "When does the next cohort start, and how many hours a week is it?",
  fundingWhySchedule: "The schedule decides whether someone can keep working while training, and needs-related payments are only for people who are unemployed and already enrolled — so the timetable and the money question are the same question.",
  fundingAskFundingStream: "Which funding stream would I be served under — adult, dislocated worker, or youth?",
  fundingWhyFundingStream: "They are different pots with different rules. The statutory priority for public assistance recipients, low-income individuals and people who are basic skills deficient applies to adult funds only. Out-of-school youth aged 16 to 24 can be served by Individual Training Accounts from youth funds.",
  fundingAskLocalDemand: "Is this occupation one this local area funds training for?",
  fundingWhyLocalDemand: "The program has to be linked to employment opportunities in the local area or one the person will commute to, and boards give priority to credentials aligned with in-demand sectors. A program can be on the state list and still not be one a particular board will pay for.",
  fundingAskItaCap: "What is the most this area will put into an Individual Training Account, and would that cover this program?",
  fundingWhyItaCap: "Caps and duration limits are local policy, not federal, so the same program can be fully funded in one county and partly funded in the next. A cap is also not necessarily the end of it: the rules allow someone to choose training that costs more than the maximum when other funds are available to make up the difference. Ask what the gap would be and what could close it.",
  fundingAskSelfSufficiency: "How does this area define employment that supports a person?",
  fundingWhySelfSufficiency: "The determination turns on whether someone can reach self-sufficiency without training, and California requires each local board to set that threshold itself — at least the lower living standard income level for the area, and often higher. It is a local number, and it is the number the decision rests on.",
  fundingAskOutOfArea: "Can I use this for a program in another county, or another state?",
  fundingWhyOutOfArea: "Training outside the local area is allowed where the program is on the state list, and outside California where state and local policies permit — both subject to local procedure. Worth asking anywhere the nearest program is a long drive, which in this state is a lot of places.",
  fundingAskFundsLeft: "Are there training funds left for this program year?",
  fundingWhyFundsLeft: "The obligation to refer an eligible person and set up an account holds unless the program has exhausted its training funds for the year. That is the one answer a website can never know, and it decides everything.",
  fundingAskOtherGrantsFirst: "What should I apply for first — a Pell Grant, or anything else?",
  fundingWhyOtherGrantsFirst: "WIOA funds are for people who cannot get grant assistance elsewhere or who need more than it covers, and centers must consider other sources first. Enrolling with a Pell application pending is allowed if arranged in advance.",
  fundingAskSupportCosts: "Can you help with transport, child care, or living costs while I train?",
  fundingWhySupportCosts: "Supportive services and needs-related payments are separate from tuition, and are only available to people already taking part in career or training services who cannot get that help anywhere else. They are worth asking about in the same conversation, not a later one.",
  fundingAskWhatToBring: "What should I bring, and how long does a determination take?",
  fundingWhyWhatToBring: "The determination rests on an interview, evaluation or assessment and career planning, and the center has to be able to document it. There is no federal minimum waiting period, so the answer is local and worth knowing before taking a day off work.",

  // The block's own furniture: labels, and the three sentences that describe what this site did
  // rather than what a rule says. Not from the module, because they are claims about this
  // dataset — what it looked for, what it found, and what it never checked.
  fundingCentersNone: (miles: number) =>
    `No America's Job Center is within about ${miles} miles of this program's city. The ` +
    `finder below searches the whole state.`,
  /**
   * Said above the offices on the 32 program pages with none inside the radius, so a reader
   * is not left to infer from a number that this site calls 27 miles nearby. What it
   * replaced was a link to a statewide finder — a search box rather than an office — on the
   * pages whose readers have the furthest to go.
   */
  fundingCentersBeyondIntro: (miles: number) =>
    `No America's Job Center is within about ${miles} miles of this program's city. These ` +
    `are the nearest ones anyway — further out, and worth a phone call before a journey:`,
  fundingCentersNotChecked:
    "This site has not established which offices are nearest to this program. The finder below searches the whole state.",
  fundingDistanceNote:
    "Distances are straight-line, so the drive is longer. Call before you travel: opening hours here are as the federal directory published them, and the state notes its own staff are not present at every location.",
  /**
   * The two labels on the office cards are federal terms of art, and on this page they had
   * nothing next to them saying what they mean. The claim and the regulations behind it are
   * `where_to_ask` in `local_help`, which the guide page prints in full with its citations.
   */
  fundingCenterTypes:
    "At a comprehensive center all the required partner programs can be reached; an affiliate site offers some of them.",
  /**
   * The accessible name of a phone link. Three offices on one page publish three bare
   * numbers, and a screen reader announcing "link, 619-319-9675" three times says nothing
   * about which office is being called. WCAG 2.2 AAA 2.4.9 asks that a link's purpose be
   * clear from the link alone. The visible number stays inside the name, so the spoken label
   * still contains the written one.
   */
  fundingCallLabel: (center: string, phone: string) => `Call ${center} at ${phone}`,
  fundingFindersIntro: "Find a center anywhere in California, and check what is on the list today:",
  fundingEnglishSources:
    "The rules cited here, and the state and federal sites linked to, are published in English.",
  fundingComprehensive: "Comprehensive center",
  fundingAffiliate: "Affiliate site",
  fundingPhone: "Phone",
  fundingHours: "Hours",
  fundingMilesAway: (miles: number) => `about ${miles} miles away`,
  fundingVeteransRep: "Has a veterans' representative",
  fundingClosed: "The directory records this office as temporarily closed",
  jobsHeading: (n: number): string =>
    n === 1 ? "The job this trains for" : "The jobs this trains for",
  jobDetail: "Pay, hiring, and what people studied",
  fundingGuideTitle: "Paying for training in California",
  fundingGuideIntro:
    "Federal and state money can pay for training for people who qualify. None of it is decided on this site, and nothing here is a promise that a particular person will be funded. What follows is what the public rules say, who decides, and what to ask them.",
  fundingGuideLink: "How this gets paid for, and what to ask",
  navPaying: "Paying for it",
  filterLabel: "Filter this list",
  filterPlaceholder: "Type a job or provider name",
  filterShowing: (shown: number, total: number): string =>
    `Showing ${shown.toLocaleString("en-US")} of ${total.toLocaleString("en-US")}`,
  filterNoMatches: "Nothing here matches that. Try fewer letters, or a word from the middle of the name.",
  alternativesHeading: "Related work California expects more of",
  alternativesNote:
    "The U.S. Department of Labor lists these as related to the job above, and California projects growth in them rather than decline. Related is not the same as interchangeable: the training, the licences and the pay can all differ, and this program does not train for these. It is a place to start asking, not a recommendation.",
  alternativesPrograms: (n: number): string =>
    n === 1 ? "1 program here" : `${n.toLocaleString("en-US")} programs here`,
  alternativesNoPrograms: "No programs here train for it",
  saveProgram: "Save",
  savedProgram: "Saved",
  savedCount: (n: number): string => (n === 1 ? "1 saved program" : `${n} saved programs`),
  savedShow: "Show only saved",
  savedShowAll: "Show all results",
  savedClear: "Clear saved",
  savedFull: "You can save up to 20 programs. Remove one to save another.",
  savedWhere: "Saved on this device only. Nothing is sent anywhere, and clearing your browser data clears this.",
  shareSaved: "Copy a link to these",
  sharedListTitle: "Someone shared these programs with you",
  sharedListBody: (n: number): string =>
    n === 1
      ? "One program, from someone else's list. Nothing is saved on this device unless you save it."
      : `${n} programs, from someone else's list. Nothing is saved on this device unless you save them.`,
  sharedListDropped: (n: number): string =>
    n === 1
      ? "One program in that link is no longer in the state's data and is not shown."
      : `${n} programs in that link are no longer in the state's data and are not shown.`,
  sharedListSave: "Save these to my list",
  sharedListExit: "Search all programs instead",
  copyLink: "Copy link to this search",
  copyLinkDone: "Link copied",
  providerCostRange: "Cost range",
  providerCostOne: "Cost",
  providerTrainsFor: "Jobs these programs train for",
  providerNoneReportedTitle: "This provider reported no outcomes",
  providerNoneReportedBody:
    "Nothing is published about how people who took these programs did afterwards. That is a fact about the provider's reporting, not evidence that the training is worse. About a third of California programs are in the same position, and for some the figures were withheld to protect the privacy of a small group.",
  fundingHowSummary: "How this gets paid for, and what to ask",
  fundingQuestionsHeading: "What to ask before you commit",
  fundingQuestionsJobCenter: "Questions for the America's Job Center",
  fundingQuestionsProvider: "Questions for the training provider",
  fundingRuleLabel: "The rule:",
  /**
   * Rendered on Spanish pages only. This section is about money and eligibility, for the
   * readers least able to absorb an error. It has been reviewed by a native Spanish
   * speaker (slegarraga) on 2026-08-06. Saying so
   * is the honest move — but a bare "may contain errors" gives a reader nothing to do, so it
   * names English as the reference text and points at the people who actually decide. It
   * deliberately does not promise that anyone at the center speaks Spanish: the directory's
   * language field was blank for nine of ten centers sampled, so that claim is unsupported.
   */
  fundingTranslationNote:
    "This section was reviewed by a native Spanish speaker (slegarraga) on 2026-08-06, and the English text remains the reference version. If anything here is unclear, ask at the center — they are the ones who decide.",

  /* ---- Outcomes data coverage --------------------------------------------------------
   *
   * This page answers a question nobody publishes an answer to: of the training programs
   * California lists as eligible, how many carry any evidence of what happened to the people
   * who took them? California's own list is a CalJOBS search screen with no download behind
   * it, so the federal scorecard the state files into is the only public record the question
   * can be asked of at all.
   *
   * The copy has one hard constraint, and it is the reason the page can exist without doing
   * harm: it describes records, never conduct. Two of the categories with the most blank
   * cells in California are two of the categories with the most distinct federal reporting
   * obligations, so a sentence that reads as "these providers do not report" would be both
   * unkind and wrong. Every string below is written so that a gap is a finding about data
   * infrastructure, and so that a reader who arrives looking for someone to blame leaves
   * without a candidate.
   *
   * No sentence here states a number. Every figure is interpolated from a count taken over
   * the dataset at build time, so the page corrects itself on a refresh and cannot go stale
   * while continuing to sound precise.
   * ------------------------------------------------------------------------------------ */
  coverageTitle: "How complete California's training outcomes data is",
  /** Link text wherever this page is referenced compactly. Reads on its own, out of context. */
  coverageNavShort: "How complete this data is",
  /* Distinct from the visible "On this page" heading above the list. A nav whose accessible
     name only repeats the heading beside it tells a screen reader user nothing they did not
     already have; this says what pressing something in it will do. */
  coverageJumpLabel: "Jump to a section of this page",
  coverageLede:
    "Every program on California's Eligible Training Provider List is reported to the federal government, and that federal report is where the outcome figures live. This page counts how much of it is filled in: measure by measure, provider category by provider category, and against the size of the group each figure is meant to describe.",
  coverageWhy:
    "California publishes its Eligible Training Provider List only as a search screen inside CalJOBS. There is no file to download, and no published count of how many listed programs carry outcome data. So a person choosing between two programs, and an agency deciding where a reporting effort would do the most good, are both working without that number. The federal scorecard is the same programs under a different cover, and it can be counted, so this page counts it and shows the working.",
  coverageFraming:
    "This measures a public record. It does not assess any provider, college, or agency. A blank cell here is a fact about how workforce data is collected and about which providers are required to file what. It is not evidence that a program is poor, that a provider withheld something it owed, or that anyone failed at anything.",

  // The stamp. It sits beside every figure on the page rather than once at the top, because
  // a coverage number without a date is an invitation to be corrected by someone who knows
  // the scorecard lags, and the correction would be right.
  coverageStamp: (first: string, last: string, date: string) =>
    `Federal ETP Scorecard, program years ${first} to ${last}, read on ${date}.`,
  coverageStampNote: (statedOn: string) =>
    `That program-year window is not in the data. No record the scorecard publishes carries a program-year or reporting-period field of any kind, on either of its indexes. The window comes from a sentence on the scorecard's own About page, read there on ${statedOn}, and the data dictionary published alongside the same data still names an earlier program year, so the source does not agree with itself. A refresh upstream can move the window without anything on this page noticing, which is why the date this project read the record sits beside every figure below.`,

  coverageProgramsCounted: "California programs in the federal record",
  coverageSilentLabel: "Publish no outcome measure at all",
  coverageSilentNoRecordLabel: "Of those, filed no cohort count either",
  coverageHeadlineBody: (silent: string, total: string, withCohort: string, unfiled: string) =>
    `${silent} of ${total} California programs publish no completion rate, no employment rate, and no median earnings figure. Those split two ways that matter. Of them, ${withCohort} filed a count of the people they served, exited, or completed, so a record exists and the outcome cells on it are empty. The remaining ${unfiled} filed no performance figures of any kind, so there is no record to have cells in.`,
  coverageHeadlineSecond:
    "Both are gaps, and they are not the same gap. One is a measure that was not published beside a group that was; the other is a program about which the federal record says nothing. A fix for the first is a reporting rule. A fix for the second is a data pipeline.",

  coverageMeasuresHeading: "What is filled in, measure by measure",
  coverageMeasuresIntro:
    "Every outcome measure the scorecard carries for a program, and how many of California's programs publish each one. Nothing here is derived, combined, or estimated: these are the columns the feed has.",
  coverageMeasureColumn: "Measure",
  coverageReportedColumn: "Published",
  coverageBlankColumn: "Blank beside a filed cohort",
  coverageUnfiledColumn: "No performance record",
  coverageMissingColumn: "Not published",
  coverageMeasureNote:
    "The employment count and the employment rate are separate filings, and the count is not the rate's numerator. The rate is divided by a differently scoped group of leavers that this feed does not publish, so those two rows move independently and neither can be rebuilt from the other.",
  // Rendered only while the separation actually holds. See `reportingRouteSplit`.
  coverageRouteSplit: (providerFloor: string, providerN: string, wageCeiling: string, wageN: string) =>
    `The table divides along a line that has nothing to do with any provider. The counts of who was served, who left, who finished and who earned a credential are the training provider's to supply. The employment and earnings figures are produced by the state, by matching the provider's roster against unemployment-insurance wage records. In this snapshot the two groups do not overlap at all: the least-published measure the provider supplies, ${providerFloor}, is filled in for ${providerN} programs, and the most-published measure the wage match produces, ${wageCeiling}, for ${wageN}. Every measure that has to survive a records match is published less often than every measure that does not.`,
  coverageRouteSplitCaveat:
    "That is a description of the published data, not an explanation of it, and it is not a claim that the match is done badly. It does locate the gap: for most of these programs the reporting relationship exists and is working, and the measures going missing are the ones that depend on two systems finding the same person.",
  coverageMeasureTotalServed: "People served",
  coverageMeasureTotalExited: "People who left the program",
  coverageMeasureTotalCompleted: "People who completed",
  coverageMeasureCompletionRate: "Completion rate",
  coverageMeasureCredentials: "Credentials earned",
  coverageMeasureEmployedQ2: "Employed two quarters after leaving (count)",
  coverageMeasureEmploymentRate: "Employment rate two quarters after leaving",
  coverageMeasureEmployedQ4: "Employed four quarters after leaving (count)",
  coverageMeasureEarnings: "Median earnings in the second quarter after leaving",

  coverageByTypeHeading: "By the category the provider filed under",
  coverageByTypeIntro:
    "The category below is the provider's own, as filed in the federal record. It is not a clean map of California's training system: in this snapshot community colleges appear under both Public and Higher Ed: Associate's Degree, and adult schools, regional occupational programs, and county offices of education all arrive as Public. It is reported as filed rather than re-sorted, because re-sorting it would mean inventing a classification here and then measuring the invention.",
  coverageCategoryColumn: "Category as filed",
  coverageProgramsColumn: "Programs",
  coveragePublishSomeColumn: "Publish at least one measure",
  coveragePublishNoneColumn: "Publish none",
  coverageShareNoneColumn: "Share publishing none",
  coverageEntityUnstated: "No category filed",
  coverageByTypeCaveat:
    "Rows are ordered by how many programs each category holds, not by how much each leaves blank. Ordering by the blank rate would publish a league table of who reports least, and the categories at the top of it would be the ones with the most distinct reporting obligations, which is the opposite of what the numbers show.",

  coverageObligationsHeading: "Not every provider owes the same report",
  coverageObligationsIntro:
    "A blank row is only readable against what its filer was actually required to file, and that is not the same for everyone on the list. Four differences do real work in the tables above, and none of them is a provider choosing to say nothing.",
  coverageObligationRegisteredApprenticeship:
    "Registered apprenticeship programs are on the list on different terms from everybody else. They are eligible by virtue of being registered, for as long as they stay registered, so they never go through the initial eligibility process the other providers go through. They are also not required to submit eligible training provider performance information at all, in so many words, and where they do submit it the submission is voluntary. An apprenticeship program with an empty row is doing exactly what the rule asks of it.",
  coverageObligationCalifornia:
    "California asks everyone else for it. The state's current eligible training provider directive exempts registered apprenticeship from performance reporting and nobody else, including its community colleges and its public universities. Those institutions reach the list by a different route, on their accreditation or their status as public institutions rather than by meeting the numeric performance thresholds the directive applies to private postsecondary providers, but the reporting duty is the same one everybody else has. So a blank row at a college is not an exemption being used. It is something else, and this page cannot tell you what.",
  coverageObligationAllStudents:
    "The scorecard is meant to describe everyone who engaged in a program of study, not only the people whose training the workforce system paid for. Getting from one to the other is a records problem: the provider supplies the roster, and the state produces the employment and earnings figures by matching that roster against its unemployment-insurance wage records. Where that match cannot be made, there is nothing to publish about the people it would have covered, and no filing by the provider would produce it.",
  coverageObligationSuppression:
    "A results cell is withheld when the group behind it is small enough that publishing the figure could identify a person in it. That is a privacy protection working as designed, and it is not distinguishable at source from a cell nobody filled in.",
  // Names the top of a ranking the table above deliberately does not sort by. A reader finds
  // that ranking on their own in about four seconds, so the choice is between letting them
  // find it unaccompanied and naming it with the obligations attached. This names it.
  coverageObligationsClosing: (first: string, second: string) =>
    `In this snapshot the two categories leaving the most rows empty are ${first} and ${second}. The first is the one the regulation above makes voluntary rather than required. For the second, and for every other row in that table, this page cannot tell you which of these explanations applies to any particular program, or whether any of them does. Reading that column as a ranking of diligence would get the direction of the finding backwards.`,
  coverageCitationsNote:
    "The primary texts below, federal and state, are published in English only.",

  coverageCohortHeading: "Blank cells against the size of the group",
  coverageCohortIntro:
    "If small-group suppression is what is behind an empty cell, the blank rate should fall as the group grows. That is a prediction the data can be asked about, and asking it is the only way this page can say anything about why a cell is empty without inventing a reason.",
  coverageCohortColumn: "People who left the program",
  coverageCohortAtLeast: (lower: string) => `${lower} or more`,
  coverageCohortRange: (lower: string, upper: string) => `${lower} to ${upper}`,
  coverageCohortOf: (missing: string, total: string) => `${missing} of ${total}`,
  coverageCohortCaveat:
    "Only cohorts a provider filed against a single program are counted here. A provider that filed one cohort covering a whole institution would land in the largest band while describing a population that is not one program. Programs that filed no exit count appear in no band at all, because an unstated group size is not a small group.",
  coverageCohortReading:
    "Completion and employment behave the way small-group suppression predicts: the blank rate is highest in the smallest groups and falls as the groups grow. Earnings does not fall to meet them. It stays the least published measure in every band, including the largest, where group size can no longer be the explanation. Whatever is keeping the earnings column empty in large programs is something other than protecting a small group.",

  coverageProvidersHeading: "Where the silence sits",
  coverageProvidersBody: (silent: string, total: string, programs: string) =>
    `${silent} of the ${total} providers named in this record publish nothing for any program they filed, covering ${programs} programs between them. Every other program with an empty row belongs to a provider that did publish something somewhere, which is worth knowing: for most of the gap, the reporting relationship exists and a particular measure is missing from it.`,

  coverageMethodHeading: "How this page counts",
  coverageMethodSource:
    "The source is the U.S. Department of Labor's Eligible Training Provider scorecard, the WIOA ETA-9171 performance report that states file and the Department publishes. California's programs are read from it whole, with no sampling and no exclusions. Every figure on this page is a count taken over that record at build time, and none is typed into the text.",
  coverageMethodBlankHeading: "What a blank means, precisely",
  coverageMethodBlank:
    "The scorecard writes a single sentinel value wherever a measure has no figure, and its own data dictionary says that one value covers three different situations: a group too small to publish without identifying somebody in it, no data reported for the program at all, and data the Department found significant quality problems in. One sentinel, three causes, and no way to tell them apart from outside. So this page does not separate them, and any page that claims to has invented the distinction. What the record can support is a different and narrower split: whether it described a group at all.",
  coverageMethodThreshold:
    "There is also no published number behind the first of those three. The rule is a standard rather than a threshold: disaggregated data is not required where the count is too small to be statistically reliable or where publishing it would reveal something about an individual participant. No minimum cell size appears in the reporting guidance, the form instructions, or the data dictionary, so this page states no threshold either, and the cohort-size table above is a description of what the published data does rather than a reconstruction of a rule.",
  coverageMethodStates:
    "Published means the measure carries a figure. Blank beside a filed cohort means the record states how many people were served, left, or completed, and leaves this particular measure empty. No performance record means the record states neither, so nothing about outcomes was filed for that program in any form.",
  coverageMethodZeroHeading: "A masked figure is not a zero",
  coverageMethodZero:
    "Nothing on this page adds, averages, ranks, or renders a missing measure as if it were zero. A withheld completion rate is not a completion rate of nought, and a program with an empty row has not scored badly, it has not been scored. Where a genuine reported zero exists in this data it is treated as the real and serious finding it is, and kept visibly apart from an empty cell.",
  coverageMethodFloorHeading: "When a share is withheld",
  coverageMethodFloor: (minimum: string) =>
    `A percentage is published only where at least ${minimum} records sit behind it. Below that a single record moves the answer by more than three points, which is more precision than the denominator can carry, so the counts are published and the share is left out. That is the same rule this project applies to every figure it cannot stand behind.`,
  coverageMethodLimitsHeading: "What this page does not claim",
  coverageMethodLimits:
    "It does not claim that California's own Eligible Training Provider List holds the same programs as the federal file. The state publishes no export to check that against, which is the gap this whole page sits in. It does not claim to know why any individual cell is empty. It does not rank providers, categories, or agencies, and it draws no conclusion about the quality of any program from the presence or absence of a figure about it. And the program-year window beside every figure is quoted from the scorecard's About page rather than measured from the data, because the data carries no such field: if that sentence changes upstream, this page will not notice on its own.",
  coverageMethodRebuild:
    "The dataset behind this page is rebuilt from the public sources by a documented pipeline, and the counting is done by a tested module rather than by hand. Anyone can reproduce it.",

  coverageCiteHeading: "Citing or correcting this page",
  coverageCiteBody: (date: string) =>
    `If you are quoting a figure from this page, quote the read date with it: the underlying record was read on ${date}, and the scorecard is refreshed periodically, so a figure here can be behind the source without either being wrong. This page is a stable address and will keep answering the same question as the data underneath it changes.`,
  coverageCiteCorrections:
    "If you work on this data and something here is misread, the correction is welcome and will be made. That includes the reporting obligations described above: they are the part of this page least visible in the data itself and most easily got wrong from outside.",

  ctdlTitle: "The CTDL export, and what it does and does not carry",
  ctdlLede:
    "This project publishes California's training programs as CTDL, the vocabulary Credential Engine maintains for describing credentials and learning opportunities. This page is the export's own account of itself: which classes and properties it fills in, what the source record says that it drops, and what an independent validator found when it was pointed at the result.",
  ctdlWhy:
    "A mapping is only worth anything if somebody can check it. So the counts here are produced by the export at the moment it runs, the omissions are counted the same way as the coverage, and the validator's findings are published whichever way they came out.",

  ctdlBoundaryHeading: "What this is not",
  ctdlBoundaryRegistry:
    "None of this has been published to the Credential Registry. Not a submission, not a sandbox, nothing. The records exist as files in this project and nowhere else.",
  ctdlBoundaryEndorsement:
    "This is not affiliated with, endorsed by, or reviewed by Credential Engine. They publish CTDL openly and this project reads it; that is the whole of the relationship.",
  ctdlBoundaryCtids:
    "The identifiers are derived locally and are not Registry-assigned. A real CTID is issued when a resource is published to the Registry, which these are not, and the identifier URIs deliberately live on this project's own host rather than on a registry domain.",
  ctdlBoundaryDemo:
    "It is a demonstration of mapping discipline rather than a production publication. It exists to show how a public source maps onto a public vocabulary, and what is lost on the way.",

  ctdlStamp: (snapshot: string) =>
    `Counted from the export of the ${snapshot} dataset snapshot, at the moment that export ran.`,
  ctdlSnapshotMismatch: (exportSnapshot: string, siteSnapshot: string) =>
    `Note: this export describes the ${exportSnapshot} snapshot, and the rest of this site is currently serving ${siteSnapshot}. The figures below describe the export, not the pages around it.`,

  ctdlCoverageHeading: "What the export contains",
  ctdlCoverageIntro:
    "One entity per training program, one per distinct provider name as filed, and one statistics profile for each program that reports at least one outcome. A program that reported nothing gets no statistics profile at all: an empty one would read as \"measured, and empty\".",
  ctdlEntityColumn: "CTDL class",
  ctdlEntityCountColumn: "Entities",

  ctdlPropertiesHeading: "Which properties are filled in",
  ctdlPropertiesIntro:
    "Every property below is emitted only where the source asserted something. A blank is a blank: no placeholder, no zero, and nothing inferred from a neighbouring field. The order is the export's own, not best-first.",
  ctdlPropertyColumn: "Property",
  ctdlPropertyCountColumn: "Programs carrying it",
  ctdlPropertyShareColumn: "Share",

  ctdlMeasuresHeading: "Which outcome measures are projected",
  ctdlMeasuresIntro:
    "Each reported measure becomes one metric and one observation inside the program's statistics profile. The share is against the programs that have a statistics profile at all, not against every program: a measure missing because a program reported nothing is a different fact from a measure missing from a program that reported something else.",
  ctdlMeasureColumn: "Measure",
  ctdlMeasureCountColumn: "Observations",
  ctdlMeasureShareColumn: "Of programs with any outcome",

  ctdlGapsHeading: "What the export does not carry",
  ctdlGapsIntro:
    "The source record says more than this export projects. Counting only what was emitted would describe a projection as though it were the whole record, so the dropped fields are counted too, with the CTDL term that would have carried each one where such a term exists.",
  ctdlGapsReading:
    "Where a CTDL term is named, the vocabulary has somewhere to put this and the export does not use it. That is a gap in the export, not a limit of CTDL, and it is stated that way rather than left for a reader to work out from an absence.",
  ctdlGapColumn: "What the source says",
  ctdlGapProgramsColumn: "Programs reporting it",
  ctdlGapTermColumn: "CTDL term that would carry it",
  ctdlGapNoTerm: "None used",
  ctdlGapFieldsLabel: "Source fields",
  ctdlCostFloor: (n: string) =>
    `Separately, ${n} program(s) report a cost total that a suppressed component makes a floor rather than a price. CTDL's price property has no way to say "at least", so no cost is published for those rather than publishing a floor as though it were the fee.`,

  ctdlGapOutcomeMeasures: "Four of the nine reported outcome measures",
  ctdlGapOutcomeMeasuresWhy:
    "The source reports nine WIOA performance measures and this export projects five. Total served, total exited, total completed and employment in the fourth quarter after exit are reported and are not carried. The statistics layer could express them in exactly the same shape as the five that are.",
  ctdlGapProgramLength: "How long the program takes",
  ctdlGapProgramLengthWhy:
    "CTDL has a property for the estimated duration of a learning opportunity. The source's length in weeks and hours is not carried, and neither is the competency-based flag, which means a program finishes when the student can do the work and so has no fixed length by design.",
  ctdlGapProgramFormat: "Online, in person, or both",
  ctdlGapProgramFormatWhy:
    "CTDL has a delivery-type property, but its value has to be a concept from a controlled vocabulary that credreg.net serves as a web page rather than as data. This export emits no concept it cannot check against machine-readable data, so the format is not carried.",
  ctdlGapInstructionalProgramCode: "The CIP code for the field of study",
  ctdlGapInstructionalProgramCodeWhy:
    "CTDL has an instructional-program property that takes a CIP alignment, in the same shape this export already uses for the occupation's SOC code. The CIP code the source filed is not carried.",
  ctdlGapProgramLocation: "Where the program is offered",
  ctdlGapProgramLocationWhy:
    "CTDL has a property for where a learning opportunity is available. The program's location, and the region this project derives from it, are not carried. For a separate reason, no address is put on the organization either: the location on a record is the program's, not necessarily the provider's.",
  ctdlGapProviderCategory: "What kind of provider it is",
  ctdlGapProviderCategoryWhy:
    "The source's provider category does not map onto CTDL's agent-sector vocabulary without judgement calls, and that vocabulary is served as a web page rather than as data. The organization carries the name the source filed and nothing else.",
  ctdlGapWioaFundedCost: "What it costs a student funded under WIOA",
  ctdlGapWioaFundedCostWhy:
    "That is a different cost to a different payer, and CTDL can carry it as a second cost profile distinguished by a concept from a vocabulary served as a web page rather than as data. Only the out-of-pocket total is carried.",
  ctdlGapOccupationProjections: "The state's ten-year outlook for the occupation",
  ctdlGapOccupationProjectionsWhy:
    "This export projects the federal training record. California's projections for the occupation each program feeds — median wage, expected openings, growth — are joined to the program everywhere else on this site and are not carried here. They describe an occupation rather than this program, and hanging them off the program would assert that the program leads to that wage, which the source does not say. The occupation code itself is carried, so the alignment is stated and the projection is not.",

  ctdlValidationHeading: "What an independent validator found",
  ctdlValidationIntro: (tool: string, version: string) =>
    `The export checks itself, but every one of those checks was written by the same hand as the export, against the same reading of the same schema — which is the reading a mistake would survive. So it is also run through ${tool} ${version}, a separate tool with its own copies of Credential Engine's schema and a citation for every rule it applies. It makes no network request and submits nothing anywhere.`,
  ctdlValidationEntities: (n: string) => `${n} entities were checked.`,
  ctdlValidationSeverityColumn: "Severity",
  ctdlValidationCountColumn: "Findings",
  ctdlSeverityError: "Error (blocking)",
  ctdlSeverityWarning: "Warning",
  ctdlSeverityInfo: "Information",
  ctdlSeverityUnverifiable: "Unverifiable",
  ctdlValidationResult:
    "No errors, and one warning, on every entity in the graph. The warning is the tension this export already had on the record: the published grammar says an identifier is a random UUID, and an export that has to produce the same identifiers every time cannot use a random one. Nothing else came back — no property used on a class that does not declare it, no reference pointing at nothing, no relationship stated in one direction and contradicted in the other, no invented term.",
  ctdlValidationUnaccepted:
    "This run returned a finding that has not been reasoned about. The export refuses to publish in that state, so if you are reading this sentence on a live page, something is wrong and a correction is welcome.",
  ctdlFindingCodeColumn: "Finding",
  ctdlFindingCountColumn: "Times",
  ctdlFindingEntitiesColumn: "Entities",
  ctdlFindingStateColumn: "State",
  ctdlFindingAccepted: "Accepted, with a reason",
  ctdlFindingUnaccepted: "Not accepted",
  ctdlFindingsNote:
    "An accepted finding is a decision on the record, not a filter: it stays counted here and in the machine-readable statement. Any finding whose code has not been reasoned about fails the export instead of appearing quietly among the others.",

  ctdlScopeHeading: "What the validator could and could not judge",
  ctdlScopeBody: (
    knownClasses: string,
    classes: string,
    knownProperties: string,
    properties: string,
  ) =>
    `A clean result is only as wide as the vocabulary the checker holds. This one drives its structural checks from the core schema documents it carries, so it was in a position to judge ${knownClasses} of the ${classes} classes and ${knownProperties} of the ${properties} properties this export emits.`,
  ctdlScopeUnjudged:
    "The rest are the outcome-statistics layer, which publishes its own schema document that the validator does not carry, plus one currency property. A term a checker has never heard of is one it declines to judge, not one it approves.",
  ctdlScopeCaveat:
    "Those terms were checked by the export itself against the statistics schema, fetched and recorded in this project's provenance. That is a weaker guarantee than an outside opinion, and it is named as one.",
  ctdlScopeClassesLabel: "Classes not judged",
  ctdlScopePropertiesLabel: "Properties not judged",

  ctdlMappingHeading: "What each mapping rests on",
  ctdlMappingIntro:
    "Every class and property here was chosen against a published definition rather than from memory, and the export refuses at build time to emit a term the vocabulary does not define. These are the primary definitions, not summaries of them.",
  ctdlMappingCitationsNote:
    "Credential Engine publishes these in English only, so they are marked as English on this page.",
  ctdlExportSourceLink: "Read the export, including the reason recorded beside every mapping",

  ctdlGetHeading: "Getting the export, and rebuilding it",
  ctdlGetIntro:
    "The graph is about 17 MB of JSON-LD, which is too large to commit and too specific to one snapshot to serve as though it were current. It is built on demand and packaged with a checksum, and the two statements this page renders from are published beside it.",
  ctdlGetStatements: "The statements this page is built from, as published:",
  ctdlGetCoverageFile: "Coverage statement (what is carried, and what is not)",
  ctdlGetValidationFile: "Validation statement (what the validator found)",
  ctdlGetReproduce:
    "To rebuild the graph from source: clone the repository, run the pipeline to fetch the public federal and state data, then run the export and the validation. Both are single commands and both are deterministic — the same dataset always produces byte-identical output, so a rebuild can be compared against a published one directly.",
  ctdlGetReleases: "Packaged exports are published as releases:",

  ctdlCiteHeading: "Corrections",
  ctdlCiteBody:
    "If a mapping here is wrong, or a property is being used in a way the schema does not intend, that is worth an issue. This is a demonstration and the point of it is to be checkable; a correction from somebody who works on this vocabulary is the most useful thing this page could produce.",
};

/**
 * Every key in `en` must exist in every other dictionary, with a matching signature.
 * Deliberately not `as const`: literal types would require the Spanish text to be
 * character-identical to the English.
 */
type Dictionary = typeof en;

/**
 * The dictionary as a parameter type, for modules that take `t` rather than a language.
 * Exported so the funding copy tables can live beside the components that render them
 * instead of inside a single page file.
 */
export type Copy = Dictionary;

const es: Dictionary = {
  siteName: "Afterward",
  tagline: "Programas de capacitación en California y qué pasó con quienes los tomaron",
  notAffiliated:
    "No es un sitio del estado de California. Es un proyecto independiente hecho con datos públicos.",
  skipToContent: "Saltar al contenido principal",

  searchLabel: "Busque programas, instituciones u ocupaciones",
  // Program and occupation names in the source data are English only, so a Spanish
  // example would return nothing. These terms actually match.
  searchPlaceholder: "medical assistant, welding, Fresno…",
  filters: "Filtros",
  clearFilters: "Borrar filtros",
  resultsCount: (n: number, total: number) => `${fmt(n)} de ${fmt(total)} programas`,
  noResults: "Ningún programa coincide con estos filtros.",
  noResultsHint: "Quite un filtro o busque un término más general.",

  filterOutcomes: "Solo programas con resultados reportados",
  filterOutlook: "Perspectiva laboral",
  outlookAny: "Cualquier perspectiva",
  outlookGrowing: "Solo ocupaciones en crecimiento",
  outlookShrinking: "Solo ocupaciones en declive",
  statShrinking: (n: number) =>
    `${fmt(n)} preparan para ocupaciones que California espera que se reduzcan`,
  statReported: (n: number, total: number) =>
    `${fmt(n)} de ${fmt(total)} reportan qué pasó con sus estudiantes`,
  showThese: "Ver estos",
  filterCity: "Ciudad",
  filterAnyCity: "Cualquier lugar de California",
  filterMaxCost: "Costo máximo de su bolsillo",
  filterAnyCost: "Cualquier costo",

  filterLength: "Lo máximo que puede dedicarle",
  filterAnyLength: "Cualquier duración",
  lengthAtMost: (weeks: number): string => {
    const gloss = LENGTH_GLOSS.es[weeks];
    return gloss ? `${gloss} (${fmt(weeks)} semanas)` : `${fmt(weeks)} semanas o menos`;
  },
  filterLengthNote:
    "Las semanas tal como las reportó la institución. La duración también es lo que hace " +
    "comparables dos tasas de finalización: entre los programas de California cuyas cifras " +
    "describen solo ese programa, la mediana de quienes terminaron es del 97% en los de " +
    "cuatro semanas o menos, y baja en cada escalón de duración hasta el 78% en los de más " +
    "de un año. Un programa largo y uno corto no se están midiendo con la misma vara.",
  filterLengthUnmeasured: (n: number): string =>
    n === 1
      ? "Este filtro también deja fuera 1 programa que coincide con el resto de su búsqueda: " +
        "su institución no reportó la duración, así que el filtro no tiene nada que evaluar. " +
        "Que un programa nunca haya dicho cuánto dura no significa que no dure nada."
      : `Este filtro también deja fuera ${fmt(n)} de los programas que coinciden con el resto ` +
        `de su búsqueda: sus instituciones no reportaron la duración, así que el filtro no ` +
        `tiene nada que evaluar. Que un programa nunca haya dicho cuánto dura no significa ` +
        `que no dure nada.`,
  filterLengthCompetency: (n: number): string =>
    n === 1
      ? "Este filtro también deja fuera 1 programa basado en competencias que coincide con el " +
        "resto de su búsqueda. Termina cuando la persona ya sabe hacer el trabajo, así que no " +
        "tiene una duración fija que comparar con un límite de tiempo. Así lo diseñó la " +
        "institución; no es algo que falte en el registro."
      : `Este filtro también deja fuera ${fmt(n)} programas basados en competencias que ` +
        `coinciden con el resto de su búsqueda. Terminan cuando la persona ya sabe hacer el ` +
        `trabajo, así que no tienen una duración fija que comparar con un límite de tiempo. ` +
        `Así los diseñaron sus instituciones; no es algo que falte en el registro.`,
  lengthCompetencyBased: "Basado en competencias: sin duración fija",
  lengthCompetencyBasedLong:
    "La institución reportó este programa como basado en competencias: termina cuando la " +
    "persona ya sabe hacer el trabajo, así que no tiene un número fijo de semanas. Eso es lo " +
    "que reportó la institución, no un vacío en el registro.",
  filterNameLength: (label: string): string => `el límite de tiempo «${label}»`,

  sortBy: "Ordenar por",
  sortRelevance: "Más relevante",
  sortEarnings: "Mayores ingresos reportados",
  sortCost: "Menor costo",
  sortLength: "Más corto primero",
  sortOpenings: "Más vacantes",

  cost: "Costo",
  costAtLeast: (v: string) => `Al menos ${v}`,
  costPartial:
    "No se reportó uno de los componentes del costo, así que el total real es más alto que este.",
  leadsToSeveral:
    "Prepara para más de una ocupación. La perspectiva mostrada es la más débil de ellas.",
  length: "Duración",
  weeks: (n: number) => `${fmt(n)} semanas`,
  provider: "Institución",
  providerPrograms: "Programas ofrecidos",
  providerReporting: "Reportan resultados",
  providerShrinking: "Preparan para ocupaciones en declive",
  providerProgramList: "Todos los programas aquí",
  allPrograms: "Ver todos los programas de esta institución",
  leadsTo: "Lleva a",
  programsForThisJob: "Programas que capacitan para este empleo",
  notReported: "No reportado",
  notReportedLong:
    "La institución no reportó este dato, o se omitió para proteger la privacidad de un grupo pequeño.",

  outcomes: "Qué pasó con quienes tomaron este programa",
  completionRate: "Terminaron el programa",
  employmentRate: "Trabajando 6 meses después",
  medianEarnings: "Ingresos en un trimestre después",
  medianEarningsNote:
    "Los ingresos de un solo trimestre, unos tres meses, no un salario anual. No los compare directamente con el pago anual de la ocupación.",
  peopleServed: "Personas inscritas",
  peopleExited: "Personas que salieron o terminaron",
  outcomesUnreported: "Este programa no reportó resultados",
  outcomesUnreportedBody:
    "Cerca de un tercio de los programas de California no reportan nada. Eso dice algo sobre su reporte, no sobre si el programa funciona.",
  outcomesNoFigures:
    "Este programa no reportó tasa de finalización, tasa de empleo ni cifra de ingresos",
  outcomesNoFiguresBody:
    "El registro federal de este programa incluye un conteo de personas y ninguna cifra junto a él. Eso dice algo sobre su reporte, no sobre si el programa funciona.",
  basedOn: (n: number) => `Con base en ${fmt(n)} personas`,
  smallSample: "Grupo pequeño — interprete con cuidado",

  occupationOutlook: "Lo que California espera de este empleo",
  medianWage: "Pago típico en California",
  jobOpenings: "Vacantes proyectadas",
  growth: "Cambio proyectado",
  growing: "En crecimiento",
  shrinking: "En declive",
  shrinkingWarning:
    "California proyecta que esta ocupación se reducirá en los próximos diez años. Menos vacantes puede significar una búsqueda más difícil.",
  entryEducation: "Normalmente requiere",
  perYear: "al año",
  relatedWork: "Trabajos relacionados",
  relatedWorkNote:
    "Ocupaciones de la misma familia que esta, ordenadas por vacantes proyectadas. Se relacionan por cómo las agrupa la clasificación laboral, no porque las habilidades se transfieran.",
  byRegion: "Pago por región",
  region: "Región",

  compareTitle: "Lado a lado",
  compareTrayLabel: "Programas seleccionados para comparar",
  compareMeasure: "Medida",
  compareAdd: "Comparar",
  compareCount: (n: number, max: number) => `${n} de ${max} seleccionados para comparar`,
  compareOpen: "Comparar estos",
  compareHide: "Ocultar comparación",
  compareClear: "Borrar todo",
  compareRemove: (name: string) => `Quitar ${name} de la comparación`,
  compareFull: "La comparación está llena. Quite uno para agregar otro.",
  compareNote:
    "La celda resaltada es la cifra reportada más fuerte de esa fila. Las filas donde menos de dos programas reportaron algo no se marcan, porque ser el único que reportó un número no es lo mismo que ser el mejor.",
  compareBestCost: "El costo reportado más bajo de esta comparación",
  compareBestLength: "La duración reportada más corta de esta comparación",
  compareBestCompletion:
    "La tasa de finalización reportada más alta de esta comparación, entre programas de " +
    "duración comparable cuyos resultados describen solo ese programa",
  compareBestEmployment:
    "La tasa de empleo reportada más alta de esta comparación, entre programas cuyos " +
    "resultados describen solo ese programa",
  compareBestEarnings:
    "Los ingresos reportados más altos de esta comparación, entre programas cuyos " +
    "resultados describen solo ese programa",
  compareNoStandout: "Ninguna cifra de esta fila se destaca como la más fuerte reportada",
  compareCompletionLength:
    "Aquí no se marca la finalización: estos programas no duran lo mismo. Entre los programas " +
    "de California cuyas cifras describen solo ese programa, la mediana de quienes terminaron " +
    "baja en cada escalón de duración — 97% en los de cuatro semanas o menos, 91% hasta tres " +
    "meses, 85% hasta seis, 80% hasta un año y 78% más allá. Marcar una celda indicaría cuál " +
    "de estos es más corto, no cuál es mejor. Las tasas no cambian, y la finalización se " +
    "sigue marcando cuando los programas comparados duran más o menos lo mismo.",

  vsState: "Programa típico de California",
  vsStateAbove: "Mejor que lo típico",
  vsStateBelow: "Peor que lo típico",
  ofReporting: (n: number) => `de ${fmt(n)} que reportan`,
  benchmarkNote:
    "Comparado con el programa típico de California que reportó esta misma medida. Los programas que no reportan nada no entran en la comparación.",

areaNote: (unplaced, total) =>
      `Las regiones son las áreas laborales que publica California. Un programa entra en una ` +
      `solo si su ciudad aparece en el título de esa región, así que ${fmt(unplaced)} de ` +
      `${fmt(total)} programas —algunos dentro de los condados de esas mismas regiones— aquí ` +
      `no pertenecen a ninguna. Elegir una región los oculta; no los coloca en otro lugar.`,
    unplacedOption: (n) => `Sin región asignada (${fmt(n)})`,
    anyCityInArea: "Cualquier ciudad de esta región",
    anyCityUnplaced: "Cualquier ciudad sin región",
    areaHidesUnplaced: (n) =>
      `Otros ${fmt(n)} programas coinciden con esta búsqueda, pero están en ciudades que ` +
      `California no ubica en ninguna región. No aparecen aquí y tampoco están en otra parte.`,
    unplacedHeading: "Programas que California no ubica en ninguna región",
    unplacedBody:
      "Sus ciudades no aparecen en ninguna área laboral publicada, así que no se les atribuye " +
      "el pago de ninguna región. Es un vacío en la geografía del estado, no un juicio sobre " +
      "los programas, y abarca tanto ciudades dentro de las regiones de arriba como ciudades " +
      "lejos de todas ellas.",
    statUnplaced: (n, total) =>
      `${fmt(n)} de ${fmt(total)} están en ciudades que California no ubica en ninguna región`,

  onetCredit:
    "Este sitio incorpora información de O*NET Web Services del Departamento de Trabajo de Estados Unidos, Administración de Empleo y Capacitación (USDOL/ETA). O*NET\u00ae es una marca registrada de USDOL/ETA.",
  aboutData: "De dónde vienen estos datos",
  snapshot: (d: string) => `Datos actualizados: ${d}`,
  viewProgram: "Detalles del programa",
  providerSite: "Sitio de la institución",
  providerHomePage: "Página principal de la institución",
  linkUnreachable: (date: string) =>
    `No pudimos abrir esta página cuando la revisamos el ${date}.`,
  linkSubstituted: (date: string) =>
    `No pudimos abrir la página que aparece en el registro federal cuando la revisamos el ${date}, así que este enlace lleva a la página principal de la institución.`,
  linkForSale: (date: string) =>
    `Cuando la revisamos el ${date}, esta dirección web mostraba una página que ofrece el dominio a la venta, no el sitio de la institución. Buscar la institución por su nombre, o llamarla por teléfono, tiene más probabilidades de encontrarla.`,
  linkRedirectUnrelated: (date: string) =>
    `Cuando la revisamos el ${date}, esta dirección web llevaba a otro sitio web, sin relación con esta institución. Buscar la institución por su nombre, o llamarla por teléfono, tiene más probabilidades de encontrarla.`,
  linkRedirectUnconfirmed: (date: string) =>
    `Cuando la revisamos el ${date}, esta dirección web llevaba a otro sitio web y no pudimos confirmar que sea el de esta institución. Buscar la institución por su nombre, o llamarla por teléfono, tiene más probabilidades de encontrarla.`,
  backToSearch: "Volver a la búsqueda",
  coverageNote: (pct: number) =>
    `${pct}% de los programas de California reportan al menos un resultado. Los demás se muestran con lo que se sabe.`,

  // ---- Browse indexes ----
  browseOccupationsTitle: "Todas las ocupaciones que California proyecta",
  browseOccupationsIntro:
    "California publica una proyección a diez años para cada ocupación que sigue. Aquí están todas, agrupadas según si el estado espera que el trabajo crezca o se reduzca y ordenadas por las vacantes que proyecta.",
  occupationsListed: "Ocupaciones en la lista",
  noScriptSearch:
    "La búsqueda necesita JavaScript, que no está funcionando aquí. Navegar no lo necesita: " +
    "cada ocupación y cada proveedor es un enlace simple en las páginas de abajo.",
  noScriptBrowseOccupations: "Ver todas las ocupaciones",
  noScriptBrowseProviders: "Ver todos los proveedores",
  titlesEnglishOnly:
    "Los nombres de las ocupaciones usan el nombre en español que publica O*NET cuando existe, " +
    "y permanecen en inglés cuando no.",
  programTextEnglishOnly:
    "Los nombres de los programas y sus descripciones aparecen aquí en inglés, porque es el " +
    "único idioma en que los publican los registros federales y estatales. Los nombres de las " +
    "ocupaciones están traducidos cuando O*NET publica un nombre en español. Todo lo demás en " +
    "esta página está traducido.",
  occupationColumn: "Ocupación",
  programsHere: "Programas en esta lista",
  onThisPage: "En esta página",
  jumpToOutlook: "Ir a una sección de esta lista",
  sortedByOpenings:
    "Ordenado por vacantes proyectadas, de mayor a menor. Una ocupación sin cifra publicada va al final en vez de contarse como ninguna.",
  bandShrinking: "Trabajos de los que California espera menos",
  bandShrinkingNote:
    "El estado proyecta menos de estos empleos en los próximos diez años. Capacitarse para uno no es un error, pero conviene decidirlo con la cifra a la vista.",
  bandSteady: "Trabajos sin cambio proyectado",
  bandSteadyNote:
    "El estado proyecta dentro de diez años la misma cantidad de estos empleos que hay hoy.",
  bandGrowing: "Trabajos de los que California espera más",
  bandGrowingNote:
    "El estado proyecta crecimiento aquí. Eso no dice nada sobre el pago, ni sobre si algún programa en particular lo prepara para ese trabajo.",
  bandUnknown: "Trabajos sin proyección publicada",
  bandUnknownNote:
    "El estado no publicó un cambio proyectado para estos. Es información que falta, no una proyección de cero.",

  browseProvidersTitle: "Todas las instituciones de capacitación",
  browseProvidersIntro:
    "Cada escuela, colegio y organización de capacitación con al menos un programa de California en estos datos, en orden alfabético y con cuánto publica de su propio historial.",
  browseProvidersDerived:
    "El índice federal de instituciones no trae filas de California, así que esta lista se reconstruye a partir de los propios programas. Las grafías que solo difieren en mayúsculas o puntuación se combinan en una sola entrada.",
  jumpToLetter: "Ir a las instituciones por letra inicial",
  otherLetter: "0–9 y otros",
  citiesColumn: "Ciudades",
  moreCities: (n: number) => `+${fmt(n)} más`,
  reportingRatio: (n: number, total: number) => `${fmt(n)} de ${fmt(total)}`,
  providersListed: "Instituciones en la lista",
  programsListed: "Programas en total",
  providersReportingSome: "Publican al menos un resultado",

  browseAllOccupations: "Ver todas las ocupaciones",
  browseAllProviders: "Ver todas las instituciones",

  // ---- Site chrome ----
  navLabel: "Navegación principal",
  navOccupations: "Ocupaciones",
  navProviders: "Instituciones",

  langSwitchHome: "inicio",

  siteSummary:
    "De uso gratuito y sin cuenta. Cada cifra viene de registros públicos federales y estatales, y un programa que no reportó nada aparece justamente así: sin nada reportado.",

  // ---- What a search engine shows ----
  metaProgramTitle: (program: string, place: string) =>
    place ? `${program} en ${place}` : program,
  metaProgramReported: (place: string) =>
    `${place}. Costo, duración y los resultados que reportó este programa: finalización, empleo seis meses después e ingresos.`,
  metaProgramUnreported: (place: string) =>
    `${place}. Costo y duración. Este programa no reportó resultados, lo cual no es prueba de que funcione mal.`,

  metaProviderTitle: (name: string, programs: number, place: string) =>
    `${name} — ${
      programs === 1 ? "1 programa de capacitación" : `${fmt(programs)} programas de capacitación`
    } en ${place}`,
  metaProviderCities: (n: number) => `${fmt(n)} ciudades de California`,
  metaProviderDescription: (reporting: number, total: number) =>
    `${fmt(reporting)} de ${fmt(total)} programas aquí reportan qué pasó con sus estudiantes. Costo, duración y resultados reportados de cada uno, con datos públicos.`,

  metaOccupationTitle: (title: string) =>
    `${title} en California — pago, perspectiva laboral y programas de capacitación`,
  metaOccupationTitleNoPay: (title: string) =>
    `${title} en California — perspectiva laboral y programas de capacitación`,
  metaOccupationWage: (wage: string) =>
    `California proyecta este trabajo a diez años y publica una mediana de ${wage} al año. Aquí se listan todos los programas que preparan para él.`,
  metaOccupationNoWage:
    "California no publica un pago mediano estatal para este trabajo. Aquí están su proyección a diez años, las regiones para las que sí publica cifras y todos los programas que preparan para él.",

  // ---- Page not found ----
  notFoundTitle: "Esta página no existe",
  notFoundBody:
    "Puede que la dirección esté mal escrita, o que apunte a un programa o a una institución que no está en el archivo federal con el que se hizo este sitio. Aquí nada está detrás de una cuenta, así que todo lo que tiene el sitio se alcanza desde estas tres páginas.",
  notFoundSearch: "Buscar todos los programas de capacitación de California",

  // ---- Federal occupation detail (CareerOneStop / O*NET, PROVENANCE D6) ----
  occupationDescriptionNote:
    "Así describe este trabajo el Departamento de Trabajo de EE. UU. Solo se publica en inglés.",
  occupationDescriptionNoteEs:
    "Así describe este trabajo el Departamento de Trabajo de EE. UU., en el español del propio Departamento.",
  wageSpreadHeading: "El rango real de sueldos",
  wageSpreadNote: (year: number): string =>
    `Una mediana es un solo punto. Estas son las cifras de ${year} de la Oficina de Estadísticas Laborales de EE. UU. para California, y muestran qué tan distintos son los sueldos de quienes ya hacen este trabajo. Léalas como ese rango, no como un sueldo inicial ni como una promesa de dónde va a terminar una persona.`,
  localRangeHeading: (area: string): string => `Cuánto se paga en ${area}`,
  localRangeStatewide: "En todo California",
  localRangeAreaColumn: "Zona",
  wageChartKey:
    "Cada barra va desde la décima parte peor pagada hasta la mejor pagada. La parte más oscura del medio es donde está la mitad de las personas, y la línea es la mediana.",
  localRangeNote: (area: string, year: number): string =>
    `Las cifras de ${year} de la Oficina de Estadísticas Laborales de EE. UU. para ${area}, junto a las mismas cifras de todo el estado. Una región puede quedar bastante por debajo o por encima del rango estatal, y el dato estatal es el que más se cita, así que cuando difieren, la fila local es la que describe el trabajo cerca de este programa.`,
  wageP10: "La décima parte peor pagada gana menos de",
  wageP25: "Una cuarta parte gana menos de",
  wageP50: "La mitad gana menos de",
  wageP75: "Tres cuartas partes ganan menos de",
  wageP90: "La décima parte mejor pagada gana más de",

  skillsHeading: "Las habilidades que más se usan en este trabajo",
  skillsNote:
    "O*NET, la base de datos ocupacional del Departamento de Trabajo de EE. UU., califica qué tan importante es cada una para este trabajo, y aquí aparecen en ese orden, de mayor a menor. Las calificaciones no se muestran, porque los datos traen el número sin la escala en la que se midió. Los nombres aparecen tal como se publican, en inglés.",
  skillsUnrated: (names: string) =>
    `O*NET también menciona estas, pero no las calificó, así que quedan fuera del orden en vez de ir al final: ${names}.`,

  brightOutlookLabel: "Bright Outlook: una designación del Departamento de Trabajo de EE. UU.",
  brightOutlookNote:
    "Es la designación del propio Departamento, hecha con sus proyecciones nacionales. No es una evaluación de este proyecto ni de California: las demás cifras de esta página vienen de la proyección de California, que puede apuntar en sentido contrario y en algunas ocupaciones lo hace.",
  outlookRapidGrowth: "Crecimiento rápido",
  outlookManyOpenings: "Muchas vacantes",

  similarWork: "Trabajos similares",
  similarWorkNote:
    "O*NET, la base de datos ocupacional del Departamento de Trabajo de EE. UU., señala estas ocupaciones como trabajos parecidos a este: es su propia lectura del oficio, no una agrupación por código. Conservan el orden de O*NET y solo aparecen las que California proyecta.",

  // ---- Figures borrowed from a wider occupation ----
  aggregateHeading: "Estas cifras describen un grupo de ocupaciones más amplio",
  cohortMarkerLabel: "Abarca más que este programa",
  cohortTableNote:
    "Las filas marcadas con \u2020 llevan cifras que el proveedor presentó por un grupo más amplio " +
    "que el programa nombrado: varios de sus programas, o toda la institución. Se muestran porque " +
    "son reales. No pueden compararse con las filas contiguas, porque no describen un solo curso.",
  aggregateBroadGroup: (group: string, codes: string) =>
    `California no publica cifras de pago ni de vacantes por separado para la ocupación que enseña este programa (${codes}). Solo reporta ese trabajo dentro de ${group}, la categoría más amplia en la que lo coloca la clasificación ocupacional, así que el pago, las vacantes y el cambio proyectado que aparecen abajo son los de esa categoría completa. Léalos como el rango en el que cae esta ocupación, no como una cifra de la ocupación misma.`,
  aggregateHybrid: (group: string, codes: string) =>
    `California no publica cifras de pago ni de vacantes por separado para la ocupación que enseña este programa (${codes}). La clasificación federal que sigue cuenta ese trabajo junto con varias ocupaciones relacionadas bajo ${group}, porque no se pueden medir por separado, así que el pago, las vacantes y el cambio proyectado que aparecen abajo son los del grupo combinado. Léalos como el rango en el que cae esta ocupación, no como una cifra de la ocupación misma.`,
  unnamedOccupation: "la ocupación bajo la cual California lo reporta",
  entryEducationWithheld: "No se muestra para este programa",
  entryEducationWithheldNote: (group: string) =>
    `California sí publica un requisito de estudios habitual para ${group}, pero es una sola respuesta para todo el grupo y puede exigir un título que la ocupación propia de este programa nunca pide. Se omite aquí en vez de mostrarlo junto a un programa al que quizá no corresponde. Es una decisión de este sitio, no un dato que la institución haya dejado de reportar.`,

  // ---- Methodology ----
  methodologyLink: "Cómo se obtienen las cifras de este sitio y qué no le dicen",
  aboutTitle: "Sobre estas cifras",
  aboutLede:
    "Este sitio publica en abierto cifras de desempeño sobre instituciones de capacitación de California, con nombre y apellido, y las pone una al lado de la otra. Vale la pena hacerlo, y vale la pena ser preciso sobre qué son esas cifras. Todo lo que sigue explica de dónde sale cada dato, quién lo produjo, qué deja fuera y qué hacer si usted cree que lo representa mal.",
  aboutIndependence:
    "Afterward es un proyecto independiente y sin fines de lucro. No está afiliado ni respaldado ni operado por el estado de California, el Departamento de Desarrollo del Empleo de California, ninguna junta local de desarrollo laboral ni el Departamento de Trabajo de EE. UU. Usa el sistema de diseño de código abierto de California, y por eso estas páginas se parecen a los sitios oficiales del estado. No lo son.",
  aboutProgramsCounted: "Programas descritos aquí",
  aboutProvidersNamed: "Instituciones nombradas aquí",
  aboutProgramsReporting: "Programas que reportan algún resultado",

  aboutSourcesHeading: "De dónde sale cada cifra",
  aboutSourcesBody:
    "Aquí no hay investigación propia, este proyecto no estima nada por su cuenta y nada es un pronóstico suyo. Cada número del sitio está copiado de uno de tres registros públicos y se puede rastrear hasta él.",
  aboutSourceProgramsLabel: "Programas, instituciones, costo, duración y resultados",
  aboutSourceProgramsBody:
    "El informe federal de desempeño de instituciones de capacitación elegibles (ETA-9171) del Departamento de Trabajo de EE. UU., que los estados presentan bajo la Ley de Innovación y Oportunidad en la Fuerza Laboral y que el Departamento debe publicar. De ahí viene cada nombre de institución, cada precio, cada duración y cada medida de lo que pasó con quienes se inscribieron.",
  aboutSourceOccupationsLabel: "Pago, vacantes proyectadas y perspectiva laboral",
  aboutSourceOccupationsBody:
    "El Departamento de Desarrollo del Empleo de California: sus proyecciones de empleo por ocupación a largo plazo para 2024–2034 y sus estadísticas de salarios cuando la proyección no trae salario. Son las estimaciones propias del estado a diez años para una ocupación, a nivel estatal y en las áreas que el estado nombra.",
  aboutSourceFederalLabel: "Descripciones de la ocupación y habilidades",
  aboutSourceFederalBody:
    "CareerOneStop, el servicio del Departamento de Trabajo de EE. UU. que publica en inglés el contenido ocupacional de O*NET. Cuando el Departamento también publica la ocupación en español mediante Mi Próximo Paso —600 de las 670 de California—, la página en español usa el nombre y la descripción en español del propio Departamento. Las otras 70 conservan el nombre en inglés, y nada en este sitio está traducido por máquina.",
  aboutSourceWagesLabel: "Cuánto paga una ocupación en todo su rango",
  aboutSourceWagesBody:
    "Las Estadísticas de Empleo y Salarios por Ocupación de California, que publica el EDD a partir de la Oficina de Estadísticas Laborales de EE. UU. Incluyen los percentiles 10, 25, 50, 75 y 90, y por eso una página de ocupación puede mostrar el rango completo y no solo la mediana. Cada percentil puede ocultarse por separado, y cuando se oculta se deja en blanco en lugar de estimarlo a partir de los percentiles vecinos.",
  aboutSourcesDates:
    "Cada fuente, su licencia y la fecha en que se consultó están registradas en el archivo público de procedencia del proyecto, y cualquiera puede reconstruir el conjunto de datos completo a partir de esas fuentes.",
  aboutProvenanceLink: "Leer el archivo de procedencia",

  aboutSelfReportedHeading: "Los resultados los reportan las propias instituciones, y este sitio no los verifica",
  aboutSelfReportedBody:
    "La finalización, el empleo y los ingresos los reporta cada institución de capacitación a California, y California al gobierno federal. Este proyecto reproduce lo que se presentó. No lo audita, no lo puede confirmar y no tiene manera de distinguir una cifra elaborada con cuidado de una hecha al descuido. Un número aquí es prueba de lo que una institución reportó, no de lo que ocurrió.",
  aboutSelfReportedSecond:
    "Esto importa sobre todo en el sentido que la gente no espera. Las medidas no se ajustan según a quién inscribe cada programa. Un programa que atiende a las personas más lejos del empleo tenderá a reportar menos empleo y menores ingresos que uno que inscribe a personas que ya están cerca de un trabajo, y nada en estos datos separa a los dos.",

  aboutMissingHeading: "Qué significa un espacio en blanco",
  aboutMissingBody:
    "Un valor que falta aquí significa que no se reportó o que se omitió. Nunca significa cero y nunca se muestra como cero. Según las reglas federales, los resultados de grupos pequeños se suprimen para que no se pueda identificar a ninguna persona participante, así que un espacio en blanco puede ser tanto un programa demasiado pequeño para publicarlo sin riesgo como uno que no presentó nada.",
  aboutMissingSecond: (reporting: string, total: string) =>
    `Cerca de un tercio de los programas de California no reporta absolutamente nada: ${reporting} de ${total} publican al menos una medida. Es una proporción tan grande que esconderla distorsionaría el sitio entero, así que un programa que no reportó nada aparece junto a los demás y lo dice con todas sus letras. La falta de datos no es prueba de que un programa funcione mal, y esta interfaz está hecha para no confundir esas dos ideas.`,

  aboutQuarterHeading: "La cifra de ingresos cubre tres meses, no un año",
  aboutQuarterBody:
    "Los ingresos medianos de esta medida federal son los ingresos del segundo trimestre después de que alguien salió del programa: un solo trimestre, unos tres meses. No es un salario anual ni un sueldo inicial. Aparece en la misma página que el pago anual típico de la ocupación, que es otra medida, de otra fuente y de otro periodo, y las dos no se deben leer una contra la otra.",

  aboutComparisonsHeading: "Qué afirman las comparaciones y qué no",
  aboutComparisonsBody:
    "Una tasa sola no se puede interpretar: nadie sabe si 45% empleado es bueno. Por eso, cuando un programa reporta una medida, se muestra frente al programa mediano de California que reportó esa misma medida. Los programas que no reportaron nada no entran en esa mediana, así que es una comparación entre quienes sí publican, no una comparación contra el estado entero.",
  /*
   * Corrected here, not appended to. This key still described «Mejor que lo típico» as a live
   * judgement long after the site withdrew it, which is why `about/page.tsx` carries a local
   * Spanish override and a TODO to delete it "once the Spanish key is corrected in i18n.ts".
   * Adding a sentence about the completion rule to a paragraph that still advertised the
   * withdrawn verdict would have left the key wrong in a new way, so it is replaced whole. The
   * override still wins on the rendered page until that constant goes.
   */
  aboutComparisonsSecond:
    "Este sitio llegó a etiquetar programas como «mejores» o «peores» que lo típico frente a esa mediana. Ya no lo hace. La mediana juntaba a todos los programas que reportan, sin importar su duración, y un certificado de cuatro semanas y una carrera de dos años no son comparables en finalización: medidos contra programas de su misma duración, ese rótulo estaba sencillamente invertido en alrededor de uno de cada diez programas. Las cifras y la mediana se siguen mostrando; la conclusión la saca usted, porque la comparación no podía sostenerla. Cuando dos programas se ponen lado a lado, la celda marcada es la cifra reportada más fuerte de esa fila; una fila donde menos de dos programas reportaron algo se queda sin marcar, porque ser el único que presentó un número no es lo mismo que ser el mejor. La finalización solo se marca cuando los programas duran más o menos lo mismo, porque ahí la misma distorsión aparece de dos en dos: la mediana de quienes terminaron baja del 97% en los de cuatro semanas o menos al 78% en los de más de un año, así que marcar entre duraciones distintas marca al curso más corto.",
  aboutComparisonsThird:
    "Ninguna comparación se construye a partir de un espacio en blanco. A un programa que no reportó nada nunca se le llama peor que el promedio, porque no hay nada que comparar y decirlo sería una acusación, no un hecho.",

  aboutAggregateHeading: "Cuando una cifra ocupacional describe más de una ocupación",
  aboutAggregateBody: (aggregate: string) =>
    `California no publica una estimación para cada ocupación. Para algunas, el estado reporta el trabajo solo dentro de una ocupación más amplia: la categoría superior, o un grupo que las estadísticas federales usan para oficios que no pueden medir por separado. En vez de dejar esos programas sin ninguna cifra ocupacional, este sitio muestra las de la ocupación más amplia y lo advierte en la página, nombrando esa ocupación más amplia y el código ocupacional propio del programa. Eso ocurre en ${aggregate} de las páginas de programa de este sitio.`,
  aboutAggregateSecond:
    "En ese caso hay un dato que se descarta a propósito en lugar de tomarlo prestado: el requisito de estudios habitual. Un salario mediano sobre una población más amplia sigue siendo una aproximación de algo a lo que la persona pertenece. Un título no lo es: es una sola respuesta asignada a todo el grupo, y en un grupo que mezcla una ocupación de nivel de maestría con un certificado de colegio comunitario no es aproximada, es falsa. Decirle a alguien que necesita un título que no necesita, para el trabajo que está estudiando ahora mismo, es el mismo tipo de error que mostrar como cero una cifra suprimida.",

  aboutLimitsHeading: "Limitaciones conocidas",
  aboutLimitsBody:
    "Esto es lo que este sitio hace mal o todavía no puede hacer. Se enumera aquí en vez de dejar que se descubra después.",
  aboutLimitTranslation:
    "Los nombres de los programas, las descripciones y los nombres de los proveedores aparecen en inglés en las páginas en español, porque las fuentes federales y estatales publican ese texto solo en inglés. Los títulos de las ocupaciones son distintos: el Departamento publica un nombre en español para 600 de las 670 ocupaciones de California, y la página en español lo usa; las otras 70 mantienen el título en inglés. Nada en este sitio está traducido automáticamente.",
  aboutLimitEtpl:
    "Los programas que aparecen aquí son los que California presentó al gobierno federal. Queda sin resolver si la lista estatal de instituciones elegibles incluye programas que el archivo federal omite, porque California no publica una descarga masiva de esa lista. Un programa ausente de este sitio no es necesariamente un programa que no existe.",
  aboutLimitUnmatched: (unmatched: string) =>
    `${unmatched} programas no muestran ninguna cifra ocupacional. California no publica proyección para la ocupación con la que están etiquetados, y no se sustituye por una ocupación parecida, porque un oficio de nombre similar con otro salario se vería exactamente igual que una respuesta correcta.`,
  aboutLimitArea: (unplaced: string) =>
    `${unplaced} programas no muestran una cifra de pago regional. Su ciudad no es una de las áreas metropolitanas o rurales que California nombra al publicar salarios, y no se toman prestadas las cifras de un área vecina para llenar el hueco.`,
  aboutLimitUrl: (noUrl: string) =>
    `${noUrl} programas no tienen un enlace de sitio web utilizable. La mayoría nunca presentó uno, y unos pocos presentaron algo que no era una dirección web, que se descarta en vez de convertirse en un enlace.`,
  aboutLimitProjections:
    "Las proyecciones ocupacionales son estimaciones del estado a diez años, no garantías. Una ocupación que California espera que crezca puede no crecer, y una que espera que se reduzca puede seguir siendo la decisión correcta para una persona concreta en un lugar concreto.",
  aboutLimitSnapshot: (date: string) =>
    `Todo lo que hay aquí es una instantánea tomada el ${date}. El archivo federal se actualiza cada trimestre, así que una cifra corregida en la fuente después de esa fecha todavía no está corregida aquí.`,

  aboutCorrectionsHeading: "Si una cifra de aquí lo representa mal",
  aboutCorrectionsBody:
    "Este sitio nombra organizaciones reales y publica números sobre ellas, así que tiene que existir una forma de avisar que algo está mal. Por favor abra un reporte en el repositorio público del proyecto, indicando el programa y la cifra que está cuestionando.",
  aboutCorrectionsSecond:
    "Hay dos desenlaces posibles y conviene distinguirlos. Cuando el error es de este proyecto — un cruce mal hecho, una medida mal etiquetada, un programa unido a la ocupación equivocada — se corrige, y la corrección no depende de quién la pida. Cuando lo que está mal es el registro público de origen, la corrección tiene que pasar por el organismo que lo publicó, ya que este sitio reproduce ese registro y no puede apartarse de él en silencio; el hilo del reporte es un buen lugar para dejar constancia de que hay una corrección en curso, y esa constancia se respeta aquí.",
  aboutCorrectionsLink: "Abrir un reporte sobre una cifra de este sitio",

  aboutAdviceHeading: "Esto no es asesoría",
  aboutAdviceBody:
    "Nada de lo que hay aquí es asesoría financiera, legal, educativa ni profesional. Inscribirse en un programa de capacitación es un compromiso económico y personal serio. Use esto como una fuente entre varias, y hable con la institución, con su America's Job Center local o con una persona orientadora antes de decidir.",

  // ---- En qué consiste el trabajo (página del programa) ----
  workHeading: "En qué consiste este trabajo",
  workNote:
    "Esto describe el trabajo que hace la gente, no las clases que enseña este programa. Viene del Departamento de Trabajo de EE. UU., que pregunta a quienes ya hacen ese trabajo. El Departamento lo publica solo en inglés, así que los nombres de los oficios y las frases de abajo quedan en inglés en esta página.",
  alsoCalled: "En los anuncios de empleo puede aparecer como:",
  tasksNote:
    "Parte de lo que hace la gente en este trabajo. El Departamento califica qué tan importante es cada tarea, y aquí aparecen en ese orden.",
  moreTasks: (n: number) => `Ver ${fmt(n)} tareas más de este trabajo`,
  workDescriptionOnly:
    "El Departamento no publica una lista de tareas diarias para este trabajo. Así describe la labor en su lugar.",
  workNothing:
    "El Departamento no publica ni descripción ni lista de tareas para este trabajo. Es un vacío del registro federal, no una señal de que el trabajo sea raro.",

  costHeading: "Cuánto cuesta y cuánto dura",
  payHeading: "Cuánto paga el trabajo y a quién contratan",

  // ---- Cómo se entra ----
  entryHeading: "Cómo se entra",
  entryExperience: "Experiencia previa necesaria",
  entryTraining: "Capacitación después de la contratación",
  expNone: "Ninguna",
  expUnder5: "Menos de 5 años en un trabajo parecido",
  expOver5: "5 años o más en un trabajo parecido",
  ojtNone: "Ninguna",
  ojtUnderMonth: "Menos de un mes",
  ojtToYear: "De 1 a 12 meses",
  ojtOverYear: "Más de un año",
  ojtInternship: "Prácticas o residencia",
  ojtApprenticeship: "Un aprendizaje",
  entryWarnExperience:
    "La mayoría de quienes consiguen este trabajo ya pasaron 5 años o más en uno parecido. Terminar este programa puede no bastar por sí solo. Pregunte a la institución quién contrata a sus egresados y qué hicieron esas personas antes.",
  entryNoteExperience:
    "Los empleadores suelen esperar algo de tiempo en un trabajo parecido, además de la capacitación. Pregunte a la institución qué hicieron sus egresados antes de ser contratados.",
  entryNoteApprenticeship:
    "A este trabajo se suele entrar por un aprendizaje, no solo con un curso en el salón de clases. Pregunte a la institución si este programa lleva a uno.",
  entryNoteInternship:
    "A este trabajo se suele entrar por prácticas o una residencia, no solo con un curso en el salón de clases. Pregunte a la institución si este programa lleva a eso.",
  entryNoteLongTraining:
    "A quienes entran los capacitan en el trabajo por más de un año después de empezar. La parte del salón de clases es el comienzo de este oficio, no todo el oficio.",
  entryNoteDirect:
    "No se pide experiencia previa y a quienes entran no los someten a una capacitación larga. Para un trabajo así, un programa suele ser la puerta de entrada.",
  entrySource:
    "Son las respuestas del gobierno federal sobre la ocupación, no reglas que ponga esta institución. California publica las mismas dos respuestas para cada uno de estos trabajos.",

  /* ---- Puede que alguien más pague este programa ------------------------------------------
   *
   * NEEDS A HUMAN REVIEWER BEFORE IT SHIPS. This is money and eligibility, the audience is the
   * people most harmed by getting it wrong, and a negation is the first thing lost in
   * translation. Four things a reviewer should check line by line:
   *
   * 1. Nothing here promises anybody funding. "Se pueden pagar" is a statement about what the
   *    rules allow, never about this reader; "podrían" carries every hedge the English carries.
   *    No "garantiza" and no "gratis" appears anywhere below, deliberately, even inside a
   *    negation — a reader skimming official-looking prose takes the word and drops the "not".
   * 2. The tense in `fundingLede`. "Estaba en la lista" is the claim; "está en la lista" is a
   *    different and unsupported one, and one letter separates them.
   * 3. The proper nouns stay in English on purpose — "America's Job Center", "Individual
   *    Training Account", "Eligible Training Provider List" — because a reader has to say those
   *    words to somebody or type them into a search. The Spanish gloss is beside each.
   * 4. `fundingWhoDecides` and `fundingLocal` are the two that say what this site cannot do.
   *    If any sentence in them reads as softer than its English, that is a defect, not a style
   *    choice.
   * -------------------------------------------------------------------------------------- */
  fundingLede: (date: string) =>
    `Este programa estaba en la Lista de Instituciones de Capacitación Elegibles de California (Eligible Training Provider List) cuando el estado la reportó por última vez al Departamento de Trabajo de EE. UU. (${date}). Los programas de esa lista se pueden pagar mediante una Cuenta Individual de Capacitación (Individual Training Account). Las inscripciones en la lista se renuevan cada cierto tiempo y pueden vencer, así que un programa que estaba en la lista en esa fecha puede no estar hoy. Pregunte antes de contar con ello.`,
  fundingHeading: "Puede que alguien más pague este programa",
  fundingIta:
    "El dinero federal para capacitación de la Ley de Innovación y Oportunidad en la Fuerza Laboral (WIOA) se paga mediante una Cuenta Individual de Capacitación: un acuerdo entre una junta local de desarrollo laboral y una institución de capacitación, que se establece en nombre de una sola persona. Ese dinero solo puede ir a una institución que esté en la Lista de Instituciones de Capacitación Elegibles del estado, que es la lista de la que sale cada programa de este sitio.",
  fundingBeforeHeading: "Pregunte antes de inscribirse, no después",
  fundingBefore:
    "El orden que fijan las reglas empieza en el centro, no en la escuela. Antes de que un centro pueda determinar que alguien es elegible para servicios de capacitación, tiene que reunir lo suficiente para decidir: como mínimo, mediante una entrevista, evaluación o valoración y la planificación de carrera. Remitir a la persona a la institución que eligió y abrir la cuenta vienen después, y las dos cosas le corresponden al centro: la cuenta es un acuerdo de pago con la institución de capacitación, y es la institución la que cobra a través de ella. Por eso la llamada va antes de inscribirse y antes de pagar. A quien ya haya hecho una de las dos cosas le conviene preguntar igualmente, y preguntar qué significa eso en su caso.",
  fundingCentersHeading: "El lugar donde preguntar es un America's Job Center of California",
  fundingCenters:
    "En un centro integral (comprehensive center) se puede acceder a los programas de todos los socios obligatorios; un sitio afiliado (affiliate site) ofrece algunos de ellos. El Departamento de Desarrollo del Empleo de California remite a la gente al buscador de CareerOneStop para encontrar uno. Conviene comunicarse con un centro antes de ir: el estado advierte que su propio personal no está físicamente en todas las oficinas.",
  fundingWhoCanBeServedHeading: "A quién se puede atender",
  fundingWhoCanBeServed:
    "California resume los criterios generales en tres puntos: la edad, el registro en el Servicio Selectivo cuando corresponde y la autorización para trabajar en Estados Unidos. La autorización de trabajo se verifica cuando la persona pasa a un servicio que la requiere, no en la puerta: las evaluaciones de carrera, un plan de empleo, el manejo del caso, la enseñanza de destrezas básicas y de inglés, la ayuda para completar los trámites de la autorización de trabajo y las referencias para transporte, cuidado infantil, alimentos y vivienda figuran todas como servicios que un área local puede brindar sin verificarla primero.",
  fundingInterviewHeading: "Espere una entrevista, no un formulario",
  fundingInterview:
    "Antes de que se pueda determinar que alguien es elegible para servicios de capacitación, esa persona debe recibir una entrevista, evaluación o valoración y planificación de carrera, o algo más que le dé al centro información suficiente para decidir. No hay un tiempo mínimo de espera fijado a nivel federal, pero tampoco hay manera de saltarse la conversación, y por eso este sitio no le puede decir a nadie si cumple los requisitos.",
  fundingDecidesHeading: "Qué es lo que decide el centro",
  fundingDecides:
    "Los servicios de capacitación se pueden poner a disposición de personas adultas y de trabajadores desplazados cuando el centro determina que es poco probable o imposible que consigan, solo con los servicios de carrera, un empleo que lleve a la autosuficiencia; que necesitan capacitarse para llegar ahí; y que tienen las destrezas y los requisitos para completar la capacitación con éxito. El programa además tiene que estar ligado a oportunidades de empleo en el área local, o en algún lugar al que la persona esté dispuesta a trasladarse o mudarse.",
  fundingPriorityHeading:
    "Diga si recibe asistencia pública, tiene bajos ingresos o necesita reforzar destrezas básicas",
  fundingPriority:
    "En la vía de financiamiento para adultos, la ley federal exige dar prioridad a quienes reciben asistencia pública, a otras personas de bajos ingresos y a quienes tienen deficiencias en destrezas básicas. California le indica al personal de los centros que siga un orden explícito: primero las personas veteranas y sus cónyuges elegibles que además están en uno de esos grupos; luego esos grupos; luego las demás personas veteranas y cónyuges elegibles; luego las poblaciones que el Gobernador o la junta local hayan agregado; y al final todas las demás. La prioridad no excluye a nadie y no se aplica a la vía de trabajadores desplazados. Solo funciona si usted se lo dice al centro, y California fija la prioridad de cada persona en el momento en que se determina su elegibilidad: por eso lo que cuenta es la primera cita.",
  fundingOtherFundingHeading: "Lleve lo que ya tiene: este dinero cubre un faltante",
  fundingOtherFunding:
    "El financiamiento de WIOA para capacitación es solo para quienes no pueden conseguir ayuda de otras subvenciones, o para quienes necesitan más de lo que esas fuentes cubren. Los centros deben considerar primero las Becas Pell, los fondos estatales de capacitación y la asistencia para familias necesitadas. Una persona se puede inscribir mientras su solicitud de Beca Pell sigue pendiente, si el centro lo acuerda de antemano con la institución.",
  fundingSupportHeading: "Pregunte qué más se puede cubrir mientras se capacita",
  fundingSupport:
    "Los servicios de apoyo —ayuda con el transporte, con el cuidado de niños y de otras personas dependientes, y otros— podrían brindarse a quienes participan en servicios de carrera o de capacitación y no pueden conseguirlos por otro lado. Las personas adultas que están desempleadas, no califican para el seguro de desempleo y están inscritas en una capacitación también podrían ser elegibles para pagos por necesidad (needs-related payments).",
  fundingLocalHeading: "La respuesta depende del área local y del año",
  fundingLocal:
    "Una vez que se determina que una persona es elegible y ya eligió una institución, el centro debe remitirla y abrir una cuenta, salvo que el programa haya agotado sus fondos de capacitación del año. Cuánto vale una cuenta, qué ocupaciones financia una junta, qué se considera un empleo que sostiene a una persona y cómo se aplica la prioridad se deciden localmente, en las 45 áreas locales de desarrollo laboral de California. Cumplir con todas estas reglas todavía no asegura un lugar. La propia guía de California para el personal de los centros lo dice sin rodeos: WIOA no es un programa de derecho automático, su financiamiento no es ilimitado y las juntas locales ofrecen servicios a quienes son elegibles cuando hay fondos disponibles.",
  fundingWhoDecides:
    "Si a una persona le pagan o no un programa lo deciden su junta local de desarrollo laboral y el personal del America's Job Center que la entrevista: no lo decide este sitio, ni lo decide la institución de capacitación. California tiene 45 áreas locales de desarrollo laboral y cada una fija sus propias políticas, así que la respuesta puede ser distinta para dos personas de condados vecinos. Nada de lo que dice esta página es una promesa de financiamiento ni una determinación de elegibilidad.",
  fundingAskEtplNow:
    "¿Este programa está ahora mismo en la Lista de Instituciones de Capacitación Elegibles de California?",
  fundingWhyEtplNow:
    "Una Cuenta Individual de Capacitación solo le puede pagar a una institución que esté en esa lista, y la elegibilidad se otorga por programa y no por escuela: una institución que está en la lista puede tener programas que no lo están. Además la elegibilidad tiene plazo y hay que renovarla.",
  fundingAskFullPrice:
    "¿Qué incluye el precio y qué tendré que comprar aparte: libros, herramientas, uniformes, cuotas de examen, cuotas de licencia?",
  fundingWhyFullPrice:
    "Las instituciones le reportan al estado la colegiatura y los materiales como cifras separadas, y cualquiera de las dos puede faltar, así que el costo que aparece aquí puede ser un piso y no un total. Las cuotas de examen y de licencia suelen quedar fuera de ambas.",
  fundingAskCredential:
    "¿Qué obtengo exactamente al final, quién lo expide y lo reconoce un empleador o una junta de licencias?",
  fundingWhyCredential:
    "Un programa de la lista tiene que llevar a una credencial, a un empleo o a un avance medible hacia uno, pero un «certificado de finalización» de una escuela y una licencia que reconoce una junta estatal son cosas muy distintas.",
  fundingAskWithdrawal:
    "Si dejo el programa a medias, ¿cuánto debo y qué pasa con el dinero ya pagado?",
  fundingWhyWithdrawal:
    "Una Cuenta Individual de Capacitación es un acuerdo de pago con la institución y puede pagarse por partes, así que quién le debe qué a quién si alguien se retira es una pregunta para la institución y el centro juntos, y hay que hacerla antes de inscribirse, no después.",
  fundingAskSchedule: "¿Cuándo empieza el siguiente grupo y cuántas horas por semana son?",
  fundingWhySchedule:
    "El horario decide si alguien puede seguir trabajando mientras se capacita, y los pagos por necesidad son solo para personas desempleadas que ya están inscritas: por eso el calendario y el dinero son la misma pregunta.",
  fundingAskFundingStream:
    "¿Bajo qué vía de financiamiento me atenderían: adultos, trabajadores desplazados o jóvenes?",
  fundingWhyFundingStream:
    "Son fondos distintos con reglas distintas. La prioridad que fija la ley para quienes reciben asistencia pública, para otras personas de bajos ingresos y para quienes tienen deficiencias en destrezas básicas se aplica solo a los fondos para adultos. A las personas jóvenes de 16 a 24 años que están fuera de la escuela se les puede atender con Cuentas Individuales de Capacitación de los fondos para jóvenes.",
  fundingAskLocalDemand: "¿Es esta una ocupación para la que esta área local financia capacitación?",
  fundingWhyLocalDemand:
    "El programa tiene que estar ligado a oportunidades de empleo en el área local o en otra a la que la persona esté dispuesta a trasladarse, y las juntas dan prioridad a las credenciales alineadas con los sectores de mayor demanda. Un programa puede estar en la lista estatal y aun así no ser uno que una junta en particular pague.",
  fundingAskItaCap:
    "¿Cuál es el máximo que esta área pone en una Cuenta Individual de Capacitación y alcanzaría para este programa?",
  fundingWhyItaCap:
    "Los topes y los límites de duración son política local, no federal, así que el mismo programa puede quedar cubierto por completo en un condado y solo en parte en el de al lado. Un tope tampoco es necesariamente el final del asunto: las reglas permiten elegir una capacitación que cueste más que el máximo cuando hay otros fondos para cubrir la diferencia. Pregunte de cuánto sería esa diferencia y con qué se podría cubrir.",
  fundingAskSelfSufficiency: "¿Cómo define esta área un empleo que sostiene a una persona?",
  fundingWhySelfSufficiency:
    "La determinación depende de si alguien puede alcanzar la autosuficiencia sin capacitarse, y California exige que cada junta local fije ese umbral por su cuenta: al menos el nivel de ingresos de vida mínimo (lower living standard income level) del área, y a menudo más alto. Es un número local, y es el número sobre el que descansa la decisión.",
  fundingAskOutOfArea: "¿Puedo usar esto para un programa en otro condado o en otro estado?",
  fundingWhyOutOfArea:
    "La capacitación fuera del área local se permite cuando el programa está en la lista estatal, y fuera de California cuando las políticas estatales y locales lo permiten; en ambos casos según el procedimiento local. Vale la pena preguntarlo dondequiera que el programa más cercano quede lejos, que en este estado son muchos lugares.",
  fundingAskFundsLeft: "¿Quedan fondos de capacitación para este año del programa?",
  fundingWhyFundsLeft:
    "La obligación de remitir a una persona elegible y abrirle una cuenta se mantiene salvo que el programa haya agotado sus fondos de capacitación del año. Esa es la única respuesta que un sitio web nunca puede saber, y lo decide todo.",
  fundingAskOtherGrantsFirst: "¿Qué debo solicitar primero: una Beca Pell u otra cosa?",
  fundingWhyOtherGrantsFirst:
    "Los fondos de WIOA son para quienes no pueden conseguir ayuda de otras subvenciones o necesitan más de lo que esa ayuda cubre, y los centros deben considerar primero las otras fuentes. Se permite inscribirse con una solicitud de Beca Pell pendiente si se acuerda de antemano.",
  fundingAskSupportCosts:
    "¿Me pueden ayudar con el transporte, el cuidado de niños o los gastos para vivir mientras me capacito?",
  fundingWhySupportCosts:
    "Los servicios de apoyo y los pagos por necesidad son aparte de la colegiatura, y solo están disponibles para quienes ya participan en servicios de carrera o de capacitación y no pueden conseguir esa ayuda en ningún otro lado. Conviene preguntarlo en la misma conversación, no en una posterior.",
  fundingAskWhatToBring: "¿Qué debo llevar y cuánto tarda una determinación?",
  fundingWhyWhatToBring:
    "La determinación se basa en una entrevista, evaluación o valoración y en la planificación de carrera, y el centro tiene que poder documentarla. No hay un tiempo mínimo de espera federal, así que la respuesta es local y conviene saberla antes de pedir un día libre en el trabajo.",

  fundingCentersNone: (miles: number) =>
    `No hay ningún America's Job Center a menos de unas ${miles} millas de la ciudad de este ` +
    `programa. El buscador de abajo busca en todo el estado.`,
  fundingCentersBeyondIntro: (miles: number) =>
    `No hay ningún America's Job Center a menos de unas ${miles} millas de la ciudad de este ` +
    `programa. Aun así, estas son las oficinas más cercanas: quedan más lejos, y conviene ` +
    `llamar antes de hacer el viaje:`,
  fundingCentersNotChecked:
    "Este sitio no estableció cuáles son las oficinas más cercanas a este programa. El buscador de abajo busca en todo el estado.",
  fundingDistanceNote:
    "Las distancias son en línea recta, así que el trayecto es más largo. Llame antes de ir: los horarios que aparecen aquí son los que publicó el directorio federal, y el estado advierte que su propio personal no está en todas las oficinas.",
  fundingCenterTypes:
    "En un centro integral (comprehensive center) se puede acceder a los programas de todos los socios obligatorios; un sitio afiliado (affiliate site) ofrece algunos de ellos.",
  fundingCallLabel: (center: string, phone: string) => `Llamar a ${center} al ${phone}`,
  fundingFindersIntro:
    "Encuentre un centro en cualquier parte de California y consulte qué hay hoy en la lista:",
  fundingEnglishSources:
    "Las reglas que se citan aquí y los sitios estatales y federales enlazados están publicados en inglés.",
  fundingComprehensive: "Centro integral",
  fundingAffiliate: "Sitio afiliado",
  fundingPhone: "Teléfono",
  fundingHours: "Horario",
  fundingMilesAway: (miles: number) => `a unas ${miles} millas`,
  fundingVeteransRep: "Tiene representante para personas veteranas",
  fundingClosed: "El directorio registra esta oficina como cerrada temporalmente",
  jobsHeading: (n: number) =>
    n === 1 ? "El empleo para el que capacita" : "Los empleos para los que capacita",
  jobDetail: "Sueldo, contratación y qué estudió la gente",
  fundingGuideTitle: "Pagar la capacitación en California",
  fundingGuideIntro:
    "Hay fondos federales y estatales que pueden pagar la capacitación de quienes reúnen los requisitos. Nada de eso se decide en este sitio, y nada de lo aquí escrito promete que una persona vaya a recibir fondos. Lo que sigue es lo que dicen las reglas públicas, quién decide y qué conviene preguntarles.",
  fundingGuideLink: "Cómo se paga esto y qué preguntar",
  navPaying: "Cómo pagarlo",
  filterLabel: "Filtrar esta lista",
  filterPlaceholder: "Escriba un empleo o el nombre de una escuela",
  filterShowing: (shown: number, total: number): string =>
    `Mostrando ${shown.toLocaleString("es-MX")} de ${total.toLocaleString("es-MX")}`,
  filterNoMatches:
    "Nada coincide con eso. Pruebe con menos letras o con una palabra del medio del nombre.",
  alternativesHeading: "Trabajos relacionados de los que California espera más",
  alternativesNote:
    "El Departamento del Trabajo de EE. UU. considera que estos empleos están relacionados con el de arriba, y California proyecta crecimiento en ellos en lugar de disminución. Relacionado no significa intercambiable: la capacitación, las licencias y el sueldo pueden ser distintos, y este programa no capacita para estos empleos. Es un punto de partida para preguntar, no una recomendación.",
  alternativesPrograms: (n: number): string =>
    n === 1 ? "1 programa aquí" : `${n.toLocaleString("es-MX")} programas aquí`,
  alternativesNoPrograms: "Ningún programa de aquí capacita para eso",
  saveProgram: "Guardar",
  savedProgram: "Guardado",
  savedCount: (n: number): string =>
    n === 1 ? "1 programa guardado" : `${n} programas guardados`,
  savedShow: "Ver solo los guardados",
  savedShowAll: "Ver todos los resultados",
  savedClear: "Borrar los guardados",
  savedFull: "Puede guardar hasta 20 programas. Quite uno para guardar otro.",
  savedWhere:
    "Se guardan solo en este dispositivo. No se envía nada a ningún lado, y si borra los datos del navegador, esto se borra.",
  shareSaved: "Copiar un enlace a estos",
  sharedListTitle: "Alguien le compartió estos programas",
  sharedListBody: (n: number): string =>
    n === 1
      ? "Un programa, de la lista de otra persona. No se guarda nada en este dispositivo a menos que usted lo guarde."
      : `${n} programas, de la lista de otra persona. No se guarda nada en este dispositivo a menos que usted los guarde.`,
  sharedListDropped: (n: number): string =>
    n === 1
      ? "Un programa de ese enlace ya no está en los datos del estado y no se muestra."
      : `${n} programas de ese enlace ya no están en los datos del estado y no se muestran.`,
  sharedListSave: "Guardar estos en mi lista",
  sharedListExit: "Buscar todos los programas",
  copyLink: "Copiar el enlace de esta búsqueda",
  copyLinkDone: "Enlace copiado",
  providerCostRange: "Rango de costos",
  providerCostOne: "Costo",
  providerTrainsFor: "Empleos para los que capacitan estos programas",
  providerNoneReportedTitle: "Esta escuela no reportó resultados",
  providerNoneReportedBody:
    "No se publica nada sobre cómo les fue después a quienes tomaron estos programas. Eso dice algo sobre lo que la escuela reportó, no es prueba de que la capacitación sea peor. Alrededor de un tercio de los programas de California está en la misma situación, y en algunos casos las cifras se ocultaron para proteger la privacidad de un grupo pequeño.",
  fundingHowSummary: "Cómo se paga esto y qué preguntar",
  fundingQuestionsHeading: "Qué preguntar antes de comprometerse",
  fundingQuestionsJobCenter: "Preguntas para el America's Job Center",
  fundingQuestionsProvider: "Preguntas para la institución de capacitación",
  fundingRuleLabel: "La regla:",
  fundingTranslationNote:
    "Esta sección fue revisada por una persona hablante nativa de español (slegarraga) el 6 de agosto de 2026. La versión en inglés sigue siendo la de referencia. Si algo aquí no queda claro, pregúntelo en el centro: son ellos quienes deciden.",

  // ---- Cobertura de los datos de resultados ----
  coverageTitle: "Qué tan completos están los datos de resultados de la capacitación en California",
  coverageNavShort: "Qué tan completos están estos datos",
  coverageJumpLabel: "Ir a una sección de esta página",
  coverageLede:
    "Cada programa de la Lista de Instituciones de Capacitación Elegibles de California se reporta al gobierno federal, y ese informe federal es donde viven las cifras de resultados. Esta página cuenta cuánto de ese informe está lleno: medida por medida, categoría de institución por categoría de institución, y frente al tamaño del grupo que cada cifra debería describir.",
  coverageWhy:
    "California publica su Lista de Instituciones de Capacitación Elegibles únicamente como una pantalla de búsqueda dentro de CalJOBS. No hay archivo que descargar ni conteo publicado de cuántos programas de la lista traen datos de resultados. Así que tanto una persona que elige entre dos programas como una agencia que decide dónde rendiría más un esfuerzo de reporte trabajan sin ese número. El informe federal son los mismos programas con otra portada, y sí se puede contar, así que esta página lo cuenta y muestra el procedimiento.",
  coverageFraming:
    "Esto mide un registro público. No evalúa a ninguna institución, colegio ni agencia. Una celda en blanco aquí dice algo sobre cómo se recogen los datos laborales y sobre qué está obligado a presentar cada tipo de institución. No es prueba de que un programa sea malo, ni de que una institución haya ocultado algo que debía, ni de que alguien haya fallado.",

  coverageStamp: (first: string, last: string, date: string) =>
    `Informe federal ETP, años de programa ${first} a ${last}, consultado el ${date}.`,
  coverageStampNote: (statedOn: string) =>
    `Ese rango de años de programa no está en los datos. Ningún registro que publica el informe federal trae un campo de año de programa ni de periodo de reporte, en ninguno de sus dos índices. El rango sale de una frase en la página «About» del propio informe, consultada ahí el ${statedOn}, y el diccionario de datos que se publica junto a esos mismos datos todavía nombra un año de programa anterior, así que la fuente no coincide consigo misma. Una actualización en el origen puede mover ese rango sin que nada de esta página se entere, y por eso la fecha en que este proyecto consultó el registro aparece junto a cada cifra de abajo.`,

  coverageProgramsCounted: "Programas de California en el registro federal",
  coverageSilentLabel: "No publican ninguna medida de resultados",
  coverageSilentNoRecordLabel: "De esos, tampoco presentaron un conteo de personas",
  coverageHeadlineBody: (silent: string, total: string, withCohort: string, unfiled: string) =>
    `${silent} de ${total} programas de California no publican tasa de finalización, ni tasa de empleo, ni ingresos medianos. Y se dividen en dos grupos que conviene distinguir. De ellos, ${withCohort} presentaron un conteo de las personas que atendieron, que salieron o que terminaron, así que el registro existe y las celdas de resultados están vacías. Los ${unfiled} restantes no presentaron ninguna cifra de desempeño, así que no hay registro en el que pueda haber celdas.`,
  coverageHeadlineSecond:
    "Los dos son huecos, y no son el mismo hueco. Uno es una medida que no se publicó junto a un grupo que sí se declaró; el otro es un programa del que el registro federal no dice nada. Lo primero se arregla con una regla de reporte. Lo segundo se arregla con una tubería de datos.",

  coverageMeasuresHeading: "Qué está lleno, medida por medida",
  coverageMeasuresIntro:
    "Todas las medidas de resultados que el informe federal trae para un programa, y cuántos programas de California publican cada una. Aquí nada se deriva, se combina ni se estima: estas son las columnas que tiene la fuente.",
  coverageMeasureColumn: "Medida",
  coverageReportedColumn: "Publicada",
  coverageBlankColumn: "En blanco junto a un grupo declarado",
  coverageUnfiledColumn: "Sin registro de desempeño",
  coverageMissingColumn: "No publicada",
  coverageMeasureNote:
    "El conteo de personas empleadas y la tasa de empleo son dos datos distintos, y el conteo no es el numerador de la tasa. La tasa se divide entre un grupo de personas salientes definido de otra manera que esta fuente no publica, así que esas dos filas se mueven por separado y ninguna se puede reconstruir a partir de la otra.",
  coverageRouteSplit: (providerFloor: string, providerN: string, wageCeiling: string, wageN: string) =>
    `La tabla se parte por una línea que no tiene nada que ver con ninguna institución. Los conteos de a cuántas personas se atendió, cuántas salieron, cuántas terminaron y cuántas obtuvieron una credencial los aporta la institución de capacitación. Las cifras de empleo e ingresos las produce el estado, cruzando la lista de personas de la institución con los registros salariales del seguro de desempleo. En esta instantánea los dos grupos no se solapan en absoluto: la medida menos publicada de las que aporta la institución, «${providerFloor}», está llena en ${providerN} programas, y la más publicada de las que produce el cruce salarial, «${wageCeiling}», en ${wageN}. Toda medida que tiene que sobrevivir a un cruce de registros se publica menos que cualquier medida que no.`,
  coverageRouteSplitCaveat:
    "Eso describe los datos publicados, no los explica, y no afirma que el cruce esté mal hecho. Sí ubica el hueco: en la mayoría de estos programas la relación de reporte existe y funciona, y las medidas que faltan son justo las que dependen de que dos sistemas encuentren a la misma persona.",
  coverageMeasureTotalServed: "Personas atendidas",
  coverageMeasureTotalExited: "Personas que salieron del programa",
  coverageMeasureTotalCompleted: "Personas que terminaron",
  coverageMeasureCompletionRate: "Tasa de finalización",
  coverageMeasureCredentials: "Credenciales obtenidas",
  coverageMeasureEmployedQ2: "Con empleo dos trimestres después de salir (conteo)",
  coverageMeasureEmploymentRate: "Tasa de empleo dos trimestres después de salir",
  coverageMeasureEmployedQ4: "Con empleo cuatro trimestres después de salir (conteo)",
  coverageMeasureEarnings: "Ingresos medianos del segundo trimestre después de salir",

  coverageByTypeHeading: "Según la categoría con la que la institución se registró",
  coverageByTypeIntro:
    "La categoría de abajo es la que declaró la propia institución en el registro federal. No es un mapa limpio del sistema de capacitación de California: en esta instantánea los colegios comunitarios aparecen tanto en «Public» como en «Higher Ed: Associate's Degree», y las escuelas para adultos, los programas ocupacionales regionales y las oficinas de educación de condado llegan todos como «Public». Se reporta tal como se presentó y no se reordena, porque reordenarla significaría inventar aquí una clasificación y luego medir el invento.",
  coverageCategoryColumn: "Categoría declarada",
  coverageProgramsColumn: "Programas",
  coveragePublishSomeColumn: "Publican al menos una medida",
  coveragePublishNoneColumn: "No publican ninguna",
  coverageShareNoneColumn: "Proporción que no publica ninguna",
  coverageEntityUnstated: "Sin categoría declarada",
  coverageByTypeCaveat:
    "Las filas van ordenadas por cuántos programas tiene cada categoría, no por cuánto deja en blanco cada una. Ordenarlas por la proporción en blanco publicaría una tabla de posiciones de quién reporta menos, y arriba quedarían justo las categorías con las obligaciones de reporte más distintas, que es lo contrario de lo que muestran las cifras.",

  coverageObligationsHeading: "No todas las instituciones deben el mismo informe",
  coverageObligationsIntro:
    "Una fila en blanco solo se puede leer frente a lo que su institución estaba realmente obligada a presentar, y eso no es igual para todas las que están en la lista. Hay cuatro diferencias que pesan de verdad en las tablas de arriba, y ninguna de ellas es una institución que decida callar.",
  coverageObligationRegisteredApprenticeship:
    "Los programas de aprendizaje registrado están en la lista en condiciones distintas a las de las demás instituciones. Son elegibles por el hecho de estar registrados, mientras sigan registrados, así que nunca pasan por el proceso de elegibilidad inicial por el que sí pasan las otras. Tampoco están obligados a entregar información de desempeño como institución de capacitación elegible, dicho con esas palabras, y cuando la entregan lo hacen de forma voluntaria. Un programa de aprendizaje con la fila vacía está haciendo exactamente lo que la norma le pide.",
  coverageObligationCalifornia:
    "A todas las demás California sí se la pide. La directiva estatal vigente sobre instituciones de capacitación elegibles exime del reporte de desempeño al aprendizaje registrado y a nadie más, ni siquiera a sus colegios comunitarios ni a sus universidades públicas. Esas instituciones llegan a la lista por otra vía, por su acreditación o por su carácter de institución pública, en lugar de tener que cumplir los umbrales numéricos de desempeño que la directiva aplica a las instituciones privadas, pero la obligación de reportar es la misma que la de todas las demás. Así que una fila en blanco en un colegio no es una exención en uso. Es otra cosa, y esta página no le puede decir cuál.",
  coverageObligationAllStudents:
    "El informe federal debería describir a todas las personas que cursaron un programa de estudios, no solo a aquellas cuya capacitación pagó el sistema laboral. Pasar de lo uno a lo otro es un problema de registros: la institución entrega la lista de personas y el estado produce las cifras de empleo e ingresos cruzándola con sus registros salariales del seguro de desempleo. Donde ese cruce no se puede hacer, no hay nada que publicar sobre las personas que habría cubierto, y ninguna presentación de la institución lo produciría.",
  coverageObligationSuppression:
    "Una celda de resultados se oculta cuando el grupo detrás de ella es tan pequeño que publicar la cifra podría identificar a una persona. Es una protección de privacidad funcionando como debe, y en la fuente no se distingue de una celda que nadie llenó.",
  coverageObligationsClosing: (first: string, second: string) =>
    `En esta instantánea las dos categorías que dejan más filas vacías son ${first} y ${second}. La primera es aquella cuyo reporte el reglamento de arriba hace voluntario en vez de obligatorio. Para la segunda, y para cualquier otra fila de esa tabla, esta página no le puede decir cuál de estas explicaciones aplica a un programa concreto, ni si aplica alguna. Leer esa columna como un ranking de cumplimiento invertiría el sentido del hallazgo.`,
  coverageCitationsNote:
    "Los textos que se citan abajo, federales y estatales, se publican solo en inglés.",

  coverageCohortHeading: "Celdas en blanco frente al tamaño del grupo",
  coverageCohortIntro:
    "Si lo que hay detrás de una celda vacía es la protección de grupos pequeños, la proporción en blanco debería bajar a medida que el grupo crece. Esa es una predicción que se le puede preguntar a los datos, y preguntarla es la única forma en que esta página puede decir algo sobre por qué una celda está vacía sin inventarse un motivo.",
  coverageCohortColumn: "Personas que salieron del programa",
  coverageCohortAtLeast: (lower: string) => `${lower} o más`,
  coverageCohortRange: (lower: string, upper: string) => `de ${lower} a ${upper}`,
  coverageCohortOf: (missing: string, total: string) => `${missing} de ${total}`,
  coverageCohortCaveat:
    "Aquí solo se cuentan los grupos que una institución presentó para un único programa. Una institución que presentó un solo grupo que abarca a toda la escuela caería en el tramo más grande describiendo a una población que no es un programa. Los programas que no presentaron conteo de salidas no están en ningún tramo, porque un tamaño de grupo no declarado no es un grupo pequeño.",
  coverageCohortReading:
    "La finalización y el empleo se comportan como predice la protección de grupos pequeños: la proporción en blanco es más alta en los grupos más chicos y baja conforme crecen. Los ingresos no bajan igual. Siguen siendo la medida menos publicada en todos los tramos, incluido el más grande, donde el tamaño del grupo ya no puede ser la explicación. Lo que mantiene vacía la columna de ingresos en los programas grandes es otra cosa, no la protección de un grupo pequeño.",

  coverageProvidersHeading: "Dónde está el silencio",
  coverageProvidersBody: (silent: string, total: string, programs: string) =>
    `${silent} de las ${total} instituciones nombradas en este registro no publican nada para ninguno de los programas que presentaron, y entre todas suman ${programs} programas. Todos los demás programas con la fila vacía pertenecen a una institución que sí publicó algo en alguna parte, y eso vale la pena saberlo: en la mayor parte del hueco la relación de reporte existe y lo que falta es una medida concreta.`,

  coverageMethodHeading: "Cómo cuenta esta página",
  coverageMethodSource:
    "La fuente es el informe de desempeño de instituciones de capacitación elegibles del Departamento de Trabajo de EE. UU., el ETA-9171 que los estados presentan bajo la Ley de Innovación y Oportunidad en la Fuerza Laboral y que el Departamento debe publicar. Los programas de California se leen completos, sin muestreo y sin exclusiones. Cada cifra de esta página es un conteo hecho sobre ese registro al construir el sitio, y ninguna está escrita a mano en el texto.",
  coverageMethodBlankHeading: "Qué significa exactamente un espacio en blanco",
  coverageMethodBlank:
    "El informe federal escribe un mismo valor centinela dondequiera que una medida no traiga cifra, y su propio diccionario de datos dice que ese único valor cubre tres situaciones distintas: un grupo demasiado pequeño para publicarlo sin identificar a alguien, ningún dato reportado para el programa, y datos en los que el Departamento encontró problemas serios de calidad. Un centinela, tres causas y ninguna manera de distinguirlas desde fuera. Por eso esta página no las separa, y cualquier página que diga separarlas se inventó la distinción. Lo que el registro sí sostiene es una división distinta y más estrecha: si describió a un grupo o no.",
  coverageMethodThreshold:
    "Tampoco hay un número publicado detrás de la primera de esas tres causas. La regla es un criterio, no un umbral: no se exige desglosar los datos cuando el conteo es demasiado pequeño para ser estadísticamente confiable o cuando publicarlo revelaría algo sobre una persona participante concreta. Ningún tamaño mínimo de celda aparece en la guía de reporte, ni en las instrucciones del formulario, ni en el diccionario de datos, así que esta página tampoco enuncia ningún umbral, y la tabla por tamaño de grupo de arriba describe lo que hacen los datos publicados, no reconstruye una regla.",
  coverageMethodStates:
    "«Publicada» significa que la medida trae cifra. «En blanco junto a un grupo declarado» significa que el registro dice cuántas personas fueron atendidas, salieron o terminaron, y deja vacía esa medida en particular. «Sin registro de desempeño» significa que no dice ni lo uno ni lo otro, así que de ese programa no se presentó nada sobre resultados, en ninguna forma.",
  coverageMethodZeroHeading: "Una cifra oculta no es un cero",
  coverageMethodZero:
    "Nada en esta página suma, promedia, ordena ni muestra una medida faltante como si fuera cero. Una tasa de finalización oculta no es una finalización de cero, y un programa con la fila vacía no sacó mala nota: no lo calificaron. Cuando en estos datos hay un cero realmente reportado, se trata como el hallazgo real y serio que es, y se mantiene claramente separado de una celda vacía.",
  coverageMethodFloorHeading: "Cuándo se omite una proporción",
  coverageMethodFloor: (minimum: string) =>
    `Un porcentaje se publica solo cuando hay al menos ${minimum} registros detrás. Por debajo de eso un solo registro mueve la respuesta más de tres puntos, que es más precisión de la que aguanta el denominador, así que se publican los conteos y se omite la proporción. Es la misma regla que este proyecto aplica a toda cifra que no puede sostener.`,
  coverageMethodLimitsHeading: "Qué no afirma esta página",
  coverageMethodLimits:
    "No afirma que la propia lista de California contenga los mismos programas que el archivo federal. El estado no publica una descarga con la cual comprobarlo, y ese es justamente el hueco en el que vive esta página entera. No afirma saber por qué está vacía ninguna celda concreta. No clasifica instituciones, categorías ni agencias, y no saca ninguna conclusión sobre la calidad de un programa a partir de que haya o no haya una cifra sobre él. Y el rango de años de programa que aparece junto a cada cifra está citado de la página «About» del informe federal, no medido en los datos, porque los datos no traen ese campo: si esa frase cambia en el origen, esta página no se va a enterar sola.",
  coverageMethodRebuild:
    "El conjunto de datos detrás de esta página se reconstruye desde las fuentes públicas con una tubería documentada, y el conteo lo hace un módulo con pruebas, no una persona a mano. Cualquiera puede reproducirlo.",

  coverageCiteHeading: "Cómo citar o corregir esta página",
  coverageCiteBody: (date: string) =>
    `Si va a citar una cifra de esta página, cite también la fecha de consulta: el registro de base se consultó el ${date}, y el informe federal se actualiza cada cierto tiempo, así que una cifra de aquí puede ir por detrás de la fuente sin que ninguna de las dos esté mal. Esta página tiene una dirección estable y va a seguir respondiendo la misma pregunta conforme cambien los datos que tiene debajo.`,
  coverageCiteCorrections:
    "Si usted trabaja con estos datos y aquí hay algo mal leído, la corrección es bienvenida y se hará. Eso incluye las obligaciones de reporte descritas arriba: son la parte de esta página menos visible en los datos mismos y la más fácil de entender mal desde fuera.",

  ctdlTitle: "La exportación CTDL: qué lleva y qué no",
  ctdlLede:
    "Este proyecto publica los programas de capacitación de California en CTDL, el vocabulario que mantiene Credential Engine para describir credenciales y oportunidades de aprendizaje. Esta página es el informe que la exportación hace de sí misma: qué clases y propiedades llena, qué dice el registro de origen que ella descarta, y qué encontró un validador independiente al revisar el resultado.",
  ctdlWhy:
    "Una correspondencia solo vale algo si alguien puede comprobarla. Por eso las cifras de aquí las produce la exportación en el momento de ejecutarse, las omisiones se cuentan igual que la cobertura, y los hallazgos del validador se publican salgan como salgan.",

  ctdlBoundaryHeading: "Qué no es esto",
  ctdlBoundaryRegistry:
    "Nada de esto se ha publicado en el Credential Registry. Ni un envío, ni una prueba, nada. Los registros existen como archivos en este proyecto y en ningún otro lugar.",
  ctdlBoundaryEndorsement:
    "Esto no está afiliado a Credential Engine ni cuenta con su respaldo o revisión. Ellos publican CTDL de forma abierta y este proyecto lo lee; ahí termina la relación.",
  ctdlBoundaryCtids:
    "Los identificadores se derivan localmente y no los asigna el Registry. Un CTID real se emite cuando un recurso se publica en el Registry, y estos no lo están; las direcciones de los identificadores viven a propósito en el servidor de este proyecto y no en un dominio del registro.",
  ctdlBoundaryDemo:
    "Es una demostración de disciplina en la correspondencia, no una publicación en producción. Existe para mostrar cómo una fuente pública se corresponde con un vocabulario público, y qué se pierde en el camino.",

  ctdlStamp: (snapshot: string) =>
    `Contado a partir de la exportación de la instantánea de datos del ${snapshot}, en el momento en que esa exportación se ejecutó.`,
  ctdlSnapshotMismatch: (exportSnapshot: string, siteSnapshot: string) =>
    `Nota: esta exportación describe la instantánea del ${exportSnapshot} y el resto del sitio está sirviendo ahora la del ${siteSnapshot}. Las cifras de abajo describen la exportación, no las páginas que la rodean.`,

  ctdlCoverageHeading: "Qué contiene la exportación",
  ctdlCoverageIntro:
    "Una entidad por programa de capacitación, una por cada nombre distinto de institución tal como fue reportado, y un perfil de estadísticas por cada programa que reporta al menos un resultado. Un programa que no reportó nada no recibe perfil alguno: uno vacío se leería como «se midió, y salió vacío».",
  ctdlEntityColumn: "Clase de CTDL",
  ctdlEntityCountColumn: "Entidades",

  ctdlPropertiesHeading: "Qué propiedades están llenas",
  ctdlPropertiesIntro:
    "Cada propiedad de abajo se emite solo donde la fuente afirmó algo. Un vacío es un vacío: sin relleno, sin ceros y sin nada deducido de un campo vecino. El orden es el propio de la exportación, no el de las mejor cubiertas primero.",
  ctdlPropertyColumn: "Propiedad",
  ctdlPropertyCountColumn: "Programas que la llevan",
  ctdlPropertyShareColumn: "Proporción",

  ctdlMeasuresHeading: "Qué medidas de resultados se proyectan",
  ctdlMeasuresIntro:
    "Cada medida reportada se convierte en una métrica y una observación dentro del perfil de estadísticas del programa. La proporción se calcula sobre los programas que tienen perfil, no sobre todos: una medida que falta porque el programa no reportó nada es un hecho distinto de una medida que falta en un programa que sí reportó otra cosa.",
  ctdlMeasureColumn: "Medida",
  ctdlMeasureCountColumn: "Observaciones",
  ctdlMeasureShareColumn: "De los programas con algún resultado",

  ctdlGapsHeading: "Qué no lleva la exportación",
  ctdlGapsIntro:
    "El registro de origen dice más de lo que esta exportación proyecta. Contar solo lo emitido describiría una proyección como si fuera el registro entero, así que los campos descartados también se cuentan, junto con el término de CTDL que habría podido llevar cada uno cuando ese término existe.",
  ctdlGapsReading:
    "Donde se nombra un término de CTDL, el vocabulario tiene dónde poner ese dato y la exportación no lo usa. Eso es una carencia de la exportación, no un límite de CTDL, y se dice así en vez de dejar que quien lea lo deduzca de una ausencia.",
  ctdlGapColumn: "Qué dice la fuente",
  ctdlGapProgramsColumn: "Programas que lo reportan",
  ctdlGapTermColumn: "Término de CTDL que lo llevaría",
  ctdlGapNoTerm: "Ninguno en uso",
  ctdlGapFieldsLabel: "Campos de origen",
  ctdlCostFloor: (n: string) =>
    `Aparte, ${n} programa(s) reportan un costo total que, por tener un componente suprimido, es un mínimo y no un precio. La propiedad de precio de CTDL no tiene forma de decir «al menos», así que para esos no se publica costo alguno en vez de publicar un mínimo como si fuera la tarifa.`,

  ctdlGapOutcomeMeasures: "Cuatro de las nueve medidas de resultados reportadas",
  ctdlGapOutcomeMeasuresWhy:
    "La fuente reporta nueve medidas de desempeño de WIOA y esta exportación proyecta cinco. El total de personas atendidas, el total que salió, el total que completó y el empleo en el cuarto trimestre tras la salida se reportan y no se llevan. La capa de estadísticas podría expresarlas exactamente igual que a las cinco que sí van.",
  ctdlGapProgramLength: "Cuánto dura el programa",
  ctdlGapProgramLengthWhy:
    "CTDL tiene una propiedad para la duración estimada de una oportunidad de aprendizaje. La duración en semanas y horas de la fuente no se lleva, ni tampoco la marca de programa por competencias, que significa que el programa termina cuando la persona sabe hacer el trabajo y por diseño no tiene duración fija.",
  ctdlGapProgramFormat: "En línea, presencial o ambos",
  ctdlGapProgramFormatWhy:
    "CTDL tiene una propiedad de modalidad, pero su valor debe ser un concepto de un vocabulario controlado que credreg.net publica como página web y no como datos. Esta exportación no emite ningún concepto que no pueda contrastar con datos legibles por máquina, así que la modalidad no se lleva.",
  ctdlGapInstructionalProgramCode: "El código CIP del campo de estudio",
  ctdlGapInstructionalProgramCodeWhy:
    "CTDL tiene una propiedad de programa instruccional que admite una correspondencia CIP, con la misma forma que esta exportación ya usa para el código SOC de la ocupación. El código CIP que reportó la fuente no se lleva.",
  ctdlGapProgramLocation: "Dónde se imparte el programa",
  ctdlGapProgramLocationWhy:
    "CTDL tiene una propiedad para dónde está disponible una oportunidad de aprendizaje. Ni la ubicación del programa ni la región que este proyecto deriva de ella se llevan. Por una razón distinta, tampoco se pone dirección a la organización: la ubicación de un registro es la del programa, no necesariamente la de la institución.",
  ctdlGapProviderCategory: "Qué tipo de institución es",
  ctdlGapProviderCategoryWhy:
    "La categoría de institución de la fuente no se corresponde con el vocabulario de sector de CTDL sin decisiones de criterio, y ese vocabulario se publica como página web y no como datos. La organización lleva el nombre que reportó la fuente y nada más.",
  ctdlGapWioaFundedCost: "Cuánto cuesta a quien recibe fondos de WIOA",
  ctdlGapWioaFundedCostWhy:
    "Ese es otro costo y otro pagador, y CTDL puede llevarlo como un segundo perfil de costo distinguido por un concepto de un vocabulario publicado como página web y no como datos. Solo se lleva el total de gasto de bolsillo.",
  ctdlGapOccupationProjections: "La proyección estatal a diez años de la ocupación",
  ctdlGapOccupationProjectionsWhy:
    "Esta exportación proyecta el registro federal de capacitación. Las proyecciones de California para la ocupación a la que lleva cada programa — salario mediano, vacantes previstas, crecimiento — se unen al programa en todo el resto de este sitio y aquí no se llevan. Describen una ocupación y no este programa, y colgarlas del programa afirmaría que el programa lleva a ese salario, cosa que la fuente no dice. El código de la ocupación sí se lleva, de modo que la correspondencia queda dicha y la proyección no.",

  ctdlValidationHeading: "Qué encontró un validador independiente",
  ctdlValidationIntro: (tool: string, version: string) =>
    `La exportación se revisa a sí misma, pero todas esas revisiones las escribió la misma mano que la exportación, sobre la misma lectura del mismo esquema, que es justo la lectura a la que un error sobreviviría. Por eso también pasa por ${tool} ${version}, una herramienta aparte con sus propias copias del esquema de Credential Engine y una cita para cada regla que aplica. No hace ninguna petición de red ni envía nada a ningún sitio.`,
  ctdlValidationEntities: (n: string) => `Se revisaron ${n} entidades.`,
  ctdlValidationSeverityColumn: "Gravedad",
  ctdlValidationCountColumn: "Hallazgos",
  ctdlSeverityError: "Error (bloqueante)",
  ctdlSeverityWarning: "Advertencia",
  ctdlSeverityInfo: "Información",
  ctdlSeverityUnverifiable: "No verificable",
  ctdlValidationResult:
    "Ningún error, y una advertencia en todas las entidades del grafo. La advertencia es la tensión que esta exportación ya tenía anotada: la gramática publicada dice que un identificador es un UUID aleatorio, y una exportación que debe producir los mismos identificadores cada vez no puede usar uno aleatorio. No salió nada más: ninguna propiedad usada en una clase que no la declara, ninguna referencia que apunte a la nada, ninguna relación afirmada en un sentido y contradicha en el otro, ningún término inventado.",
  ctdlValidationUnaccepted:
    "Esta ejecución devolvió un hallazgo sobre el que nadie ha razonado. La exportación se niega a publicar en ese estado, así que si usted está leyendo esta frase en una página en vivo, algo va mal y la corrección es bienvenida.",
  ctdlFindingCodeColumn: "Hallazgo",
  ctdlFindingCountColumn: "Veces",
  ctdlFindingEntitiesColumn: "Entidades",
  ctdlFindingStateColumn: "Estado",
  ctdlFindingAccepted: "Aceptado, con motivo",
  ctdlFindingUnaccepted: "No aceptado",
  ctdlFindingsNote:
    "Un hallazgo aceptado es una decisión anotada, no un filtro: sigue contado aquí y en la declaración legible por máquina. Cualquier hallazgo cuyo código no se haya razonado hace fallar la exportación en vez de aparecer discretamente entre los demás.",

  ctdlScopeHeading: "Qué pudo y qué no pudo juzgar el validador",
  ctdlScopeBody: (
    knownClasses: string,
    classes: string,
    knownProperties: string,
    properties: string,
  ) =>
    `Un resultado limpio alcanza solo hasta donde llega el vocabulario que tiene quien revisa. Este basa sus comprobaciones estructurales en los documentos de esquema centrales que lleva consigo, así que estuvo en condiciones de juzgar ${knownClasses} de las ${classes} clases y ${knownProperties} de las ${properties} propiedades que emite esta exportación.`,
  ctdlScopeUnjudged:
    "El resto es la capa de estadísticas de resultados, que publica su propio documento de esquema que el validador no lleva, más una propiedad de moneda. Un término del que quien revisa nunca ha oído hablar es uno que se abstiene de juzgar, no uno que aprueba.",
  ctdlScopeCaveat:
    "Esos términos los revisó la propia exportación contra el esquema de estadísticas, obtenido y anotado en la procedencia de este proyecto. Esa es una garantía más débil que una opinión de fuera, y así se dice.",
  ctdlScopeClassesLabel: "Clases no juzgadas",
  ctdlScopePropertiesLabel: "Propiedades no juzgadas",

  ctdlMappingHeading: "En qué se apoya cada correspondencia",
  ctdlMappingIntro:
    "Cada clase y cada propiedad de aquí se eligió contra una definición publicada y no de memoria, y la exportación se niega, al construirse, a emitir un término que el vocabulario no defina. Estas son las definiciones primarias, no resúmenes de ellas.",
  ctdlMappingCitationsNote:
    "Credential Engine las publica solo en inglés, por lo que aquí van marcadas como inglés.",
  ctdlExportSourceLink:
    "Leer la exportación, con el motivo anotado junto a cada correspondencia",

  ctdlGetHeading: "Cómo obtener la exportación y cómo reconstruirla",
  ctdlGetIntro:
    "El grafo son unos 17 MB de JSON-LD: demasiado grande para versionarlo y demasiado propio de una instantánea concreta como para servirlo como si fuera actual. Se construye a demanda y se empaqueta con una suma de verificación, y las dos declaraciones que esta página muestra se publican junto a él.",
  ctdlGetStatements: "Las declaraciones con las que se arma esta página, tal como se publican:",
  ctdlGetCoverageFile: "Declaración de cobertura (qué se lleva y qué no)",
  ctdlGetValidationFile: "Declaración de validación (qué encontró el validador)",
  ctdlGetReproduce:
    "Para reconstruir el grafo desde el origen: clone el repositorio, ejecute la canalización que descarga los datos públicos federales y estatales, y luego ejecute la exportación y la validación. Ambas son un solo comando y ambas son deterministas: la misma instantánea produce siempre una salida idéntica byte a byte, así que una reconstrucción se puede comparar directamente con una publicada.",
  ctdlGetReleases: "Las exportaciones empaquetadas se publican como releases:",

  ctdlCiteHeading: "Correcciones",
  ctdlCiteBody:
    "Si alguna correspondencia de aquí está mal, o una propiedad se usa de un modo que el esquema no pretende, eso merece un reporte. Esto es una demostración y su razón de ser es poder comprobarse; una corrección de alguien que trabaja con este vocabulario es lo más útil que esta página podría producir.",
};

function fmt(n: number): string {
  return new Intl.NumberFormat("en-US").format(n);
}

const DICTIONARIES: Record<Lang, Dictionary> = { en, es };

export function dict(lang: Lang): Dictionary {
  return DICTIONARIES[lang];
}

export const OTHER_LANG: Record<Lang, Lang> = { en: "es", es: "en" };
export const LANG_NAME: Record<Lang, string> = { en: "English", es: "Español" };

/**
 * Spanish for the provider categories the federal feed files, and nothing else.
 *
 * Deliberately outside the dictionary. Everything in `en` and `es` is text this project
 * wrote; these are keys the U.S. Department of Labor writes, and the map is a lookup on a
 * value that arrives from outside rather than a string with an English original to be
 * translated from. Keeping it separate also keeps the completeness test honest: a nested
 * object inside the dictionary would satisfy that test without any of its contents being
 * checked.
 *
 * Only the categories present in California's record are here. A category this map has never
 * seen falls back to the filed English, which is the correct answer rather than a failure:
 * inventing a Spanish name for a federal classification nobody has read would be worse than
 * showing the one the record actually carries. `translated` tells the caller which happened,
 * so an untranslated fallback can be marked `lang="en"` for a screen reader, the same way
 * every other English-only feed string on a Spanish page is.
 */
const ENTITY_TYPE_ES: Record<string, string> = {
  Public: "Pública",
  "Private For-Profit": "Privada con fines de lucro",
  "Private Non-Profit": "Privada sin fines de lucro",
  "Higher Ed: Associate's Degree": "Educación superior: grado de asociado",
  "Higher Ed: Baccalaureate or Higher": "Educación superior: licenciatura o más",
  "Higher Ed: Certificate of Completion": "Educación superior: certificado de finalización",
  "National Apprenticeship": "Aprendizaje registrado",
  Other: "Otra",
};

export interface EntityTypeLabel {
  text: string;
  /** False when the filed English is being shown because no translation exists for it. */
  translated: boolean;
}

export function entityTypeLabel(lang: Lang, filed: string): EntityTypeLabel {
  if (lang === "en") return { text: filed, translated: true };
  const translation = ENTITY_TYPE_ES[filed];
  return translation === undefined
    ? { text: filed, translated: false }
    : { text: translation, translated: true };
}
