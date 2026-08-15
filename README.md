# Afterward

**California training programs, what happened to the people who took them, and where those
programs actually lead.**

### [afterward.chelseakr.com](https://afterward.chelseakr.com)

> Not affiliated with the State of California. It uses the state's open-source design
> system, so a permanent notice on every page says so.

3,266 California training programs, joined to the state's own ten-year projection for the
occupation each one leads to. No account, no tracking, English and Spanish.

**Status:** Beta. Version `0.1.0`, first signed tag not yet cut. The public site, the bilingual
interface, and the data pipeline are live and covered by an automated test suite. Datasets are
tagged separately per build (latest `dataset-2026-08-07`). Independent personal project.

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
shrinking occupation and a growing one, a small cohort, a competency-based program, and a
program with no matching occupation. Fixture builds are marked `is_fixture: true` in
`coverage.json`.

## Honesty about coverage

`coverage.json` is a first-class output, not a debug artifact. **More than a third** of
California's reported programs publish no outcome data at all — 1,209 of 3,266, while the
other 2,057 report at least one measure — and the pipeline counts and publishes that rather than hiding it. Two rules follow from this and are enforced
in code:

- A withheld or suppressed measure is `null`, never `0`. WIOA suppresses small-cohort cells
  to protect participant privacy; rendering one as a zero would misrepresent a real
  provider's performance.
- "Not reported" and "reported as zero" are different facts and must stay visually
  different everywhere they appear.
- And a null is not always "not reported". The scorecard writes `-1` for a suppressed value
  everywhere except the two program-length fields, where it means the program is
  competency-based: it finishes when the student can do the work, so it has no fixed length by
  design. 12 of California's 3,266 programs say that, and the site says it back rather than
  calling them unreported. Every rule here cuts both ways, and this is the direction that is
  easier to miss: publishing an absence over a fact is the same error as publishing a zero
  over a blank. See [PROVENANCE.md](PROVENANCE.md), "Notes on D1".

`/outcomes-coverage/` takes that headline apart in public, in both languages: which measure is
missing, from which kind of provider, and against how large a group. It exists because nobody
else publishes the number. California's ETPL is a CalJOBS search screen with no export behind
it, so the federal scorecard is the only record the question can be asked of, and the answer
is two different gaps rather than one: 1,167 of the 1,209 silent programs filed no cohort
count either, so there is no record for a measure to be missing from. Median earnings is the
measure most often absent, and the only one whose absence cohort size does not explain.
The measures also split by who produces them, with no overlap: everything the provider files
is published more often than everything the state produces by matching a roster against wage
records. Provider categories are ordered by size and never by how much each leaves blank, with
the reporting obligations that legitimately differ between them stated beside the table: an
apprenticeship program with an empty row is doing what 20 CFR 677.230(b) asks of it, and a
community college with one is not, because California's directive exempts nobody else. Every
figure carries the program-year window and the date the record was read. The scorecard
publishes no program-year field anywhere in its data, states the window only in prose on its
About page, and its data dictionary still names an earlier year.

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
(`ceterms:estimatedCost`) and reported outcome statistics as one `qdata:DataSetProfile` per
program carrying `qdata:Metric`/`qdata:Observation` pairs, linked to the program both ways
(`qdata:relevantDataSet` / `qdata:relevantDataSetFor`). It is a
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
the source reports that the export deliberately does not carry, with reasons.

### Checking it with something that is not itself

Every guard above is written by the same hand as the export, against the same reading of the
same schema — which is the reading a mistake would survive. So the export is also put through
[`ctdl-validate`](https://pypi.org/project/ctdl-validate/), a separate published tool with its
own vendored copies of Credential Engine's schema encodings and a citation for every rule it
applies. It is consumed as an ordinary dependency and never modified from here.

```bash
make ctdl-validate   # exports, then validates, and writes dist/ctdl/ctdl-validation.json
```

What it found, on the 2026-08-07 snapshot: **no errors, and one warning, 5,907 times.** The
warning is `CTID_NOT_UUIDV4`, on every entity in the graph — the tension this export already
declared in writing, that a CTID is specified as a random UUIDv4 and a deterministic
re-export cannot use one. Nothing else fired: no domain violation, no range violation, no
unresolved reference, no inverse mismatch, no undeclared term. Every finding code has to be
listed in `ACCEPTED_CODES` with a reason or the run fails, so an accepted warning stays a
decision on the record rather than a filter, and a new class of finding cannot arrive quietly.

The scope of that result is published beside it, because a clean run over terms nobody checked
is not evidence. `ctdl-validate` drives its domain, range, inverse and unknown-term checks from
the schema encodings it vendors — core CTDL and CTDL-ASN — and the QData layer publishes its
own encoding at `https://credreg.net/qdata/schema/encoding/json`, which neither of those
contains. So the validator could judge 4 of the 7 classes and 17 of the 24 properties this
export emits; the three classes and seven properties it could not are the QData
outcome-statistics layer plus `schema:currency`. Those terms rest on the QData encoding check
the export runs itself. The counts are computed from the emitted document against the
validator's own schema index, not asserted.

### What it does not carry

A coverage statement that counts only what was emitted describes a projection as though it
were the whole record. `ctdl-coverage.json` therefore also counts the other half: eight things
the ETPL record says that this export drops, each with the CTDL term that would have carried
it where such a term exists. On the 2026-08-07 snapshot, and every figure below is counted by
the export rather than typed here:

| The source says | Programs | CTDL term that would carry it |
|---|---|---|
| The CIP code for the field of study | 3,266 | `ceterms:instructionalProgramType` |
| Online, in person, or both | 3,266 | `ceterms:learningDeliveryType` |
| How long the program takes | 3,266 | `ceterms:estimatedDuration` |
| Where the program is offered | 3,266 | `ceterms:availableAt` |
| What kind of provider it is | 3,266 | `ceterms:agentSectorType` |
| What it costs a student funded under WIOA | 3,266 | `ceterms:CostProfile` + `ceterms:directCostType` |
| The state's ten-year outlook for the occupation | 3,250 | none used |
| Four of the nine reported outcome measures | 2,099 | `qdata:Metric` / `qdata:Observation` |

Where a term is named, the vocabulary has somewhere to put the field and this export does not
use it — a gap in the export, not a limit of CTDL, and stated that way. Three of them turn on
the same documented rule: `learningDeliveryType`, `agentSectorType` and `directCostType` all
take a concept from a scheme credreg.net serves as an HTML page rather than as fetchable data,
and this export emits no concept it cannot check against machine-readable data. The occupation
projections are the one refusal rather than an omission: they describe an occupation, not this
program, and hanging them off the program would assert that the program leads to that wage,
which the source does not say. The SOC alignment is carried; the projection is not.

`/ctdl/` publishes all of this, in both languages, beside the validator's findings.

### Getting the export, and rebuilding it

Two statements are committed and served, because they are about a kilobyte each and because
committing them makes every figure on `/ctdl/` a reviewable diff rather than an invisible
build artifact:

- `web/public/ctdl/ctdl-coverage.json` → `https://afterward.chelseakr.com/ctdl/ctdl-coverage.json`
- `web/public/ctdl/ctdl-validation.json` → `https://afterward.chelseakr.com/ctdl/ctdl-validation.json`

The graph itself is ~17 MB and is never committed, on the same rule the dataset follows.
`make ctdl-package` writes `dist/afterward-ctdl-<snapshot>.jsonld.gz` (~1.5 MB) with a
`.sha256` beside it, for attaching to a release. To rebuild the whole thing from public
sources:

```bash
make install                       # Python toolchain, via uv
make data                          # fetches from U.S. DOL and CA EDD into web/public/data/
make ctdl-export                   # dist/ctdl/learning-programs.jsonld + ctdl-coverage.json
make ctdl-validate                 # + ctdl-validation.json, and fails on anything unaccounted for
make ctdl-statements               # copies the two statements into web/public/ctdl/
make ctdl-package                  # gzip + sha256, into dist/
```

Everything downstream of `make data` is deterministic — same dataset, byte-identical output —
so a rebuild can be diffed against a published one directly. That is also why there is no
generation timestamp anywhere in the output: the only date it carries is the dataset's own
`snapshot_date`, which is the date that actually identifies what the file describes. A
wall-clock stamp would change the bytes on every run and make exactly that comparison
impossible.

Provenance for the export, in one place: the source data is D1 (U.S. DOL ETP scorecard) and
D2/D3 (CA EDD) at the `snapshot_date` recorded in every statement; the vocabulary is D7
(credreg.net), vendored with its retrieval date and SHA-256 in
`src/afterward/ctdl/ctdl-context.source.json`; the method is `src/afterward/ctdl/export.py`,
which records beside each mapping the definition it was checked against. See
[PROVENANCE.md](PROVENANCE.md).

Outcome statistics originally used `ceterms:aggregateData`, which surfaced a schema gap —
`ceterms:LearningProgram` missing from that property's per-class enumeration — filed as
[Schema-Development #1080](https://github.com/CredentialEngine/Schema-Development/issues/1080).
The maintainers' answer settled the design: the Credential Registry no longer accepts
`aggregateData` for publishing, and the supported pattern is the QData layer this export
now uses. The move also made the source's completion and employment *rates* projectable
(`qdata:percentage`, source fraction × 100 — a documented unit conversion the round-trip
guard applies identically), where `AggregateDataProfile` had no rate property at all. Every
QData term was verified against the schema encoding fetched 2026-08-07 from credreg.net;
`qdata:metricType` concepts come from the machine-readable `qdata:MetricCategory` scheme in
that same file. `qdata:DataSetTimeFrame` is deliberately not emitted: the source states no
reporting-period dates, and the export does not invent them.

## Development

```bash
make install
make verify    # provenance-check, lint, typecheck, test, security, audit
```

## Development disclosure

Built AI-assisted (Claude Code). The honesty rules above bind the tooling as much as the
author: every figure the site publishes is produced by the pipeline from the sources
recorded in [PROVENANCE.md](PROVENANCE.md), the null-versus-zero rule is enforced by tests
rather than by intention, and nothing ships that the data does not support. There is no AI
in the product itself: no model runs at build time or runtime, and nothing on the site is
generated, summarized, or ranked by one. Decisions and their reasons are recorded as they
were made, in [docs/design-log.md](docs/design-log.md) and [docs/adr/](docs/adr/).

## Standards Conformance

Per the portfolio standards set. N/A rows carry their reason and an ADR; nothing is skipped
silently.

| Standard | State |
|----------|-------|
| Responsible-Tech Framework | Applies (honest record: [docs/RESPONSIBLE-TECH-AUDITS.md](docs/RESPONSIBLE-TECH-AUDITS.md)) |
| Code Quality | Applies (ruff, mypy --strict, pytest with an 85% branch-coverage floor at 91.62% measured, uv.lock, pre-commit) |
| Security & Supply-Chain | Applies (SHA-pinned actions, gitleaks, bandit, pip-audit, Dependabot, OIDC-only deploy with no static keys) |
| CI/CD | Applies (`make verify` and `make web-verify` run identically in CI; deploys are dispatch-only and refuse to run without CI green on the exact commit) |
| Observability | Applies (static-site tier: deploy-time guards, live-site smoke tests, quarterly upstream freshness checks; declared in [docs/ROADMAP.md](docs/ROADMAP.md)) |
| Performance | Applies (pre-rendered static export served from S3/CloudFront, so pages do no server round trip and ship no client data fetch). **Not yet enforced:** no performance budget is gated in CI and none has been measured, so treat this row as declared scope rather than proven numbers |
| Accessibility | Applies (WCAG 2.2 AAA target; axe and contrast gates block the build; what automation proves and what it cannot: [docs/wcag-2.2-aaa-conformance.md](docs/wcag-2.2-aaa-conformance.md)) |
| Internationalization | Applies (EN/ES ship together; typed modules instead of catalogs: [docs/I18N.md](docs/I18N.md), ADR 0002) |
| AI Evaluation | N/A (no model, prompt, retrieval, or generation surface anywhere in the product; declared in [docs/ROADMAP.md](docs/ROADMAP.md)) |
| Documentation | Applies (README, CHANGELOG, CONTRIBUTING, SECURITY, DISCLAIMER, PROVENANCE, design log, ADRs) |
| Quality & Metrics | Applies (metrics ledger: [docs/ROADMAP.md](docs/ROADMAP.md)) |
| Release & Versioning | N/A (not consumed downstream: ADR [docs/adr/0001-release-and-versioning-na.md](docs/adr/0001-release-and-versioning-na.md); dataset snapshots are date-tagged releases consumed only by the deploy workflow) |
| AI Development Measurement | Applies (this repo was built AI-assisted, disclosed under [Development disclosure](#development-disclosure); the product itself ships no model). The committed, dated artifact is the metrics ledger in [docs/ROADMAP.md](docs/ROADMAP.md); no AI-usage or delivery metric gates a merge here, by design, since activity counters are diagnostic rather than outcomes |
| Incident Response | Applies (private vulnerability reporting and a stated acknowledgement expectation in [SECURITY.md](SECURITY.md), plus the in-scope and out-of-scope list). Scope is a static site with no accounts, no cookies, and no user-submitted input; no incident has been recorded, so there is no `docs/incidents/` yet |
| Data Governance | Applies (per-source terms and the clean-room rule in [PROVENANCE.md](PROVENANCE.md), enforced by `make provenance-check`; privacy review in [docs/RESPONSIBLE-TECH-AUDITS.md](docs/RESPONSIBLE-TECH-AUDITS.md) section C). The dataset holds no personal data, and upstream small-cohort suppression is preserved rather than reversed |

## License

Apache 2.0. Source data is U.S. Government work (public domain) and California open data;
see [PROVENANCE.md](PROVENANCE.md) for per-source terms.

## Support

This is independent, unpaid work. If it has been useful to you, you can
<a href='https://ko-fi.com/T6T6GMYTU' target='_blank'><img height='36' style='border:0px;height:36px;' src='https://storage.ko-fi.com/cdn/kofi6.png?v=6' border='0' alt='Buy Me a Coffee at ko-fi.com' /></a>
