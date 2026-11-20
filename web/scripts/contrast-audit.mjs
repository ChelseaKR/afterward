/**
 * Color contrast audit.
 *
 * The accessibility audit runs in jsdom, which has no layout engine and therefore cannot
 * compute contrast. That left the project asserting WCAG conformance without checking the
 * one thing a screen-reader pass does not cover, so this closes it analytically instead:
 * resolve the design system's own tokens for light and dark, then compute the real WCAG 2.1
 * ratio for every foreground/background pair this site actually puts on screen.
 *
 * Analytical rather than rendered, so it cannot catch a pairing produced by some CSS
 * cascade nobody predicted. It does catch the thing that actually goes wrong: choosing a
 * token that is too close to the one behind it.
 *
 * Usage: node scripts/contrast-audit.mjs
 */

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const DS_DIR = dirname(require.resolve("@cagovweb/design-system/package.json"));
const CSS = readFileSync(join(DS_DIR, "dist", "California-Design-System.css"), "utf-8");
/** Must match the theme imported in app/globals.css. */
const THEME = "valley";
const THEME_CSS = readFileSync(
  join(DS_DIR, "dist", `California-Design-System.theme.${THEME}.css`),
  "utf-8",
);

/** WCAG 2.1 minimums. Large text is >=24px, or >=18.66px bold. */
/*
 * WCAG 2.2 level AAA, 1.4.6 Contrast (Enhanced): 7:1 for body text, 4.5:1 for large text.
 *
 * Raised from AA on 2026-08-05. Four pairings failed at the higher bar and are fixed rather
 * than excepted: the not-reported gray went from --gray-80 (6.63:1) to --gray-90 (9.51:1),
 * and every control tinted with --link moved to --primary-100. Several of those were sitting
 * at 7.02:1 — clearing AAA by two hundredths — which is the same margin this project already
 * refused once on the browse filter's count line.
 *
 * The names are kept as AA_* so the pairings below read unchanged; the values are AAA.
 */
const AA_NORMAL = 7.0;
const AA_LARGE = 4.5;

/** Literal hex values: `--gray-static-10: #fefefe`. These never vary by theme. */
function staticTokens() {
  const tokens = new Map();
  for (const source of [CSS, THEME_CSS]) {
    for (const [, name, hex] of source.matchAll(/--([a-z0-9-]+):\s*(#[0-9a-f]{3,8})\b/gi)) {
      if (!tokens.has(name.toLowerCase())) tokens.set(name.toLowerCase(), hex.toLowerCase());
    }
  }
  return tokens;
}

/**
 * Semantic tokens (`--gray-90`) alias a static one, and each is declared exactly twice: the
 * light mapping first, the dark override second. Reading them in file order is both simpler
 * and more faithful than trying to reimplement the stylesheet's theming, which interleaves
 * several `:root` blocks with several `prefers-color-scheme: dark` blocks and defeated an
 * earlier brace-walking version of this script.
 *
 * Theme files are read too: the base stylesheet leaves `--primary-static-*` undefined, so
 * without a theme every `--primary` token resolves to nothing at all.
 */
function aliasesByScheme() {
  const light = new Map();
  const dark = new Map();
  const seen = new Map();

  for (const source of [CSS, THEME_CSS]) {
    for (const [, name, alias] of source.matchAll(
      /--([a-z0-9-]+):\s*var\(\s*--([a-z0-9-]+)\s*\)/gi,
    )) {
      const key = name.toLowerCase();
      const count = (seen.get(key) ?? 0) + 1;
      seen.set(key, count);
      (count === 1 ? light : dark).set(key, alias.toLowerCase());
    }
  }

  // Anything declared once applies to both schemes.
  return { light, dark: new Map([...light, ...dark]) };
}

/**
 * A token's hex value under one scheme's alias table.
 *
 * Took a `scheme` argument it never read: the scheme is carried entirely by which `aliases`
 * map the caller passes. A half-landed refactor, and the finding that came out of pointing
 * ESLint at these scripts for the first time.
 */
function resolve(token, statics, aliases) {
  let name = token.replace(/^--/, "").toLowerCase();
  // Aliases chain: --primary-100 -> --primary-static-100 -> --valley-static-100 -> #hex.
  for (let hop = 0; hop < 8; hop += 1) {
    if (statics.has(name)) return statics.get(name);
    const next = aliases.get(name);
    if (!next) return null;
    name = next;
  }
  return null;
}

function toRgb(hex) {
  let value = hex.replace("#", "");
  if (value.length === 3) value = [...value].map((c) => c + c).join("");
  return [0, 2, 4].map((i) => parseInt(value.slice(i, i + 2), 16));
}

/** WCAG relative luminance. */
function luminance(hex) {
  const [r, g, b] = toRgb(hex).map((channel) => {
    const c = channel / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a, b) {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (light + 0.05) / (dark + 0.05);
}

/**
 * Every foreground/background pairing this site puts on screen, named as it appears in
 * app/globals.css so a failure points at the rule that has to change.
 */
const PAIRS = [
  ["body text", "--gray-120", "--gray-10", AA_NORMAL],
  ["masthead", "--gray-10", "--primary-100", AA_NORMAL],
  ["non-affiliation notice", "--gray-20", "--gray-120", AA_NORMAL],
  ["machine-translation notice", "--gray-20", "--gray-120", AA_NORMAL],
  ["machine-translation notice link", "--gray-20", "--gray-120", AA_NORMAL],
  ["link on page", "--primary-100", "--gray-10", AA_NORMAL],
  ["link on card", "--primary-100", "--gray-10", AA_NORMAL],
  ["card provider line", "--gray-90", "--gray-10", AA_NORMAL],
  ["fact label", "--gray-90", "--gray-10", AA_NORMAL],
  ["not-reported text", "--gray-90", "--gray-10", AA_NORMAL],
  ["filters panel text", "--gray-120", "--gray-20", AA_NORMAL],
  ["stat strip", "--gray-120", "--gray-20", AA_NORMAL],
  ["compare tray", "--gray-20", "--gray-120", AA_NORMAL],
  ["compare tray link", "--gray-20", "--gray-120", AA_NORMAL],
  ["compare open button", "--gray-120", "--gray-10", AA_NORMAL],
  ["table row header", "--gray-90", "--gray-10", AA_NORMAL],
  ["measure value", "--gray-120", "--gray-10", AA_LARGE],
  ["footer text", "--gray-90", "--gray-10", AA_NORMAL],
  ["panel-quiet body", "--gray-120", "--gray-20", AA_NORMAL],
  // Browse tables highlight the row under the cursor, which moves three kinds of text onto
  // a different background. Easy to forget precisely because it only exists on hover.
  ["hovered row link", "--primary-100", "--gray-20", AA_NORMAL],
  ["hovered row text", "--gray-120", "--gray-20", AA_NORMAL],
  ["hovered row unreported", "--gray-90", "--gray-20", AA_NORMAL],
  /*
   * The save, share and filter controls, added after this list was first written — and the
   * reason this list now exists as something to append to rather than a fixed set.
   *
   * All three shipped briefly with `color: var(--primary-70)`, which is the teal used for
   * rules and accents: 3.63:1 against the page, comfortably failing AA. Two of them also had
   * `background: var(--white)`, a token this theme does not define, so the declaration was
   * dropped and the buttons rendered transparent. This audit passed throughout, because it
   * checks the pairings named here and none of those were among them. A new control needs a
   * new line here, or it is unchecked rather than correct.
   */
  ["save button", "--primary-100", "--gray-10", AA_NORMAL],
  ["save button, saved", "--gray-10", "--primary-100", AA_NORMAL],
  ["copy-link button", "--primary-100", "--gray-10", AA_NORMAL],
  ["saved bar button", "--primary-100", "--gray-20", AA_NORMAL],
  ["saved bar note", "--gray-90", "--gray-20", AA_NORMAL],
  ["browse filter count", "--gray-90", "--gray-10", AA_NORMAL],
  ["related-work facts line", "--gray-90", "--gray-10", AA_NORMAL],
  ["English title under a Spanish one", "--gray-90", "--gray-10", AA_NORMAL],
  ["wage percentile label", "--gray-90", "--gray-10", AA_NORMAL],
  ["wage percentile value", "--gray-120", "--gray-10", AA_NORMAL],
  ["local range column header", "--gray-90", "--gray-10", AA_NORMAL],
  ["local range figure", "--gray-120", "--gray-10", AA_NORMAL],
  ["shared list body", "--gray-90", "--gray-20", AA_NORMAL],
  ["shared list button", "--primary-100", "--gray-20", AA_NORMAL],
];

/*
 * WCAG 1.4.11 Non-text Contrast: 3:1 for what shows a control is there, and where focus is.
 *
 * Added with the WCAG 2.2 A/AA conformance report (docs/accessibility/ACR.md, 2026-11). The
 * list above is all text, so nothing here ever looked at a focus ring or a field border. The
 * ring the site's own controls use was `--primary-60`: 2.87:1 on the page and 2.34:1 on the
 * grey panels where most of those controls sit. The select and search-box border was
 * `--gray-60`, 2.76:1 on the filter panel.
 *
 * The pairs alone would repeat the fault the comment on PAIRS records -- a ring colour added
 * later would be unchecked rather than correct -- so every `outline: ... var(--token)` in
 * app/globals.css must be the foreground of a "focus ring" pair below, and the form-field
 * border token must be the foreground of the "field border" pairs, or this audit fails.
 */
const NON_TEXT = 3.0;
const NON_TEXT_PAIRS = [
  ["focus ring on page", "--primary-80", "--gray-10", NON_TEXT],
  ["focus ring on panel", "--primary-80", "--gray-20", NON_TEXT],
  ["focus ring in masthead", "--gray-10", "--primary-100", NON_TEXT],
  ["focus ring in notice", "--gray-10", "--gray-120", NON_TEXT],
  ["field border on page", "--gray-70", "--gray-10", NON_TEXT],
  ["field border on filter panel", "--gray-70", "--gray-20", NON_TEXT],
];

const SITE_CSS = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "..", "app", "globals.css"),
  "utf-8",
);

/** Ring and field-border tokens globals.css uses that no non-text pair checks. */
function uncheckedNonTextTokens(css) {
  const covered = (prefix) =>
    new Set(NON_TEXT_PAIRS.filter(([label]) => label.startsWith(prefix)).map(([, fg]) => fg));
  const rings = covered("focus ring");
  const borders = covered("field border");
  const missing = [];
  for (const [, token] of css.matchAll(/outline:\s*[\d.]+(?:px|rem)\s+solid\s+var\((--[a-z0-9-]+)\)/g)) {
    if (!rings.has(token)) missing.push(`focus ring ${token}`);
  }
  const field = css.match(/\.field select\s*\{[^}]*border:\s*[\d.]+px\s+solid\s+var\((--[a-z0-9-]+)\)/);
  if (!field) missing.push("field border (rule not found in globals.css)");
  else if (!borders.has(field[1])) missing.push(`field border ${field[1]}`);
  return [...new Set(missing)];
}

const statics = staticTokens();
const aliases = aliasesByScheme();
let failures = 0;
let unresolved = 0;

for (const scheme of ["light", "dark"]) {
  console.log(`\n${scheme}`);

  for (const [label, fgToken, bgToken, minimum] of [...PAIRS, ...NON_TEXT_PAIRS]) {
    const fg = resolve(fgToken, statics, aliases[scheme]);
    const bg = resolve(bgToken, statics, aliases[scheme]);

    // An unresolvable token is a failure, not a skip. A gate that passes because it could
    // not evaluate anything is worse than no gate: it reports confidence it does not have.
    if (!fg || !bg) {
      unresolved += 1;
      console.log(`  UNRESOLVED  ${label} — no value for ${!fg ? fgToken : bgToken}`);
      continue;
    }

    const ratio = contrast(fg, bg);
    const ok = ratio >= minimum;
    if (!ok) failures += 1;
    console.log(
      `  ${ok ? "pass" : "FAIL"}  ${label.padEnd(24)} ${ratio.toFixed(2)}:1 ` +
        `(needs ${minimum}) ${fg} on ${bg}`,
    );
  }
}

const unchecked = uncheckedNonTextTokens(SITE_CSS);
for (const token of unchecked) console.log(`  UNCHECKED  ${token} — add a non-text pair for it`);

if (failures > 0 || unresolved > 0 || unchecked.length > 0) {
  const parts = [];
  if (failures) parts.push(`${failures} pairing(s) below their WCAG 2.2 minimum (1.4.6 / 1.4.11)`);
  if (unresolved) parts.push(`${unresolved} pairing(s) could not be resolved`);
  if (unchecked.length) parts.push(`${unchecked.length} ring or border token(s) no pair checks`);
  console.error(`\ncontrast-audit: ${parts.join("; ")}`);
  process.exit(1);
}
console.log(
  `\ncontrast-audit: all ${PAIRS.length} text pairings meet WCAG 2.2 AAA (1.4.6) and all ` +
    `${NON_TEXT_PAIRS.length} focus-ring and field-border pairings meet 1.4.11, in both light ` +
    `and dark`,
);
