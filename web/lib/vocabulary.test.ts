import { describe, expect, it } from "vitest";

import { translateTerm } from "./vocabulary";

describe("translateTerm", () => {
  it("translates education levels into Spanish", () => {
    expect(translateTerm("Associate's degree", "es")).toBe("Título de asociado");
    expect(translateTerm("High school diploma or equivalent", "es")).toBe(
      "Diploma de preparatoria o equivalente",
    );
  });

  it("translates experience and training vocabularies", () => {
    expect(translateTerm("Less than 5 years", "es")).toBe("Menos de 5 años");
    expect(translateTerm("Apprenticeship", "es")).toBe("Aprendizaje");
  });

  it("translates the literal 'None' the feeds use for no requirement", () => {
    expect(translateTerm("None", "es")).toBe("Ninguno");
    expect(translateTerm("none", "es")).toBe("Ninguno");
    expect(translateTerm("None", "en")).toBe("None");
  });

  it("passes English through unchanged", () => {
    expect(translateTerm("Bachelor's degree", "en")).toBe("Bachelor's degree");
  });

  it("falls back to the source text for unknown values", () => {
    // Showing untranslated English beats showing nothing, and keeps the gap visible.
    expect(translateTerm("Some future category", "es")).toBe("Some future category");
  });

  it("treats null and blank as absent", () => {
    expect(translateTerm(null, "es")).toBeNull();
    expect(translateTerm("   ", "es")).toBeNull();
  });

  it("covers every education value present in the source data", () => {
    const observed = [
      "No formal educational credential",
      "High school diploma or equivalent",
      "Some college, no degree",
      "Postsecondary non-degree award",
      "Associate's degree",
      "Bachelor's degree",
      "Master's degree",
      "Doctoral or professional degree",
      "None",
    ];
    for (const value of observed) {
      expect(translateTerm(value, "es")).not.toBe(value);
    }
  });
});
