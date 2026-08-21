"use client";

import Link from "next/link";
import { useDeferredValue, useEffect, useMemo, useState } from "react";

import { dict, feedTextLang, type Lang } from "@/lib/i18n";
import { lengthText, money, percent, signedPercent, tidyName } from "@/lib/format";
import {
  ANY_AREA,
  UNPLACED_AREA,
  areaFromOptionValue,
  areaOf,
  areaOptionValue,
  areas,
  cities,
  competencyBasedLength,
  isShrinking,
  matchesArea,
  matchesFilters,
  runSearch,
  score,
  summarise,
  terms,
  unmeasuredLength,
  unplacedMatches,
  type AreaFilter,
  type Filters,
  type Outlook,
  type Sort,
} from "@/lib/search";
import type { SearchEntry } from "@/lib/types";
import { Fact } from "./Measure";
import { CompareTable, CompareTray, MAX_COMPARE } from "./Compare";
import { isOwnCohort } from "@/lib/compare";
import { filtersFromParams, filtersToQueryString } from "@/lib/shareable";
import {
  SHORTLIST_PARAM,
  shortlistIds,
  idsFromParam,
  idsToParam,
  MAX_ITEMS as MAX_SAVED,
  type ShortlistItem,
  isSaved as idIsSaved,
  readShortlist,
  toggle as toggleSaved,
  writeShortlist,
} from "@/lib/shortlist";
import { slugify } from "@/lib/providers";

const COST_CAPS = [2000, 5000, 10000, 20000];

/*
 * Length caps, in weeks.
 *
 * The same four bands this project already segments completion by — see the note beside the
 * withdrawn "better than typical" verdict in `Measure` — so the control a reader narrows with
 * and the evidence that narrowing matters are the same cut of the data rather than two
 * different ones. They also land where the dataset does: 239 programs finish inside four
 * weeks, 846 inside twelve, 1,740 inside twenty-six and 2,732 inside a year, so every option
 * meaningfully divides the list instead of returning almost all of it or almost none.
 */
const LENGTH_CAPS = [4, 12, 26, 52];

const PAGE_SIZE = 25;

/** Matches the private helper in lib/i18n.ts: grouped digits, the same in both languages. */
function fmt(n: number): string {
  return new Intl.NumberFormat("en-US").format(n);
}

/**
 * One filter the reader could drop, and what dropping it would find.
 *
 * Assembled only when the search returns nothing. "Try removing a filter" asks the reader to
 * do the work of guessing which of six controls is the one excluding everything, when the
 * page can simply run the search six more times and tell them — including telling them, when
 * it is true, that no single removal helps.
 */
interface Relaxation {
  key: string;
  label: string;
  count: number;
  apply: () => void;
}

export function SearchApp({ programs, lang }: { programs: SearchEntry[]; lang: Lang }) {
  const t = dict(lang);
  const [query, setQuery] = useState("");
  const [onlyReported, setOnlyReported] = useState(false);
  const [outlook, setOutlook] = useState<Outlook>("any");
  const [maxCost, setMaxCost] = useState<number | null>(null);
  const [maxWeeks, setMaxWeeks] = useState<number | null>(null);
  const [area, setArea] = useState<AreaFilter>(ANY_AREA);
  const [city, setCity] = useState<string | null>(null);
  const [sort, setSort] = useState<Sort>("relevance");
  const [limit, setLimit] = useState(PAGE_SIZE);

  const deferredQuery = useDeferredValue(query);

  const filters = useMemo<Filters>(
    () => ({ query: deferredQuery, onlyReported, outlook, maxCost, maxWeeks, area, city, sort }),
    [deferredQuery, onlyReported, outlook, maxCost, maxWeeks, area, city, sort],
  );

  /*
    The search carried in the URL, put back on the controls.

    `filtersFromParams` has existed and been tested since the share link shipped, and nothing
    called it. Only the writing half was wired up, so "Copy link to this search" handed
    somebody a link that opened on all 3,266 programs — the recipient saw a different screen
    from the sender, and neither of them could tell. The same gap emptied the search on the
    way back from a program page, which is the movement someone actually makes while working
    through a result list: open one, read it, return, open the next.

    Read after mount rather than during render, for the reason the shortlist below is: these
    pages are statically exported and prerendered where there is no location to read, so
    reading during render would make the server and client disagree and React would throw the
    markup away. `restored` gates the writer beneath, which must not run against default state
    before the incoming link has been read — that would erase the very parameters it is about
    to restore.
  */
  const [restored, setRestored] = useState(false);

  useEffect(() => {
    const incoming = filtersFromParams(new URLSearchParams(window.location.search));
    setQuery(incoming.query);
    setOnlyReported(incoming.onlyReported);
    setOutlook(incoming.outlook);
    setMaxCost(incoming.maxCost);
    setMaxWeeks(incoming.maxWeeks);
    setArea(incoming.area);
    setCity(incoming.city);
    setSort(incoming.sort);
    setRestored(true);
  }, []);

  const results = useMemo(() => runSearch(programs, filters), [programs, filters]);

  const stats = useMemo(() => summarise(programs), [programs]);
  const areaOptions = useMemo(() => areas(programs), [programs]);
  const unreported = stats.total - stats.reported;

  /*
    Programs the length filter removes for reasons the filter itself cannot state.

    Exactly the disclosure the outlook filter makes below, for exactly the same reason: "26
    weeks or less" reads as a claim about every program it leaves out, and for these it is not
    one. A control that silently drops a program on the grounds that it has no comparable
    length has told the reader it is too long, which is a thing the data does not say.

    Two counts, not one, because there are two populations here and until 2026-08-07 this site
    reported one of them as the other. Nobody filed a length for the first. The second is
    competency-based: it finishes when the student can do the work, which is a fact about the
    course that a reader may well be looking for, and describing it as unreported hid it
    inside a bucket labelled "the provider did not say".
  */
  const hiddenNoLength = useMemo(() => unmeasuredLength(programs, filters), [programs, filters]);
  const hiddenCompetency = useMemo(
    () => competencyBasedLength(programs, filters),
    [programs, filters],
  );

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

  /*
    Programs the outlook filter removes for having no projection at all.

    "Only jobs California expects to grow" is read as a claim about every program it leaves
    out, and for these it is not one: the state publishes no ten-year figure for the work,
    so the filter has nothing to test. Saying so is the same rule the site follows for a
    suppressed outcome — an absent number is never quietly converted into a bad one.

    A job the state expects to stay the same size is a different case and is deliberately
    left silent: it really is not growing, and the option says "expects to grow".
  */
  const hiddenNoProjection = useMemo(() => {
    if (filters.outlook === "any") return 0;
    const searchTerms = terms(filters.query);
    const ignoringOutlook: Filters = { ...filters, outlook: "any" };

    let found = 0;
    for (const entry of programs) {
      if (entry.g !== null) continue;
      if (score(entry, searchTerms) < 0) continue;
      if (!matchesFilters(entry, ignoringOutlook)) continue;
      found += 1;
    }
    return found;
  }, [programs, filters]);

  function selectArea(next: AreaFilter) {
    setArea(next);
    // The city list is a subset of the region, so a city carried over from another one would
    // silently return nothing and read as "no programs here" rather than "these cannot both
    // be true".
    setCity(null);
    setLimit(PAGE_SIZE);
  }

  /*
    What each active filter is costing this search, computed only when the answer is empty.

    Each entry re-runs the whole search with exactly one control returned to its default, so
    the count beside it is the real number of programs that control is holding back rather
    than an estimate. Entries that would still find nothing are dropped: offering a reader a
    button that leads to another empty screen is the same failure as the hint this replaces.
  */
  const relaxations = useMemo<Relaxation[]>(() => {
    if (results.length > 0) return [];

    const options: Relaxation[] = [];
    const found = (override: Partial<Filters>) => runSearch(programs, { ...filters, ...override }).length;

    if (filters.query.trim() !== "") {
      options.push({
        key: "query",
        label: t.filterNameQuery(filters.query.trim()),
        count: found({ query: "" }),
        apply: () => setQuery(""),
      });
    }
    if (onlyReported) {
      options.push({
        key: "reported",
        label: t.filterNameReported,
        count: found({ onlyReported: false }),
        apply: () => setOnlyReported(false),
      });
    }
    if (outlook !== "any") {
      options.push({
        key: "outlook",
        label: t.filterNameOutlook(
          outlook === "growing" ? t.outlookGrowing : t.outlookShrinking,
        ),
        count: found({ outlook: "any" }),
        apply: () => setOutlook("any"),
      });
    }
    if (maxCost !== null) {
      options.push({
        key: "cost",
        label: t.filterNameCost(t.costAtMost(money(maxCost, lang) ?? "")),
        count: found({ maxCost: null }),
        apply: () => setMaxCost(null),
      });
    }
    if (maxWeeks !== null) {
      options.push({
        key: "length",
        label: t.filterNameLength(t.lengthAtMost(maxWeeks)),
        count: found({ maxWeeks: null }),
        apply: () => setMaxWeeks(null),
      });
    }
    if (area.kind !== "any") {
      // The unplaced selection is a real choice with a real name, so removing it is named
      // after what it selects rather than after the absence of a region.
      options.push({
        key: "area",
        label: area.kind === "area" ? t.filterNameArea(area.name) : t.filterNameUnplaced,
        count: found({ area: ANY_AREA }),
        apply: () => {
          setArea(ANY_AREA);
          setCity(null);
          setLimit(PAGE_SIZE);
        },
      });
    }
    if (city !== null) {
      options.push({
        key: "city",
        label: t.filterNameCity(city),
        count: found({ city: null }),
        apply: () => {
          setCity(null);
          setLimit(PAGE_SIZE);
        },
      });
    }

    return options.filter((option) => option.count > 0).sort((a, b) => b.count - a.count);
  }, [
    results.length,
    programs,
    filters,
    t,
    lang,
    onlyReported,
    outlook,
    maxCost,
    maxWeeks,
    area,
    city,
  ]);

  // Comparison selection, kept as ids so it survives filtering: picking two programs and
  // then narrowing the search should not silently discard the choice.
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [compareOpen, setCompareOpen] = useState(false);

  /*
   * The shortlist, which lives on this device and nowhere else.
   *
   * Read after mount rather than during render: the pages are statically exported and
   * prerendered on a machine with no localStorage, so reading during render would make the
   * server and client disagree about what is saved and React would discard the markup.
   *
   * What someone saves here is not a shopping basket. Taken together it can indicate that a
   * person is out of work, roughly what they earn, where they live and — from a run of
   * phlebotomy and nursing-assistant courses — something close to health information. That
   * is the argument for localStorage over an account: the safest place to keep this is the
   * reader's own machine, and the safest quantity to collect is none.
   */
  const [saved, setSaved] = useState<ShortlistItem[]>([]);
  const [savedOnly, setSavedOnly] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setSaved(readShortlist());
  }, []);

  /*
   * A shortlist someone was sent.
   *
   * This is the thing people actually do with a site like this: pick four programs and show
   * them to a case manager, a partner, or whoever is helping. A URL does that better than an
   * account would, because the person receiving it does not have to sign up to open it — and
   * the ids are already short enough that twenty fit in a link.
   *
   * Read after mount, like the shortlist itself: these pages are statically exported and
   * prerendered where there is no location to read.
   */
  const [sharedIds, setSharedIds] = useState<string[]>([]);

  useEffect(() => {
    const raw = new URLSearchParams(window.location.search).get(SHORTLIST_PARAM);
    setSharedIds(idsFromParam(raw));
  }, []);

  /*
   * Only the ids this dataset can actually open. An id that no longer exists is dropped and
   * counted, and the count is shown: a link that quietly renders three programs when it was
   * sent with four leaves the reader believing they have seen the whole list.
   */
  const sharedPrograms = useMemo(
    () =>
      sharedIds
        .map((id) => programs.find((entry) => entry.i === id))
        .filter((entry): entry is SearchEntry => entry !== undefined),
    [sharedIds, programs],
  );
  const droppedFromShare = sharedIds.length - sharedPrograms.length;
  const viewingShared = sharedIds.length > 0;

  // Just the state change. The effect below owns the address bar, and two writers racing over
  // one URL is how a shared list ends up half-removed.
  function exitShared() {
    setSharedIds([]);
  }

  function onToggleSave(id: string) {
    setSaved((current) => {
      const next = toggleSaved(current, id, Date.now());
      writeShortlist(next);
      return next;
    });
  }

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

  /*
   * The saved view narrows what is already on screen rather than searching afresh: someone
   * who saved four programs and then typed a new query is asking which of their four match
   * it, not to have the query thrown away.
   */
  const shown = viewingShared
    ? sharedPrograms
    : savedOnly
      ? visible.filter((entry) => idIsSaved(saved, entry.i))
      : visible;

  /*
   * The current search, as a query string. Encoding the state in the URL makes the search
   * shareable, bookmarkable and back-button-correct, and it is what turns "show someone" into
   * a link rather than a feature that needs an account behind it.
   *
   * Built from `filters` rather than from the raw controls, so the link and the results on
   * screen are the same search: `filters` carries the deferred query the visible list was
   * computed from, and a link that promised a query the page had not run yet would be a
   * quieter version of the bug this whole block fixes.
   */
  const search = filtersToQueryString(filters);

  /*
   * The address bar, kept equal to the search.
   *
   * `replaceState`, never `pushState`. Pushing would put a history entry behind every
   * keystroke, so Back from a program page would walk a reader through "weldin", "weldi",
   * "weld" one press at a time instead of returning them to their search. Replacing means the
   * one entry for this page always describes what is on it, which is what makes the browser's
   * own Back button restore the results — no navigation code involved.
   *
   * The shared-shortlist parameter is carried through rather than rebuilt. It belongs to a
   * different feature and this writer does not encode it, so composing it back in is what
   * stops a link someone was sent from being stripped by the first render that follows it.
   */
  useEffect(() => {
    if (!restored) return;
    /*
      Nothing is written while the rendered search is behind the box. `search` is built from
      the deferred query, so the render that first sees a new keystroke still carries the old
      one — and on arrival from a link that is the render that would write `/en/` over the
      `?q=welding` it had just restored. Waiting for the two to agree also means the address
      bar is updated once per settled search rather than once per character, which keeps a
      long query well clear of the browsers that throttle history writes.
    */
    if (deferredQuery !== query) return;

    const params = new URLSearchParams(search);
    if (sharedIds.length > 0) params.set(SHORTLIST_PARAM, idsToParam(sharedIds));
    const encoded = params.toString();
    const next = `${window.location.pathname}${encoded ? `?${encoded}` : ""}${window.location.hash}`;

    if (next === `${window.location.pathname}${window.location.search}${window.location.hash}`) {
      return;
    }
    // The existing state object is passed back so Next's router keeps whatever it stored for
    // this entry; only the URL is ours to change.
    window.history.replaceState(window.history.state, "", next);
  }, [restored, search, sharedIds, deferredQuery, query]);

  const anyFilterActive =
    filters.query.trim() !== "" ||
    onlyReported ||
    outlook !== "any" ||
    maxCost !== null ||
    maxWeeks !== null ||
    area.kind !== "any" ||
    city !== null;

  function clear() {
    setQuery("");
    setOnlyReported(false);
    setOutlook("any");
    setMaxCost(null);
    setMaxWeeks(null);
    setArea(ANY_AREA);
    setCity(null);
    setSort("relevance");
    setLimit(PAGE_SIZE);
  }

  return (
    <div className="shell search-layout">
      {/*
        The one thing the search page never said: what it is.

        A first-time visitor previously met a filter panel and a list of program names with
        no statement of whose data this is, what it costs them, or what a blank means — the
        tagline in the masthead was the whole of it, and the page that explains the figures
        was reachable only from an individual program. Spanning both grid columns so it sits
        above the panel rather than inside it, and kept to a heading, two sentences and a
        link so the results stay within a screen or so of the top on a phone.
      */}
      <div style={{ gridColumn: "1 / -1" }}>
        <h1
          style={{
            margin: "0 0 0.5rem",
            fontSize: "clamp(1.375rem, 3.5vw, 1.75rem)",
            lineHeight: 1.2,
          }}
        >
          {t.searchIntroHeading}
        </h1>
        <p style={{ margin: "0 0 0.5rem", maxWidth: "var(--measure)", lineHeight: 1.5 }}>
          {t.searchIntroBody}
        </p>
        <p style={{ margin: 0 }}>
          <Link href={`/${lang}/about/`}>{t.methodologyLink} →</Link>
        </p>
      </div>

      {/*
        Collapsed on a phone, always open on a desktop.

        Measured before this: 2,262 pixels — 2.7 phone screens — of masthead, intro and
        filter controls before the first result. Someone arriving from a search engine met
        five selects and twenty-six checkboxes before a single program. The panel is not
        wrong, it is just not what they came for.

        A <details> rather than CSS `order`, because reordering with CSS separates what a
        sighted reader sees from what a keyboard reaches, and the results-before-filters
        arrangement would then be true only visually. Here the document order never changes;
        the desktop rule below simply always reveals the content and hides the toggle.
      */}
      <div className="search-controls">
      {/*
        The query box sits outside the disclosure on purpose. Collapsing the filter panel
        with the search field still inside it hid the one control every visitor needs, which
        is a worse failure than the scrolling it was meant to fix.
      */}
      {/*
        * Search is client-side, so with JavaScript off the box below is an affordance that
        * does nothing -- the form has no action and submitting it just reloads the page.
        * Browsing needs no JavaScript at all: all 670 occupation pages and 581 provider
        * pages ship as static links. Say which half works and point at it, rather than
        * leave someone on a library machine or a locked-down phone poking an inert box.
        */}
      <noscript>
        <p className="lede">
          {t.noScriptSearch}{" "}
          <Link href={`/${lang}/occupations/`}>{t.noScriptBrowseOccupations}</Link>
          {" · "}
          <Link href={`/${lang}/providers/`}>{t.noScriptBrowseProviders}</Link>
        </p>
      </noscript>
      <form
        className="query-form"
        role="search"
        aria-label={t.searchLabel}
        onSubmit={(e) => e.preventDefault()}
      >
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
      </form>

      <details className="filters-disclosure">
        <summary>{t.filters}</summary>
        <form
          className="filters"
          aria-label={t.filters}
          onSubmit={(e) => e.preventDefault()}
        >
        {/*
          The checkbox names its own consequence and the note underneath refuses the
          inference it invites. "Only programs with reported outcomes" was true and unusable:
          it did not say that a third of the dataset is on the other side of it, and it read
          as a quality filter, which is exactly what it is not.
        */}
        <fieldset style={{ border: 0, margin: 0, padding: 0 }}>
          <legend>{t.filterUnreportedLegend}</legend>
          <label className="checkline">
            <input
              type="checkbox"
              checked={onlyReported}
              aria-describedby="reported-note"
              onChange={(e) => {
                setOnlyReported(e.target.checked);
                setLimit(PAGE_SIZE);
              }}
            />
            <span>{t.filterHideUnreported(unreported)}</span>
          </label>
          <p
            id="reported-note"
            style={{ margin: "0.5rem 0 0", fontSize: "0.8125rem", lineHeight: 1.45 }}
          >
            {t.filterHideUnreportedNote(unreported)}
          </p>
        </fieldset>

        <div className="field">
          <label htmlFor="outlook">{t.filterOutlook}</label>
          <select
            id="outlook"
            value={outlook}
            aria-describedby={hiddenNoProjection > 0 ? "outlook-note" : undefined}
            onChange={(e) => {
              setOutlook(e.target.value as Outlook);
              setLimit(PAGE_SIZE);
            }}
          >
            <option value="any">{t.outlookAny}</option>
            <option value="growing">{t.outlookGrowing}</option>
            <option value="shrinking">{t.outlookShrinking}</option>
          </select>
          {hiddenNoProjection > 0 && (
            <p id="outlook-note" style={{ margin: 0, fontSize: "0.8125rem", lineHeight: 1.45 }}>
              {t.filterOutlookNoProjection(hiddenNoProjection)}
            </p>
          )}
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

        {/*
          Cost is the decision for someone out of work, so the note says what the price
          covers and — as importantly — what it does not net off. The federal field is the
          tuition and supplies a student pays without WIOA funding; naming it "out-of-pocket"
          with no gloss invited the reading that aid had already been deducted.
        */}
        <div className="field">
          <label htmlFor="cost">{t.filterMaxCost}</label>
          <select
            id="cost"
            value={maxCost ?? ""}
            aria-describedby="cost-note"
            onChange={(e) => {
              setMaxCost(e.target.value === "" ? null : Number(e.target.value));
              setLimit(PAGE_SIZE);
            }}
          >
            <option value="">{t.filterAnyCost}</option>
            {COST_CAPS.map((cap) => (
              <option key={cap} value={cap}>
                {t.costAtMost(money(cap, lang) ?? "")}
              </option>
            ))}
          </select>
          <p id="cost-note" style={{ margin: 0, fontSize: "0.8125rem", lineHeight: 1.45 }}>
            {t.filterMaxCostNote}
          </p>
        </div>

        {/*
          The other half of what the reader is spending, directly beneath the money.

          Cost has had a control since the first release and time has not, though the index
          has carried a length all along and shows it on every card. Someone choosing between
          a 12-week certificate and a 72-week pathway is making two different decisions about
          their year, and until now the only way to act on that was to read 3,266 cards.

          The note does the second job: it says what the filter cannot test, and it says why
          narrowing here is worth doing before reading anyone's completion rate. Those medians
          are this project's own measurement — the same one that retired the "better than
          typical" verdict from the program page — and they are stated so a reader can see
          that a short program and a long one are not on one scale.
        */}
        <div className="field">
          <label htmlFor="length">{t.filterLength}</label>
          <select
            id="length"
            value={maxWeeks ?? ""}
            aria-describedby={
              // Each disclosure joins the description only while it has something to say, so a
              // screen reader is never pointed at an element that is not on the page.
              ["length-note"]
                .concat(hiddenNoLength > 0 ? ["length-unmeasured"] : [])
                .concat(hiddenCompetency > 0 ? ["length-competency"] : [])
                .join(" ")
            }
            onChange={(e) => {
              setMaxWeeks(e.target.value === "" ? null : Number(e.target.value));
              setLimit(PAGE_SIZE);
            }}
          >
            <option value="">{t.filterAnyLength}</option>
            {LENGTH_CAPS.map((cap) => (
              <option key={cap} value={cap}>
                {t.lengthAtMost(cap)}
              </option>
            ))}
          </select>
          <p id="length-note" style={{ margin: 0, fontSize: "0.8125rem", lineHeight: 1.45 }}>
            {t.filterLengthNote}
          </p>
          {hiddenNoLength > 0 && (
            <p
              id="length-unmeasured"
              style={{ margin: 0, fontSize: "0.8125rem", lineHeight: 1.45 }}
            >
              {t.filterLengthUnmeasured(hiddenNoLength)}
            </p>
          )}
          {hiddenCompetency > 0 && (
            <p
              id="length-competency"
              style={{ margin: 0, fontSize: "0.8125rem", lineHeight: 1.45 }}
            >
              {t.filterLengthCompetency(hiddenCompetency)}
            </p>
          )}
        </div>

        <div className="field">
          <label htmlFor="sort">{t.sortBy}</label>
          <select id="sort" value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
            <option value="relevance">{t.sortRelevance}</option>
            <option value="earnings">{t.sortEarnings}</option>
            <option value="cost">{t.sortCost}</option>
            {/*
              Ordering on length is safe in a way ordering on completion or earnings is not.
              Length is a property of the course, so it stays comparable however the provider
              filed its outcome rows — the distinction `ownCohortOnly` in lib/compare.ts is
              built on, and the reason `sortEarnings` above has to exclude the 98 programs
              whose figures describe a whole institution while this does not.
            */}
            <option value="length">{t.sortLength}</option>
            <option value="openings">{t.sortOpenings}</option>
          </select>
        </div>

        <button type="button" className="button" onClick={clear}>
          {t.clearFilters}
        </button>
      </form>
      </details>
      </div>

      <section aria-label={t.resultsRegion}>
        {/*
          The facts that justify the whole dataset, stated before any result. The first two
          are public today and neither is discoverable beside the other anywhere else. The
          third is about the dataset's own reach rather than California's training system,
          and it sits here because a reader deserves it before, not after, they narrow by
          region and wonder where everything went.

          Each button names the number it will show, so the three do not read as three
          identical "Show these" and so a screen-reader user hearing them out of context can
          tell them apart.
        */}
        <ul className="stat-strip">
          <li>
            {t.statReported(stats.reported, stats.total)}{" "}
            <button
              type="button"
              className="linklike"
              onClick={() => {
                setOnlyReported(true);
                setLimit(PAGE_SIZE);
              }}
            >
              {t.showOnlyReported(stats.reported)}
            </button>
          </li>
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
              {t.showTheseN(stats.shrinking)}
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
                {t.showTheseN(stats.unplaced)}
              </button>
            </li>
          )}
        </ul>

        {/*
          The cost of the region filter, in the exact terms of the search that is running.
          A reader who narrowed to Fresno MSA must not read the result as "everything near
          Fresno", and the honest correction is the count of what a region can never include.
        */}
        {hiddenUnplaced > 0 && (
          <div className="panel panel-quiet" style={{ marginBottom: "1.5rem" }}>
            <p style={{ margin: 0 }}>
              {t.areaHidesUnplaced(hiddenUnplaced)}{" "}
              <button type="button" className="linklike" onClick={() => selectArea(UNPLACED_AREA)}>
                {t.showTheseN(hiddenUnplaced)}
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

        {/*
          The shortlist bar, shown only once something is in it.

          An empty control explaining a feature nobody has used yet is an advertisement. The
          bar appears the moment the first program is saved, which is also the moment the
          sentence about where it is stored becomes true and worth reading.
        */}
        {viewingShared && (
          <div className="shared-bar">
            <p className="shared-bar-title">
              <strong>{t.sharedListTitle}</strong>
            </p>
            <p className="shared-bar-body">{t.sharedListBody(sharedPrograms.length)}</p>
            {droppedFromShare > 0 && (
              <p className="shared-bar-body">{t.sharedListDropped(droppedFromShare)}</p>
            )}
            <div className="saved-bar-actions">
              <button
                type="button"
                onClick={() => {
                  // Merged, not replaced: someone opening a shared link may already have a
                  // list of their own, and losing it to a link they were sent would be the
                  // worst possible reading of "save these".
                  setSaved((current) => {
                    let next = current;
                    for (const entry of sharedPrograms) {
                      if (!idIsSaved(next, entry.i)) next = toggleSaved(next, entry.i, Date.now());
                    }
                    writeShortlist(next);
                    return next;
                  });
                  exitShared();
                }}
              >
                {t.sharedListSave}
              </button>
              <button type="button" onClick={exitShared}>
                {t.sharedListExit}
              </button>
            </div>
          </div>
        )}

        {!viewingShared && saved.length > 0 && (
          <div className="saved-bar">
            <p className="saved-bar-count">
              <strong>{t.savedCount(saved.length)}</strong>
            </p>
            <div className="saved-bar-actions">
              <button type="button" onClick={() => setSavedOnly((v) => !v)}>
                {savedOnly ? t.savedShowAll : t.savedShow}
              </button>
              <button
                type="button"
                onClick={() => {
                  const url = new URL(window.location.href);
                  url.search = "";
                  url.searchParams.set(SHORTLIST_PARAM, idsToParam(shortlistIds(saved)));
                  void navigator.clipboard?.writeText(url.toString()).then(() => {
                    setCopied(true);
                    window.setTimeout(() => setCopied(false), 2000);
                  });
                }}
              >
                {copied ? t.copyLinkDone : t.shareSaved}
              </button>
              <button
                type="button"
                onClick={() => {
                  setSaved([]);
                  writeShortlist([]);
                  setSavedOnly(false);
                }}
              >
                {t.savedClear}
              </button>
            </div>
            <p className="saved-bar-note">{t.savedWhere}</p>
          </div>
        )}

        <div className="results-head">
          {/*
            The count is the results section's own heading as well as its live region: it is
            the only true title the section has, and making it one gives the page an h1 → h2
            → h3 outline it previously lacked entirely. `aria-live` rather than
            `role="status"`, which would replace the heading role and take the outline back.
          */}
          <h2 className="results-count" aria-live="polite" aria-atomic="true">
            {viewingShared
              ? t.resultsCount(sharedPrograms.length, programs.length)
              : t.resultsCount(results.length, programs.length)}
          </h2>
          {/*
            Sharing is the thing people actually do with this site: send it to a case manager,
            a partner, the person at the job center. A URL does that better than an account
            would, because whoever receives it does not have to sign up to open it.
          */}
          <button
            type="button"
            className="copy-link"
            onClick={() => {
              const url = `${window.location.origin}${window.location.pathname}${search}`;
              void navigator.clipboard?.writeText(url).then(() => {
                setCopied(true);
                window.setTimeout(() => setCopied(false), 2000);
              });
            }}
          >
            {copied ? t.copyLinkDone : t.copyLink}
          </button>
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
          /*
            The empty state does the arithmetic instead of asking the reader to.

            "Try removing a filter or searching for a broader term" is advice the page is far
            better placed to give than to receive: it knows which controls are set, and it can
            afford to re-run a 3,266-row scan once per control to find out which of them is
            the one holding everything back. So it names them, with the count each would
            return, strongest first.
          */
          <div className="panel panel-quiet">
            <p>
              <strong>{t.noResults}</strong>
            </p>

            {relaxations.length > 0 ? (
              <>
                <p>{t.noResultsRelaxLead}</p>
                <ul style={{ margin: "0 0 0.5rem", paddingLeft: "1.25rem" }}>
                  {relaxations.map((option) => (
                    <li key={option.key} style={{ marginBottom: "0.375rem" }}>
                      <button type="button" className="linklike" onClick={option.apply}>
                        {t.noResultsRelaxOption(option.label, option.count)}
                      </button>
                    </li>
                  ))}
                </ul>
              </>
            ) : anyFilterActive ? (
              <p>
                {t.noResultsNothingHelps}{" "}
                <button type="button" className="linklike" onClick={clear}>
                  {t.clearFilters}
                </button>
              </p>
            ) : (
              <p>{t.noResultsHint}</p>
            )}

            {/*
              Said whenever a search term found nothing, in both languages. It is the whole
              explanation for a Spanish speaker — the corpus is English-only, so a Spanish
              term cannot match — and the Spanish wording carries the worked examples for
              that reason rather than mirroring the English sentence for sentence.
            */}
            {filters.query.trim() !== "" && (
              <p style={{ marginBottom: 0 }}>{t.searchEnglishOnly}</p>
            )}
          </div>
        ) : (
          <>
            <ul className="card-list">
              {shown.map((entry) => (
                <ResultCard
                  key={entry.i}
                  entry={entry}
                  lang={lang}
                  compared={compareIds.includes(entry.i)}
                  compareFull={compareIds.length >= MAX_COMPARE}
                  onToggleCompare={toggleCompare}
                  saved={idIsSaved(saved, entry.i)}
                  savedFull={saved.length >= MAX_SAVED}
                  onToggleSave={onToggleSave}
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
  saved,
  savedFull,
  onToggleSave,
}: {
  entry: SearchEntry;
  lang: Lang;
  compared: boolean;
  compareFull: boolean;
  onToggleCompare: (id: string) => void;
  saved: boolean;
  savedFull: boolean;
  onToggleSave: (id: string) => void;
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
          <Link href={`/${lang}/programs/${entry.i}/`} lang={feedTextLang(lang)}>
            {entry.n ?? "—"}
          </Link>
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
        {/*
          A button, not a checkbox. Comparing is a selection within this page; saving is an
          action with a consequence that outlives it, and the control says which state it is
          in rather than which state it would move to.
        */}
        <button
          type="button"
          className={`save-toggle${saved ? " is-saved" : ""}`}
          aria-pressed={saved}
          disabled={savedFull && !saved}
          title={savedFull && !saved ? t.savedFull : undefined}
          onClick={() => onToggleSave(entry.i)}
        >
          {saved ? t.savedProgram : t.saveProgram}
        </button>
      </div>
      <p className="card-provider">
        {entry.p ? (
          <Link href={`/${lang}/providers/${slugify(entry.p)}/`} lang={feedTextLang(lang)}>
            {tidyName(entry.p)}
          </Link>
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
        {/*
          Through `lengthText`, which is where "a null length is not always 'not reported'"
          is decided once for the card, the program page and the comparison table alike.
        */}
        <Fact label={t.length} value={lengthText(entry.w, entry.cb, t)} lang={lang} />
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
        <p className="cohort-note">
          <span className="badge badge-small">{t.cohortNotOwn}</span>{" "}
          {t.cohortNotOwnNote}
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
