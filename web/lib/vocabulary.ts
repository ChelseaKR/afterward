/**
 * Translations for the controlled vocabularies in the source data.
 *
 * The site chrome was translated from the start, but the *data* arrives in English only:
 * education levels, experience requirements, and training types all come from federal and
 * state feeds. A Spanish page that reads "Normalmente requiere: Associate's degree" is not
 * a translated page, so these closed lists are translated too.
 *
 * Occupation titles and program descriptions are open-ended and remain in English. That is
 * a known limitation, recorded in the design log rather than hidden.
 */

import type { Lang } from "./i18n";

const EDUCATION: Record<string, string> = {
  "No formal educational credential": "Sin credencial educativa formal",
  "High school diploma or equivalent": "Diploma de preparatoria o equivalente",
  "Some college, no degree": "Algo de universidad, sin título",
  "Postsecondary non-degree award": "Certificado postsecundario sin título",
  "Associate's degree": "Título de asociado",
  "Bachelor's degree": "Licenciatura",
  "Master's degree": "Maestría",
  "Doctoral or professional degree": "Doctorado o título profesional",
};

const EXPERIENCE: Record<string, string> = {
  "Less than 5 years": "Menos de 5 años",
  "5 years or more": "5 años o más",
};

const TRAINING: Record<string, string> = {
  "Short-term on-the-job training": "Capacitación breve en el trabajo",
  "Moderate-term on-the-job training": "Capacitación mediana en el trabajo",
  "Long-term on-the-job training": "Capacitación prolongada en el trabajo",
  "Internship/residency": "Prácticas o residencia",
  Apprenticeship: "Aprendizaje",
};

/** The feeds use the literal string "None" for "no requirement". */
const NONE: Record<Lang, string> = { en: "None", es: "Ninguno" };

const TABLES = [EDUCATION, EXPERIENCE, TRAINING];

/**
 * Translate a controlled-vocabulary value.
 *
 * Unknown values fall through to the original English rather than rendering blank: showing
 * the untranslated source beats showing nothing, and a gap here should be visible so it can
 * be fixed rather than silently swallowed.
 */
export function translateTerm(value: string | null, lang: Lang): string | null {
  if (value === null) return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (lang === "en") return trimmed;
  if (trimmed.toLowerCase() === "none") return NONE.es;

  for (const table of TABLES) {
    const hit = table[trimmed];
    if (hit) return hit;
  }
  return trimmed;
}
