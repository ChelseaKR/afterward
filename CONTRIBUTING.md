# Contributing

## Where to start

- **A figure looks wrong**, the Spanish reads badly, or something is hard to use — open an
  issue. There are templates for those three; none of them needs you to run the code.
- **Spanish review is the most valuable thing an outside contributor can do here.** The
  translation has had no native reviewer, the site says so, and the strings are all in one
  file. You do not need TypeScript.
- **Code**: issues labelled `good first issue` are scoped to one file and say what "done"
  looks like.

## Setup

You do **not** need API credentials or the production dataset. `make data-offline` builds
everything from a committed 60-program fixture with no network access, and that is what CI
uses. Credentials only matter if you are changing how a source is fetched.

If you have a real dataset on this machine, `make data-offline` backs it up before the
fixture overwrites it — it writes straight over `web/public/data`, which is otherwise the
only copy.


```bash
make install       # Python pipeline (uv)
make web-install   # front end (npm)
make data-offline  # build the site dataset from the committed fixture, no network
make web-dev       # http://localhost:3000
```

`make data` fetches the real dataset from the U.S. DOL and California EDD. You only need it
if you are changing the pipeline; everything else works from the fixture.

Optional: `uv run pre-commit install` wires fast local hooks (ruff, gitleaks, whitespace)
that catch the common CI failures before a commit leaves your machine. CI remains the gate
of record either way.

## Before opening a pull request

```bash
make verify        # provenance, lint, typecheck, Python tests, security, dependency audit
make web-verify    # typecheck, lint, front-end tests, static export, accessibility audits
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
