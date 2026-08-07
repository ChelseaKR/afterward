# 0000. Record architecture decisions

## Status

Accepted (2026-08-07)

## Context

This project already keeps a dated design log (`docs/design-log.md`) whose entries record
what was decided and from which inputs, and a provenance record (`PROVENANCE.md`) that is
mechanically enforced. What it did not have is the portfolio's standard ADR shape: one file
per decision, numbered, in `docs/adr/`, which is where the portfolio standards system
(CODE-QUALITY-STANDARD section 8) looks for the reasoning behind any standards N/A
declaration or expensive-to-reverse choice.

## Decision

Keep lightweight MADR-style ADRs in `docs/adr/`, one file per decision, numbered
sequentially (`NNNN-kebab-case-title.md`), append-only: superseding an old decision means a
new ADR that says so, never editing or deleting the old one. Each ADR carries Status,
Context, Decision, and Consequences, and, where it backs a standards N/A declaration, a
"Revisit if" trigger.

The design log stays. It records the day-by-day narrative and the measured figures; ADRs
record the durable decisions the narrative produced. An ADR may cite a design-log entry
rather than restate it.

## Consequences

- Every N/A row in the README's Standards Conformance table must cite an ADR.
- Future maintainers can find the reasoning behind a nonconformance without reconstructing
  it from git blame or a 400-line design log.
