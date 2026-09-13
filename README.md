# Afterward

**California training programs, what happened to the people who took them, and where those
programs actually lead.**

### [afterward.chelseakr.com](https://afterward.chelseakr.com)

> Not affiliated with the State of California. It uses the state's open-source design
> system, so a permanent notice on every page says so.

3,266 California training programs, 3,250 of them joined to the state's own ten-year
projection for the occupation they lead to. California publishes no projection for the
occupation the other 16 are tagged with, and the site says that rather than showing a gap
that reads like a zero. No account, no tracking, English and Spanish.

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
length, format, and the federally-reported outcome measures — and joins it to California's
own ten-year projection for the occupation it feeds: median wage, projected openings,
expected entry-level education, statewide and by region. 3,250 of the 3,266 get one. The
state publishes no projection for the occupation the other 16 are tagged with, and no
nearby occupation is substituted, because a similar-sounding job at a different wage would
look exactly like a correct answer.

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
make web-verify    # typecheck, lint, unit tests, contrast audit, static export, axe passes
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

### The rate's denominator, and how little of it can honestly be shown

The published Q2 employment rate is DE123/DE129, and **DE129 is not on the search API**, so
the site publishes a rate whose denominator it cannot show — the one figure a reader cannot
check on a site whose whole argument is that a reader must be able to. DOL's bulk export
carries it, and [PROVENANCE.md](PROVENANCE.md) settled in 2026-08 that the bulk file must not
*replace* the API and left reading it beside the API for this one gap open.

It is now read, for that one column, joined on provider, program name, CIP and ZIP, on its own
vintage, into its own block that is never merged into a scorecard figure. Pass a local copy:

```sh
afterward build --bulk-export ~/Downloads/DownloadPrograms.xlsx
```

Nothing fetches it. A build without one records `bulk_export_not_read` on every program and
`null` — not `0` — in every count, because a build that has not looked has not found that no
program has a denominator.

The result is smaller than it first looks, and that is the finding. `de129` reproduces the
**bulk file's own** rate on 1,782 of 1,782 California rows carrying all three figures. Graded
against the rate *this site publishes*, it reproduces on **365 of 3,266 programs**. 839 have a
bulk row whose arithmetic reproduces the bulk file's own older rate and not the site's — all
839 of them — which is the two files being two different reads rather than noise. Those 839
show nothing, and are counted in their own bucket rather than folded into "no data".

The front end shows none of this yet: whether a denominator on an older vintage may sit on a
program page beside a newer rate, or belongs only on `/outcomes-coverage/` as a statement
about the measure, is a judgement about what the site claims, in two languages, and it has not
been made. See PROVENANCE.md, "Notes on D1B".

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
| U.S. DOL ETP bulk export (`DownloadPrograms.xlsx`) | One column, read beside the scorecard and never instead of it: `de129`, the denominator behind the published employment rate |
| CA EDD Long-Term Occupational Employment Projections (2024–2034) | Wages, job openings, growth, entry-level education, by region |
| CA EDD OEWS | Wage detail |
| Projections Central (state long-term projections) | The occupation side of a build for any state other than California: employment now, employment projected, and the change between them |
| U.S. Census ANSI/FIPS state codes | The link between the two-letter code the ETP feed reports and the numeric code Projections Central is keyed by |

Full source list, licensing, access dates, and this project's provenance constraints are in
[PROVENANCE.md](PROVENANCE.md).

## Building a second state, and what a second state does not get

`afterward build --state NV` produces a dataset for another state. The program side has
always been state-parameterised — the ETP scorecard reports 55 states and territories, and
`--state` is checked against that list before a build starts, so an unrecognised code is a
refusal rather than a successful fetch of nothing. What is new is the occupation side:
California reads EDD directly, every other state reads Projections Central, and the two
sources do not publish the same things.

**They agree where they overlap.** Projections Central's California rows are EDD's own
figures republished: across the 56 occupations in the committed dataset, base employment,
projected employment, numeric change and percentage change agree 56 of 56 exactly.

**Seven of eleven occupation measures are absent from a second state's dataset**, and the
dataset says which. Every `coverage.json` now carries a `projection_source` block naming the
publisher, the endpoint, the period, and the measures that publisher has no column for:

| Measure | California (EDD) | Any other state (Projections Central) |
|---|---|---|
| Employment now, projected, and the change | yes | yes |
| Median annual and hourly wage | yes | **no column exists** |
| OEWS 10th–90th percentile spread | yes | no — that extract is California's |
| Ten-year job openings | yes | **no** — the source publishes an *annual average*, which is a different measure and is not carried |
| Entry-level education, work experience, on-the-job training | yes | no |
| Regional (sub-state) figures | 31 areas | no — the source publishes one figure per state |
| Spanish occupation titles | O\*NET, where it has them | the same: O\*NET is keyed by occupation, not by state |
| Occupation descriptions, skills, tasks, related occupations | CareerOneStop and O\*NET | the same |

So a second state's occupation pages would lead with growth rather than pay, and every
program would carry `region: null` with the reason `source_publishes_no_areas` — a fact
about the publisher, not a failed lookup. That last distinction is the point of the whole
block: without it, a null wage in a Nevada record is byte-identical to a California wage
EDD withheld, and `afterward.build.check_projection_source` refuses any dataset that
contradicts its own declaration in either direction.

**Hosting a second site is out of scope.** What exists is the dataset and the method.

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

## Flat CSV export, as a data package

`make csv-export` writes `dist/csv/` as a complete [Frictionless Data
Package](https://datapackage.org/): the whole dataset as one table, a Table Schema generated
from the same column definitions in the same pass, the three emitted JSON files
(`programs.json`, `occupations.json`, `coverage.json`) copied in beside it, a
`datapackage.json` declaring every one of them with its size and sha256, and a `SHA256SUMS`
derived from that descriptor rather than a hand-kept list. For the reader most likely to check
these figures — a journalist or a researcher with a spreadsheet — sharded JSON is the wrong
shape.

The JSON files are **copied** rather than referenced. A descriptor naming a file it did not
bring has a path that resolves for whoever built the package and for nobody who downloaded it,
which is a broken package that reads as a complete one. The export refuses to finish if the
descriptor ends up declaring a file that is not there, or one whose bytes do not match the hash
beside it.

The descriptor carries the two sentences a reader needs before quoting a blank — which
providers must report performance and which are exempt (`PROVENANCE.md` I7–I11), and why there
is no `suppressed` state — inside the package, rather than only in a README they may never have
downloaded.

No clock is consulted and the package version is the snapshot date, so the same snapshot writes
byte-identical output.

The design is one rule: **no blank ever carries a meaning.** Every measure has a state column
beside it, the state column is never empty, and a value cell is empty only where the state
cell says why. A reader who reaches for `fillna(0)` has been told, in the column next to the
one they filled, that there was never a number there.

The vocabulary is three words, and the fourth one that is missing is the point:

| State | Meaning |
| --- | --- |
| `reported` | A number the source filed, present in the value column beside it. |
| `not_reported` | No number. The ETP scorecard's `-1` and its empty string. |
| `competency_based` | On `length_weeks` and `length_hours` only: the programme advances on demonstrated competency and has no fixed length. A fact, not a gap. |

There is deliberately no `suppressed`. WIOA does suppress small-cohort cells, and that is why
many of these measures are absent — but the ETP scorecard serves a suppressed cell and an
unreported cell as the same `-1`, and its data dictionary calls the sentinel "not reported or
suppressed" without separating them. By the time a measure reaches the emitted record the
cause is gone. Writing `suppressed` into a cell whose cause nobody measured would be this
project's own headline failure mode wearing its opposite face: not an absence published as a
number, but an absence published as a specific cause. If the source ever separates the two,
the vocabulary can grow.

Deterministic, like the CTDL export: rows sort by `uuid`, no wall-clock appears anywhere, and
the only date in the output is the dataset's own `snapshot_date`. The export refuses to write
at all if any measure cell would end up with a blank state beside it, so a failed run leaves
no partial file to mistake for a good one. It writes nothing into `web/public/data/`, so the
bytes the site serves are untouched.

## A receipt for every program, and a verb that replays one

Every program record in the dataset has a `receipt.json` beside it, at
`/data/receipts/<uuid>.json`, and it says what this project published about that one record:

- **`record_sha256`** — the digest of the exact bytes of `programs/<uuid>.json`. Not of a
  canonical re-rendering: a reader runs `shasum -a 256 programs/<uuid>.json` on the release
  tarball and compares the string, with no rule to reimplement and nothing to take on trust.
- **Every measure's state**, in the same three-word vocabulary the flat CSV uses, read
  through the same function, so the two cannot come to different opinions about a blank.
- **How the occupation join reached each occupation**, and the program's own SOC codes, so the
  join can be audited against the table it cites.
- **What the link checker found**, and which version of the classifier found it.

**A measure that is not reported carries no number.** Its entry is exactly
`{"state": "not_reported"}` — no `value` key, no null, no zero. That rule matters more here
than on the page: a receipt is read by machines that never saw the page's caveats, and an
absence that leaks into one as a zero travels further than one on a screen.

```
afterward verify-record <uuid> --dataset afterward-dataset-<date>.tar.gz
```

recomputes that record's receipt from the dataset and reports agreement field by field.
Change one measure in a copy of the dataset and it names that field and no other. Exit codes
are **0** they agree, **1** they disagree, and **2** *nothing was compared* — no such record,
no receipt beside it, a dataset that cannot say which snapshot it is, or a schema version this
build does not know. Two is never a pass, and the word "verified" is not printed on that path.

`--receipt <path>` holds the dataset to a receipt from somewhere else — the one a page served
you — which is the reader's own question: is the page I am reading describing the record in
this release? With no `--receipt` it asks whether the archive is internally consistent, which
is the state a half-finished `make data` or a partly-synced bucket leaves behind and which no
digest of the whole archive can see.

`scripts/receipt_check.py` runs the pairing over a whole dataset on both the packaging path
(`make dataset-verify`) and the publishing path (`deploy.yml`). It is standard library only
for the same reason `dataset_shape_check.py` is: the deploy job installs Node and no Python
toolchain, and a check the publishing path cannot run guards only the path a stale dataset
never arrives by. A dataset built before receipts existed carries none; that is reported by
name and passes, because three published releases predate the feature — but it is never
reported silently, since "nothing was compared" and "everything checked out" must not print
the same way.

Two things a receipt deliberately does not carry. **The tarball's own sha256**, because
`make dataset-package` archives the whole dataset directory, receipts included, so a digest of
the archive inside the archive is a fixed point that does not exist. And **anything signed** —
ADR 0001 records that this project does not sign releases, so a receipt proves that a record
and its receipt were written by one build and claims nothing about who ran it.

Measured on the 2026-08-17 snapshot: about 1.3 KB per receipt uncompressed and about 0.5 KB
over the wire, which is roughly half again the sharded program bytes and a little over four
megabytes for the whole dataset. Deterministic, like the other artifacts: no clock is read,
measure order follows the table's own column list, and the same record writes the same bytes.

## What changed between two datasets

Every refresh replaces the dataset wholesale, and the only review it gets is the shape floors in
`dataset_check.py`: a count that did not collapse. That review cannot see the events this project
exists to notice.

`afterward diff <earlier-dataset-dir> <later-dataset-dir>` writes `changes.json` and a Markdown
summary into `dist/diff/`. `make dataset-diff` runs it against `PREVIOUS_DATASET_DIR` (an unpacked
`dataset-<date>` release) and the working dataset.

Three things happen when a programme's number disappears, and they are not the same event:

- The programme **left the list** — `program_removed`, and **no measure events at all**. Its
  measures did not stop being reported; it stopped being listed.
- The programme is still listed and **stopped reporting** that measure — `stopped_reporting`, on
  that measure, on that programme. Somebody who used to answer no longer does.
- The programme was **never on the list**, so nothing moved.

Collapsing those into "the number is gone" is the same error, one level up, that this codebase
spends its life avoiding on a single value. Outcome events are counted per measure and never
summed: nine measures moving once and one measure moving nine times are different events.

**An empty diff means "compared, and nothing moved". It never means "could not compare."** A
dataset directory that is missing, unreadable, carries no `snapshot_date`, or holds a record with
no `uuid` is a refusal that writes nothing and exits 2. Returning zero counts because there was
nothing to read would be a statement that the refresh changed nothing, published on the strength
of never having looked.

Deterministic, like the other exports: events sort by kind then by programme so the emitted order
cannot move the bytes, no wall-clock is recorded anywhere, and the only dates in the output are
the two snapshots' own. It writes into `dist/` only, so the bytes the site serves are untouched.


## Development

```bash
make install
make verify    # provenance-check, lint, typecheck, test, security, audit
```

## Development disclosure

Built AI-assisted (Claude Code). The honesty rules above bind the tooling as much as the
author: every figure the site publishes is produced by the pipeline from the sources
recorded in [PROVENANCE.md](PROVENANCE.md), the null-versus-zero rule is enforced by tests
rather than by intention, and nothing ships that the data does not support. Decisions and
their reasons are recorded as they were made, in [docs/design-log.md](docs/design-log.md)
and [docs/adr/](docs/adr/).

## AI in the product

Until 2026-08-21 there was none: no model ran at build time or runtime, and nothing on the
site was generated, summarized, or ranked by one. That is still true of the static site and
of every figure on it. What changed is recorded in
[ADR 0003](docs/adr/0003-runtime-ai-at-the-edges.md): an optional, opt-in runtime service,
`afterward.ask`, is being added in a series of changes, and this section is rewritten as
each one lands.

The shape is fixed by that ADR and does not move. A person who opts in can describe their
situation in English or Spanish; a model turns that into a structured query against the
published dataset — it structures, it does not invent — the query runs deterministically over
the same `programs.json`, `occupations.json` and `coverage.json` the site serves, and the
model narrates the records it is handed. Every substantive claim in the narration cites a
record id and is verified against the published JSON before it is shown; a claim that does
not verify is withheld and counted. A suppressed measure is narrated as not reported, never
as a zero. The only comparison the model may make is the one the site already makes, against
the median of programs reporting the same measure. Spanish produced by the model is labelled
AI-translated and unreviewed, and never alters a number. Every AI output is labelled
AI-generated, unofficial, and not a recommendation from the State of California.

Nothing in the service is deployed publicly yet. That is a decision the owner has not made;
see the ADR's "Consequences". The evaluation suites that score the service — including the
one that matters most, whether absence is ever rendered as a value — live in `evals/` with
their recorded results.

## Standards Conformance

Per the portfolio standards set. N/A rows carry their reason and an ADR; nothing is skipped
silently.

| Standard | State |
|----------|-------|
| Responsible-Tech Framework | Applies (honest record: [docs/RESPONSIBLE-TECH-AUDITS.md](docs/RESPONSIBLE-TECH-AUDITS.md)) |
| Code Quality | Applies (ruff and ESLint; `mypy --strict` over `src`, `scripts` and `tests`, not `src` alone; pytest with an 85% branch-coverage floor at 94.75% measured 2026-08-28; `tsc --noEmit` under `strict` and `noUncheckedIndexedAccess` on the front end; uv.lock, pre-commit). **Not linted:** `.ts`/`.tsx`, because `typescript-eslint` does not support TypeScript 7.0 (typescript-eslint#10940); stated in `web/eslint.config.mjs` rather than implied |
| Security & Supply-Chain | Applies (SHA-pinned actions, gitleaks, bandit, pip-audit, Dependabot, OIDC-only deploy with no static keys) |
| CI/CD | Applies (`make verify` and `make web-verify` run identically in CI; deploys are dispatch-only and refuse to run without CI green on the exact commit) |
| Observability | Applies (static-site tier: deploy-time guards, live-site smoke tests, quarterly upstream freshness checks; declared in [docs/ROADMAP.md](docs/ROADMAP.md)) |
| Performance | Applies (pre-rendered static export served from S3/CloudFront, so pages do no server round trip and ship no client data fetch). **Not yet enforced:** no performance budget is gated in CI and none has been measured, so treat this row as declared scope rather than proven numbers |
| Accessibility | Applies (WCAG 2.2 AAA target; axe and contrast gates block the build; what automation proves and what it cannot: [docs/wcag-2.2-aaa-conformance.md](docs/wcag-2.2-aaa-conformance.md)) |
| Internationalization | Applies (EN/ES ship together; typed modules instead of catalogs: [docs/I18N.md](docs/I18N.md), ADR 0002) |
| AI Evaluation | Applies since 2026-08-21 ([ADR 0003](docs/adr/0003-runtime-ai-at-the-edges.md)): the optional `afterward.ask` service has a prompt, a retrieval step and a generation surface. Committed eval suites and provenance-stamped results live in `evals/`; the static site itself still contains no model |
| Documentation | Applies (README, CHANGELOG, CONTRIBUTING, SECURITY, DISCLAIMER, PROVENANCE, design log, ADRs) |
| Quality & Metrics | Applies (metrics ledger: [docs/ROADMAP.md](docs/ROADMAP.md)) |
| Release & Versioning | N/A (not consumed downstream: ADR [docs/adr/0001-release-and-versioning-na.md](docs/adr/0001-release-and-versioning-na.md); dataset snapshots are date-tagged releases consumed only by the deploy workflow) |
| AI Development Measurement | Applies (this repo was built AI-assisted, disclosed under [Development disclosure](#development-disclosure); the runtime AI the product itself ships is a separate matter, under [AI in the product](#ai-in-the-product)). The committed, dated artifact is the metrics ledger in [docs/ROADMAP.md](docs/ROADMAP.md); no AI-usage or delivery metric gates a merge here, by design, since activity counters are diagnostic rather than outcomes |
| Incident Response | Applies (private vulnerability reporting and a stated acknowledgement expectation in [SECURITY.md](SECURITY.md), plus the in-scope and out-of-scope list). Scope is a static site with no accounts and no cookies, plus the optional `afterward.ask` service, which accepts free text and is in scope once deployed; no incident has been recorded, so there is no `docs/incidents/` yet |
| Data Governance | Applies (per-source terms and the clean-room rule in [PROVENANCE.md](PROVENANCE.md), enforced by `make provenance-check`; privacy review in [docs/RESPONSIBLE-TECH-AUDITS.md](docs/RESPONSIBLE-TECH-AUDITS.md) section C). The dataset holds no personal data, and upstream small-cohort suppression is preserved rather than reversed |

## License

Apache 2.0. Source data is U.S. Government work (public domain) and California open data;
see [PROVENANCE.md](PROVENANCE.md) for per-source terms.

## Support

This is independent, unpaid work. If it has been useful to you, you can
<a href='https://ko-fi.com/T6T6GMYTU' target='_blank'><img height='36' style='border:0px;height:36px;' src='https://storage.ko-fi.com/cdn/kofi6.png?v=6' border='0' alt='Buy Me a Coffee at ko-fi.com' /></a>
