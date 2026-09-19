"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { initGoogleAnalytics, trackGooglePageView } from "@/lib/analytics";

/**
 * Google Analytics 4: starts it (if `lib/analytics.ts` allows) and sends one page view per
 * path change, including the first.
 *
 * Mounted in the language layout, which Next keeps across client-side navigations, so
 * `usePathname` is what changes when a reader follows a link. Keyed on the path only: the
 * search page rewrites its query string as someone types, and a refined search is not a new
 * page. Renders nothing, and does nothing at all in a build without a measurement ID.
 */
export function GoogleAnalytics(): null {
  const pathname = usePathname();
  useEffect(() => {
    if (!initGoogleAnalytics()) return;
    trackGooglePageView(pathname, window.location.search);
  }, [pathname]);
  return null;
}
