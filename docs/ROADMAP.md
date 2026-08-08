# Roadmap and metrics ledger

Created 2026-08-07 as part of the portfolio standards conformance pass. Two jobs: carry the
per-repo declarations the portfolio standards system expects (observability tier, AI
evaluation scope, the metrics ledger), and point at where this project's actual forward
planning lives.

## Where the real planning lives

This repo plans in dated documents, not in a single mutable list. Current source material:

- `docs/next-steps-research-2026-08-04.md`: candidate features, researched.
- `docs/accounts-design-2026-08-04.md`: why there are no accounts, and what a shortlist
  needs instead.
- `docs/education-attainment-not-shipped-2026-08-05.md` and
  `docs/onet-technologies-not-shipped-2026-08-04.md`: features investigated and deliberately
  not shipped, with reasons. A roadmap that only lists what will be built hides half the
  decisions.
- `docs/enrichment-expansion-2026-08-04.md`, `docs/oews-assessment-2026-08-04.md`,
  `docs/onet-assessment-2026-08-04.md`: source-by-source assessments of what could join the
  dataset.

## Standard declarations

```
AI-Evaluation-Standard: N/A  (the product contains no model, prompt, retrieval,
                              or generation surface; nothing here scores, ranks,
                              or generates with an LLM)
```

The pipeline is deterministic parsing and joining of public government data; the site is a
static export of its output. Development of this repo was AI-assisted (disclosed in the
README), which is a fact about tooling, not about the product: no model runs at build time
or runtime, so there is no eval surface. Re-enter scope if any model-backed feature (say,
description summarization or a chat guide) is ever added.

**Observability: Tier B (static frontend), narrowed honestly.** There is no server, no RUM,
and no analytics, by design ("no account, no tracking" is a product commitment, so
user-behavior telemetry is out of scope permanently, not deferred). What exists instead:

- Deploy-time verification: the deploy workflow smoke-tests the live site through
  CloudFront, asserts the published dataset snapshot end-to-end, and verifies every built
  file object-by-object in S3 (`.github/workflows/deploy.yml`, guards 1 through 5).
- `make deploy-check` asks the live site whether every asset its pages reference resolves.
- A quarterly scheduled CI job checks the upstream government feeds still respond and still
  contain California data, so a broken source surfaces before the next refresh is due.

## Metrics ledger

Per QUALITY-AND-METRICS-STANDARD's ledger shape. Values as measured 2026-08-07.

| Metric | Target | Measured by | Gate | Owner |
|--------|--------|-------------|------|-------|
| Statement coverage, Python pipeline [CQ-08] | >= 85% (measured: 92%) | `pytest --cov` via `make test`; `fail_under = 85` in pyproject.toml | AUTO | maintainer |
| mypy --strict errors [CQ-06] | 0 | `make typecheck` in `make verify` | AUTO | maintainer |
| ruff lint + format findings [CQ-04] | 0 | `make lint` in `make verify` | AUTO | maintainer |
| axe-core violations, built pages [A11Y-01] | 0, all rules enabled including AAA | `npm run a11y` + `npm run a11y:rendered` in `make web-verify` | AUTO | maintainer |
| Token contrast ratios, both schemes [A11Y-05] | AAA thresholds (7:1 body text) | `npm run contrast` in `make web-verify` | AUTO | maintainer |
| EN/ES key parity [I18N-08] | 100% (missing key = compile error) | `tsc --noEmit` in `make web-verify` | AUTO | maintainer |
| Untranslated Spanish strings | 0 identical to English | vitest test in `make web-verify` | AUTO | maintainer |
| Provenance clean-room violations | 0 | `make provenance-check` in `make verify` | AUTO | maintainer |
| bandit findings, src/ [SEC] | 0 | `make security` in `make verify` | AUTO | maintainer |
| Known-vulnerable dependencies | 0 fixed HIGH+CRITICAL | `make audit` (pip-audit) in `make verify` | AUTO | maintainer |
| SHA-pinned `uses:` in workflows [SEC-25] | 100% (currently 12/12) | review on change; Dependabot maintains pins | REVIEW | maintainer |
| Fixture published to production | never | deploy workflow guards 1 and 2 + `make publish-preflight` | AUTO | maintainer |
| Screen-reader walkthrough [A11Y-11, A11Y-14] | per release | committed, dated artifact | REVIEW, **open: none performed yet** | maintainer |

The last row is open and stays visibly open: no human assistive-technology walkthrough has
been performed, no tool substitutes for one, and `docs/wcag-2.2-aaa-conformance.md` records
exactly what the automated gates prove and what they cannot.
