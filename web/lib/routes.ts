import { allOccupationCodes, allProgramIds, getSearchIndex } from "./data";
import { LANGUAGES, type Lang } from "./i18n";
import { groupByProvider } from "./providers";

/**
 * Every URL this site publishes, as one list, read by everything that has to agree about it.
 *
 * This was `app/sitemap.ts`'s local variable. It is here because three things now have to
 * name the same set of pages and any two of them disagreeing is invisible: the sitemap tells
 * a crawler which URLs exist, each page's `alternates` tells that crawler which URLs are the
 * same record in the other language, and `lib/site.test.ts` checks the second against the
 * first. A test that walked its own list of pages would be checking that a list agrees with
 * itself -- it would stay green through a route added to the sitemap and given no canonical,
 * which is precisely the defect it exists to catch.
 *
 * A path is stored split, as the language and the rest, rather than joined. Joined, every
 * consumer has to re-derive the twin by string surgery on the first segment -- and
 * `app/sitemap.ts` did exactly that, with a `replace(/^\/(en|es)\//, ...)` whose alternation
 * is a third copy of `LANGUAGES` that a third locale would not update. Split, the twin is
 * the same `rest` under another `lang`, and there is nothing to keep in step.
 *
 * `rest` is the path after the language, with a trailing slash and no leading one: `""` for a
 * language home page, `"programs/1234/"` for a program. It is what `pageMetadata` in
 * `lib/site.ts` takes, so the string that reaches a page's `<link rel="canonical">` is the
 * string this file produced.
 */
export interface SitePath {
  lang: Lang;
  /** The path after `/{lang}/`, trailing slash included: `""`, `"occupations/"`, … */
  rest: string;
  /** Sitemap priority. Nothing else reads it; it travels with the path so it stays paired. */
  priority: number;
}

/** `/{lang}/{rest}` — the one place a `SitePath` becomes a URL path. */
export function pathOf({ lang, rest }: Pick<SitePath, "lang" | "rest">): string {
  return `/${lang}/${rest}`;
}

/**
 * Every page, in both languages.
 *
 * Search is how someone finds out that the program they were about to enroll in reports
 * nothing, or trains for work the state expects less of. Being findable is part of the
 * point, not an afterthought.
 *
 * `about/` is deliberately absent, exactly as it was when this lived in `app/sitemap.ts`.
 * Adding it is a change to what the sitemap advertises and belongs to whoever decides that,
 * not to a refactor that moved the list.
 */
export function sitePaths(): SitePath[] {
  const providers = groupByProvider(getSearchIndex().programs);

  const rests: Array<{ rest: string; priority: number }> = [
    { rest: "", priority: 1 },
    // The browse indexes rank above any single occupation or provider: each one is the
    // whole set in one page, and they are the two pages a crawler needs in order to reach
    // the rest of the site without executing the search.
    { rest: "occupations/", priority: 0.8 },
    { rest: "providers/", priority: 0.8 },
    // The funding rules, which used to be repeated inside every program page and are now
    // one page those pages link to. A crawler that never reaches it would see 6,532 links
    // pointing at a page absent from the sitemap.
    { rest: "paying-for-training/", priority: 0.8 },
    // The coverage page is meant to be cited, by people who will find it through a search
    // rather than by walking the site. It is the only page here that answers a question
    // about California's training data as a whole rather than about one program, so a
    // crawler that cannot reach it is the difference between the page existing and the
    // page being useful.
    { rest: "outcomes-coverage/", priority: 0.8 },
    // The CTDL export's account of itself. Same reasoning as the coverage page and a
    // narrower audience: the people who would check a mapping against the schema will
    // arrive from a search or a link, never by walking a training-program site.
    { rest: "ctdl/", priority: 0.6 },
    ...allOccupationCodes().map((soc) => ({ rest: `occupations/${soc}/`, priority: 0.7 })),
    ...providers.map((provider) => ({ rest: `providers/${provider.slug}/`, priority: 0.6 })),
    ...allProgramIds().map((id) => ({ rest: `programs/${id}/`, priority: 0.5 })),
  ];

  return LANGUAGES.flatMap((lang) => rests.map(({ rest, priority }) => ({ lang, rest, priority })));
}
