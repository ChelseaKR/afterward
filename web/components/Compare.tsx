"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type CSSProperties } from "react";

import { dict, type Lang } from "@/lib/i18n";
import { isShrinking } from "@/lib/search";
import { count, money, percent, signedPercent, tidyName } from "@/lib/format";
import type { Program, SearchEntry } from "@/lib/types";
import {
  bestOf,
  completionMark,
  isOwnCohort,
  occupationFigures,
  ownCohortOnly,
  programRecordUrl,
  COHORT_NOT_OWN,
  MAX_COMPARE,
} from "@/lib/compare";

export { MAX_COMPARE };

/*
 * TODO(i18n): these five strings belong in `web/lib/i18n.ts` under the names given here —
 * `occupationRow`, `occupationRowNote`, `occupationFiguresLoading`,
 * `occupationFiguresUnavailable`, `unnamedOccupationShort`. They are defined here only
 * because that file was owned by a concurrent change when this landed, and the alternative
 * was leaving a table that reads a top salary off one job and a weak outlook off another and
 * prints them as one program. Both languages are complete so no page ships half-translated.
 *
 * `t.leadsTo` is no longer used by this component; the row it labelled has been replaced by
 * one that carries each job's own figures.
 */
interface OccupationCopy {
  /** Row header for the per-occupation block. */
  row: string;
  /** Said once above the table, before any figure is read. */
  note: string;
  /** The record is on its way. */
  loading: string;
  /** The record could not be read, so the names are all this cell can honestly show. */
  unavailable: string;
  /** An occupation with neither a title nor a code published. */
  unnamed: string;
}

const OCCUPATION_COPY: Record<Lang, OccupationCopy> = {
  en: {
    row: "Jobs this leads to, and California's figures for each",
    note:
      "Pay, projected change, and openings describe a job, not a program, and many programs " +
      "lead to more than one job. Each job's figures are listed under that job, so a high " +
      "salary from one and a weak outlook from another are never read as a single profile.",
    loading: "Loading each job's figures…",
    unavailable: "Each job's own figures are on the program page above.",
    unnamed: "Occupation not named",
  },
  es: {
    row: "Empleos a los que lleva, y las cifras de California para cada uno",
    note:
      "El pago, el cambio proyectado y las vacantes describen un empleo, no un programa, y " +
      "muchos programas llevan a más de un empleo. Las cifras de cada empleo se listan bajo " +
      "ese empleo, para que un salario alto de uno y un panorama débil de otro nunca se lean " +
      "como un solo perfil.",
    loading: "Cargando las cifras de cada empleo…",
    unavailable: "Las cifras propias de cada empleo están en la página del programa, arriba.",
    unnamed: "Ocupación sin nombre",
  },
};

/**
 * Sticky tray showing what has been picked for comparison.
 *
 * Deciding between programs is the moment this whole dataset exists for, and it is not a
 * moment anyone can hold in their head across a scrolling list of cards.
 */
export function CompareTray({
  selected,
  lang,
  onRemove,
  onClear,
  onOpen,
  open,
}: {
  selected: SearchEntry[];
  lang: Lang;
  onRemove: (id: string) => void;
  onClear: () => void;
  onOpen: () => void;
  open: boolean;
}) {
  const t = dict(lang);
  if (selected.length === 0) return null;

  return (
    <div className="compare-tray" role="region" aria-label={t.compareTitle}>
      <div className="shell compare-tray-inner">
        <p className="compare-tray-count">
          {t.compareCount(selected.length, MAX_COMPARE)}
          {/*
            Said out loud when the limit is reached. The card checkboxes go disabled at that
            point, which removes them from the tab order, so a keyboard user could never
            reach the tooltip that used to be the only explanation.
          */}
          {selected.length >= MAX_COMPARE && (
            <span
              role="status"
              style={{ display: "block", fontWeight: 400, opacity: 0.85, marginTop: "0.15rem" }}
            >
              {t.compareFull}
            </span>
          )}
        </p>

        <ul className="compare-chips">
          {selected.map((entry) => (
            <li key={entry.i}>
              <span>{entry.n ?? "—"}</span>
              <button
                type="button"
                onClick={() => onRemove(entry.i)}
                aria-label={t.compareRemove(entry.n ?? "")}
              >
                ×
              </button>
            </li>
          ))}
        </ul>

        <div className="compare-tray-actions">
          <button type="button" className="linklike" onClick={onClear}>
            {t.compareClear}
          </button>
          <button
            type="button"
            className="compare-open"
            onClick={onOpen}
            disabled={selected.length < 2}
          >
            {open ? t.compareHide : t.compareOpen}
          </button>
        </div>
      </div>
    </div>
  );
}

/** One row of the comparison table. `values` are pre-formatted, null meaning not reported. */
function Row({
  label,
  values,
  lang,
  best,
  bestNote,
}: {
  label: string;
  values: (string | null)[];
  lang: Lang;
  /** Index of the strongest reported value, or null when no comparison is meaningful. */
  best: number | null;
  /**
   * What the mark on `best` means, said aloud next to that cell's value. Font weight and an
   * inset rule are how the mark reaches a sighted reader; neither reaches a screen reader, so
   * this is the only place the mark exists for one.
   */
  bestNote: string;
}) {
  const t = dict(lang);
  const reportedCount = values.filter((value) => value !== null).length;
  // Real figures are on screen, in numbers a reader could compare themselves, and none is
  // marked — a tie, or every reporter disqualified from the ranking. Silence here reads the
  // same as "nobody won"; a row with fewer than two figures at all doesn't need this, because
  // the "Not reported" cells already say why there is nothing to compare.
  const noStandout = best === null && reportedCount >= 2;
  return (
    <tr>
      <th scope="row">
        {label}
        {noStandout && <span className="visually-hidden"> — {t.compareNoStandout}</span>}
      </th>
      {values.map((value, index) => (
        <td key={index} className={best === index ? "is-best" : undefined}>
          {value === null ? (
            <span className="unreported" title={t.notReportedLong}>
              {t.notReported}
            </span>
          ) : best === index ? (
            <>
              {value}
              <span className="visually-hidden"> ({bestNote})</span>
            </>
          ) : (
            value
          )}
        </td>
      ))}
    </tr>
  );
}

/**
 * Full records for the compared programs, keyed by id.
 *
 * `undefined` means still on its way and `null` means it could not be read; the cell tells
 * those apart because "we are fetching this" and "there is nothing to fetch" are different
 * things to say to someone waiting. Nothing here is ever coerced into a figure.
 *
 * Fetched rather than shipped: the search index carries only what a card or a filter needs,
 * and per-job figures are wanted for at most four programs and only once someone opens the
 * comparison. A failed request costs the reader the numbers, not the truth — the cell falls
 * back to naming the jobs, which is what the index can honestly support on its own.
 */
function useProgramRecords(ids: string[]): Record<string, Program | null | undefined> {
  const [records, setRecords] = useState<Record<string, Program | null>>({});
  const requested = useRef(new Set<string>());
  // A primitive so the effect re-runs when the selection changes rather than on every
  // render of a fresh array with the same contents in it.
  const key = ids.join(",");

  useEffect(() => {
    for (const id of key === "" ? [] : key.split(",")) {
      if (requested.current.has(id)) continue;
      requested.current.add(id);

      void fetch(programRecordUrl(id))
        .then((response) => (response.ok ? (response.json() as Promise<Program>) : null))
        .catch(() => null)
        .then((record) => setRecords((current) => ({ ...current, [id]: record })));
    }
    // No abort on cleanup: the selection changing does not make an in-flight record
    // unwanted, and a program removed from the tray is frequently put back.
  }, [key]);

  return records;
}

const JOB_LIST: CSSProperties = { listStyle: "none", margin: 0, padding: 0 };
const JOB_FIRST: CSSProperties = { marginTop: 0 };
const JOB_NEXT: CSSProperties = { marginTop: "0.7rem" };
const JOB_NAME: CSSProperties = { display: "block", fontWeight: 600 };
// --gray-90 on the panel's --gray-10, the pairing the contrast audit already covers as
// "card provider line".
const JOB_FIGURE: CSSProperties = {
  display: "block",
  color: "var(--gray-90)",
  fontSize: "0.8125rem",
  marginTop: "0.15rem",
  whiteSpace: "normal",
};

/** One labelled figure belonging to one named job. Null renders as an absence, never a zero. */
function JobFigure({ label, value, lang }: { label: string; value: string | null; lang: Lang }) {
  const t = dict(lang);
  return (
    <small style={JOB_FIGURE}>
      {label}:{" "}
      {value === null ? (
        <span className="unreported" title={t.notReportedLong}>
          {t.notReported}
        </span>
      ) : (
        value
      )}
    </small>
  );
}

/**
 * Every job one program leads to, each with its own published figures.
 *
 * This replaces four rows that took "Typical pay in California" from the highest-paying job
 * a program feeds and "Projected change" from the weakest-growing one and printed them in
 * the same column. For 1,045 programs those were different jobs, and the column described
 * nobody: a Sports Medicine course at a high-school ROP showed a physician's $289,473 beside
 * an athletic trainer's +5.0%. Grouping under the job name makes that sentence unsayable.
 */
function OccupationCell({
  entry,
  record,
  lang,
}: {
  entry: SearchEntry;
  record: Program | null | undefined;
  lang: Lang;
}) {
  const t = dict(lang);
  const copy = OCCUPATION_COPY[lang];

  const figures = record ? occupationFigures(record) : null;
  const jobs: (string | null)[] = figures ? figures.map((job) => job.title) : entry.o;

  if (jobs.length === 0) {
    return (
      <span className="unreported" title={t.notReportedLong}>
        {t.notReported}
      </span>
    );
  }

  return (
    <ul style={JOB_LIST}>
      {jobs.map((title, index) => {
        const job = figures?.[index];
        const soc = job?.socCode ?? null;
        const name = title ?? soc ?? copy.unnamed;
        const change = job ? signedPercent(job.change, lang) : null;

        return (
          <li key={`${soc ?? "unnamed"}-${index}`} style={index === 0 ? JOB_FIRST : JOB_NEXT}>
            <span style={JOB_NAME}>
              {soc === null ? name : <Link href={`/${lang}/occupations/${soc}/`}>{name}</Link>}
            </span>
            {job ? (
              <>
                <JobFigure label={t.medianWage} value={money(job.wage, lang)} lang={lang} />
                <JobFigure
                  label={t.growth}
                  value={
                    change === null
                      ? null
                      : `${change}${isShrinking(job.change) ? ` · ${t.shrinking}` : ""}`
                  }
                  lang={lang}
                />
                <JobFigure label={t.jobOpenings} value={count(job.openings, lang)} lang={lang} />
              </>
            ) : null}
          </li>
        );
      })}
      {figures === null && (
        <li style={JOB_NEXT}>
          <small style={JOB_FIGURE}>
            {record === null ? copy.unavailable : copy.loading}
          </small>
        </li>
      )}
    </ul>
  );
}

export function CompareTable({ entries, lang }: { entries: SearchEntry[]; lang: Lang }) {
  const t = dict(lang);
  const copy = OCCUPATION_COPY[lang];
  const records = useProgramRecords(entries.map((entry) => entry.i));
  const completion = completionMark(entries);

  return (
    <section className="compare-panel" aria-label={t.compareTitle}>
      <h2>{t.compareTitle}</h2>
      <p className="compare-note">{t.compareNote}</p>
      <p className="compare-note">{copy.note}</p>
      {/* Only when it applies to something on screen, and in full words rather than a badge. */}
      {entries.some((entry) => entry.r && !isOwnCohort(entry)) && (
        <p className="compare-note">{COHORT_NOT_OWN[lang].note}</p>
      )}
      {/*
        * Up here with the other notes rather than beside the row it governs, for the same
        * reason the cohort note is: it is one fact about this particular set of programs, and
        * the alternative — a full-width cell spliced into the table body — puts prose inside a
        * grid of figures where a screen reader announces it as a row of data. The condition is
        * the narrow one: a mark existed and length removed it. A completion row that nobody
        * reported is silent, because length is not why that one is blank.
        */}
      {completion.withheldForLength && (
        <p className="compare-note">{t.compareCompletionLength}</p>
      )}

      <div className="table-scroll">
        <table className="compare-table">
          <thead>
            <tr>
              <th scope="col">
                <span className="visually-hidden">{t.compareMeasure}</span>
              </th>
              {entries.map((entry) => (
                <th key={entry.i} scope="col">
                  <Link href={`/${lang}/programs/${entry.i}/`}>{entry.n ?? "—"}</Link>
                  <small>{tidyName(entry.p)}</small>
                  {/*
                    * Said at the top of the column rather than on each affected figure: it is
                    * one fact about how this provider filed, and it governs all three cohort
                    * rows below. The figures themselves stay — they are real, and hiding them
                    * would be its own misrepresentation — but nothing in this table ranks
                    * them.
                    */}
                  {entry.r && !isOwnCohort(entry) && (
                    <small>
                      <span className="badge badge-small">{COHORT_NOT_OWN[lang].badge}</span>
                    </small>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <Row
              label={t.cost}
              lang={lang}
              values={entries.map((e) => money(e.$, lang))}
              best={bestOf(entries, (e) => e.$, "low")}
              bestNote={t.compareBestCost}
            />
            <Row
              label={t.length}
              lang={lang}
              values={entries.map((e) => (e.w === null ? null : t.weeks(e.w)))}
              best={bestOf(entries, (e) => e.w, "low")}
              bestNote={t.compareBestLength}
            />
            {/*
              * The three cohort measures. Cost and length above are properties of the course
              * and stay comparable however the provider filed its outcome rows; these three
              * are properties of the cohort, so a program whose cohort is a whole college's
              * is withheld from the ranking — not from the table.
              *
              * Completion carries a second disqualification the other two do not, because it
              * is the row length decides: its median falls 97% → 78% across the length bands
              * the filter above already uses, so marking a winner across lengths marks the
              * shorter program. `completionMark` holds that measurement and the reason the
              * rule stops at this row.
              */}
            <Row
              label={t.completionRate}
              lang={lang}
              values={entries.map((e) => percent(e.cr, lang))}
              best={completion.best}
              bestNote={t.compareBestCompletion}
            />
            <Row
              label={t.employmentRate}
              lang={lang}
              values={entries.map((e) => percent(e.er, lang))}
              best={bestOf(entries, ownCohortOnly((e) => e.er), "high")}
              bestNote={t.compareBestEmployment}
            />
            <Row
              label={t.medianEarnings}
              lang={lang}
              values={entries.map((e) => money(e.me, lang))}
              best={bestOf(entries, ownCohortOnly((e) => e.me), "high")}
              bestNote={t.compareBestEarnings}
            />
            {/*
              * One row, grouped by job, in place of four that were grouped by measure.
              *
              * The four rows are gone rather than annotated. `wage`, `g` and `op` in the
              * search index are a maximum, a minimum and a maximum taken independently
              * across a program's occupations, so no wording could make three of them in one
              * column describe a single job; the only honest fix was to stop laying them out
              * that way. Nothing marks a "best" here either — there is no one figure per
              * program left to be best at, which is exactly the claim that was false.
              */}
            <tr>
              <th scope="row" style={{ whiteSpace: "normal", minWidth: "10rem" }}>
                {copy.row}
              </th>
              {entries.map((entry) => (
                <td key={entry.i} style={{ verticalAlign: "top" }}>
                  <OccupationCell entry={entry} record={records[entry.i]} lang={lang} />
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}
