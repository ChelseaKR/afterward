# OEWS wage distributions — assessment, 2026-08-04

Read-only assessment of source **D3, CA EDD Occupational Employment and Wage Statistics
(OEWS)**, which PROVENANCE.md has listed since the first commit as "wage detail (percentiles)
where projections lack it" but which no code has ever read.

Measured against the full published extract — `oews-2009-2026_original.csv`, 111,711,223
bytes, 580,790 rows, resolved through CKAN from dataset slug `oews` — and against the
snapshot of source D2 in `data/raw/lt-occ-emp-2024-2034.csv` (17,294 rows, 670 statewide
detailed occupations).

Every number below was measured. Nothing in the repository was modified outside the three
files this work owns, and no build was run.

Deliverable: `src/camino/sources/oews.py`, a standalone client, with `tests/test_oews.py`.
Integration is a separate step and was not attempted.

---

## Headline

**Integrate it.** The join is essentially perfect, the data adds something the projections
genuinely cannot express, and the work of reading it safely is already done.

| | |
|---|---|
| SOC join, statewide | **669 / 670 (99.9%)** |
| Area-name join | **32 / 32 (100%)** |
| Occupations gaining a full 5-percentile distribution | **657 / 670 (98.1%)** |
| Regional (area, occupation) cells gaining a full distribution | **12,189 / 12,987 (93.9%)** |
| Occupations gaining a wage they do not currently have | 1 |
| Median wage disagreements, statewide | **0 of 657** — the two sources are the same number |
| Median wage disagreements, regional | **11,292 of 11,994 (94.1%)** — and the cause is not what it looks like |

The regional disagreement is the most important finding here and is **not** a disagreement
between OEWS and the projections. It is a disagreement *inside the projections file*, which
OEWS is what let us see. Section 5.

---

## 1. What the dataset actually contains

Per row: an area, a year, an industry, a SOC code and title, a wage basis, an employment
estimate, a mean wage, the **10th, 25th, 50th, 75th and 90th percentile wages**, and a mean
relative standard error.

**It is a panel, not a snapshot.** All eighteen annual vintages from 2009 to 2026 are stacked
in one file, every one labelled `1st Qtr`. EDD's own dataset notes say the estimates "are a
snapshot in time and should not be used as a time series", because area definitions and
methods change underneath them. Anything reading this file must pick one `Year` and stay in
it. The client's `latest_year()` and `select()` exist to make that the default rather than a
thing a caller has to remember.

**Geography.** The 2026 vintage publishes 32 areas: California statewide, 28 metropolitan
areas, and 3 rural regions. OEWS types the rural three as `OES Survey Region`; the
projections type the same three as `Consortium`. The *type labels differ, the names do not*,
which is what the join actually rests on.

**SOC coding.** Six digits, unhyphenated (`151252`), which the client reformats to the
`15-1252` used everywhere else here. 844 distinct codes in 2026: 814 detailed occupations,
23 major groups, 7 broad groups. There is **no `SOC Level` column** — unlike the projections
— so the level has to be read off the code's shape. That is a real difference in the two
files' ergonomics and is the one place where OEWS is the weaker source: the projections
publish their hierarchy level explicitly, and this codebase has already been burned once by
inferring level from code shape.

**Wage basis.** Every (area, occupation) appears twice, once annual and once hourly. They are
not two measurements — annual divided by hourly is 2,080 to within a rounding cent for 99.5%
of 2026 rows. Presenting both as corroboration would be double-counting one survey.

### What it does not contain

Two things the brief anticipated, which are worth recording as absent:

- **No entry-level or experienced wage columns.** OEWS publishes these in some BLS products;
  this California extract does not. The 10th and 25th percentiles are the nearest available
  proxy for "what a new entrant might earn", and they are a proxy, not the same measure.
- **No industry detail.** `Industry Name` takes exactly two values across all 580,790 rows —
  `Total, All Industries` and `Total, All Industry` — which are two spellings of the same
  all-industry total. There is no "what does a medical assistant earn in a hospital versus a
  clinic" in this file.

---

## 2. The join, measured

### SOC codes: 669 / 670

Joining the 670 statewide detailed occupations in the projections against the 838 statewide
SOC codes in OEWS 2026, on the reformatted six-digit code:

| | |
|---|---|
| Projections statewide detailed occupations | 670 |
| Matched to an OEWS 2026 row | **669 (99.9%)** |
| Unmatched | 1 — `11-1031` Legislators |

Both feeds are on the 2018 SOC and no crosswalk is needed. This is a materially better join
than the D1→D2 program join documented in `soc-match-gap-2026-08-04.md`, and for a simple
reason: D2 and D3 are both EDD products built on the same BLS taxonomy.

169 OEWS codes have no counterpart among the projections' detailed occupations. Those are the
23 major groups, the 7 broad groups, and ~139 detailed occupations California surveys but
does not project (Astronomers, Hydrologists, Historians, Farm Labor Contractors). They are
not a loss; nothing needs them.

### Area names: 32 / 32

The 2026 OEWS area names are **character-for-character** what the projections put before their
parenthetical county gloss:

```
OEWS 2026:    "Fresno MSA"
projections:  "Fresno MSA (Fresno and Madera Counties)"
```

`ProjectionArea.short_name` already computes exactly that string, for display purposes. It
turns out to be the join key, on both sides, for all 31 non-statewide areas plus `California`.
**There is no crosswalk to write and none was written.** `area_name_joins_to_projections()`
exists only so that fact is asserted and tested in one place instead of being a coincidence a
caller leans on silently.

This is worth flagging as fragile-but-currently-free. Older vintages *in the same file* name
the same places differently — `Bakersfield MSA` (2009–2022) versus `Bakersfield-Delano MSA`
(2023–), `Sacramento--Roseville--Arden-Arcade MSA` with its doubled hyphens, `San
Diego-Carlsbad MSA` versus `San Diego-Chula Vista-Carlsbad MSA`. The client deliberately does
no normalization, prefix matching or edit-distance repair: if a future republication renames
an area, the join must fail loudly rather than quietly attribute one region's wages to
another. The test suite pins the 32 current names verbatim and asserts that a near-miss like
`Bakersfield MSA` does **not** match.

### Regional cells: 94.7%

| | |
|---|---|
| Projections regional (area, occupation) cells | 12,987 |
| Joined to an OEWS 2026 row | 12,305 (94.7%) |
| …carrying a **full** 5-percentile distribution | **12,189 (93.9%)** |
| OEWS regional cells with no projections counterpart | 3,472 |

Coverage is even across areas; the weakest is Salinas MSA (276 of 361 projections cells,
76%), the strongest Los Angeles-Long Beach-Glendale MD (695 of 704, 99%).

---

## 3. The `$0` invariant — and it is worse here than in the projections

This project has already had to fix EDD writing `0` where it has no wage: 13 occupations
rendered "$0 a year". OEWS carries the same habit and carries it far more widely, so the
client handles it at the point of parse.

**The suppression convention changes mid-file, and never mixes:**

| Vintages | Suppressed wage written as | Suppressed headcount written as |
|---|---|---|
| 2009–2017 | `0` | `0` |
| 2018–2026 | blank | blank |

In the zero-writing vintages the sentinel is *provable*, not inferred, because a suppressed
percentile is written as `0` while its neighbors are not — producing orderings no
distribution can have. Statewide Chief Executives, 2015:

```
p10 $99,662.99   p25 $158,290.67   p50 $0   p75 $0   p90 $0
```

Read literally, half of all chief executives earn nothing.

The scale of this, across all 580,790 rows:

| | |
|---|---|
| Rows whose percentiles run backwards, as published | **16,872** |
| …resolved by mapping `0` → `None` | **16,870 (99.99%)** |
| …remaining after that | 2 (one occupation, 2010, both wage bases) |

A rule that repairs 99.99% of the impossible orderings in a file is describing that file's
convention, not guessing at it.

### A second sentinel: zero employment

Also found, and also handled. 48,253 rows carry an employment estimate of `0` — **all of them
in the 2009–2017 vintages** — and **45,932 of those publish a positive wage in the same row**.
A wage estimated from an occupation that employs nobody is not a small number, it is an
impossible one. The 2018–2026 vintages contain no zero headcount at all and blank the field
instead, exactly as they do for wages.

This is the one place where the reasoning differs from job openings in the projections, where
a zero is kept because "no openings" is a coherent thing to publish. "No workers, and here is
what they are paid" is not.

### Other sentinels checked, and what was found

- **No `-1` anywhere.** Zero negative values in any numeric column, in any vintage.
- **No textual null tokens.** `N/A`, `*`, `**` and similar appear nowhere in the numeric
  columns; the only non-numeric value is the empty string (98,463 occurrences).
- **Relative standard error of exactly `0`** — 103 rows in the 2026 annual vintage. These are
  *not* a suppression sentinel: they are all Postal Service occupations plus a handful of
  small government ones (`43-5051` Postal Service Clerks, `43-5052` Mail Carriers, `11-9131`
  Postmasters, `19-3092` Geographers), which are administrative-record occupations where the
  wage is known exactly rather than sampled. A zero sampling error is the correct value.
  Recorded here because it looks like a sentinel and is not; the client parses it as a plain
  float and does not zero-map it.
- **Partial suppression is real.** One 2026 row (`27-2021` Athletes and Sports Competitors)
  publishes four percentiles and withholds only the 90th. Callers must treat the five
  percentiles as independently suppressible; the client's `is_complete` exists for this.
- **Mean outside `[p10, p90]`** — 41 rows in 2026. Not treated as an error: a sufficiently
  heavy right tail legitimately produces this. Noted so a future reader does not re-derive it.

After parsing the full file through the client: **zero `0` wages, zero `0` headcounts, and 2
non-monotonic rows out of 580,790.**

---

## 4. Which occupations gain a distribution, and which do not

Over the 670 statewide detailed occupations the projections publish:

| Outcome | Count |
|---|---|
| Full 5-percentile distribution | **657 (98.1%)** |
| Partial (4 of 5 percentiles) | 1 — `27-2021` Athletes and Sports Competitors |
| OEWS row exists, every wage suppressed | 11 |
| No OEWS row at all | 1 — `11-1031` Legislators |

The 11 fully-suppressed occupations are almost exactly the set the projections already
suppress, which is a good sign — the two products are suppressing the same thin cells:

> `17-2041` Chemical Engineers · `27-1022` Fashion Designers · `27-2011` Actors ·
> `27-2031` Dancers · `27-2042` Musicians and Singers · `27-2091` Disc Jockeys, Except Radio ·
> `27-2099` Entertainers and Performers · `27-3011` Broadcast Announcers ·
> `27-3023` News Analysts, Reporters, and Journalists · `29-1214` Emergency Medicine
> Physicians · `35-2013` Cooks, Private Household

These are the irregular- and hourly-work occupations `edd_lmi._to_wage` already documents.
**OEWS does not rescue them**, and no integration should imply that it might.

**It rescues exactly one.** Of the 13 occupations that currently have no median wage in the
projections, `13-1011` Agents and Business Managers of Artists, Performers, and Athletes gains
one: OEWS 2026 publishes a statewide median of **$99,756** and a full distribution, where the
projections file carries a literal `0`.

So: if the goal were "fill in missing medians", the answer would be no — one occupation is not
worth 112 MB. The case for OEWS is entirely about **spread**, below.

---

## 5. Median disagreements — the important finding

### Statewide: the two sources are the same number

Comparing the projections' `Median Annual Wage` against the OEWS statewide annual median, for
every occupation where both publish one:

| | |
|---|---|
| Comparable occupations | 657 |
| Agreeing to within $1 | **657 (100%)** |
| Median absolute difference | **$0** |

The projections' statewide median wage **is** the OEWS 2026 statewide median, re-published.
The same test against every other vintage confirms it: the median absolute difference grows
monotonically as you walk back — $2,273 against 2025, $4,366 against 2024, $23,213 against
2009 — and collapses to zero only at 2026. The hourly medians match too (616 of 616 within a
cent).

There is no source conflict to report at the state level, because there are not two sources.
There is one survey, published twice.

### Regional: 94% disagree, and the reason is a mixed vintage

The same comparison at regional level looks alarming:

| | |
|---|---|
| Comparable regional cells | 11,994 |
| Agreeing with OEWS **2026** to within $1 | **4 (0.03%)** |
| Disagreeing by more than 0.5% | 11,292 (94.1%) |
| Median relative difference | **+2.84%** (OEWS higher) |
| Cells where OEWS is more than 25% higher or lower | 423 (3.5%) |

Extreme cases look like genuine source conflict — `29-1229` Physicians, All Other in Modesto
MSA reads $79,411 in the projections against $332,638 in OEWS, +319%.

**It is not a source conflict.** Running the same test against every vintage:

| Comparison | Agreement within $1 |
|---|---|
| Projections **statewide** vs OEWS **2026** | 657 / 657 — **100%** |
| Projections **regional** vs OEWS **2025** | 12,018 / 12,341 — **97.4%** |
| Projections **regional** vs OEWS 2026 | 4 / 11,994 — 0.03% |
| Projections statewide vs OEWS 2025 | 0 / 650 — 0% |

**The projections file mixes two OEWS vintages: its statewide wages are OEWS 2026, its
regional wages are OEWS 2025.** The hourly figures confirm it independently (11,466 of 11,775
regional cells match OEWS 2025 to the cent).

That is a real defect in data this project already ships, found only because OEWS made it
visible. Its consequences today:

- An occupation page's statewide median and its regional medians are **one year apart**, and
  nothing on the page says so. The gap is small in the middle of the distribution (+2.84% at
  the median, roughly one year of wage growth) but reaches ±25% for 3.5% of cells and >50%
  for 0.5%, concentrated in occupations with heavy right tails where a year of sampling churn
  moves the estimate a lot.
- Comparing a region against the state, which is the natural thing a reader does, is currently
  comparing two different years.

The 323 regional cells that do *not* match OEWS 2025 are a separate and benign finding: 22 of
them sit at exactly **$34,320**, which is California's $16.50 minimum wage × 2,080 hours, and
18 of those had an OEWS estimate *below* that floor. EDD is raising sub-minimum survey
estimates to the legal minimum in the projections product. That is a defensible editorial
choice, it is not documented anywhere in the file, and anything integrating OEWS regional
wages directly will lose it — 18 cells would drop below minimum wage on the page.

**This finding stands on its own and should be actioned whether or not OEWS is integrated.**
It is not this module's to fix; recording it here is the deliverable.

---

## 6. What OEWS adds that the projections cannot

The projections publish one number per occupation. That number is the same number OEWS
publishes. What OEWS adds is everything around it — and the spread is large enough that the
median alone is genuinely misleading for most occupations.

Across the 657 occupations with a full statewide distribution:

| | |
|---|---|
| p90 ÷ p10, median | **2.19×** |
| p90 ÷ p10, range | 1.01× (Taxi Drivers) to 7.83× (Commercial Pilots) |
| p75 ÷ p25, median | 1.54× |
| Interquartile width as a share of the median | **43%** |
| Occupations where p90 is at least 2× the median | 44 |
| Occupations where p10 is below 70% of the median | **350 (53%)** |

Concretely, at the state level in 2026:

| Occupation | 10th | 25th | median | 75th | 90th | spread |
|---|---|---|---|---|---|---|
| Registered Nurses | $104,095 | $125,867 | $144,197 | $178,018 | $219,291 | 2.1× |
| Medical Assistants | $40,285 | $47,411 | $50,918 | $63,437 | $79,258 | 2.0× |
| Licensed Practical / Vocational Nurses | $66,192 | $76,935 | $81,982 | $96,343 | $103,262 | 1.6× |
| Nursing Assistants | $41,126 | $47,011 | $48,836 | $56,188 | $62,648 | 1.5× |
| Pharmacy Technicians | $44,049 | $47,730 | $56,653 | $67,426 | $83,463 | 1.9× |
| Automotive Service Technicians | $39,260 | $47,897 | $66,817 | $79,239 | $97,974 | 2.5× |
| Heavy and Tractor-Trailer Truck Drivers | $42,746 | $49,807 | $61,548 | $73,913 | $83,754 | 2.0× |
| Software Developers | $108,001 | $140,825 | $179,292 | $222,735 | $280,303 | 2.6× |

This is directly the question the brief poses. Someone weighing a year of training on
"Medical Assistants: $50,918" is being shown a number that a quarter of the occupation earns
less than $47,411 against, and that the top tenth exceeds by $28,000. Two occupations with
nearly identical medians can have quite different floors — Nursing Assistants and Medical
Assistants sit $2,000 apart at the median but $6,600 apart at the 90th percentile, and LVNs
have both a much higher floor ($66,192) and a *narrower* ceiling than their median suggests.
The entry-level end is what a career-changer actually faces first, and the projections do not
publish it at all.

Regional spread is comparable (median p90/p10 of 2.03×) and adds a second axis: Registered
Nurses' median ranges from $106,346 in El Centro MSA to $222,807 in San Jose-Sunnyvale-Santa
Clara MSA, a 2.1× swing across California that a statewide distribution alone conceals.

---

## 7. Recommendation

**Integrate, with four conditions.**

The case for: the join is 99.9% on SOC and 100% on area names with no crosswalk to write; 98%
of occupations gain a full distribution; the spread is large enough (43% of the median across
the interquartile range, and 53% of occupations with a p10 below 70% of their median) that a
lone median materially understates the risk and the upside of a training decision; and it is
the source PROVENANCE.md has claimed for this purpose since day one, so integrating it makes
the provenance record true rather than aspirational.

The conditions:

1. **Pin the vintage explicitly and show it.** Never read the file without selecting a year.
   `latest_year()` should be preferred to a literal, since EDD appends a vintage annually and
   a hard-coded year goes stale while still parsing cleanly.

2. **Fix the mixed vintage in the projections first, or label it.** Section 5. Adding OEWS
   2026 distributions beside projections regional medians sourced from OEWS 2025 would put
   two vintages of the same survey on one page, in adjacent components, with a p50 that does
   not match the p50 in the distribution next to it. That is worse than the current state.
   The cleanest resolution is to take *all* wage figures — statewide and regional, median and
   percentiles — from OEWS at one pinned vintage, and let the projections supply what only
   they have: growth, openings, education and training requirements.

3. **Do not present the hourly rows as independent corroboration.** They are the annual
   figure ÷ 2,080.

4. **Do not imply the 11 suppressed occupations are merely missing regional detail.** They
   are suppressed in both products, for the same reason, and the honest label is the one the
   codebase already uses: not reported.

On cost: a 112 MB download on the same quarterly refresh cadence as the existing sources,
buffered once and filtered to ~16,600 rows for one vintage and basis. That is the largest
single fetch in the project, and it is the only real objection. It is not enough of one — the
file is fetched at build time, never by a reader, and the site ships static.

### What is deliberately not in the module

- No crosswalk, normalization or fuzzy matching on area names. The exact join works today; a
  future rename must break loudly.
- No repair of non-monotonic rows beyond the zero-sentinel rule. `is_monotonic` reports;
  it does not reorder. Two rows in eighteen years fail it, and silently sorting them would
  destroy the cheapest available detector of a *new* sentinel in a future republication.
- No mapping of broad-group codes to the detailed occupations underneath them.
  `soc_vintage.py` already owns that decision and owns the justification for each row of it.
