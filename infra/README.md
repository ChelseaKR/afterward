# Infrastructure

One CloudFormation stack publishes [afterward.chelseakr.com](https://afterward.chelseakr.com):
a private, versioned S3 bucket; CloudFront with Origin Access Control and TLS; Route 53
A/AAAA aliases; directory-route rewriting so `/en/occupations/` resolves to its
`index.html`; security headers; and a narrowly scoped GitHub OIDC deploy role.

The bucket is never public. CloudFront reads it through OAC, so the only way to the content
is through the distribution and its headers.

`aws-static-site.yml` in this directory is that stack, and it is the only one this repo's
CI touches. `legacy/camino-static-site.yml` is a second, retired stack for the predecessor
hostname; see below.

## The retired stack

`legacy/camino-static-site.yml` is the `camino-static-site` stack (us-east-1), which served
`camino.chelseakr.com` before the 2026-08-05 rename. It is retired rather than deleted: the
CloudFront function answers every request with a 301 to the matching
`afterward.chelseakr.com` URL, path and query preserved, and the bucket is emptied by
lifecycle rule but kept (`DeletionPolicy: Retain`) so the redirect can be reverted. It
publishes no content and nothing here deploys it — the template is committed so the change
that retired it has a reviewable diff and a place to apply the next one from. Apply by hand:

```bash
aws cloudformation deploy --region us-east-1 --stack-name camino-static-site \
  --template-file infra/legacy/camino-static-site.yml --capabilities CAPABILITY_NAMED_IAM
```

One string in it still says "NearMiss" — the CloudFront distribution's `Comment`, copied
from that stack's template when this one was bootstrapped. Left as filed: this file is a
verbatim `get-template` capture plus the retirement change, and editing a string inside a
retired stack would make the capture stop matching what is deployed for no benefit to
anyone.

## First deployment is two phases, on purpose

`PublishDns=false` creates everything except the DNS records. Upload the built site, check
it at the CloudFront domain, and only then update the same stack with `PublishDns=true` to
point the subdomain at it. Nobody reaches a half-built site at the real address.

```bash
# Phase 1 — everything except DNS. CloudFront requires certificates from us-east-1.
aws cloudformation create-stack \
  --stack-name afterward-static-site --region us-east-1 \
  --template-body file://infra/aws-static-site.yml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters ParameterKey=PublishDns,ParameterValue=false

# Certificate validation is DNS-based against the hosted zone and takes a few minutes.
aws cloudformation wait stack-create-complete \
  --stack-name afterward-static-site --region us-east-1

# Build against the real dataset and the real hostname. Both matter: an offline build
# publishes the 60-program fixture, and an unset site URL puts example.invalid in the
# sitemap and robots.txt.
make data                      # or: cp -r data/processed/* web/public/data/
cd web && NEXT_PUBLIC_SITE_URL=https://afterward.chelseakr.com npm run build

# Upload. Hashed assets are immutable; everything else must revalidate, because the
# dataset changes underneath the same URLs.
aws s3 sync out/ s3://afterward.chelseakr.com/ --delete \
  --cache-control "public, max-age=0, must-revalidate" \
  --exclude "_next/static/*"
aws s3 sync out/_next/static/ s3://afterward.chelseakr.com/_next/static/ --delete \
  --cache-control "public, max-age=31536000, immutable"

# Check it at the CloudFront domain first (see the stack's CloudFrontDomainName output).

# Phase 2 — publish DNS once the content is verified.
aws cloudformation update-stack \
  --stack-name afterward-static-site --region us-east-1 \
  --template-body file://infra/aws-static-site.yml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters ParameterKey=PublishDns,ParameterValue=true
```

## Redeploying

`.github/workflows/deploy.yml` does this. Run it by hand rather than repeating the commands
above; the manual path is what put a 404 at `/` and `https://example.invalid` in the
sitemap, and every guard in the workflow exists because of a specific way that went wrong.

### The dataset has to come from outside CI

`make data` reads the DOL ETP endpoint, which answers GitHub Actions runners with **403**,
and enriches from CareerOneStop with per-user credentials. CI therefore builds from the
committed 60-program fixture. A runner cannot produce production data, so the deploy does
not try: it downloads a dataset that was built where the fetch works, and refuses anything
that smells like the fixture.

```bash
make data              # on a machine with credentials and unblocked egress
make dataset-publish   # verifies, tars, checksums, and cuts a dataset-<snapshot> release
```

Then run **Actions → Deploy → Run workflow** on `main` with `dataset_tag=dataset-<snapshot>`.
The workflow builds the site from that dataset, uploads, invalidates, and smoke-tests.

### What it refuses to do

| Guard | Failure it prevents |
|---|---|
| CI must be green on the deployed commit | Publishing code that never passed lint, tests, or `make provenance-check` |
| `main` only, `production` environment only | Publishing a branch; also the only OIDC subject the deploy role trusts |
| `is_fixture`, a 2,000-program floor, and file count vs. manifest | Publishing the 60-program fixture, which looks entirely plausible |
| Placeholder-host scan over the export | `https://example.invalid` in `sitemap.xml` and `robots.txt` |
| Every built file matched to an S3 object by name | `sync` exiting 0 having skipped `index.html`, so `/` 404s |
| `head-object` on a hashed asset and on `index.html` | Cache headers not landing, so the dataset sticks or assets re-download |
| Live fetch of `/`, `/en/`, `/es/`, `/robots.txt`, `/sitemap.xml`, `/data/coverage.json` | Declaring success on a site nobody can load, or one serving a stale snapshot |

The live `coverage.json` check compares the snapshot date and program count against what was
just uploaded, so a stale edge response fails the deploy instead of passing it.

### How big the export is, and what gets dropped before it ships

Roughly 9,000 pages, and almost none of the bytes are markup. `npm run size-report` (from
`web/`) prints the breakdown; `npm run build` prints it again and prunes. Measured against
the 3,266-program snapshot of 2026-08-04:

| Category | Before | After | Files after |
|---|---|---|---|
| `index.html` — markup plus the inline payload React hydrates from | 247.4 MiB | 247.4 MiB | 9,046 |
| `index.txt` — RSC payload for navigation the router did not prefetch | 145.7 MiB | 145.7 MiB | 9,044 |
| `__next._full.txt` — the same bytes again, requested by nothing | 145.7 MiB | **0** | **0** |
| `__next.<segment>.__PAGE__.txt` — segment-cache prefetch | 133.4 MiB | 133.4 MiB | 9,044 |
| `data/**` — `web/public/data`, copied verbatim | 32.9 MiB | 32.9 MiB | 3,940 |
| `__next._tree.txt` — route tree, ~600 bytes each | 5.3 MiB | 5.3 MiB | 9,044 |
| `sitemap.xml`, JS, CSS, `robots.txt` | 4.6 MiB | 4.6 MiB | 16 |
| **Total** | **715.0 MiB / 49,178 objects** | **569.4 MiB / 40,134 objects** | |

`__next._full.txt` is written by the server renderer so a *running* Next server could answer
a whole-page segment prefetch from the same map it builds the per-segment payloads in. The
static exporter copies that map to disk wholesale, so a site with no server gets 9,044
copies of a file no browser will ever request: the string `_full` appears in no chunk this
site serves, and each file is byte-for-byte the `index.txt` sitting beside it. The prune is
interlocked on both of those facts and refuses rather than fails if either stops holding —
see `web/scripts/size-report.mjs`.

Expect the first deploy after this to report about 9,000 fewer objects, and `sync --delete`
to spend a while removing the old ones. Nothing about what a page says changes.

Two things measured and deliberately left alone:

- **`data/**` (32.9 MiB, 3,940 objects).** Only `coverage.json` is used — the smoke test in
  the table above fetches it to prove the live site is serving the snapshot just uploaded.
  The comparison panel fetches `/data/programs/<id>.json` when a reader opens it, so those
  objects are load-bearing and must not be pruned from the bucket. The rest is build-time
  input: the search index is baked into the page, and `web/lib/data.ts` reads `public/data`
  from disk during the export only. But those URLs answer 200 today, and
  `/data/coverage.json` shows the prefix is published on purpose, so dropping the others is a
  decision about a public surface rather than a size fix. Worth making deliberately; not
  worth making silently.
- **The three remaining copies of each payload.** `index.html` needs its inline copy to
  hydrate. `index.txt` is what the router fetches when it navigates somewhere it has not
  prefetched — a `router.push`, a link clicked before its prefetch landed, an entry past its
  300s stale time. The `__PAGE__` segment is what a `<Link>` prefetch actually pulls. Remove
  any of them and navigation breaks in a way that only shows up on someone else's network.

### Two details worth knowing

The upload runs three passes: hashed assets without `--delete`, then everything else with
it, then hashed assets with it. Assets exist before any page references them, and orphaned
chunks are pruned only after the pages that used them are gone.

Cache headers are verified on the S3 objects, not over HTTPS, because
`SiteResponseHeaders` sets `Cache-Control: public, max-age=0, must-revalidate` as an
overriding custom header on the only cache behavior. Every edge response carries that,
including hashed assets — so the object's `immutable` header is real but invisible from
outside, and the year-long asset caching the split is meant to buy is not currently
happening at the edge. Removing that custom header would let the per-object values through.

Invalidation is a full `/*`. The dataset refreshes on a quarterly-ish cadence, so precision
would only be a way to miss something.

```bash
# Manual fallback, if Actions is unavailable. Everything above still applies.
aws cloudfront create-invalidation --distribution-id E2WV13UCB2U1MF --paths "/*"
```
