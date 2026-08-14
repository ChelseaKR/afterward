/**
 * The CTDL export's two published statements, and the shapes the page renders from them.
 *
 * `public/ctdl/` holds a coverage statement and a validation statement, each written by
 * `make ctdl-statements` and each counted from the exported graph at the moment it was
 * written. They are committed, unlike `public/data/`, for two reasons: they are about a
 * kilobyte each, and committing them means every figure on `/ctdl/` arrives as a reviewable
 * diff rather than as a build artifact nobody looks at. The 17 MB graph they describe is not
 * committed, on exactly the same rule the dataset follows.
 *
 * Nothing in this module computes a figure. Every number on the page is read from a statement
 * the Python export produced; the functions here only reshape, sort and pair things up. That
 * is the whole point of the split — the page cannot say something the export did not count,
 * because there is nothing here for it to say it with.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

const CTDL_DIR = join(process.cwd(), "public", "ctdl");

/** Counts of what the export emitted, keyed by CTDL class or property name. */
export type TermCounts = Readonly<Record<string, number>>;

export interface UnprojectedField {
  /** Programs whose source record asserts any of `source_fields`. */
  readonly reported_in_source: number;
  readonly source_fields: Readonly<Record<string, number>>;
  /**
   * The CTDL term that would have carried this, or "" where the export uses none.
   *
   * Non-empty is the uncomfortable case and the one worth showing: the vocabulary has
   * somewhere to put this and the export does not use it, which is a gap in the export
   * rather than a limit of CTDL.
   */
  readonly ctdl_term: string;
  readonly reason: string;
}

export interface CtdlCoverage {
  readonly note: string;
  readonly snapshot_date: string;
  readonly source_programs: number;
  readonly entities: TermCounts;
  readonly learning_program_properties: TermCounts;
  readonly observation_measures: TermCounts;
  readonly not_projected: {
    readonly cost_total_incomplete: { readonly reported_in_source: number; readonly reason: string };
    readonly source_fields: Readonly<Record<string, UnprojectedField>>;
  };
}

export interface FindingRule {
  readonly citation: string;
  readonly url: string;
  readonly retrieved: string;
}

export interface FindingSummary {
  readonly severity: string;
  readonly count: number;
  readonly entities: number;
  readonly accepted: boolean;
  readonly reason: string;
  readonly message: string;
  readonly rule: FindingRule;
}

export interface CtdlValidation {
  readonly note: string;
  readonly snapshot_date: string;
  readonly document: string;
  readonly tool: {
    readonly name: string;
    readonly version: string;
    readonly package: string;
    readonly source: string;
  };
  readonly entities_validated: number;
  readonly findings: Readonly<Record<string, number>>;
  readonly codes: Readonly<Record<string, FindingSummary>>;
  readonly validator_scope: {
    readonly note: string;
    readonly classes_emitted: number;
    readonly classes_in_validator_schema: number;
    readonly classes_not_in_validator_schema: readonly string[];
    readonly properties_emitted: number;
    readonly properties_in_validator_schema: number;
    readonly properties_not_in_validator_schema: readonly string[];
  };
}

function readStatement<T>(name: string): T {
  return JSON.parse(readFileSync(join(CTDL_DIR, name), "utf-8")) as T;
}

export function getCtdlCoverage(): CtdlCoverage {
  return readStatement<CtdlCoverage>("ctdl-coverage.json");
}

export function getCtdlValidation(): CtdlValidation {
  return readStatement<CtdlValidation>("ctdl-validation.json");
}

/**
 * The four severities ctdl-validate defines, in the order it reports them, zeroes included.
 *
 * A severity row that appears only when something happened cannot be read as "no errors"; it
 * can only be read as "no errors are mentioned". The zeroes are the finding.
 */
export const SEVERITIES = ["ERROR", "WARNING", "INFO", "UNVERIFIABLE"] as const;
export type Severity = (typeof SEVERITIES)[number];

export function severityCounts(validation: CtdlValidation): { severity: Severity; count: number }[] {
  return SEVERITIES.map((severity) => ({ severity, count: validation.findings[severity] ?? 0 }));
}

export interface FindingRow extends FindingSummary {
  readonly code: string;
}

/** Every finding code the validator returned, worst first, then by name. */
export function findingRows(validation: CtdlValidation): FindingRow[] {
  const rank = (severity: string) => {
    const index = (SEVERITIES as readonly string[]).indexOf(severity);
    return index === -1 ? SEVERITIES.length : index;
  };
  return Object.entries(validation.codes)
    .map(([code, summary]) => ({ code, ...summary }))
    .sort((a, b) => rank(a.severity) - rank(b.severity) || a.code.localeCompare(b.code));
}

/**
 * Whether the validator returned anything nobody has already reasoned about.
 *
 * The export refuses to write a statement in which this is true, so on a published page it is
 * always false. It is computed rather than assumed anyway: a page that says "no errors"
 * because it was written on a day when there were none is not a report, it is a sentence.
 */
export function hasUnacceptedFindings(validation: CtdlValidation): boolean {
  return (
    (validation.findings.ERROR ?? 0) > 0 ||
    Object.values(validation.codes).some((summary) => !summary.accepted)
  );
}

export interface PropertyRow {
  readonly term: string;
  readonly count: number;
  /** Share of the exported programs carrying it, 0–1, or null when there are no programs. */
  readonly share: number | null;
}

/**
 * Each counted LearningProgram property with the share of programs carrying it.
 *
 * Order comes from the statement, which publishes these in the export's own publication
 * order. Not re-sorted by how well each one does: ordering a coverage table by completeness
 * turns a measurement into a scoreboard, which is the same rule `/outcomes-coverage/` follows
 * for provider categories.
 */
export function propertyRows(coverage: CtdlCoverage): PropertyRow[] {
  const programs = coverage.entities["ceterms:LearningProgram"] ?? 0;
  return Object.entries(coverage.learning_program_properties).map(([term, count]) => ({
    term,
    count,
    share: programs > 0 ? count / programs : null,
  }));
}

export interface MeasureRow {
  readonly field: string;
  readonly count: number;
  /** Share of programs that have any outcome profile at all, 0–1, or null when none do. */
  readonly share: number | null;
}

/**
 * Each projected outcome measure against the programs that have an outcome profile.
 *
 * The denominator is the number of `qdata:DataSetProfile` entities, not the number of
 * programs. A measure absent because the program reported nothing at all is a different fact
 * from a measure absent from a program that reported something else, and dividing by every
 * program would blend the two into one misleadingly low number.
 */
export function measureRows(coverage: CtdlCoverage): MeasureRow[] {
  const profiles = coverage.entities["qdata:DataSetProfile"] ?? 0;
  return Object.entries(coverage.observation_measures).map(([field, count]) => ({
    field,
    count,
    share: profiles > 0 ? count / profiles : null,
  }));
}

export interface GapRow extends UnprojectedField {
  readonly key: string;
  /** The source paths and their counts, ordered as the statement lists them. */
  readonly fields: { readonly path: string; readonly count: number }[];
}

/**
 * Everything the source record says that the export drops, most-affected first.
 *
 * Sorted by how many programs lose something, because unlike a provider table this ranks the
 * export's own omissions rather than anybody else's reporting, and the biggest gap is the one
 * a reader most needs at the top.
 */
export function gapRows(coverage: CtdlCoverage): GapRow[] {
  return Object.entries(coverage.not_projected.source_fields)
    .map(([key, field]) => ({
      key,
      ...field,
      fields: Object.entries(field.source_fields).map(([path, count]) => ({ path, count })),
    }))
    .sort((a, b) => b.reported_in_source - a.reported_in_source || a.key.localeCompare(b.key));
}

/**
 * The snapshot the export describes, and the snapshot the rest of the site is serving.
 *
 * These agree when `make ctdl-statements` has been re-run since the last `make data`, and
 * they are meant to. When they do not, the page says so rather than letting a reader assume
 * one date covers both: the export is a projection of a dataset, and which dataset is the
 * first thing anybody checking it needs to know.
 */
export function snapshotAgreement(
  exportSnapshot: string,
  siteSnapshot: string,
): { agree: boolean; exportSnapshot: string; siteSnapshot: string } {
  return { agree: exportSnapshot === siteSnapshot, exportSnapshot, siteSnapshot };
}
