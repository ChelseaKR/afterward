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
| D3 | CA EDD — Occupational Employment and Wage Statistics (OEWS 2009–2026) | `https://data.ca.gov/dataset/oews` | 2026-08-04 | California open data, public domain | Wage detail (percentiles) where projections lack it |
| D4 | CA EDD — Regional Planning Unit Overviews | `https://data.ca.gov/dataset/regional-planning-unit-overviews` | 2026-08-04 | California open data, public domain | Region definitions for geographic filtering |
| D5 | O\*NET Database | `https://www.onetcenter.org/database.html` | pending | CC BY 4.0 (attribution required) | Skills/tasks per SOC; occupation adjacency (Phase 2) |

### Notes on D1

The DOL endpoint is the public search backend for `trainingproviderresults.gov`. It serves
the ETA-9171 WIOA Eligible Training Provider Performance Report data, which states are
statutorily required to report and DOL is required to publish. Access is unauthenticated and
read-only. This project queries it politely: paginated bulk reads on a quarterly refresh
cadence, cached locally, with no per-user-request traffic to DOL (the published site is
static). If DOL publishes an official bulk file, this project will switch to it.

Sentinel value: `-1` in a `field_c_*` or `field_total_*` column means "not reported or
suppressed", **not** zero. The pipeline maps it to null and the UI must render it as
"not reported" — never as a zero or a low score.

## Design inputs

| # | Input | Date | What it informed |
|---|---|---|---|
| I1 | CalJOBS (caljobs.ca.gov) — the incumbent CA workforce portal | 2026-08-04 | Problem definition: account gating, buried outcomes, no comparison workflow |
| I2 | CA Career Passport pilot (CCCCO), Governor's release 2026-06-17; C2C "Informing the California Career Passport" | 2026-08-04 | Positioning: this is navigation/search, complementary to a credential wallet; non-overlapping scope |
| I3 | Newsom Master Plan for Career Education (Dec 2024 framework) | 2026-08-04 | Audience framing: pathways with or without a four-year degree |
| I4 | U.S. DOL TrainingProviderResults.gov public site | 2026-08-04 | Confirmed what federal outcome measures exist and are publishable |
| I5 | WIOA §116 / TEGL 03-18 ETP reporting guidance | 2026-08-04 | Understanding of measure definitions (Q2/Q4 employment, credential attainment, median earnings) |
