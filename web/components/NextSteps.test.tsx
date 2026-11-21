// @vitest-environment jsdom

/**
 * The "Before you decide" box on program pages.
 *
 * What is pinned here is what the box may and may not say. It links to places the site
 * already describes and claims nothing of its own, so each link must appear exactly when its
 * destination exists and never otherwise: a "who may pay" link on a page whose funding
 * section did not render would jump to nothing, and a box with no links would be a heading
 * promising next steps over an empty list.
 *
 * The axe pass excludes the layout-dependent rules for the reason `AskPanel.a11y.test.tsx`
 * gives. Contrast and target size are answered for the built page by `npm run contrast` and
 * the Chromium pass in `npm run a11y:rendered`.
 */

import axe from "axe-core";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LANGUAGES, dict } from "@/lib/i18n";

import { NextSteps, type NextStepsProps } from "./NextSteps";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: unknown }) => (
    <a href={href} {...rest}>
      {children as never}
    </a>
  ),
}));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const LAYOUT_DEPENDENT = new Set(["color-contrast", "color-contrast-enhanced", "target-size"]);

const FULL: Omit<NextStepsProps, "lang"> = {
  funding: true,
  provider: { href: "/en/providers/fairfield-suisun-adult-school/", name: "Fairfield Suisun Adult School" },
  website: { href: "https://example.test/sterile-processing", label: "Provider's website" },
};

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

async function render(props: NextStepsProps) {
  await act(async () => root.render(<NextSteps {...props} />));
}

function links(): { text: string; href: string | null }[] {
  return [...container.querySelectorAll("a")].map((a) => ({
    text: a.textContent ?? "",
    href: a.getAttribute("href"),
  }));
}

describe("the Before you decide box", () => {
  for (const lang of LANGUAGES) {
    const t = dict(lang);

    it(`lists who may pay, the provider's programs and its website, in ${lang}`, async () => {
      await render({ lang, ...FULL });
      expect(container.querySelector("h2")?.textContent).toBe(t.nextStepsHeading);
      expect(links()).toEqual([
        { text: t.nextStepsFunding, href: "#funding" },
        {
          text: t.nextStepsProviderPrograms("Fairfield Suisun Adult School"),
          href: "/en/providers/fairfield-suisun-adult-school/",
        },
        { text: "Provider's website", href: "https://example.test/sterile-processing" },
      ]);
    });

    it(`has no accessibility violations, in ${lang}`, async () => {
      await render({ lang, ...FULL });
      const results = await axe.run(container, { resultTypes: ["violations"] });
      const violations = results.violations.filter((v) => !LAYOUT_DEPENDENT.has(v.id));
      expect(violations.map((v) => v.id)).toEqual([]);
    });
  }

  it("is a labelled navigation region named by its own heading", async () => {
    await render({ lang: "en", ...FULL });
    const nav = container.querySelector("nav");
    const heading = container.querySelector("h2");
    expect(nav?.getAttribute("aria-labelledby")).toBe(heading?.id);
  });

  it("opens the provider's site the way the page's own provider link does", async () => {
    await render({ lang: "en", ...FULL });
    const external = container.querySelector('a[href^="https://"]');
    expect(external?.getAttribute("rel")).toBe("nofollow noopener noreferrer");
    expect(external?.getAttribute("target")).toBe("_blank");
  });

  it("does not link to a funding section the page did not render", async () => {
    await render({ lang: "en", ...FULL, funding: false });
    expect(links().map((l) => l.href)).not.toContain("#funding");
  });

  it("leaves out the provider links when the record names no provider or no site", async () => {
    await render({ lang: "en", funding: true, provider: null, website: null });
    expect(links()).toEqual([{ text: dict("en").nextStepsFunding, href: "#funding" }]);
  });

  it("renders nothing at all when it would have no links", async () => {
    await render({ lang: "en", funding: false, provider: null, website: null });
    expect(container.innerHTML).toBe("");
  });
});
