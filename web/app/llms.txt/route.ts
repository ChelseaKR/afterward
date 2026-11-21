import { getCoverage, getSearchIndex } from "@/lib/data";
import { llmsTxt } from "@/lib/llms";
import { SITE_URL } from "@/lib/site";

// Required for `output: "export"`: written once at build time as `out/llms.txt`, like robots.txt.
export const dynamic = "force-static";

export function GET(): Response {
  const body = llmsTxt({
    site: SITE_URL,
    programs: getSearchIndex().programs.length,
    dataDate: getCoverage().snapshot_date,
  });
  return new Response(body, { headers: { "Content-Type": "text/plain; charset=utf-8" } });
}
