import type { Metadata } from "next";

import { dict, type Lang } from "./i18n";

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

/**
 * Everything a shared link to one page under `/[lang]/` needs: that page's own title and
 * description, over the site's card image, in the reader's language.
 *
 * A page here is a specific claim -- one program at one provider in one city, one occupation
 * and what California pays for it -- and every one of them was unfurling as the site. The
 * detail routes set a rich `<title>` and a rich `description` and stopped there, on the
 * reasonable-sounding assumption that Open Graph would follow the title it sits beside. It
 * does not: `og:title` and `title` are unrelated fields to Next, so a page that sets only
 * `title` inherits `app/[lang]/layout.tsx`'s `openGraph` untouched. All 6,532 program pages,
 * 1,162 provider pages and 1,340 occupation pages therefore shared one card reading
 * "Afterward — California training programs, and what happened to the people who took them",
 * which is true of the site and says nothing about the page someone actually sent you. For a
 * site whose entire value is its individual records, that is the one place a generic answer
 * costs the most.
 *
 * ---- Why this takes the whole object rather than the two fields that were missing ----
 *
 * Next does not deep-merge `openGraph`. `resolveMetadata` assigns
 * `newResolvedMetadata.openGraph = resolveOpenGraph(metadata.openGraph, ...)` per segment, so
 * a child that declares `openGraph` *replaces* its parent's rather than adding to it. Writing
 * the obvious two lines -- `openGraph: { title, description }` -- on a program page would set
 * the title correctly and silently drop `og:image`, `og:site_name`, `og:locale` and `og:type`,
 * trading a card with the wrong words for no card at all. The fix for a missing field is
 * therefore the complete object, and the complete object is written once, here.
 *
 * `twitter` is set for the same reason and a sharper one. Next fills `twitter:title` and
 * `twitter:description` from `openGraph` only when the resolved `twitter` does not already
 * have them -- and after the layout it always does, so a page setting `openGraph` alone would
 * publish a specific `og:title` next to a `twitter:title` still reading the site's name.
 * `twitter.card` has no fallback at all: omit it and the layout's `summary_large_image`
 * disappears with the rest of the replaced object and the card silently shrinks to a
 * thumbnail. Nothing about that is visible in review; it is visible only in the built `<head>`.
 *
 * `images` is deliberately the language card every other page uses, not a card per program.
 * The picture is a claim about which site this is and it is equally true on all of them --
 * the distinction `app/[lang]/layout.tsx` draws between that and a canonical URL. One PNG per
 * program -- 3,266 of them -- would be a build cost and a bandwidth cost for a picture nobody
 * is choosing between; the words are the part that differs per page, and the words are what
 * this fixes.
 *
 * No `openGraph.url` and no `alternates`, for the reason recorded at length in that layout.
 *
 * Callers pass the same `title` and `description` they were already returning, so the card
 * and the page cannot drift: there is one expression per page, read three times.
 */
export function shareMetadata(lang: Lang, title: string, description: string): Metadata {
  const t = dict(lang);
  const images = [langCard(lang, t.ogImageAlt)];

  return {
    title,
    description,
    openGraph: {
      type: "website",
      siteName: t.siteName,
      locale: lang === "es" ? "es_US" : "en_US",
      title,
      description,
      images,
    },
    twitter: { card: "summary_large_image", title, description, images },
  };
}
