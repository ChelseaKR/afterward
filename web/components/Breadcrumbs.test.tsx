// @vitest-environment jsdom

/**
 * The breadcrumb on program, occupation and provider pages, and the BreadcrumbList JSON-LD
 * that goes out with it.
 *
 * Pinned: the visible trail and the structured trail are one list, so they cannot disagree;
 * `aria-current="page"` marks the last item only when it is the page being read (a program
 * page's trail ends at its provider, which is a parent); and nothing in a name can close the
 * script element the JSON-LD sits in. The axe pass excludes the layout-dependent rules for
 * the reason `AskPanel.a11y.test.tsx` gives; target size and contrast are answered on the
 * built pages by `npm run a11y:rendered` and `npm run contrast`.
 */

import axe from "axe-core";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LANGUAGES, dict } from "@/lib/i18n";
import { SITE_URL } from "@/lib/site";

import { Breadcrumbs, breadcrumbJsonLd, type Crumb } from "./Breadcrumbs";

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    prefetch: _prefetch,
    ...rest
  }: {
    href: string;
    children: unknown;
    prefetch?: boolean;
  }) => (
    <a href={href} {...rest}>
      {children as never}
    </a>
  ),
}));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const LAYOUT_DEPENDENT = new Set(["color-contrast", "color-contrast-enhanced", "target-size"]);

function providerTrail(lang: "en" | "es"): Crumb[] {
  const t = dict(lang);
  return [
    { name: t.siteName, href: `/${lang}/` },
    { name: t.navProviders, href: `/${lang}/providers/` },
    { name: "Fairfield Suisun Adult School", href: `/${lang}/providers/fairfield-suisun-adult-school/` },
  ];
}

let container: HTMLElement;
let root: Root;

beforeEach(() => {
  container = document.createElement("main");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

describe("Breadcrumbs", () => {
  for (const lang of LANGUAGES) {
    it(`is a navigation landmark named by the dictionary, in ${lang}`, async () => {
      await act(async () =>
        root.render(<Breadcrumbs lang={lang} trail={providerTrail(lang)} current />),
      );
      const nav = container.querySelector("nav");
      expect(nav?.getAttribute("aria-label")).toBe(dict(lang).breadcrumbLabel);
      expect(nav?.querySelectorAll("ol > li")).toHaveLength(3);
    });

    it(`has no accessibility violations, in ${lang}`, async () => {
      await act(async () =>
        root.render(<Breadcrumbs lang={lang} trail={providerTrail(lang)} current />),
      );
      const results = await axe.run(container, { resultTypes: ["violations"] });
      const violations = results.violations.filter((v) => !LAYOUT_DEPENDENT.has(v.id));
      expect(violations.map((v) => v.id)).toEqual([]);
    });
  }

  it("marks the last item as this page, unlinked, when it is this page", async () => {
    await act(async () =>
      root.render(<Breadcrumbs lang="en" trail={providerTrail("en")} current />),
    );
    const items = [...container.querySelectorAll("li")];
    expect(items.slice(0, 2).every((li) => li.querySelector("a") !== null)).toBe(true);
    const last = items[2];
    expect(last?.querySelector("a")).toBeNull();
    expect(last?.querySelector('[aria-current="page"]')?.textContent).toBe(
      "Fairfield Suisun Adult School",
    );
  });

  it("links every item, and marks none current, when the trail ends at a parent", async () => {
    // A program page: its trail ends at the provider, which is not the page being read.
    await act(async () =>
      root.render(<Breadcrumbs lang="en" trail={providerTrail("en")} current={false} />),
    );
    expect(container.querySelectorAll("li a")).toHaveLength(3);
    expect(container.querySelector("[aria-current]")).toBeNull();
  });

  it("marks a name the feed publishes in English only", async () => {
    const trail = providerTrail("es").map((crumb, index) =>
      index === 2 ? { ...crumb, lang: "en" as const } : crumb,
    );
    await act(async () => root.render(<Breadcrumbs lang="es" trail={trail} current />));
    expect(container.querySelector('[aria-current="page"]')?.getAttribute("lang")).toBe("en");
  });

  it("publishes the same trail as BreadcrumbList JSON-LD", async () => {
    await act(async () =>
      root.render(<Breadcrumbs lang="en" trail={providerTrail("en")} current />),
    );
    const script = container.querySelector('script[type="application/ld+json"]');
    const data = JSON.parse(script?.textContent ?? "{}");
    expect(data["@type"]).toBe("BreadcrumbList");
    expect(data.itemListElement).toEqual(
      providerTrail("en").map((crumb, index) => ({
        "@type": "ListItem",
        position: index + 1,
        name: crumb.name,
        item: `${SITE_URL}${crumb.href}`,
      })),
    );
  });
});

describe("breadcrumbJsonLd", () => {
  it("cannot be closed early by a name", () => {
    const json = breadcrumbJsonLd([
      { name: "</script><script>alert(1)</script>", href: "/en/providers/x/" },
    ]);
    expect(json).not.toContain("<");
    expect(JSON.parse(json).itemListElement[0].name).toBe("</script><script>alert(1)</script>");
  });
});
