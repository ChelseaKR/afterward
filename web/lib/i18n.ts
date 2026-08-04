/**
 * English and Spanish ship together from the first release.
 *
 * About 28% of Californians speak Spanish at home, and the people most likely to need this
 * tool are among the least well served by English-only government software. Translation is
 * therefore a launch requirement, not a later phase, and the type below makes an untranslated
 * string a compile error rather than a silent fallback to English.
 */

export const LANGUAGES = ["en", "es"] as const;
export type Lang = (typeof LANGUAGES)[number];

export const DEFAULT_LANG: Lang = "en";

export function isLang(value: string): value is Lang {
  return (LANGUAGES as readonly string[]).includes(value);
}

const en = {
  siteName: "Camino",
  tagline: "California training programs, and what happened to the people who took them",
  notAffiliated:
    "Not a California state website. An independent project built from public data.",
  skipToContent: "Skip to main content",

  searchLabel: "Search programs, providers, or jobs",
  searchPlaceholder: "medical assistant, welding, Fresno…",
  filters: "Filters",
  clearFilters: "Clear filters",
  resultsCount: (n: number, total: number) => `${fmt(n)} of ${fmt(total)} programs`,
  noResults: "No programs match these filters.",
  noResultsHint: "Try removing a filter or searching for a broader term.",

  filterOutcomes: "Only programs with reported outcomes",
  filterOutlook: "Job outlook",
  outlookAny: "Any outlook",
  outlookGrowing: "Only growing jobs",
  outlookShrinking: "Only shrinking jobs",
  statShrinking: (n: number) => `${fmt(n)} train for jobs California expects to shrink`,
  statReported: (n: number, total: number) =>
    `${fmt(n)} of ${fmt(total)} report what happened to their students`,
  showThese: "Show these",
  filterCity: "City",
  filterAnyCity: "Anywhere in California",
  filterMaxCost: "Maximum out-of-pocket cost",
  filterAnyCost: "Any cost",
  sortBy: "Sort by",
  sortRelevance: "Best match",
  sortEarnings: "Highest reported earnings",
  sortCost: "Lowest cost",
  sortOpenings: "Most job openings",

  cost: "Cost",
  costAtLeast: (v: string) => `At least ${v}`,
  costPartial:
    "One cost component was not reported, so the real total is higher than this.",
  leadsToSeveral: "Trains for more than one job. The outlook shown is the weakest of them.",
  length: "Length",
  weeks: (n: number) => `${fmt(n)} weeks`,
  provider: "Provider",
  providerPrograms: "Programs offered",
  providerReporting: "Report outcomes",
  providerShrinking: "Train for shrinking jobs",
  providerProgramList: "All programs here",
  allPrograms: "See all programs from this provider",
  leadsTo: "Leads to",
  notReported: "Not reported",
  notReportedLong: "The provider did not report this, or it was withheld to protect the privacy of a small group.",

  outcomes: "What happened to people who took this",
  completionRate: "Finished the program",
  employmentRate: "Working 6 months later",
  medianEarnings: "Earnings in one quarter after",
  medianEarningsNote:
    "A single quarter of earnings, roughly three months, not a yearly salary. Do not compare it directly with the yearly pay shown for the occupation.",
  peopleServed: "People enrolled",
  peopleExited: "People who left or finished",
  outcomesUnreported: "No outcomes reported for this program",
  outcomesUnreportedBody:
    "About a third of California programs report nothing. That is a fact about the program's reporting, not evidence that it works or does not.",
  basedOn: (n: number) => `Based on ${fmt(n)} people`,
  smallSample: "Small group — treat with caution",

  occupation: "The job this trains for",
  medianWage: "Typical pay in California",
  jobOpenings: "Projected openings",
  growth: "Projected change",
  growing: "Growing",
  shrinking: "Shrinking",
  shrinkingWarning:
    "California projects this job will shrink over the next ten years. Fewer openings may mean a harder search.",
  entryEducation: "Usually needs",
  perYear: "per year",
  relatedWork: "Related work",
  relatedWorkNote:
    "Occupations in the same family as this one, ordered by projected openings. Related by how the job classification groups them, not by a claim that the skills transfer.",
  byRegion: "Pay by region",
  region: "Region",

  compareTitle: "Side by side",
  compareMeasure: "Measure",
  compareAdd: "Compare",
  compareCount: (n: number, max: number) => `${n} of ${max} selected to compare`,
  compareOpen: "Compare these",
  compareHide: "Hide comparison",
  compareClear: "Clear all",
  compareRemove: (name: string) => `Remove ${name} from comparison`,
  compareFull: "Comparison is full. Remove one to add another.",
  compareNote:
    "A highlighted cell is the strongest reported figure in that row. Rows where fewer than two programs reported anything are not marked, because being the only one to file a number is not the same as being the best.",

  vsState: "Typical California program",
  vsStateAbove: "Better than typical",
  vsStateBelow: "Worse than typical",
  ofReporting: (n: number) => `of ${fmt(n)} reporting`,
  benchmarkNote:
    "Compared with the median California program that reported this same measure. Programs reporting nothing are not in the comparison, so this is a comparison among those willing to publish.",

  aboutData: "Where this comes from",
  snapshot: (d: string) => `Data snapshot: ${d}`,
  viewProgram: "Program details",
  providerSite: "Provider's website",
  backToSearch: "Back to search",
  coverageNote: (pct: number) =>
    `${pct}% of California programs report at least one outcome. The rest are listed with what is known.`,

  // ---- Browse indexes ----
  browseOccupationsTitle: "Every occupation California projects",
  browseOccupationsIntro:
    "California publishes a ten-year projection for every occupation it tracks. All of them are here, grouped by whether the state expects the work to grow or shrink and ordered by the openings it projects.",
  occupationsListed: "Occupations listed",
  titlesEnglishOnly:
    "Occupation titles appear in English because that is the only language the state publishes them in.",
  occupationColumn: "Occupation",
  programsHere: "Programs listed here",
  onThisPage: "On this page",
  jumpToOutlook: "Jump to a section of this list",
  sortedByOpenings:
    "Ordered by projected openings, most first. An occupation with no published figure goes last rather than being counted as none.",
  bandShrinking: "Work California expects less of",
  bandShrinkingNote:
    "The state projects fewer of these jobs over the next ten years. Training for one is not a mistake, but it is a decision worth making with the number in front of you.",
  bandSteady: "Work with no projected change",
  bandSteadyNote:
    "The state projects the same number of these jobs in ten years as there are today.",
  bandGrowing: "Work California expects more of",
  bandGrowingNote:
    "The state projects growth here. That says nothing about the pay, and nothing about whether any particular program prepares you for the work.",
  bandUnknown: "Work with no projection published",
  bandUnknownNote:
    "The state published no projected change for these. That is missing information, not a projection of zero.",

  browseProvidersTitle: "Every training provider",
  browseProvidersIntro:
    "Every school, college, and training organisation with at least one California program in this dataset, listed alphabetically with how much of its own record it publishes.",
  browseProvidersDerived:
    "The federal providers index carries no California rows, so this roster is rebuilt from the programs themselves. Spellings that differ only in capitalisation or punctuation are merged into one entry.",
  jumpToLetter: "Jump to providers by first letter",
  otherLetter: "0–9 and other",
  citiesColumn: "Cities",
  moreCities: (n: number) => `+${fmt(n)} more`,
  reportingRatio: (n: number, total: number) => `${fmt(n)} of ${fmt(total)}`,
  providersListed: "Providers listed",
  programsListed: "Programs across them",
  providersReportingSome: "Publish at least one outcome",

  browseAllOccupations: "Browse all occupations",
  browseAllProviders: "Browse all providers",

  // ---- Site chrome ----
  navLabel: "Main navigation",
  navOccupations: "Occupations",
  navProviders: "Providers",

  // Shown at the site root, where a visitor arriving from a search engine has been told
  // nothing yet. Two sentences: what it costs them, and what the numbers are.
  siteSummary:
    "Free to use, with no account. Every figure comes from public federal and state records, and a program that reported nothing is shown as having reported nothing.",
};

/**
 * Every key in `en` must exist in every other dictionary, with a matching signature.
 * Deliberately not `as const`: literal types would require the Spanish text to be
 * character-identical to the English.
 */
type Dictionary = typeof en;

const es: Dictionary = {
  siteName: "Camino",
  tagline: "Programas de capacitación en California y qué pasó con quienes los tomaron",
  notAffiliated:
    "No es un sitio del estado de California. Es un proyecto independiente hecho con datos públicos.",
  skipToContent: "Saltar al contenido principal",

  searchLabel: "Busque programas, instituciones u ocupaciones",
  // Program and occupation names in the source data are English only, so a Spanish
  // example would return nothing. These terms actually match.
  searchPlaceholder: "medical assistant, welding, Fresno…",
  filters: "Filtros",
  clearFilters: "Borrar filtros",
  resultsCount: (n: number, total: number) => `${fmt(n)} de ${fmt(total)} programas`,
  noResults: "Ningún programa coincide con estos filtros.",
  noResultsHint: "Quite un filtro o busque un término más general.",

  filterOutcomes: "Solo programas con resultados reportados",
  filterOutlook: "Perspectiva laboral",
  outlookAny: "Cualquier perspectiva",
  outlookGrowing: "Solo ocupaciones en crecimiento",
  outlookShrinking: "Solo ocupaciones en declive",
  statShrinking: (n: number) =>
    `${fmt(n)} preparan para ocupaciones que California espera que se reduzcan`,
  statReported: (n: number, total: number) =>
    `${fmt(n)} de ${fmt(total)} reportan qué pasó con sus estudiantes`,
  showThese: "Ver estos",
  filterCity: "Ciudad",
  filterAnyCity: "Cualquier lugar de California",
  filterMaxCost: "Costo máximo de su bolsillo",
  filterAnyCost: "Cualquier costo",
  sortBy: "Ordenar por",
  sortRelevance: "Más relevante",
  sortEarnings: "Mayores ingresos reportados",
  sortCost: "Menor costo",
  sortOpenings: "Más vacantes",

  cost: "Costo",
  costAtLeast: (v: string) => `Al menos ${v}`,
  costPartial:
    "No se reportó uno de los componentes del costo, así que el total real es más alto que este.",
  leadsToSeveral:
    "Prepara para más de una ocupación. La perspectiva mostrada es la más débil de ellas.",
  length: "Duración",
  weeks: (n: number) => `${fmt(n)} semanas`,
  provider: "Institución",
  providerPrograms: "Programas ofrecidos",
  providerReporting: "Reportan resultados",
  providerShrinking: "Preparan para ocupaciones en declive",
  providerProgramList: "Todos los programas aquí",
  allPrograms: "Ver todos los programas de esta institución",
  leadsTo: "Lleva a",
  notReported: "No reportado",
  notReportedLong:
    "La institución no reportó este dato, o se omitió para proteger la privacidad de un grupo pequeño.",

  outcomes: "Qué pasó con quienes tomaron este programa",
  completionRate: "Terminaron el programa",
  employmentRate: "Trabajando 6 meses después",
  medianEarnings: "Ingresos en un trimestre después",
  medianEarningsNote:
    "Los ingresos de un solo trimestre, unos tres meses, no un salario anual. No los compare directamente con el pago anual de la ocupación.",
  peopleServed: "Personas inscritas",
  peopleExited: "Personas que salieron o terminaron",
  outcomesUnreported: "Este programa no reportó resultados",
  outcomesUnreportedBody:
    "Cerca de un tercio de los programas de California no reportan nada. Eso dice algo sobre su reporte, no sobre si el programa funciona.",
  basedOn: (n: number) => `Con base en ${fmt(n)} personas`,
  smallSample: "Grupo pequeño — interprete con cuidado",

  occupation: "La ocupación para la que prepara",
  medianWage: "Pago típico en California",
  jobOpenings: "Vacantes proyectadas",
  growth: "Cambio proyectado",
  growing: "En crecimiento",
  shrinking: "En declive",
  shrinkingWarning:
    "California proyecta que esta ocupación se reducirá en los próximos diez años. Menos vacantes puede significar una búsqueda más difícil.",
  entryEducation: "Normalmente requiere",
  perYear: "al año",
  relatedWork: "Trabajos relacionados",
  relatedWorkNote:
    "Ocupaciones de la misma familia que esta, ordenadas por vacantes proyectadas. Se relacionan por cómo las agrupa la clasificación laboral, no porque las habilidades se transfieran.",
  byRegion: "Pago por región",
  region: "Región",

  compareTitle: "Lado a lado",
  compareMeasure: "Medida",
  compareAdd: "Comparar",
  compareCount: (n: number, max: number) => `${n} de ${max} seleccionados para comparar`,
  compareOpen: "Comparar estos",
  compareHide: "Ocultar comparación",
  compareClear: "Borrar todo",
  compareRemove: (name: string) => `Quitar ${name} de la comparación`,
  compareFull: "La comparación está llena. Quite uno para agregar otro.",
  compareNote:
    "La celda resaltada es la cifra reportada más fuerte de esa fila. Las filas donde menos de dos programas reportaron algo no se marcan, porque ser el único que reportó un número no es lo mismo que ser el mejor.",

  vsState: "Programa típico de California",
  vsStateAbove: "Mejor que lo típico",
  vsStateBelow: "Peor que lo típico",
  ofReporting: (n: number) => `de ${fmt(n)} que reportan`,
  benchmarkNote:
    "Comparado con el programa típico de California que reportó esta misma medida. Los programas que no reportan nada no entran en la comparación.",

  aboutData: "De dónde vienen estos datos",
  snapshot: (d: string) => `Datos actualizados: ${d}`,
  viewProgram: "Detalles del programa",
  providerSite: "Sitio de la institución",
  backToSearch: "Volver a la búsqueda",
  coverageNote: (pct: number) =>
    `${pct}% de los programas de California reportan al menos un resultado. Los demás se muestran con lo que se sabe.`,

  // ---- Browse indexes ----
  browseOccupationsTitle: "Todas las ocupaciones que California proyecta",
  browseOccupationsIntro:
    "California publica una proyección a diez años para cada ocupación que sigue. Aquí están todas, agrupadas según si el estado espera que el trabajo crezca o se reduzca y ordenadas por las vacantes que proyecta.",
  occupationsListed: "Ocupaciones en la lista",
  titlesEnglishOnly:
    "Los nombres de las ocupaciones aparecen en inglés porque el estado solo los publica en ese idioma.",
  occupationColumn: "Ocupación",
  programsHere: "Programas en esta lista",
  onThisPage: "En esta página",
  jumpToOutlook: "Ir a una sección de esta lista",
  sortedByOpenings:
    "Ordenado por vacantes proyectadas, de mayor a menor. Una ocupación sin cifra publicada va al final en vez de contarse como ninguna.",
  bandShrinking: "Trabajos de los que California espera menos",
  bandShrinkingNote:
    "El estado proyecta menos de estos empleos en los próximos diez años. Capacitarse para uno no es un error, pero conviene decidirlo con la cifra a la vista.",
  bandSteady: "Trabajos sin cambio proyectado",
  bandSteadyNote:
    "El estado proyecta dentro de diez años la misma cantidad de estos empleos que hay hoy.",
  bandGrowing: "Trabajos de los que California espera más",
  bandGrowingNote:
    "El estado proyecta crecimiento aquí. Eso no dice nada sobre el pago, ni sobre si algún programa en particular lo prepara para ese trabajo.",
  bandUnknown: "Trabajos sin proyección publicada",
  bandUnknownNote:
    "El estado no publicó un cambio proyectado para estos. Es información que falta, no una proyección de cero.",

  browseProvidersTitle: "Todas las instituciones de capacitación",
  browseProvidersIntro:
    "Cada escuela, colegio y organización de capacitación con al menos un programa de California en estos datos, en orden alfabético y con cuánto publica de su propio historial.",
  browseProvidersDerived:
    "El índice federal de instituciones no trae filas de California, así que esta lista se reconstruye a partir de los propios programas. Las grafías que solo difieren en mayúsculas o puntuación se combinan en una sola entrada.",
  jumpToLetter: "Ir a las instituciones por letra inicial",
  otherLetter: "0–9 y otros",
  citiesColumn: "Ciudades",
  moreCities: (n: number) => `+${fmt(n)} más`,
  reportingRatio: (n: number, total: number) => `${fmt(n)} de ${fmt(total)}`,
  providersListed: "Instituciones en la lista",
  programsListed: "Programas en total",
  providersReportingSome: "Publican al menos un resultado",

  browseAllOccupations: "Ver todas las ocupaciones",
  browseAllProviders: "Ver todas las instituciones",

  // ---- Site chrome ----
  navLabel: "Navegación principal",
  navOccupations: "Ocupaciones",
  navProviders: "Instituciones",

  siteSummary:
    "De uso gratuito y sin cuenta. Cada cifra viene de registros públicos federales y estatales, y un programa que no reportó nada aparece justamente así: sin nada reportado.",
};

function fmt(n: number): string {
  return new Intl.NumberFormat("en-US").format(n);
}

const DICTIONARIES: Record<Lang, Dictionary> = { en, es };

export function dict(lang: Lang): Dictionary {
  return DICTIONARIES[lang];
}

export const OTHER_LANG: Record<Lang, Lang> = { en: "es", es: "en" };
export const LANG_NAME: Record<Lang, string> = { en: "English", es: "Español" };
