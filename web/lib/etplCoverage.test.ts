import { describe, expect, it } from "vitest";

import {
  COHORT_BANDS,
  HEADLINE_MEASURES,
  MEASURE_KEYS,
  MIN_RATE_DENOMINATOR,
  PROVIDER_FILED_MEASURES,
  WAGE_MATCH_MEASURES,
  UNSTATED_ENTITY_TYPE,
  coverageByCohortSize,
  coverageByEntityType,
  entityTypeOf,
  etplCoverageReport,
  filedACohort,
  headlineCoverage,
  measureCoverage,
  measureState,
  mostlySilentCategories,
  providerSilence,
  reportingRouteSplit,
  share,
} from "./etplCoverage";
import type { Program, ProgramOutcomes } from "./types";

function outcomes(overrides: Partial<ProgramOutcomes> = {}): ProgramOutcomes {
  return {
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
    ...overrides,
  };
}

function program(overrides: Partial<Program> = {}): Program {
  return {
    uuid: "id",
    provider_name: "Fresno City College",
    program_name: "Program",
    description: null,
    program_format: null,
    program_url: null,
    provider_link: null,
    entity_type: "Public",
    cip_code: null,
    soc_codes: [],
    location: { city: "Fresno", state: "CA", zip: null, lat: null, lon: null },
    region: null,
    length: { weeks: null, hours: null },
    cost: {
      tuition: null,
      supplies: null,
      total_out_of_pocket: null,
      total_is_complete: false,
      wioa_funded_cost: null,
    },
    outcomes: outcomes(),
    occupations: [],
    ...overrides,
  };
}

/** `n` copies of a program, each with a distinct uuid so nothing collapses by identity. */
function many(n: number, overrides: Partial<Program> = {}): Program[] {
  return Array.from({ length: n }, (_, i) => program({ uuid: `id-${i}`, ...overrides }));
}

describe("share", () => {
  it("computes a share once the denominator can carry one", () => {
    expect(share(15, 60)).toBe(0.25);
  });

  it("withholds a share the denominator is too small to support", () => {
    // Not zero, and not a rounded-off percentage either: at n below the floor a single
    // record moves the answer by more than the reader can safely read.
    expect(share(1, MIN_RATE_DENOMINATOR - 1)).toBeNull();
  });

  it("withholds rather than dividing by nothing", () => {
    // 0/0 is not 0%. An empty band was never measured.
    expect(share(0, 0)).toBeNull();
  });

  it("publishes a genuine zero share when the denominator supports it", () => {
    // Nobody missing out of 100 is a real and important finding, not a missing one.
    expect(share(0, 100)).toBe(0);
  });
});

describe("filedACohort", () => {
  it("is true when any of the three counts is present", () => {
    expect(filedACohort(outcomes({ total_served: 40 }))).toBe(true);
    expect(filedACohort(outcomes({ total_exited: 40 }))).toBe(true);
    expect(filedACohort(outcomes({ total_completed: 40 }))).toBe(true);
  });

  it("treats a reported zero cohort as a filing", () => {
    // "We served nobody" is a statement. It is not the absence of one.
    expect(filedACohort(outcomes({ total_served: 0 }))).toBe(true);
  });

  it("is false when the record describes no cohort at all", () => {
    expect(filedACohort(outcomes())).toBe(false);
  });
});

describe("measureState", () => {
  it("calls a present measure reported", () => {
    expect(measureState(outcomes({ completion_rate: 0.8 }), "completion_rate")).toBe("reported");
  });

  it("calls a reported zero reported, not missing", () => {
    // 0% employed is a devastating fact about a program, not a blank cell.
    expect(measureState(outcomes({ employment_rate_q2: 0 }), "employment_rate_q2")).toBe(
      "reported",
    );
  });

  it("separates an empty cell on a filed record from a record with nothing on it", () => {
    const withCohort = outcomes({ total_exited: 40 });
    expect(measureState(withCohort, "median_earnings")).toBe("blank");
    expect(measureState(outcomes(), "median_earnings")).toBe("unfiled");
  });
});

describe("measureCoverage", () => {
  it("splits a corpus into the three states and never loses a program", () => {
    const programs = [
      ...many(40, { outcomes: outcomes({ total_exited: 50, median_earnings: 9000 }) }),
      ...many(35, { outcomes: outcomes({ total_exited: 50 }) }),
      ...many(25, { outcomes: outcomes() }),
    ];

    const coverage = measureCoverage(programs, "median_earnings");
    expect(coverage.programs).toBe(100);
    expect(coverage.reported).toBe(40);
    expect(coverage.blank).toBe(35);
    expect(coverage.unfiled).toBe(25);
    expect(coverage.reported + coverage.blank + coverage.unfiled).toBe(coverage.programs);
    expect(coverage.missingShare).toBe(0.6);
  });

  it("covers every measure the pipeline ingests", () => {
    // Guards against a measure being added to the feed's parse and quietly left off this
    // page, which would understate the gap by exactly the measure nobody thought about.
    const programs = many(MIN_RATE_DENOMINATOR);
    for (const key of MEASURE_KEYS) {
      expect(measureCoverage(programs, key).missingShare).toBe(1);
    }
  });
});

describe("headlineCoverage", () => {
  it("counts a program reporting any one headline measure as reporting", () => {
    const programs = [
      program({ uuid: "a", outcomes: outcomes({ completion_rate: 0.9 }) }),
      program({ uuid: "b", outcomes: outcomes({ employment_rate_q2: 0.5 }) }),
      program({ uuid: "c", outcomes: outcomes({ median_earnings: 8000 }) }),
    ];
    expect(headlineCoverage(programs).reporting).toBe(3);
    expect(headlineCoverage(programs).silent).toBe(0);
  });

  it("separates silence with a filed cohort from silence with no record at all", () => {
    const programs = [
      ...many(10, { outcomes: outcomes({ total_served: 80 }) }),
      ...many(20, { outcomes: outcomes() }),
    ];
    const headline = headlineCoverage(programs);
    expect(headline.silent).toBe(30);
    expect(headline.silentWithACohort).toBe(10);
    expect(headline.silentWithNoRecord).toBe(20);
    expect(headline.silentShare).toBe(1);
  });

  it("reads the measures rather than the record's own reported flag", () => {
    // The flag and the measures are written by the same pipeline pass today. If they ever
    // part company, this page must agree with its own per-measure table.
    const programs = many(MIN_RATE_DENOMINATOR, {
      outcomes: outcomes({ reported: true }),
    });
    expect(headlineCoverage(programs).reporting).toBe(0);
  });

  it("uses exactly the three headline measures", () => {
    expect([...HEADLINE_MEASURES]).toEqual([
      "completion_rate",
      "employment_rate_q2",
      "median_earnings",
    ]);
  });
});

describe("coverageByEntityType", () => {
  it("groups on the category as filed and orders by size", () => {
    const programs = [
      ...many(5, { entity_type: "National Apprenticeship" }),
      ...many(9, { entity_type: "Public", outcomes: outcomes({ completion_rate: 0.7 }) }),
      ...many(2, { entity_type: "Other" }),
    ];

    const rows = coverageByEntityType(programs);
    expect(rows.map((r) => r.entityType)).toEqual(["Public", "National Apprenticeship", "Other"]);
    expect(rows[0]?.reporting).toBe(9);
    expect(rows[0]?.reportedByMeasure.completion_rate).toBe(9);
    expect(rows[1]?.silent).toBe(5);
  });

  it("withholds a category's share until the category is big enough to carry one", () => {
    const rows = coverageByEntityType(many(4, { entity_type: "Other" }));
    expect(rows[0]?.silent).toBe(4);
    expect(rows[0]?.silentShare).toBeNull();
  });

  it("keeps a program whose filer stated no category rather than dropping it", () => {
    // Dropping it would shrink the denominator of the whole page to hide one awkward row.
    const rows = coverageByEntityType([program({ entity_type: null })]);
    expect(rows).toHaveLength(1);
    expect(rows[0]?.entityType).toBe(UNSTATED_ENTITY_TYPE);
    expect(entityTypeOf(program({ entity_type: null }))).toBe(UNSTATED_ENTITY_TYPE);
  });

  it("orders ties by name so a rebuild does not reshuffle the table", () => {
    const rows = coverageByEntityType([
      program({ uuid: "a", entity_type: "Public" }),
      program({ uuid: "b", entity_type: "Other" }),
    ]);
    expect(rows.map((r) => r.entityType)).toEqual(["Other", "Public"]);
  });
});

describe("reportingRouteSplit", () => {
  /** A corpus where the provider's own counts are filled in and the wage match is not. */
  function split(providerReported: number, wageReported: number) {
    const programs = [
      ...many(providerReported, {
        outcomes: outcomes({
          total_served: 60,
          total_exited: 60,
          total_completed: 50,
          completion_rate: 0.8,
          credentials_earned: 40,
        }),
      }),
      ...many(wageReported, {
        outcomes: outcomes({
          total_served: 60,
          total_exited: 60,
          total_completed: 50,
          completion_rate: 0.8,
          credentials_earned: 40,
          employed_q2: 30,
          employment_rate_q2: 0.5,
          employed_q4: 28,
          median_earnings: 9000,
        }),
      }),
    ];
    return reportingRouteSplit(MEASURE_KEYS.map((key) => measureCoverage(programs, key)));
  }

  it("names the weakest provider-supplied measure and the strongest wage-match one", () => {
    const routes = split(40, 20);
    expect(routes.providerFloor?.reported).toBe(60);
    expect(routes.wageMatchCeiling?.reported).toBe(20);
    expect(routes.separated).toBe(true);
  });

  it("refuses to claim a separation the data does not show", () => {
    // Every measure filled in on every record: the groups overlap exactly, so the page must
    // print nothing rather than a sentence about a pattern that is not there.
    const routes = split(0, 40);
    expect(routes.separated).toBe(false);
  });

  it("does not claim a separation when the two groups merely touch", () => {
    // Strictly greater, not greater-or-equal. Equal coverage is not a divide.
    const programs = many(40, {
      outcomes: outcomes({
        total_served: 60,
        total_exited: 60,
        total_completed: 50,
        completion_rate: 0.8,
        credentials_earned: 40,
        employed_q2: 30,
        employment_rate_q2: 0.5,
        employed_q4: 28,
        median_earnings: 9000,
      }),
    });
    const routes = reportingRouteSplit(MEASURE_KEYS.map((key) => measureCoverage(programs, key)));
    expect(routes.providerFloor?.reported).toBe(routes.wageMatchCeiling?.reported);
    expect(routes.separated).toBe(false);
  });

  it("says nothing at all when handed no measures", () => {
    expect(reportingRouteSplit([])).toEqual({
      providerFloor: null,
      wageMatchCeiling: null,
      separated: false,
    });
  });

  it("assigns every ingested measure to exactly one route", () => {
    // A measure added to the feed and to neither group would silently vanish from this
    // comparison, which would make the separation look cleaner than it is.
    const assigned = [...PROVIDER_FILED_MEASURES, ...WAGE_MATCH_MEASURES];
    expect([...assigned].sort()).toEqual([...MEASURE_KEYS].sort());
    expect(new Set(assigned).size).toBe(MEASURE_KEYS.length);
  });
});

describe("mostlySilentCategories", () => {
  it("names the categories leaving the most rows empty, most first", () => {
    const rows = coverageByEntityType([
      ...many(40, { entity_type: "National Apprenticeship" }),
      ...many(40, { entity_type: "Public", outcomes: outcomes({ completion_rate: 0.7 }) }),
      ...many(40, {
        entity_type: "Higher Ed: Associate's Degree",
        outcomes: outcomes({ completion_rate: 0.7 }),
      }).map((p, i) => (i < 20 ? { ...p, outcomes: outcomes() } : p)),
    ]);

    expect(mostlySilentCategories(rows, 2).map((r) => r.entityType)).toEqual([
      "National Apprenticeship",
      "Higher Ed: Associate's Degree",
    ]);
  });

  it("will not put a category at the top on a denominator too small to rank it", () => {
    // Three silent programs out of four is not a finding about a category, and the page
    // that names the top of this list explains it in the next sentence.
    const rows = coverageByEntityType([
      ...many(4, { entity_type: "Other" }),
      ...many(40, { entity_type: "Public", outcomes: outcomes({ completion_rate: 0.7 }) }),
    ]);
    expect(mostlySilentCategories(rows, 2).map((r) => r.entityType)).toEqual(["Public"]);
  });

  it("returns nothing when no category is large enough to carry a share", () => {
    expect(mostlySilentCategories(coverageByEntityType(many(4)), 2)).toEqual([]);
  });
});

describe("coverageByCohortSize", () => {
  it("places a program in the band its exiter count falls in, upper bound inclusive", () => {
    const programs = [
      program({ uuid: "a", outcomes: outcomes({ total_exited: 10 }) }),
      program({ uuid: "b", outcomes: outcomes({ total_exited: 11 }) }),
      program({ uuid: "c", outcomes: outcomes({ total_exited: 5000 }) }),
    ];
    const bands = coverageByCohortSize(programs);
    expect(bands[0]?.programs).toBe(1);
    expect(bands[1]?.programs).toBe(1);
    expect(bands.at(-1)?.programs).toBe(1);
  });

  it("leaves a program with no exiter count out of every band", () => {
    // An unstated cohort size is not a small cohort, and pooling it into the first band
    // would manufacture exactly the correlation this table is testing for.
    const bands = coverageByCohortSize(many(50, { outcomes: outcomes({ total_served: 40 }) }));
    expect(bands.every((band) => band.programs === 0)).toBe(true);
  });

  it("excludes a cohort that is not this program's own", () => {
    // A cohort filed against a whole institution lands in the largest band and describes a
    // population that is not one program.
    const shared = outcomes({
      total_exited: 9000,
      cohort: { ...outcomes().cohort, attributable: false },
    });
    const bands = coverageByCohortSize(many(40, { outcomes: shared }));
    expect(bands.at(-1)?.programs).toBe(0);
  });

  it("reports the blank count for a band too small to carry a share", () => {
    const bands = coverageByCohortSize(many(3, { outcomes: outcomes({ total_exited: 5 }) }));
    expect(bands[0]?.programs).toBe(3);
    expect(bands[0]?.missingCount.median_earnings).toBe(3);
    expect(bands[0]?.missingShare.median_earnings).toBeNull();
  });

  it("covers the exiter range without a gap between bands", () => {
    for (let i = 1; i < COHORT_BANDS.length; i += 1) {
      expect(COHORT_BANDS[i]?.lower).toBe((COHORT_BANDS[i - 1]?.upper ?? 0) + 1);
    }
    expect(COHORT_BANDS.at(-1)?.upper).toBeNull();
  });
});

describe("providerSilence", () => {
  it("counts a provider that published nothing for any of its programs", () => {
    const programs = [
      program({ uuid: "a", provider_name: "Silent Academy" }),
      program({ uuid: "b", provider_name: "Silent Academy" }),
      program({
        uuid: "c",
        provider_name: "Reporting College",
        outcomes: outcomes({ completion_rate: 0.6 }),
      }),
    ];
    const silence = providerSilence(programs);
    expect(silence.providers).toBe(2);
    expect(silence.silentProviders).toBe(1);
    expect(silence.programsAtSilentProviders).toBe(2);
  });

  it("merges a provider filing under two spellings of one name", () => {
    // Shouting is not a second organisation, and a provider must not be able to look like
    // two filers by holding down shift.
    const silence = providerSilence([
      program({ uuid: "a", provider_name: "PROCAREER  ACADEMY" }),
      program({ uuid: "b", provider_name: "Procareer Academy" }),
    ]);
    expect(silence.providers).toBe(1);
    expect(silence.silentProviders).toBe(1);
  });

  it("counts providers the same way the provider index does", () => {
    // The two pages are one click apart and both publish a count of California's training
    // providers. Keying this on anything but the index's own slug would put two different
    // answers to the same question on one site.
    const silence = providerSilence([
      program({ uuid: "a", provider_name: "Health & Safety Institute" }),
      program({ uuid: "b", provider_name: "Health and Safety Institute" }),
    ]);
    expect(silence.providers).toBe(1);
  });

  it("leaves an unnamed filer out rather than pooling it with another", () => {
    const silence = providerSilence([
      program({ uuid: "a", provider_name: null }),
      program({ uuid: "b", provider_name: "  " }),
      // A name with nothing sluggable in it is as anonymous as a missing one.
      program({ uuid: "c", provider_name: "!!!" }),
    ]);
    expect(silence.providers).toBe(0);
    expect(silence.silentProviders).toBe(0);
  });

  it("does not call a provider silent because one of its programs is", () => {
    const silence = providerSilence([
      program({ uuid: "a", provider_name: "Mixed College" }),
      program({
        uuid: "b",
        provider_name: "Mixed College",
        outcomes: outcomes({ median_earnings: 9000 }),
      }),
    ]);
    expect(silence.silentProviders).toBe(0);
  });
});

describe("etplCoverageReport", () => {
  it("reports every measure and reconciles the headline with the corpus", () => {
    const programs = [
      ...many(30, { outcomes: outcomes({ total_exited: 60, completion_rate: 0.8 }) }),
      ...many(30, { outcomes: outcomes({ total_exited: 60 }) }),
      ...many(40, { outcomes: outcomes() }),
    ];

    const report = etplCoverageReport(programs);
    expect(report.measures).toHaveLength(MEASURE_KEYS.length);
    expect(report.headline.programs).toBe(100);
    expect(report.headline.reporting).toBe(30);
    expect(report.headline.silent).toBe(70);
    expect(report.headline.silentWithACohort).toBe(30);
    expect(report.headline.silentWithNoRecord).toBe(40);

    const completion = report.measures.find((m) => m.key === "completion_rate");
    expect(completion?.reported).toBe(30);
    expect(completion?.blank).toBe(30);
    expect(completion?.unfiled).toBe(40);
  });

  it("survives an empty corpus without inventing a zero percent", () => {
    const report = etplCoverageReport([]);
    expect(report.headline.programs).toBe(0);
    expect(report.headline.silentShare).toBeNull();
    expect(report.byEntityType).toEqual([]);
    expect(report.measures.every((m) => m.missingShare === null)).toBe(true);
  });
});
