import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { afterAll, describe, expect, it } from "vitest";

import { isPerLanguage, routeTemplates } from "@/scripts/routes.mjs";

import { LANGUAGES } from "../lib/i18n";

/**
 * Proof that `scripts/seo-audit.mjs` can fail, one deliberate defect at a time.
 *
 * A gate over 9,046 pages that has never been seen to go red is a gate nobody can distinguish
 * from a `main()` that returns 0. This repository has met that shape before -- an accessibility
 * job whose skips read as passes, a link check on a host that cannot 404 -- so the audit is
 * run here against synthetic exports built to be wrong in one specific way each, and the
 * assertion is that each one is rejected and that the reason names the page.
 *
 * The intact fixture is asserted to pass first. Without it, every case below would be
 * satisfied by a script that exits 1 on everything, which is the other way a gate proves
 * nothing.
 *
 * ---- Why the fixture is generated from the real route list ----
 *
 * `seo-audit.mjs` refuses an export that is missing any route the app router declares, and it
 * reads that list from `app/` itself. A fixture with a hand-written set of pages would either
 * fail every case for the wrong reason or force the audit to take an `--app-dir` flag that
 * nothing in production would ever pass. So the fixture is built from `routeTemplates()`: add
 * a page to the site and these exports grow a page too, and the coverage check is exercised
 * by the same act.
 */

const SCRIPT = fileURLToPath(new URL("./seo-audit.mjs", import.meta.url));
const ORIGIN = "https://example.invalid";

/** Enough distinct records to clear the audit's own floor under a collapsed sweep. */
const DETAIL_INSTANCES = 20;

interface Entry {
  loc: string;
  alternates: Record<string, string>;
}

interface Page {
  /** Path inside the export, e.g. `en/programs/p0/index.html`. */
  file: string;
  canonical: string | null;
  alternates: Record<string, string>;
  noindex?: boolean;
}

interface Export {
  entries: Entry[];
  pages: Page[];
}

/** `/[lang]/programs/[id]` -> `programs/p0/`, with dynamic segments filled in. */
function restFor(template: string, instance: number): string {
  const segments = template
    .split("/")
    .filter(Boolean)
    .filter((segment) => segment !== "[lang]")
    .map((segment) => (segment.startsWith("[") ? `x${instance}` : segment));
  return segments.length === 0 ? "" : `${segments.join("/")}/`;
}

function alternatesFor(rest: string): Record<string, string> {
  return {
    ...Object.fromEntries(LANGUAGES.map((lang) => [lang, `${ORIGIN}/${lang}/${rest}`])),
    "x-default": `${ORIGIN}/en/${rest}`,
  };
}

/**
 * A correct export: every route the app router declares, in both languages, self-canonical,
 * with reciprocal alternates in the head and the same set in the sitemap.
 *
 * `about/` is built and indexable and deliberately absent from the sitemap, exactly as the
 * real site has it — so the "indexable, not in the sitemap, still has to name itself" rule is
 * exercised by the intact fixture rather than only by a mutation of it.
 */
function intact(): Export {
  const templates = routeTemplates().filter(isPerLanguage);
  /** A detail route: one with a dynamic segment other than the language. */
  const isDetail = (template: string) => template.replace("/[lang]", "").includes("[");
  const rests = templates.flatMap((template) =>
    isDetail(template)
      ? Array.from({ length: DETAIL_INSTANCES }, (_, i) => restFor(template, i))
      : [restFor(template, 0)],
  );

  const entries: Entry[] = [];
  const pages: Page[] = [];

  for (const rest of rests) {
    for (const lang of LANGUAGES) {
      const loc = `${ORIGIN}/${lang}/${rest}`;
      const alternates = alternatesFor(rest);
      pages.push({ file: `${lang}/${rest}index.html`, canonical: loc, alternates });
      if (rest !== "about/") entries.push({ loc, alternates });
    }
  }

  // The language chooser at `/`, which canonicalises to `/en/` and is in no sitemap, and the
  // 404, which is `noindex` and owes nobody a canonical.
  pages.push({ file: "index.html", canonical: `${ORIGIN}/en/`, alternates: {} });
  pages.push({ file: "404.html", canonical: null, alternates: {}, noindex: true });

  return { entries, pages };
}

function sitemapXml(entries: Entry[]): string {
  const urls = entries
    .map(({ loc, alternates }) => {
      const links = Object.entries(alternates)
        .map(([lang, href]) => `<xhtml:link rel="alternate" hreflang="${lang}" href="${href}" />`)
        .join("\n");
      return `<url>\n<loc>${loc}</loc>\n${links}\n</url>`;
    })
    .join("\n");
  return (
    '<?xml version="1.0" encoding="UTF-8"?>\n' +
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" ' +
    'xmlns:xhtml="http://www.w3.org/1999/xhtml">\n' +
    `${urls}\n</urlset>\n`
  );
}

function pageHtml(page: Page): string {
  const head = [
    page.noindex === true ? '<meta name="robots" content="noindex"/>' : "",
    page.canonical === null ? "" : `<link rel="canonical" href="${page.canonical}"/>`,
    ...Object.entries(page.alternates).map(
      // `hrefLang`, with the capital L React serialises, so the fixture is the shape the real
      // export has rather than the shape a matcher would find most convenient.
      ([lang, href]) => `<link rel="alternate" hrefLang="${lang}" href="${href}"/>`,
    ),
  ].join("");
  return `<!DOCTYPE html><html><head>${head}</head><body>page</body></html>`;
}

const roots: string[] = [];

/** Write one export to a fresh directory and return it. */
function write(model: Export): string {
  const root = mkdtempSync(join(tmpdir(), "afterward-seo-audit-"));
  roots.push(root);
  writeFileSync(join(root, "sitemap.xml"), sitemapXml(model.entries));
  for (const page of model.pages) {
    const path = join(root, page.file);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, pageHtml(page));
  }
  return root;
}

function audit(root: string): { code: number; output: string } {
  const run = spawnSync(process.execPath, [SCRIPT, root], { encoding: "utf-8" });
  return { code: run.status ?? -1, output: `${run.stdout}${run.stderr}` };
}

afterAll(() => {
  for (const root of roots) rmSync(root, { recursive: true, force: true });
});

describe("the intact export", () => {
  const { code, output } = audit(write(intact()));

  it("passes, so the failures below are about the defect and not about the fixture", () => {
    expect(output).toContain("self-canonical against the sitemap");
    expect(code).toBe(0);
  });

  it("was a real sweep and says how big it was", () => {
    expect(output).toMatch(/\d+ sitemap URLs over \d+ records/);
  });
});

/**
 * One defect each. `mutate` edits the correct model in place; `says` is the substring the
 * operator has to be able to read in the failure.
 */
const DEFECTS: ReadonlyArray<{
  what: string;
  mutate: (model: Export) => void;
  says: string;
}> = [
  {
    what: "a page with no canonical — the measured live defect, on 9,046 pages",
    mutate: (model) => {
      const page = model.pages.find((candidate) => candidate.file.startsWith("es/programs/"));
      if (page !== undefined) page.canonical = null;
    },
    says: "no <link rel=\"canonical\">",
  },
  {
    what: "a page whose canonical names a different URL",
    mutate: (model) => {
      const page = model.pages.find((candidate) => candidate.file.startsWith("es/programs/"));
      if (page !== undefined) page.canonical = `${ORIGIN}/en/`;
    },
    says: "sitemap says",
  },
  {
    what: "a page with no hreflang in its head — the other half of the live defect",
    mutate: (model) => {
      const page = model.pages.find((candidate) => candidate.file.startsWith("en/programs/"));
      if (page !== undefined) page.alternates = {};
    },
    says: "no <link rel=\"alternate\" hreflang>",
  },
  {
    what: "a head missing x-default while the sitemap declares one",
    mutate: (model) => {
      const page = model.pages.find((candidate) => candidate.file.startsWith("en/programs/"));
      if (page !== undefined) {
        page.alternates = Object.fromEntries(
          Object.entries(page.alternates).filter(([lang]) => lang !== "x-default"),
        );
      }
    },
    says: "head declares hreflang",
  },
  {
    what: "a head whose hreflang href disagrees with the sitemap's",
    mutate: (model) => {
      const page = model.pages.find((candidate) => candidate.file.startsWith("en/programs/"));
      if (page !== undefined) page.alternates = { ...page.alternates, es: `${ORIGIN}/es/` };
    },
    says: "head says hreflang",
  },
  {
    what: "a one-way sitemap alternate, which search engines discard in silence",
    mutate: (model) => {
      const entry = model.entries.find(({ loc }) => loc.includes("/en/programs/"));
      if (entry !== undefined) entry.alternates = { ...entry.alternates, es: `${ORIGIN}/es/` };
    },
    says: "does not name it back",
  },
  {
    what: "a sitemap entry that leaves itself out of its own alternate set",
    mutate: (model) => {
      const entry = model.entries.find(({ loc }) => loc.includes("/es/programs/"));
      if (entry !== undefined) {
        entry.alternates = Object.fromEntries(
          Object.entries(entry.alternates).filter(([lang]) => lang !== "es"),
        );
      }
    },
    says: "does not name it",
  },
  {
    what: "a URL advertised to crawlers that the export never built",
    mutate: (model) => {
      model.pages = model.pages.filter((page) => !page.file.startsWith("es/programs/x0/"));
    },
    says: "was never built",
  },
  {
    what: "an indexable page outside the sitemap that names no URL",
    mutate: (model) => {
      const page = model.pages.find((candidate) => candidate.file === "en/about/index.html");
      if (page !== undefined) page.canonical = null;
    },
    says: "has to say which URL it is",
  },
  {
    what: "a relative canonical, which a reader resolves against itself",
    mutate: (model) => {
      const page = model.pages.find((candidate) => candidate.file === "index.html");
      if (page !== undefined) page.canonical = "/en/";
    },
    says: "is relative",
  },
  {
    what: "a route the app router declares and the export is missing entirely",
    mutate: (model) => {
      model.pages = model.pages.filter((page) => !page.file.startsWith("es/ctdl/"));
      model.entries = model.entries.filter(({ loc }) => !loc.includes("/es/ctdl/"));
    },
    says: "missing pages the app router declares",
  },
  {
    what: "a sweep that collapsed to a handful of records",
    mutate: (model) => {
      const kept = new Set(model.entries.slice(0, 4).map(({ loc }) => loc));
      model.entries = model.entries.filter(({ loc }) => kept.has(loc));
    },
    says: "the sweep collapsed",
  },
];

describe.each(DEFECTS)("$what", ({ mutate, says }) => {
  const model = intact();
  mutate(model);
  const { code, output } = audit(write(model));

  it("is rejected", () => {
    expect(code).not.toBe(0);
  });

  it("is rejected for this reason, named where an operator will read it", () => {
    expect(output).toContain(says);
  });
});
