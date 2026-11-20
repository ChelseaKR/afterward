// @vitest-environment jsdom

/**
 * Two things on the search page that a screen reader user could not get from it, both found
 * by the WCAG 2.2 A/AA audit behind docs/accessibility/ACR.md (2026-11).
 *
 * - The "show more" control was a button whose whole name was "+ 50". Read aloud out of
 *   context, as a button list reads it, that is a number and a symbol, not a purpose
 *   (2.4.6 Headings and Labels).
 * - "Copy link" swaps its own text to "Link copied" for two seconds. A sighted reader sees
 *   that; a screen reader is not told, because a button's text changing is not a status
 *   message any assistive technology announces (4.1.3 Status Messages).
 *
 * Mounted with react-dom directly, as the other component tests are, over synthetic entries
 * so the test does not depend on which dataset happens to be in `public/data`.
 */

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { dict, type Lang } from "@/lib/i18n";
import type { SearchEntry } from "@/lib/types";

import { SearchApp } from "./SearchApp";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: unknown }) => (
    <a href={href} {...rest}>
      {children as never}
    </a>
  ),
}));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function entry(n: number): SearchEntry {
  return {
    i: `id-${n}`,
    n: `Program ${n}`,
    p: `Provider ${n}`,
    c: "Fresno",
    a: null,
    $: 1000 + n,
    $partial: false,
    at: true,
    w: 10,
    s: ["53-3032"],
    o: ["Heavy and Tractor-Trailer Truck Drivers"],
    g: 4.1,
    op: 1000,
    cr: 0.9,
    er: 0.8,
    me: 40000,
    r: true,
  };
}

/** More than one page of results, so the "show more" control renders. */
const PROGRAMS = Array.from({ length: 30 }, (_, n) => entry(n));

let container: HTMLElement;
let root: Root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

async function mount(lang: Lang) {
  await act(async () => root.render(<SearchApp programs={PROGRAMS} lang={lang} />));
}

describe.each(["en", "es"] as const)("SearchApp (%s)", (lang) => {
  const t = dict(lang);

  it("names the show-more button by what it does, not by a bare count", async () => {
    await mount(lang);
    const more = container.querySelector<HTMLButtonElement>(".card-list ~ p button");
    expect(more).not.toBeNull();
    const shown = container.querySelectorAll(".card-list > li").length;
    expect(more!.textContent).toBe(t.showMore(PROGRAMS.length - shown));
    expect(more!.textContent).not.toMatch(/^\+/);
  });

  it("announces a copied link through a status region, not only by relabelling the button", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    await mount(lang);

    const status = container.querySelector('.results-head [role="status"]');
    expect(status).not.toBeNull();
    expect(status!.textContent).toBe("");

    await act(async () => {
      container.querySelector<HTMLButtonElement>(".copy-link")!.click();
    });
    expect(writeText).toHaveBeenCalledOnce();
    expect(status!.textContent).toBe(t.copyLinkDone);
  });
});
