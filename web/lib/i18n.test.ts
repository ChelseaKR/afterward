import { describe, expect, it } from "vitest";

import { LANGUAGES, OTHER_LANG, dict, isLang } from "./i18n";

const en = dict("en");
const es = dict("es");

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
      // Proper nouns are the same in both languages and are the only legitimate exception.
      .filter(([key]) => key !== "siteName")
      .map(([key]) => key);

    expect(untranslated).toEqual([]);
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
  it("recognises supported languages only", () => {
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
