/**
 * Translations for the controlled vocabularies in the source data.
 *
 * The site chrome was translated from the start, but the *data* arrives in English only:
 * education levels, experience requirements, and training types all come from federal and
 * state feeds. A Spanish page that reads "Normalmente requiere: Associate's degree" is not
 * a translated page, so these closed lists are translated too.
 *
 * Occupation titles are no longer part of that limitation. Mi Próximo Paso publishes 600 of
 * California's 670 occupations in Spanish, and since commits 71c3434 and a8514e3 the Spanish
 * pages use the Department's own Spanish name and description everywhere they appear; the
 * other 70 keep the English name. What remains English is the program description, which is
 * the provider's own text and has no Spanish edition to use.
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

/**
 * How a program is delivered, from the federal ETP file's `field_program_format`.
 *
 * A closed list like the three above, but published as whole sentences rather than as terms,
 * which is why it went unnoticed: it does not look like a vocabulary. It is one. All 3,266
 * California programs carry exactly one of these three strings and nothing else, so every
 * Spanish program page was showing one English sentence in the middle of its own content —
 * 840 hybrid, 1,882 in-person, 544 online.
 *
 * Translated as sentences, not word for word: "e-learning" and "distance learning" are one
 * idea in Spanish, and the federal phrasing lists them as two.
 */
const FORMAT: Record<string, string> = {
  "This program provides in-person instruction only.":
    "Este programa se imparte únicamente de manera presencial.",
  "This is a hybrid or blended program providing both in-person and online instruction.":
    "Este es un programa híbrido o combinado: se imparte tanto de manera presencial como en línea.",
  "This program provides online instruction, e-learning, or distance learning only.":
    "Este programa se imparte únicamente en línea, por aprendizaje electrónico o a distancia.",
};

/** The feeds use the literal string "None" for "no requirement". */
const NONE: Record<Lang, string> = { en: "None", es: "Ninguno" };

const TABLES = [EDUCATION, EXPERIENCE, TRAINING, FORMAT];

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
