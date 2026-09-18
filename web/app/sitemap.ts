import type { MetadataRoute } from "next";

// Required for `output: "export"`: these are files on disk, not routes.
export const dynamic = "force-static";

import { LANGUAGES } from "@/lib/i18n";
import { pathOf, sitePaths } from "@/lib/routes";
import { SITE_URL } from "@/lib/site";

/**
 * Every page, in both languages, cross-linked with hreflang alternates.
 *
 * This is where the site declares its en/es pairing, and the only place it does: 18,092
 * `<xhtml:link rel="alternate" hreflang>` entries over 9,046 URLs. Sitemap-level hreflang is
 * a first-class declaration, and at this scale it is the one that does not put three extra
 * tags in the head of every page. The pages themselves deliberately carry none -- see
 * `pageAlternates` in `lib/site.ts` -- because two declarations of one relationship are two
 * things that can disagree, with nothing to say which a crawler believed.
 *
 * Which makes the reciprocity of what is written here load-bearing, and it went ungated for
 * months. A one-way annotation is discarded by search engines, so a bug that made `/en/x/`
 * name `/es/x/` without being named back would cost the site its entire bilingual-search
 * story while showing no symptom and building green. `lib/alternates.test.ts` now checks
 * every URL in both directions, and `scripts/seo-audit.mjs` repeats it over the built file.
 *
 * ---- No `lastModified` here, deliberately ----
 *
 * It used to be `new Date(getCoverage().snapshot_date)` -- one date, on all 9,046 URLs. That
 * was a real date belonging to a real thing, and the thing it belongs to is the dataset rather
 * than the page, so the claim was wrong in both directions at once. It moved for a program
 * whose row was byte-identical to last month's, because the corpus around it refreshed. And it
 * did not move when a copy change rewrote a sentence on 165 program pages under an unchanged
 * dataset, because this site deploys code and data separately. `lastmod` is the one field in a
 * sitemap that is a factual claim about the content, and nothing this function can see knows
 * when any one page's content last changed.
 *
 * `scripts/lastmod.mjs` does know, because it runs after the export exists and can digest the
 * bytes: a page whose digest matches the ledger published beside the last deploy keeps the date
 * it last changed, one whose digest differs is dated now, and one that nothing has yet watched
 * change carries no date at all. So the dates are added there, from evidence, or not added. That
 * script refuses an export whose sitemap is already dated, which is what keeps this function
 * honest after this comment stops being read.
 *
 * The URL list itself is `lib/routes.ts`, because each page now emits a canonical derived
 * from the same list and the two have to agree. It also used to hold a
 * `replace(/^\/(en|es)\//, ...)` -- a third hand-written copy of `LANGUAGES` that a third
 * locale would not have updated.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  return sitePaths().map(({ lang, rest, priority }) => ({
    url: `${SITE_URL}${pathOf({ lang, rest })}`,
    changeFrequency: "yearly" as const,
    priority,
    alternates: {
      languages: Object.fromEntries(
        LANGUAGES.map((other) => [other, `${SITE_URL}${pathOf({ lang: other, rest })}`]),
      ),
    },
  }));
}
