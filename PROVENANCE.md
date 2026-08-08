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
| D2 | CA EDD — Long-Term Occupational Employment Projections (2024–2034) | `https://data.ca.gov/dataset/long-term-occupational-employment-projections` | 2026-08-04 | California open data, public domain | Occupation growth, job openings, median wages, entry-level education, by region |
| D3 | CA EDD — Occupational Employment and Wage Statistics (OEWS 2009–2026) | `https://data.ca.gov/dataset/oews` | 2026-08-04 | California open data, public domain | Statewide annual wage percentiles (10th, 25th, 50th, 75th, 90th) shown as the pay range on occupation pages, 2026 vintage. Fetched separately from a build, not on every one: the published extract is the whole 2009–2026 panel (~112 MB, 580,790 records) because EDD publishes no per-year resource. |
| D4 | CA EDD — Regional Planning Unit Overviews | `https://data.ca.gov/dataset/regional-planning-unit-overviews` | 2026-08-04 | California open data, public domain | Region definitions for geographic filtering |
| D5 | O\*NET Web Services (USDOL/ETA), including Mi Próximo Paso | `https://api-v2.onetcenter.org` | 2026-08-04 | O\*NET Web Services Terms of Service and Data License. **Attribution and a link are required in any product using the Services.** Registered with O\*NET under the project name "Camino", which is what this site was called until 2026-08-05; the registration is unchanged. Key is per-user and never committed. | Spanish occupation titles and descriptions from Mi Próximo Paso, on the 600 of California's 670 occupations it covers. Nothing is translated by this project: an occupation Mi Próximo Paso does not carry keeps its English name. |
| D6 | CareerOneStop Web API (U.S. DOL) | `https://api.careeronestop.org/v1` | 2026-08-04 | U.S. Government work. Requires free registration; credentials are per-user and are **never** committed. | Occupation descriptions, O\*NET skill ratings, tasks, alternate job titles, O\*NET related occupations, Bright Outlook, and typical experience / on-the-job training. Also carries the national education attainment distribution, which is parsed and typed but **not rendered anywhere on the site**; see the note below |
| D7 | Credential Engine — CTDL schema, JSON-LD context and term definitions (credreg.net) | `https://credreg.net/ctdl/schema/context/json`, `https://credreg.net/ctdl/terms/<Term>/json` | 2026-08-06 | Credential Engine publishes CTDL openly for exactly this use. Schema definitions only; **no registry data is read, and nothing is published to any registry.** | The vocabulary for the demonstration CTDL export (`make ctdl-export`): the context is vendored at `src/afterward/ctdl/ctdl-context.json` with retrieval provenance beside it, and every emitted class and property was checked against the fetched term definitions |

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
static). If DOL publishes an official bulk file, this project will switch to it.

### Notes on D1: `-1` has two meanings, and only one of them is suppression

`-1` in a `field_c_*` or `field_total_*` column means "not reported or suppressed", **not**
zero. The pipeline maps it to null and the UI must render it as "not reported", never as a
zero or a low score. The data dictionary (I7) gives three documented causes: a sample too small
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

Both fields stay published, unreconciled, and undocumented as the same quantity by anything
downstream of the parse — `build.py`'s `search_entry` and the emitted `outcomes` block carry
a comment recording this finding beside both fields.

## Design inputs

| # | Input | Date | What it informed |
|---|---|---|---|
| I1 | CalJOBS (caljobs.ca.gov) — the incumbent CA workforce portal | 2026-08-04 | Problem definition: account gating, buried outcomes, no comparison workflow |
| I2 | CA Career Passport pilot (CCCCO), Governor's release 2026-06-17; C2C "Informing the California Career Passport" | 2026-08-04 | Positioning: this is navigation/search, complementary to a credential wallet; non-overlapping scope |
| I3 | Newsom Master Plan for Career Education (Dec 2024 framework) | 2026-08-04 | Audience framing: pathways with or without a four-year degree |
| I4 | U.S. DOL TrainingProviderResults.gov public site | 2026-08-04 | Confirmed what federal outcome measures exist and are publishable |
| I5 | WIOA §116 / TEGL 03-18 ETP reporting guidance | 2026-08-04 | Understanding of measure definitions (Q2/Q4 employment, credential attainment, median earnings) |
| I6 | ETA-9171 form data element definitions, PY21+ (OMB 1205-0526), read via the Wayback Machine's 2024 capture — the live DOL URL 403s automated fetches | 2026-08-07 | Confirmed DE121 (`total_exited`) and DE129 (the published employment rate's actual denominator) are differently-scoped exiter cohorts, not the same population under two names; see "Notes on D1" |
| I7 | [TrainingProviderResults.gov ETP Data Dictionary v4.0](https://www.trainingproviderresults.gov/assets/ETP_Data_Dictionary.pdf), updated 2024-05-15 (cover page names PY2022, OMB 1205-0526, TEGL 03-18) | 2026-08-07 | The `-1` sentinel's three documented suppression causes, and the exception that overturned how this pipeline read two fields: on `d113_program_length_hours` and `d114_program_length_weeks` alone it notes that "a suppressed value (-1) indicates it was reported as a competency-based program". Also the source for `c_q2_employment_percent` = DE123/DE129. See "Notes on D1" above |
