import { describe, expect, it } from "vitest";

import { bestOf, isOwnCohort, occupationFigures, ownCohortOnly, programRecordUrl } from "./compare";
import type { Program, ProgramOccupation, SearchEntry } from "./types";

function entry(overrides: Partial<SearchEntry> = {}): SearchEntry {
  return {
    i: "id",
    n: "Program",
    p: "Provider",
    c: "Fresno",
    a: "Fresno MSA",
    $: 4000,
    $partial: false,
    at: true,
    w: 30,
    s: [],
    o: ["Occupation"],
    g: 10,
    wage: 45000,
    op: 500,
    cr: 0.8,
    er: 0.7,
    me: 32000,
    r: true,
    ...overrides,
  };
}

/**
 * The comparison highlights the strongest reported figure in each row. Getting this wrong
 * would recommend a training program to someone on the strength of a number nobody filed.
 */
describe("bestOf", () => {
  it("picks the highest when higher is better", () => {
    const entries = [entry({ me: 20000 }), entry({ me: 50000 }), entry({ me: 30000 })];
    expect(bestOf(entries, (e) => e.me, "high")).toBe(1);
  });

  it("picks the lowest when lower is better", () => {
    const entries = [entry({ $: 9000 }), entry({ $: 1000 }), entry({ $: 5000 })];
    expect(bestOf(entries, (e) => e.$, "low")).toBe(1);
  });

  it("ignores unreported values rather than treating them as zero", () => {
    // A null cost is not free, and a null salary is not $0.
    const entries = [entry({ $: null }), entry({ $: 5000 }), entry({ $: 3000 })];
    expect(bestOf(entries, (e) => e.$, "low")).toBe(2);

    const earnings = [entry({ me: null }), entry({ me: 10000 }), entry({ me: 20000 })];
    expect(bestOf(earnings, (e) => e.me, "high")).toBe(2);
  });

  it("marks nothing when only one program reported the measure", () => {
    // Being the only provider willing to file a number is not the same as being the best,
    // and highlighting it would reward disclosure as if it were performance.
    const entries = [entry({ me: 50000 }), entry({ me: null }), entry({ me: null })];
    expect(bestOf(entries, (e) => e.me, "high")).toBeNull();
  });

  it("marks nothing when no program reported the measure", () => {
    const entries = [entry({ me: null }), entry({ me: null })];
    expect(bestOf(entries, (e) => e.me, "high")).toBeNull();
  });

  it("marks nothing on a tie", () => {
    const entries = [entry({ $: 5000 }), entry({ $: 5000 }), entry({ $: 9000 })];
    expect(bestOf(entries, (e) => e.$, "low")).toBeNull();
  });

  it("treats a reported zero as a real value", () => {
    // 0% employed is a devastating fact, not a missing one, and must be able to lose.
    const entries = [entry({ er: 0 }), entry({ er: 0.5 })];
    expect(bestOf(entries, (e) => e.er, "high")).toBe(1);

    // And a genuine $0 cost is the cheapest, not an absence.
    const free = [entry({ $: 0 }), entry({ $: 5000 })];
    expect(bestOf(free, (e) => e.$, "low")).toBe(0);
  });

  it("handles negative growth correctly when higher is better", () => {
    const entries = [entry({ g: -15 }), entry({ g: -2 }), entry({ g: null })];
    expect(bestOf(entries, (e) => e.g, "high")).toBe(1);
  });
});

function occupation(overrides: Partial<ProgramOccupation> = {}): ProgramOccupation {
  return {
    soc_code: "29-1141",
    title: "Registered Nurses",
    median_annual_wage: 137690,
    total_job_openings: 25110,
    percent_change: 7.2,
    entry_level_education: "Bachelor's degree",
    region: null,
    match: { kind: "exact", program_soc_codes: ["29-1141"], entry_level_education_withheld: false },
    ...overrides,
  };
}

function program(occupations: ProgramOccupation[]): Program {
  return {
    uuid: "id",
    provider_name: "Provider",
    program_name: "Program",
    description: null,
    program_format: null,
    program_url: null,
    provider_link: null,
    entity_type: null,
    cip_code: null,
    soc_codes: [],
    location: { city: "Bakersfield", state: "CA", zip: null, lat: null, lon: null },
    region: null,
    length: { weeks: 30, hours: null },
    cost: {
      tuition: null,
      supplies: null,
      total_out_of_pocket: null,
      total_is_complete: true,
      wioa_funded_cost: null,
    },
    outcomes: {
      total_served: null,
      total_exited: null,
      total_completed: null,
      completion_rate: null,
      credentials_earned: null,
      median_earnings: null,
      employment_rate_q2: null,
      employed_q2: null,
      employed_q4: null,
      reported: false,
      cohort: {
        attributable: true,
        internally_consistent: true,
        shared_with_sibling_programs: null,
        exited_exceeds_served: false,
        completed_exceeds_served: false,
        oversized_for_one_program: false,
      },
    },
    occupations,
  };
}

/**
 * The comparison used to take a program's pay from the highest-paying job it feeds and its
 * projected change from the weakest-growing one, then print them in the same column. These
 * tests pin the shape that makes that recombination unrepresentable: one row per occupation,
 * each carrying only its own figures.
 */
describe("occupationFigures", () => {
  it("keeps each job's figures with that job rather than picking extremes across them", () => {
    // The real KERN HIGH SCHOOL DISTRICT-ROP "Sports Medicine" record: $289,473 and +5.0%
    // are different jobs, and the old table printed them as one program's profile.
    const rows = occupationFigures(
      program([
        occupation({
          soc_code: "29-1229",
          title: "Physicians, All Other",
          median_annual_wage: 289473,
          percent_change: 9.5,
          total_job_openings: 9800,
        }),
        occupation({
          soc_code: "29-9091",
          title: "Athletic Trainers",
          median_annual_wage: 80687,
          percent_change: 5.0,
          total_job_openings: 1290,
        }),
      ]),
    );

    expect(rows).toEqual([
      {
        title: "Physicians, All Other",
        socCode: "29-1229",
        wage: 289473,
        change: 9.5,
        openings: 9800,
      },
      { title: "Athletic Trainers", socCode: "29-9091", wage: 80687, change: 5.0, openings: 1290 },
    ]);

    // The pairing the old table produced — the highest wage beside the lowest change — is
    // not any row here, which is the whole point.
    expect(rows.some((row) => row.wage === 289473 && row.change === 5.0)).toBe(false);
  });

  it("preserves unreported figures as null rather than zero", () => {
    const rows = occupationFigures(
      program([
        occupation({ median_annual_wage: null, percent_change: null, total_job_openings: null }),
      ]),
    );
    expect(rows).toEqual([
      { title: "Registered Nurses", socCode: "29-1141", wage: null, change: null, openings: null },
    ]);
  });

  it("keeps a job California publishes nothing about, rather than shortening the list", () => {
    const rows = occupationFigures(
      program([
        occupation({ soc_code: "11-1011", title: "Chief Executives" }),
        occupation({
          soc_code: null,
          title: null,
          median_annual_wage: null,
          percent_change: null,
          total_job_openings: null,
        }),
      ]),
    );
    expect(rows).toHaveLength(2);
    expect(rows[1]).toEqual({
      title: null,
      socCode: null,
      wage: null,
      change: null,
      openings: null,
    });
  });

  it("returns nothing for a program matched to no occupation", () => {
    expect(occupationFigures(program([]))).toEqual([]);
  });
});

describe("programRecordUrl", () => {
  it("points at the published record from the site root", () => {
    expect(programRecordUrl("f6900f55-31e5-11f1-ba03-00155dd2f085")).toBe(
      "/data/programs/f6900f55-31e5-11f1-ba03-00155dd2f085.json",
    );
  });

  it("encodes the id so it cannot escape the directory", () => {
    expect(programRecordUrl("../coverage")).toBe("/data/programs/..%2Fcoverage.json");
  });
});

/**
 * 103 programs carry outcome figures their provider filed against a whole institution or a
 * group of sibling courses. The numbers are real, so they stay on screen — but a comparison
 * built from them claims the two columns describe one course each, and they do not.
 */
describe("ownCohortOnly", () => {
  it("stops a program that filed an institution's figures from winning a row", () => {
    const entries = [
      entry({ cr: 0.95, at: false }),
      entry({ cr: 0.8, at: true }),
      entry({ cr: 0.7, at: true }),
    ];
    expect(bestOf(entries, ownCohortOnly((e) => e.cr), "high")).toBe(1);
  });

  it("marks nothing when only one comparable program is left", () => {
    // Same rule as a measure only one program reported: with a single candidate there is
    // no comparison to win.
    const entries = [entry({ cr: 0.95, at: false }), entry({ cr: 0.8, at: true })];
    expect(bestOf(entries, ownCohortOnly((e) => e.cr), "high")).toBeNull();
  });

  it("leaves attributable programs comparable exactly as before", () => {
    const entries = [entry({ me: 20000 }), entry({ me: 50000 }), entry({ me: 30000 })];
    expect(bestOf(entries, ownCohortOnly((e) => e.me), "high")).toBe(1);
  });

  it("withholds rather than zeroes, so a suppressed figure cannot lose either", () => {
    // Read directly: the wrapper must hand `bestOf` a null, not a 0 that would win a
    // lowest-cost row or lose a highest-earnings one.
    expect(ownCohortOnly((e) => e.cr)(entry({ cr: 0.95, at: false }))).toBeNull();
    expect(ownCohortOnly((e) => e.cr)(entry({ cr: 0, at: true }))).toBe(0);
  });

  it("treats an index with no attributability field as unestablished, not as fine", () => {
    const stale = { ...entry(), at: undefined } as unknown as SearchEntry;
    expect(isOwnCohort(stale)).toBe(false);
    expect(ownCohortOnly((e) => e.cr)(stale)).toBeNull();
  });
});
