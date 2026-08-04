import type { MetadataRoute } from "next";

// Required for `output: "export"`: these are files on disk, not routes.
export const dynamic = "force-static";

import { allOccupationCodes, allProgramIds, getCoverage, getSearchIndex } from "@/lib/data";
import { LANGUAGES } from "@/lib/i18n";
import { groupByProvider } from "@/lib/providers";

/**
 * Base URL for absolute sitemap entries.
 *
 * Set NEXT_PUBLIC_SITE_URL at build time. The placeholder is obviously a placeholder rather
 * than a plausible-looking domain, so a sitemap built without it cannot quietly ship URLs
 * pointing at somewhere real that this project does not control.
 */
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL?.replace(/\/$/, "") ?? "https://example.invalid";

/**
 * Every page, in both languages, cross-linked with hreflang alternates.
 *
 * Search is how someone finds out that the program they were about to enrol in reports
 * nothing, or trains for work the state expects less of. Being findable is part of the
 * point, not an afterthought.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date(getCoverage().snapshot_date);
  const providers = groupByProvider(getSearchIndex().programs);

  const paths = [
    ...LANGUAGES.map((lang) => ({ path: `/${lang}/`, priority: 1 })),
    ...LANGUAGES.flatMap((lang) =>
      allOccupationCodes().map((soc) => ({
        path: `/${lang}/occupations/${soc}/`,
        priority: 0.7,
      })),
    ),
    ...LANGUAGES.flatMap((lang) =>
      providers.map((provider) => ({
        path: `/${lang}/providers/${provider.slug}/`,
        priority: 0.6,
      })),
    ),
    ...LANGUAGES.flatMap((lang) =>
      allProgramIds().map((id) => ({ path: `/${lang}/programs/${id}/`, priority: 0.5 })),
    ),
  ];

  return paths.map(({ path, priority }) => ({
    url: `${SITE_URL}${path}`,
    lastModified,
    changeFrequency: "yearly" as const,
    priority,
    alternates: {
      languages: Object.fromEntries(
        LANGUAGES.map((other) => [
          other,
          `${SITE_URL}${path.replace(/^\/(en|es)\//, `/${other}/`)}`,
        ]),
      ),
    },
  }));
}
