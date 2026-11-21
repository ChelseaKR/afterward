import { describe, expect, it } from "vitest";

import { llmsTxt } from "./llms";

/**
 * The owner-approved draft (2026-11-21, D4 A), byte for byte, with the figures it was drafted
 * with. Any change to the wording has to change this test, which is the point: the copy was
 * approved as written.
 */
const APPROVED = `# Afterward

> Afterward lists 3,266 California training programs reported under the federal Workforce Innovation and Opportunity Act (WIOA): each program's cost, length and the outcomes it reported (completion, employment six months after, earnings), next to California's ten-year projection for the occupation it leads to. It is an independent project, not a California state website. English and Spanish.

What a blank means: a program that reported no outcome is shown as having reported nothing. A blank is not a zero and not a bad result.

Data date: the program and outcome records in this build are dated 2026-09-18.

How to cite: name Afterward, link the program page, and credit the U.S. Department of Labor (Eligible Training Provider scorecard, ETA-9171) and the California Employment Development Department (long-term occupational projections), with the data date shown on the page.

## Pages

- Program pages: https://afterward.chelseakr.com/en/programs/<id>/, one per program
- [Occupations](https://afterward.chelseakr.com/en/occupations/): pay, job outlook and the programs that train for each
- [Providers](https://afterward.chelseakr.com/en/providers/)
- [Paying for training](https://afterward.chelseakr.com/en/paying-for-training/)
- [How complete the outcomes data is](https://afterward.chelseakr.com/en/outcomes-coverage/)
- [Spanish](https://afterward.chelseakr.com/es/)
- [Sitemap](https://afterward.chelseakr.com/sitemap.xml)
`;

describe("llms.txt", () => {
  it("is the approved draft, word for word, with the build's figures", () => {
    expect(
      llmsTxt({ site: "https://afterward.chelseakr.com", programs: 3266, dataDate: "2026-09-18" }),
    ).toBe(APPROVED);
  });

  it("takes the count, the date and the host from the build", () => {
    const text = llmsTxt({ site: "https://example.invalid", programs: 60, dataDate: "2026-01-02" });
    expect(text).toContain("Afterward lists 60 California training programs");
    expect(text).toContain("are dated 2026-01-02.");
    expect(text).not.toContain("afterward.chelseakr.com");
  });
});
