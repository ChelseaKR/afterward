# Camino

**California training programs, what happened to the people who took them, and where those
programs actually lead.**

> Status: pre-alpha, and not affiliated with the State of California. It uses the state's
> open-source design system, so a permanent notice on every page says so.

## The problem

If you are a Californian deciding whether to spend months and thousands of dollars on a
training program, you cannot easily find out what happened to the people who finished it.
The state's workforce portal puts its training list behind an account, and the outcome data
that does exist — how many people completed, how many got jobs, what they earned — is
published by the federal government in a form no Californian is expected to find.

Meanwhile the state publishes excellent occupation data: what jobs are growing, in which
regions, and what they pay. Nobody puts the two next to each other.

Camino does exactly that, from public data, with no account and no tracking.

## What it does today

The pipeline pulls every California training program reported under WIOA — provider, cost,
length, format, and the federally-reported outcome measures — and joins each one to
California's own ten-year projection for the occupation it feeds: median wage, projected
openings, expected entry-level education, statewide and by region.

```bash
make install       # Python pipeline
make data          # fetches from U.S. DOL and CA EDD, writes web/public/data/
make web-install   # front end
make web-dev       # http://localhost:3000
```

The pipeline emits a full dataset (`programs.json`, `occupations.json`, `coverage.json`)
plus a sharded bundle the site consumes: a slim `search-index.json` for client-side search,
and per-program and per-occupation detail fetched only when opened.

The front end is a Next.js static export in `web/` — search with filters, program detail,
and occupation detail, in English and Spanish. It builds to about 8,000 pages in under
twenty seconds and needs no server at runtime.

```bash
make web-verify    # typecheck, unit tests, static export, axe pass over built pages
```

## Honesty about coverage

`coverage.json` is a first-class output, not a debug artifact. Roughly **half** of
California's reported programs have no published outcome data at all, and the pipeline
counts and publishes that rather than hiding it. Two rules follow from this and are enforced
in code:

- A withheld or suppressed measure is `null`, never `0`. WIOA suppresses small-cohort cells
  to protect participant privacy; rendering one as a zero would misrepresent a real
  provider's performance.
- "Not reported" and "reported as zero" are different facts and must stay visually
  different everywhere they appear.

## Design commitments

- **No account, no tracking.** Everything is public, static, and readable without logging in.
- **English and Spanish from the first release**, not as a later phase. A missing translation
  is a compile error, and a test fails if a Spanish string is left identical to the English.
- **Accessible**, mobile-first. The people most likely to need this are least likely to be on
  a new device with a big screen. `make web-verify` runs axe over the built pages and fails
  the build on any violation. Colour contrast still needs a browser check before launch,
  since the audit runs in jsdom, which has no layout engine.
- **Not a government site, and it says so.** The California Design System makes the pages
  look official. A non-affiliation notice sits in the banner landmark on every page, in both
  languages, rather than in footer small print.
- **Reproducible.** `make data` rebuilds every artifact from public sources; nothing is
  hand-edited, and every source is recorded in [PROVENANCE.md](PROVENANCE.md).

## Data sources

| Source | Provides |
|---|---|
| U.S. DOL Eligible Training Provider scorecard (WIOA ETA-9171) | Programs, providers, cost, length, CIP + SOC codes, outcome measures |
| CA EDD Long-Term Occupational Employment Projections (2024–2034) | Wages, job openings, growth, entry-level education, by region |
| CA EDD OEWS | Wage detail |

Full source list, licensing, access dates, and this project's provenance constraints are in
[PROVENANCE.md](PROVENANCE.md).

## Development

```bash
make install
make verify    # provenance-check, lint, typecheck, test, security, audit
```

## License

Apache 2.0. Source data is U.S. Government work (public domain) and California open data;
see [PROVENANCE.md](PROVENANCE.md) for per-source terms.
