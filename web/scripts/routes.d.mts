/**
 * Types for `routes.mjs`, hand-written because `tsconfig.json` sets `allowJs: false` and the
 * gate scripts are `.mjs`. Same reasoning as `a11y-verdict.d.mts` beside it: without this a
 * `.ts` file cannot import them and `tsc --noEmit` refuses it, which is the "the check does
 * not run" shape these scripts exist to prevent.
 *
 * Only what a TypeScript caller uses is declared. `routes.mjs` is the authority on behavior.
 */

/** Absolute path of the app router tree these functions read by default. */
export const APP_DIR: string;

/** Absolute path of `lib/i18n.ts`, which `languages()` parses `LANGUAGES` out of. */
export const I18N_FILE: string;

/** The locales `generateStaticParams` builds, read out of `lib/i18n.ts`. Throws if absent. */
export function languages(i18nFile?: string): string[];

/** Every route template the app router will emit a page for, dynamic segments bracketed. */
export function routeTemplates(appDir?: string): string[];

/** A route template as a matcher over an exported file's path, relative to the export root. */
export function exportedPagePattern(template: string, lang: string | null): RegExp;

/** True when `template` has a `[lang]` segment and so is built once per language. */
export function isPerLanguage(template: string): boolean;

/** Which route templates no path in `paths` covers, and in which language. */
export function uncovered(
  paths: readonly string[],
  options?: { appDir?: string; i18nFile?: string; langs?: readonly string[] },
): string[];
