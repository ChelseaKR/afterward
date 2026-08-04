# The 77 unmatched programs — 2026-08-04

Read-only investigation of the SOC join between source D1 (DOL ETP programs) and source D2
(CA EDD long-term occupational projections), measured against the snapshot in
`data/processed/` (3,266 programs, 670 statewide detailed occupation rows).

Deliverable: `src/camino/sources/soc_vintage.py`, a standalone mapping module. Nothing else
in the repository was modified and no build was run.

## Headline

| | |
|---|---|
| Programs in the snapshot | 3,266 |
| Matched to at least one occupation today | 3,189 (97.6%) |
| **Recoverable with a cited, defensible mapping** | **61** |
| Matched after the mapping | 3,250 (99.5%) |
| **Genuinely unmatchable, refused** | **16** (0.5%) |

Secondary effects on programs that already matched: occupation attachments rise from 5,379
to 5,514 (+135), and the number of distinct occupations any program reaches rises from 423
to 433. 172 of the 306 dead SOC-code slots in the corpus are closed.

## The premise was wrong, and that matters

The earlier audit's hypothesis — that the two feeds sit on different SOC revisions and that
the healthcare-support codes were renumbered between them — does not survive contact with
the BLS crosswalk. Checked in
[`soc_2010_to_2018_crosswalk.xlsx`](https://www.bls.gov/soc/2018/soc_2010_to_2018_crosswalk.xlsx):

- `21-1011` Substance Abuse and Behavioral Disorder Counselors and `21-1014` Mental Health
  Counselors — the two codes behind 19 of the 77 — are **identical in the 2010 and 2018
  SOC**, same code, same title. Nothing was renumbered.
- `31-1121` Home Health Aides and `31-1122` Personal Care Aides *are* 2018 codes (from 2010's
  `31-1011` and `39-9021`), but EDD is not on the 2010 SOC either. EDD publishes `19-3033`
  Clinical and Counseling Psychologists, `13-1082` Project Management Specialists and
  `29-2072` Medical Records Specialists, all of which exist only in the 2018 SOC.

**Both feeds are on the 2018 SOC.** Had the module been built on the vintage hypothesis it
would have mapped `21-1011` by inventing a renumbering that never happened, and any
resemblance of the result to the truth would have been luck.

The real mismatch is **level of aggregation**. D1 tags a program with a *detailed* 2018 SOC
occupation. D2 follows the BLS publication taxonomy, which for some occupations produces no
separate estimate and reports them only inside a larger occupation. Two shapes:

1. **SOC broad group.** EDD publishes `31-1120` Home Health and Personal Care Aides, the
   broad group, and never its members `31-1121`/`31-1122`. Seven such groups appear in the
   EDD snapshot. Confirmed against
   [`soc_structure_2018.xlsx`](https://www.bls.gov/soc/2018/soc_structure_2018.xlsx).
2. **BLS hybrid code.** Five codes EDD publishes — `21-1018`, `25-2052`, `25-9045`,
   `51-2028`, `53-1047` — appear **nowhere in the 2018 SOC**. They exist only in the BLS
   publication taxonomy, which defines each as the union of named SOC occupations BLS cannot
   estimate separately. O\*NET calls them "2018 hybrid SOC occupations".

A useful confirmation: EDD's own `SOC Level` column marks all twelve of these aggregates as
level 4, its most detailed level. EDD is not withholding detail it has; there is no CA
estimate below these codes to withhold.

## Method and sources

Every row was confirmed from **both ends** before it was written down.

| # | Source | URL | What it settled |
|---|---|---|---|
| S1 | BLS, 2018 SOC structure | `https://www.bls.gov/soc/2018/soc_structure_2018.xlsx` | Which code is the broad-group parent of which detailed occupation; that the five hybrid targets are not SOC codes at all (867 detailed occupations enumerated, none of them) |
| S2 | BLS, 2010-to-2018 SOC crosswalk | `https://www.bls.gov/soc/2018/soc_2010_to_2018_crosswalk.xlsx` | That no code in the gap was renumbered between revisions |
| S3 | BLS OEWS occupation profiles | `https://www.bls.gov/oes/current/oes211018.htm` and siblings | Each hybrid target's membership: "This occupation includes the 2018 SOC occupations …" |
| S4 | O\*NET OnLine | `https://www.onetonline.org/link/summary/31-1121.00` | Per **source** code, which occupation the wage and employment figures were actually collected under |
| S5 | O\*NET My Next Move, data-source pages | `https://www.mynextmove.org/help/data/31-1121.00` | Same relation stated explicitly: "BLS wage data was collected under the 2018 SOC occupation 31-1120 (Home Health and Personal Care Aides)" |

S4/S5 are what made this checkable rather than inferable. S3 tells you what a hybrid code
*contains*; S4/S5 tell you, for one specific detailed code, where its data went. Asking the
question from the source side also produced the decisive negative result: **all 64 dead
codes in the corpus were queried against S4, not just the 24 on the 77.** Every code with a
substitution note pointing at an EDD-published aggregate is in the table. Every code without
one is refused. The two sets did not have to line up this cleanly, and the fact that they do
is the strongest evidence the table is not doing anything clever.

S3 was read through search-result extracts; direct fetches of `bls.gov/oes/` were refused by
BLS's bot policy. S1, S2, S4 and S5 were downloaded and parsed directly. Every S3 statement
is independently corroborated by S4 and S5, so no row rests on the extract alone.

## The mapping

`AGGREGATIONS` holds 29 source codes over 12 targets. 18 of the 29 appear in this snapshot;
the rest are the remaining members of the same groups, included because the ETP feed
refreshes quarterly and a partial table would reopen the gap for whichever sibling turns up
next. All 12 targets are present in the current EDD snapshot, and
`resolve_published_soc()` re-checks that at call time rather than trusting the table.

### Rows that close the 77

| Source | → Target | Kind | Programs recovered | Confidence |
|---|---|---|---|---|
| `31-1121`, `31-1122` | `31-1120` Home Health and Personal Care Aides | broad group | 23 | **High** |
| `21-1011`, `21-1014` | `21-1018` Substance Abuse, Behavioral Disorder, and Mental Health Counselors | hybrid | 19 | **High** |
| `25-9042`, `25-9043`, `25-9049` | `25-9045` Teaching Assistants, Except Postsecondary | hybrid | 10 | **High** |
| `29-2011`, `29-2012` | `29-2010` Clinical Laboratory Technologists and Technicians | broad group | 6 | **High** (see caveat) |
| `47-4099` | `47-4090` Miscellaneous Construction and Related Workers | broad group | 3 | **Medium** |

### Rows that fix dead codes on already-matched programs

`13-1021`, `13-1022` → `13-1020`; `13-2022`, `13-2023` → `13-2020`; `25-2055`, `25-2056` →
`25-2052`; `51-2092` → `51-2090`; `53-1043` → `53-1047`. Same evidence, same confidence.

Confidence is about **containment**, which is the only claim the table makes: is the target's
published population, by BLS's own definition, a superset of the source occupation? For
broad groups that is settled by the SOC hierarchy and for hybrids by the OEWS definition, so
almost everything is High. `47-4099` Construction and Related Workers, All Other is Medium
only because containment is certain but the target is a residual bucket, and the reader
learns little from "Miscellaneous Construction and Related Workers" — 2,390 statewide
openings against a `47-2061` Construction Laborers figure two orders of magnitude larger.
The three programs are pre-apprenticeship curricula that plainly feed the construction
trades. The honest position is that D1 tagged them with a residual code and neither BLS nor
EDD publishes anything narrower; guessing `47-2061` would be a similarity judgement, which
is exactly what this module refuses to make.

## Two caveats the integrator must handle

**1. A mapped program is shown a broader group's numbers.** For `31-1120` that is harmless —
home health aides and personal care aides are paid alike, and it is the only figure
California publishes. For `29-2010` it is not: the group blends technologists with
technicians, and the six recovered programs are Medical Laboratory Technician and phlebotomy
certificates sitting at the bottom of that range. `SocAggregation.kind` is on the return
value so the interface can say which occupation the numbers actually describe.

**2. `entry_level_education` on an aggregate can be flatly wrong for the program.** Two of
the five rescuing targets carry a typical-entry credential above the training on offer:

- `21-1018` reads **Master's degree**. The 19 recovered programs are community-college
  alcohol-and-drug-counseling certificates. California's SUD counselor certification is not
  a master's-level credential; the master's belongs to the mental-health-counselor half of
  the hybrid. Rendered without qualification this tells someone their certificate does not
  qualify them for the job it does qualify them for.
- `29-2010` reads **Bachelor's degree**, which is the technologist half. MLT is an
  associate-level occupation.

This is a presentation problem, not a mapping problem — the number is EDD's and it is
faithful. But it is the same class of hazard as rendering a suppressed measure as zero, and
recovering these 61 programs makes it live on 25 program pages that previously showed no
occupation panel at all. Worth deciding before integration, not after.

## The 16 refusals

None of these has a defensible target. In every case BLS publishes the occupation under its
own code — confirmed via S4, no substitution note on any of them — so there is no aggregate
to fall back to. EDD simply does not publish the occupation for California. There is nothing
to recover, and the module returns `None`.

| SOC | Occupation | Programs | Why refused |
|---|---|---|---|
| `19-1032` | Foresters | 1 | Sibling `19-1031` Conservation Scientists is published; broad group `19-1030` is not. A sibling is not a parent. |
| `19-3041` | Sociologists | 1 | Sole member of broad group `19-3040`; EDD publishes neither. |
| `19-3094` | Political Scientists | 1 | Broad group `19-3090` unpublished. `19-3099` Social Scientists, All Other is a residual **sibling**, not a parent. |
| `19-4042`, `19-4043`, `19-4044` | Environmental Science and Geoscience Technicians | 3 | EDD publishes no member of `19-4040` and not the broad group. `19-4099` is again a residual sibling. |
| `37-2021` | Pest Control Workers | 2 | Sole member of broad group `37-2020`; EDD publishes neither. The `37-2010` cleaning-worker codes it does publish are a different broad group. |
| `39-3099` | Entertainment Attendants and Related Workers, All Other | 1 | Broad group `39-3090` unpublished; the three published siblings are not parents. |
| `45-4029` | Logging Workers, All Other | 1 | Broad group `45-4020` unpublished; `45-4022` is a sibling. |
| `47-2011` | Boilermakers | 2 | Sole member of broad group `47-2010`; EDD publishes neither. |
| `47-2043` | Floor Sanders and Finishers | 1 | Broad group `47-2040` unpublished. EDD publishes the other three flooring codes, which makes a nearest-neighbor guess tempting and wrong. |
| `47-5022` | Excavating and Loading Machine and Dragline Operators, Surface Mining | 1 | Broad group `47-5020` unpublished; `47-5023` Earth Drillers is a sibling. |
| `49-9081` | Wind Turbine Service Technicians | 1 | Sole member of broad group `49-9080`; EDD publishes neither. |
| `55-2013` | First-Line Supervisors of All Other Tactical Operations Specialists | 1 | Military occupation. EDD publishes no `55-` occupations at all. |

The recurring temptation in this list is the **residual sibling**: `19-3099` and `19-4099`
both end in `99` and both sound like catch-alls, so mapping `19-3094` Political Scientists
into `19-3099` Social Scientists, All Other looks reasonable. It is not. "All Other" is a
detailed occupation defined by *excluding* its named siblings, so `19-3099` is precisely the
set of social scientists who are **not** political scientists. That mapping would attach a
wage drawn from a population the trainee is by definition not in.

The second temptation is the **nearest neighbor**: `47-2043` Floor Sanders and Finishers is
refused while the other three codes in its broad group are published. A flooring
apprenticeship is obviously flooring work — but `47-2041` Carpet Installers is a different
job with a different wage, and picking it would be a title-similarity judgement dressed up as
a crosswalk.

One guardrail earned its place from a live near-miss. O\*NET reports that wage data for
`45-3031` Fishing and Hunting Workers is collected under **`45-0000`** — the entire
Farming, Fishing, and Forestry major group. A rule of "follow O\*NET's substitution note"
would have swallowed that. The table therefore stops at broad-group level, and
`TestTableInvariants::test_no_target_is_a_minor_or_major_group` asserts it.

## Verification

```
uv run pytest tests/test_soc_vintage.py -q     # 66 passed
uv run mypy src                                # strict, clean
uv run ruff check . && uv run ruff format --check .
uv run python scripts/provenance_check.py
```

Measured against the live snapshot: 12/12 targets present in `occupations.json`; 61 of 77
programs recovered; every code that matched before still resolves to itself.
