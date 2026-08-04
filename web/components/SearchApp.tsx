"use client";

import Link from "next/link";
import { useDeferredValue, useMemo, useState } from "react";

import { dict, type Lang } from "@/lib/i18n";
import { money, percent, signedPercent, tidyName } from "@/lib/format";
import {
  ANY_AREA,
  UNPLACED_AREA,
  areaFromOptionValue,
  areaOf,
  areaOptionValue,
  areas,
  cities,
  isShrinking,
  matchesArea,
  runSearch,
  summarise,
  unplacedMatches,
  type AreaFilter,
  type Filters,
  type Outlook,
  type Sort,
} from "@/lib/search";
import type { SearchEntry } from "@/lib/types";
import { Fact } from "./Measure";
import { CompareTable, CompareTray, MAX_COMPARE } from "./Compare";
import { COHORT_NOT_OWN, isOwnCohort } from "@/lib/compare";
import { slugify } from "@/lib/providers";

const COST_CAPS = [2000, 5000, 10000, 20000];
const PAGE_SIZE = 25;

/** Matches the private helper in lib/i18n.ts: grouped digits, the same in both languages. */

export function SearchApp({ programs, lang }: { programs: SearchEntry[]; lang: Lang }) {
  const t = dict(lang);
  const [query, setQuery] = useState("");
  const [onlyReported, setOnlyReported] = useState(false);
  const [outlook, setOutlook] = useState<Outlook>("any");
  const [maxCost, setMaxCost] = useState<number | null>(null);
  const [area, setArea] = useState<AreaFilter>(ANY_AREA);
  const [city, setCity] = useState<string | null>(null);
  const [sort, setSort] = useState<Sort>("relevance");
  const [limit, setLimit] = useState(PAGE_SIZE);

  const deferredQuery = useDeferredValue(query);

  const filters = useMemo<Filters>(
    () => ({ query: deferredQuery, onlyReported, outlook, maxCost, area, city, sort }),
    [deferredQuery, onlyReported, outlook, maxCost, area, city, sort],
  );

  const results = useMemo(() => runSearch(programs, filters), [programs, filters]);

  const stats = useMemo(() => summarise(programs), [programs]);
  const areaOptions = useMemo(() => areas(programs), [programs]);

  /*
    Region and city, and why both survive.

    Region is the better grain and is therefore the primary control: in this snapshot it
    collapses a 227-entry city list into 27 published labour-market areas, and someone
    weighing a move thinks in "the Bakersfield area", not in city limits. Counts below are
    that snapshot's; the code reads them from the data. Region cannot replace city
    outright, because California's published areas are titled after two or three principal
    cities and a program joins one only when its city is one of those. That leaves 1,741
    programs — 53% — in cities no area title names, and city is the only geographic handle
    they have. Dropping city would take the last one away from more than half the dataset.

    Two independent controls would let a reader ask for Fresno MSA and Visalia at once and
    get a blank screen with no explanation, so the city list derives from the region
    selection instead: it lists only the cities inside whatever region is chosen, and
    changing region clears a stale city. One control narrows the other; neither can
    contradict it.

    What neither control does is guess. A region never absorbs a nearby unplaced city, so
    Clovis stays out of Fresno MSA and Pleasant Hill stays out of the Oakland MD even though
    both sit in those areas' counties. Everything below exists to make that visible instead
    of letting the filter imply a catchment it does not have.
  */
  const cityOptions = useMemo(
    () => cities(programs.filter((program) => matchesArea(program, area))),
    [programs, area],
  );

  // Only asked for a named region: under "any" nothing is hidden, and under "unplaced" these
  // programs are the result set rather than the omission from it.
  const hiddenUnplaced = useMemo(
    () => (area.kind === "area" ? unplacedMatches(programs, filters) : 0),
    [programs, filters, area.kind],
  );

  function selectArea(next: AreaFilter) {
    setArea(next);
    // The city list is a subset of the region, so a city carried over from another one would
    // silently return nothing and read as "no programs here" rather than "these cannot both
    // be true".
    setCity(null);
    setLimit(PAGE_SIZE);
  }

  // Comparison selection, kept as ids so it survives filtering: picking two programs and
  // then narrowing the search should not silently discard the choice.
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [compareOpen, setCompareOpen] = useState(false);

  const compareSelected = useMemo(
    () =>
      compareIds
        .map((id) => programs.find((p) => p.i === id))
        .filter((p): p is SearchEntry => p !== undefined),
    [compareIds, programs],
  );

  function toggleCompare(id: string) {
    setCompareIds((current) => {
      if (current.includes(id)) return current.filter((x) => x !== id);
      if (current.length >= MAX_COMPARE) return current;
      return [...current, id];
    });
  }

  const visible = results.slice(0, limit);

  function clear() {
    setQuery("");
    setOnlyReported(false);
    setOutlook("any");
    setMaxCost(null);
    setArea(ANY_AREA);
    setCity(null);
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
          <label htmlFor="area">{t.region}</label>
          <select
            id="area"
            value={areaOptionValue(area)}
            aria-describedby="area-note"
            onChange={(e) => selectArea(areaFromOptionValue(e.target.value))}
          >
            <option value="">{t.filterAnyCity}</option>
            {areaOptions.map((option) => (
              <option
                key={option.name}
                value={areaOptionValue({ kind: "area", name: option.name })}
              >
                {option.name} ({option.count.toLocaleString()})
              </option>
            ))}
            {/*
              Named and selectable, never a silent remainder. Without this option the 53% of
              programs the state places nowhere would be reachable only by leaving the filter
              alone, which is indistinguishable from hiding them.
            */}
            {stats.unplaced > 0 && (
              <option value={areaOptionValue(UNPLACED_AREA)}>
                {t.unplacedOption(stats.unplaced)}
              </option>
            )}
          </select>
          <p id="area-note" style={{ margin: 0, fontSize: "0.8125rem", lineHeight: 1.45 }}>
            {t.areaNote(stats.unplaced, stats.total)}
          </p>
        </div>

        <div className="field">
          <label htmlFor="city">{t.filterCity}</label>
          <select
            id="city"
            value={city ?? ""}
            onChange={(e) => {
              setCity(e.target.value === "" ? null : e.target.value);
              setLimit(PAGE_SIZE);
            }}
          >
            {/*
              The "all" label follows the region, so it never claims a reach the list does
              not have: with a region chosen these are that region's cities, not California's.
            */}
            <option value="">
              {area.kind === "any"
                ? t.filterAnyCity
                : area.kind === "unplaced"
                  ? t.anyCityUnplaced
                  : t.anyCityInArea}
            </option>
            {cityOptions.map((option) => (
              <option key={option.name} value={option.name}>
                {option.name} ({option.count.toLocaleString()})
              </option>
            ))}
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
          The facts that justify the whole dataset, stated before any result. The first two
          are public today and neither is discoverable beside the other anywhere else. The
          third is about the dataset's own reach rather than California's training system,
          and it sits here because a reader deserves it before, not after, they narrow by
          region and wonder where everything went.
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
          {/*
            Stated here rather than only inside the filter, because it is a fact about the
            dataset a reader is owed before they reach for a region: half of these programs
            are somewhere the state's own geography does not describe.
          */}
          {stats.unplaced > 0 && (
            <li>
              {t.statUnplaced(stats.unplaced, stats.total)}{" "}
              <button type="button" className="linklike" onClick={() => selectArea(UNPLACED_AREA)}>
                {t.showThese}
              </button>
            </li>
          )}
        </ul>

        {/*
          The cost of the region filter, in the exact terms of the search that is runnint.
          A reader who narrowed to Fresno MSA must not read the result as "everything near
          Fresno", and the honest correction is the count of what a region can never include.
        */}
        {hiddenUnplaced > 0 && (
          <div className="panel panel-quiet" style={{ marginBottom: "1.5rem" }}>
            <p style={{ margin: 0 }}>
              {t.areaHidesUnplaced(hiddenUnplaced)}{" "}
              <button type="button" className="linklike" onClick={() => selectArea(UNPLACED_AREA)}>
                {t.showThese}
              </button>
            </p>
          </div>
        )}

        {area.kind === "unplaced" && (
          <div className="panel panel-quiet" style={{ marginBottom: "1.5rem" }}>
            <p>
              <strong>{t.unplacedHeading}</strong>
            </p>
            <p style={{ margin: 0 }}>{t.unplacedBody}</p>
          </div>
        )}

        <div className="results-head">
          <p className="results-count" role="status" aria-live="polite">
            {t.resultsCount(results.length, programs.length)}
          </p>
        </div>

        {/*
          Outside the results branch on purpose. The comparison is a working set the reader
          assembled, not a view of the current results, so narrowing a search to nothing must
          not make it vanish while the tray still says two are selected.
        */}
        {compareOpen && compareSelected.length >= 2 && (
          <CompareTable entries={compareSelected} lang={lang} />
        )}

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
                <ResultCard
                  key={entry.i}
                  entry={entry}
                  lang={lang}
                  compared={compareIds.includes(entry.i)}
                  compareFull={compareIds.length >= MAX_COMPARE}
                  onToggleCompare={toggleCompare}
                />
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

      <CompareTray
        selected={compareSelected}
        lang={lang}
        open={compareOpen}
        onRemove={(id) => setCompareIds((c) => c.filter((x) => x !== id))}
        onClear={() => {
          setCompareIds([]);
          setCompareOpen(false);
        }}
        onOpen={() => setCompareOpen((open) => !open)}
      />
    </div>
  );
}

function ResultCard({
  entry,
  lang,
  compared,
  compareFull,
  onToggleCompare,
}: {
  entry: SearchEntry;
  lang: Lang;
  compared: boolean;
  compareFull: boolean;
  onToggleCompare: (id: string) => void;
}) {
  const t = dict(lang);
  const shrinking = isShrinking(entry.g);
  const atLimit = compareFull && !compared;
  // Named only where the state named it. A card with no region says nothing about where the
  // program is beyond its city, which is exactly the claim the data supports.
  const region = areaOf(entry);

  return (
    <li className={`card${entry.r ? "" : " is-unreported"}${shrinking ? " is-shrinking" : ""}`}>
      <div className="card-head">
        <h3>
          <Link href={`/${lang}/programs/${entry.i}/`}>{entry.n ?? "—"}</Link>
        </h3>
        <label className="compare-check" title={atLimit ? t.compareFull : undefined}>
          <input
            type="checkbox"
            checked={compared}
            disabled={atLimit}
            onChange={() => onToggleCompare(entry.i)}
            aria-label={`${t.compareAdd}: ${entry.n ?? ""}`}
          />
          <span>{t.compareAdd}</span>
        </label>
      </div>
      <p className="card-provider">
        {entry.p ? (
          <Link href={`/${lang}/providers/${slugify(entry.p)}/`}>{tidyName(entry.p)}</Link>
        ) : null}
        {entry.c ? ` · ${entry.c}` : ""}
        {region === null ? "" : ` · ${region}`}
      </p>

      <dl className="facts">
        <Fact
          label={t.cost}
          value={
            entry.$ === null
              ? null
              : entry.$partial
                ? t.costAtLeast(money(entry.$, lang) ?? "")
                : money(entry.$, lang)
          }
          lang={lang}
        />
        <Fact label={t.length} value={entry.w === null ? null : t.weeks(entry.w)} lang={lang} />
        <Fact label={t.employmentRate} value={percent(entry.er, lang)} lang={lang} />
        <Fact label={t.medianEarnings} value={money(entry.me, lang)} lang={lang} />
      </dl>

      {/*
        * Said on the card, beneath the figures it qualifies, because the card is where a
        * reader first compares these numbers against the card above and below it. The
        * figures stay: they are what the provider filed, and they are real. What the card
        * must not do is let them pass as this one program's result.
        *
        * Gated on `entry.r` as well: five of the 103 reported no outcomes at all, and a
        * caution about figures that are not on screen would be a puzzle rather than a
        * warning.
        */}
      {entry.r && !isOwnCohort(entry) && (
        <p style={{ margin: "0.875rem 0 0", fontSize: "0.875rem", lineHeight: 1.45 }}>
          <span className="badge badge-small">{COHORT_NOT_OWN[lang].badge}</span>{" "}
          {COHORT_NOT_OWN[lang].note}
        </p>
      )}

      {entry.o.length > 0 && (
        <p style={{ marginBottom: 0, marginTop: "0.875rem", fontSize: "0.9375rem" }}>
          {t.leadsTo}: <strong>{entry.o.join(" · ")}</strong>
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
