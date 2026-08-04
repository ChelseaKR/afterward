import { describe, expect, it } from "vitest";

import { LANGUAGES, OTHER_LANG, dict, isLang } from "./i18n";

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
