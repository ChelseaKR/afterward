# 0001. Declare the Release & Versioning standard's release pipeline N/A (not consumed downstream)

## Status

Accepted (2026-08-07)

## Context

RELEASE-AND-VERSIONING-STANDARD requires every repo either to produce versioned releases
(semver tags, a CHANGELOG-driven bump, a hardened tag-triggered release workflow) or to
declare N/A with a reason on the record. Afterward has no semver tags and no code-release
workflow, and that is a design, not an omission:

- The shipped artifact is a static site, published only by the dispatch-only
  `.github/workflows/deploy.yml`, which refuses to run without a green CI conclusion on the
  exact commit being deployed. Nothing downstream consumes an afterward *version*: no
  package on PyPI or npm, no API another service pins, no library another repo imports.
- The one thing that is released through GitHub Releases is the dataset
  (`make dataset-publish`, tags like `dataset-2026-08-04`). Those are immutable, checksummed
  data snapshots consumed by the deploy workflow, named by snapshot date because the date is
  the identity that matters. They are not software versions and deliberately do not look
  like them.

## Decision

Declare the Release & Versioning standard's release pipeline N/A (not consumed downstream)
for this repository. Continuous deployment of a static site from `main` via the guarded
dispatch workflow is the delivery model. The dataset release handshake stays exactly as it
is: date-tagged, checksummed, verified on both ends (documented in `Makefile` and in
`deploy.yml`'s header).

CHANGELOG.md itself remains required and kept (DOCUMENTATION-STANDARD forbids marking it
N/A); its entries are dated rather than version-numbered.

## Consequences

- README's Standards Conformance table carries `Release & Versioning | N/A (not consumed
  downstream)` citing this ADR.
- Every production deploy still names exactly which dataset snapshot and which commit it
  published, in the workflow run summary, so "what is live" stays answerable without
  version tags.

## Revisit if

Anything starts consuming this repo as a dependency: a published package, a versioned API,
another repo importing the pipeline, or a downstream consumer of the CTDL export that needs
stability guarantees. At that point semver tags and a hardened release workflow become
required.
