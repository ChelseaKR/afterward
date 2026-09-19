/**
 * Types for `mt-notice.mjs`, hand-written because `tsconfig.json` sets `allowJs: false` and
 * the gate scripts are `.mjs` (the same arrangement as `a11y-verdict.d.mts`).
 */

export const NOTICE_ATTR: string;
export const ENGLISH_LINK_ID: string;

/** `true` when the page must carry the notice, `false` when it must not. */
export function noticeRequired(relPath: string, html: string): boolean;

/** Every reason the page fails the rule, or an empty list. */
export function noticeProblems(relPath: string, html: string): string[];
