import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/site";

// Required for `output: "export"`: these are files on disk, not routes.
export const dynamic = "force-static";

/**
 * Everything here is public data and every page is meant to be found. Nothing is disallowed,
 * because there is nothing to hide and no user-specific page to protect.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/" }],
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
