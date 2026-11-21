// @vitest-environment jsdom

/**
 * "Show programs in" on occupation pages.
 *
 * Pinned: it renders nothing on the server, so a reader without JavaScript gets the whole
 * list and no control that does nothing; choosing an area hides every card filed under a
 * different one, including the programs with no area, which are never shown under a nearby
 * area; "All of California" brings every card back; and a choice that could narrow nothing
 * is not offered. The axe pass excludes the layout-dependent rules for the reason
 * `AskPanel.a11y.test.tsx` gives; the built page is checked in Chromium by
 * `npm run a11y:rendered`.
 */

import axe from "axe-core";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { dict } from "@/lib/i18n";
import { regionOptions } from "@/lib/regionOptions";

import { RegionFilter } from "./RegionFilter";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const LAYOUT_DEPENDENT = new Set(["color-contrast", "color-contrast-enhanced", "target-size"]);

/** The cards an occupation page renders, by the area each was placed in ("" = none). */
const CARDS = [
  ["a", "Vallejo MSA"],
  ["b", "Oakland-Fremont-Berkeley MD"],
  ["c", "Vallejo MSA"],
  ["d", ""],
  ["e", "Oakland-Fremont-Berkeley MD"],
] as const;

let container: HTMLElement;
let root: Root;

beforeEach(() => {
  container = document.createElement("main");
  container.innerHTML =
    '<div id="filter"></div><ul id="occupation-programs">' +
    CARDS.map(([id, area]) => `<li data-id="${id}" data-area="${area}">${id}</li>`).join("") +
    "</ul>";
  document.body.appendChild(container);
  root = createRoot(container.querySelector("#filter") as HTMLElement);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

function filter(lang: "en" | "es" = "en", areas: readonly string[] = CARDS.map(([, a]) => a)) {
  const t = dict(lang);
  return (
    <RegionFilter
      listId="occupation-programs"
      label={t.regionFilterLabel}
      allLabel={t.regionFilterAll(areas.length)}
      total={areas.length}
      options={regionOptions(areas.map((area) => (area === "" ? null : area)))}
    />
  );
}

function visible(): string[] {
  return [...container.querySelectorAll<HTMLElement>("#occupation-programs > li")]
    .filter((li) => !li.hidden)
    .map((li) => li.dataset.id ?? "");
}

async function choose(value: string) {
  const select = container.querySelector("select") as HTMLSelectElement;
  await act(async () => {
    select.value = value;
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

describe("RegionFilter", () => {
  it("renders nothing on the server, so without JavaScript the whole list shows", () => {
    expect(renderToStaticMarkup(filter())).toBe("");
  });

  it("labels the control and lists the areas alphabetically with their counts", async () => {
    await act(async () => root.render(filter()));
    const t = dict("en");
    expect(container.querySelector("label")?.textContent).toBe(t.regionFilterLabel);
    expect([...container.querySelectorAll("option")].map((o) => o.textContent)).toEqual([
      t.regionFilterAll(5),
      "Oakland-Fremont-Berkeley MD (2)",
      "Vallejo MSA (2)",
    ]);
  });

  it("shows only one area's programs, never the unplaced ones, and then all again", async () => {
    await act(async () => root.render(filter()));
    expect(visible()).toEqual(["a", "b", "c", "d", "e"]);
    await choose("Vallejo MSA");
    expect(visible()).toEqual(["a", "c"]);
    await choose("Oakland-Fremont-Berkeley MD");
    expect(visible()).toEqual(["b", "e"]);
    await choose("");
    expect(visible()).toEqual(["a", "b", "c", "d", "e"]);
  });

  it("is not offered when one area holds every program", async () => {
    await act(async () => root.render(filter("en", ["Vallejo MSA", "Vallejo MSA"])));
    expect(container.querySelector("select")).toBeNull();
  });

  it("is offered when one area holds every placed program and some are unplaced", async () => {
    await act(async () => root.render(filter("en", ["Vallejo MSA", ""])));
    expect(container.querySelector("select")).not.toBeNull();
  });

  for (const lang of ["en", "es"] as const) {
    it(`has no accessibility violations, in ${lang}`, async () => {
      await act(async () => root.render(filter(lang)));
      const results = await axe.run(container, { resultTypes: ["violations"] });
      const violations = results.violations.filter((v) => !LAYOUT_DEPENDENT.has(v.id));
      expect(violations.map((v) => v.id)).toEqual([]);
    });
  }
});

describe("regionOptions", () => {
  it("counts each area once per program and leaves unplaced programs out", () => {
    expect(regionOptions(["Napa MSA", null, "Chico MSA", "Napa MSA", ""])).toEqual([
      { area: "Chico MSA", count: 1 },
      { area: "Napa MSA", count: 2 },
    ]);
  });
});
