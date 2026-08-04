/**
 * Logic for the side-by-side comparison.
 *
 * Separate from the component so the "which of these is best" decision can be tested
 * directly. That decision is the one place in the UI where the tool comes closest to giving
 * advice, so it has to be conservative about what it claims.
 */

import type { Lang } from "./i18n";
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

/*
 * TODO(i18n): `cohortNotOwn` and `cohortNotOwnNote` belong in `web/lib/i18n.ts` under those
 * names. They live here because that file was owned by a concurrent change when this landed,
 * and here rather than in either component because both the result card and the comparison
 * header need the same words for the same fact. Both languages are complete.
 */
export const COHORT_NOT_OWN: Record<Lang, { badge: string; note: string }> = {
  en: {
    badge: "Outcomes cover more than this program",
    note:
      "The provider filed these figures against more than the program named — several of " +
      "its programs, or the whole institution. They are shown because they are real, and " +
      "they are left out of the highlighting because they do not describe this program.",
  },
  es: {
    badge: "Los resultados abarcan más que este programa",
    note:
      "El proveedor presentó estas cifras para más que el programa nombrado — varios de sus " +
      "programas, o toda la institución. Se muestran porque son reales, y quedan fuera de " +
      "las marcas porque no describen este programa.",
  },
};

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
 * is fetched per-program on demand", `search_entry` in src/camino/build.py), and per-job
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
