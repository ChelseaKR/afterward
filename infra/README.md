# Infrastructure

One CloudFormation stack publishes [camino.chelseakr.com](https://camino.chelseakr.com):
a private, versioned S3 bucket; CloudFront with Origin Access Control and TLS; Route 53
A/AAAA aliases; directory-route rewriting so `/en/occupations/` resolves to its
`index.html`; security headers; and a narrowly scoped GitHub OIDC deploy role.

The bucket is never public. CloudFront reads it through OAC, so the only way to the content
is through the distribution and its headers.

## First deployment is two phases, on purpose

`PublishDns=false` creates everything except the DNS records. Upload the built site, check
it at the CloudFront domain, and only then update the same stack with `PublishDns=true` to
point the subdomain at it. Nobody reaches a half-built site at the real address.

```bash
# Phase 1 — everything except DNS. CloudFront requires certificates from us-east-1.
aws cloudformation create-stack \
  --stack-name camino-static-site --region us-east-1 \
  --template-body file://infra/aws-static-site.yml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters ParameterKey=PublishDns,ParameterValue=false

# Certificate validation is DNS-based against the hosted zone and takes a few minutes.
aws cloudformation wait stack-create-complete \
  --stack-name camino-static-site --region us-east-1

# Build against the real dataset and the real hostname. Both matter: an offline build
# publishes the 60-program fixture, and an unset site URL puts example.invalid in the
# sitemap and robots.txt.
make data                      # or: cp -r data/processed/* web/public/data/
cd web && NEXT_PUBLIC_SITE_URL=https://camino.chelseakr.com npm run build

# Upload. Hashed assets are immutable; everything else must revalidate, because the
# dataset changes underneath the same URLs.
aws s3 sync out/ s3://camino.chelseakr.com/ --delete \
  --cache-control "public, max-age=0, must-revalidate" \
  --exclude "_next/static/*"
aws s3 sync out/_next/static/ s3://camino.chelseakr.com/_next/static/ --delete \
  --cache-control "public, max-age=31536000, immutable"

# Check it at the CloudFront domain first (see the stack's CloudFrontDomainName output).

# Phase 2 — publish DNS once the content is verified.
aws cloudformation update-stack \
  --stack-name camino-static-site --region us-east-1 \
  --template-body file://infra/aws-static-site.yml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters ParameterKey=PublishDns,ParameterValue=true
```

## Redeploying

Sync again and invalidate. The dataset refreshes far more slowly than the code, so a full
invalidation is fine and cheap at this cadence.

```bash
aws cloudfront create-invalidation --distribution-id <id> --paths "/*"
```
