# 0004. The root is a 301 to /en/, and each deploy announces its changed pages to IndexNow

## Status

Accepted (2026-11-17, owner decision on a search review). The CloudFront half takes effect
only when the owner deploys the `afterward-static-site` stack; the IndexNow half on the next
run of the Deploy workflow.

## Context

A read-only search review on 2026-11-17 (Search Console, URL Inspection, GA4) found:

- Google picked `/` as the canonical for the homepage, then left it "Crawled - currently not
  indexed", last crawled 2026-08-22. `/` is a `<meta http-equiv="refresh">` language chooser
  (`web/app/page.tsx`), not a page with content of its own, and `/en/` is reported as a
  duplicate of it. So the page that links to every other page carries no weight in search.
- Every other inspected URL is also "Crawled - currently not indexed". Search sent 0 clicks in
  the last 28 days. ChatGPT sent 22 of the 25 engaged sessions in the same window, and
  ChatGPT search draws on Bing, which Afterward never tells about a change: Bing finds pages
  only when it happens to crawl.

The owner chose the cheap steps only (D2, option A): no pruning, no `noindex`, and a
re-check of Search Console around 2027-01-10.

## Decision

1. **`/` and `/index.html` answer a 301 to `/en/` at the edge**, in the existing
   `RouteRewriteFunction`, with the query string kept so `utm_*` tags on a shared root link
   still reach the page they land on. Every other route resolves exactly as before. The
   chooser page stays in the export: it is what a local preview of the export serves, and
   what the edge served before the stack update.
2. **Each deploy announces its new and changed pages to IndexNow**, with the same stdlib
   module the portfolio's other sites carry (`src/afterward/indexnow.py`). The sitemap's
   `<lastmod>` moves only when a page's digest moves (`web/scripts/lastmod.mjs`), so the
   deploy diffs the built sitemap against the live one before the upload and picks the URLs
   that are new or whose `<lastmod>` changed. A separate job sends that list after the deploy
   and its smoke test pass. It holds `contents: read` and nothing else, and it never fails the
   run. The key is public by design and is served from `web/public/<key>.txt`.

## Consequences

- Visitors see no difference: browsers already ended on `/en/`.
- The deploy's smoke test accepts either a 301 from `/` to `/en/` or the chooser page, because
  the stack and the site are deployed separately and either order is fine. A 404 at the root,
  or a redirect anywhere else, still fails it.
- A live sitemap the deploy cannot read means nothing is announced that run, not everything.
- `web/lib/edgeRoutes.test.ts` runs the function code lifted from the template, and
  `tests/test_indexnow_wiring.py` holds the order of the deploy steps and the submit job's
  permissions.

## Revisit if

Search Console shows no re-indexing by about 2027-01-10. Then the owner's plan is to stop
spending on Afterward's search traffic rather than to do more here.
