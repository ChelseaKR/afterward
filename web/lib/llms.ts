/**
 * The site's llms.txt: a plain-text summary for AI assistants, served at `/llms.txt`.
 *
 * Nearly every engaged visit to Afterward arrives from an assistant (22 of 23 in the 28 days
 * to 2026-11-21), on a single program page, and the site had no llms.txt. The wording is the
 * owner-approved draft of 2026-11-21 (option D4 A), word for word; `llms.test.ts` holds it to
 * that draft. Only the program count, the data date and the host come from the build, so the
 * file cannot drift from the pages it describes. The date is the same snapshot date every
 * page's footer prints, which is the "data date shown on the page" the citation line names.
 */

export interface LlmsFacts {
  /** The site's origin with no trailing slash, as `SITE_URL` gives it. */
  site: string;
  /** How many programs this build lists. */
  programs: number;
  /** The dataset's snapshot date, as the footer prints it. */
  dataDate: string;
}

export function llmsTxt({ site, programs, dataDate }: LlmsFacts): string {
  const count = new Intl.NumberFormat("en-US").format(programs);
  return [
    "# Afterward",
    "",
    `> Afterward lists ${count} California training programs reported under the federal Workforce Innovation and Opportunity Act (WIOA): each program's cost, length and the outcomes it reported (completion, employment six months after, earnings), next to California's ten-year projection for the occupation it leads to. It is an independent project, not a California state website. English and Spanish.`,
    "",
    "What a blank means: a program that reported no outcome is shown as having reported nothing. A blank is not a zero and not a bad result.",
    "",
    `Data date: the program and outcome records in this build are dated ${dataDate}.`,
    "",
    "How to cite: name Afterward, link the program page, and credit the U.S. Department of Labor (Eligible Training Provider scorecard, ETA-9171) and the California Employment Development Department (long-term occupational projections), with the data date shown on the page.",
    "",
    "## Pages",
    "",
    `- Program pages: ${site}/en/programs/<id>/, one per program`,
    `- [Occupations](${site}/en/occupations/): pay, job outlook and the programs that train for each`,
    `- [Providers](${site}/en/providers/)`,
    `- [Paying for training](${site}/en/paying-for-training/)`,
    `- [How complete the outcomes data is](${site}/en/outcomes-coverage/)`,
    `- [Spanish](${site}/es/)`,
    `- [Sitemap](${site}/sitemap.xml)`,
    "",
  ].join("\n");
}
