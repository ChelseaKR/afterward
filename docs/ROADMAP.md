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
AI-Evaluation-Standard: Applies  (since 2026-08-21, ADR 0003: the optional
                                  afterward.ask runtime service has a prompt, a
                                  retrieval step and a generation surface)
```

Until 2026-08-21 this read `N/A`, with the sentence "Re-enter scope if any model-backed
feature (say, description summarization or a chat guide) is ever added." One has been, by
the owner's direction, and the declaration moves with it. The pipeline is still deterministic
parsing and joining of public government data and the site is still a static export of its
output; no model runs at build time, and nothing the static site shows was generated,
summarized or ranked by one. The model runs only in `afterward.ask`, only after a person opts
in, and only in the roles ADR 0003 bounds. The eval surface that follows — query structuring,
suppression faithfulness, citation grounding, comparability — is committed under `evals/`
with provenance-stamped results, and the ledger below carries its gates.

**Observability: Tier B (static frontend), narrowed honestly.** There is no server behind
the static site, no RUM, and no analytics, by design ("no account, no tracking" is a product
commitment, so user-behavior telemetry is out of scope permanently, not deferred). The
optional `afterward.ask` service, when deployed, will carry request counts and cost
counters and nothing about who asked or what they typed (ADR 0003). What exists instead:

- Deploy-time verification: the deploy workflow smoke-tests the live site through
  CloudFront, asserts the published dataset snapshot end-to-end, and verifies every built
  file object-by-object in S3 (`.github/workflows/deploy.yml`, guards 1 through 5).
- `make deploy-check` asks the live site whether every asset its pages reference resolves.
- A quarterly scheduled CI job checks the upstream government feeds still respond and still
  contain California data, so a broken source surfaces before the next refresh is due.

## Open: re-run the eval suites on the shipped prompt

The one file under `evals/results/` measures prompt `2026-08-21.1`. The shipped
`PROMPT_VERSION` is `2026-08-21.2`, and the verifier has changed three times under it since
that run: #72 added `DENIAL_BEFORE_ZERO` and widened `_cited_records`, and #114 added
`direction_reversed`. The file now carries a `superseded` banner saying so, and
`evals.provenance_problems` refuses any future run whose `prompt_version` is not the shipped
one unless it carries such a banner — so this cannot go stale silently again.

What is still owed is the measurement itself: a live run of all four suites on the shipped
prompt, committed under `evals/results/`. It needs a Bedrock invocation on
`global.anthropic.claude-sonnet-4-6` (the model this account can invoke) and an owner's
judgment on the numbers it produces, so it is not something a code change can close. **#94,
which asks whether to deploy `afterward.ask`, should cite that run rather than the superseded
one.**

## Metrics ledger

Per QUALITY-AND-METRICS-STANDARD's ledger shape. Values as measured 2026-08-07.

| Metric | Target | Measured by | Gate | Owner |
|--------|--------|-------------|------|-------|
| Branch coverage, Python pipeline [CQ-08] | >= 85% (measured: 94.75% on 2026-08-28) | `pytest --cov` via `make test`; `branch = true` + `fail_under = 85` in pyproject.toml | AUTO | maintainer |
| mypy --strict errors [CQ-06] | 0, over `src`, `scripts` and `tests` (71 files) | `make typecheck` in `make verify`; scope is `files` in pyproject.toml, held there by `tests/test_typing_scope.py` | AUTO | maintainer |
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
