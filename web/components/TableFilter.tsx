"use client";

import { useEffect, useId, useMemo, useState } from "react";

import { type Lang, dict } from "@/lib/i18n";

/**
 * Type-to-filter for the two browse indexes.
 *
 * The occupations index is 670 rows and 36,585 pixels — about forty desktop screens — and the
 * providers index is not far behind. Both were already sorted and sectioned sensibly; what
 * neither offered was a way to answer "is my job on this list?" without scrolling past every
 * job that is not. The bands and the jump links stay, because they answer a different
 * question, which is what someone browses when they do not yet know what they are looking for.
 *
 * It filters the rendered DOM rather than re-rendering rows from a copy of the data. Handing
 * the same 670 rows to the client as props would have shipped the table twice, once as HTML
 * and once as JSON, on a page whose problem is already its size.
 *
 * Without JavaScript the input never appears and every row is visible, which is the correct
 * fallback: the unfiltered list is the whole list.
 */
export function TableFilter({ lang, scope }: { lang: Lang; scope: string }) {
  const t = dict(lang);
  const inputId = useId();
  const [query, setQuery] = useState("");
  const [total, setTotal] = useState(0);
  const [shown, setShown] = useState(0);
  const [ready, setReady] = useState(false);

  const needle = useMemo(() => query.trim().toLowerCase(), [query]);

  useEffect(() => {
    setReady(true);
  }, []);

  useEffect(() => {
    const root = document.querySelector(scope);
    if (root === null) return;
    const rows = Array.from(root.querySelectorAll<HTMLElement>("tbody tr"));
    setTotal(rows.length);

    let visible = 0;
    for (const row of rows) {
      const match = needle === "" || (row.textContent ?? "").toLowerCase().includes(needle);
      row.hidden = !match;
      if (match) visible += 1;
    }
    setShown(visible);

    /*
     * A section whose rows have all been filtered out is hidden with them. Leaving the
     * heading, its standfirst and an empty table behind would tell a reader that the band
     * exists and contains nothing matching, which is true but reads as four broken headings
     * stacked on top of each other.
     */
    for (const section of Array.from(root.querySelectorAll<HTMLElement>("section"))) {
      const sectionRows = Array.from(section.querySelectorAll<HTMLElement>("tbody tr"));
      if (sectionRows.length === 0) continue;
      section.hidden = sectionRows.every((row) => row.hidden);
    }
  }, [needle, scope]);

  // Rendered only once mounted: an input that cannot filter is worse than no input.
  if (!ready) return null;

  return (
    <div className="table-filter">
      <label htmlFor={inputId}>{t.filterLabel}</label>
      <input
        id={inputId}
        type="search"
        value={query}
        placeholder={t.filterPlaceholder}
        onChange={(event) => setQuery(event.target.value)}
      />
      <p aria-live="polite" className="table-filter-count">
        {needle !== "" && shown === 0 ? t.filterNoMatches : t.filterShowing(shown, total)}
      </p>
    </div>
  );
}
