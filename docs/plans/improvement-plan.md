# Improvement plan, 2026-08-28

An audit of this repository's own gates, on the rule that a check which cannot fail is worse
than no check at all. Everything below was observed by running the gates, not read off the
documentation. What the documentation claims and what the gates do is itself one of the
findings.

## What was already true

`make verify` passes (exit 0): provenance-check, ruff format check, ruff lint, mypy strict,
1,240 tests at 94.75% branch coverage against an 85% floor, bandit, pip-audit.
`make web-verify` passes (exit 0): tsc, 385 vitest cases, 34 contrast pairings in light and
dark, static export, axe over 22 built pages, axe in Chromium over the rendered search
results and comparison table.

Several gates are already hardened against the exact failure this audit hunts for, and were
found sound: `a11y-audit.mjs` refuses a page it was told to read and cannot, and refuses a
route the app declares that no target represents; `contrast-audit.mjs` counts an unresolvable
token as a failure rather than a skip; `dataset_check.py` refuses the fixture; the `audit`
target's retry loop exits non-zero when every attempt fails; the deploy workflow's
missing-file loop accumulates rather than taking the last iteration's status. `make install`
uses `uv sync --locked`, which reads `pyproject.toml` and fails on drift, not `--frozen`,
which does not.

## Findings

### 1. Two Python surfaces have never been type-checked, and one of them is the gates

`pyproject.toml` sets `[tool.mypy] files = ["src"]`. `scripts/` (eight gate scripts, including
the ones that decide whether a dataset may be backed up, packaged, or published) and `tests/`
(1,240 cases) are outside that scope. The README's Code Quality row says "mypy --strict"
without saying which third of the repository it reads.

Compounding it: `src/afterward/` ships no `py.typed` marker. Pointing mypy at anything outside
the package makes it treat `afterward` as an untyped third-party import -- 60 of the 181
errors that appear when the scope is widened are that one missing file. The marker is also a
packaging defect in its own right: the wheel declares no types to anything that installs it.

### 2. The rendered accessibility gate claims coverage it skipped

`web/scripts/a11y-rendered.mjs` audits the assistant panel only when the build contains one,
which requires `NEXT_PUBLIC_ASK_URL` at build time. No build sets it -- not `make web-verify`,
not CI, not the deploy workflow -- so the branch never runs. The gate prints
`skip  Assistant panel (English): not in this build` and then prints, as its verdict:

    a11y-rendered: no violations in the rendered search results, comparison table, or assistant panel

The panel is the newest and least-reviewed interface in the repository, and no gate anywhere
has ever run axe over it. This is the failure `a11y-audit.mjs` refuses one file away, in
words that are already in the tree: "A page this gate is told to read and cannot is unaudited,
not passing."

### 3. `npm run lint` cannot run at all, and nothing runs it

`web/package.json` maps `lint` to `next lint`, which Next 16 removed. It now parses `lint` as
a directory argument and exits 1 with `Invalid project directory provided, no such directory:
web/lint`. Nothing noticed because `npm run verify` does not include `lint`; no ESLint has
ever run over this front end. `eslint` and `eslint-config-next` are devDependencies kept
current by Dependabot -- PRs #76 and #77 are open right now -- for a command that cannot run.

Restoring the full Next config is blocked upstream, not by choice: `eslint-config-next@16.3.1`
loads `typescript-eslint@8.66.0`, which refuses to start against this repository's
TypeScript 7.0 (`typescript-eslint does not support TS 7.0`, tracked at
typescript-eslint#10940).

### 4. A CI assertion with no `make` target

`.github/workflows/ci.yml`'s "Confirm this build is not publishable" step is inline shell. It
is a real assertion -- CI must produce a fixture-backed, placeholder-hosted artifact -- and it
is the one thing in the pipeline a developer cannot reproduce locally, so a tree that passes
`make verify` and `make web-verify` can still be rejected by CI.

## Plan

1. **Type-check the gate scripts and the test suite.** Add `src/afterward/py.typed`; widen
   mypy's scope to `src`, `scripts`, `tests`; fix the residual errors; point the pre-commit
   hook at the config rather than at `src`. Tests keep `disallow_any_generics` and
   `warn_return_any` off, stated in the config with the reason: an ad-hoc dict fixture does
   not need generic parameters, and forcing them buys churn rather than safety. Everything
   else stays strict, including `scripts/`, which is strict with no relaxation at all.
2. **Stop the rendered gate claiming what it skipped, and audit the panel for real.** The
   summary names what it audited and what it did not. The assistant panel gets a genuine axe
   pass in the unit suite, where it can be mounted open with every rule enabled without a
   second Next build.
3. **Make the front-end lint run.** Point `lint` at ESLint itself over the `.mjs` gate
   scripts -- the files that are neither type-checked by `tsc` (`allowJs: false`) nor linted
   by anything today -- and put it in `verify`. State the TSX gap and its upstream cause in
   the config, so an unlinted surface is declared rather than implied.
4. **Give CI's publishability assertion a `make` target** and call it from CI, so the local
   gate and the CI gate read the same file.
5. **Record what stays blocked** in this document, including anything blocked for want of a
   source this project is willing to cite.

## What was done

All five phases landed. Each commit records the break that was watched to fail and the
restore that was watched to pass.

1. `src/afterward/py.typed` added and confirmed in the built wheel; mypy's scope widened to
   `src`, `scripts`, `tests`; the path argument removed from `make typecheck` and from the
   pre-commit hook, which was the half that made the config change a no-op; 181 errors fixed
   rather than silenced. `make typecheck` now reads 71 files where it read 30.
   `tests/test_typing_scope.py` fails if any of that is undone.
2. `components/AskPanel.a11y.test.tsx` runs axe over the panel closed, open in both
   languages, and showing an answer. It found nothing: the panel was accessible, it was only
   unaudited. `a11y-rendered.mjs` now takes its expectation of a panel from the same variable
   that decides whether one is built, fails on a disagreement in either direction, and builds
   its verdict from what it read.
3. `npm run lint` is `eslint .` and is in the `verify` chain. It found one thing on its first
   run: a dead `scheme` parameter in `contrast-audit.mjs`, removed with byte-identical output
   over all 34 pairings. `scripts/verify-wiring.test.ts` asserts every gate is still in the
   chain, which is the failure that let the broken lint script last.
4. `make ci-artifact-check` is the assertion CI makes about its own artifact, as a script
   that is type-checked and tested rather than six lines of inline shell, and CI calls the
   target.
5. Stale claims corrected: the README and `docs/ROADMAP.md` said 92.12% branch coverage while
   the tree measured 94.75% before any of this work; the README's Code Quality row said
   "mypy --strict" without a scope and named no linter for the front end; two `make`
   summaries omitted gates that run.

## Findings that were checked and found sound

Reported so the ground is known to have been covered, not to pad the list. `gitleaks` runs
over full history in CI (`fetch-depth: 0`) *and* over staged content in a pre-commit hook, so
an uncommitted key is caught before it can become a leak; `make install` is
`uv sync --locked`, which reads `pyproject.toml`, not `--frozen`, which does not; the `audit`
target's retry loop exits non-zero when every attempt fails rather than taking the last
iteration's status; the deploy workflow's missing-file loop accumulates into a variable
instead of relying on exit status; `dataset_check.py` refuses the fixture and was verified
doing it; `a11y-audit.mjs` refuses both a page it cannot read and a route no target
represents; `contrast-audit.mjs` counts an unresolvable token as a failure. No semgrep here,
so none of its traps apply. No test was found asserting a suppressed value as zero, and no
golden file is regenerated by the code that checks it -- `data-manifest.json` is written only
by an explicit `make dataset-manifest`, which is an operator action after a real refresh.

## Blocked, and why

- **Issue #32, native Spanish review.** Needs a native speaker's judgement. One section has a
  credited external review (`docs/spanish-funding-review-2026-08-06.md`); the rest does not,
  and `docs/I18N.md` says so. Nothing here can close it without claiming a competence this
  work does not have.
- **Issue #1, screen-reader walkthrough.** Needs a person driving VoiceOver, NVDA or JAWS.
  Automated AAA coverage is real and is not a substitute; the conformance note already says
  exactly that.
- **ESLint over `.ts`/`.tsx`.** Blocked upstream on typescript-eslint's TypeScript 7 support.
  Downgrading TypeScript to buy a linter would trade a working type-checker for a lint pass.
  `tsc --noEmit` under `strict` and `noUncheckedIndexedAccess` continues to cover these files
  for types; no lint rules apply to them, and that is now written down rather than implied by
  a script that exits 1 for an unrelated reason.
- **Dependabot's pip PRs.** #73 updates the `anthropic` constraint in `pyproject.toml` and
  cannot update `uv.lock`, so `make install` (`uv sync --locked`) fails and the PR is blocked.
  The gate is behaving correctly; the ecosystem cannot satisfy it unaided. Resolving it means
  either running `uv lock` on the branch by hand or moving the Python ecosystem to one
  Dependabot can lock. Left as a decision for the owner rather than taken here.
