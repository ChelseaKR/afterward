/**
 * How much of California's ETPL outcome data is actually published.
 *
 * California's Eligible Training Provider List exists only as a CalJOBS search screen, and
 * the state publishes no downloadable file of its programs and their results. The federal
 * ETP Scorecard (ETA-9171) is where those same programs are reported, so it is the only
 * public record from which the question "how much of this is filled in?" can be answered at
 * all. This module answers it by counting, and nothing else in this file asserts anything a
 * count cannot support.
 *
 * Three commitments carry over from the rest of the project and constrain every function
 * here:
 *
 * 1. A null measure is not a zero. Nothing below sums, averages or sorts a null as if it
 *    were one; nulls are counted as their own category and reported as such.
 * 2. Absence is not delinquency. This module measures records, not organisations. Several
 *    provider categories have different federal reporting obligations, so a category with a
 *    high blank rate is a fact about obligations and data plumbing before it is a fact about
 *    anyone's conduct, and the page built on this must say so.
 * 3. A share over a tiny denominator is not published as a share. See `MIN_RATE_DENOMINATOR`.
 *
 * Everything is a pure function over program records, so the numbers are testable without a
 * dataset, a network, or a browser.
 */

import { slugify } from "./providers";
import type { Program, ProgramOutcomes } from "./types";

/**
 * The outcome measures the pipeline ingests from the ETP Scorecard, in reading order.
 *
 * This list is the feed's, not this page's: every key here is a column
 * `afterward.sources.dol_etp` parses, and no measure is invented, derived or combined. Order
 * runs from the widest population (everyone served) to the narrowest and latest-arriving
 * (earnings two quarters after exit), which is also roughly the order in which they go
 * blank.
 */
export const MEASURE_KEYS = [
  "total_served",
  "total_exited",
  "total_completed",
  "completion_rate",
  "credentials_earned",
  "employed_q2",
  "employment_rate_q2",
  "employed_q4",
  "median_earnings",
] as const;

export type MeasureKey = (typeof MEASURE_KEYS)[number];

/**
 * The three measures a program has to be silent on before this project calls it silent.
 *
 * Deliberately the same three the pipeline's own `outcomes.reported` flag uses, so the
 * headline on this page and the "reports any outcome" figure in the site's footer cannot
 * disagree. They are the three the ETP Scorecard is built around: did people finish, did
 * they work, what did they earn.
 */
export const HEADLINE_MEASURES = [
  "completion_rate",
  "employment_rate_q2",
  "median_earnings",
] as const satisfies readonly MeasureKey[];

/**
 * The counts that constitute a claim about who was measured.
 *
 * A record carrying any of these has described a cohort, which is what makes an empty
 * measure beside it a different fact from a record that describes nobody at all.
 */
const COHORT_COUNTS = ["total_served", "total_exited", "total_completed"] as const;

/**
 * Smallest denominator this module will publish a percentage over.
 *
 * Not a convention borrowed from anywhere: at n = 30 a single record moves the share by 3.3
 * points, and below that the reader is being invited to read precision the denominator
 * cannot carry. The underlying counts are still published, since they are real and a band of
 * four programs is a finding about the band, but the share is withheld, which is the same
 * rule this dataset applies to every other figure it cannot stand behind.
 */
export const MIN_RATE_DENOMINATOR = 30;

/**
 * A share, or null when the denominator is too small or absent to carry one.
 *
 * Returns null rather than 0 for an empty denominator, for the reason the whole project
 * exists: 0% is a measurement and "we did not measure this" is not.
 */
export function share(numerator: number, denominator: number): number | null {
  if (denominator < MIN_RATE_DENOMINATOR) return null;
  return numerator / denominator;
}

/** True when this record makes any claim at all about the size of a cohort. */
export function filedACohort(outcomes: ProgramOutcomes): boolean {
  return COHORT_COUNTS.some((key) => outcomes[key] !== null);
}

/**
 * Why one measure on one record is empty, as far as the published record can say.
 *
 * The scorecard writes one sentinel, `-1`, for three different things. Its published data
 * dictionary (v4.0, 2024-05-15) says a value is suppressed from public view when "data
 * submitted for the program contains sample sizes that are too small to protect Personally
 * Identifiable Information", when "no data were reported for the program", or when "the
 * Department identified significant data quality issues with the state submitted data". One
 * sentinel, three causes, no way to tell them apart from the outside. So this does not claim
 * to know which. It draws the line the record *can* support, which is whether a cohort was
 * described at all:
 *
 * - `reported`: the measure has a value.
 * - `blank`: the record describes a cohort and leaves this measure empty. Consistent with
 *   every one of the three causes above. The record cannot tell you which, and neither
 *   will this.
 * - `unfiled`: the record describes no cohort and carries no measure. Nothing about
 *   performance was filed for this program at all.
 */
export type MeasureState = "reported" | "blank" | "unfiled";

export function measureState(outcomes: ProgramOutcomes, key: MeasureKey): MeasureState {
  if (outcomes[key] !== null) return "reported";
  return filedACohort(outcomes) ? "blank" : "unfiled";
}

/**
 * Which absence a program page is looking at when all three headline measures are empty.
 *
 * The same split this page already publishes as `silentWithACohort` and `silentWithNoRecord`,
 * exported because a program page needs it too and had been printing the wrong half of it.
 * Of California's 1,209 silent programs, 42 filed a count of the people they served, exited
 * or completed. Their pages printed that count -- "People enrolled 16" -- and then, directly
 * underneath, "No outcomes reported for this program", which the number above it contradicts.
 * Two of the 42 also filed how many people were working a year on.
 *
 * Naming what is absent is not a smaller claim than "nothing", it is a truer one: the reader
 * is deciding whether to spend a year and several thousand dollars, and "this provider
 * reported nothing" is a sentence about a named college that the federal record does not
 * support. A limitation of what this project counts must not arrive on the page as a fact
 * about a provider.
 */
export type UnreportedNotice = "silentWithACohort" | "silentWithNoRecord";

export function unreportedNotice(outcomes: ProgramOutcomes): UnreportedNotice {
  return filedACohort(outcomes) ? "silentWithACohort" : "silentWithNoRecord";
}

/** One measure's coverage across a set of programs. */
export interface MeasureCoverage {
  key: MeasureKey;
  programs: number;
  reported: number;
  blank: number;
  unfiled: number;
  /** Blank plus unfiled, over all programs. Null below `MIN_RATE_DENOMINATOR`. */
  missingShare: number | null;
}

export function measureCoverage(programs: readonly Program[], key: MeasureKey): MeasureCoverage {
  let reported = 0;
  let blank = 0;
  let unfiled = 0;

  for (const program of programs) {
    const state = measureState(program.outcomes, key);
    if (state === "reported") reported += 1;
    else if (state === "blank") blank += 1;
    else unfiled += 1;
  }

  return {
    key,
    programs: programs.length,
    reported,
    blank,
    unfiled,
    missingShare: share(blank + unfiled, programs.length),
  };
}

/**
 * How a set of programs divides on the headline question: any outcome at all, or none.
 *
 * `silentWithACohort` is the small and interesting remainder, a provider that told the
 * federal record how many people it served and then published no completion, employment or
 * earnings figure for any of them. It is separated out because collapsing it into "silent"
 * would describe a record that exists as a record that does not.
 */
export interface HeadlineCoverage {
  programs: number;
  reporting: number;
  silent: number;
  silentWithACohort: number;
  silentWithNoRecord: number;
  /** Share of programs publishing no headline measure. Null below the denominator floor. */
  silentShare: number | null;
}

export function headlineCoverage(programs: readonly Program[]): HeadlineCoverage {
  let reporting = 0;
  let silentWithACohort = 0;
  let silentWithNoRecord = 0;

  for (const program of programs) {
    // Read the three measures rather than trusting the `reported` flag beside them, so this
    // page cannot quietly disagree with its own per-measure table if the flag ever drifts.
    const any = HEADLINE_MEASURES.some((key) => program.outcomes[key] !== null);
    if (any) reporting += 1;
    else if (filedACohort(program.outcomes)) silentWithACohort += 1;
    else silentWithNoRecord += 1;
  }

  const silent = silentWithACohort + silentWithNoRecord;
  return {
    programs: programs.length,
    reporting,
    silent,
    silentWithACohort,
    silentWithNoRecord,
    silentShare: share(silent, programs.length),
  };
}

/**
 * The provider category as the filer wrote it in the federal record.
 *
 * `entity_type` is self-declared and is not a clean partition of California's training
 * system: this snapshot files community colleges under both "Public" and "Higher Ed:
 * Associate's Degree", and adult schools, regional occupational programs and county offices
 * of education all arrive as "Public". The category is therefore reported here as the filer's
 * own classification and never re-derived from a provider's name, which would be this project
 * inventing a taxonomy and then measuring it.
 */
export const UNSTATED_ENTITY_TYPE = "__unstated__";

export function entityTypeOf(program: Program): string {
  return program.entity_type ?? UNSTATED_ENTITY_TYPE;
}

export interface EntityTypeCoverage {
  entityType: string;
  programs: number;
  reporting: number;
  silent: number;
  /** Share of this category's programs publishing no headline measure. */
  silentShare: number | null;
  /** Reported counts for each headline measure, in `HEADLINE_MEASURES` order. */
  reportedByMeasure: Record<(typeof HEADLINE_MEASURES)[number], number>;
}

/**
 * Coverage per provider category, largest category first.
 *
 * Ordered by size rather than by blank rate. Ranking categories by how much they leave empty
 * would publish a league table of who reports least, which is the reading this page exists to
 * prevent: the two categories with the most blanks in California are the two with the most
 * distinct federal reporting obligations, and a sorted column would put them at the top with
 * an implied verdict attached.
 */
export function coverageByEntityType(programs: readonly Program[]): EntityTypeCoverage[] {
  const groups = new Map<string, Program[]>();
  for (const program of programs) {
    const key = entityTypeOf(program);
    const bucket = groups.get(key);
    if (bucket === undefined) groups.set(key, [program]);
    else bucket.push(program);
  }

  const rows: EntityTypeCoverage[] = [];
  for (const [entityType, members] of groups) {
    const headline = headlineCoverage(members);
    const reportedByMeasure = {} as EntityTypeCoverage["reportedByMeasure"];
    for (const key of HEADLINE_MEASURES) {
      reportedByMeasure[key] = members.filter((p) => p.outcomes[key] !== null).length;
    }
    rows.push({
      entityType,
      programs: members.length,
      reporting: headline.reporting,
      silent: headline.silent,
      silentShare: headline.silentShare,
      reportedByMeasure,
    });
  }

  // Size first, then the filed name, so two categories of equal size do not swap places
  // between builds and make a diff of this page look like a change in the data.
  rows.sort((a, b) => b.programs - a.programs || a.entityType.localeCompare(b.entityType));
  return rows;
}

/**
 * Which side of the reporting pipeline each measure arrives from.
 *
 * Not a distinction this project invented, and the reason it is worth drawing: DOL's ETP
 * reporting guidance assigns the elements to different collectors. The counts of who was
 * served, who left, who finished and who earned a credential are the training provider's to
 * supply. The employment and earnings elements are produced by the State by matching the
 * provider's roster against unemployment-insurance wage records, a duty 20 CFR 677.230(e)(1)
 * places on the State rather than on the provider.
 *
 * The two rates are grouped by where their inputs come from. Completion divides one
 * provider-supplied count by another. The employment rate's numerator is a wage-match
 * element, so it travels with the wage match.
 *
 * Nothing here asserts that one route works better than the other. It is a grouping, and
 * `reportingRouteSplit` reports only whether the published data happens to separate along it.
 */
export const PROVIDER_FILED_MEASURES = [
  "total_served",
  "total_exited",
  "total_completed",
  "completion_rate",
  "credentials_earned",
] as const satisfies readonly MeasureKey[];

export const WAGE_MATCH_MEASURES = [
  "employed_q2",
  "employment_rate_q2",
  "employed_q4",
  "median_earnings",
] as const satisfies readonly MeasureKey[];

export interface ReportingRouteSplit {
  /** The least-published measure the provider supplies. */
  providerFloor: MeasureCoverage | null;
  /** The most-published measure the State produces by wage match. */
  wageMatchCeiling: MeasureCoverage | null;
  /**
   * True only when the two groups do not overlap at all: every measure the provider supplies
   * is published more often than every measure the wage match produces.
   *
   * A guard rather than a headline. The page renders the sentence about this only when it is
   * true, so a refresh in which the pattern softens deletes the claim instead of leaving a
   * stale one on a page whose whole subject is figures going stale.
   */
  separated: boolean;
}

export function reportingRouteSplit(measures: readonly MeasureCoverage[]): ReportingRouteSplit {
  const pick = (keys: readonly MeasureKey[]): MeasureCoverage[] =>
    measures.filter((m) => (keys as readonly string[]).includes(m.key));

  const provider = pick(PROVIDER_FILED_MEASURES);
  const wageMatch = pick(WAGE_MATCH_MEASURES);
  if (provider.length === 0 || wageMatch.length === 0) {
    return { providerFloor: null, wageMatchCeiling: null, separated: false };
  }

  const providerFloor = provider.reduce((a, b) => (b.reported < a.reported ? b : a));
  const wageMatchCeiling = wageMatch.reduce((a, b) => (b.reported > a.reported ? b : a));
  return {
    providerFloor,
    wageMatchCeiling,
    separated: providerFloor.reported > wageMatchCeiling.reported,
  };
}

/**
 * The categories leaving the most rows empty, named so they can be accounted for.
 *
 * This is the ranking `coverageByEntityType` deliberately refuses to publish as a column, and
 * it exists for the opposite reason: a reader will find the top of that ranking on their own
 * within about four seconds of seeing the table, and the choice is between letting them find
 * it unaccompanied or naming it with the reporting obligations attached. Naming it is better.
 * The caller is expected to explain it in the same breath.
 *
 * Categories whose share was withheld for a small denominator are not candidates. A category
 * of four programs cannot be "the category leaving the most empty", and putting it at the top
 * of a list on the strength of three records would be exactly the misreading the denominator
 * floor exists to prevent.
 */
export function mostlySilentCategories(
  rows: readonly EntityTypeCoverage[],
  limit: number,
): EntityTypeCoverage[] {
  return rows
    .filter((row): row is EntityTypeCoverage & { silentShare: number } => row.silentShare !== null)
    .sort((a, b) => b.silentShare - a.silentShare || a.entityType.localeCompare(b.entityType))
    .slice(0, limit);
}

/**
 * Exiter-cohort bands, for testing the blank rate against cohort size.
 *
 * WIOA suppresses small-cohort cells to protect participants, so if suppression is what is
 * behind an empty cell, the blank rate should fall as cohorts grow. That is a prediction the
 * data can be asked about, and asking it is the only way this page can say anything at all
 * about *why* a cell is empty without inventing a reason.
 *
 * `upper` is inclusive. Null means no upper bound.
 */
export const COHORT_BANDS: readonly { lower: number; upper: number | null }[] = [
  { lower: 1, upper: 10 },
  { lower: 11, upper: 25 },
  { lower: 26, upper: 50 },
  { lower: 51, upper: 100 },
  { lower: 101, upper: 250 },
  { lower: 251, upper: null },
];

export interface CohortBandCoverage {
  lower: number;
  upper: number | null;
  programs: number;
  /** Blank share per headline measure, null where the band is too small to carry one. */
  missingShare: Record<(typeof HEADLINE_MEASURES)[number], number | null>;
  missingCount: Record<(typeof HEADLINE_MEASURES)[number], number>;
}

/**
 * Blank rates by cohort size, over attributable cohorts only.
 *
 * Restricted to `cohort.attributable` for the reason the rest of the site restricts its
 * medians: 103 California programs carry a cohort their provider filed against a whole
 * institution or a group of sibling courses, several of them tens of thousands of people
 * strong. Those rows would land in the largest band and describe a population that is not one
 * program, which is exactly the confounding this table is trying to see past.
 *
 * Programs that filed no exiter count are absent from every band rather than pooled into the
 * smallest one. An unstated cohort size is not a small cohort.
 */
export function coverageByCohortSize(programs: readonly Program[]): CohortBandCoverage[] {
  return COHORT_BANDS.map(({ lower, upper }) => {
    const members = programs.filter((program) => {
      const { total_exited: exited, cohort } = program.outcomes;
      if (!cohort.attributable || exited === null) return false;
      return exited >= lower && (upper === null || exited <= upper);
    });

    const missingCount = {} as CohortBandCoverage["missingCount"];
    const missingShare = {} as CohortBandCoverage["missingShare"];
    for (const key of HEADLINE_MEASURES) {
      const missing = members.filter((p) => p.outcomes[key] === null).length;
      missingCount[key] = missing;
      missingShare[key] = share(missing, members.length);
    }

    return { lower, upper, programs: members.length, missingCount, missingShare };
  });
}

/** Providers that published nothing for any program they filed. */
export interface ProviderSilence {
  providers: number;
  silentProviders: number;
  programsAtSilentProviders: number;
}

/**
 * Provider-level silence, keyed exactly as the provider index keys it.
 *
 * `slugify` rather than a normalisation written here, and that is the whole point: the
 * browse index this page links to publishes its own count of providers publishing at least
 * one outcome, and two pages one click apart disagreeing about how many training providers
 * California has would undermine both. One identity function, one answer. It also merges the
 * spellings that differ only in case or punctuation, so a provider cannot become two filers
 * by holding down shift.
 *
 * Records with no usable provider name are excluded from both counts rather than pooled under
 * a shared blank, which would attribute one anonymous filer's silence to another's.
 */
export function providerSilence(programs: readonly Program[]): ProviderSilence {
  const byProvider = new Map<string, { programs: number; reporting: number }>();

  for (const program of programs) {
    const filed = program.provider_name?.trim();
    const name = filed ? slugify(filed) : "";
    if (!name) continue;
    const row = byProvider.get(name) ?? { programs: 0, reporting: 0 };
    row.programs += 1;
    if (HEADLINE_MEASURES.some((key) => program.outcomes[key] !== null)) row.reporting += 1;
    byProvider.set(name, row);
  }

  let silentProviders = 0;
  let programsAtSilentProviders = 0;
  for (const row of byProvider.values()) {
    if (row.reporting === 0) {
      silentProviders += 1;
      programsAtSilentProviders += row.programs;
    }
  }

  return {
    providers: byProvider.size,
    silentProviders,
    programsAtSilentProviders,
  };
}

/** Everything the coverage page publishes, computed in one pass over the corpus. */
export interface EtplCoverageReport {
  headline: HeadlineCoverage;
  measures: MeasureCoverage[];
  routes: ReportingRouteSplit;
  byEntityType: EntityTypeCoverage[];
  byCohortSize: CohortBandCoverage[];
  providers: ProviderSilence;
}

export function etplCoverageReport(programs: readonly Program[]): EtplCoverageReport {
  const measures = MEASURE_KEYS.map((key) => measureCoverage(programs, key));
  return {
    headline: headlineCoverage(programs),
    measures,
    routes: reportingRouteSplit(measures),
    byEntityType: coverageByEntityType(programs),
    byCohortSize: coverageByCohortSize(programs),
    providers: providerSilence(programs),
  };
}
