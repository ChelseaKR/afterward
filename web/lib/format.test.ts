import { describe, expect, it } from "vitest";

import { count, isSmallSample, money, percent, signedPercent, tidyName } from "./format";

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
  it("treats values at or below 1 as fractions", () => {
    expect(percent(0.64, "en")).toBe("64%");
    expect(percent(1, "en")).toBe("100%");
  });

  it("treats values above 1 as whole percentages", () => {
    // The feed is inconsistent about this; both encodings appear.
    expect(percent(64, "en")).toBe("64%");
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
