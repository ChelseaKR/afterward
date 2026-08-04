"use client";

import Link from "next/link";
import { useDeferredValue, useMemo, useState } from "react";

import { dict, type Lang } from "@/lib/i18n";
import { money, percent, signedPercent, tidyName } from "@/lib/format";
import { isShrinking, runSearch, summarise, type Outlook, type Sort } from "@/lib/search";
import type { SearchEntry } from "@/lib/types";
import { Fact } from "./Measure";

const COST_CAPS = [2000, 5000, 10000, 20000];
const PAGE_SIZE = 25;

export function SearchApp({ programs, lang }: { programs: SearchEntry[]; lang: Lang }) {
  const t = dict(lang);
  const [query, setQuery] = useState("");
  const [onlyReported, setOnlyReported] = useState(false);
  const [outlook, setOutlook] = useState<Outlook>("any");
  const [maxCost, setMaxCost] = useState<number | null>(null);
  const [sort, setSort] = useState<Sort>("relevance");
  const [limit, setLimit] = useState(PAGE_SIZE);

  const deferredQuery = useDeferredValue(query);

  const results = useMemo(
    () => runSearch(programs, { query: deferredQuery, onlyReported, outlook, maxCost, sort }),
    [programs, deferredQuery, onlyReported, outlook, maxCost, sort],
  );

  const stats = useMemo(() => summarise(programs), [programs]);

  const visible = results.slice(0, limit);

  function clear() {
    setQuery("");
    setOnlyReported(false);
    setOutlook("any");
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
        </fieldset>

        <div className="field">
          <label htmlFor="outlook">{t.filterOutlook}</label>
          <select
            id="outlook"
            value={outlook}
            onChange={(e) => setOutlook(e.target.value as Outlook)}
          >
            <option value="any">{t.outlookAny}</option>
            <option value="growing">{t.outlookGrowing}</option>
            <option value="shrinking">{t.outlookShrinking}</option>
          </select>
        </div>

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
        {/*
          The two facts that justify the whole dataset, stated before any result. Both are
          public today and neither is discoverable beside the other anywhere else.
        */}
        <ul className="stat-strip">
          <li>{t.statReported(stats.reported, stats.total)}</li>
          <li>
            {t.statShrinking(stats.shrinking)}{" "}
            <button
              type="button"
              className="linklike"
              onClick={() => {
                setOutlook("shrinking");
                setLimit(PAGE_SIZE);
              }}
            >
              {t.showThese}
            </button>
          </li>
        </ul>

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
  const shrinking = isShrinking(entry.g);

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
