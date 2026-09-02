/**
 * Types for `a11y-verdict.mjs`, hand-written because `tsconfig.json` sets `allowJs: false`
 * and the gate scripts are `.mjs`. Without this the `.test.ts` beside it cannot import them
 * and `tsc --noEmit` refuses the file, which is the same "the check does not run" shape the
 * module itself exists to fix.
 */

/** Whether a build made with this environment carries the assistant panel. */
export function askServiceConfigured(raw: string | undefined | null): boolean;

/** The line the rendered accessibility gate ends on, naming only what it read. */
export function verdict(result: { failures: number; audited: readonly string[] }): string;
