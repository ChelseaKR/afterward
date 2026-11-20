// @vitest-environment jsdom

/**
 * The comparison tray must not hide the control that has keyboard focus (WCAG 2.4.11 Focus
 * Not Obscured, found by the 2026-11 audit behind docs/accessibility/ACR.md).
 *
 * The tray is sticky at the bottom of the viewport. Tabbing scrolls each control just into
 * view at the bottom edge, which is where the tray is, so focus landed behind it: in
 * Chromium, three filter selects on a desktop and most of the result list on a phone. The
 * fix pads the document's scroll area by the tray's height while the tray is on screen.
 * jsdom has no layout, so the height is stubbed; the browser half of this is checked by the
 * keyboard walk in the ACR's evaluation.
 */

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { dict } from "@/lib/i18n";
import type { SearchEntry } from "@/lib/types";

import { CompareTray, MAX_COMPARE } from "./Compare";

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
    c: null,
    a: null,
    $: null,
    $partial: false,
    at: true,
    w: null,
    s: [],
    o: [],
    g: null,
    op: null,
    cr: null,
    er: null,
    me: null,
    r: false,
  };
}

const TRAY_HEIGHT = 239.4;
let height = TRAY_HEIGHT;

let container: HTMLElement;
let root: Root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (
    this: HTMLElement,
  ) {
    const h = this.classList.contains("compare-tray") ? height : 0;
    return { x: 0, y: 0, top: 0, left: 0, right: 0, bottom: h, width: 0, height: h } as DOMRect;
  });
});

afterEach(async () => {
  height = TRAY_HEIGHT;
  await act(async () => root.unmount());
  container.remove();
  vi.restoreAllMocks();
  document.documentElement.style.removeProperty("scroll-padding-bottom");
});

function tray(selected: SearchEntry[]) {
  return (
    <CompareTray
      selected={selected}
      lang="en"
      open={false}
      onRemove={() => {}}
      onClear={() => {}}
      onOpen={() => {}}
    />
  );
}

describe("CompareTray and focus", () => {
  it("pads the page's scroll area by the tray's height while the tray is shown", async () => {
    await act(async () => root.render(tray([entry(1), entry(2)])));
    expect(container.querySelector(".compare-tray")).not.toBeNull();
    expect(document.documentElement.style.scrollPaddingBottom).toBe(
      `${Math.ceil(TRAY_HEIGHT) + 8}px`,
    );
  });

  it("re-measures on the render that grows the tray, not a frame later", async () => {
    await act(async () => root.render(tray([entry(1), entry(2)])));
    height = 408;
    await act(async () => root.render(tray([entry(1), entry(2), entry(3)])));
    expect(document.documentElement.style.scrollPaddingBottom).toBe("416px");
  });

  it("gives the padding back when the tray goes away", async () => {
    await act(async () => root.render(tray([entry(1)])));
    expect(document.documentElement.style.scrollPaddingBottom).not.toBe("");
    await act(async () => root.render(tray([])));
    expect(container.querySelector(".compare-tray")).toBeNull();
    expect(document.documentElement.style.scrollPaddingBottom).toBe("");
  });
});

describe("CompareTray and the comparison limit", () => {
  it("keeps its status region in the page before the limit is reached, so the message is announced", async () => {
    await act(async () => root.render(tray([entry(1)])));
    const status = container.querySelector('.compare-tray [role="status"]');
    expect(status).not.toBeNull();
    expect(status!.textContent).toBe("");

    const full = Array.from({ length: MAX_COMPARE }, (_, n) => entry(n));
    await act(async () => root.render(tray(full)));
    expect(container.querySelector('.compare-tray [role="status"]')).toBe(status);
    expect(status!.textContent).toBe(dict("en").compareFull);
  });
});
