import { describe, expect, it } from "vitest";

import {
  count,
  isSmallSample,
  lengthText,
  money,
  percent,
  signedPercent,
  tidyName,
} from "./format";
import { dict } from "./i18n";

/**
 * The rule these tests exist to defend: a null measure must never render as a number.
 * WIOA withholds small-cohort cells to protect participant privacy, and a suppressed cell
 * displayed as 0% would misstate a real training provider's performance.
 */
describe("null never becomes a number", () => {
  it("returns null from every formatter", () => {
    expect(money(null, "en")).toBeNull();
    expect(percent(null, "en")).toBeNull();
    expect(signedPercent(null, "en")).toBeNull();
    expect(count(null, "en")).toBeNull();
  });

  it("still formats a genuine zero, which is a real reported value", () => {
    expect(money(0, "en")).toBe("$0");
    expect(percent(0, "en")).toBe("0%");
    expect(count(0, "en")).toBe("0");
  });
});

describe("money", () => {
  it("formats whole dollars without cents", () => {
    expect(money(32000, "en")).toBe("$32,000");
  });

  it("rounds rather than truncating", () => {
    expect(money(10200.6, "en")).toBe("$10,201");
  });
});

describe("percent", () => {
  it("formats a fraction", () => {
    expect(percent(0.64, "en")).toBe("64%");
    expect(percent(1, "en")).toBe("100%");
  });

  it("does not guess units", () => {
    // The pipeline validates that rates are fractions at parse time and refuses anything
    // outside 0..1, so there is nothing to disambiguate here. The old heuristic ("above 1
    // means whole percentages") read a genuine 1% as 100%, silently.
    expect(percent(0.01, "en")).toBe("1%");
    expect(percent(0.005, "en")).toBe("1%"); // rounds, but does not become 50%
  });
});

describe("signedPercent", () => {
  it("always shows the sign so growth and decline are unmistakable", () => {
    expect(signedPercent(12.5, "en")).toBe("+12.5%");
    expect(signedPercent(-15.8, "en")).toBe("-15.8%");
  });

  it("marks a flat projection explicitly", () => {
    expect(signedPercent(0, "en")).toBe("0%");
  });
});

describe("isSmallSample", () => {
  it("flags small cohorts so their rates are read with caution", () => {
    expect(isSmallSample(9)).toBe(true);
    expect(isSmallSample(25)).toBe(true);
    expect(isSmallSample(26)).toBe(false);
  });

  it("does not flag unknown or empty cohorts", () => {
    expect(isSmallSample(null)).toBe(false);
    expect(isSmallSample(0)).toBe(false);
  });
});

describe("tidyName", () => {
  it("title-cases the shouting provider names in the federal feed", () => {
    expect(tidyName("FRESNO CITY COLLEGE")).toBe("Fresno City College");
  });

  it("lowercases small joining words inside a name", () => {
    expect(tidyName("UNIVERSITY OF CALIFORNIA")).toBe("University of California");
  });

  it("leaves already-cased names alone", () => {
    expect(tidyName("Carteret Community College")).toBe("Carteret Community College");
  });

  it("returns an empty string for null", () => {
    expect(tidyName(null)).toBe("");
  });
});

describe("localisation", () => {
  it("uses US grouping for Spanish, matching what CA Spanish speakers read daily", () => {
    // es-US deliberately, not es-ES: the audience is in California, where a comma is the
    // thousands separator on every pay stub and utility bill they already receive.
    expect(count(1234567, "es")).toBe("1,234,567");
    expect(money(32000, "es")).toBe("$32,000");
  });

  it("keeps the not-reported contract in both languages", () => {
    expect(money(null, "es")).toBeNull();
    expect(percent(null, "es")).toBeNull();
  });
});

/**
 * The counterpart rule, and the one the pipeline broke until 2026-08-07: a null that is not an
 * absence must never render as "not reported".
 *
 * Every place that shows a program's length turns a null from this function into the site's
 * "Not reported" treatment, so returning null here *is* the claim that nobody said. A
 * competency-based program's provider did say: the course finishes when the student can do the
 * work. That is the whole of the bug, and this is where it cannot come back.
 */
describe("lengthText", () => {
  it.each(["en", "es"] as const)("never returns null for a competency-based program (%s)", (lang) => {
    const t = dict(lang);
    expect(lengthText(null, true, t)).toBe(t.lengthCompetencyBased);
    expect(lengthText(null, true, t)).not.toBeNull();
    expect(lengthText(null, true, t)).not.toBe(t.notReported);
  });

  it("still returns null for a record that genuinely says nothing", () => {
    expect(lengthText(null, false, dict("en"))).toBeNull();
  });

  it("prefers the design statement over a week count filed beside it", () => {
    const t = dict("en");
    expect(lengthText(6, true, t)).toBe(t.lengthCompetencyBased);
  });

  it("reads a record built before the field as it always behaved", () => {
    const t = dict("en");
    expect(lengthText(6, undefined, t)).toBe(t.weeks(6));
    expect(lengthText(null, undefined, t)).toBeNull();
  });
});
