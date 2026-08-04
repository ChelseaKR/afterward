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
  matchesFilters,
  runSearch,
  score,
  summarise,
  terms,
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
function fmt(n: number): string {
  return new Intl.NumberFormat("en-US").format(n);
}

/*
 * TODO(i18n): every string in `COPY` belongs in `web/lib/i18n.ts`, under the key named in the
 * comment above it. They live here because that file was owned by a concurrent change when
 * this landed. Both languages are complete, and the Spanish is written for a Spanish reader
 * rather than rendered from the English — the search hint in particular says something the
 * English one has no reason to say, because the searchable corpus is English-only and that
 * costs a Spanish speaker a result set and an English speaker nothing.
 */
interface SearchCopy {
  /** i18n key: searchIntroHeading */
  introHeading: string;
  /** i18n key: searchIntroBody */
  introBody: string;
  /** i18n key: resultsRegion */
  resultsRegion: string;

  /** i18n key: filterUnreportedLegend */
  unreportedLegend: string;
  /** i18n key: filterHideUnreported */
  unreportedCheckbox: (missing: number) => string;
  /** i18n key: filterHideUnreportedNote */
  unreportedNote: (missing: number) => string;

  /** i18n key: filterOutlook (replaces) */
  outlookLabel: string;
  /** i18n key: outlookAny (replaces) */
  outlookAny: string;
  /** i18n key: outlookGrowing (replaces) */
  outlookGrowing: string;
  /** i18n key: outlookShrinking (replaces) */
  outlookShrinking: string;
  /** i18n key: filterOutlookNoProjection */
  outlookNoProjection: (n: number) => string;

  /** i18n key: areaNote (replaces) */
  areaNote: (unplaced: number, total: number) => string;

  /** i18n key: filterMaxCost (replaces) */
  costLabel: string;
  /** i18n key: costAtMost */
  costAtMost: (value: string) => string;
  /** i18n key: filterMaxCostNote */
  costNote: string;

  /** i18n key: sortEarnings (replaces) */
  sortEarnings: string;
  /** i18n key: sortOpenings (replaces) */
  sortOpenings: string;

  /** i18n key: statReported (replaces) */
  statReported: (reported: number, total: number) => string;
  /** i18n key: statShrinking (replaces) */
  statShrinking: (n: number) => string;
  /** i18n key: statUnplaced (replaces) */
  statUnplaced: (unplaced: number, total: number) => string;
  /** i18n key: showTheseN (replaces showThese, which reads the same on every button) */
  showTheseN: (n: number) => string;
  /** i18n key: showOnlyReported */
  showOnlyReported: (n: number) => string;

  /** i18n key: noResultsRelaxLead */
  relaxLead: string;
  /** i18n key: noResultsRelaxOption */
  relaxOption: (label: string, n: number) => string;
  /** i18n key: noResultsNothingHelps */
  nothingHelps: string;
  /** i18n key: searchEnglishOnly */
  englishOnly: string;

  /*
   * Each active control, named as something a sentence can remove. "Region: Fresno MSA" is
   * how a filter panel labels itself; it is not how anyone says which one to drop.
   */
  /** i18n key: filterNameQuery */
  nameQuery: (query: string) => string;
  /** i18n key: filterNameReported */
  nameReported: string;
  /** i18n key: filterNameOutlook */
  nameOutlook: (option: string) => string;
  /** i18n key: filterNameCost */
  nameCost: (cap: string) => string;
  /** i18n key: filterNameArea */
  nameArea: (area: string) => string;
  /** i18n key: filterNameUnplaced */
  nameUnplaced: string;
  /** i18n key: filterNameCity */
  nameCity: (city: string) => string;
}

const COPY: Record<Lang, SearchCopy> = {
  en: {
    introHeading: "Search California training programs",
    introBody:
      "Every California training program in the federal record: what it costs, how long it " +
      "takes, and — where the provider reported it — how many people finished, how many " +
      "were working six months later, and what they earned. Free to use, no account, and " +
      "the roughly one program in three that reported nothing is listed here too, saying so.",
    resultsRegion: "Search results",

    unreportedLegend: "Programs that reported nothing",
    unreportedCheckbox: (missing) => `Hide the ${fmt(missing)} programs that reported nothing`,
    unreportedNote: (missing) =>
      `Hiding them is not the same as hiding bad programs. Nobody knows how those ` +
      `${fmt(missing)} did — only that they did not say: some filed nothing, and for others ` +
      `the figure was withheld to protect the privacy of a small group.`,

    outlookLabel: "What California expects of the job",
    outlookAny: "All jobs",
    outlookGrowing: "Only jobs California expects to grow",
    outlookShrinking: "Only jobs California expects to shrink",
    outlookNoProjection: (n) =>
      `This filter also leaves out ${fmt(n)} of the programs that match the rest of your ` +
      `search: California publishes no ten-year projection for the work they train for, so ` +
      `there is nothing here for the filter to test. Missing information is not a ` +
      `projection of zero.`,

    areaNote: (unplaced, total) =>
      `California's labour-market regions are each named after two or three cities, and a ` +
      `program counts as being in one only when its city is one of those. That leaves ` +
      `${fmt(unplaced)} of these ${fmt(total)} programs in no region at all — some in the ` +
      `same county as a region listed here, some right next door to one. Choosing a region ` +
      `hides those ${fmt(unplaced)}; it does not move them somewhere else.`,

    costLabel: "Most you can pay",
    costAtMost: (value) => `${value} or less`,
    costNote:
      "Tuition and supplies as the provider reported them, for someone paying without public " +
      "workforce funding. No grant or aid you might qualify for is taken off it.",

    sortEarnings: "Highest reported earnings (one quarter)",
    sortOpenings: "Most openings projected for the job",

    statReported: (reported, total) =>
      `${fmt(reported)} of these ${fmt(total)} programs reported what happened to their ` +
      `students. The other ${fmt(total - reported)} reported nothing at all, which is not ` +
      `evidence that they are worse.`,
    statShrinking: (n) =>
      `${fmt(n)} of these programs train for work California expects there to be less of ` +
      `in ten years.`,
    statUnplaced: (unplaced, total) =>
      `${fmt(unplaced)} of the ${fmt(total)} are in cities California's own published ` +
      `regions do not name, so no region's pay or openings figures are claimed for them.`,
    showTheseN: (n) => (n === 1 ? "Show that one" : `Show those ${fmt(n)}`),
    showOnlyReported: (n) => `Show only the ${fmt(n)} that reported`,

    relaxLead: "Removing any one of these would find programs:",
    relaxOption: (label, n) =>
      n === 1
        ? `Remove ${label} — 1 program matches`
        : `Remove ${label} — ${fmt(n)} programs match`,
    nothingHelps:
      "Removing any single one of them still finds nothing, so more than one is doing the " +
      "excluding.",
    englishOnly:
      "Program names and job titles here are recorded in English only, exactly as the " +
      "provider filed them and the state published them. A search term in another language " +
      "will not match one.",

    nameQuery: (query) => `your search for “${query}”`,
    nameReported: "the filter hiding programs that reported nothing",
    nameOutlook: (option) => `the job filter “${option}”`,
    nameCost: (cap) => `the price limit “${cap}”`,
    nameArea: (area) => `the region “${area}”`,
    nameUnplaced: "the choice to show only programs California places in no region",
    nameCity: (city) => `the city “${city}”`,
  },
  es: {
    introHeading: "Busque programas de capacitación en California",
    introBody:
      "Aquí está cada programa de capacitación de California que consta en el registro " +
      "federal: cuánto cuesta, cuánto dura y —cuando la institución lo reportó— cuántas " +
      "personas terminaron, cuántas estaban trabajando seis meses después y cuánto ganaron. " +
      "Es gratis y sin cuenta, y alrededor de uno de cada tres programas no reportó nada: " +
      "esos también aparecen aquí, y lo dicen.",
    resultsRegion: "Resultados de la búsqueda",

    unreportedLegend: "Programas que no reportaron nada",
    unreportedCheckbox: (missing) =>
      `Ocultar los ${fmt(missing)} programas que no reportaron nada`,
    unreportedNote: (missing) =>
      `Ocultarlos no es lo mismo que ocultar los programas malos. Nadie sabe cómo les fue a ` +
      `esos ${fmt(missing)}; solo que no lo dijeron: unos no presentaron nada y a otros se ` +
      `les omitió la cifra para proteger la privacidad de un grupo pequeño.`,

    outlookLabel: "Qué espera California de la ocupación",
    outlookAny: "Todas las ocupaciones",
    outlookGrowing: "Solo ocupaciones que California espera que crezcan",
    outlookShrinking: "Solo ocupaciones que California espera que se reduzcan",
    outlookNoProjection: (n) =>
      `Este filtro también deja fuera ${fmt(n)} de los programas que coinciden con el resto ` +
      `de su búsqueda: California no publica una proyección a diez años para el trabajo que ` +
      `enseñan, así que el filtro no tiene nada que evaluar. Que falte el dato no es una ` +
      `proyección de cero.`,

    areaNote: (unplaced, total) =>
      `Las regiones laborales de California llevan el nombre de dos o tres ciudades cada ` +
      `una, y un programa cuenta como parte de una región solo si su ciudad es una de esas. ` +
      `Por eso ${fmt(unplaced)} de estos ${fmt(total)} programas no quedan en ninguna ` +
      `región: algunos están en el mismo condado que una región de esta lista, y algunos ` +
      `justo al lado de una. Elegir una región oculta esos ${fmt(unplaced)}; no los coloca ` +
      `en otro lugar.`,

    costLabel: "Lo máximo que puede pagar",
    costAtMost: (value) => `${value} o menos`,
    costNote:
      "La colegiatura y los materiales tal como los reportó la institución, para quien paga " +
      "sin fondos públicos de capacitación. No se le descuenta ninguna beca ni ayuda a la " +
      "que usted pudiera calificar.",

    sortEarnings: "Mayores ingresos reportados (un trimestre)",
    sortOpenings: "Más vacantes proyectadas para la ocupación",

    statReported: (reported, total) =>
      `${fmt(reported)} de estos ${fmt(total)} programas reportaron qué pasó con sus ` +
      `estudiantes. Los otros ${fmt(total - reported)} no reportaron nada, lo cual no es ` +
      `prueba de que sean peores.`,
    statShrinking: (n) =>
      `${fmt(n)} de estos programas preparan para trabajos de los que California espera que ` +
      `haya menos dentro de diez años.`,
    statUnplaced: (unplaced, total) =>
      `${fmt(unplaced)} de los ${fmt(total)} están en ciudades que las regiones publicadas ` +
      `de California no nombran, así que no se les atribuye el pago ni las vacantes de ` +
      `ninguna región.`,
    showTheseN: (n) => (n === 1 ? "Ver ese" : `Ver esos ${fmt(n)}`),
    showOnlyReported: (n) => `Ver solo los ${fmt(n)} que reportaron`,

    relaxLead: "Quitar cualquiera de estos sí encontraría programas:",
    relaxOption: (label, n) =>
      n === 1
        ? `Quitar ${label}: coincide 1 programa`
        : `Quitar ${label}: coinciden ${fmt(n)} programas`,
    nothingHelps:
      "Quitar uno solo de ellos sigue sin encontrar nada, así que hay más de uno dejando " +
      "programas fuera.",
    englishOnly:
      "Los nombres de los programas y de las ocupaciones están registrados solo en inglés, " +
      "tal como los presentó la institución y los publicó el estado. Un término en español " +
      "no va a coincidir con ninguno: pruebe la palabra en inglés — «welding» en lugar de " +
      "«soldadura», «medical assistant» en lugar de «asistente médico».",

    nameQuery: (query) => `su búsqueda de «${query}»`,
    nameReported: "el filtro que oculta los programas que no reportaron nada",
    nameOutlook: (option) => `el filtro de ocupación «${option}»`,
    nameCost: (cap) => `el límite de precio «${cap}»`,
    nameArea: (area) => `la región «${area}»`,
    nameUnplaced: "la opción de ver solo los programas que California no ubica en ninguna región",
    nameCity: (city) => `la ciudad «${city}»`,
  },
};

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
  const copy = COPY[lang];
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
  const unreported = stats.total - stats.reported;

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
        label: copy.nameQuery(filters.query.trim()),
        count: found({ query: "" }),
        apply: () => setQuery(""),
      });
    }
    if (onlyReported) {
      options.push({
        key: "reported",
        label: copy.nameReported,
        count: found({ onlyReported: false }),
        apply: () => setOnlyReported(false),
      });
    }
    if (outlook !== "any") {
      options.push({
        key: "outlook",
        label: copy.nameOutlook(
          outlook === "growing" ? copy.outlookGrowing : copy.outlookShrinking,
        ),
        count: found({ outlook: "any" }),
        apply: () => setOutlook("any"),
      });
    }
    if (maxCost !== null) {
      options.push({
        key: "cost",
        label: copy.nameCost(copy.costAtMost(money(maxCost, lang) ?? "")),
        count: found({ maxCost: null }),
        apply: () => setMaxCost(null),
      });
    }
    if (area.kind !== "any") {
      // The unplaced selection is a real choice with a real name, so removing it is named
      // after what it selects rather than after the absence of a region.
      options.push({
        key: "area",
        label: area.kind === "area" ? copy.nameArea(area.name) : copy.nameUnplaced,
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
        label: copy.nameCity(city),
        count: found({ city: null }),
        apply: () => {
          setCity(null);
          setLimit(PAGE_SIZE);
        },
      });
    }

    return options.filter((option) => option.count > 0).sort((a, b) => b.count - a.count);
  }, [results.length, programs, filters, copy, t, lang, onlyReported, outlook, maxCost, area, city]);

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
  const anyFilterActive =
    filters.query.trim() !== "" ||
    onlyReported ||
    outlook !== "any" ||
    maxCost !== null ||
    area.kind !== "any" ||
    city !== null;

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
          {copy.introHeading}
        </h1>
        <p style={{ margin: "0 0 0.5rem", maxWidth: "var(--measure)", lineHeight: 1.5 }}>
          {copy.introBody}
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
          <legend>{copy.unreportedLegend}</legend>
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
            <span>{copy.unreportedCheckbox(unreported)}</span>
          </label>
          <p
            id="reported-note"
            style={{ margin: "0.5rem 0 0", fontSize: "0.8125rem", lineHeight: 1.45 }}
          >
            {copy.unreportedNote(unreported)}
          </p>
        </fieldset>

        <div className="field">
          <label htmlFor="outlook">{copy.outlookLabel}</label>
          <select
            id="outlook"
            value={outlook}
            aria-describedby={hiddenNoProjection > 0 ? "outlook-note" : undefined}
            onChange={(e) => {
              setOutlook(e.target.value as Outlook);
              setLimit(PAGE_SIZE);
            }}
          >
            <option value="any">{copy.outlookAny}</option>
            <option value="growing">{copy.outlookGrowing}</option>
            <option value="shrinking">{copy.outlookShrinking}</option>
          </select>
          {hiddenNoProjection > 0 && (
            <p id="outlook-note" style={{ margin: 0, fontSize: "0.8125rem", lineHeight: 1.45 }}>
              {copy.outlookNoProjection(hiddenNoProjection)}
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
            {copy.areaNote(stats.unplaced, stats.total)}
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
          <label htmlFor="cost">{copy.costLabel}</label>
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
                {copy.costAtMost(money(cap, lang) ?? "")}
              </option>
            ))}
          </select>
          <p id="cost-note" style={{ margin: 0, fontSize: "0.8125rem", lineHeight: 1.45 }}>
            {copy.costNote}
          </p>
        </div>

        <div className="field">
          <label htmlFor="sort">{t.sortBy}</label>
          <select id="sort" value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
            <option value="relevance">{t.sortRelevance}</option>
            <option value="earnings">{copy.sortEarnings}</option>
            <option value="cost">{t.sortCost}</option>
            <option value="openings">{copy.sortOpenings}</option>
          </select>
        </div>

        <button type="button" className="button" onClick={clear}>
          {t.clearFilters}
        </button>
      </form>
      </details>
      </div>

      <section aria-label={copy.resultsRegion}>
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
            {copy.statReported(stats.reported, stats.total)}{" "}
            <button
              type="button"
              className="linklike"
              onClick={() => {
                setOnlyReported(true);
                setLimit(PAGE_SIZE);
              }}
            >
              {copy.showOnlyReported(stats.reported)}
            </button>
          </li>
          <li>
            {copy.statShrinking(stats.shrinking)}{" "}
            <button
              type="button"
              className="linklike"
              onClick={() => {
                setOutlook("shrinking");
                setLimit(PAGE_SIZE);
              }}
            >
              {copy.showTheseN(stats.shrinking)}
            </button>
          </li>
          {/*
            Stated here rather than only inside the filter, because it is a fact about the
            dataset a reader is owed before they reach for a region: half of these programs
            are somewhere the state's own geography does not describe.
          */}
          {stats.unplaced > 0 && (
            <li>
              {copy.statUnplaced(stats.unplaced, stats.total)}{" "}
              <button type="button" className="linklike" onClick={() => selectArea(UNPLACED_AREA)}>
                {copy.showTheseN(stats.unplaced)}
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
                {copy.showTheseN(hiddenUnplaced)}
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
          {/*
            The count is the results section's own heading as well as its live region: it is
            the only true title the section has, and making it one gives the page an h1 → h2
            → h3 outline it previously lacked entirely. `aria-live` rather than
            `role="status"`, which would replace the heading role and take the outline back.
          */}
          <h2 className="results-count" aria-live="polite" aria-atomic="true">
            {t.resultsCount(results.length, programs.length)}
          </h2>
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
                <p>{copy.relaxLead}</p>
                <ul style={{ margin: "0 0 0.5rem", paddingLeft: "1.25rem" }}>
                  {relaxations.map((option) => (
                    <li key={option.key} style={{ marginBottom: "0.375rem" }}>
                      <button type="button" className="linklike" onClick={option.apply}>
                        {copy.relaxOption(option.label, option.count)}
                      </button>
                    </li>
                  ))}
                </ul>
              </>
            ) : anyFilterActive ? (
              <p>
                {copy.nothingHelps}{" "}
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
              <p style={{ marginBottom: 0 }}>{copy.englishOnly}</p>
            )}
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
