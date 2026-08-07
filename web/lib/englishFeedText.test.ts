import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

/**
 * Guards every render site of the fields the feed publishes in English only, closing the gap
 * WCAG 3.1.2 Language of Parts leaves: no automated rule (in axe or anywhere else) detects a
 * missing `lang` attribute, only an invalid one, so `npm run a11y` cannot see this class of
 * defect. `program_name`, `description`, `provider_name` and `entry.n`/`entry.p` (their
 * search-index equivalents) are the closed set of fields with no Spanish counterpart in the
 * feed at all — see `feedTextLang` in `./i18n`. This reads the source rather than rendered
 * output because these are async Server Components with no lightweight render harness here;
 * reading the source is what actually catches a future render site that forgets the guard.
 */
function read(path: string): string {
  return readFileSync(path, "utf-8");
}

/**
 * Every occurrence of `marker` must be preceded, within `window` characters, by
 * `feedTextLang(lang)`. Every render site puts the `lang` attribute on the opening tag of the
 * element wrapping the text, which precedes the text itself, so searching backward from each
 * occurrence is what "this text is guarded" actually means here.
 */
function expectEveryOccurrenceGuarded(source: string, marker: string, window = 250): void {
  let index = source.indexOf(marker);
  let occurrences = 0;
  while (index !== -1) {
    occurrences += 1;
    const before = source.slice(Math.max(0, index - window), index);
    expect(
      before.includes("feedTextLang(lang)"),
      `"${marker}" (occurrence ${occurrences}) is not preceded by feedTextLang(lang) within ${window} characters`,
    ).toBe(true);
    index = source.indexOf(marker, index + marker.length);
  }
  expect(occurrences, `"${marker}" was not found at all — has the render site moved?`).toBeGreaterThan(0);
}

describe("English-only feed text carries lang=\"en\" on Spanish pages", () => {
  it("guards the program name, provider name and description on the program page", () => {
    const source = read("app/[lang]/programs/[id]/page.tsx");
    expectEveryOccurrenceGuarded(source, "{program.program_name}");
    // Braced: `placeOf()` above also calls `tidyName(program.provider_name)`, unbraced, to
    // build page metadata rather than a DOM element, and is deliberately not guarded.
    expectEveryOccurrenceGuarded(source, "{tidyName(program.provider_name)}");
    expectEveryOccurrenceGuarded(source, "{program.description}");
  });

  it("guards the provider name on the provider detail page", () => {
    // `>...<`: `generateMetadata` above also calls `tidyName(provider.name)`, as a plain
    // function argument rather than inside a tag, to build the page's `<title>`.
    expectEveryOccurrenceGuarded(
      read("app/[lang]/providers/[slug]/page.tsx"),
      ">{tidyName(provider.name)}<",
    );
  });

  it("guards the provider name on the provider index", () => {
    expectEveryOccurrenceGuarded(read("app/[lang]/providers/page.tsx"), "{tidyName(provider.name)}");
  });

  it("guards the program name and provider name on an occupation's program list", () => {
    const source = read("app/[lang]/occupations/[soc]/page.tsx");
    expectEveryOccurrenceGuarded(source, '{entry.n ?? "—"}');
    expectEveryOccurrenceGuarded(source, "{tidyName(entry.p)}");
  });

  it("guards the program name and provider name on a search result card", () => {
    const source = read("components/SearchApp.tsx");
    expectEveryOccurrenceGuarded(source, '{entry.n ?? "—"}');
    expectEveryOccurrenceGuarded(source, "{tidyName(entry.p)}");
  });

  it("guards the program name (tray chip and table column) and provider name in the comparison", () => {
    const source = read("components/Compare.tsx");
    expectEveryOccurrenceGuarded(source, '{entry.n ?? "—"}');
    expectEveryOccurrenceGuarded(source, "{tidyName(entry.p)}");
  });
});
