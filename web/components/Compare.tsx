"use client";

import Link from "next/link";

import { dict, type Lang } from "@/lib/i18n";
import { isShrinking } from "@/lib/search";
import { money, percent, signedPercent, tidyName } from "@/lib/format";
import type { SearchEntry } from "@/lib/types";
import { bestOf, MAX_COMPARE } from "@/lib/compare";

export { MAX_COMPARE };

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
}: {
  label: string;
  values: (string | null)[];
  lang: Lang;
  /** Index of the strongest reported value, or null when no comparison is meaningful. */
  best: number | null;
}) {
  const t = dict(lang);
  return (
    <tr>
      <th scope="row">{label}</th>
      {values.map((value, index) => (
        <td key={index} className={best === index ? "is-best" : undefined}>
          {value === null ? (
            <span className="unreported" title={t.notReportedLong}>
              {t.notReported}
            </span>
          ) : (
            value
          )}
        </td>
      ))}
    </tr>
  );
}

export function CompareTable({ entries, lang }: { entries: SearchEntry[]; lang: Lang }) {
  const t = dict(lang);

  return (
    <section className="compare-panel" aria-label={t.compareTitle}>
      <h2>{t.compareTitle}</h2>
      <p className="compare-note">{t.compareNote}</p>

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
            />
            <Row
              label={t.length}
              lang={lang}
              values={entries.map((e) => (e.w === null ? null : t.weeks(e.w)))}
              best={bestOf(entries, (e) => e.w, "low")}
            />
            <Row
              label={t.completionRate}
              lang={lang}
              values={entries.map((e) => percent(e.cr, lang))}
              best={bestOf(entries, (e) => e.cr, "high")}
            />
            <Row
              label={t.employmentRate}
              lang={lang}
              values={entries.map((e) => percent(e.er, lang))}
              best={bestOf(entries, (e) => e.er, "high")}
            />
            <Row
              label={t.medianEarnings}
              lang={lang}
              values={entries.map((e) => money(e.me, lang))}
              best={bestOf(entries, (e) => e.me, "high")}
            />
            <Row
              label={t.leadsTo}
              lang={lang}
              values={entries.map((e) => (e.o.length > 0 ? e.o.join(" · ") : null))}
              best={null}
            />
            <Row
              label={t.medianWage}
              lang={lang}
              values={entries.map((e) => money(e.wage, lang))}
              best={bestOf(entries, (e) => e.wage, "high")}
            />
            <Row
              label={t.growth}
              lang={lang}
              values={entries.map((e) =>
                e.g === null
                  ? null
                  : `${signedPercent(e.g, lang)}${isShrinking(e.g) ? ` · ${t.shrinking}` : ""}`,
              )}
              best={bestOf(entries, (e) => e.g, "high")}
            />
            <Row
              label={t.jobOpenings}
              lang={lang}
              values={entries.map((e) =>
                e.op === null ? null : new Intl.NumberFormat(lang === "es" ? "es-US" : "en-US").format(e.op),
              )}
              best={bestOf(entries, (e) => e.op, "high")}
            />
          </tbody>
        </table>
      </div>
    </section>
  );
}
