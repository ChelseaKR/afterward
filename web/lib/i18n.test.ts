import { describe, expect, it } from "vitest";

import { LANGUAGES, OTHER_LANG, dict, entityTypeLabel, feedTextLang, isLang } from "./i18n";

const en = dict("en");
const es = dict("es");

/**
 * Keys allowed to be identical across languages, each for a stated reason.
 *
 * `siteName` is a proper noun. `searchPlaceholder` holds example search terms, and the
 * searchable corpus — program names, provider names, occupation titles — is English only,
 * so Spanish examples would send a Spanish speaker straight to an empty result set. The
 * honest placeholder is one that actually matches something.
 */
const DELIBERATELY_SHARED = new Set(["siteName", "searchPlaceholder"]);

/**
 * TypeScript already guarantees every key exists in every dictionary. What it cannot catch
 * is a key that was copied from English and never actually translated, which is the failure
 * mode that quietly ships a half-Spanish page.
 */
describe("translation completeness", () => {
  it("has the same key set in both languages", () => {
    expect(Object.keys(es).sort()).toEqual(Object.keys(en).sort());
  });

  it("has no user-facing string left identical to the English", () => {
    const untranslated = Object.entries(en)
      .filter(([key, value]) => typeof value === "string" && value === (es as never)[key])
      .filter(([key]) => !DELIBERATELY_SHARED.has(key))
      .map(([key]) => key);

    expect(untranslated).toEqual([]);
  });

  it("keeps the shared-string exceptions to the documented few", () => {
    // Guards the exception list itself: it should stay a short, justified set rather than
    // becoming somewhere to park anything that fails the test above.
    expect(DELIBERATELY_SHARED.size).toBeLessThanOrEqual(3);
  });

  it("keeps interpolating strings as functions in both languages", () => {
    for (const [key, value] of Object.entries(en)) {
      if (typeof value === "function") {
        expect(typeof (es as never)[key]).toBe("function");
      }
    }
  });

  it("produces different output from interpolating functions", () => {
    expect(en.resultsCount(5, 10)).not.toBe(es.resultsCount(5, 10));
    expect(en.weeks(12)).not.toBe(es.weeks(12));
  });

  it("keeps numbers intact through interpolation", () => {
    expect(es.resultsCount(1234, 5678)).toContain("1,234");
    expect(es.weeks(30)).toContain("30");
  });
});

describe("language routing", () => {
  it("recognizes supported languages only", () => {
    expect(isLang("en")).toBe(true);
    expect(isLang("es")).toBe(true);
    expect(isLang("fr")).toBe(false);
    expect(isLang("")).toBe(false);
  });

  it("maps each language to the other for the toggle", () => {
    expect(OTHER_LANG.en).toBe("es");
    expect(OTHER_LANG.es).toBe("en");
  });

  it("covers every language in the toggle map", () => {
    for (const lang of LANGUAGES) {
      expect(OTHER_LANG[lang]).toBeDefined();
      expect(OTHER_LANG[lang]).not.toBe(lang);
    }
  });
});

describe("the non-affiliation notice", () => {
  it("exists in every language", () => {
    // The site wears California's official design system. Every visitor, in every
    // language, must be told it is not a state website.
    for (const lang of LANGUAGES) {
      expect(dict(lang).notAffiliated.length).toBeGreaterThan(20);
    }
  });

  it("names California in both languages so the denial is unambiguous", () => {
    expect(en.notAffiliated).toMatch(/California/);
    expect(es.notAffiliated).toMatch(/California/);
  });
});

/**
 * Provider categories arrive from the federal feed rather than from this project, so they
 * are not covered by the completeness test above. They still reach a Spanish reader, on the
 * one page whose whole subject is a breakdown by category, so they need their own guard.
 */
describe("entityTypeLabel", () => {
  /** Every category present in California's record, as the feed spells it. */
  const FILED = [
    "Public",
    "Private For-Profit",
    "Private Non-Profit",
    "Higher Ed: Associate's Degree",
    "Higher Ed: Baccalaureate or Higher",
    "Higher Ed: Certificate of Completion",
    "National Apprenticeship",
    "Other",
  ];

  it("returns the category as filed on an English page", () => {
    for (const filed of FILED) {
      expect(entityTypeLabel("en", filed)).toEqual({ text: filed, translated: true });
    }
  });

  it("translates every category California actually files", () => {
    for (const filed of FILED) {
      const label = entityTypeLabel("es", filed);
      expect(label.translated).toBe(true);
      expect(label.text).not.toBe(filed);
    }
  });

  it("falls back to the filed English, and says so, for a category it has never seen", () => {
    // Inventing a Spanish name for a federal classification nobody has read would be worse
    // than showing the one the record carries. `translated: false` is what lets the page
    // mark that fallback as English rather than leave it inside `lang="es"`.
    expect(entityTypeLabel("es", "Tribal Entity")).toEqual({
      text: "Tribal Entity",
      translated: false,
    });
  });
});

describe("feedTextLang", () => {
  it("marks feed text as English only on a Spanish page", () => {
    expect(feedTextLang("es")).toBe("en");
  });

  it("emits no attribute on an English page, where it would be redundant", () => {
    expect(feedTextLang("en")).toBeUndefined();
  });
});
