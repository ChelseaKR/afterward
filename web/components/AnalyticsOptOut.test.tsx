// @vitest-environment jsdom

/**
 * The footer's "Opt out of analytics" control, and the page views the layout sends as a
 * reader moves around. Rendered with react-dom directly, as the other component tests are.
 */

import axe from "axe-core";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { dict } from "@/lib/i18n";
import {
  ANALYTICS_OPT_OUT_KEY,
  PRODUCTION_HOSTNAME,
  resetGoogleAnalyticsForTests,
} from "@/lib/analytics";

import { AnalyticsOptOut } from "./AnalyticsOptOut";
import { GoogleAnalytics } from "./GoogleAnalytics";

let pathname = "/en/";
vi.mock("next/navigation", () => ({ usePathname: () => pathname }));

declare const jsdom: { reconfigure(options: { url: string }): void };

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const LAYOUT_DEPENDENT = new Set(["color-contrast", "color-contrast-enhanced", "target-size"]);

function labels(lang: "en" | "es") {
  const t = dict(lang);
  return {
    optOut: t.analyticsOptOut,
    optIn: t.analyticsOptIn,
    offStatus: t.analyticsOffStatus,
    onStatus: t.analyticsOnStatus,
  };
}

let container: HTMLElement;
let root: Root;

beforeEach(() => {
  container = document.createElement("footer");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  window.localStorage.clear();
});

const button = () => container.querySelector("button");
const status = () => container.querySelector('[role="status"]')?.textContent ?? "";

describe("AnalyticsOptOut", () => {
  it("opts out, is remembered on the next page, and opts back in", async () => {
    await act(async () => root.render(<AnalyticsOptOut labels={labels("en")} />));
    expect(button()?.textContent).toBe("Opt out of analytics");
    expect(window.localStorage.getItem(ANALYTICS_OPT_OUT_KEY)).toBeNull();

    await act(async () => button()?.click());
    expect(window.localStorage.getItem(ANALYTICS_OPT_OUT_KEY)).toBe("1");
    expect(button()?.textContent).toBe("Opt back in");
    expect(status()).toBe("Analytics is off in this browser.");

    // The next page reads the stored choice.
    await act(async () => root.unmount());
    root = createRoot(container);
    await act(async () => root.render(<AnalyticsOptOut labels={labels("en")} />));
    expect(button()?.textContent).toBe("Opt back in");

    await act(async () => button()?.click());
    expect(window.localStorage.getItem(ANALYTICS_OPT_OUT_KEY)).toBeNull();
    expect(button()?.textContent).toBe("Opt out of analytics");
    expect(status()).toBe("Analytics is back on.");
  });

  it("is in Spanish on Spanish pages", async () => {
    await act(async () => root.render(<AnalyticsOptOut labels={labels("es")} />));
    expect(button()?.textContent).toBe("Desactivar las analíticas");
    await act(async () => button()?.click());
    expect(button()?.textContent).toBe("Volver a activarlas");
    expect(status()).toBe("Las analíticas están desactivadas en este navegador.");
  });

  it("has no axe violations in either state", async () => {
    await act(async () => root.render(<AnalyticsOptOut labels={labels("en")} />));
    await act(async () => button()?.click());
    const results = await axe.run(container, { resultTypes: ["violations"] });
    expect(results.violations.filter((v) => !LAYOUT_DEPENDENT.has(v.id)).map((v) => v.id)).toEqual([]);
  });

  it("renders nothing where storage is blocked, since the choice could not be kept", async () => {
    const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    try {
      await act(async () => root.render(<AnalyticsOptOut labels={labels("en")} />));
      expect(getItem).toHaveBeenCalled();
      expect(button()).toBeNull();
    } finally {
      getItem.mockRestore();
    }
  });
});

describe("GoogleAnalytics (the layout's page-view sender)", () => {
  beforeEach(() => {
    jsdom.reconfigure({ url: `https://${PRODUCTION_HOSTNAME}/en/` });
    resetGoogleAnalyticsForTests();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    delete window.dataLayer;
    Reflect.deleteProperty(window, "ga-disable-G-GXZNBWJB8D");
    for (const script of document.head.querySelectorAll("script")) script.remove();
  });

  const pageViews = () =>
    (window.dataLayer ?? [])
      .map((entry) => Array.from(entry as ArrayLike<unknown>))
      .filter((command) => command[0] === "event" && command[1] === "page_view");

  it("sends nothing in a build without an ID", async () => {
    vi.stubEnv("NEXT_PUBLIC_GA_MEASUREMENT_ID", "");
    await act(async () => root.render(<GoogleAnalytics />));
    expect(window.dataLayer).toBeUndefined();
  });

  it("sends one page view on arrival and one per client-side navigation", async () => {
    vi.stubEnv("NEXT_PUBLIC_GA_MEASUREMENT_ID", "G-GXZNBWJB8D");
    pathname = "/en/";
    await act(async () => root.render(<GoogleAnalytics />));
    expect(pageViews()).toHaveLength(1);

    pathname = "/en/about/";
    await act(async () => root.render(<GoogleAnalytics />));
    expect(pageViews()).toHaveLength(2);

    // Same path again (a re-render, or a search refined in place): not a new page.
    await act(async () => root.render(<GoogleAnalytics />));
    expect(pageViews()).toHaveLength(2);
  });
});
