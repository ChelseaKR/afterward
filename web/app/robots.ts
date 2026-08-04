import type { MetadataRoute } from "next";

// Required for `output: "export"`: these are files on disk, not routes.
export const dynamic = "force-static";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL?.replace(/\/$/, "") ?? "https://example.invalid";

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
