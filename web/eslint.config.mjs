/**
 * ESLint over the gate scripts.
 *
 * `package.json` mapped `lint` to `next lint` until 2026-08-28. Next 16 removed that
 * subcommand, so the script parsed `lint` as a directory and exited 1 with
 * `Invalid project directory provided, no such directory: web/lint`. Nothing noticed,
 * because `npm run verify` never called it: no ESLint had ever run over this front end,
 * while `eslint` and `eslint-config-next` sat in devDependencies being kept current by
 * Dependabot for a command that could not run.
 *
 * What is linted, and what is not, stated rather than implied:
 *
 * `scripts/*.mjs` are linted here. They are the accessibility, contrast and page-weight
 * gates, and they are the one surface in this repository nothing else reads: `tsconfig.json`
 * sets `allowJs: false`, so `tsc --noEmit` does not see them, and until now neither did any
 * linter. A gate script is exactly the code that must not be wrong.
 *
 * `**\/*.ts` and `**\/*.tsx` are **not** linted, and that is a limitation rather than a
 * judgement. `eslint-config-next@16.3.1` loads `typescript-eslint@8.66.0`, which refuses to
 * start against this repository's TypeScript 7.0 -- "typescript-eslint does not support
 * TS 7.0", tracked at typescript-eslint#10940. There is no TypeScript parser here that runs,
 * so there are no rules to apply to those files. Downgrading TypeScript to buy a lint pass
 * would trade a working type checker for one. `tsc --noEmit` under `strict` and
 * `noUncheckedIndexedAccess` continues to cover them for types, and `eslint-config-next` is
 * kept installed because it is the path back the day the parser supports TS 7.
 *
 * The rules are enumerated rather than pulled from a preset, so each one is a decision. They
 * are the subset of ESLint's own recommended set that catches a mistake rather than a style,
 * which is the only kind of finding worth failing a build over.
 */

/** The Node globals these scripts actually use. Listed rather than imported from `globals`,
 *  which is only present here as a transitive dependency of a config that cannot run. */
const NODE_GLOBALS = {
  console: "readonly",
  process: "readonly",
  URL: "readonly",
  Buffer: "readonly",
  TextEncoder: "readonly",
  TextDecoder: "readonly",
  setTimeout: "readonly",
  clearTimeout: "readonly",
  fetch: "readonly",
  performance: "readonly",
  // Present only inside `page.evaluate` callbacks, which are serialised and run in Chromium.
  // Declaring them file-wide is the cost of those two scripts holding Node code and browser
  // code in one module; the alternative is `no-undef` off, which is worse.
  window: "readonly",
  document: "readonly",
};

export default [
  {
    // Everything this config has nothing to say about. The TypeScript sources are excluded
    // for the reason in the header: there is no parser here that can read them.
    ignores: [
      "out/**",
      ".next/**",
      "node_modules/**",
      "public/**",
      "**/*.ts",
      "**/*.tsx",
      "**/*.d.mts",
    ],
  },
  {
    files: ["**/*.mjs"],
    languageOptions: {
      ecmaVersion: 2024,
      sourceType: "module",
      globals: NODE_GLOBALS,
    },
    linterOptions: {
      // An `eslint-disable` for a rule that is not firing is a comment claiming a problem
      // that is not there, and the next reader has to work out which.
      reportUnusedDisableDirectives: "error",
    },
    rules: {
      // A name that does not exist. In a file nothing type-checks, this is the whole game:
      // a typo in a gate script is a crash at the moment the gate is meant to speak.
      "no-undef": "error",
      // A variable or argument nobody reads. `contrast-audit.mjs` carried a `scheme`
      // parameter that had been dead since the aliases were passed in separately, which is
      // the shape of a refactor that half-landed.
      "no-unused-vars": ["error", { args: "all", argsIgnorePattern: "^_", caughtErrors: "none" }],
      // Code after a return, a comparison that is always true, a condition that cannot be
      // reached: in a gate, each of these is a check that does not run.
      "no-unreachable": "error",
      "no-constant-condition": "error",
      "no-constant-binary-expression": "error",
      "no-self-compare": "error",
      "no-unsafe-negation": "error",
      // A duplicate key or a duplicate case silently discards the earlier one, which in a
      // table of pairings or thresholds is a check quietly deleted.
      "no-dupe-keys": "error",
      "no-dupe-args": "error",
      "no-duplicate-case": "error",
      "no-dupe-else-if": "error",
      // A promise nobody awaited inside a loop or a condition is a check that reports before
      // it has an answer, which is the exact failure this repository keeps auditing for.
      "require-atomic-updates": "error",
      "no-async-promise-executor": "error",
      // An empty catch swallows the reason a gate could not run and lets it pass.
      "no-empty": ["error", { allowEmptyCatch: false }],
      "no-fallthrough": "error",
      "no-sparse-arrays": "error",
      "use-isnan": "error",
      "valid-typeof": "error",
    },
  },
];
