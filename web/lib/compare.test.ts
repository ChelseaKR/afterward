import { describe, expect, it } from "vitest";

import {
  bestOf,
  completionMark,
  isOwnCohort,
  lengthBand,
  occupationFigures,
  oneLengthBand,
  ownCohortOnly,
  programRecordUrl,
} from "./compare";
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

describe("lengthBand", () => {
  it("places a program by the caps the length filter already uses", () => {
    expect([1, 4, 5, 12, 13, 26, 27, 52, 53, 260].map(lengthBand)).toEqual([
      0, 0, 1, 1, 2, 2, 3, 3, 4, 4,
    ]);
  });

  it("gives no band to a program that never said how long it takes", () => {
    // 12 of California's 3,266. A program with no length is not a short program.
    expect(lengthBand(null)).toBeNull();
    expect(lengthBand(undefined as unknown as number)).toBeNull();
    expect(lengthBand(Number.NaN)).toBeNull();
  });
});

describe("oneLengthBand", () => {
  it("accepts programs on the same scale and rejects programs on different ones", () => {
    expect(oneLengthBand([entry({ w: 13 }), entry({ w: 26 })])).toBe(true);
    expect(oneLengthBand([entry({ w: 26 }), entry({ w: 27 })])).toBe(false);
    expect(oneLengthBand([entry({ w: 4 }), entry({ w: 4 }), entry({ w: 60 })])).toBe(false);
  });

  it("refuses when any program's length was never established", () => {
    expect(oneLengthBand([entry({ w: 20 }), entry({ w: null })])).toBe(false);
  });
});

/**
 * Completion is the row length decides. Measured on the shipped index over the 1,947 programs
 * reporting both a completion rate and a length whose figures describe that program alone, the
 * median share who finished is 97% at four weeks or less, 91% at 5-12, 85% at 13-26, 80% at
 * 27-52 and 78% beyond a year. Marking a winner across those lengths marks the shorter course.
 */
describe("completionMark", () => {
  it("marks the strongest rate when the programs are the same length", () => {
    const entries = [entry({ cr: 0.7, w: 14 }), entry({ cr: 0.9, w: 24 })];
    expect(completionMark(entries)).toEqual({ best: 1, withheldForLength: false });
  });

  it("marks nothing when the programs are not the same length, and says length is why", () => {
    // The real pair: Elite Permanent Makeup & Cosmetology College's three-week course at 81%
    // and Cosmetica Beauty and Barbering Academy's 60-week Cosmetology at 80%, both training
    // for Hairdressers, Hairstylists, and Cosmetologists. The three-week course finishes 16
    // points below the median for its length; the 60-week course finishes 2 points above it.
    // The table used to mark the three-week course.
    const entries = [entry({ cr: 0.81, w: 3 }), entry({ cr: 0.8, w: 60 })];
    expect(completionMark(entries)).toEqual({ best: null, withheldForLength: true });
  });

  it("blames length only when length is what took the mark away", () => {
    // Nobody reported, so there was never a mark. Explaining an absence length did not cause
    // would tell a reader the programs were disqualified when they simply filed nothing.
    const unreported = [entry({ cr: null, w: 3 }), entry({ cr: null, w: 60 })];
    expect(completionMark(unreported)).toEqual({ best: null, withheldForLength: false });

    // Same for a tie and for a single reporting program: `bestOf`'s own rules got there first.
    const tied = [entry({ cr: 0.9, w: 3 }), entry({ cr: 0.9, w: 60 })];
    expect(completionMark(tied)).toEqual({ best: null, withheldForLength: false });

    const alone = [entry({ cr: 0.9, w: 3 }), entry({ cr: null, w: 60 })];
    expect(completionMark(alone)).toEqual({ best: null, withheldForLength: false });
  });

  it("ignores the length of a program that could not have won anyway", () => {
    // The 60-week program filed a whole institution's cohort, so `ownCohortOnly` already took
    // it out of the ranking. Letting its length veto the two that remain would withhold a mark
    // on account of a program that was never in the running.
    const entries = [
      entry({ cr: 0.95, w: 60, at: false }),
      entry({ cr: 0.7, w: 14, at: true }),
      entry({ cr: 0.9, w: 24, at: true }),
    ];
    expect(completionMark(entries)).toEqual({ best: 2, withheldForLength: false });
  });

  it("withholds when a compared program never reported a length", () => {
    // Unestablished, not near enough — the same reading a missing cohort flag gets.
    const entries = [entry({ cr: 0.9, w: null }), entry({ cr: 0.7, w: 20 })];
    expect(completionMark(entries)).toEqual({ best: null, withheldForLength: true });
  });

  it("still refuses a program whose cohort is not its own, whatever the lengths", () => {
    const entries = [
      entry({ cr: 0.99, w: 20, at: false }),
      entry({ cr: 0.8, w: 20, at: true }),
      entry({ cr: 0.7, w: 24, at: true }),
    ];
    expect(completionMark(entries)).toEqual({ best: 1, withheldForLength: false });
  });
});

/**
 * The length rule stops at completion on purpose. Measured the same way, employment inverts on
 * 1.27% of same-band pairs against 4.53% across bands and earnings on 2.89% against 5.85% —
 * under half of completion's 2.63%/10.22% — and neither is directional: their band medians do
 * not fall with length, and the marked program is the shorter one 53.2% and 46.2% of the time,
 * either side of chance. Withholding those marks would remove a working signal.
 */
describe("length does not disqualify the rows it does not confound", () => {
  it("still marks employment and earnings across different lengths", () => {
    const entries = [entry({ er: 0.6, me: 9000, w: 3 }), entry({ er: 0.8, me: 21000, w: 60 })];
    expect(bestOf(entries, ownCohortOnly((e) => e.er), "high")).toBe(1);
    expect(bestOf(entries, ownCohortOnly((e) => e.me), "high")).toBe(1);
  });

  it("still marks cost and length, which are properties of the course", () => {
    // What a course costs and how long it runs are not claims about a cohort, so nothing about
    // whose cohort was filed or how the lengths differ makes them incomparable.
    const entries = [entry({ $: 9000, w: 3, at: false }), entry({ $: 4000, w: 60, at: true })];
    expect(bestOf(entries, (e) => e.$, "low")).toBe(1);
    expect(bestOf(entries, (e) => e.w, "low")).toBe(0);
  });
});
