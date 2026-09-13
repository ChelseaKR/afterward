# Provenance

This file records every design input and data source used to build this project, logged at
the time of use. It exists to make the project's independent origin auditable.

## Clean-room constraint

**This project is not derived from My Career NJ (mycareer.nj.gov) or any New Jersey
workforce product, in design or implementation.** That exclusion covers the
publicly-licensed `newjersey/d4ad` / `dol-mcnj-main` repository, which has deliberately
**not** been cloned, read, or consulted as a reference at any point.

The project author previously worked on a New Jersey workforce chatbot as an employee of a
vendor (engagement ended 2026-07-21). No work product, architecture, prompt, evaluation
asset, or non-public information from that engagement is used here. This repository's first
commit postdates the end of that engagement.

`make provenance-check` enforces the exclusion mechanically: it fails the build if any
NJ-workforce reference appears anywhere in the repository outside this file.

## Permitted reference classes

1. Federal government properties and data (U.S. DOL, O\*NET, NCES, Census).
2. California state properties and data (EDD, data.ca.gov, CWDB, CCCCO, Cradle-to-Career).
3. Non-New-Jersey state workforce tools, for general product comparison only.
4. General product, accessibility, and engineering practice.

## Data sources

| # | Source | URL | Accessed | License / terms | Used for |
|---|---|---|---|---|---|
| D1 | U.S. DOL Eligible Training Provider scorecard search API (backs the public TrainingProviderResults.gov site) | `https://cxsearch.dol.gov/etp` | 2026-08-04 | U.S. Government work, public domain (17 U.S.C. §105). Public WIOA ETP performance data DOL is required to publish under WIOA §116(d)(4). | Program records, provider names, cost, length, CIP + SOC codes, WIOA outcome measures |
| D1B | U.S. DOL Eligible Training Provider bulk export (`DownloadPrograms.xlsx`) | `https://www.trainingproviderresults.gov/data/DownloadPrograms.xlsx` | 2026-09-07 | Same U.S. Government work as D1, public domain (17 U.S.C. §105). | **One column, read beside D1 and never instead of it:** `de129`, the actual denominator of the published Q2 employment rate. Not fetched by any build — an operator passes a local copy to `afterward build --bulk-export`. See "Notes on D1B" below |
| D2 | CA EDD — Long-Term Occupational Employment Projections (2024–2034) | `https://data.ca.gov/dataset/long-term-occupational-employment-projections` | 2026-08-04 | California open data, public domain | Occupation growth, job openings, median wages, entry-level education, by region |
| D3 | CA EDD — Occupational Employment and Wage Statistics (OEWS 2009–2026) | `https://data.ca.gov/dataset/oews` | 2026-08-04 | California open data, public domain | Statewide annual wage percentiles (10th, 25th, 50th, 75th, 90th) shown as the pay range on occupation pages, 2026 vintage. Fetched separately from a build, not on every one: the published extract is the whole 2009–2026 panel (~112 MB, 580,790 records) because EDD publishes no per-year resource. |
| D4 | CA EDD — Regional Planning Unit Overviews | `https://data.ca.gov/dataset/regional-planning-unit-overviews` | 2026-08-04 | California open data, public domain | Region definitions for geographic filtering |
| D5 | O\*NET Web Services (USDOL/ETA), including Mi Próximo Paso | `https://api-v2.onetcenter.org` | 2026-08-04 | O\*NET Web Services Terms of Service and Data License. **Attribution and a link are required in any product using the Services.** Registered with O\*NET under the project name "Camino", which is what this site was called until 2026-08-05; the registration is unchanged. Key is per-user and never committed. | Spanish occupation titles and descriptions from Mi Próximo Paso, on the 600 of California's 670 occupations it covers. Nothing is translated by this project: an occupation Mi Próximo Paso does not carry keeps its English name. |
| D6 | CareerOneStop Web API (U.S. DOL) | `https://api.careeronestop.org/v1` | 2026-08-04 | U.S. Government work. Requires free registration; credentials are per-user and are **never** committed. | Occupation descriptions, O\*NET skill ratings, tasks, alternate job titles, O\*NET related occupations, Bright Outlook, and typical experience / on-the-job training. Also carries the national education attainment distribution, which is parsed and typed but **not rendered anywhere on the site**; see the note below |
| D7 | Credential Engine — CTDL schema, JSON-LD context and term definitions (credreg.net) | `https://credreg.net/ctdl/schema/context/json`, `https://credreg.net/ctdl/terms/<Term>/json` | 2026-08-06 | Credential Engine publishes CTDL openly for exactly this use. Schema definitions only; **no registry data is read, and nothing is published to any registry.** | The vocabulary for the demonstration CTDL export (`make ctdl-export`): the context is vendored at `src/afterward/ctdl/ctdl-context.json` with retrieval provenance beside it, and every emitted class and property was checked against the fetched term definitions |
| D8 | U.S. Census Bureau — 2020 ZCTA-to-county relationship file | `https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_county20_natl.txt` | 2026-09-07 | U.S. Government work, public domain (17 U.S.C. §105) | The ZIP-to-county link behind the second program-placement rule. A California extract is vendored at `src/afterward/sources/zcta-county-ca-2020.csv` with retrieval provenance beside it; see the note below for why this file and not HUD's, and for what it cannot answer |
| D9 | Projections Central — state long-term occupational employment projections (Projections Managing Partnership) | `https://public.projectionscentral.org/Projections/LongTermRestJson/<state FIPS>` | 2026-09-11 | **No licence or public-domain statement is served with the data.** The site publishes a disclaimer — *"Projection data accessible from this site are the responsibility of each agency that developed the projections"* — and the Partnership is funded by USDOL/ETA, but neither the site nor the endpoint states terms. Recorded as found rather than asserted; see the note below | The occupation side of a build for any state other than California: base and projected employment, numeric and percentage change. Fetched at build time, never vendored |
| D9B | U.S. Census Bureau — ANSI/FIPS state and equivalent codes | `https://www2.census.gov/geo/docs/reference/state.txt` | 2026-09-11 | U.S. Government work, public domain (17 U.S.C. §105) | The only link between the two-letter state code the ETP feed (D1) reports and the numeric code D9 is keyed by. A two-column extract is vendored at `src/afterward/sources/state-fips-ansi.csv` with retrieval provenance beside it |

### Note on D9 — what a second state's dataset does not get, measured (#105)

`afterward build --state NV` reads its occupation figures from Projections Central rather
than from EDD, because EDD publishes California and nothing else. The adapter and the
choices behind it are in `src/afterward/sources/projections_central.py`; this records the
four measurements that shaped them, all made against the live service on 2026-09-11.

**1. The national row is served in the same array as the states.** The all-states endpoint
answers with one row per reporting state *plus* `{"Area": " United States", "STFIPS": "0"}`,
filed first, between nothing and Alabama. An adapter that took the first row, or that fell
back when its own state was absent, would publish a national figure as a state one — a real
measurement of the wrong population, which is worse than a blank because nothing on the page
contradicts it. This project asks the per-state endpoint instead, and checks every row's
`STFIPS` against the code it requested; the national row is refused by name, not filtered
out.

**2. There is no wage column at all, and the openings column is a different measure.** The
whole column set is `Area, Title, Base, Projected, Change, PercentChange, AvgAnnualOpenings,
STFIPS, StateURL, OccCode, BaseYear, ProjYear`. No median wage, no percentile spread, no
regional breakdown, no entry-level education, work experience or on-the-job training.
`AvgAnnualOpenings` is an annual average where this project's `total_job_openings` is EDD's
ten-year total: checked against the committed California dataset, EDD's figure is **10.0
times** the Projections Central figure for **all 56** occupations in it (22,890 a year
against 228,840 over the cycle for Registered Nurses). So the source's openings figure has
no field in this schema and is not carried.

Seven of the eleven occupation measures are therefore absent from a Projections Central
state, and every dataset now says which those are: `coverage.json` carries a
`projection_source` block naming the publisher, the endpoint, the period and the measures
that publisher has no column for, and `afterward.build.check_projection_source` refuses a
dataset that contradicts it in either direction. Without that, a Nevada occupation's
`median_annual_wage: null` is byte-identical to a California occupation whose wage EDD
withheld — one a fact about a publisher, the other a fact about a job.

**3. The bulk CSV the site offers is a cycle older than the JSON.**
`projections/file/longterm/csv` hands back a presigned link to `ltprojections.csv`, whose
metadata reports `lastModified 08/13/2026`. All **36,073** of its rows are the **2022-2032**
cycle, while `projections/daterange/longterm` and the JSON endpoint both serve
**2024-2034**; it also omits one state entirely (FIPS 15 — 54 states against the JSON's 55).
One download would have been cheaper than seven paginated requests and would have published
a cycle-old projection under a current date. Every record's period is read from the record.

**4. An unusable query parameter answers 404 "No results found." — the same answer a state
with no data gets.** `items_per_page` accepts 10, 25, 50, 100 and 1000; 5, 20, 200, 500 and
2000 were each measured and each answered 404. A 404 is therefore never read as "this state
publishes nothing": the adapter sends only an accepted page size, and a 404 raises.

**On the licence column.** There is no licence statement to cite, and the entry says so
rather than assuming one. That is also why nothing from this source is vendored: the two
recorded responses under `tests/fixtures/projections-central/` are test material, named as
such, and the build fetches live — the same shape as D2, and the safer one while the terms
are unstated. This is the one source in this file whose terms are not established, and a
second state's dataset should not be redistributed on the strength of an assumption about
them.

**What a second state gets, measured on Nevada, 2026-09-11.** 1,069 ETP programs from D1;
657 published projection rows, of which 649 are detailed occupations, 7 are broad
occupations and one is the all-occupations total; 648 occupations indexed after one refusal
(below); 1,042 of 1,069 programs joined to at least one occupation (97.5%). Every program is
unplaced, for the named reason `source_publishes_no_areas` — not because a crosswalk failed,
but because this source publishes no sub-state geography for any state.

**One Nevada row is refused rather than published.** `45-4029 Logging Workers, All Other`
arrives as `Base: "0", Projected: "0", Change: "0", PercentChange: "25"`. Employment is
published to the nearest ten, so the zeros are a rounding floor and the percentage was
computed before rounding. Publishing `base_employment: 0` would say nobody in Nevada does
this work, and `percent_change: 25` beside it would say a workforce of nobody is growing by
a quarter. The row contradicts itself, so it is dropped, counted, and named in
`coverage.json` under `projection_source.rows_refused`.

**And the adapter was checked against the source this project already trusts.** Projections
Central's California rows are EDD's own figures republished: over the 56 occupations in the
committed dataset, base employment, projected employment, numeric change and percentage
change agree **56 of 56, exactly**, with no rounding tolerance applied. That is what makes
the absent columns a statement about the publisher rather than a suspicion about the reader.

### Note on D9B — a code table with no names in it

The extract at `src/afterward/sources/state-fips-ansi.csv` carries the upstream file's
`STATE` and `STUSAB` columns and drops `STATE_NAME` and `STATENS`. Nothing in this
repository joins on a state's name: D1 keys on the two-letter code, D9 keys on the numeric
code, and every check the adapter makes against a fetched payload compares codes. A name
column would be fifty-seven spellings to keep in step with no join to serve.

A row in it is not a claim that anybody publishes anything for that state. Whether the ETP
feed reports programs for a state is asked of the feed (`afterward.sources.dol_etp
.fetch_states`, one aggregation, 55 reporters on 2026-09-11) and whether Projections Central
publishes projections for it is asked of Projections Central. `--state` is refused up front
against the first of those, so an unreported code is a named refusal rather than a
successful fetch of nothing.

### Notes on D8 — why the Census relationship file and not HUD's crosswalk (#126)

`area_for_city` places a program only when EDD's own area title names its city, which left
**1,741 of 3,266 programs — 53% — unplaced**, including Van Nuys, Clovis and Pleasant Hill.
A second rule places a program by the county its ZIP resolves to, where an area's own title
names that county. That rule needs a ZIP-to-county crosswalk, and there are two candidates.
This is the decision, written down before the code as #126 required, with what it was
measured on.

**Chosen: the Census Bureau's 2020 ZCTA-to-county relationship file.** Four reasons.

1. **The only thing this rule asks of a crosswalk is a county *set*, not a share.** HUD's
   USPS crosswalk gives residential and business address ratios per ZIP-county pair, and the
   rule here is "one area or unplaced" — never "the county with the largest share", which
   would be a judgement of exactly the kind this project avoids. The ratios are therefore
   not an advantage; they are a temptation the rule has already refused.
2. **It is decennial, not periodic.** The 2020 relationship files are a fixed product of the
   2020 census and do not move until the 2030 geography is published. HUD's is republished
   quarterly, so a vendored copy of it would be stale the quarter after it was taken and a
   live fetch would put a placement rule behind a third publisher's uptime. A snapshot of
   something that has stopped changing can be committed, diffed and cited.
3. **It needs no credential.** HUD's crosswalk is served through an API that requires a
   registered token. D5 and D6 already require per-user credentials and are already the two
   sources a build can silently do without; a third would put the site's geography behind a
   registration nobody but the owner can perform.
4. **It carries the county FIPS code, so the join can be keyed on the code rather than the
   name.** That is not cosmetic. The national file has a Lake County in Oregon and
   California has a Lake County of its own in a different EDD area, and a name-keyed join
   would read one as the other.

**What it cannot answer, measured rather than estimated.** A ZCTA is a census tabulation
geography, not a mailing ZIP, and DOL files a mailing ZIP in `field_zip`. Against the
2026-08-04 snapshot: **3,228 of 3,266 program ZIPs exist as ZCTAs; 38 records across 4
distinct ZIPs do not** — 90239, 93380, 93403 and 95343, which are PO Box ranges and one ZIP
unique to a single campus. Those stay unplaced and are counted under
`area_placement.unplaced_by_reason.zip_not_in_crosswalk` rather than absorbed into the
residual. HUD's file, being built from USPS delivery points, would answer for them; that is
the one thing it does better and it is worth 5 of the 1,741.

**What the rule does to the dataset, computed by the pipeline rather than typed.** On the
same snapshot, placement goes from 1,525 (46.7%) to **3,101 of 3,266 (94.9%)**: 1,525 by the
city rule and 1,576 by the county rule. The residual is 165 — **160 whose ZIP straddles two
EDD areas** (La Palma and Cypress across Los Angeles/Orange; Davis and Dixon across
Solano/Yolo; Truckee across Nevada/Placer) and the 5 with no crosswalk row. Nothing is
placed by proximity and nothing is placed on a share. The three rural Consortium regions,
which no program could ever reach by the city rule because their names are EDD coinages
rather than CBSA titles, gain 71 programs between them.

**The two rules were checked against each other before the second was trusted.** Of the
1,525 programs the city rule places, 1,440 have a ZIP the county rule also resolves cleanly,
and the two agree on **1,440 of 1,440** — no disagreements. The city rule still goes first,
because it reaches its answer without a third publisher, and `region.matched_on` on every
record says which rule spoke.

**The vendored extract keeps the out-of-state half of every border ZCTA**, which is the one
thing about it that looks like an inefficiency and is not. Seven of its 2,003 rows name a
county in Nevada or Oregon. Dropping them would complete those ZCTAs' county sets and turn a
refusal into a placement — ZCTA 89439 is half in Sierra County, California and half in Washoe
County, Nevada, and without the Washoe row it would place cleanly in the North Valley region.
The subset rule is therefore *every row of every ZCTA that touches California*, stated on the
extract's own retrieval record and enforced by a test that names those rows individually.

`scripts/zip_county_refresh.py` (`make zip-county-refresh`) re-derives the extract from the
national file and recomputes every figure in the retrieval record, so the extract is
reproducible rather than trusted. Nothing in a build fetches it.

### Note on D7 — the second opinion, and what it could and could not see

The CTDL export's own guards check it against the vendored context under D7. That check and
the export were written together, from the same reading of the same schema, so it cannot
catch a mistake in that reading. `make ctdl-validate` therefore runs the export through
[`ctdl-validate`](https://pypi.org/project/ctdl-validate/) as well — a separate published
tool with its own vendored snapshots of Credential Engine's schema encodings and a citation
for every rule it applies. It is consumed as a dependency and never modified from this
repository, it makes no network request at validation time, and it submits nothing anywhere.

On the 2026-08-07 snapshot it returned no errors and one warning, `CTID_NOT_UUIDV4`, on all
5,907 entities: the locally derived CTIDs are UUIDv5 and the published grammar says v4. That
is the tension already recorded above, arriving from the outside, and it is accepted with the
reason in `afterward.ctdl.validate.ACCEPTED_CODES` rather than filtered out. Any other finding
code fails the run.

The limit of that result is recorded with it, in `dist/ctdl/ctdl-validation.json`. That tool
drives its domain, range, inverse and unknown-term checks from the core CTDL and CTDL-ASN
schema encodings it vendors. The QData layer publishes a separate encoding at
`https://credreg.net/qdata/schema/encoding/json` (fetched 2026-08-07 for the export's own
term checks), which neither of those documents contains, so the validator could judge 4 of
the 7 classes and 17 of the 24 properties this export emits. The three classes and seven
properties outside its reach are
`qdata:DataSetProfile`, `qdata:Metric`, `qdata:Observation`, `qdata:hasMetric`,
`qdata:hasObservation`, `qdata:isObservationOf`, `qdata:median`, `qdata:metricType`,
`qdata:relevantDataSetFor` and `schema:currency` — a term the tool has never heard of is one
it declines to judge, not one it approves. Those terms rest on the QData encoding check the
export performs itself, and the counts are computed from the emitted document rather than
asserted.

### Notes on D5 — what is and is not taken from it

O\*NET's `software_skills` table was read, wired in and removed rather than published; the
measurements and the reasoning are in `docs/onet-technologies-not-shipped-2026-08-04.md`.
Job zones and work activities are likewise parsed by the client and not displayed. The tasks,
skill ratings, alternate titles and related-occupation lists on this site reach it through
CareerOneStop (D6), which serves O\*NET-derived data under its own terms — so O\*NET is
credited for those as well, and the notice below covers both routes.

The education-attainment distribution also arrives through D6 and is **not** O\*NET's: it is a
BLS measurement over the American Community Survey's occupation categories, and O\*NET is not
credited for it. It was listed here as O\*NET-derived until 2026-08-05.

### Notes on D5 — required attribution

The O\*NET Web Services Data License requires that any product using the Services credit and
link to O\*NET. The site carries this notice, and it must not be removed while any O\*NET-
derived field is displayed:

> This site incorporates information from O\*NET Web Services by the U.S. Department of Labor,
> Employment and Training Administration (USDOL/ETA). O\*NET® is a trademark of USDOL/ETA.

This obligation applies to O\*NET data reaching the site **through CareerOneStop as well**
(D6): the skill ratings, related occupations and descriptions already published are O\*NET
content served through a DOL front end. The notice therefore predates any direct use of the
O\*NET API and is owed on the currently-published site.

Base URL is `https://api-v2.onetcenter.org` — not the older `services.onetcenter.org`, which
answers every request with a 401 regardless of key. Authentication is an `X-API-Key` header.
Occupation records link their own sub-resources by `href`, so a client should follow those
rather than construct paths.

### Notes on D6

Requires a registered user id and token, read from the environment (`CAREERONESTOP_USER_ID`,
`CAREERONESTOP_TOKEN`) via a gitignored `.env.local`; see `.env.example`. Credentials are
used at build time only and never reach the browser, since the site ships as static files.

Enrichment is **optional**. With no credentials configured the pipeline runs unchanged and
occupation pages simply carry no description, skills, or related-occupation list. CI has no
credentials and builds from the committed fixture.

Responses are cached under `data/raw/cos-cache/` so a rebuild does not re-ask for data that
has not changed. One request per occupation, throttled.

The API serves English only. Passing `language=es` returns English, so D6 contributes nothing
to the Spanish pages. The Spanish occupation title and description come from O\*NET's Mi
Próximo Paso instead (D5), on 600 of the 670 occupations; the remaining 70 keep the English
name. What is still English on a Spanish page is the program description, which is the
provider's own filed text.

### Notes on D6 — the education block is published against a decision not to publish it

`docs/education-attainment-not-shipped-2026-08-05.md` decided that the national attainment
distribution should not be published, because 268 of the 670 occupations (40.0%) receive a
distribution byte-identical to another occupation's and nothing in the response says so. That
decision changed the docstrings and did not change the site. Measured 2026-08-05 against the
deployed snapshot: the seven-level distribution renders on 3,250 of the 3,266 program pages,
1,695 of the 5,514 program-occupation rows (30.7%) sit on one of the shared 268, and the
`typical_experience` / `typical_on_the_job_training` pair is the sole source of the "Getting
in" block — EDD's equivalent `work_experience` and `job_training` are parsed and never
rendered. So the row above lists them as used, because they are.

Two claims in that note were wrong about the site as it stood and are corrected in a dated
postscript inside it: "Nothing renders it", and that the distribution is "deliberately not
published anywhere on the site". Its argument against publishing was unaffected; only its
description of what was already shipped was wrong. **Withdrawing the block is now done (#20,
2026-08-07)** — a second postscript in the same file records it. `distribution` stays in the
dataset and in `web/lib/types.ts`, typed and unrendered, because the underlying BLS
measurement is real and the field EDD publishes no version of; nothing on the site renders it.

### Notes on D1

The DOL endpoint is the public search backend for `trainingproviderresults.gov`. It serves
the ETA-9171 WIOA Eligible Training Provider Performance Report data, which states are
statutorily required to report and DOL is required to publish. Access is unauthenticated and
read-only. This project queries it politely: paginated bulk reads on a quarterly refresh
cadence, cached locally, with no per-user-request traffic to DOL (the published site is
static). DOL does now publish a bulk file. It was evaluated on 2026-08-07 and this project is
staying on the search API; the reasons are in "the bulk export, evaluated" below.

### Notes on D1: `-1` has two meanings, and only one of them is suppression

`-1` in a `field_c_*` or `field_total_*` column means "not reported or suppressed", **not**
zero. The pipeline maps it to null and the UI must render it as "not reported", never as a
zero or a low score. The data dictionary (I9) gives three documented causes: a sample too small
to publish without identifying someone, no data reported for the program, or data the
Department found quality problems in.

**On `field_program_length_hours` and `field_program_length_weeks`, and nowhere else, `-1`
means the program is competency-based.** The dictionary attaches a note to those two elements
(`d113`, `d114`) that it attaches to no others: "NOTE: For this element, a suppressed value
(-1) indicates it was reported as a competency-based program." Such a program has no fixed
clock length because of how it is taught, not because anything was withheld.

`dol_etp.clean_measure` was applied to those two fields until 2026-08-07, which read the marker
as suppression. 12 of California's 3,266 programs, from 6 providers, therefore reached the site
as "length not reported" and were dropped by the length filter, publishing a deliberate design
decision as a provider's failure to answer. `dol_etp.clean_length` now reads them, and
`length.competency_based` in `programs.json` (`cb` in the search index) carries the state as
its own positive fact rather than as a null:

| Program length, California, read 2026-08-07 | Programs |
|---|---:|
| A clock length filed, in weeks and hours | 3,254 |
| Competency-based, no fixed length by design | 12 |
| Nothing filed at all | 0 |

The third row is the finding that fell out of the fix. Every California program either states a
length or states that it has none, and the 12 the site used to describe as unreported were
never in the third state. Every count here is recomputed at build time and none is asserted in
code; `build.check_length_integrity` refuses to emit a `-1` as a duration, or a record that
cannot say which of the three rows it belongs to.

### Notes on D1: the bulk export, evaluated 2026-08-07

DOL publishes `https://www.trainingproviderresults.gov/data/DownloadPrograms.xlsx` (36.2 MB,
one sheet, 57 columns, 77,085 program rows across 61 state and territory values, 4,258 of them
California). This is the file the note above used to promise a switch to. **The switch is not
being made, and the promise is resolved rather than left open.** Three reasons, each measured
against the same day's read of the search API:

1. **It carries no program identifier at all.** No `uuid`, no `nid`, no `id` and no `title`,
   although the dictionary lists the last three. Its only identifier is `provider_unique_id`,
   which the dictionary itself says "is not persistent from year to year". Every program page
   this site publishes is keyed by the API's `field_uuid`, so there is no join back and no
   stable URL to keep: switching would break every program link with nothing to migrate them
   by.
2. **It is an older vintage, and not a superset.** Joined on provider, program name, CIP and
   ZIP, 2,618 keys are shared, 646 of California's current programs are absent from the bulk
   file entirely, and 1,635 bulk rows have no counterpart in the current list. Across the 2,615
   uniquely paired programs the two disagree about half the time on every outcome measure, and
   the disagreement runs one way: the bulk file suppresses a figure the API publishes 87 to 199
   times per measure, against 13 to 61 the other way. Its newest `de172` (date added to a state
   ETP list) is 2024-09-16, while the scorecard's About page says the live data covers training
   programs on states' lists "as of June 30, 2025" and the dictionary's cover page names
   PY2022. Adopting it would move the site's figures backwards and withhold more of them.
3. **It does not close the program-year gap.** No column on it names a program year, a
   reporting period or a cycle, so the window would still have to be quoted from prose with the
   date it was read. The only date it carries is `de172`, which is when a program was added to
   a state's list, not what period its outcomes describe.

Licensing is not the obstacle: the file is the same U.S. Government work as D1, public domain
under 17 U.S.C. §105.

**What it has that the API does not**, and what a follow-up is worth opening for: seven
columns, of which `de129` is the significant one. That is the *actual denominator of the
published Q2 employment rate*, which the note below records as unpublished in the search API
and impossible to reconstruct from it. On the 1,801 California rows carrying all three figures,
`d123_total_employed_q2 / de129` reproduces the published `c_q2_employment_percent` to within
0.01 on **1,801 of 1,801**. The rest are `de130`, `de170` and `de171` (the Q4 and WIOA-exiter
denominators), `CIP_Title`, `provider_unique_id` and `de172`. The API in turn holds
`field_uuid`, `field_cluster`, `field_wioa`, `field_provider_ref` and the
dictionary-deprecated `field_tags`, plus Drupal search-index internals that are not data.

That makes the bulk file worth reading **beside** the API for one specific gap, on its own
vintage and labelled as such, and not worth reading instead of it. Nothing in this change
ingests it.

### Notes on D1B: reading the bulk export beside the API, measured 2026-09-07

The assessment above resolved, in the negative, whether to *switch* to the bulk file, and
left one thing open: "what a follow-up is worth opening for: seven columns, of which `de129`
is the significant one." `src/afterward/sources/dol_bulk.py` is that follow-up, and nothing
in it reopens the switch. The file is read for one column, joined on the same four keys, on
its own vintage, into its own block that is never merged into a D1 figure.

**What was re-measured.** The file was re-fetched on 2026-09-07: 36.2 MB, one sheet, **57
columns**, 77,085 rows across 55 `reportingstate` values, **4,171 of them California** — down
from 4,258 on 2026-08-07, so the file has been republished since the assessment. Its
California `de172` now tops out at **2024-06-30**. Over the whole file, on the 1,782
California rows carrying all three figures, `d123_total_employed_q2 / de129` reproduces the
bulk file's own `c_q2_employment_percent` to within 0.01 on **1,782 of 1,782**. The
assessment's 1,801/1,801 still holds in kind.

**A premise that moved, and it is the finding.** 1,782 of 1,782 is a fact about the bulk
file's *internal* consistency. It is not the question this site has to answer, which is
whether `de129` is the denominator of the rate **this site publishes**. Joined against the
3,266-program dataset and graded against D1's own `employment_rate_q2`:

| state | programs | what it means |
|---|---|---|
| shown | **365** | the bulk row reproduces D1's published rate; the denominator is shown |
| rate not published | 1,227 | D1 publishes no rate, so there is nothing for a denominator to sit under |
| does not reconstruct | 839 | a bulk row whose arithmetic does not reproduce D1's rate |
| no bulk row | 686 | absent from the bulk file entirely |
| bulk figure suppressed | 149 | the bulk file withholds the numerator or the denominator |

**All 839** of the non-reconstructing programs reproduce the bulk file's *own* older rate
exactly. The disagreement is not noise in the arithmetic; it is the two files being two
different reads of the same programs, which is what the assessment above concluded on other
grounds. So the denominator is publishable for **365 of 3,266 programs**, or 365 of the 2,039
that publish a rate — a far smaller number than "1,801 of 1,801" invites, and the honest one.

**The join.** Provider, program name, CIP and ZIP, as the assessment used, reproduced by the
pipeline rather than quoted: 2,578 shared keys, 686 current programs absent from the bulk
file, 1,579 bulk rows with no counterpart, 6 keys the bulk file republishes (dropped rather
than picked between) and 2 rows it cannot key at all. Against the assessment's 2,618 / 646 /
1,635 the differences are the two refreshes between the reads.

Getting there needed one repair the assessment does not mention. The bulk file files CIP
codes that have been through a binary float: `11.020099999999999` for 11.0201,
`52.020099999999999` for 52.0201. A CIP detail is two or four digits and never more, so five
or more decimals can only be that residue. Without repairing it the four-key join finds
**635** shared keys, with 2,018 more agreeing on provider and program name and disagreeing
only on a code that is the same code. `dol_bulk.repair_float_cip` rounds exactly that shape
and leaves every other width alone, including the bare series and four-digit families CIP
genuinely publishes.

**`de172` is a serial number, not a date.** It arrives as `45473`, which is 2024-06-30 in
Excel's counting from 1899-12-30. Publishing 45473 as a vintage would put a number that reads
like a measurement next to figures that are ones.

**Four states, and a fifth that is not one of them.** Every program record carries an
`employment_denominator` block: `shown`, `rate_not_published`, `bulk_figures_suppressed`,
`bulk_row_does_not_reconstruct`, or `no_bulk_row`. Above those sits `bulk_export_not_read`,
which is a fact about the *build* and not about the program — and when a build carries it,
every count in `coverage.json`'s `employment_denominator` block is `null` rather than `0`. A
build that has not looked has not found that no program has a denominator. CI always carries
it: the DOL endpoint answers a runner with 403 and nothing here fetches the file.

**What is not done.** The front end shows none of this yet. `/outcomes-coverage/` does not
carry the reconstruction rate, and no program page shows a denominator, because whether a
denominator on an older vintage may sit on a program page beside a newer rate at all — or may
appear only on `/outcomes-coverage/` as a methodological statement about the measure — is a
judgement about what this site claims, in two languages, and #127 says so. The data half is
built and measured; the rendering decision is not made here. `employment_denominator` is
deliberately absent from `SITE_COVERAGE_KEYS` for that reason: the site does not read it, and
the shape check must not claim it does.

### Notes on D1: the feed carries no program year

The scorecard publishes **no reporting-period or program-year field**, on either index. Every
key on a `etp_scorecard_programs` document and on the `etp_scorecard_states` document was
enumerated against the live endpoint on 2026-08-07, and no key on either index names a program
year, a reporting period, a cycle, or any date at all. The nearest thing to a date anywhere in
a record is `field_reportingstate`, which holds a two-letter state code. The same is true of
the machine-readable bulk export DOL publishes at
`https://www.trainingproviderresults.gov/data/DownloadPrograms.xlsx`: 58 columns, no
program-year column.

The reporting period is asserted in exactly one place, and it is prose: the scorecard's About
page (I10) says the data covers July 1, 2021 through June 30, 2025, i.e. program years 2021 to
2024. The ETP data dictionary published beside the same data (I9) still says PY2022, so the
source does not agree with itself, and neither statement is in anything a client can read
programmatically.

This is the same finding the CTDL export records from the other direction, where it is the
reason `qdata:DataSetTimeFrame` is deliberately not emitted: the source states no reporting
period, and this project does not invent one.

The consequence for anything published from this data is that the program-year window has to
be **quoted, with the date the quote was read**, and the figures stamped with the date the
record was read. `/outcomes-coverage/` does both beside every table rather than leaving a
reader to assume the figures are current, because the scorecard lags and an undated coverage
number invites a correction that would be right. `SCORECARD_PERIOD` in that page's source is
the single place the quoted window lives; it is not derived and cannot be, so a refresh
upstream can move it with nothing in this repository noticing.

There is also a bulk file now (linked above), which the "Notes on D1" paragraph about
switching to an official bulk export should be read against. Nothing in this change switches
to it.

### Notes on D1 — `employed_q2` is not the numerator of `employment_rate_q2` (#25)

Both fields ship (`employed_q2`, `employment_rate_q2` in `programs.json`). A consumer joining
them, or computing `employed_q2 / total_exited`, gets a different answer from the published
rate on 66.9% of the 1,760 programs where both are present, by more than 10 points — and 65
programs report more people employed than exited. This is not noise in the feed. The
[ETA-9171 form's own data element definitions](https://www.dol.gov/sites/dolgov/files/ETA/Performance/pdfs/ICR/ETA_9171%20PY21+.pdf)
(PY21+, OMB 1205-0526; the live URL 403s automated fetches including this project's, so this
was read via the Wayback Machine's 2024 capture) name three distinct elements:

- **DE121** (`total_exited`) — "the total number of students who completed, withdrew, or
  transferred from this program of study **in the reporting period**."
- **DE123** (`employed_q2`) — explicitly labelled "**(Numerator)**" — "the total number of
  ... exiters who were in the 2nd quarter after exit and have been determined to be in
  unsubsidized employment ... within the reporting period."
- **DE129**, the rate's actual denominator (`c_q2_employment_percent` = DE123/DE129, per the
  [TrainingProviderResults.gov data dictionary](https://www.trainingproviderresults.gov/assets/ETP_Data_Dictionary.pdf))
  — "the total number of ... exiters (completed, withdrew, or transferred) **who were in the
  2nd quarter after exit** within the reporting period."

DE121 and DE129 read almost identically and are not the same population. DE121 is every
exiter in the current reporting period, including someone who exited last month and whose 2nd
quarter after exit has not happened yet. DE129 is restricted to exiters whose 2nd-quarter
outcome could actually be determined by the time of reporting — a cohort shaped by the measurement lag every quarter-after-exit
indicator carries, not by the reporting period's exit window. `total_exited` (DE121) is
published; DE129 is not, in this feed. So `employed_q2 / total_exited` is not the calculation
DOL performs, and cannot be — the pieces are genuinely denominated differently, not loosely
related. `completion_rate` has no such gap: DE122/DE121 uses the same denominator the site
already publishes, which is exactly why it reconciles exactly across all 2,047 programs where
this project checked, while the employment pair does not.

Postscript, 2026-08-07: DE129 *is* published, in DOL's bulk export, as the column `de129`, on
that file's own older vintage. The paragraph above is unchanged as a statement about this feed,
which is what the site is built from. See "the bulk export, evaluated" above for the
reconciliation that column makes possible and for why it is not a reason to switch sources.

Both fields stay published, unreconciled, and undocumented as the same quantity by anything
downstream of the parse — `build.py`'s `search_entry` and the emitted `outcomes` block carry
a comment recording this finding beside both fields.

Postscript, 2026-08-15: the finding now travels with the data. Everything above lives in this
file and in source comments, neither of which arrives with `programs.json`, so a consumer
downloading the dataset had the two fields and no way to tell which was the rate. `coverage.json`
carries an `employment_measures` block naming `employment_rate_q2` as the measure to use,
stating that it cannot be reconstructed from anything published here, and counting — from the
emitted records, at build time, rather than typed — how far `employed_q2 / total_exited` is
from it, with `completion_rate` beside it as the control that does reconcile.
`scripts/outcome_claims_check.py` re-derives those counts from the packaged dataset and
refuses to let `make dataset-verify` pass one where the statement and the data disagree,
which is the failure this project has now met twice: a repository that was right and a
published file that was old.

## Design inputs

| # | Input | Date | What it informed |
|---|---|---|---|
| I1 | CalJOBS (caljobs.ca.gov) — the incumbent CA workforce portal | 2026-08-04 | Problem definition: account gating, buried outcomes, no comparison workflow |
| I2 | CA Career Passport pilot (CCCCO), Governor's release 2026-06-17; C2C "Informing the California Career Passport" | 2026-08-04 | Positioning: this is navigation/search, complementary to a credential wallet; non-overlapping scope |
| I3 | Newsom Master Plan for Career Education (Dec 2024 framework) | 2026-08-04 | Audience framing: pathways with or without a four-year degree |
| I4 | U.S. DOL TrainingProviderResults.gov public site | 2026-08-04 | Confirmed what federal outcome measures exist and are publishable |
| I5 | WIOA §116 / TEGL 03-18 ETP reporting guidance | 2026-08-04 | Understanding of measure definitions (Q2/Q4 employment, credential attainment, median earnings) |
| I6 | ETA-9171 form data element definitions, PY21+ (OMB 1205-0526), read via the Wayback Machine's 2024 capture — the live DOL URL 403s automated fetches | 2026-08-07 | Confirmed DE121 (`total_exited`) and DE129 (the published employment rate's actual denominator) are differently-scoped exiter cohorts, not the same population under two names; see "Notes on D1" |
| I7 | 20 CFR 677.230, 680.450, 680.470 and 680.490, read via Cornell LII and the eCFR versioner API (the eCFR HTML site answers automated fetches with a redirect to an unblock page) | 2026-08-07 | The reporting-obligation section of `/outcomes-coverage/`. **677.230(b)** is the operative exemption and says it in terms: "Apprenticeship programs registered under the National Apprenticeship Act are not required to submit ETP performance information. If a registered apprenticeship program voluntarily submits performance information to a State, the State must include this information in the report." **677.230(e)(1)** puts the UI wage-record match on the State, not the provider, which is what the page's reporting-route paragraph rests on. **680.450(b)** exempts them from initial eligibility; **680.470(a)** makes them automatically eligible while registered; **680.490** excludes them by its own heading ("providers *other than registered apprenticeship programs*"). An earlier draft of this page cited 680.470 for the performance exemption, which is wrong: 680.470(e) covers only *voluntary* reporting |
| I8 | WIOA sec. 116(d)(4) and 116(d)(6)(C), 29 U.S.C. 3141(d)(4) and (d)(6)(C), read via Cornell LII | 2026-08-07 | (d)(4): the ETP report covers "all individuals engaging in the program of study (or the equivalent)", not only WIOA participants, which is the obligation the data-linkage gap sits under. (d)(6)(C): the suppression rule is a **standard, not a threshold**. Disaggregation "shall not be required when the number of participants in a category is insufficient to yield statistically reliable information or when the results would reveal personally identifiable information". No numeric minimum cell size was found in TEGL 03-18, TEN 24-19, the ETA-9171 instructions, the ETP data dictionary, or 20 CFR 677/680, so the page states none |
| I9 | [TrainingProviderResults.gov ETP Data Dictionary v4.0](https://www.trainingproviderresults.gov/assets/ETP_Data_Dictionary.pdf), updated 2024-05-15 (cover page names PY2022, OMB 1205-0526, TEGL 03-18) | 2026-08-07 | The `-1` sentinel's three documented causes, quoted on the page and in `etplCoverage.ts`: "sample sizes that are too small to protect Personally Identifiable Information", "No data were reported for the program", or "the Department identified significant data quality issues with the state submitted data". It also carries an exception that overturned how this pipeline read two fields: on `d113_program_length_hours` and `d114_program_length_weeks` alone, "a suppressed value (-1) indicates it was reported as a competency-based program". `clean_length` now models that as its own state rather than a null. The same document is the source for `c_q2_employment_percent` = DE123/DE129, for `provider_unique_id` being non-persistent across years, and for `field_tags` being deprecated. See both "Notes on D1" sections above |
| I10 | TrainingProviderResults.gov About page (`https://www.trainingproviderresults.gov/#!/about`; the SPA route serves a shell to a fetch, so read from its Angular template at `/modules/about-page/about-page.template.html`) | 2026-08-07 | The **only** statement of which program years the scorecard covers: "training programs approved to be on states' ETP list as of June 30, 2025, covering the period from July 1, 2021, through June 30, 2025", i.e. program years 2021 through 2024. This is what `SCORECARD_PERIOD` in `web/app/[lang]/outcomes-coverage/page.tsx` quotes; the two must be updated together. The same page names states with known PY2023 data-quality problems and records that Oklahoma had not submitted PY2024 |
| I11 | California EDD Workforce Services Directive **WSD25-02**, "California Eligible Training Provider List", issued 2026-02-23 (Amendment 1, 2026-05-19), superseding WSD21-03 which superseded WSD15-07. Published as DOCX only | 2026-08-07 | The California half of the obligations section. Registered apprenticeship is the **only** category the directive exempts from performance reporting ("RAPs may voluntarily report performance information; however, they are exempt from ETP performance reporting requirements"). The California Community Colleges, UC and CSU are **not named anywhere in the directive** and have no reporting exemption: they reach the list by accreditation or public-institution status, and the numeric performance thresholds are limited to programs offered by "a private postsecondary institution". So this project must never describe a college's blank row as an exemption being used. The directive also has California's own small-n rule (a program is excused from *meeting* a measure with "less than ten students in the denominator"), which is a benchmark exemption and **not** the federal publication-suppression standard |
