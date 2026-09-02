import type { Lang } from "./i18n";

/**
 * Where this site lives, and what it hands a link unfurler.
 *
 * `SITE_URL` was declared separately in `app/robots.ts`, `app/sitemap.ts` and
 * `app/[lang]/layout.tsx` — the same expression written three times, and in the layout it
 * had fallen out of use entirely while still defaulting to `""` rather than to the
 * placeholder the other two use. One copy, one fallback, one place to read the reasoning.
 *
 * Set NEXT_PUBLIC_SITE_URL at build time. The placeholder is obviously a placeholder rather
 * than a plausible-looking domain, so a build made without it cannot quietly ship absolute
 * URLs — sitemap entries, share-card images — pointing at somewhere real that this project
 * does not control. `.github/workflows/deploy.yml` greps the whole export for it and refuses
 * to publish if it appears, and `scripts/ci_artifact_check.py` asserts the mirror image: a
 * CI build must still carry it.
 */
export const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL?.replace(/\/$/, "") ?? "https://example.invalid";

/**
 * How the site describes itself where no language has been chosen yet: the root layout's
 * defaults and the language chooser's own card.
 *
 * Here rather than in either file because both need them and both had their own copy of the
 * title, which is how a pair of strings that must agree comes to disagree. Everything under
 * `/[lang]/` overrides these from the dictionary instead.
 */
export const ROOT_TITLE = "Afterward — California training programs and their outcomes";
export const ROOT_DESCRIPTION =
  "Search California training programs and see what they cost, what happened to the people " +
  "who took them, and what the jobs they lead to actually pay. Built from public data.";

/**
 * The image a shared link shows, per language.
 *
 * Three cards rather than one. The two language cards carry that language's tagline and,
 * along the top, that language's non-affiliation notice — the same reasoning
 * `app/[lang]/layout.tsx` gives for writing the description per language, applied to the
 * picture: a notice is only useful in a language its reader speaks, and a card is the one
 * surface where the wrong language cannot be skimmed past. The third is bilingual and
 * belongs to the site root, which is the one URL that belongs to no language and whose page
 * is itself written in both.
 *
 * 1200x630 is the size Slack, LinkedIn, X, Mastodon, iMessage and Facebook all crop from
 * cleanly, and it is what `og:image:width`/`height` below promise. Those two are not
 * decoration: an unfurler that knows the aspect ratio before the bytes arrive reserves the
 * right box and does not reflow the card, and Slack in particular will fall back to a small
 * thumbnail without them.
 *
 * The files are flat PNGs of type at ~50 KB each, well inside the ~1 MB above which Slack
 * and iMessage silently drop an image and show no card at all.
 */
const CARD = { width: 1200, height: 630, type: "image/png" } as const;

/** The bilingual card, for the language-chooser at the root. */
export function rootCard(alt: string) {
  return { url: `${SITE_URL}/og/afterward.png`, alt, ...CARD };
}

/** The card for one language's pages. */
export function langCard(lang: Lang, alt: string) {
  return { url: `${SITE_URL}/og/afterward-${lang}.png`, alt, ...CARD };
}
