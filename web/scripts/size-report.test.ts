import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

/**
 * The first-visit budget is the only thing in the build that can fail over page weight, and
 * it is the reader's bill rather than ours: this site is for people deciding whether to spend
 * a year and several thousand dollars on training, and a fair share of them arrive on a
 * phone, on a metered connection, or on library wifi.
 *
 * It measured a hand-written list of routes and treated a route it could not find as a line
 * of output rather than a failure — `(not built)`, then on to the next one. So an export
 * missing pages reported every remaining route inside budget and exited 0, and a route added
 * to `app/` was never in the list to begin with: two of the site's twelve templates, the
 * provider detail page and `/ctdl/`, had no budget on them at all when this was written.
 *
 * That is the same defect the accessibility audit fixed one file over, and these tests are
 * its counterpart: a sample has to be stated, and then checked against both the build and the
 * app, or it is not a sample.
 */
const REPORT = fileURLToPath(new URL("./size-report.mjs", import.meta.url));

/** The pages `ROUTES` names, as paths relative to an export root. */
const PAGES = [
  "index.html",
  "404.html",
  "en/index.html",
  "en/about/index.html",
  "en/ctdl/index.html",
  "en/occupations/index.html",
  "en/occupations/00-0000/index.html",
  "en/outcomes-coverage/index.html",
  "en/paying-for-training/index.html",
  "en/programs/some-program/index.html",
  "en/providers/index.html",
  "en/providers/some-provider/index.html",
];

const CHUNK = "/_next/static/chunks/main-0123456789abcdef.js";

function buildExport({ omit = [], html = "" }: { omit?: string[]; html?: string } = {}): string {
  const root = mkdtempSync(join(tmpdir(), "size-report-"));
  for (const page of PAGES) {
    if (omit.includes(page)) continue;
    const file = join(root, page);
    mkdirSync(join(file, ".."), { recursive: true });
    writeFileSync(file, `<!doctype html><html lang="en"><body>${html}</body></html>`);
  }
  return root;
}

/** An app router tree: this repository's routes, plus whatever `extra` names. */
function buildApp(extra: string[] = []): string {
  const root = mkdtempSync(join(tmpdir(), "size-report-app-"));
  const routes = [
    "page.tsx",
    "not-found.tsx",
    "[lang]/page.tsx",
    "[lang]/about/page.tsx",
    "[lang]/ctdl/page.tsx",
    "[lang]/occupations/page.tsx",
    "[lang]/occupations/[soc]/page.tsx",
    "[lang]/outcomes-coverage/page.tsx",
    "[lang]/paying-for-training/page.tsx",
    "[lang]/programs/[id]/page.tsx",
    "[lang]/providers/page.tsx",
    "[lang]/providers/[slug]/page.tsx",
    ...extra,
  ];
  for (const route of routes) {
    const file = join(root, route);
    mkdirSync(join(file, ".."), { recursive: true });
    writeFileSync(file, "export default function Page() { return null; }\n");
  }
  return root;
}

function run(root: string, appDir?: string) {
  return spawnSync(process.execPath, [REPORT, root], {
    encoding: "utf-8",
    env: appDir === undefined ? process.env : { ...process.env, SIZE_REPORT_APP_DIR: appDir },
  });
}

describe("a route the budget did not weigh is unmeasured, not within budget", () => {
  it("fails when a page in the list is not in the export", () => {
    const result = run(buildExport({ omit: ["en/ctdl/index.html"] }));
    expect(result.status).toBe(1);
    expect(result.stdout).toContain("NOT BUILT");
    expect(result.stderr).toContain("/en/ctdl/");
  });

  it("fails when a whole page kind is missing rather than weighing the rest", () => {
    const result = run(
      buildExport({
        omit: ["en/providers/index.html", "en/providers/some-provider/index.html"],
      }),
    );
    expect(result.status).toBe(1);
    expect(result.stderr).toContain("/en/providers/<slug>/");
  });

  it("fails when the app declares a route no entry measures", () => {
    const result = run(buildExport(), buildApp(["[lang]/scholarships/page.tsx"]));
    expect(result.status).toBe(1);
    expect(result.stderr).toContain("/[lang]/scholarships");
    expect(result.stderr).toContain("no entry in ROUTES measures it");
  });

  it("fails on an asset the page names and the export does not contain", () => {
    // Weighing a missing chunk as zero made the one broken build the lightest one measured.
    const result = run(buildExport({ html: `<script src="${CHUNK}"></script>` }));
    expect(result.status).toBe(1);
    expect(result.stderr).toContain(CHUNK);
    expect(result.stderr).toContain("not in");
  });

  it("passes a complete export of exactly the routes the app declares", () => {
    // The other half: a gate that cannot pass is switched off as fast as one that cannot fail.
    const result = run(buildExport(), buildApp());
    expect(result.status).toBe(0);
    expect(result.stdout).toContain("/en/providers/<slug>/");
  });

  it("reads this repository's own app when nothing overrides it", () => {
    const result = run(buildExport());
    expect(result.status).toBe(0);
  });
});
