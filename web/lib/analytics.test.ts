// @vitest-environment jsdom

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ANALYTICS_OPT_OUT_KEY,
  CONSENT_DENIED_REGIONS,
  PRODUCTION_HOSTNAME,
  clearGoogleAnalyticsCookies,
  gaMeasurementId,
  gaPageLocation,
  gaReferrer,
  initGoogleAnalytics,
  privacySignalOn,
  resetGoogleAnalyticsForTests,
  setAnalyticsOptOut,
  trackGooglePageView,
} from "./analytics";

/**
 * Google Analytics 4: loads only with a real ID, on the production host, and without GPC,
 * DNT or the footer opt-out; otherwise loads with the agreed consent defaults and config, and
 * sends scrubbed page views.
 *
 * Every "does not load" test first asserts that its setup took effect (the signal is visible
 * to the page, the flag is stored, the host is what the test says), so a setup that silently
 * does nothing cannot pass as a guard that works.
 */

const ID = "G-GXZNBWJB8D";
const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const REPO = (path: string) => join(REPO_ROOT, path);

declare const jsdom: { reconfigure(options: { url: string }): void };

function commands(): unknown[][] {
  return (window.dataLayer ?? []).map((entry) => Array.from(entry as ArrayLike<unknown>));
}

function gaScripts(): HTMLScriptElement[] {
  return Array.from(
    document.head.querySelectorAll<HTMLScriptElement>('script[src*="googletagmanager.com"]'),
  );
}

function expectNothingLoaded(): void {
  expect(gaScripts()).toHaveLength(0);
  expect(window.dataLayer).toBeUndefined();
  expect(Object.getOwnPropertyDescriptor(window, `ga-disable-${ID}`)).toBeUndefined();
}

function setNavigatorValue(key: string, value: unknown): void {
  Object.defineProperty(navigator, key, { configurable: true, value });
}

beforeEach(() => {
  jsdom.reconfigure({ url: `https://${PRODUCTION_HOSTNAME}/en/` });
  resetGoogleAnalyticsForTests();
  vi.stubEnv("NEXT_PUBLIC_GA_MEASUREMENT_ID", ID);
});

afterEach(() => {
  vi.unstubAllEnvs();
  for (const key of ["globalPrivacyControl", "doNotTrack", "msDoNotTrack"]) {
    Reflect.deleteProperty(navigator, key);
  }
  Reflect.deleteProperty(window, "doNotTrack");
  Reflect.deleteProperty(window, `ga-disable-${ID}`);
  delete window.dataLayer;
  for (const script of gaScripts()) script.remove();
  window.localStorage.clear();
  for (const name of ["_ga", `_ga_${ID.slice(2)}`, "_ga_OTHERSITE"]) {
    document.cookie = `${name}=; Max-Age=0; path=/`;
  }
  document.title = "";
});

describe("gaMeasurementId()", () => {
  it("accepts a GA4 measurement ID and trims it", () => {
    expect(gaMeasurementId(ID)).toBe(ID);
    expect(gaMeasurementId(` ${ID}\n`)).toBe(ID);
  });

  // (`undefined` is the no-ID build, covered below: it selects the built-in default.)
  it.each([null, 42, "", "   ", "UA-12345-1", "G-", "g-gxznbwjb8d", 'G-GX"><script>'])(
    "rejects %j",
    (raw) => {
      expect(gaMeasurementId(raw)).toBeNull();
    },
  );
});

describe("initGoogleAnalytics(): when GA must not load", () => {
  it("loads nothing when no ID is built in", () => {
    vi.stubEnv("NEXT_PUBLIC_GA_MEASUREMENT_ID", "");
    expect(process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID).toBe("");
    expect(initGoogleAnalytics()).toBe(false);
    expectNothingLoaded();
  });

  it("loads nothing when the ID is malformed", () => {
    vi.stubEnv("NEXT_PUBLIC_GA_MEASUREMENT_ID", "UA-12345-1");
    expect(initGoogleAnalytics()).toBe(false);
    expectNothingLoaded();
  });

  it.each(["localhost", "127.0.0.1", "chelseakr.com", "camino.chelseakr.com"])(
    "loads nothing when the page is served from %s",
    (host) => {
      jsdom.reconfigure({ url: `http://${host}/en/` });
      expect(window.location.hostname).toBe(host);
      expect(initGoogleAnalytics()).toBe(false);
      expectNothingLoaded();
    },
  );

  it("loads nothing under Global Privacy Control", () => {
    setNavigatorValue("globalPrivacyControl", true);
    expect(privacySignalOn()).toBe(true);
    expect(initGoogleAnalytics()).toBe(false);
    expectNothingLoaded();
  });

  it.each([
    ["navigator.doNotTrack", () => setNavigatorValue("doNotTrack", "1")],
    ['navigator.doNotTrack = "yes"', () => setNavigatorValue("doNotTrack", "yes")],
    ["navigator.msDoNotTrack", () => setNavigatorValue("msDoNotTrack", "1")],
    [
      "window.doNotTrack",
      () => Object.defineProperty(window, "doNotTrack", { configurable: true, value: "1" }),
    ],
  ])("loads nothing under Do Not Track (%s)", (_label, apply) => {
    expect(privacySignalOn()).toBe(false);
    apply();
    expect(privacySignalOn()).toBe(true);
    expect(initGoogleAnalytics()).toBe(false);
    expectNothingLoaded();
  });

  it("loads nothing after the footer opt-out, and removes this site's GA cookies", () => {
    window.localStorage.setItem(ANALYTICS_OPT_OUT_KEY, "1");
    document.cookie = "_ga=GA1.1.123.456; path=/";
    document.cookie = `_ga_${ID.slice(2)}=GS1.1.789; path=/`;
    document.cookie = "_ga_OTHERSITE=GS1.1.1; path=/";
    expect(window.localStorage.getItem(ANALYTICS_OPT_OUT_KEY)).toBe("1");
    expect(document.cookie).toContain("_ga=");

    expect(initGoogleAnalytics()).toBe(false);
    expectNothingLoaded();
    expect(document.cookie).not.toMatch(/(^|; )_ga=/);
    expect(document.cookie).not.toContain(`_ga_${ID.slice(2)}=`);
    // Another property's cookie on the shared parent domain is not this site's to delete.
    expect(document.cookie).toContain("_ga_OTHERSITE=");
  });

  it('treats DNT "0" and GPC false as no signal', () => {
    setNavigatorValue("doNotTrack", "0");
    setNavigatorValue("globalPrivacyControl", false);
    expect(initGoogleAnalytics()).toBe(true);
  });
});

describe("initGoogleAnalytics(): when GA loads", () => {
  it("adds exactly one async gtag.js script for the configured ID", () => {
    expect(initGoogleAnalytics()).toBe(true);
    const scripts = gaScripts();
    expect(scripts).toHaveLength(1);
    expect(scripts[0]?.async).toBe(true);
    expect(scripts[0]?.src).toBe(`https://www.googletagmanager.com/gtag/js?id=${ID}`);
    expect(initGoogleAnalytics()).toBe(true);
    expect(gaScripts()).toHaveLength(1);
  });

  it("pushes the Consent Mode v2 defaults, then the config with ads features off", () => {
    initGoogleAnalytics();
    const [regional, global, redaction, js, config] = commands();
    expect(regional).toEqual([
      "consent",
      "default",
      {
        ad_storage: "denied",
        ad_user_data: "denied",
        ad_personalization: "denied",
        analytics_storage: "denied",
        region: CONSENT_DENIED_REGIONS,
      },
    ]);
    expect(global).toEqual([
      "consent",
      "default",
      {
        ad_storage: "denied",
        ad_user_data: "denied",
        ad_personalization: "denied",
        analytics_storage: "granted",
      },
    ]);
    expect(redaction).toEqual(["set", "ads_data_redaction", true]);
    expect(js?.[0]).toBe("js");
    expect(config).toEqual([
      "config",
      ID,
      { send_page_view: false, allow_google_signals: false, allow_ad_personalization_signals: false },
    ]);
    expect(commands()).toHaveLength(5);
  });

  it("denies analytics storage in the EEA, the UK and Switzerland", () => {
    const eu27 = "AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE";
    for (const code of [...eu27.split(" "), "IS", "LI", "NO", "GB", "CH"]) {
      expect(CONSENT_DENIED_REGIONS).toContain(code);
    }
    expect(CONSENT_DENIED_REGIONS).not.toContain("US");
  });

  it("defines the ga-disable kill switch as a live view of the opt-out", () => {
    initGoogleAnalytics();
    const disabled = () => (window as unknown as Record<string, unknown>)[`ga-disable-${ID}`];
    expect(disabled()).toBe(false);
    window.localStorage.setItem(ANALYTICS_OPT_OUT_KEY, "1");
    expect(disabled()).toBe(true);
  });
});

describe("page views", () => {
  const origin = `https://${PRODUCTION_HOSTNAME}`;

  it("does nothing until GA has loaded", () => {
    trackGooglePageView("/en/", "");
    expect(window.dataLayer).toBeUndefined();
  });

  it("sends one scrubbed page view per page, chaining the referrer", () => {
    initGoogleAnalytics();
    const before = commands().length;
    document.title = "Afterward";
    trackGooglePageView("/en/", "?q=warehouse+fresno&list=u1.u2&utm_source=newsletter");
    trackGooglePageView("/en/", "?q=warehouse&utm_source=newsletter"); // a refined search
    document.title = "CDL Class A | Afterward";
    trackGooglePageView("/en/programs/u1/", "");
    expect(commands().slice(before)).toEqual([
      ["set", { page_location: `${origin}/en/?utm_source=newsletter`, page_title: "Afterward" }],
      ["event", "page_view"],
      [
        "set",
        {
          page_location: `${origin}/en/programs/u1/`,
          page_title: "CDL Class A | Afterward",
          page_referrer: `${origin}/en/?utm_source=newsletter`,
        },
      ],
      ["event", "page_view"],
    ]);
  });

  it("sends nothing once the reader opts out mid-visit", () => {
    initGoogleAnalytics();
    const before = commands().length;
    expect(setAnalyticsOptOut(true)).toBe(true);
    expect(window.localStorage.getItem(ANALYTICS_OPT_OUT_KEY)).toBe("1");
    trackGooglePageView("/en/about/", "");
    expect(commands().length).toBe(before);
  });

  it("starts GA and records the current page when the reader opts back in", () => {
    window.localStorage.setItem(ANALYTICS_OPT_OUT_KEY, "1");
    expect(initGoogleAnalytics()).toBe(false);
    expectNothingLoaded();

    window.history.pushState(null, "", "/es/about/");
    expect(setAnalyticsOptOut(false)).toBe(true);
    expect(window.localStorage.getItem(ANALYTICS_OPT_OUT_KEY)).toBeNull();
    expect(gaScripts()).toHaveLength(1);
    expect(commands()).toContainEqual([
      "set",
      expect.objectContaining({ page_location: `${origin}/es/about/` }),
    ]);
  });

  it("does not start GA on opt-back-in while a browser signal still applies", () => {
    window.localStorage.setItem(ANALYTICS_OPT_OUT_KEY, "1");
    setNavigatorValue("globalPrivacyControl", true);
    expect(setAnalyticsOptOut(false)).toBe(true);
    expectNothingLoaded();
  });

  it("reports failure, and stores nothing, when storage is blocked", () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    try {
      expect(setAnalyticsOptOut(true)).toBe(false);
      expect(setItem).toHaveBeenCalled();
    } finally {
      setItem.mockRestore();
    }
    expect(window.localStorage.getItem(ANALYTICS_OPT_OUT_KEY)).toBeNull();
  });
});

describe("address scrubbing", () => {
  const origin = `https://${PRODUCTION_HOSTNAME}`;

  it("keeps plain slugs and only the utm_* campaign tags", () => {
    expect(gaPageLocation(origin, "/en/occupations/53-3032/", "?sort=cost&utm_medium=social")).toBe(
      `${origin}/en/occupations/53-3032/?utm_medium=social`,
    );
  });

  it("redacts any path segment that is not a plain slug", () => {
    expect(gaPageLocation(origin, "/en/someone@example.com/", "")).toBe(`${origin}/en/:redacted/`);
    expect(gaPageLocation(origin, "/es/a%20b/", "")).toBe(`${origin}/es/:redacted/`);
    expect(gaPageLocation(origin, `/${"a".repeat(101)}/`, "")).toBe(`${origin}/:redacted/`);
  });

  it("reduces another site to its origin and scrubs one of our own pages", () => {
    expect(gaReferrer("https://www.google.com/search?q=cdl+fresno", origin)).toBe(
      "https://www.google.com/",
    );
    expect(gaReferrer(`${origin}/en/?q=nurse#results`, origin)).toBe(`${origin}/en/`);
    expect(gaReferrer("", origin)).toBe("");
    expect(gaReferrer("not a url", origin)).toBe("");
  });

  it("clearGoogleAnalyticsCookies() is a no-op without an ID", () => {
    document.cookie = "_ga=GA1.1.1.1; path=/";
    clearGoogleAnalyticsCookies(null);
    expect(document.cookie).toContain("_ga=");
  });
});

describe("where the ID and the CSP live", () => {
  it("only the production deploy build sets the measurement ID", () => {
    const deploy = readFileSync(REPO(".github/workflows/deploy.yml"), "utf8");
    expect(deploy.match(/NEXT_PUBLIC_GA_MEASUREMENT_ID:/g)).toHaveLength(1);
    expect(deploy).toContain(`NEXT_PUBLIC_GA_MEASUREMENT_ID: ${ID}`);
    const ci = readFileSync(REPO(".github/workflows/ci.yml"), "utf8");
    expect(ci).not.toContain("NEXT_PUBLIC_GA_MEASUREMENT_ID");
  });

  it("the CloudFront CSP allows exactly the GA origins the loader needs", () => {
    const template = readFileSync(REPO("infra/aws-static-site.yml"), "utf8");
    const block = template.match(/ContentSecurityPolicy: >-\n((?: {14}.*\n)+)/)?.[1] ?? "";
    const csp = block.replace(/\s+/g, " ").trim();
    expect(csp).toContain("default-src 'self'");
    const directive = (name: string) =>
      csp
        .split(";")
        .map((part) => part.trim().split(" "))
        .find(([key]) => key === name)
        ?.slice(1) ?? [];
    const google = (name: string) => directive(name).filter((src) => /google/.test(src));
    expect(google("script-src")).toEqual(["https://www.googletagmanager.com"]);
    for (const name of ["connect-src", "img-src"]) {
      expect(google(name)).toEqual(["https://*.google-analytics.com", "https://*.analytics.google.com"]);
    }
    expect(google("default-src")).toEqual([]);
  });
});
