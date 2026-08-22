# Security Policy

## Reporting a vulnerability

Please report security issues privately through GitHub's
[private vulnerability reporting](https://github.com/ChelseaKR/afterward/security/advisories/new)
rather than in a public issue.

Expect an acknowledgement within a week. This is a personal project, not a staffed service,
so please size your expectations accordingly.

## Scope

The published site is static: pre-rendered HTML and JSON, no server, no database, no user
accounts, and no user-submitted input. That removes most of the usual attack surface. An
optional runtime service, `afterward.ask`, accepts free text from people who opt in and
sends it to a model provider (`docs/adr/0003-runtime-ai-at-the-edges.md`); it is in scope
once deployed, and so is anything that lets model output reach the page without passing the
verifier. The things genuinely worth reporting:

- Supply-chain problems in the Python or npm dependency tree.
- A way to make the build pipeline execute untrusted content from an upstream data source.
- Cross-site scripting via unescaped values from the upstream feeds. Program descriptions,
  provider names, and URLs all originate from third parties and are rendered on the page.
- Anything that causes this project to send traffic somewhere it should not — including
  the static site making any off-origin request before a person has opted in to the AI
  panel.
- A way to make `afterward.ask` show a figure the published dataset does not contain, or to
  get past its rate limit or daily cap.

## Not in scope

- Accuracy of the underlying government data. That is a data quality question — open a
  normal issue. See [DISCLAIMER.md](DISCLAIMER.md).
- Denial of service against the upstream public APIs. If you find a way this project could
  hammer a government endpoint, that *is* in scope, and it is a bug worth reporting.

## Data handling

This project collects nothing. There are no accounts, no cookies set by the application, no
analytics, and no personally identifiable information in the dataset. The upstream federal
data is aggregated and small cohorts are suppressed at source; that suppression is preserved
rather than reversed, and no attempt is made to re-identify anyone.
