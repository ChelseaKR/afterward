/**
 * Size report for the static export, and the one prune that is provably safe.
 *
 * ---------------------------------------------------------------------------------------
 * What the export is actually made of
 * ---------------------------------------------------------------------------------------
 * `output: "export"` with ~9,000 pages produces roughly 715 MiB across ~49,000 files, and
 * almost none of that is markup. Every page directory holds the same RSC payload up to four
 * times:
 *
 *   index.html                     the rendered markup, plus the payload again inline in
 *                                  `self.__next_f.push(...)` so React can hydrate
 *   index.txt                      the payload, fetched by the client router when it
 *                                  navigates to a route it has not prefetched
 *   __next._full.txt               the payload again, byte for byte identical to index.txt
 *   __next.<segment>.__PAGE__.txt  the page segment alone, fetched by the segment cache
 *                                  when a <Link> prefetches
 *   __next._tree.txt               the route tree for that URL, ~600 bytes
 *
 * Three of those five are load-bearing and this script does not touch them:
 *
 *   - `index.html` carries the inline payload React hydrates from. Stripping it would turn
 *     every page into unhydratable markup.
 *   - `index.txt` is what `fetchServerResponse` requests: the router appends `index.txt` to
 *     any path ending in `/`. That is the navigation path taken whenever the route cache has
 *     no fulfilled entry — a `router.push`, a link clicked before its prefetch landed, a
 *     prefetch suppressed by Data Saver, or an entry past its 300s stale time.
 *   - `__next.<segment>.__PAGE__.txt` and `__next._tree.txt` are what the client segment
 *     cache requests when a `<Link>` enters the viewport.
 *
 * ---------------------------------------------------------------------------------------
 * Why `__next._full.txt` is different
 * ---------------------------------------------------------------------------------------
 * `_full` is written by the server renderer (`collect-segment-data.js` does
 * `resultMap.set('/_full', fullPageDataBuffer)`) so that a *running Next server* can answer
 * a segment-prefetch request for the whole page out of the same map. The static exporter
 * copies every entry in that map to disk, `_full` included.
 *
 * A browser never asks for it. `convertSegmentPathToStaticExportFilename` is the only thing
 * that turns a segment path into a `__next.*.txt` URL, and the only segment paths the client
 * ever hands it are the route-tree key, `/_tree`, `/_head` and `/_index`. The string
 * `_full` appears nowhere in Next's client bundle, and nowhere in a single byte this site
 * serves — it survives only as a filename. Meanwhile its contents are byte-for-byte the
 * same as the `index.txt` sitting beside it, which the client *does* request.
 *
 * So it is ~20% of the export, ~18% of the objects in the bucket, and dead. `--prune`
 * removes it, behind two interlocks that make the deletion self-checking rather than a
 * belief about a Next version:
 *
 *   1. no shipped chunk under `_next/static` may mention `_full` — if a future release
 *      starts requesting it, that string appears and pruning is refused outright;
 *   2. each file must be byte-identical to the `index.txt` beside it, so the bytes are
 *      demonstrably still reachable at another URL before this one is removed.
 *
 * A refusal is a warning, never an error. The worst case is a larger upload, and failing a
 * deploy over a size optimisation would be a far more expensive mistake than shipping one
 * duplicate file per page.
 *
 * Usage:
 *   node scripts/size-report.mjs [outDir]            # measure only
 *   node scripts/size-report.mjs [outDir] --prune    # measure, prune, measure again
 */

import { readdirSync, readFileSync, statSync, unlinkSync, existsSync } from "node:fs";
import { join } from "node:path";

const args = process.argv.slice(2);
const PRUNE = args.includes("--prune");
const OUT = args.find((a) => !a.startsWith("--")) ?? "out";

const DUPLICATE = "__next._full.txt";
/** The sibling whose bytes must match before a duplicate is removed. */
const CANONICAL = "index.txt";
/** `public/` is copied verbatim into the export; this is where it lands. */
const DATA_DIR = join(OUT, "data");

/** Every file, once, with its size. One walk feeds both the report and the prune. */
function walk(dir, files = []) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) walk(path, files);
    else if (entry.isFile()) files.push({ path, name: entry.name, size: statSync(path).size });
  }
  return files;
}

/**
 * Categories chosen to answer "where is the bulk", not to mirror file extensions. The four
 * RSC families are separated because they are the whole question: collapsing them into
 * "text files" is how 435 MiB of near-duplicate payload stays invisible.
 */
function categorise({ path, name }) {
  if (name === DUPLICATE) return "RSC __next._full.txt (duplicate of index.txt)";
  if (name === "__next._tree.txt") return "RSC __next._tree.txt (route tree)";
  if (name.startsWith("__next.") && name.endsWith("__PAGE__.txt")) {
    return "RSC __next.<segment>.__PAGE__.txt (segment prefetch)";
  }
  if (name === CANONICAL) return "RSC index.txt (client navigation)";
  if (name.endsWith(".html")) return "HTML (markup + inline hydration payload)";
  if (name.endsWith(".json")) {
    return path.startsWith(DATA_DIR) ? "JSON (public/data, copied verbatim)" : "JSON (other)";
  }
  if (name.endsWith(".js")) return "JS";
  if (name.endsWith(".css")) return "CSS";
  if (name.endsWith(".xml")) return "XML (sitemap)";
  return "other";
}

const MiB = 1024 * 1024;
const mib = (bytes) => (bytes / MiB).toFixed(2).padStart(9);

function report(files, heading) {
  const totals = new Map();
  for (const file of files) {
    const key = categorise(file);
    const row = totals.get(key) ?? { bytes: 0, count: 0 };
    row.bytes += file.size;
    row.count += 1;
    totals.set(key, row);
  }

  const bytes = files.reduce((sum, f) => sum + f.size, 0);
  console.log(`\n${heading}`);
  console.log("      MiB      %    files  category");
  for (const [key, row] of [...totals].sort((a, b) => b[1].bytes - a[1].bytes)) {
    const pct = ((100 * row.bytes) / bytes).toFixed(1).padStart(5);
    console.log(`${mib(row.bytes)} ${pct}  ${String(row.count).padStart(7)}  ${key}`);
  }
  console.log(`${mib(bytes)} 100.0  ${String(files.length).padStart(7)}  TOTAL`);
  return { bytes, count: files.length };
}

/**
 * Interlock 1. Not a version check: the question is whether *this* bundle can construct a
 * `_full` URL, and the bundle is right there to be read.
 */
function clientMentionsDuplicate() {
  const staticDir = join(OUT, "_next", "static");
  if (!existsSync(staticDir)) return true; // No bundle to clear it: assume the worst.
  return walk(staticDir)
    .filter((f) => f.name.endsWith(".js"))
    .some((f) => readFileSync(f.path, "utf-8").includes("_full"));
}

function prune(files) {
  const candidates = files.filter((f) => f.name === DUPLICATE);
  if (candidates.length === 0) {
    console.log("\nNothing to prune.");
    return files;
  }

  if (clientMentionsDuplicate()) {
    console.log(
      `\n::warning::Refusing to prune: a shipped chunk references "_full", so this ` +
        `build may request ${DUPLICATE}. Left ${candidates.length} file(s) in place.`,
    );
    return files;
  }

  let removed = 0;
  let bytes = 0;
  const kept = [];
  for (const file of candidates) {
    const canonical = join(file.path.slice(0, -DUPLICATE.length), CANONICAL);
    if (!existsSync(canonical) || !readFileSync(canonical).equals(readFileSync(file.path))) {
      kept.push(file.path);
      continue;
    }
    unlinkSync(file.path);
    removed += 1;
    bytes += file.size;
  }

  console.log(
    `\nPruned ${removed} x ${DUPLICATE} (${(bytes / MiB).toFixed(2)} MiB), ` +
      `each byte-identical to the ${CANONICAL} beside it.`,
  );
  if (kept.length > 0) {
    console.log(
      `::warning::${kept.length} ${DUPLICATE} file(s) did not match their ${CANONICAL} ` +
        `and were left alone, starting with ${kept[0]}.`,
    );
  }
  return files.filter((f) => f.name !== DUPLICATE || kept.includes(f.path));
}

if (!existsSync(OUT)) {
  console.error(`No such directory: ${OUT}. Run \`next build\` first.`);
  process.exit(1);
}

const files = walk(OUT);
const before = report(files, `Static export size: ${OUT}`);
if (PRUNE) {
  const after = report(prune(files), `After prune: ${OUT}`);
  const saved = before.bytes - after.bytes;
  console.log(
    `\nReclaimed ${(saved / MiB).toFixed(2)} MiB ` +
      `(${((100 * saved) / before.bytes).toFixed(1)}%) and ` +
      `${before.count - after.count} objects.`,
  );
}
