# Widening the CareerOneStop request — 2026-08-04

`src/camino/sources/careeronestop.py` asked source D6 for two things: `relatedOnetTitles`
and `skills`. The endpoint returns considerably more. This is the record of what was taken,
what was refused, what it measures out at across all 670 California occupations, and one
judgement call that the pipeline has been waiting on.

The test for inclusion was narrow and applied to every field: **does knowing this change
whether a person spends a year and several thousand dollars on a training program?** A
field that is merely true, or merely available, did not qualify.

## Headline

| | |
|---|---|
| Occupations fetched | 670 (all of them, one throttled request each) |
| Fields added | tasks, alternate titles, education attainment distribution, typical prior experience, typical on-the-job training |
| Fields refused | knowledge, ability, interests, detailed work activities, wages, projections, career video, SOC description, green flag, OOH and state-resource links, training programs |
| Education attainment coverage | **670 / 670 (100%)**, including all 12 aggregates |
| Occupations where the attainment figures describe a *different* population than the page | **0** |
| Program rows with a withheld `entry_level_education` now backed by a distribution | **135 / 135** |
| Pre-existing field coverage | unchanged, exactly (see regression check below) |

## What was added

### Tasks — the biggest gap the site had

Before this, the site could not say what a person in an occupation actually *does* beyond a
one-paragraph description. Registered Nurses returns 41 tasks, including "Order, interpret,
and evaluate diagnostic tests to identify and assess patient's condition."

This is the field a reader can actually check themselves against. A description is a
definition; a task list is the job. Someone choosing between a phlebotomy certificate and a
medical-billing certificate learns more from eight concrete sentences about the day than
from any wage figure, because the wage tells them what the job pays and the tasks tell them
whether they want it.

Two decisions inside the parse:

- **Ranked, not first-eight.** The API returns tasks in no useful order — 29-1141's first
  entry is rated 4.41 and its third is rated 4.44. Showing the first eight would be an
  arbitrary sample presented as a summary. `_parse_tasks` sorts by O*NET's rating and keeps
  the top `TOP_TASKS = 8`.
- **An unrated task sorts last with a null rating, never zero.** Same rule as skills. As it
  happens, zero tasks in the entire corpus came back unrated, so this guard is currently
  unexercised — it is there because the invariant is not conditional on today's data.

### Education attainment distribution — the field this document is really about

`EducationTraining.EducationType` is the distribution of education that people working in
the occupation actually **hold**:

> Registered Nurses — Less than high school 0.5%, High school 1.2%, Some college 3.9%,
> **Associate's 25.6%**, Bachelor's 54.4%, Master's 11.8%, Doctoral or professional 2.7%.

The site currently tells that reader one thing: "Bachelor's degree". A quarter of the people
doing the job hold an associate's, which is the credential a California community college
ADN program awards. The single category is not false — it is BLS's assignment of the
typical entry requirement — but for a person weighing a two-year public-college program
against a four-year one, the distribution is the number that answers their question and the
category is the number that discourages them from asking it.

Extracted alongside it, from the same block:

- **`typical_experience`** — BLS's "work experience in a related occupation". 25 of the 670
  occupations require **5 years or more**, and another 73 require some.
- **`typical_on_the_job_training`** — 12 occupations are entered by **apprenticeship**, 21
  by **internship or residency**, 44 by more than a year of on-the-job training.

These two were not in the brief and are worth as much as anything that was. They answer
"will finishing this program actually get me in?", which is a different question from
"what credential does it award". A classroom certificate for an occupation whose typical
entry is an apprenticeship is a materially different purchase, and nothing on the site says
so today.

### Alternate titles — a search fix, measured

`AlternateTitles` came back empty in earlier probing. **It is populated; it just needs the
`alternateOnetTitles=true` parameter**, which nothing was sending. With it on, 591 of 670
occupations return titles — **5,350 in total**, a median of 10 per occupation:

> Registered Nurses → Charge Nurse, School Nurse, Staff RN, Emergency Department RN,
> Oncology RN, Operating Room Registered Nurse, Psychiatric RN, Certified Operating Room
> Nurse (CNOR), Relief Charge Nurse, Staff Nurse.

Someone typing "RN" or "school nurse" today finds nothing. This is the cheapest large
improvement in the set: it costs no extra request, and it fixes a class of failure where the
site *has* the answer and cannot be asked for it.

The API returns at most 10, so `ALTERNATE_TITLE_LIMIT = 20` never binds on today's data. It
stays as a bound rather than a policy — nothing is being silently truncated, and if the API
starts returning 60 the payload will not quietly triple.

## What was refused, and why

**`KnowledgeDataList` (33 entries) and `AbilityDataList` (52 entries).** Both were fetched
during probing and both were rejected. Knowledge has a real argument in its favor: it is
domain-concrete ("Medicine and Dentistry", "Building and Construction") where the skills
list is abstract ("Critical Thinking", "Operations Monitoring"). It was still refused,
because it does not change the decision — nobody weighing a nursing program is surprised
that the job involves medicine — and it would put a second unlabelled 1-to-5 O\*NET rating
scale on a page that already carries one. Two rated lists side by side, on the same
unexplained scale, dilute rather than inform.

Ability is a firmer no. "Mathematical Reasoning: 3.0", "Category Flexibility: 3.38" is
aptitude framing. On a page whose purpose is to help someone decide to enrol, a list of
innate capacities scored out of five reads as a screening test, and it is not actionable:
there is no response to a low ability rating except discouragement. *What would change this:*
if the interface ever grows a proper explanation of the O\*NET scale, Knowledge is the first
field to reconsider. Ability is not.

**`Interests`** (Holland/RIASEC codes). Refused for the same reason as Ability, plus one:
interest inventories are a guidance instrument that means something when a person has taken
one, and nothing when it is printed at them.

**`Dwas` (detailed work activities, 41 entries).** These are the generalised forms of the
tasks — "Analyze test data or images to inform diagnosis or treatment" where the task says
"Order, interpret, and evaluate diagnostic tests". Strictly redundant with a field already
taken, and less concrete. Refused.

**`Wages` and `Projections`.** Refused on the project's existing rule: EDD (D2/D3) publishes
these for California, and CareerOneStop publishes them nationally. Two medians for the same
occupation, differing because they cover different geographies, is a contradiction on the
page. The California figure is the one that describes the reader's labor market.

**`COSVideoURL`.** Present for 658/658 occupations that return a profile at all, so coverage
was not the objection. It is an outbound
link to a `careeronestop.org` video page with a query string — not an asset this static site
can host, caption, or translate, and the project already documents that the API serves
English only. Everything the video conveys about what the work looks like, the task list now
conveys in text that is translatable, screen-readable, indexable, and free of a
third-party link to keep alive. Tasks dominate it on every axis except vividness.

**`SocInfo.SocDescription`.** Measured before refusing, from the pre-existing cache: it is
byte-identical to `OnetDescription` for 587 of 658 occupations and longer for 30. The
hypothesis that it carries licensing language the O\*NET description omits was tested
directly — 15 SOC descriptions mention licensing, registration or certification, and in
**zero** cases does the O\*NET description omit it. A second description field that is the
same text 89% of the time is clutter.

**`Green`.** Measured: `Green == "Y"` for **0 of 658** occupations. O\*NET's green-economy
classification has not been maintained for over a decade. A flag that is never set is not a
field.

**`OOHs` and `StateResourcesLinks`.** Outbound link collections. The project already runs a
link-checking module because outbound links rot; adding two more per occupation buys
maintenance cost, not decisions.

**`TrainingPrograms`.** Returned null throughout, and the project already has a
California-specific training corpus with published outcome measures (D1). A national
program list next to the ETP corpus would be strictly worse data in a more prominent slot.

## Measured coverage, all 670 occupations

Fetched with the new parameter set on 2026-08-04, parsed with the shipped client, counted
from the parsed records.

| Field | Occupations with a value |
|---|---|
| `description` | 658 / 670 (98.2%) |
| `skills` | 581 / 670 (86.7%) |
| `related_onet` | 600 / 670 (89.6%) |
| `bright_outlook` | 249 / 670 (37.2%) |
| **`tasks`** | **581 / 670 (86.7%)** |
| **`alternate_titles`** | **591 / 670 (88.2%)** |
| **`education.distribution`** | **670 / 670 (100.0%)** |
| **`education.typical_experience`** | **670 / 670 (100.0%)** |
| **`education.typical_on_the_job_training`** | **670 / 670 (100.0%)** |

**Regression check.** The four pre-existing fields land on 658 / 581 / 249 / 600, which is
exactly what the currently published `coverage.json` reports. Widening the request changed
nothing about what was already there.

**Where the gaps are.** The 89 occupations with no tasks are *precisely* the 89 with no
skills — the same set, not a coincidence: O\*NET rates an occupation or it does not. 58 of
them are "All Other" residual codes, 12 are the aggregates discussed below, and the rest are
occupations new enough in the 2018 SOC that O\*NET has not surveyed them (Data Scientists,
Project Management Specialists, Financial Risk Specialists). Nothing is recoverable here;
these occupations have no O\*NET profile to read.

**Distribution shape.** All 670 distributions carry the same seven levels in the same order,
all 670 sum to 100 ± 0.6, and **not one cell is unpublished**. 179 cells across the corpus
are a genuine `0.0`. That number is the reason `_number` returns `0.0` rather than falling
through to `None`, and the reason nothing in the parse uses truthiness on a percentage: 179
real measurements would otherwise have been deleted.

## The cache had to change, and it invalidated itself

The 658 entries in `data/raw/cos-cache/` were fetched with the old narrow parameter set.
They are not smaller versions of the current answer — they are the current answer with
`Tasks`, `AlternateTitles` and `EducationTraining` **absent**. Serving one would have put
"this occupation reports no tasks" on a page when the truth is that nobody asked for tasks:
exactly the null-means-not-reported confusion this project exists to avoid, arriving through
the back door of a cache key.

Every entry now records the request that produced it — `cache_format`, the O\*NET code, the
state, and the full parameter dictionary — and `_read_cache` serves an entry only when all
four match what is about to be requested. An entry that cannot say what produced it is a
miss. The consequence is that `REQUEST_PARAMS` is the cache key: widening it again will
invalidate the cache by construction rather than by anyone remembering to clear it.

All 670 occupations were re-fetched under the new parameter set, sequentially, one request
at a time, on the module's existing 0.3s throttle. No parallelism.

`cache_envelope()` is public so that anything writing an entry by hand — a test, a fixture,
a backfill — writes one the module will accept, rather than duplicating the shape.

This did break `tests/test_build.py::TestFetchEnrichment::test_a_warm_cache_is_served_without_a_request`,
which wrote a bare payload and asserted it was served. That is not a design that survives a
parameter change: any invalidation rule at all makes a bare, unlabelled entry a miss. The
test now asserts the real contract — an entry matching the current parameter set is served
without a request, and one recorded as fetched without `tasks` is not.

The no-credentials invariant is untouched and does not depend on the cache: `fetch_enrichment`
returns `{}` before building a client, so a CI runner with no credentials makes no request
regardless of what is or is not on disk.

## The education distribution where the single category is withheld

### What was found

The pipeline withholds `entry_level_education` on **135 program rows** because those
programs match through an aggregate whose single credential category can be flatly wrong for
the specific program — `21-1018` reading "Master's degree" onto community-college
substance-use-counselling certificates. The question put to this task was whether the
distribution can stand in.

The first finding was discouraging. **All 12 aggregates 404 on this API.** They are BLS
publication aggregates and BLS hybrid codes, not O\*NET occupations, which is why those 12
occupation pages carry no description and no skills today. There is no `21-1018` entry to
fetch a distribution from.

The second finding reversed it. BLS publishes education attainment per **matrix
occupation**, and `EducationTraining.MatOccupation.MatOccCode` names which one. For every
detailed occupation inside one of these aggregates, the matrix occupation **is the
aggregate**: `21-1011` Substance Abuse and Behavioral Disorder Counselors and `21-1014`
Mental Health Counselors return the *identical* distribution, both stamped `MatOccCode:
211018`. The figures were never the member's own.

So the distribution is reachable, and reaching it is a lookup rather than a substitution.
`_aggregate_education` fetches a member, and **checks** that `MatOccCode` equals the
aggregate before using anything; a member reporting for something else is discarded and the
next one tried. Nothing else from the member's response is carried over — its description,
tasks and skills genuinely *are* the member's own, and putting Home Health Aides' tasks on a
Home Health and Personal Care Aides page would be the substitution this is careful not to
make. All 12 aggregates resolved, and **135 of 135 withheld rows now have a distribution
behind them.**

A corollary worth stating on its own: across all 670 occupations, the number whose
attainment figures were measured for a *different* population than the page they would
appear on is **zero**. `reported_for_soc` is on the record so that this stays checkable
rather than assumed.

### The judgement: yes, but not in that slot, and it is not a replacement

**It can be published where the category is withheld.** The reason for the withholding does
not transfer. The category is a *requirement claim* — BLS's judgement of what a person
typically needs to enter — assigned once to a whole union of occupations, and inherited by a
member it may not fit. The distribution is a *population measurement* of a group the trainee
will belong to. It makes no claim about any individual or any member, so it cannot be wrong
about them in the way the category can. It is the same class of claim as the median wage and
the opening count, which those pages already show, already label as the aggregate's, and
already ask readers to read as approximate.

The numbers support publishing it rather than merely permitting it. For `21-1018`, BLS's own
attainment data says **15.4% of people in the occupation hold less than a bachelor's** and
**39.2% hold less than a master's**. The withheld category asserts "Master's degree". The
distribution is not just safer than the category — it is evidence that the category was
misleading, sourced from the same agency.

**But four limits, and they are not small.**

1. **It answers an adjacent question, not the withheld one.** The reader wanted "what do I
   need?" and gets "here is what people have". If it is dropped into the same "Typical
   education" row with a new label, a reader will read 55.7% master's as *you need a
   master's* — recreating the exact false inference the withholding exists to prevent, with
   more decimal places. It can only be published as attainment, visibly not a requirement.
2. **It does not resolve the aggregation problem, it declines to commit the specific error.**
   `21-1018` is a blend of two halves with genuinely different credentials, and 55.7%
   master's is driven by the mental-health-counselling half. A certificate student could
   read it and conclude the field is closed to them. That is the opposite error, and it is
   still an error. The distribution is honest about the union and silent about the split.
3. **It is national; every other figure on the page is California.** EDD does not publish
   this. Mixing scopes without saying so is its own quiet falsehood.
4. **The two are on different scales and cannot be compared arithmetically.** The attainment
   scale is the seven Census levels; EDD's category vocabulary includes **"Postsecondary
   non-degree award"**, which has no counterpart on it, and which is the stated category for
   **45 occupations** — disproportionately the certificate-shaped ones this site is for. For
   those, "percentage who meet the requirement" is not computable and must not be presented
   as if it were.

So: **publish it, label it as attainment, label it national, name the occupation it was
measured for, and do not let it occupy the row the withheld category vacated.** It is a
second fact, not a replacement fact.

### The larger finding: this is not really about the 12

The withheld category is a live problem on 135 program rows. The *unqualified* category is a
live problem on all 670 occupation pages, including the aggregates — `21-1018`'s occupation
page shows "Master's degree" today with no qualification at all, since the withholding only
applies to the program-page embed.

Across the 625 occupations comparable on both scales:

| Share of workers holding **less** than EDD's stated category | Occupations |
|---|---|
| more than 10% | 347 |
| more than 20% | 220 |
| more than 30% | 153 |
| more than 40% | 96 |
| more than 50% | **60** |

Median: 12.1%. The widest gaps are not edge cases — Orthotists and Prosthetists reads
"Master's degree" while **88.9%** of them hold less; Dietetic Technicians reads "Associate's
degree" while 71.7% hold less; Construction Managers reads "Bachelor's degree" while 66.0%
hold less.

On 60 occupations the site currently states a credential that most people doing the job do
not have. Publishing the distribution beside the category fixes a real and much larger
problem than the one that prompted it.

## For whoever integrates this

1. **`OccupationEnrichment` is backward compatible.** `tasks`, `alternate_titles` and
   `education` are appended with defaults; every existing field, its type and its position
   are unchanged, and `as_dict()` keeps all five original keys. `build.py` needs no change
   to keep working, and a test constructing the type from the original six fields still
   compiles.
2. **`education.reported_for_soc` must be checked at the point of use**, not trusted. It is
   `null` when BLS's code was unreadable. It happens to equal the page's own SOC for all 670
   occupations today; that is a measurement, not a guarantee.
3. **PROVENANCE.md's D6 row needs updating** — its "Used for" column still says
   "Occupation descriptions, O\*NET skill ratings, O\*NET related occupations, Bright
   Outlook". It should also name tasks, alternate titles, and national education attainment.
   That file is outside this change's ownership.
4. **`fixtures/data/occupations.json` predates these fields** and will need regenerating
   (`make fixture` after a real `make data`) if CI is to exercise them.
5. **Alternate titles belong in the search index**, not on the page. They exist to be matched
   against; rendering ten near-synonyms under a heading is noise.

## Verification

```
uv run pytest tests/test_careeronestop.py -q       # 47 passed
uv run pytest tests/test_build.py -q               # 94 passed
uv run mypy src                                    # strict, clean
uv run ruff check . && uv run ruff format --check .
uv run python scripts/provenance_check.py          # clean
```

Coverage figures above were measured by running the shipped client over all 670 occupations
in the current `data/processed/occupations.json` snapshot and counting the parsed records —
the same way `enrichment_coverage()` counts, and for the same reason: it measures what a
reader would find on the pages, not how many responses came back.
