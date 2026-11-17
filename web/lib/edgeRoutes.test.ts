import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

/**
 * The CloudFront viewer-request function in `infra/aws-static-site.yml`, run as written.
 *
 * It is the one piece of routing that exists only at the edge, so nothing else in this suite
 * exercises it: the static export, the axe passes and the SEO audit all read files on disk.
 * This lifts the `FunctionCode` block out of the template byte for byte and calls `handler`
 * on CloudFront-shaped events, so the template and the test cannot drift apart.
 *
 * ADR 0004: `/` (and `/index.html`) answer a 301 to `/en/` with the query string kept, and
 * every other route resolves exactly as it did before.
 */

const TEMPLATE = join(
  dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "infra",
  "aws-static-site.yml",
);

type QueryValue = { value: string; multiValue?: { value: string }[] };
type Request = { uri: string; querystring: Record<string, QueryValue> };
type Redirect = {
  statusCode: number;
  statusDescription: string;
  headers: { location: { value: string } };
};

function functionCode(): string {
  const template = readFileSync(TEMPLATE, "utf8");
  const start = template.indexOf("  RouteRewriteFunction:");
  expect(start).toBeGreaterThan(-1);
  const block = template
    .slice(start)
    .match(/FunctionCode: \|\n((?: {8}.*\n|\n)+)/)?.[1];
  expect(block).toBeDefined();
  return (block ?? "").replace(/^ {8}/gm, "");
}

// The function is plain cloudfront-js-2.0 source with no imports; evaluating it is the only
// way to run the bytes CloudFormation will publish rather than a copy of them.
const handler = new Function(
  `${functionCode()}\nreturn handler;`,
)() as (event: { request: Request }) => Request | Redirect;

function run(uri: string, querystring: Record<string, QueryValue> = {}) {
  return handler({ request: { uri, querystring } });
}

describe("the root redirect", () => {
  it("answers / with a permanent redirect to /en/", () => {
    const response = run("/") as Redirect;
    expect(response.statusCode).toBe(301);
    expect(response.statusDescription).toBe("Moved Permanently");
    expect(response.headers.location.value).toBe("/en/");
  });

  it("does the same for /index.html, the chooser's own file", () => {
    expect((run("/index.html") as Redirect).headers.location.value).toBe(
      "/en/",
    );
  });

  it("keeps the query string, so campaign tags reach the page they land on", () => {
    const response = run("/", {
      utm_source: { value: "chatgpt.com" },
      tag: { value: "a", multiValue: [{ value: "a" }, { value: "b c" }] },
    }) as Redirect;
    expect(response.headers.location.value).toBe(
      "/en/?utm_source=chatgpt.com&tag=a&tag=b%20c",
    );
  });

  it("redirects nothing else", () => {
    for (const uri of [
      "/en/",
      "/es/",
      "/en/programs/abc/",
      "/robots.txt",
      "/sitemap.xml",
    ]) {
      expect(run(uri)).not.toHaveProperty("statusCode");
    }
  });
});

describe("directory routes still resolve to their index documents", () => {
  it.each([
    ["/en/", "/en/index.html"],
    ["/es/occupations/", "/es/occupations/index.html"],
    ["/en/occupations", "/en/occupations/index.html"],
    ["/robots.txt", "/robots.txt"],
    ["/data/coverage.json", "/data/coverage.json"],
  ])("%s -> %s", (uri, expected) => {
    expect((run(uri) as Request).uri).toBe(expected);
  });
});
