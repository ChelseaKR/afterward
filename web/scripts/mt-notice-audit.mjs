/**
 * Machine-translation notice audit over the static export.
 *
 * Fails the build on any exported page that shows Spanish without the notice, any English
 * page that carries it, and any notice missing its Spanish text, its English text, its link to
 * the English, or its place above the main content. The rule itself is in `mt-notice.mjs`.
 *
 * It reads the bytes that get uploaded rather than the layout that should have produced
 * them, because a notice rendered by a layout is one refactor away from a route that no
 * longer uses that layout.
 *
 * And it refuses to pass over nothing: an export with fewer Spanish pages than the floor is a
 * failure, not a short run that prints "0 problems".
 *
 * Usage: node scripts/mt-notice-audit.mjs [outDir]
 */

import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join, relative, sep } from "node:path";

import { noticeProblems, noticeRequired } from "./mt-notice.mjs";

const OUT = process.argv.slice(2).find((arg) => !arg.startsWith("--")) ?? "out";

/**
 * The floor under the sweep. CI's 60-program fixture exports hundreds of Spanish pages and
 * production thousands; this sits below both and above what a collapsed export would leave.
 */
const MIN_SPANISH_PAGES = 20;

function exportedPages(dir) {
  const found = [];
  const walk = (current) => {
    for (const entry of readdirSync(current, { withFileTypes: true })) {
      const path = join(current, entry.name);
      if (entry.isDirectory()) walk(path);
      else if (entry.name.endsWith(".html")) found.push(relative(dir, path).split(sep).join("/"));
    }
  };
  walk(dir);
  return found.sort();
}

if (!existsSync(OUT)) {
  console.error(`mt-notice-audit: no export at ${OUT}. Run \`npm run build\` first.`);
  process.exit(1);
}

const problems = [];
let required = 0;
let spanish = 0;
for (const page of exportedPages(OUT)) {
  const html = readFileSync(join(OUT, page), "utf-8");
  if (noticeRequired(page, html)) required += 1;
  if (page.startsWith("es/")) spanish += 1;
  problems.push(...noticeProblems(page, html));
}

if (spanish < MIN_SPANISH_PAGES) {
  problems.push(
    `only ${spanish} Spanish page(s) in ${OUT}, under the floor of ${MIN_SPANISH_PAGES}: ` +
      "an export this small was not audited, whatever it says",
  );
}

if (problems.length > 0) {
  for (const problem of problems) console.error(`  - ${problem}`);
  console.error(`\nmt-notice-audit: FAIL (${problems.length} problem(s))`);
  process.exit(1);
}

console.log(
  `mt-notice-audit: all ${required} page(s) showing machine-translated Spanish carry the notice ` +
    `(${spanish} under es/), and no English page does`,
);
