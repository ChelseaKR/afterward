/**
 * Which exported pages must carry the machine-translation notice, and whether one does.
 *
 * Pure functions, in their own module so `mt-notice.test.ts` can hold them without walking a
 * build. `mt-notice-audit.mjs` applies them to every page in the export.
 *
 * The rule (owner decision, 2026-09-18): every page that shows the site's machine-translated
 * Spanish says so, in the page body near the top, in both languages, with a link to the
 * English. So:
 *
 * - every page under `es/` must carry it;
 * - every page under `en/` must not -- the English is not machine-translated, and a notice
 *   saying it was would be a false statement on every English page;
 * - every other page (the root chooser, the 404 page) belongs to no language, and must carry
 *   it exactly when it shows Spanish, which it marks with `lang="es"`.
 *
 * "Carries it" is checked on the markup, not on the source that should have produced it:
 * exactly one notice element, a Spanish and an English paragraph inside it, a link to an
 * English URL, and all of it before `<main` so it is at the top of the page rather than at the
 * bottom. The flight payload Next inlines repeats the component's props as JSON, which is why
 * the attribute is matched in its HTML form (`attr=""`) and never counted from the payload.
 */

export const NOTICE_ATTR = "data-machine-translation-notice";
export const ENGLISH_LINK_ID = "mt-notice-english";

/** Characters after the notice's opening tag within which its parts must appear. */
const NOTICE_SPAN = 4000;

/**
 * Whether the page at `relPath` (relative to the export root, `/`-separated) must carry the
 * notice: `true` required, `false` forbidden.
 */
export function noticeRequired(relPath, html) {
  if (relPath.startsWith("es/")) return true;
  if (relPath.startsWith("en/")) return false;
  return /\blang="es"/.test(html);
}

/** Every reason the page fails the rule, or an empty list. */
export function noticeProblems(relPath, html) {
  const marker = `${NOTICE_ATTR}=""`;
  const count = html.split(marker).length - 1;
  const required = noticeRequired(relPath, html);

  if (!required) {
    return count === 0 ? [] : [`${relPath}: carries the machine-translation notice but shows no machine-translated text`];
  }
  if (count === 0) return [`${relPath}: shows Spanish without the machine-translation notice`];
  if (count > 1) return [`${relPath}: carries the machine-translation notice ${count} times`];

  const problems = [];
  const at = html.indexOf(marker);
  const main = html.indexOf("<main");
  if (main !== -1 && at > main) {
    problems.push(`${relPath}: the machine-translation notice is not above the page's main content`);
  }
  const notice = html.slice(at, at + NOTICE_SPAN);
  if (!/<p lang="es">(?:(?!<\/p>)[\s\S])*\S(?:(?!<\/p>)[\s\S])*<\/p>/.test(notice)) {
    problems.push(`${relPath}: the machine-translation notice has no Spanish text`);
  }
  if (!/<p lang="en">(?:(?!<\/p>)[\s\S])*\S(?:(?!<\/p>)[\s\S])*<\/p>/.test(notice)) {
    problems.push(`${relPath}: the machine-translation notice has no English text`);
  }
  const link = notice.match(new RegExp(`<a\\b[^>]*\\bid="${ENGLISH_LINK_ID}"[^>]*>`));
  if (!link || !/\bhref="\/en\//.test(link[0])) {
    problems.push(`${relPath}: the machine-translation notice does not link to the English version`);
  }
  return problems;
}
