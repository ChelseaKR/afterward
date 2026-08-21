/**
 * Logic for the side-by-side comparison.
 *
 * Separate from the component so the "which of these is best" decision can be tested
 * directly. That decision is the one place in the UI where the tool comes closest to giving
 * advice, so it has to be conservative about what it claims.
 */

import { clockWeeks } from "./search";
import type { Program, SearchEntry } from "./types";

export const MAX_COMPARE = 4;

/**
 * Whether a program's reported outcomes describe that program.
 *
 * 103 of California's 3,266 filed a cohort that covers more than the program named — an
 * institution-wide total repeated against every course, or one cohort shared by eleven
 * sibling programs. The figures are real and stay on screen. What cannot stand is any
 * *comparison* built from them: ranking one against another, or marking one the strongest in
 * a row, silently asserts that both columns describe a single course.
 *
 * A missing flag is read as "not established", not as "fine". An index built before the
 * field existed cannot tell us whose cohort a number belongs to, and the site's rule
 * everywhere else — an unplaced city is not filed under a nearby region, an unreported
 * measure is not a zero — is to claim nothing rather than assume the convenient case.
 */
export function isOwnCohort(entry: SearchEntry): boolean {
  return entry.at === true;
}

/**
 * Wrap a measure reader so it yields a value only for programs whose cohort is their own.
 *
 * Applied to completion, employment and earnings, which are properties of the cohort, and
 * deliberately not to cost or length, which are properties of the course and stay comparable
 * however the provider filed its outcome rows.
 *
 * The withheld value arrives at `bestOf` as null, which it already skips — so a program
 * filing a whole college's numbers cannot win a row, and where fewer than two comparable
 * programs are left the row goes unmarked, exactly as it does when nobody reported.
 */
export function ownCohortOnly(
  read: (entry: SearchEntry) => number | null,
): (entry: SearchEntry) => number | null {
  return (entry) => (isOwnCohort(entry) ? read(entry) : null);
}

/**
 * Upper bound in weeks of each length band; anything past the last bound is its own band.
 *
 * Not invented for this file. These are the site's own length vocabulary — the four caps the
 * length filter offers, "About a month or less" through "About a year or less" (`LENGTH_GLOSS`
 * in i18n.ts) — and the segmentation the project already publishes its completion medians
 * against, on the About page and in `filterLengthNote`. Choosing a different cut here would
 * leave the site giving two incompatible answers to "when are two completion rates on the same
 * scale", and a reader auditing one against the other would be right to distrust both.
 */
export const LENGTH_BAND_BOUNDS: readonly number[] = [4, 12, 26, 52];

/**
 * Which length band a program sits in, or null when it has no clock length to band.
 *
 * Two populations arrive with nothing to band, and neither may be put on the scale: a program
 * whose provider filed no length, and a competency-based one, which has no fixed length by
 * design. A length that cannot be established is read the way a missing cohort flag is: as
 * "not established", never as "near enough", so such a program is not measured against one
 * that did say. Callers pass `clockWeeks(entry)` rather than `entry.w`, which is where the
 * second population becomes null.
 */
export function lengthBand(weeks: number | null): number | null {
  // `Number.isFinite` as well as the null test: an index built before `w` existed arrives with
  // the key absent rather than null, and undefined has to reach "no band" too.
  if (weeks === null || !Number.isFinite(weeks)) return null;
  const index = LENGTH_BAND_BOUNDS.findIndex((bound) => weeks <= bound);
  return index === -1 ? LENGTH_BAND_BOUNDS.length : index;
}

/**
 * Whether every one of these programs has a clock length, and all of them land in one band.
 *
 * False as soon as one of them is competency-based, which is the answer that matters: this
 * gates the completion mark, and the whole reason the mark needs gating is that the median
 * share who finish falls with length. A course with no fixed length has no place on that
 * scale, so nothing here may rank it against one that has.
 */
export function oneLengthBand(entries: SearchEntry[]): boolean {
  const bands = entries.map((entry) => lengthBand(clockWeeks(entry)));
  return bands.every((band) => band !== null) && new Set(bands).size <= 1;
}

/**
 * Index of the strongest reported value among the entries, or null when highlighting one
 * would mislead.
 *
 * Returns null in three cases, each deliberate:
 *   - fewer than two programs reported the measure, because being the only provider willing
 *     to file a number is not the same as being the best one;
 *   - nobody reported it;
 *   - the best value is tied, because there is no single winner to mark.
 *
 * Unreported values are skipped, never coerced. A null cost is not free and a null salary
 * is not zero.
 */
export function bestOf(
  entries: SearchEntry[],
  read: (entry: SearchEntry) => number | null,
  direction: "high" | "low",
): number | null {
  const reported = entries
    .map((entry, index) => ({ index, value: read(entry) }))
    .filter((candidate): candidate is { index: number; value: number } => candidate.value !== null);

  if (reported.length < 2) return null;

  const winner = reported.reduce((a, b) =>
    direction === "high" ? (b.value > a.value ? b : a) : b.value < a.value ? b : a,
  );

  if (reported.filter((candidate) => candidate.value === winner.value).length > 1) return null;
  return winner.index;
}

/** What the completion row may mark, and whether length is why it may mark nothing. */
export interface CompletionMark {
  /** Index of the cell to mark, or null when marking one would mislead. */
  best: number | null;
  /**
   * True only when there was a mark and length took it away. The table says "these are not
   * the same length" exactly when that is the reason, and never over a row nobody reported —
   * an explanation offered for an absence it does not explain is its own small lie.
   */
  withheldForLength: boolean;
}

/**
 * The completion row's mark, withheld when the programs being compared are not the same length.
 *
 * `bestOf` marked the highest completion rate in this row whatever the programs' lengths, and
 * completion is the one measure on this table that length largely decides. Measured on the
 * shipped index over the 1,947 programs that report both a completion rate and a length and
 * whose figures describe that program alone, the median share who finished falls at every step
 * up in length: 97% at four weeks or less (n=153), 91% at 5-12 (n=396), 85% at 13-26 (n=596),
 * 80% at 27-52 (n=588), 78% beyond a year (n=214). So a four-week certificate at 97% beside a
 * 72-week pathway at 80% is two programs sitting exactly on their own medians, and the mark
 * told the reader the first one had won something.
 *
 * It goes further than flattering the short program. Elite Permanent Makeup & Cosmetology
 * College's three-week "Permanent Makeup Triple Certificate Course" (81%) and Cosmetica Beauty
 * and Barbering Academy's 60-week "Cosmetology" (80%) both train for Hairdressers,
 * Hairstylists, and Cosmetologists, so they are a comparison someone really makes. The table
 * marked the three-week course. It finishes 16 points below the median for programs its
 * length; the 60-week course finishes 2 points above. The mark was pointed at the weaker of
 * the two.
 *
 * How often, measured: grade every program against a smoothed expectation for its own length
 * (the median of its 200 nearest neighbours by weeks) and rank every pair. Where both programs
 * share a band the mark lands on the weaker-for-its-length one 2.63% of the time, which is the
 * residual these deliberately wide bands leave. Where they do not share a band, 10.22%. Length
 * adds 7.59 points of error, and adds it in a direction: across bands, the marked program is
 * the shorter one 60.9% of the time.
 *
 * This is the confounding the project has already withdrawn a claim over once. "Better than
 * typical" came off program pages because the median it judged against pooled every length
 * (the block comment in `Measure.tsx` carries that measurement), and this table went on making
 * the same claim two programs at a time.
 *
 * Completion only, deliberately. The same measurement over the other two cohort rows puts
 * employment at 1.27% within a band against 4.53% across (+3.26) and earnings at 2.89% against
 * 5.85% (+2.96) — well under half of completion's excess — and neither is directional. Their
 * band medians do not fall with length (employment 76/71/69/65/69.5%; earnings
 * $10,220/$10,500/$11,042/$10,725/$13,290), and the marked program is the shorter one 53.2%
 * and 46.2% of the time, either side of chance. There is no length advantage being handed
 * out, so withholding those marks would cost a reader a working signal to answer a problem
 * those rows do not have. Cost and length keep their marks for the older reason: they are
 * properties of the course, and what a course costs is not a claim about a cohort.
 *
 * The rule refuses more than it strictly must, and that is the direction to err in. Bands are
 * coarse, so a 26-week and a 27-week program are held incomparable — 1.76% of realistic
 * comparison sets (two to four programs sharing a SOC code and a city), 2.9% of the refusals.
 * A ratio test would catch those, but at 1.5x it keeps 27.4% of pairs at 2.64% error against
 * these bands' 24.5% at 2.63%: the data does not tell the two rules apart, and only one of
 * them is already published.
 */
export function completionMark(entries: SearchEntry[]): CompletionMark {
  const read = ownCohortOnly((entry) => entry.cr);
  const best = bestOf(entries, read, "high");
  if (best === null) return { best: null, withheldForLength: false };

  // Only the programs that could actually have won it. One disqualified by `ownCohortOnly` is
  // already out of the ranking, and letting its length veto the comparison between the two
  // still standing would withhold a mark on account of a program that was never in the running.
  const candidates = entries.filter((entry) => read(entry) !== null);
  if (oneLengthBand(candidates)) return { best, withheldForLength: false };
  return { best: null, withheldForLength: true };
}

/**
 * One occupation's own published figures, kept together.
 *
 * The reason this type exists is the reason the comparison used to be wrong. The search
 * index summarises a program's occupations into three scalars — `wage` is the *highest* of
 * them, `g` the *lowest* projected change, `op` the *largest* opening count — and each is
 * chosen independently. For the 1,045 programs where the highest-paying job is not the
 * weakest-growing one, laying those scalars out as three rows of one column invents a job
 * that does not exist: KERN HIGH SCHOOL DISTRICT-ROP's "Sports Medicine" showed $289,473
 * (Physicians, All Other) beside +5.0% (Athletic Trainers) as though one person could be
 * paid the first while facing the second.
 *
 * Grouping by occupation makes that recombination impossible to express: a figure can only
 * be drawn next to the other figures for the same job.
 *
 * Every field stays `number | null`. A job California published no wage for is not a job
 * that pays nothing.
 */
export interface OccupationFigures {
  title: string | null;
  socCode: string | null;
  wage: number | null;
  change: number | null;
  openings: number | null;
}

/**
 * Split a program record into one row per occupation, in the order the record lists them.
 *
 * A row is emitted for every occupation the program feeds, including one whose figures are
 * all null: the fact that a program trains for a job California publishes nothing about is
 * itself worth seeing, and dropping the row would quietly shorten the list of destinations.
 */
export function occupationFigures(program: Program): OccupationFigures[] {
  return program.occupations.map((occupation) => ({
    title: occupation.title,
    socCode: occupation.soc_code,
    wage: occupation.median_annual_wage,
    change: occupation.percent_change,
    openings: occupation.total_job_openings,
  }));
}

/**
 * Where one program's full record is published.
 *
 * The pipeline writes a record per program under `public/data/programs/`, the static export
 * copies the directory verbatim, and the deploy uploads it — those URLs already answer 200.
 * The search index deliberately carries only what a card or a filter needs ("Everything else
 * is fetched per-program on demand", `search_entry` in src/afterward/build.py), and per-job
 * figures are exactly that: about 4 KB per program, wanted for at most four programs, and
 * only once someone opens the comparison.
 *
 * Absolute because the site sets no `basePath` and every page sits under a trailing-slash
 * directory, so a relative path would resolve against `/en/programs/<id>/` rather than the
 * site root. The id comes from the dataset rather than from user input, but it is encoded
 * anyway: a path segment built by concatenation is worth making safe by construction.
 */
export function programRecordUrl(id: string): string {
  return `/data/programs/${encodeURIComponent(id)}.json`;
}
