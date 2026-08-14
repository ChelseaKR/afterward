import { describe, expect, it } from "vitest";

import {
  SEVERITIES,
  findingRows,
  gapRows,
  getCtdlCoverage,
  getCtdlValidation,
  hasUnacceptedFindings,
  measureRows,
  propertyRows,
  severityCounts,
  snapshotAgreement,
  type CtdlValidation,
} from "./ctdl";

/**
 * The published statements, read the way the page reads them.
 *
 * These are committed files rather than fixtures, deliberately: they are the exact bytes the
 * page renders and the exact bytes the site serves, so a test against anything else would be
 * testing a copy of the thing that matters.
 */
const coverage = getCtdlCoverage();
const validation = getCtdlValidation();

function withFindings(overrides: Partial<CtdlValidation>): CtdlValidation {
  return { ...validation, ...overrides };
}

/**
 * One real finding summary, to build hypothetical ones from.
 *
 * Taken from the published statement rather than invented so the shapes under test stay the
 * shapes the export actually writes. If the export ever stops returning any finding at all,
 * this throws rather than silently testing nothing.
 */
const [sampleFinding] = Object.values(validation.codes);
if (sampleFinding === undefined) {
  throw new Error("the published validation statement carries no findings to build on");
}

describe("the published statements", () => {
  it("describe the same snapshot as each other", () => {
    expect(validation.snapshot_date).toBe(coverage.snapshot_date);
  });

  it("say plainly that nothing reached the Credential Registry", () => {
    expect(coverage.note).toContain("not published to any registry");
    expect(validation.note).toContain("Credential Registry");
  });

  it("name the validator and the version that produced the findings", () => {
    expect(validation.tool.name).toBe("ctdl-validate");
    expect(validation.tool.version).toMatch(/^\d+\.\d+/);
  });
});

describe("severityCounts", () => {
  it("returns every severity, including the ones that did not occur", () => {
    // The zeroes are the finding. A table listing only what happened cannot be read as "no
    // errors", only as "no errors are mentioned".
    expect(severityCounts(validation).map((row) => row.severity)).toEqual([...SEVERITIES]);
  });

  it("reads a missing severity as zero rather than dropping the row", () => {
    const counts = severityCounts(withFindings({ findings: { WARNING: 2 } }));
    expect(counts).toEqual([
      { severity: "ERROR", count: 0 },
      { severity: "WARNING", count: 2 },
      { severity: "INFO", count: 0 },
      { severity: "UNVERIFIABLE", count: 0 },
    ]);
  });
});

describe("findingRows", () => {
  it("puts the worst severity first", () => {
    const rows = findingRows(
      withFindings({
        codes: {
          B_WARNING: { ...sampleFinding, severity: "WARNING" },
          A_ERROR: { ...sampleFinding, severity: "ERROR" },
        },
      }),
    );
    expect(rows.map((row) => row.code)).toEqual(["A_ERROR", "B_WARNING"]);
  });

  it("carries the cited rule alongside the count", () => {
    // A number on its own asks the reader to take this project's word for what the rule was.
    for (const row of findingRows(validation)) {
      expect(row.rule.url).toMatch(/^https?:\/\//);
      expect(row.rule.citation.length).toBeGreaterThan(20);
    }
  });
});

describe("hasUnacceptedFindings", () => {
  it("is false for the statement actually published", () => {
    expect(hasUnacceptedFindings(validation)).toBe(false);
  });

  it("is true when anything errored", () => {
    expect(hasUnacceptedFindings(withFindings({ findings: { ERROR: 1 } }))).toBe(true);
  });

  it("is true when a finding code was never reasoned about", () => {
    expect(
      hasUnacceptedFindings(
        withFindings({ codes: { SOMETHING_NEW: { ...sampleFinding, accepted: false } } }),
      ),
    ).toBe(true);
  });
});

describe("propertyRows", () => {
  it("keeps the export's own order rather than sorting by completeness", () => {
    // Ordering a coverage table by how well each row does turns a measurement into a
    // scoreboard. Same rule the provider table on /outcomes-coverage/ follows.
    expect(propertyRows(coverage).map((row) => row.term)).toEqual(
      Object.keys(coverage.learning_program_properties),
    );
  });

  it("shares are against the exported programs and never exceed one", () => {
    for (const row of propertyRows(coverage)) {
      expect(row.share).not.toBeNull();
      expect(row.share!).toBeGreaterThan(0);
      expect(row.share!).toBeLessThanOrEqual(1);
    }
  });

  it("has no share to give when nothing was exported", () => {
    const empty = { ...coverage, entities: { ...coverage.entities, "ceterms:LearningProgram": 0 } };
    expect(propertyRows(empty).every((row) => row.share === null)).toBe(true);
  });
});

describe("measureRows", () => {
  it("divides by the programs that have an outcome profile, not by every program", () => {
    // A measure missing because a program reported nothing is a different fact from a
    // measure missing from a program that reported something else. Dividing by every
    // program blends the two into one misleadingly low number.
    const profiles = coverage.entities["qdata:DataSetProfile"] ?? 0;
    for (const row of measureRows(coverage)) {
      expect(row.share).toBeCloseTo(row.count / profiles, 10);
      expect(row.share!).toBeLessThanOrEqual(1);
    }
  });
});

describe("gapRows", () => {
  it("lists every dropped source field with a reason", () => {
    const rows = gapRows(coverage);
    expect(rows.length).toBeGreaterThan(0);
    for (const row of rows) {
      expect(row.reason.length).toBeGreaterThan(40);
      expect(row.fields.length).toBeGreaterThan(0);
    }
  });

  it("puts the gap affecting the most programs first", () => {
    const counts = gapRows(coverage).map((row) => row.reported_in_source);
    expect([...counts].sort((a, b) => b - a)).toEqual(counts);
  });

  it("names the CTDL term where the vocabulary has somewhere to put the field", () => {
    // The uncomfortable half of the coverage statement: a named term means the gap is in
    // this export rather than in CTDL, and the page has to be able to say which.
    const named = gapRows(coverage).filter((row) => row.ctdl_term !== "");
    expect(named.length).toBeGreaterThan(0);
  });

  it("never counts a per-field figure above the group total", () => {
    for (const row of gapRows(coverage)) {
      for (const field of row.fields) {
        expect(field.count).toBeLessThanOrEqual(row.reported_in_source);
      }
    }
  });
});

describe("snapshotAgreement", () => {
  it("agrees when the export describes the dataset the site is serving", () => {
    expect(snapshotAgreement("2026-08-07", "2026-08-07").agree).toBe(true);
  });

  it("disagrees, and says which is which, when they have drifted apart", () => {
    const result = snapshotAgreement("2026-08-07", "2026-09-01");
    expect(result.agree).toBe(false);
    expect(result.exportSnapshot).toBe("2026-08-07");
    expect(result.siteSnapshot).toBe("2026-09-01");
  });
});
