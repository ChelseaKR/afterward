"use client";

import { useEffect, useId, useState } from "react";

import type { RegionOption } from "@/lib/regionOptions";

/**
 * "Show programs in" on an occupation page: narrows the program list to one EDD area.
 *
 * In the page only. It changes no URL and writes no history, so it creates no page a search
 * engine could find and nothing a reader could share expecting someone else to see the same
 * list. It renders nothing until the browser has run it: without JavaScript there is no
 * control that does nothing, and the whole list shows, which is the page as it always was.
 *
 * It hides cards rather than re-rendering them. The cards are server-rendered with a
 * `data-area` naming the area each program was placed in, and a program with no area carries
 * an empty one, so it shows under "All of California" and under no single area: it is never
 * filed under a neighboring area. Setting `hidden` is an attribute change, which survives
 * hydration; the labels arrive as strings so the dictionary stays out of the browser bundle.
 */
export function RegionFilter({
  listId,
  label,
  allLabel,
  total,
  options,
}: {
  /** The `id` of the `<ul>` whose `<li data-area>` children this filters. */
  listId: string;
  label: string;
  /** "All of California (N)", already interpolated. */
  allLabel: string;
  total: number;
  options: readonly RegionOption[];
}) {
  const id = useId();
  const [ready, setReady] = useState(false);
  const [area, setArea] = useState("");

  useEffect(() => setReady(true), []);

  useEffect(() => {
    const list = document.getElementById(listId);
    if (list === null) return;
    for (const item of Array.from(list.children)) {
      if (!(item instanceof HTMLElement)) continue;
      item.hidden = area !== "" && item.dataset.area !== area;
    }
  }, [area, listId]);

  // A choice that could narrow nothing is not offered: one area holding every program.
  if (!ready || !options.some((option) => option.count < total)) return null;

  return (
    <div className="field region-filter">
      <label htmlFor={id}>{label}</label>
      <select id={id} value={area} onChange={(event) => setArea(event.target.value)}>
        <option value="">{allLabel}</option>
        {options.map((option) => (
          <option key={option.area} value={option.area}>
            {`${option.area} (${option.count})`}
          </option>
        ))}
      </select>
    </div>
  );
}
