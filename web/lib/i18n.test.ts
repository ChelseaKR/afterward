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

/**
 * Why a program has no region.
 *
 * Until the county placement rule landed (#126, #129) there was one sentence for every
 * unplaced program and it said the program's *city* is not one California names. That was
 * the whole truth while placement went by principal city alone. It is now the reason for
 * none of them: a program reaching this panel is one whose ZIP could not be resolved to a
 * single published area, and its city has nothing to do with it.
 *
 * These bind each of the pipeline's five refusals to its own sentence, and bind the
 * unrecognised case to a sentence that names no cause. `tests/test_site_copy.py` holds the
 * vocabulary itself to `afterward.build.AREA_UNPLACED_REASONS`, so a sixth reason added in
 * Python cannot quietly fall through to the default branch here.
 */
describe("the stated reason a program has no region", () => {
  /** Exactly `afterward.build.AREA_UNPLACED_REASONS`. */
  const REASONS = [
    "crosswalk_not_read",
    "no_zip",
    "zip_not_in_crosswalk",
    "county_outside_areas",
    "straddles_areas",
  ];

  for (const lang of LANGUAGES) {
    const d = dict(lang);

    it(`gives each refusal its own sentence in ${lang}`, () => {
      const said = REASONS.map((reason) => d.regionUnplacedBody("Truckee", reason));
      expect(new Set(said).size).toBe(REASONS.length);
      for (const sentence of said) expect(sentence.length).toBeGreaterThan(40);
    });

    it(`names no cause at all for a reason it does not recognise, in ${lang}`, () => {
      // A record built before `region_unplaced_reason` existed carries no key. Reading that
      // as any particular reason would publish a specific cause nobody measured, which is
      // the failure this whole panel exists to avoid.
      const absent = d.regionUnplacedBody("Truckee", undefined);
      const unknown = d.regionUnplacedBody("Truckee", "some_reason_from_a_later_build");
      expect(absent).toBe(unknown);
      for (const reason of REASONS) {
        expect(d.regionUnplacedBody("Truckee", reason)).not.toBe(absent);
      }
    });

    it(`does not blame the city where the city is not the reason, in ${lang}`, () => {
      // `straddles_areas` and `county_outside_areas` are findings about the ZIP. Naming the
      // city in them would restore the old sentence's error one program at a time.
      for (const reason of ["straddles_areas", "county_outside_areas", "crosswalk_not_read"]) {
        expect(d.regionUnplacedBody("Truckee", reason)).not.toContain("Truckee");
      }
    });

    it(`still reads without a city, in ${lang}`, () => {
      for (const reason of [...REASONS, undefined]) {
        const sentence = d.regionUnplacedBody(null, reason);
        expect(sentence).not.toContain("null");
        expect(sentence.length).toBeGreaterThan(40);
      }
    });
  }

  it("says something different in each language for every reason", () => {
    for (const reason of [...REASONS, undefined]) {
      expect(en.regionUnplacedBody("Truckee", reason)).not.toBe(
        es.regionUnplacedBody("Truckee", reason),
      );
    }
  });

  /**
   * The old copy said "About half of California's programs are in this position" / "Cerca de
   * la mitad". On the same snapshot it is now 165 of 3,266 — five per cent. A proportion
   * written into a string is a number nothing rechecks, so the fix is not to write the new
   * one: the counts a reader sees come from the dataset, and no string states a share.
   */
  it("states no proportion of the dataset in copy", () => {
    const copy = [
      ...["crosswalk_not_read", "no_zip", "zip_not_in_crosswalk", "county_outside_areas", "straddles_areas", undefined].flatMap(
        (reason) => LANGUAGES.map((lang) => dict(lang).regionUnplacedBody("Truckee", reason)),
      ),
      ...LANGUAGES.map((lang) => dict(lang).unplacedBody),
      ...LANGUAGES.map((lang) => dict(lang).areaNote(165, 3266)),
      ...LANGUAGES.map((lang) => dict(lang).statUnplaced(165, 3266)),
    ];
    for (const sentence of copy) {
      expect(sentence).not.toMatch(/\bhalf\b|\bmitad\b|\bmost of\b|\bmayor[íi]a\b|%/i);
    }
  });
});
