import type { Lang } from "@/lib/i18n";

/**
 * Which of this site's languages are machine-translated, and the notice every page showing
 * one of them carries.
 *
 * Owner decision, 2026-09-18: the Spanish ships, labeled as machine-translated. It was drafted
 * by machine alongside the English and no native speaker has reviewed it as a whole (#32 stays
 * open for that). The one exception is the funding section, which a native speaker reviewed on
 * 2026-08-06 and which says so where it appears -- hence "except where noted".
 *
 * The notice is in both languages on purpose: the reader it protects may be reading the
 * Spanish because English is harder for them, and the reader who can check it against the
 * English needs to be told in English that there is something to check.
 *
 * One definition, used by the `[lang]` layout, the root chooser and the 404 page.
 * `scripts/mt-notice-audit.mjs` reads the built export and fails the build on any page that
 * shows Spanish without it.
 */
export const MACHINE_TRANSLATED: ReadonlySet<Lang> = new Set<Lang>(["es"]);

/** Whether pages in `lang` carry the machine-translation notice. */
export function isMachineTranslated(lang: Lang): boolean {
  return MACHINE_TRANSLATED.has(lang);
}

/**
 * The notice itself. Each half is rendered under its own `lang`, so a screen reader switches
 * voice rather than reading one language with the other's phonemes.
 */
export const MACHINE_TRANSLATION_NOTICE = {
  es: {
    lead: "Traducción automática, sin revisión humana.",
    body:
      "El español de este sitio lo redactó una máquina y ninguna persona lo ha revisado, " +
      "salvo donde se indique. La versión en inglés es la de referencia.",
    link: "Consulte la versión en inglés",
  },
  en: {
    lead: "Machine-translated, not reviewed by a person.",
    body:
      "The Spanish on this site was drafted by machine and has not been reviewed by a person, " +
      "except where noted. The English version is the reference.",
    link: "See the English version",
  },
} as const;

/**
 * The attribute the build audit looks for. A constant rather than a class name, so a restyle
 * cannot quietly remove the thing the gate is counting.
 */
export const MACHINE_TRANSLATION_NOTICE_ATTR = "data-machine-translation-notice";

/**
 * The `id` of the notice's link to the English page. The `[lang]` layout's masthead script
 * points it at this page's English twin, the same way it points the language toggle; without
 * JavaScript it stays at the English home page, which is still the English version.
 */
export const MACHINE_TRANSLATION_ENGLISH_LINK_ID = "mt-notice-english";
