# Contributing

## Setup

```bash
make install       # Python pipeline (uv)
make web-install   # front end (npm)
make data-offline  # build the site dataset from the committed fixture, no network
make web-dev       # http://localhost:3000
```

`make data` fetches the real dataset from the U.S. DOL and California EDD. You only need it
if you are changing the pipeline; everything else works from the fixture.

## Before opening a pull request

```bash
make verify        # provenance, lint, typecheck, Python tests, security, dependency audit
make web-verify    # typecheck, front-end tests, static export, accessibility audit
```

Both run in CI.

## Three rules that are not negotiable

**A null measure is never a zero.** The upstream feed uses `-1` for values that were
withheld or never reported, mostly because the group was too small to report without
identifying someone. Anything that renders, serializes, sorts, or aggregates a null as if it
were zero is a bug, however convenient. If you find yourself writing `?? 0` or `or 0` around
an outcome, stop.

**Provenance is enforced, not assumed.** `make provenance-check` fails the build on
references to the prior work this project is deliberately independent of. See
[PROVENANCE.md](PROVENANCE.md). Record new data sources and design inputs there when you use
them, not afterwards.

**Both languages, always.** English and Spanish ship together. A missing key is a type
error, and a Spanish string left identical to its English original fails a test. If you add
user-facing text, translate it in the same change.

## Style

Match the surrounding code. Comments should explain a constraint the code cannot show —
why a value is treated the way it is, what a government feed does that surprises people —
not restate what the next line does.

Accessibility is a gate, not a review comment. `make web-verify` runs axe over the built
pages and fails on any violation.

## Data changes

Regenerate the CI fixture after changing the pipeline's output shape:

```bash
make data      # real fetch
make fixture   # re-derive fixtures/data from it
```

Tests assert the fixture still covers every case the UI renders differently. If one of those
fails, the fixture stopped exercising something — fix the fixture, do not weaken the test.
