"use client";

import { useEffect, useState } from "react";

import { ANALYTICS_OPT_OUT_KEY, analyticsOptOutStored, setAnalyticsOptOut } from "@/lib/analytics";

export interface AnalyticsOptOutLabels {
  optOut: string;
  optIn: string;
  offStatus: string;
  onStatus: string;
}

function storageWorks(): boolean {
  try {
    const current = window.localStorage.getItem(ANALYTICS_OPT_OUT_KEY);
    window.localStorage.setItem(ANALYTICS_OPT_OUT_KEY, current ?? "0");
    if (current === null) window.localStorage.removeItem(ANALYTICS_OPT_OUT_KEY);
    return true;
  } catch {
    return false;
  }
}

/**
 * The footer's "Opt out of analytics" control, remembered in this browser until "Opt back
 * in". The About page's privacy section describes it.
 *
 * A button, not a link: it changes a setting rather than going anywhere. It renders nothing
 * until mounted, because the exported HTML cannot know this browser's choice and hydration
 * must match it; and nothing at all where storage is blocked, since the choice could not be
 * kept. Labels come in as props from the server layout so neither dictionary ships in the
 * bundle. The button keeps its place in both states so focus stays on it after a click, and
 * a polite status line says (and announces) that analytics is off in this browser.
 */
export function AnalyticsOptOut({ labels }: { labels: AnalyticsOptOutLabels }) {
  const [state, setState] = useState<"on" | "off" | null>(null);
  const [changed, setChanged] = useState(false);

  useEffect(() => {
    if (storageWorks()) setState(analyticsOptOutStored() ? "off" : "on");
  }, []);

  if (state === null) return null;

  const choose = (optOut: boolean) => {
    if (!setAnalyticsOptOut(optOut)) return;
    setState(optOut ? "off" : "on");
    setChanged(true);
  };

  let status = "";
  if (state === "off") status = labels.offStatus;
  else if (changed) status = labels.onStatus;

  return (
    <>
      {" "}
      <button type="button" className="analytics-opt-out" onClick={() => choose(state === "on")}>
        {state === "on" ? labels.optOut : labels.optIn}
      </button>{" "}
      <span className="analytics-opt-out-status" role="status">
        {status}
      </span>
    </>
  );
}
