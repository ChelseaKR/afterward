import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { afterAll, describe, expect, it } from "vitest";

/**
 * What `scripts/lastmod.mjs` writes, and what it refuses to write.
 *
 * The property this file exists to hold is one sentence: **a build cannot stamp today's date
 * on a page that did not change.** Every fixture below is built so that "stamp the build date
 * on everything" and "stamp the build date on what moved" would give different answers, which
 * is the only way to tell them apart — on a first run, with no history, the two are identical
 * and both look correct. So the central case hands the script a ledger dated `2026-05-01` and
 * a build date of `2026-09-13` over bytes that have not changed, and requires `2026-05-01` in
 * the output. The defect this replaces would print `2026-09-13`, on all 9,046 URLs, and pass
 * any check that only asked whether a date was present.
 *
 * The refusals matter as much. Several of them are the same shape as the defect they guard:
 * a previous ledger that could not be read must be a failure and never an empty one, because
 * "no ledger" is a real state with real behaviour — it dates nothing — and a fetch that half
 * worked arriving as that state would silently re-date the whole site and say so nowhere.
 *
 * The fixtures are synthetic exports rather than a real `npm run build`, deliberately: a build
 * takes minutes, and what is under test here is the dating rule, not Next. The one thing that
 * does depend on the real build — that two builds of an unchanged tree produce identical pages
 * once the build id is normalised away — is a measurement, recorded in the script's own
 * docblock, and it is what makes digesting the whole document legitimate.
 */

const SCRIPT = fileURLToPath(new URL("./lastmod.mjs", import.meta.url));
const ORIGIN = "https://example.invalid";
const BUILD_ID = "aBuildIdOf21Chars0000";
const OLD_BUILD_ID = "anOlderBuildId0000000";

/** Distinct pages, enough that a rule applying to one of them is visible against the rest. */
const PATHS = [
  "en/",
  "es/",
  "en/programs/a/",
  "es/programs/a/",
  "en/programs/b/",
  "es/programs/b/",
  "en/occupations/29-1141/",
  "es/occupations/29-1141/",
];

interface Fixture {
  /** The directory holding `out/` and `.next/`, which is what the script is pointed inside. */
  root: string;
  out: string;
  previous: string;
}

const roots: string[] = [];

/** `en/programs/a/` -> the body the fixture writes for it, which varies per page. */
function body(path: string, mark: string, buildId: string): string {
  return (
    `<!DOCTYPE html><html><head><title>${path}</title></head>` +
    `<body><p>${path}${mark}</p>` +
    `<script>self.__next_f.push([1,"{\\"b\\":\\"${buildId}\\"}"])</script>` +
    "</body></html>"
  );
}

function sitemapXml(paths: readonly string[], dates: Record<string, string> = {}): string {
  const urls = paths
    .map((path) => {
      const loc = `${ORIGIN}/${path}`;
      const date = dates[path];
      const lastmod = date === undefined ? "" : `\n<lastmod>${date}</lastmod>`;
      return `<url>\n<loc>${loc}</loc>${lastmod}\n<changefreq>yearly</changefreq>\n</url>`;
    })
    .join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset>\n${urls}\n</urlset>\n`;
}

/** A fresh export on disk: `.next/BUILD_ID`, a sitemap, and one page per path. */
function fixture(
  options: {
    paths?: readonly string[];
    marks?: Record<string, string>;
    dates?: Record<string, string>;
    /** Paths present in the sitemap but not written to disk. */
    unbuilt?: readonly string[];
    buildId?: string;
  } = {},
): Fixture {
  const paths = options.paths ?? PATHS;
  const buildId = options.buildId ?? BUILD_ID;
  const root = mkdtempSync(join(tmpdir(), "afterward-lastmod-"));
  roots.push(root);

  mkdirSync(join(root, ".next"), { recursive: true });
  writeFileSync(join(root, ".next", "BUILD_ID"), `${buildId}\n`);

  const out = join(root, "out");
  mkdirSync(out, { recursive: true });
  writeFileSync(join(out, "sitemap.xml"), sitemapXml(paths, options.dates ?? {}));

  for (const path of paths) {
    if (options.unbuilt?.includes(path) === true) continue;
    const file = join(out, path, "index.html");
    mkdirSync(dirname(file), { recursive: true });
    writeFileSync(file, body(path, options.marks?.[path] ?? "", buildId));
  }

  return { root, out, previous: join(root, "previous.json") };
}

/**
 * A ledger as the last deploy would have published it.
 *
 * The digests are computed by running the script over the fixture once, so they are the
 * script's own — a hand-written digest would make every case a test of the test's arithmetic.
 */
function ledgerFor(f: Fixture, date: string, marks: Record<string, string> = {}): string {
  const built = fixture({ paths: PATHS, marks, buildId: OLD_BUILD_ID });
  run(built.out, []);
  const written = JSON.parse(readFileSync(join(built.out, "lastmod.json"), "utf-8")) as {
    version: number;
    buildId: string;
    pages: Record<string, { digest: string; lastmod: string | null }>;
  };
  for (const entry of Object.values(written.pages)) entry.lastmod = date;
  writeFileSync(f.previous, JSON.stringify(written));
  return f.previous;
}

function run(out: string, args: readonly string[]): { code: number; output: string } {
  const result = spawnSync(process.execPath, [SCRIPT, out, ...args], { encoding: "utf-8" });
  return { code: result.status ?? -1, output: `${result.stdout}${result.stderr}` };
}

/** Every `<lastmod>` the sitemap now carries, by URL path. */
function datesIn(out: string): Record<string, string> {
  const xml = readFileSync(join(out, "sitemap.xml"), "utf-8");
  const dates: Record<string, string> = {};
  for (const match of xml.matchAll(/<url>([\s\S]*?)<\/url>/g)) {
    const block = match[1] ?? "";
    const loc = block.match(/<loc>([^<]+)<\/loc>/)?.[1];
    const date = block.match(/<lastmod>([^<]+)<\/lastmod>/)?.[1];
    if (loc !== undefined && date !== undefined) dates[loc.slice(ORIGIN.length + 1)] = date;
  }
  return dates;
}

afterAll(() => {
  for (const root of roots) rmSync(root, { recursive: true, force: true });
});

describe("a first run, with nothing to compare against", () => {
  const f = fixture();
  const { code, output } = run(f.out, ["--date", "2026-09-13"]);

  it("succeeds", () => {
    expect(code).toBe(0);
  });

  it("dates nothing at all, rather than dating everything today", () => {
    // The whole defect in one assertion. A build with no history knows when no page last
    // changed, and the honest output is an absent field.
    expect(datesIn(f.out)).toEqual({});
    expect(output).toContain("no previous ledger");
  });

  it("still records every page's digest, so the next run can date what moved", () => {
    const ledger = JSON.parse(readFileSync(join(f.out, "lastmod.json"), "utf-8")) as {
      pages: Record<string, { digest: string; lastmod: string | null }>;
    };
    expect(Object.keys(ledger.pages)).toHaveLength(PATHS.length);
    for (const entry of Object.values(ledger.pages)) {
      expect(entry.digest).toMatch(/^[0-9a-f]{16}$/);
      expect(entry.lastmod).toBeNull();
    }
  });
});

describe("a run over pages that have not changed", () => {
  const f = fixture();
  const previous = ledgerFor(f, "2026-05-01");
  const { code, output } = run(f.out, ["--previous", previous, "--date", "2026-09-13"]);

  it("succeeds", () => {
    expect(code).toBe(0);
  });

  it("keeps the date each page last changed, four months before this build", () => {
    // The fixture whose content date differs from its build date. `2026-09-13` appearing on
    // any of these would be the defect this replaces: a freshness claim derived from the
    // build rather than from the content.
    const dates = datesIn(f.out);
    expect(Object.keys(dates).sort()).toEqual([...PATHS].sort());
    for (const path of PATHS) expect(dates[path], path).toBe("2026-05-01");
    expect(output).toContain("0 changed in this build");
  });
});

describe("a run over one page that changed", () => {
  const f = fixture({ marks: { "es/programs/a/": " — a sentence was rewritten" } });
  const previous = ledgerFor(f, "2026-05-01");
  const { code } = run(f.out, ["--previous", previous, "--date", "2026-09-13"]);

  it("dates that page today and leaves every other page where it was", () => {
    expect(code).toBe(0);
    const dates = datesIn(f.out);
    expect(dates["es/programs/a/"]).toBe("2026-09-13");
    for (const path of PATHS) {
      if (path !== "es/programs/a/") expect(dates[path], path).toBe("2026-05-01");
    }
  });
});

describe("a URL the previous ledger has never seen", () => {
  const f = fixture({ paths: [...PATHS, "en/programs/new/"] });
  const previous = ledgerFor(f, "2026-05-01");
  const { code } = run(f.out, ["--previous", previous, "--date", "2026-09-13"]);

  it("is dated this build, because this build is when it first existed", () => {
    expect(code).toBe(0);
    expect(datesIn(f.out)["en/programs/new/"]).toBe("2026-09-13");
  });
});

describe("the check over a consistent export", () => {
  const f = fixture();
  const previous = ledgerFor(f, "2026-05-01");

  it("passes, so the refusals below are about the defect and not about the fixture", () => {
    expect(run(f.out, ["--previous", previous, "--date", "2026-09-13"]).code).toBe(0);
    const { code, output } = run(f.out, ["--check"]);
    expect(output).toContain("backed by a digest of the page the export is publishing");
    expect(code).toBe(0);
  });
});

/**
 * One refusal each. `set up` leaves the fixture in the state being refused, and `says` is the
 * sentence an operator has to be able to read in the failure.
 */
const REFUSALS: ReadonlyArray<{
  what: string;
  run: () => { code: number; output: string };
  says: string;
}> = [
  {
    what: "a page edited after it was dated, so the date describes bytes nobody serves",
    run: () => {
      const f = fixture();
      const previous = ledgerFor(f, "2026-05-01");
      run(f.out, ["--previous", previous, "--date", "2026-09-13"]);
      const file = join(f.out, "en/programs/a/index.html");
      writeFileSync(file, `${readFileSync(file, "utf-8")}<!-- edited -->`);
      return run(f.out, ["--check"]);
    },
    says: "content that no longer matches",
  },
  {
    what: "a sitemap that dates URLs with no ledger to say where the dates came from",
    run: () => {
      const f = fixture({ dates: { "en/": "2026-09-13" } });
      return run(f.out, ["--check"]);
    },
    says: "to say where those dates came from",
  },
  {
    what: "a sitemap whose date disagrees with the ledger's",
    run: () => {
      const f = fixture();
      const previous = ledgerFor(f, "2026-05-01");
      run(f.out, ["--previous", previous, "--date", "2026-09-13"]);
      const path = join(f.out, "sitemap.xml");
      writeFileSync(
        path,
        readFileSync(path, "utf-8").replace("<lastmod>2026-05-01</lastmod>", "<lastmod>2026-09-13</lastmod>"),
      );
      return run(f.out, ["--check"]);
    },
    says: "sitemap says 2026-09-13",
  },
  {
    what: "an export whose sitemap is already dated — the generator claiming again, or a second run",
    run: () => {
      const f = fixture({ dates: { "en/": "2026-09-12" } });
      return run(f.out, ["--date", "2026-09-13"]);
    },
    says: "already dates",
  },
  {
    what: "a previous ledger that could not be read, which must never arrive as `no ledger`",
    run: () => {
      const f = fixture();
      writeFileSync(f.previous, "{ this is not json");
      return run(f.out, ["--previous", f.previous, "--date", "2026-09-13"]);
    },
    says: "previous.json",
  },
  {
    what: "a previous ledger written in a format this build does not know",
    run: () => {
      const f = fixture();
      writeFileSync(f.previous, JSON.stringify({ version: 99, pages: {} }));
      return run(f.out, ["--previous", f.previous, "--date", "2026-09-13"]);
    },
    says: "ledger version 99",
  },
  {
    what: "a build id that appears in no page, so normalising it away changes nothing",
    run: () => {
      // The pages embed `BUILD_ID`; `.next/BUILD_ID` says something else, which is the shape
      // a renamed field or a changed Next release would produce.
      const f = fixture();
      writeFileSync(join(f.root, ".next", "BUILD_ID"), "aBuildIdNobodyEmitted\n");
      return run(f.out, ["--date", "2026-09-13"]);
    },
    says: "appears in none of the",
  },
  {
    what: "a URL advertised to crawlers that the export never built",
    run: () => {
      const f = fixture({ unbuilt: ["es/programs/b/"] });
      return run(f.out, ["--date", "2026-09-13"]);
    },
    says: "was never built",
  },
  {
    what: "a --date that is not a plain date",
    run: () => run(fixture().out, ["--date", "2026-09-13T00:00:00.000Z"]),
    says: "is not YYYY-MM-DD",
  },
  {
    what: "a sitemap with no URLs in it, which would otherwise pass over nothing",
    run: () => {
      const f = fixture({ paths: [] });
      return run(f.out, ["--date", "2026-09-13"]);
    },
    says: "nothing to date",
  },
  {
    what: "an export directory that is not there",
    run: () => run(join(tmpdir(), "afterward-lastmod-does-not-exist"), ["--date", "2026-09-13"]),
    says: "no export to date",
  },
];

describe.each(REFUSALS)("$what", ({ run: attempt, says }) => {
  const { code, output } = attempt();

  it("is refused", () => {
    expect(code).not.toBe(0);
  });

  it("is refused for this reason, named where an operator will read it", () => {
    expect(output).toContain(says);
  });
});
