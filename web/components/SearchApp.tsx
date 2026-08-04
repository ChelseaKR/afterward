"use client";

import Link from "next/link";
import { useDeferredValue, useMemo, useState } from "react";

import { dict, type Lang } from "@/lib/i18n";
import { isSmallSample, money, percent, signedPercent, tidyName } from "@/lib/format";
import type { SearchEntry } from "@/lib/types";
import { Fact } from "./Measure";

type Sort = "relevance" | "earnings" | "cost" | "openings";

const COST_CAPS = [2000, 5000, 10000, 20000];
const PAGE_SIZE = 25;

/** Cheap substring scoring: the dataset is 3,266 rows, so no index structure is warranted. */
function score(entry: SearchEntry, terms: string[]): number {
  if (terms.length === 0) return 0;
  const name = (entry.n ?? "").toLowerCase();
  const provider = (entry.p ?? "").toLowerCase();
  const occupation = (entry.o ?? "").toLowerCase();
  const city = (entry.c ?? "").toLowerCase();

  let total = 0;
  for (const term of terms) {
    if (name.startsWith(term)) total += 6;
    else if (name.includes(term)) total += 4;
    else if (occupation.includes(term)) total += 3;
    else if (provider.includes(term)) total += 2;
    else if (city.includes(term)) total += 2;
    else return -1; // every term must match something
  }
  return total;
}

export function SearchApp({ programs, lang }: { programs: SearchEntry[]; lang: Lang }) {
  const t = dict(lang);
  const [query, setQuery] = useState("");
  const [onlyReported, setOnlyReported] = useState(false);
  const [hideShrinking, setHideShrinking] = useState(false);
  const [maxCost, setMaxCost] = useState<number | null>(null);
  const [sort, setSort] = useState<Sort>("relevance");
  const [limit, setLimit] = useState(PAGE_SIZE);

  const deferredQuery = useDeferredValue(query);

  const results = useMemo(() => {
    const terms = deferredQuery.toLowerCase().split(/\s+/).filter(Boolean);

    const matched = programs
      .map((entry) => ({ entry, rank: score(entry, terms) }))
      .filter(({ entry, rank }) => {
        if (rank < 0) return false;
        if (onlyReported && !entry.r) return false;
        // Unknown growth is not treated as shrinking; only filter what we actually know.
        if (hideShrinking && entry.g !== null && entry.g < 0) return false;
        if (maxCost !== null && (entry.$ === null || entry.$ > maxCost)) return false;
        return true;
      });

    const by: Record<Sort, (a: typeof matched[number], b: typeof matched[number]) => number> = {
      relevance: (a, b) => b.rank - a.rank || (a.entry.n ?? "").localeCompare(b.entry.n ?? ""),
      // Nulls sort last in every ordering: a program that reported nothing has not earned
      // the top of the list, and has not earned the bottom either.
      earnings: (a, b) => (b.entry.me ?? -1) - (a.entry.me ?? -1),
      cost: (a, b) => (a.entry.$ ?? Infinity) - (b.entry.$ ?? Infinity),
      openings: (a, b) => (b.entry.op ?? -1) - (a.entry.op ?? -1),
    };

    return matched.sort(by[sort]).map(({ entry }) => entry);
  }, [programs, deferredQuery, onlyReported, hideShrinking, maxCost, sort]);

  const visible = results.slice(0, limit);

  function clear() {
    setQuery("");
    setOnlyReported(false);
    setHideShrinking(false);
    setMaxCost(null);
    setSort("relevance");
    setLimit(PAGE_SIZE);
  }

  return (
    <div className="shell search-layout">
      <form className="filters" role="search" onSubmit={(e) => e.preventDefault()}>
        <div className="field">
          <label htmlFor="q">{t.searchLabel}</label>
          <input
            id="q"
            type="search"
            value={query}
            placeholder={t.searchPlaceholder}
            onChange={(e) => {
              setQuery(e.target.value);
              setLimit(PAGE_SIZE);
            }}
          />
        </div>

        <fieldset style={{ border: 0, margin: 0, padding: 0 }}>
          <legend>{t.filters}</legend>
          <label className="checkline">
            <input
              type="checkbox"
              checked={onlyReported}
              onChange={(e) => setOnlyReported(e.target.checked)}
            />
            <span>{t.filterOutcomes}</span>
          </label>
          <label className="checkline">
            <input
              type="checkbox"
              checked={hideShrinking}
              onChange={(e) => setHideShrinking(e.target.checked)}
            />
            <span>{t.filterShrinking}</span>
          </label>
        </fieldset>

        <div className="field">
          <label htmlFor="cost">{t.filterMaxCost}</label>
          <select
            id="cost"
            value={maxCost ?? ""}
            onChange={(e) => setMaxCost(e.target.value === "" ? null : Number(e.target.value))}
          >
            <option value="">{t.filterAnyCost}</option>
            {COST_CAPS.map((cap) => (
              <option key={cap} value={cap}>
                {money(cap, lang)}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="sort">{t.sortBy}</label>
          <select id="sort" value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
            <option value="relevance">{t.sortRelevance}</option>
            <option value="earnings">{t.sortEarnings}</option>
            <option value="cost">{t.sortCost}</option>
            <option value="openings">{t.sortOpenings}</option>
          </select>
        </div>

        <button type="button" className="button" onClick={clear}>
          {t.clearFilters}
        </button>
      </form>

      <section aria-label={t.searchLabel}>
        <div className="results-head">
          <p className="results-count" role="status" aria-live="polite">
            {t.resultsCount(results.length, programs.length)}
          </p>
        </div>

        {results.length === 0 ? (
          <div className="panel panel-quiet">
            <p>
              <strong>{t.noResults}</strong>
            </p>
            <p>{t.noResultsHint}</p>
          </div>
        ) : (
          <>
            <ul className="card-list">
              {visible.map((entry) => (
                <ResultCard key={entry.i} entry={entry} lang={lang} />
              ))}
            </ul>
            {results.length > visible.length && (
              <p style={{ marginTop: "1.5rem" }}>
                <button
                  type="button"
                  className="button"
                  onClick={() => setLimit((n) => n + PAGE_SIZE * 2)}
                >
                  {`+ ${Math.min(PAGE_SIZE * 2, results.length - visible.length)}`}
                </button>
              </p>
            )}
          </>
        )}
      </section>
    </div>
  );
}

function ResultCard({ entry, lang }: { entry: SearchEntry; lang: Lang }) {
  const t = dict(lang);
  const shrinking = entry.g !== null && entry.g < 0;

  return (
    <li className={`card${entry.r ? "" : " is-unreported"}${shrinking ? " is-shrinking" : ""}`}>
      <h3>
        <Link href={`/${lang}/programs/${entry.i}/`}>{entry.n ?? "—"}</Link>
      </h3>
      <p className="card-provider">
        {tidyName(entry.p)}
        {entry.c ? ` · ${entry.c}` : ""}
      </p>

      <dl className="facts">
        <Fact label={t.cost} value={money(entry.$, lang)} lang={lang} />
        <Fact label={t.length} value={entry.w === null ? null : t.weeks(entry.w)} lang={lang} />
        <Fact label={t.employmentRate} value={percent(entry.er, lang)} lang={lang} />
        <Fact label={t.medianEarnings} value={money(entry.me, lang)} lang={lang} />
      </dl>

      {entry.o && (
        <p style={{ marginBottom: 0, marginTop: "0.875rem", fontSize: "0.9375rem" }}>
          {t.leadsTo}: <strong>{entry.o}</strong>
          {shrinking && (
            <>
              {" "}
              <span className="badge badge-shrinking">
                {t.shrinking} {signedPercent(entry.g, lang)}
              </span>
            </>
          )}
        </p>
      )}
    </li>
  );
}
