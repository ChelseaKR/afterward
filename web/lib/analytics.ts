/**
 * Google Analytics 4: the one third-party script this site loads.
 *
 * Decision, 2026-09-17: the owner put GA4 on every public site, with privacy copy and every
 * "no tracking" claim updated to match. This reverses the "no account, no tracking" line the
 * README, the roadmap and the repository description used to carry; all three now say what
 * runs. The About page's privacy section (`aboutPrivacy*` in `lib/i18n.ts`) is the
 * disclosure, in both languages. Keep it and this file in step.
 *
 * Nothing loads unless ALL of these hold, checked once when the page starts:
 *
 *  - a measurement ID was built in (`NEXT_PUBLIC_GA_MEASUREMENT_ID`, a `G-…` value). Only
 *    the production build in `.github/workflows/deploy.yml` sets it. `next dev`, CI, the
 *    accessibility and SEO gates, and every local build leave it unset, and an unset or
 *    malformed value loads nothing;
 *  - the page is served from the production host, `afterward.chelseakr.com`. The same build
 *    previewed on localhost loads nothing;
 *  - the browser sends neither Global Privacy Control nor Do Not Track;
 *  - the reader has not used the footer's "Opt out of analytics" control.
 *
 * What it sends, and what it is told:
 *
 *  - Consent Mode v2 defaults: `ad_storage`, `ad_user_data` and `ad_personalization` denied
 *    everywhere; `analytics_storage` denied in the EEA, the UK and Switzerland (no `_ga`
 *    cookies there, though gtag.js still sends cookieless pings) and granted elsewhere.
 *    Nothing ever updates them.
 *  - `allow_google_signals: false`, `allow_ad_personalization_signals: false` and
 *    `ads_data_redaction`.
 *  - Page views are sent HERE, one per path change (`trackGooglePageView`, driven by
 *    `components/GoogleAnalytics.tsx`), with `send_page_view: false` so the config call does
 *    not send its own. The address GA receives is the origin, the path (any segment that is
 *    not a plain slug becomes `:redacted`) and only the `utm_*` campaign tags. Everything
 *    else in the query string is dropped: that is where a search someone typed (`q`) and a
 *    shortlist someone shared live, and neither is Google's business. Another site's
 *    referrer is reduced to its origin.
 *  - No user id and no event other than `page_view`.
 *
 * This is a single-page app once loaded (Next's client-side navigation), and the search page
 * rewrites its own address with `replaceState` as someone types. GA's enhanced measurement
 * can count "page changes based on browser history events" by itself, from the raw URL,
 * query and all, so that stream setting must be off in the GA admin.
 *
 * Opting out mid-visit: `window['ga-disable-<id>']`, Google's documented kill switch, is a
 * getter over `analyticsOptedOut()`, so the next hit after the switch is flipped is not sent,
 * and the GA cookies already set are removed.
 */

const MEASUREMENT_ID_PATTERN = /^G-[A-Z0-9]{4,20}$/;
const GTAG_SRC = "https://www.googletagmanager.com/gtag/js";

/** GA loads only when the page is served from this host. */
export const PRODUCTION_HOSTNAME = "afterward.chelseakr.com";

/**
 * Where the footer opt-out is remembered, in localStorage. Namespaced with the host so it
 * cannot collide with another app's flag.
 */
export const ANALYTICS_OPT_OUT_KEY = "afterward.chelseakr.com:analytics-opt-out";

/**
 * Where Consent Mode denies `analytics_storage` by default: the EEA (the 27 EU member states
 * plus Iceland, Liechtenstein and Norway), the United Kingdom and Switzerland, as ISO 3166-1
 * alpha-2 codes. The EU territories that carry their own ISO codes are listed too, so a
 * visitor there is not treated as outside the EU. gtag.js resolves the region itself.
 */
export const CONSENT_DENIED_REGIONS: readonly string[] = [
  // EU member states
  "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE",
  "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE",
  // EU territories with their own ISO codes
  "AX", "GF", "GP", "MQ", "MF", "RE", "YT",
  // Rest of the EEA, the UK and Switzerland
  "IS", "LI", "NO", "GB", "CH",
];

/** Campaign tags are the only query parameters worth GA's acquisition reports. */
const KEPT_QUERY_PARAMS = [
  "utm_source",
  "utm_medium",
  "utm_campaign",
  "utm_term",
  "utm_content",
  "utm_id",
] as const;

/** Every route this site exports is made of segments like these. */
const SLUG_SEGMENT = /^[a-z0-9]+(?:[-_.][a-z0-9]+)*$/i;
const MAX_SEGMENT_LENGTH = 100;

type Gtag = (...args: unknown[]) => void;

declare global {
  interface Window {
    dataLayer?: unknown[];
  }
}

let gtag: Gtag | null = null;
/** The last page view sent: the dedupe key, and the next view's referrer. */
let lastPageLocation: string | null = null;
/** The scrubbed `document.referrer`, used as the first view's referrer. */
let entryReferrer = "";

/** The built-in measurement ID, or null when unset or not a GA4 `G-…` ID. */
export function gaMeasurementId(
  raw: unknown = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID,
): string | null {
  if (typeof raw !== "string") return null;
  const id = raw.trim();
  return MEASUREMENT_ID_PATTERN.test(id) ? id : null;
}

/** True when the browser sends Global Privacy Control or Do Not Track. */
export function privacySignalOn(): boolean {
  if (typeof navigator === "undefined") return false;
  const nav = navigator as Navigator & { globalPrivacyControl?: boolean; msDoNotTrack?: string };
  if (nav.globalPrivacyControl === true) return true;
  const win = typeof window === "undefined" ? undefined : (window as Window & { doNotTrack?: string });
  const dnt = nav.doNotTrack ?? win?.doNotTrack ?? nav.msDoNotTrack;
  return dnt === "1" || dnt === "yes";
}

/** True when this browser has chosen "Opt out of analytics" in the footer. */
export function analyticsOptOutStored(): boolean {
  try {
    return window.localStorage.getItem(ANALYTICS_OPT_OUT_KEY) === "1";
  } catch {
    return false; // storage blocked: nothing could have been stored either
  }
}

/** Whether Google Analytics must stay silent: a browser signal or the opt-out. */
export function analyticsOptedOut(): boolean {
  return privacySignalOn() || analyticsOptOutStored();
}

/** A pathname in which anything that is not a plain slug is replaced. */
export function gaPagePath(pathname: string): string {
  const path = pathname.split(/[?#]/u, 1)[0] || "/";
  return path
    .split("/")
    .map((segment) =>
      segment === "" || (segment.length <= MAX_SEGMENT_LENGTH && SLUG_SEGMENT.test(segment))
        ? segment
        : ":redacted",
    )
    .join("/");
}

/** Only the campaign tags, in a fixed order, or "" when there are none. */
export function gaQuery(search: string): string {
  const input = new URLSearchParams(search);
  const kept = new URLSearchParams();
  for (const key of KEPT_QUERY_PARAMS) {
    const value = input.get(key);
    if (value) kept.set(key, value.slice(0, 100));
  }
  const query = kept.toString();
  return query ? `?${query}` : "";
}

/** The page address GA receives: scrubbed path, campaign tags, no fragment. */
export function gaPageLocation(origin: string, pathname: string, search: string): string {
  return `${origin}${gaPagePath(pathname)}${gaQuery(search)}`;
}

/** Another site is reduced to its origin; one of this site's pages is scrubbed. */
export function gaReferrer(referrer: string, origin: string): string {
  if (!referrer) return "";
  try {
    const url = new URL(referrer);
    if (url.origin === origin) return gaPageLocation(origin, url.pathname, url.search);
    return `${url.origin}/`;
  } catch {
    return "";
  }
}

/**
 * Remove this site's GA cookies (`_ga`, `_ga_<container>`). GA writes them on the widest
 * domain that accepts cookies, and a cookie can only be removed with the domain it was set
 * on, so every suffix of the current host is tried.
 */
export function clearGoogleAnalyticsCookies(id: string | null = gaMeasurementId()): void {
  if (typeof document === "undefined" || !id) return;
  const own = new Set(["_ga", `_ga_${id.slice(2)}`]);
  const names = document.cookie
    .split(";")
    .map((pair) => (pair.split("=", 1)[0] ?? "").trim())
    .filter((name) => own.has(name));
  if (names.length === 0) return;
  const labels = window.location.hostname.split(".");
  const domains = [""];
  for (let i = 0; i < labels.length - 1; i += 1) domains.push(labels.slice(i).join("."));
  for (const name of names) {
    for (const domain of domains) {
      document.cookie = `${name}=; Max-Age=0; path=/${domain ? `; domain=${domain}` : ""}`;
    }
  }
}

/**
 * Load GA if, and only if, every condition in the header holds. Returns whether it loaded.
 * Idempotent: a second call does nothing.
 */
export function initGoogleAnalytics(): boolean {
  if (gtag) return true;
  if (typeof window === "undefined" || typeof document === "undefined") return false;
  const id = gaMeasurementId();
  if (!id) return false;
  if (window.location.hostname !== PRODUCTION_HOSTNAME) return false;
  if (analyticsOptedOut()) {
    clearGoogleAnalyticsCookies(id);
    return false;
  }

  // Google's documented kill switch, read by gtag.js before every hit. A getter rather than
  // a value, so an opt-out that arrives mid-visit is honored on the very next hit.
  Object.defineProperty(window, `ga-disable-${id}`, {
    configurable: true,
    get: () => analyticsOptedOut(),
  });

  const dataLayer = (window.dataLayer = window.dataLayer ?? []);
  // gtag.js only treats an `arguments` object as a command; an array pushed in its place is
  // silently ignored, so this cannot be a rest-parameter arrow.
  const push: Gtag = function gtagPush() {
    // eslint-disable-next-line prefer-rest-params -- gtag.js requires the arguments object
    dataLayer.push(arguments);
  };

  // The more specific default wins where both match, so the order is only for the reader:
  // denied in the listed regions, analytics granted elsewhere.
  push("consent", "default", {
    ad_storage: "denied",
    ad_user_data: "denied",
    ad_personalization: "denied",
    analytics_storage: "denied",
    region: CONSENT_DENIED_REGIONS,
  });
  push("consent", "default", {
    ad_storage: "denied",
    ad_user_data: "denied",
    ad_personalization: "denied",
    analytics_storage: "granted",
  });
  push("set", "ads_data_redaction", true);
  push("js", new Date());
  push("config", id, {
    send_page_view: false,
    allow_google_signals: false,
    allow_ad_personalization_signals: false,
  });

  const script = document.createElement("script");
  script.async = true;
  script.src = `${GTAG_SRC}?id=${encodeURIComponent(id)}`;
  document.head.appendChild(script);

  gtag = push;
  entryReferrer = gaReferrer(document.referrer, window.location.origin);
  return true;
}

/**
 * Record one page view for the current route. A no-op unless GA loaded, and silent under an
 * opt-out that appeared after it did. Consecutive calls for the same scrubbed address count
 * once (React re-runs effects in development, and a search typed into the address bar is
 * not a new page).
 */
export function trackGooglePageView(pathname: string, search: string): void {
  if (!gtag || analyticsOptedOut()) return;
  const pageLocation = gaPageLocation(window.location.origin, pathname, search);
  if (pageLocation === lastPageLocation) return;
  const params: Record<string, string> = {
    page_location: pageLocation,
    page_title: document.title.slice(0, 300),
  };
  // Always set, because gtag.js otherwise reads the raw `document.referrer`.
  const referrer = lastPageLocation ?? entryReferrer;
  if (referrer) params.page_referrer = referrer;
  gtag("set", params);
  gtag("event", "page_view");
  lastPageLocation = pageLocation;
}

/**
 * The footer's analytics switch. Opting out stores the flag gtag.js reads (through
 * `ga-disable-<id>`) before every hit, then removes the GA cookies already set. Opting back
 * in clears the flag and, unless GPC or DNT still applies, starts GA if it never loaded this
 * visit and records the page being viewed.
 *
 * Returns false when the choice could not be stored (storage blocked).
 */
export function setAnalyticsOptOut(optOut: boolean): boolean {
  try {
    if (optOut) window.localStorage.setItem(ANALYTICS_OPT_OUT_KEY, "1");
    else window.localStorage.removeItem(ANALYTICS_OPT_OUT_KEY);
  } catch {
    return false;
  }
  if (optOut) {
    clearGoogleAnalyticsCookies();
    return true;
  }
  if (!analyticsOptedOut() && initGoogleAnalytics()) {
    trackGooglePageView(window.location.pathname, window.location.search);
  }
  return true;
}

/** Test-only: forget that GA loaded, so each test starts from a cold page. */
export function resetGoogleAnalyticsForTests(): void {
  gtag = null;
  lastPageLocation = null;
  entryReferrer = "";
}
