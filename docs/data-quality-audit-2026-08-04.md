# Data quality audit — 2026-08-04

> **Archival note.** The Python package was renamed `camino` -> `afterward` on
> 2026-08-05. Paths and imports below still say `src/camino/` and `camino.sources.…`
> because this note records what was true on the date in its title; substitute
> `src/afterward/` and `afterward.` when running anything from it.

Read-only audit of the full California snapshot in `data/processed/` (3,266 programs, 764
occupation rows, 3,266 search-index rows, snapshot date 2026-08-04), read against the
pipeline in `src/camino/` and the rendering code in `web/`.

Every number below was measured, not estimated. Nothing was modified; no build was run.

Each finding is tagged:

- **PIPELINE** — this code produced or preserved the problem, and this code can fix it.
- **UPSTREAM** — genuine California / federal data messiness, faithfully carried through.
  A finding *about the data*, not a bug in this repository.
- **PRESENTATION** — the value is faithful but the way it reaches a reader misstates it.
  Fixable here, and the most dangerous category, because a faithful number shown wrong is
  indistinguishable from a wrong number.

---

## Executive summary

### First: the thing that was most likely to be wrong is not wrong

**No `-1` sentinel leaked into any program outcome field.** Across all 3,266 program records
and every nested field, there are zero `-1` values and zero empty strings.
`clean_measure()` is doing its job, and `completion_rate` reconciles exactly with
`total_completed / total_exited` for all 2,047 programs that publish it — zero
disagreements. The null-preserving contract holds end to end.

The ten `-1` values that *do* appear in `occupations.json` (one statewide, nine regional)
were checked individually and are **real**: SOC 41-3031 has `percent_change = -1.0` with
base employment 60,100 and projected 59,500, an implied change of exactly −1.0%. All nine
regional cases reconcile the same way (implied −0.95% to −1.05%). These are genuine
one-percent declines, not sentinels. The EDD feed does not use `-1` as a sentinel; it uses
blanks and `N/A`, which `_to_float()` already maps to null.

### The three findings that matter most

**1. The occupation index is contaminated with statistical aggregates, and 107 occupation
pages publish a median wage of `$0`. — PIPELINE**

`OccupationProjection.is_detailed_occupation` excludes only SOC codes ending `0000` (major
groups). SOC minor groups (`XX-X000`) and broad groups (`XX-XXX0`) pass straight through.
**101 of the 764 occupation rows are statistical aggregates, not occupations** — "Top
Executives" (11-1000), "Motor Vehicle Operators" (53-3000), "Other Production Occupations"
(51-9000). EDD publishes no wage for these rows, so they carry `median_annual_wage: 0.0`,
which `money()` renders as `$0` and `Measure` does not guard because it only guards `null`.

The dataclass already parses EDD's own `SOC Level` column into `soc_level` — and then never
uses it. The correct filter is sitting unused three lines above the broken one.

This has just got much worse. The `_attach_related()` function added to `build.py` ranks
sibling occupations by projected openings, and aggregate rows always have the most openings
by construction. Simulating the current code over the full index:

| | |
|---|---|
| "Related work" rows the current pipeline would emit | 4,574 |
| …that are statistical aggregates, not occupations | **2,436 (53.3%)** |
| …that would render a median wage of `$0` | **2,373 (51.9%)** |
| Occupation pages with ≥1 aggregate row in "Related work" | **764 of 764 (100%)** |

Worked example — `/occupations/11-1011/` ("Chief Executives") would render a *Related work*
table whose first three rows are "Other Management Occupations $0", "Operations Specialties
Managers $0", and "Top Executives $0" — the last being the category that *contains* Chief
Executives, presented as a peer of it.

Thirteen of the `$0` rows are genuine detailed occupations where EDD simply publishes no
wage (Fashion Designers, Actors, Musicians and Singers, News Analysts, Cooks — Private
Household). That part is **UPSTREAM**; treating `0` as a reported wage instead of a missing
one is **PIPELINE**. Eight programs currently show a `$0` primary occupation, and **3,333 of
15,491 regional wage rows (21.5%) render `$0`** in the by-region tables.

**2. Program earnings are a quarterly measure, shown as a bare dollar amount directly above
an annual wage. — PRESENTATION, plus UPSTREAM unit mixing**

`median_earnings` is the WIOA median earnings in the second quarter after exit — a
*quarterly* figure. Median across the dataset is $10,790; the maximum is $24,880. The
program detail page renders it as `Typical earnings after: $10,790` with **no period
label**, and then, in the panel below, `Typical pay in California: $75,444` **`per year`**.

**1,398 program pages show both figures.** The median ratio of the two is 0.156 — precisely
what you would expect from a quarterly-vs-annual comparison. A reader, a journalist, or a
provider comparing those two numbers will conclude the graduates of nearly every program in
California earn a small fraction of their occupation's wage.

Worse, the upstream field is not consistently quarterly. **14 programs report a
`median_earnings` under $100** — these are hourly wages entered in a quarterly field:

| Value | Program | Cohort |
|---|---|---|
| $16.00 | Hair Lab Twenty-Four | 11 exiters |
| $17.90 | College of the Siskiyous — Certified Nursing Assistant | 22 |
| $20.00 | Merced College — Computer and Networking Technology | 11 |
| $22.00 | Merced College — Diesel Equipment Technology | 49 |
| $24.00 | Torrance Adult School — Accounting II | 77 |

A further 33 fall between $1,000 and $2,999, implausibly low for a quarter of employment.
The mis-scaled values are **UPSTREAM**. What the site does with them is not: each of those
14 pages renders `Typical earnings after: $16` followed by `California average: $16,979 ·
Below the California average`. That is a named California training provider being told, on
a public page, that its graduates earn $16.

**3. The "California average" benchmark is not the same statistic as the per-program
measure, and 91% of programs beat it. — PRESENTATION**

The statewide benchmark from the DOL states index is `employment_rate_q2: 0.27`. The median
program reports 0.69.

| Measure | Statewide bar | Program p25 / median / p75 | Rendered "Above the California average" |
|---|---|---|---|
| `completion_rate` | 0.71 | 0.69 / 0.86 / 0.97 | 1,481 of 2,047 (**72.3%**) |
| `employment_rate_q2` | 0.27 | 0.49 / 0.69 / 0.85 | 1,609 of 1,766 (**91.1%**) |
| `median_earnings` | $16,979 | $8,700 / $10,790 / $14,138 | 185 of 1,432 (**12.9%**) |

The populations *are* the same — statewide `total_exited` is 664,260 against 662,733 summed
across the 3,266 programs (1.00×), and statewide `total_completed` is 469,808 against
468,720 (1.00×). But the employment rate is not computed the same way on both sides. Neither
`sum(employed_q2)/sum(exited)` (0.296) nor the exit-weighted mean of the published program
rates (0.449) reproduces 0.27. The statewide figure uses a larger, all-exiter denominator
that the per-program rates do not.

The consequence is a badge that is almost always green on employment (91.1%) and almost
always red on earnings (87.1%) — and in both directions it is measuring something other than
what the label claims. The site's own copy already hedges this ("the statewide average is
low, so beating it is a floor"), which suggests the asymmetry was noticed but not measured.

---

## Detailed findings

### 1. Sentinel values

| Check | Result | Verdict |
|---|---|---|
| `-1` anywhere in `programs.json` | **0** | clean |
| Empty strings anywhere in `programs.json` | **0** | clean |
| `-1` in `occupations.json` | 10 — all verified genuine −1.0% projections | clean |
| Empty strings in `occupations.json` | **0** | clean |
| `completion_rate` reconciles with `completed/exited` | 2,047 agree, **0 disagree** | clean |

Two latent notes, neither currently biting:

- `clean_measure()` (which nulls `-1`) is applied to `field_lat`, `field_lon`,
  `field_program_length_weeks` and `field_program_length_hours`, where `-1` is not a
  documented sentinel. Harmless for California — no latitude or program length can be −1 —
  but it is sentinel logic applied outside the fields the sentinel belongs to. **PIPELINE,
  latent.**
- `percent()` in `web/lib/format.ts` does `value > 1 ? value / 100 : value`. No rate in the
  dataset exceeds 1.0, so this never fires today. If the feed ever switched to a 0–100
  scale, or emitted a rounding artifact like `1.02`, that value would silently render as
  `1%`. **PRESENTATION, latent.**

### 2. Impossible and internally contradictory values

All **UPSTREAM** — the pipeline reproduces the feed faithfully. There are **no** negative
costs, negative counts, negative rates, or rates above 1.0 anywhere in the dataset.
`completion_rate` ranges 0.04–1.00; `employment_rate_q2` ranges 0.00–1.00.

| Contradiction | Count | % of 3,266 | Example |
|---|---|---|---|
| `total_exited` > `total_served` | **313** | 9.6% | `f69d0523…` Merced Adult School / Phlebotomy Technician: served 374, exited 396 |
| `credentials_earned` > `total_completed` | **179** | 5.5% | `f6903297…`: 528 credentials on 244 completions |
| `total_completed` > `total_served` | **102** | 3.1% | `f69d046b…` Bay Area Video Coalition: served 13, completed 15 |
| `employed_q4` > `total_exited` | **71** | 2.2% | `f69d0c50…`: 79 employed, 41 exited |
| `employed_q2` > `total_exited` | **65** | 2.0% | `f6903297…`: 572 employed, 467 exited |

These are explainable — WIOA cohort windows differ per measure, so exiters need not have
been served in the same reporting period, and one completer can earn several credentials.
The problem is that the page does not explain it.

**313 program pages render a visible contradiction.** The top panel shows `People enrolled:
13` (from `total_served`); the completion measure below shows `Based on 15 people` (from
`total_exited`). All 313 of these programs publish a `completion_rate`, so the "Based on"
note is actually rendered in every case. **PRESENTATION.**

Named example a provider could reasonably object to: `f69d057e…` East Los Angeles Skills
Center — Physical Therapy Aide renders "People enrolled: 49" and "Based on 79 people" on the
same screen.

### 3. `employment_rate_q2` cannot be reproduced from the counts on the page

The published rate uses a different denominator than `total_exited`.

- Programs publishing both a count and a rate: **1,766** (there are no count-only or
  rate-only records — they are always suppressed together).
- `|employed_q2/total_exited − employment_rate_q2|`: median **0.170**, p90 **0.495**,
  max 9.0.
- The two disagree by more than 10 percentage points for **1,177 of 1,766 (66.7%)**.
- Only **170 of 1,766 (9.6%)** agree within ±0.011.

Example: `f690332a…` publishes `employment_rate_q2 = 0.46` while carrying `employed_q2 =
388` against `total_exited = 273` — a ratio of 1.42.

`employed_q2` and `employed_q4` are published in `programs.json` but not rendered, so no
reader currently sees the contradiction on screen. Any downstream consumer of the JSON — the
sort of person who would check these numbers — will hit it immediately. **UPSTREAM** in
origin; **PIPELINE** in that the two are emitted side by side with no note that they are not
a numerator and denominator of each other.

### 4. Suspicious distributions

**Completion rates pile at exactly 1.00.** 443 of 2,047 (**21.6%**) report exactly 100%
completion. Nothing reports 0%. Every rate in the dataset is exactly two decimal places, so
`1.00` means "99.5%–100%" — the feed publishes a rounded percentage. **UPSTREAM.**

The pile is not only small cohorts. Median cohort among the 443 is 34 exiters; 38.4% are at
or below the 25-exiter small-sample threshold, but **8 programs report exactly 100%
completion on cohorts of 500 or more**:

| Exiters | Completed | Program |
|---|---|---|
| 1,043 | 1,043 | Project Heartbeat — EMT-B Initial Certification |
| 1,022 | 1,022 | Napa Valley College — Child & Family Studies AS |
| 884 | 884 | SF State CPaGE — Clinical Medical Assistant |
| 575 | 575 | Mendocino College — Business Management Certificate |
| 514 | 514 | Napa Valley College — Accounting-Bookkeeping |
| 505 | 505 | UCLA Extension — Data Science Certificate (Online) |

Clustering by provider is the stronger signal: **55 providers report exactly 100% on every
program they report**, five of them with five or more programs (DroneAviate UAS Pilot School
14/14, Dronitek Drone Flight Academy 7/7, Oxford Institute of Technology 7/7, California
Institute of Career Development 8/8, Merced College 6/6). UCLA Extension reports 100% on 57
of its 58 reporting programs. This is a reporting-practice pattern, not a performance
pattern, and it is worth an explicit caveat on the site.

Note that Merced College also supplies four of the 14 hourly-wage-in-an-earnings-field
records. One provider's filing habits are visibly driving several findings at once.

**Other distributions checked and found unremarkable:**

- `employment_rate_q2`: 194 at exactly 1.00, 6 at exactly 0.00, otherwise smooth.
- Cost: median out-of-pocket $3,425, max $196,290 (California Aeronautical University, BS
  Aeronautics — plausible). Round-number clustering is mild: 8.8% are exact multiples of
  $1,000, 13.2% of $500. No placeholders like 9999 or 99999.
- `median_earnings`: 295 of 1,432 are exact multiples of $100, 98 of $1,000. Consistent with
  genuine rounding, not with placeholder entry.
- Geography is clean: all 3,266 records are `state: "CA"`, all coordinates fall inside
  California's bounding box, zero null-island `(0,0)` coordinates, zero malformed ZIP codes,
  zero null cities, and 227 distinct city names with no spelling variants that collapse to
  the same normalized form.

### 5. Referential integrity

**Program identity is sound.** 3,266 distinct UUIDs across 3,266 rows — zero duplicates,
zero blanks. Shard files match the JSON documents exactly: 3,266 program shards and 764
occupation shards, with no file present on one side and absent on the other. The
search-index agrees with program detail on all eight shared fields for all 3,266 rows —
**zero disagreements**.

Four `(provider, program, city)` triples appear twice under different UUIDs — Springboard
"Data Science Career Track" and "Data Analytics Career Track", Helix Opportunity "Digital
Accessibility Developer", UC Davis "Construction Management (Certificate)". These will read
as duplicate listings in search results. **UPSTREAM**, low severity.

**SOC codes with no matching occupation — the largest referential gap.** 64 distinct SOC
codes carried by programs have no row in the occupation index, affecting 306 program-SOC
references and leaving **77 programs (2.4%) with no occupation link at all**. The gap is
concentrated in exactly the occupations that dominate California workforce training:

| SOC | References | Occupation | Nearest codes present in the EDD index |
|---|---|---|---|
| 31-1121 | 30 | Home Health Aides | 31-1120 (broad), 31-1131, 31-1132 |
| 21-1011 | 24 | Substance Abuse & Behavioral Disorder Counselors | 21-1012, 21-1018, 21-1019 |
| 31-1122 | 20 | Personal Care Aides | 31-1120 (broad) |
| 25-9042 | 19 | Teaching Assistants, Preschool/Elementary | 25-9031, 25-9044, 25-9045 |
| 23-2099 | 19 | Legal Support Workers, All Other | 23-2011 only |
| 29-2012 | 18 | Medical & Clinical Laboratory Technicians | 29-2010 (broad), 29-2031… |

This is a **SOC vintage / aggregation mismatch**: the DOL feed carries detailed codes that
EDD's projections have merged into broad or renumbered codes. The mismatch itself is
**UPSTREAM**. That the pipeline makes no attempt to roll a detailed code up to its broad
parent when the detailed row is absent is **PIPELINE** — and the fix is cheap, since the
broad parent (31-1120 for both home health and personal care aides) is already in the index.

Home health and personal care aides are among the highest-volume WIOA training categories in
California. Losing them is the most consequential single gap in the join.

**Orphan occupations.** 341 of 764 occupation rows (**44.6%**) are referenced by no program,
101 of which are the aggregate rows from Finding 1. Since
`generateStaticParams` enumerates the shard directory, that is **1,528 published occupation
pages** (764 × 2 languages), of which 682 list no programs and 202 are pages for statistical
categories that are not occupations. **PIPELINE.**

### 6. Does `coverage.json` match the files?

**Yes — every count verified.** All eleven integer fields and both derived percentages were
recomputed from `programs.json` and `occupations.json` and match exactly:

| Field | coverage.json | Recomputed |
|---|---|---|
| `total_programs` | 3,266 | 3,266 |
| `programs_with_any_outcome` | 2,057 | 2,057 |
| `programs_with_median_earnings` | 1,432 | 1,432 |
| `programs_with_employment_rate` | 1,766 | 1,766 |
| `programs_with_completion_rate` | 2,047 | 2,047 |
| `programs_with_cost` | 3,266 | 3,266 |
| `programs_with_soc` | 3,266 | 3,266 |
| `programs_matched_to_occupation` | 3,189 | 3,189 |
| `distinct_providers` | 584 | 584 |
| `distinct_occupations_matched` | 423 | 423 |
| `occupation_rows_loaded` | 764 | 764 |
| `outcome_coverage_pct` | 63.0 | 63.0 |
| `occupation_match_pct` | 97.6 | 97.6 |

Four caveats on what those correct numbers *mean*:

1. **`programs_with_cost: 3,266` (100%) overstates.** `Program.total_cost` returns a sum
   whenever any component is non-null, and tuition is never null in this snapshot. 142
   programs (4.3%) report a total out-of-pocket cost of exactly **$0** — 90 of them National
   Apprenticeship and 33 Public, where $0 is plausible, but also two Private For-Profit
   providers. Reporting 100% cost coverage is defensible but flatters the data.
2. **`occupation_rows_loaded: 764` overstates by 101.** Only 663 are detailed occupations
   (Finding 1).
3. **`programs_with_any_outcome: 2,057` uses a three-measure definition.** By the broader
   test of "any non-null outcome field", the figure is 2,099, and **1,167 programs (35.7%)
   have every outcome field null**. The 42-program difference is programs where
   `reported: false` yet cohort counts exist — those pages render "No outcomes reported for
   this program" while the panel above them displays `People enrolled: 2,500`. Example:
   `f69d3670…` BW Industries / Bitwise Industries Apprenticeship Program, served 2,500,
   exited 10. **PIPELINE**, minor.
4. **`state_benchmark` is missing from this snapshot's `coverage.json`.** `build.py` writes
   it and `web/lib/types.ts` declares it required, but the key is simply absent here — this
   `data/processed/` snapshot predates commit `85d8e6c`. Because the program page reads it
   as `getCoverage().state_benchmark` and then uses optional chaining, a missing key
   **silently removes every statewide comparison from all 2,057 outcome pages** with no
   error, no warning, and no visual difference other than three absent lines. Nothing
   validates the shape of `coverage.json` at build time. **PIPELINE.**

Confirming the staleness: this snapshot's occupation records have no `related` key, which
the current `build.py` now emits. Findings 1–5 were verified against the current source and
still hold; only the artifact is old.

### 7. Things that would embarrass this project if checked

Ranked by how badly they would read in someone else's write-up.

1. **A named provider told its graduates earn $16.** 14 program pages render `Typical
   earnings after: $16` (etc.) alongside `Below the California average`. Finding 2.
2. **`$0` published as a California median wage.** 107 occupation pages, 3,333 regional
   table rows, and — under the current pipeline — 2,373 of 4,574 related-work rows. Finding 1.
3. **Related-work tables that recommend statistical categories as jobs.** "Chief Executives"
   is shown as related to "Top Executives", the category containing it. 100% of occupation
   pages affected. Finding 1.
4. **A benchmark 91% of programs beat.** Finding 3.
5. **313 pages that contradict themselves on screen** — "People enrolled: 49 / Based on 79
   people". Finding 2 of the impossible-values section.
6. **100% completion rates that cluster by provider, not by cohort size.** 55 providers at
   100% across every program they report. Finding 4.
7. **8 broken outbound links, 5 of which are not URLs.** `program_url` values with no
   scheme — `www.amanet.org`, `www.bootcampgis.com` — render as relative links and 404. Five
   entries are free text, not addresses at all: `"E-Learning and Instructional Design UCI
   DCE"`, `"Data Science Career Track"`. A further 788 URLs are plain `http://`. **UPSTREAM**
   values, **PRESENTATION** failure — one `startsWith("http")` check would catch all eight.
8. **Raw feed artifacts left in the published JSON.** 3,223 of 3,266 `description` values
   carry a leading `NNNN|` prefix (`"6091|Covers understanding user needs to create
   products that…"`). The page component strips it with `.replace(/^\d+\|/, "")` at render
   time, so the artifact is patched in exactly one code path and shipped intact to anyone
   who reads `programs.json`. Belongs in `clean_text()`. **PIPELINE.**
9. **308 CIP codes have lost a leading zero** — `"1.0505"` where the standard code is
   `"01.0505"`. Not rendered today, but it is in the published data and would break any
   downstream CIP join. **UPSTREAM** (numeric coercion at source); trivially normalized here.
10. **77 program names render in ALL CAPS in the `<h1>`.** `tidyName()` title-cases provider
    names but is not applied to `program_name`, so headings read `NURSING ASSISTANT
    TRAINING`. Two provider names also appear in both cased and shouting forms
    (`Procareer Academy` / `PROCAREER ACADEMY`), inflating the 584 distinct-provider count.

### 8. Two measures whose meaning does not survive the trip

- **`cost.wioa_funded_cost` is not a cost to a student.** Upstream field
  `field_cost_per_wioa_num`. Non-zero for 1,603 programs; **361 exceed $100,000 and 41
  exceed $1,000,000**, topping out at **$4,636,632** (Prestige Career College — Nurse
  Assistant (Hybrid), whose out-of-pocket cost is $3,500). Divided by `total_served` the
  median is $260, which is not a tuition either. It behaves like a program-level funding
  total. It is not rendered anywhere in the UI — but it is published under a name that reads
  as a price, in a file whose whole purpose is telling people what training costs.
  **PIPELINE** naming risk.
- **`length.hours` is hours per week, not total hours.** Minimum 1, median 19, **maximum
  50**, with 98.7% at or below 40 — a total-contact-hours field would not cap at 50. Implied
  total contact hours (`weeks × hours`) has a median of 360. Only `weeks` is rendered, so no
  reader is misled today; the field ships unlabelled in `programs.json`. **PIPELINE**
  naming risk.

### 9. The "shrinking jobs" headline depends on which SOC came first

The home page reports "**219** train for jobs California expects to shrink". That count, and
the outlook filter, both read `occupations[0]` only — the first SOC the provider happened to
list. Programs carry up to three.

- Programs with more than one matched occupation: **1,490**.
- Programs where a *non-primary* occupation is shrinking but the primary is not, so the
  filter misses them: **299** — more than the 219 currently counted.
- Programs flagged shrinking on the primary while another matched occupation is growing:
  **79**. Example: `f6900f55…` "BIM Technology Certificate" is flagged on 17-3019 (−15.8%)
  while also matching Construction Managers (+10.9%) and Architectural and Civil Drafters
  (+7.0%).

The 219 figure is not wrong so much as arbitrary — it measures provider SOC-ordering as much
as it measures labor demand. Given that the README calls this "the single clearest argument
for this dataset existing", it deserves a defined rule (any matched occupation shrinking? the
highest-openings one? a weighted view?) rather than an implicit dependence on list order.
**PIPELINE.**

---

## Suggested order of work

1. Fix `is_detailed_occupation` to use the already-parsed `soc_level`, and map EDD's `0`
   wages to `null`. One-line and two-line changes; clears Finding 1, 107 `$0` pages, 3,333
   `$0` table rows, 2,373 poisoned related-work rows, and 101 phantom occupation pages.
2. Label the earnings measure with its period, and add an implausibility floor that renders
   sub-$100 quarterly earnings as unreported-with-a-note rather than as a number. Clears the
   worst provider-facing risk.
3. Either compute the statewide comparison the same way the program rates are computed, or
   stop calling it an average.
4. Roll unmatched detailed SOC codes up to their broad parent. Recovers home health and
   personal care aides — 50 program references and the largest slice of the 77 unlinked
   programs.
5. Validate `coverage.json`'s shape at build time so a missing `state_benchmark` fails
   loudly instead of silently deleting 2,057 comparisons.
6. Move the `NNNN|` description strip into `clean_text()`, normalize CIP leading zeros, and
   drop `program_url` values that are not URLs.

---

*Audit performed 2026-08-04 against `data/processed/` (snapshot 2026-08-04). Analysis only —
no files in the dataset or pipeline were modified, and no build was run.*
