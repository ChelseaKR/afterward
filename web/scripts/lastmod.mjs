/**
 * Dates the sitemap from the pages that actually changed, and refuses to date the rest.
 *
 * ---- What was published before this ----
 *
 * One date, `2026-09-12T00:00:00.000Z`, on all 9,046 URLs. It was not a build stamp --
 * `app/sitemap.ts` read `getCoverage().snapshot_date`, which is a real date belonging to a
 * real thing -- but the thing it belongs to is the dataset, not the page. So the claim was
 * wrong in both directions at once:
 *
 * - **It moved for pages that did not.** A program whose row is byte-identical to last
 *   month's still advertised itself as modified, because the corpus around it refreshed.
 * - **It did not move for pages that did.** The site deploys code separately from data: a
 *   copy change that rewrites a sentence on 165 program pages ships under whatever dataset
 *   is current, and every one of those pages went on claiming the older snapshot's date.
 *
 * `lastmod` is the one field in a sitemap that is a factual claim about the content. A claim
 * derived from something other than the content is the portfolio's dominant defect wearing a
 * crawler-facing coat, and the rule that came out of it is that an absent field is honest and
 * a wrong one is not.
 *
 * ---- What this derives it from instead ----
 *
 * The bytes. For every URL in the sitemap this reads the page the export actually wrote,
 * digests it, and compares that digest against the ledger published beside the last deploy:
 *
 * - **same digest** -- the page has not changed since that date, so it keeps it;
 * - **different digest, or a URL the ledger has never seen** -- the page changed in this
 *   build, so it gets this build's date, which is the date it changed;
 * - **no ledger at all** -- nothing here knows when this page last changed, so it publishes
 *   **no `lastmod`**, and says so. A first run therefore dates nothing and teaches the next
 *   run everything.
 *
 * That last rule is the one that matters. "Stamp today on everything" and "stamp today on
 * what changed" produce identical output on a first run and diverge completely afterwards,
 * and the difference is only visible if the absent case refuses to invent a date. A build
 * cannot stamp `now` on a page that did not change, because the only date it is allowed to
 * write is one it watched the bytes move on.
 *
 * ---- Why the digest ignores Next's build id, and nothing else ----
 *
 * Measured on this repository on 2026-09-13: two independent `npm run build` runs over an
 * unchanged tree produced 284 pages of which **284 differed**, and the whole of the
 * difference was one 21-character random build id inside the inline RSC payload. Normalise
 * that single literal away and **0 of 284 differ**. So the export is reproducible, the digest
 * can be taken over the entire document, and there is no judgement call about which parts of
 * a page count as "content": all of it does, including the chunk URLs, because a bundle change
 * is a change to what the reader is served.
 *
 * The build id is read from `.next/BUILD_ID` rather than pattern-matched, so the substitution
 * is a known literal rather than a guess. If it turns out to appear in no page at all, this
 * refuses: a normaliser that matches nothing would silently mark every page as changed on
 * every deploy, which is the original defect with extra steps.
 *
 * ---- Usage ----
 *
 *   node scripts/lastmod.mjs [outDir] [--previous <file>] [--date YYYY-MM-DD] [--check]
 *
 * `--previous` is the ledger published by the last deploy, which the site serves at
 * `/lastmod.json`. Omitted is the ordinary local and CI case: no ledger, no dates.
 * `--check` reads an export without writing anything and fails if any `<lastmod>` in the
 * sitemap is not backed by a ledger entry whose digest matches that page's bytes -- which is
 * the gate, and `scripts/lastmod.test.ts` proves it can fail.
 */

import { createHash } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

/** The ledger's own format, so a future change to what is recorded is a visible one. */
const LEDGER_VERSION = 1;

/** Published beside the site, and read back by the next deploy over plain HTTPS. */
export const LEDGER_FILE = "lastmod.json";

/**
 * Sixteen hex characters of SHA-256.
 *
 * Long enough that two different pages colliding is not a thing that happens -- over 9,046
 * pages the odds are about 1 in 4 x 10^14 -- and short enough that the ledger stays around
 * 800 KB rather than 1.3 MB for a file the site publishes on every deploy.
 */
const DIGEST_CHARS = 16;

function usage(message) {
  console.error(`lastmod: ${message}`);
  console.error(
    "usage: node scripts/lastmod.mjs [outDir] [--previous <file>] [--date YYYY-MM-DD] [--check]",
  );
  process.exit(1);
}

function parseArgs(argv) {
  const options = { out: null, previous: null, date: null, check: false };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--check") options.check = true;
    else if (arg === "--previous" || arg === "--date") {
      const value = argv[i + 1];
      if (value === undefined || value.startsWith("--")) usage(`${arg} needs a value`);
      options[arg === "--previous" ? "previous" : "date"] = value;
      i += 1;
    } else if (arg.startsWith("--")) usage(`unknown option ${arg}`);
    else if (options.out === null) options.out = arg;
    else usage(`unexpected argument ${arg}`);
  }
  options.out ??= "out";
  return options;
}

/** `https://host/en/x/` -> `en/x/index.html`, the file the export wrote it to. */
export function pageFor(loc, origin) {
  const path = loc.slice(origin.length).replace(/^\//, "");
  return `${path}${path.endsWith("/") || path === "" ? "" : "/"}index.html`;
}

/** Every `<url>` block, with its `<loc>` and whether it already carries a `<lastmod>`. */
export function sitemapUrls(xml) {
  const blocks = [...xml.matchAll(/<url>([\s\S]*?)<\/url>/g)];
  return blocks
    .map(([, block]) => ({
      loc: block.match(/<loc>([^<]+)<\/loc>/)?.[1] ?? null,
      lastmod: block.match(/<lastmod>([^<]+)<\/lastmod>/)?.[1] ?? null,
    }))
    .filter((entry) => entry.loc !== null);
}

/**
 * The digest of one page, with the build id normalised out.
 *
 * `buildId` is required rather than defaulted: a digest taken without it is a different
 * digest, and two callers disagreeing about that would make every page read as changed.
 */
export function digestOf(html, buildId) {
  const normalised = html.split(buildId).join("<build-id>");
  return createHash("sha256").update(normalised).digest("hex").slice(0, DIGEST_CHARS);
}

/** Today in UTC, as a plain date. The sitemaps protocol accepts a bare `YYYY-MM-DD`. */
function todayUtc() {
  return new Date().toISOString().slice(0, 10);
}

function readLedger(path) {
  let parsed;
  try {
    parsed = JSON.parse(readFileSync(path, "utf-8"));
  } catch (error) {
    // A ledger that was asked for and could not be read is a failure, never an empty one.
    // Falling back to "no previous ledger" here would turn a fetch that half-worked into a
    // sitemap that re-dates all 9,046 pages, and nothing would say so.
    console.error(`lastmod: ${path}: ${error instanceof Error ? error.message : error}`);
    process.exit(1);
  }
  if (parsed?.version !== LEDGER_VERSION) {
    console.error(
      `lastmod: ${path}: ledger version ${String(parsed?.version)}, this build writes ` +
        `${LEDGER_VERSION}. Refusing rather than guessing what the fields mean.`,
    );
    process.exit(1);
  }
  return parsed.pages ?? {};
}

/**
 * Put a `<lastmod>` immediately after each `<loc>`, and nowhere else.
 *
 * Textual rather than a re-serialisation, so every other byte of the document Next wrote is
 * untouched -- the deploy greps this file for an exact `<loc>` line, and the sitemap gate
 * parses it.
 */
export function withLastmod(xml, datesByLoc) {
  return xml.replace(/<url>([\s\S]*?)<\/url>/g, (block) => {
    const loc = block.match(/<loc>([^<]+)<\/loc>/)?.[1];
    const date = loc === undefined ? undefined : datesByLoc.get(loc);
    if (date === undefined || date === null) return block;
    return block.replace(/(<loc>[^<]+<\/loc>)/, `$1\n<lastmod>${date}</lastmod>`);
  });
}

function main() {
  const options = parseArgs(process.argv.slice(2));

  if (options.date !== null && !/^\d{4}-\d{2}-\d{2}$/.test(options.date)) {
    usage(`--date ${options.date} is not YYYY-MM-DD`);
  }
  if (options.check && options.previous !== null) {
    usage("--check reads the export's own ledger; --previous is for a run that writes one");
  }

  const out = options.out;
  if (!existsSync(out)) usage(`${out}: no export to date. Run \`npm run build\` first.`);

  const sitemapPath = join(out, "sitemap.xml");
  if (!existsSync(sitemapPath)) usage(`${sitemapPath}: the export has no sitemap`);

  const xml = readFileSync(sitemapPath, "utf-8");
  const entries = sitemapUrls(xml);
  if (entries.length === 0) usage(`${sitemapPath}: no <loc> entries — nothing to date`);

  const origin = entries[0].loc.match(/^https?:\/\/[^/]+/)?.[0];
  if (origin === undefined) usage("the sitemap declares no absolute URLs");

  // The build id, read rather than guessed. `--check` runs against an export whose `.next`
  // may be long gone, so it takes the id the ledger recorded instead.
  const buildIdPath = join(out, "..", ".next", "BUILD_ID");

  if (options.check) return check(out, sitemapPath, entries, origin);

  if (!existsSync(buildIdPath)) {
    usage(`${buildIdPath}: no build id, so page digests could not be made comparable`);
  }
  const buildId = readFileSync(buildIdPath, "utf-8").trim();
  if (buildId === "") usage(`${buildIdPath}: empty`);

  // `app/sitemap.ts` deliberately emits no `<lastmod>`: it has no per-page date to emit one
  // from, and this step is the only thing that does. A sitemap arriving here already dated
  // means either the generator started claiming again or this ran twice over one export, and
  // the second would write a second `<lastmod>` into every `<url>`.
  const alreadyDated = entries.filter((entry) => entry.lastmod !== null);
  if (alreadyDated.length > 0) {
    console.error(
      `lastmod: ${sitemapPath} already dates ${alreadyDated.length} URLs (e.g. ` +
        `${alreadyDated[0].loc} -> ${alreadyDated[0].lastmod}). Nothing but this script may ` +
        "write a <lastmod>, and it may not write one twice.",
    );
    process.exit(1);
  }

  const previous = options.previous === null ? null : readLedger(options.previous);
  const date = options.date ?? todayUtc();

  const pages = {};
  const datesByLoc = new Map();
  let carried = 0;
  let changed = 0;
  let undated = 0;
  let sawBuildId = 0;

  for (const { loc } of entries) {
    const file = pageFor(loc, origin);
    const path = join(out, file);
    if (!existsSync(path)) {
      console.error(`lastmod: ${loc}: in the sitemap, but ${file} was never built`);
      process.exit(1);
    }

    const html = readFileSync(path, "utf-8");
    if (html.includes(buildId)) sawBuildId += 1;
    const digest = digestOf(html, buildId);

    let lastmod;
    if (previous === null) {
      lastmod = null;
      undated += 1;
    } else if (previous[file]?.digest === digest) {
      lastmod = previous[file].lastmod ?? null;
      if (lastmod === null) undated += 1;
      else carried += 1;
    } else {
      lastmod = date;
      changed += 1;
    }

    pages[file] = { digest, lastmod };
    datesByLoc.set(loc, lastmod);
  }

  if (sawBuildId === 0) {
    console.error(
      `lastmod: the build id ${buildId} appears in none of the ${entries.length} pages, so ` +
        "normalising it away changes nothing and every page would read as modified on every " +
        "deploy. Refusing rather than publishing that.",
    );
    process.exit(1);
  }

  writeFileSync(sitemapPath, withLastmod(xml, datesByLoc));
  writeFileSync(
    join(out, LEDGER_FILE),
    `${JSON.stringify({ version: LEDGER_VERSION, generated: date, buildId, pages }, null, 0)}\n`,
  );

  if (previous === null) {
    console.log(
      `lastmod: no previous ledger, so none of the ${entries.length} URLs carries a ` +
        `<lastmod>. ${LEDGER_FILE} records their digests; the next deploy dates whatever ` +
        "has moved since.",
    );
  } else {
    console.log(
      `lastmod: ${entries.length} URLs — ${changed} changed in this build and are dated ` +
        `${date}, ${carried} kept the date they last changed, ${undated} are still undated ` +
        "because nothing has yet seen them change.",
    );
  }

  // Read back what was written rather than trusting what was intended.
  check(out, sitemapPath, sitemapUrls(readFileSync(sitemapPath, "utf-8")), origin);
}

/**
 * The gate: every `<lastmod>` the sitemap publishes is backed by this export's own bytes.
 *
 * A date in the sitemap has to appear in the ledger against a digest that still matches the
 * page sitting in the export. That makes the two ways this could go wrong both failures: a
 * date with no evidence behind it, and a page edited after it was dated.
 */
function check(out, sitemapPath, entries, origin) {
  const ledgerPath = join(out, LEDGER_FILE);
  const dated = entries.filter((entry) => entry.lastmod !== null);

  if (!existsSync(ledgerPath)) {
    if (dated.length === 0) {
      console.log(`lastmod: no ${LEDGER_FILE} and no <lastmod> in the sitemap — consistent.`);
      return;
    }
    console.error(
      `lastmod: ${sitemapPath} dates ${dated.length} URLs and there is no ${LEDGER_FILE} ` +
        "to say where those dates came from.",
    );
    process.exit(1);
  }

  const ledger = JSON.parse(readFileSync(ledgerPath, "utf-8"));
  if (ledger.version !== LEDGER_VERSION) {
    console.error(`lastmod: ${ledgerPath}: unreadable ledger version ${String(ledger.version)}`);
    process.exit(1);
  }
  const buildId = ledger.buildId ?? null;
  const pages = ledger.pages ?? {};
  const problems = [];

  for (const { loc, lastmod } of entries) {
    const file = pageFor(loc, origin);
    const recorded = pages[file];

    if (recorded === undefined) {
      problems.push(`${loc}: in the sitemap and absent from ${LEDGER_FILE}`);
      continue;
    }
    if (lastmod === null) {
      if (recorded.lastmod !== null && recorded.lastmod !== undefined) {
        problems.push(`${loc}: ${LEDGER_FILE} dates it ${recorded.lastmod}, the sitemap does not`);
      }
      continue;
    }
    if (recorded.lastmod !== lastmod) {
      problems.push(
        `${loc}: sitemap says ${lastmod}, ${LEDGER_FILE} says ${String(recorded.lastmod)}`,
      );
      continue;
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(lastmod)) {
      problems.push(`${loc}: <lastmod> ${lastmod} is not a plain date`);
      continue;
    }

    const path = join(out, file);
    if (!existsSync(path)) {
      problems.push(`${loc}: dated ${lastmod}, and ${file} is not in the export`);
      continue;
    }
    if (buildId !== null) {
      const digest = digestOf(readFileSync(path, "utf-8"), buildId);
      if (digest !== recorded.digest) {
        problems.push(
          `${loc}: dated ${lastmod} against content that no longer matches — the page was ` +
            "edited after it was dated, so the date describes bytes nobody is serving",
        );
      }
    }
  }

  if (problems.length > 0) {
    console.error(`lastmod: ${problems.length} dates the export cannot account for`);
    for (const problem of problems.slice(0, 40)) console.error(`  ${problem}`);
    if (problems.length > 40) console.error(`  … and ${problems.length - 40} more`);
    process.exit(1);
  }

  console.log(
    `lastmod: ${dated.length} of ${entries.length} sitemap URLs carry a <lastmod>, every one ` +
      "backed by a digest of the page the export is publishing.",
  );
}

main();
