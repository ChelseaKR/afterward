# Afterward

**California training programs, what happened to the people who took them, and where those
programs actually lead.**

### [afterward.chelseakr.com](https://afterward.chelseakr.com)

> Not affiliated with the State of California. It uses the state's open-source design
> system, so a permanent notice on every page says so.

3,266 California training programs, joined to the state's own ten-year projection for the
occupation each one leads to. No account, no tracking, English and Spanish.

## The problem

If you are a Californian deciding whether to spend months and thousands of dollars on a
training program, you cannot easily find out what happened to the people who finished it.
The state's workforce portal puts its training list behind an account, and the outcome data
that does exist — how many people completed, how many got jobs, what they earned — is
published by the federal government in a form no Californian is expected to find.

Meanwhile the state publishes excellent occupation data: what jobs are growing, in which
regions, and what they pay. Nobody puts the two next to each other.

Afterward does exactly that, from public data, with no account and no tracking.

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
occupation detail, and provider pages, in English and Spanish. It needs no server at
runtime.

```bash
make web-verify    # typecheck, unit tests, contrast audit, static export, axe pass
```

### Working without the network

`make data` reaches out to the U.S. DOL and California EDD. That is fine from a laptop but
not from CI — the DOL endpoint returns 403 to GitHub Actions runners, and a build should not
fail because a third party is unreachable. A 60-program fixture is committed for that:

```bash
make data-offline  # build the site dataset from fixtures/data, no network
make fixture       # regenerate the fixture after a real `make data`
```

The fixture is chosen rather than sampled, so it exercises every case the UI renders
differently: reported and unreported outcomes, a suppressed measure beside a reported one, a
shrinking occupation and a growing one, a small cohort, and a program with no matching
occupation. Fixture builds are marked `is_fixture: true` in `coverage.json`.

## Honesty about coverage

`coverage.json` is a first-class output, not a debug artifact. **Roughly a third** of
California's reported programs publish no outcome data at all — 2,057 of 3,266 report at
least one measure — and the pipeline counts and publishes that rather than hiding it. Two rules follow from this and are enforced
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
  on any violation, and separately computes the real WCAG contrast ratio for every
  foreground/background pairing the site uses, in both light and dark.
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

## CTDL export (demonstration)

`make ctdl-export` writes a demonstration export of California ETPL-derived program data as
[CTDL](https://credreg.net/) JSON-LD into `dist/ctdl/`: one `ceterms:LearningProgram` per
program the site publishes and one `ceterms:CredentialOrganization` per distinct provider
name, with occupation alignments (`ceterms:occupationType` carrying 2018 SOC codes), cost
(`ceterms:estimatedCost`) and reported outcome statistics (`ceterms:aggregateData`). It is a
projection of the already-built dataset — the same `programs.json` the site serves — so it
can never disagree with the site about what the data says, and it is deliberately not part
of `make data`, `make build`, or `make verify`.

What it is not: nothing here is published to, drawn from, or claimed about any registry.
The CTIDs are derived locally — `ce-` plus a UUIDv5 over a fixed namespace and the source's
stable program identifier, so re-export is idempotent — and are **not Registry-assigned**;
real CTIDs exist only where a registry assigns them. Known limit, on the record: credreg's
CTID grammar says "a standard UUID v4 prefixed with ce-", and v4 means random — the one
thing a deterministic re-export cannot be. This export chooses v5 so identity survives
re-export, and says so rather than pretending the tension away. The `@id` URIs live under
this project's own host for the same reason.

The dataset's honesty rules transfer whole. A suppressed or unreported measure is absent
from the CTDL entity, never zero. No property is emitted on inference: no cost when a
suppressed component makes the total a floor, no organization address (the location on a
record is the program's), no occupation title on an aggregation match (it names a broader
group than the filed code), and a program page link only where the site itself publishes
one. Every emitted term is checked against a vendored copy of the CTDL context
(`src/afterward/ctdl/ctdl-context.json`, retrieval provenance beside it) and the export
refuses to write a term the schema does not define. A coverage statement
(`ctdl-coverage.json`) is counted from the emitted graph at export time — including what
the source reports that the export deliberately does not carry, with reasons: completion
and employment *rates* have no property on `ceterms:AggregateDataProfile` and would need
the QData layer (`qdata:DataSetProfile`), which this demonstration does not use.

One schema wrinkle, recorded here because it is easy to trip over: as fetched on
2026-08-06, `ceterms:aggregateData` lists `ceterms:LearningOpportunityProfile` in its
domain, and `ceterms:LearningProgram` is a subclass of it — but credreg.net's generated
per-class property list for LearningProgram does not include `aggregateData`. This export
attaches outcome statistics to programs relying on the subclass relation; a validator that
checks the per-class list instead may disagree.

## Development

```bash
make install
make verify    # provenance-check, lint, typecheck, test, security, audit
```

## License

Apache 2.0. Source data is U.S. Government work (public domain) and California open data;
see [PROVENANCE.md](PROVENANCE.md) for per-source terms.

## Support

This is independent, unpaid work. If it has been useful to you, you can
<a href='https://ko-fi.com/T6T6GMYTU' target='_blank'><img height='36' style='border:0px;height:36px;' src='https://storage.ko-fi.com/cdn/kofi6.png?v=6' border='0' alt='Buy Me a Coffee at ko-fi.com' /></a>
