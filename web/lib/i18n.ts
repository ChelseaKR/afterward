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
    "Occupation titles and program descriptions appear in English on Spanish pages. The interface and the controlled vocabularies are translated; the open-ended text from the federal and state feeds is not, because it is published in English only.",
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
  // The single "Usually needs" category is the federal judgement of what a person typically
  // needs to enter. It is not what people have: on 60 California occupations it names a
  // credential most people doing the job do not hold, and on 135 program pages it is withheld
  // outright because it was assigned to a whole group of occupations. The distribution is the
  // second fact, and it is published as a second fact — never in the row the category vacated.
  attainmentHeading: "What people in this job actually studied",
  // The seven Census attainment levels, shortened for a list a reader scans rather than
  // reads. Deliberately not borrowed from the education vocabulary the "Usually needs" row
  // uses: these are a different scale answering a different question, and wording them
  // identically would invite exactly the subtraction the note underneath rules out. One of
  // the seven — "Less than high school diploma" — has no entry in that vocabulary at all.
  eduLevelNoHs: "No high school diploma",
  eduLevelHs: "High school diploma",
  eduLevelSomeCollege: "Started college, no degree",
  eduLevelAssociate: "Two-year degree",
  eduLevelBachelor: "Four-year degree",
  eduLevelMaster: "Master's degree",
  eduLevelDoctorate: "Doctorate or professional degree",
  attainmentTop: (level: string, share: string) =>
    `Most common: ${level} — ${share} of the people doing this work.`,
  attainmentBelow: (level: string, share: string) =>
    `California says this job usually needs: ${level}. ${share} of the people doing it went less far than that.`,
  // 1,274 of the program-to-occupation attachments here state "Postsecondary non-degree
  // award", which is not a step on the attainment scale at all. Counting who "meets" it is
  // not possible, and a number invented for the sentence would look exactly like a real one.
  attainmentNoCompare: (level: string) =>
    `California says this job usually needs: ${level}. That is not one of the steps below, so there is no way to count how many people meet it.`,
  attainmentNational:
    "This counts people already doing this job, across the whole United States. Every other figure on this page is California's, and the federal government publishes no state version of this one.",
  attainmentNotRule:
    "It is what people happen to have, not a rule about who gets hired. A small row does not mean you would be turned away, and a large one is not a promise of a job.",
  attainmentScale:
    "It is also measured on a different scale from “Usually needs” above, so the two cannot be subtracted from one another.",
  attainmentMeasuredFor: (title: string) =>
    `Measured for ${title}, the wider group this job is counted inside.`,

  /* ---- Someone else may be able to pay for this ------------------------------------------
   *
   * Every program on this site was on California's Eligible Training Provider List when the
   * state last reported it, and under 20 CFR 680.410 that listing is what allows an Individual
   * Training Account to pay a provider for somebody's training. The site never said so, and a
   * reader who could have had a program paid for had no way to find that out here.
   *
   * The English below is not written here. Every string from `fundingLede` to the last
   * `fundingWhy…` is copied byte for byte from `camino.sources.local_help`, where each sentence
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
   * readers least able to absorb an error, and it has not had a native reviewer. Saying so
   * is the honest move — but a bare "may contain errors" gives a reader nothing to do, so it
   * names English as the reference text and points at the people who actually decide. It
   * deliberately does not promise that anyone at the center speaks Spanish: the directory's
   * language field was blank for nine of ten centers sampled, so that claim is unsupported.
   */
  fundingTranslationNote:
    "This section was translated without a professional review, and the English text is the reference version. If anything here is unclear, ask at the center — they are the ones who decide.",
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
    "Los nombres de las ocupaciones y las descripciones de los programas aparecen en inglés en las páginas en español. La interfaz y los vocabularios controlados sí están traducidos; el texto libre que viene de las fuentes federales y estatales no, porque solo se publica en inglés.",
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

  // ---- Qué estudiaron en realidad las personas que tienen este trabajo ----
  attainmentHeading: "Qué estudió en realidad la gente que tiene este trabajo",
  eduLevelNoHs: "Sin diploma de preparatoria",
  eduLevelHs: "Diploma de preparatoria",
  eduLevelSomeCollege: "Empezó la universidad, sin título",
  eduLevelAssociate: "Título de dos años",
  eduLevelBachelor: "Título de cuatro años",
  eduLevelMaster: "Maestría",
  eduLevelDoctorate: "Doctorado o título profesional",
  attainmentTop: (level: string, share: string) =>
    `Lo más común: ${level} — el ${share} de quienes hacen este trabajo.`,
  attainmentBelow: (level: string, share: string) =>
    `California dice que este trabajo suele requerir: ${level}. El ${share} de quienes lo hacen llegó menos lejos que eso.`,
  attainmentNoCompare: (level: string) =>
    `California dice que este trabajo suele requerir: ${level}. Eso no es uno de los niveles de abajo, así que no hay manera de contar cuánta gente lo cumple.`,
  attainmentNational:
    "Aquí se cuenta a personas que ya tienen este trabajo, en todo Estados Unidos. Todas las demás cifras de esta página son de California, y el gobierno federal no publica una versión estatal de esta.",
  attainmentNotRule:
    "Es lo que la gente tiene, no una regla sobre a quién contratan. Una fila pequeña no significa que a usted lo rechazarían, y una grande no es promesa de empleo.",
  attainmentScale:
    "Además se mide en una escala distinta de la de «Suele requerir» arriba, así que no se pueden restar una de otra.",
  attainmentMeasuredFor: (title: string) =>
    `Medido para ${title}, el grupo más amplio dentro del cual se cuenta este trabajo.`,

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
    "Esta sección se tradujo sin revisión profesional y la versión en inglés es la de referencia. Si algo aquí no queda claro, pregúntelo en el centro: son ellos quienes deciden.",
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
