# National education attainment: parsed, recommended, and not shipped

> **Correction, 2026-08-07.** The gap the note below describes is closed. `Attainment` in
> `web/app/[lang]/programs/[id]/page.tsx` — the component the 2026-08-05 correction found
> still rendering the distribution — has been deleted (#20), along with the helper functions
> and translated strings it alone used. No program page renders the seven-level distribution
> as of this commit. `distribution` stays in the shipped dataset and in `web/lib/types.ts`,
> documented and unrendered, because the underlying BLS measurement is real and the field
> that would fix its provenance problem (see "What would change the answer" below) might
> exist someday; nothing renders it in the meantime. The decision this note reached — not
> shipped — now matches the code, for the first time since commit 99a1382.

> **Correction, 2026-08-05 (later).** The decision below stands and none of its measurements
> changed. Its description of what the site was already doing is wrong. This note says
> "Nothing renders it" and that the distribution is "deliberately not published anywhere on
> the site"; both were false when written. `Attainment` in
> `web/app/[lang]/programs/[id]/page.tsx` has rendered the seven-level distribution since
> commit 99a1382, and it is live now. The scope, re-measured against the deployed snapshot:
>
> - 3,250 of the 3,266 program pages render at least one attainment block; all 5,514
>   program-occupation rows carry a distribution.
> - 1,695 of those rows (30.7%) sit on one of the shared 268, spread over 1,275 program pages.
> - The decisive pair is on one page: Shasta College's Early Childhood Education Certificate
>   feeds Preschool Teachers (25-2011) and Kindergarten Teachers (25-2012). Their
>   distributions are byte-identical. The page prints "33% of the people doing it went less
>   far" under Associate's for one and "45%" under Bachelor's for the other, adjacent, from
>   the same seven numbers. This note argued that case hypothetically; it is shipping.
> - `typical_experience` and `typical_on_the_job_training` are published too — they are the
>   only source of the "Getting in" block, and EDD's equivalent `work_experience` and
>   `job_training` are parsed and never rendered. The section below says they are "not
>   either", which is wrong for the same reason.
>
> So "What was changed in the code" is accurate about what was changed and wrong about what
> that left: it changed the docstrings and left the render in place. Carrying out the decision
> is a behaviour change and was not part of this documentation pass.

2026-08-05. `docs/enrichment-expansion-2026-08-04.md` left one thing undecided and named it
"one judgement call that the pipeline has been waiting on". This is the call, made against.

**The question.** BLS's education-attainment distribution — the share of people working in an
occupation who hold each of seven education levels — is parsed by `careeronestop.py`, attached
to all 670 occupation records by `build.py`, typed and documented in `web/lib/types.ts`, and
present in the shipped dataset. Nothing renders it. The prior note recommended that it should:
beside the withheld `entry_level_education` on the 135 program rows that match through an
aggregate, and beside the unqualified category on all 670 occupation pages, where its own
measurement found 60 occupations whose stated credential most workers in the job do not hold.

**The answer is no**, on grounds the prior note could not have reached, because its central
provenance claim turns out to be false and the field it relied on to check that claim cannot
detect the failure.

Everything below is measured from the committed snapshot (`web/public/data`, 2026-08-04, 3,266
programs, 670 occupations) and the raw response cache (`data/raw/cos-cache`, 1,272 entries).
No live API calls; no credentials needed to reproduce any of it.

## Why it looked promising, and still does

The site tells a reader one thing about what an occupation requires: a single category, from
EDD, stated flatly. "Bachelor's degree". The distribution is a measurement of a population the
reader would be joining, and where the two disagree the disagreement is large. The prior note's
figures reproduce exactly — 625 occupations comparable on both scales, median 12.1% of workers
holding less than the stated category, and 347 / 220 / 153 / 96 / 60 occupations above 10 / 20 /
30 / 40 / 50%.

Weighted by what a reader actually meets rather than by occupation, it is if anything stronger:
of the 5,514 program-occupation rows on the site, 4,240 have a computable comparison, the median
gap across them is 18.5%, and 3,129 rows (56.7%) sit on an occupation where more than a tenth of
workers hold less than the page says is typical.

That is a real problem and this note does not dispute it. The argument is that this field does
not fix it.

## What the data actually contains

### 268 of the 670 occupations are served another group's figures

The 670 distributions are not 670 measurements. They are **495 distinct distributions**. 268
occupations (40.0%) receive a distribution byte-identical, across all seven levels, to at least
one other occupation's — 93 groups, sized 2 to 24:

| Group | Occupations | Program rows on the site |
| --- | --- | --- |
| Postsecondary teachers (25-1011 … 25-1199) | 24 | 128 |
| Engineering technologists and technicians (17-3021 … 17-3029) | 8 | 69 |
| Physicians (29-1214 … 29-1229) | 8 | 0 |
| Helpers, construction trades (47-3011 … 47-3019) | 7 | 20 |
| Cooks (35-2011 … 35-2019) | 6 | 62 |
| Computer support specialists (15-1231, 15-1232) | 2 | 160 |
| Welding, soldering and brazing workers (51-4121, 51-4122) | 2 | 160 |

This is the API's own output, not something the pipeline did. In the raw cache, `25-1011.00`,
`25-1021.00` and `25-1071.00` — Business, Computer Science and Health Specialties Teachers —
each return `.6 / 1.7 / 2 / 1.5 / 15.1 / 30.6 / 48.5`, and each is stamped with its own code and
its own title.

The group boundaries are the **Census occupation categories the American Community Survey
collects**, which are coarser than the six-digit SOC: one code for all postsecondary teachers,
one for cooks, one for construction-trades helpers, one for preschool *and* kindergarten
teachers. That identification is inferred from where the boundaries fall, not from anything in
the response — which is the whole difficulty.

### The check built to catch exactly this catches none of it

`EducationProfile.reported_for_soc` exists so a caller can confirm the figures describe the page
they are going on, and the prior note's headline reported the result: *"Occupations where the
attainment figures describe a different population than the page: 0."*

Measured across all 1,272 cached responses, `MatOccCode` **repeats the code that was requested
658 times and differs 12 times**. The 12 are precisely the member lookups behind the EDD
aggregates — `21-1011` answering for `21-1018`, `31-1121` for `31-1120`. Every one of the 268
occupations above reports its own SOC and its own title.

So the check is not weak, it is blind in the direction that matters. It fires only when the
coarser group happens to be a code EDD itself publishes, and it was that narrow success — 12 for
12 on the aggregates — that made it look reliable. The true count for that headline row is at
least 268, and "at least" is the honest form: a group containing only one of California's 670
occupations is indistinguishable from a genuine per-occupation measurement.

**1,695 of the 5,514 program-occupation rows (30.7%) sit on one of the 268**, across 174 of the
433 occupations that appear on a program page. And 5 of the 10 aggregates reachable from a
program page are themselves in a shared group, covering 42 of the 135 withheld rows this
investigation started from.

### Two cases that decide it on their own

**Preschool Teachers, Except Special Education** (46 program rows) and **Kindergarten Teachers**
(15) receive the same seven numbers. The preschool page would tell someone weighing an Early
Childhood Education certificate that 34.6% of people in the occupation hold a bachelor's and
18.2% a master's — 54.6% at bachelor's or above — measured over a pool that is half kindergarten
teachers, who in California need a bachelor's and a Multiple Subject credential. The reader's
own field is largely permit-based. `reported_for_soc` says `25-2011, Preschool Teachers, Except
Special Education`. The site would be discouraging exactly the purchase it exists to inform, on
a number belonging to somebody else, with a provenance stamp certifying that it does not.

**Computer User Support Specialists** (50 rows, EDD category "Some college, no degree") and
**Computer Network Support Specialists** (110 rows, "Associate's degree") receive the same seven
numbers. The derived share holding less than the stated category comes out **12.0%** on one page
and **35.8%** on the other. One measurement, two answers, differing only in which category it
was set beside. Whatever that quantity is, it is not a property of either occupation.

### On 23.1% of program rows the comparison cannot be made at all

1,274 rows across 40 occupations carry the category "Postsecondary non-degree award", which has
no counterpart on the seven-level scale. The prior note recorded the 45 occupations. What it did
not say is which ones: **Medical Assistants (196 rows), Nursing Assistants (120), Heavy and
Tractor-Trailer Truck Drivers (95), Automotive Service Technicians (80), Medical Records
Specialists (75), Hairdressers and Cosmetologists (59), Dental Assistants (59), Phlebotomists
(55)**. These are the certificate occupations the site is most for. The field is silent in
precisely the place its argument was strongest.

### Where it is computable, it still cannot be acted on

A share of incumbents cannot distinguish "the stated requirement is softer than it looks" from
"the requirement rose and these people predate it". Those imply opposite purchases, and the data
says nothing about which one it is:

- **Athletic Trainers** — 58.6% hold less than the stated master's; 7 program rows. CAATE closed
  baccalaureate matriculation after fall 2022 and a master's is now the only route to BOC
  certification. The number is true of the people in the job and false as guidance for anyone
  enrolling now.
- **Healthcare Social Workers** — 62.8% below master's; 4 program rows. California's Board of
  Behavioral Sciences registers an ASW and licenses an LCSW only on a master's in social work.
- **Construction Managers** — 66.0% below the stated bachelor's; 30 program rows. Here the
  number probably does mean what a reader would take it to mean.

Three occupations, one shape of number, and it points the right way once. The page cannot label
which is which, because the source does not know.

### The rest of the block is a restatement of what the site already has

`typical_experience` and `typical_on_the_job_training` agree with EDD's `work_experience` and
`job_training` **category for category on all 670 occupations** — 572 / 73 / 25 on experience,
280 / 165 / 148 / 44 / 21 / 12 on training, with no occupation disagreeing on either. BLS's
wording is plainer ("1 to 12 months on-the-job training" where EDD says "Moderate-term"), which
is a translation the site can make in `vocabulary.ts` without a second federal source and
without a second claim to reconcile.

## The decision

Not shipped, in either slot.

It fails the project's test twice over. It cannot change whether a person spends a year and
several thousand dollars, because on 30.7% of the rows where it would appear it is not about
their occupation, on 23.1% it cannot be compared to anything, and on the remainder it is
ambiguous between two readings that argue for opposite decisions. And it fails harder than a
merely useless field would: it is *specific*, it is *federal*, and it carries a provenance stamp
naming the reader's own occupation, so it looks like exactly the kind of grounded number this
site is built out of. A reader has no way to discount it.

That is the same conclusion as `onet-technologies-not-shipped-2026-08-04.md` and it rests on the
same rule, one step further along: there, no ranking made the data say something true and useful,
and absence was the honest output. Here the data says something true — 34.6% of *someone* holds
a bachelor's — and attaching it to a named occupation is what makes it false. The occupation
page already refuses to print `4.12` next to a skill because a number with no scale invites a
wrong reading, and inviting a wrong reading is not better than showing less. This is that rule
applied to a number whose scale is fine and whose *subject* is wrong.

The larger problem the prior note found is real and is not addressed by this decision: the site
states a single credential category on 670 pages with no qualification, and on 60 of them most
people doing the job hold less than it. That needs a fix. This field is not it.

## What was changed in the code

Nothing was ripped out. `_parse_education` and `_aggregate_education` still run and the field is
still in the dataset, because `MatOccCode` is load-bearing for the aggregate lookup and because
deleting the parse would leave the next person an empty space instead of this note. What changed
is that the code no longer claims things that are not true:

- `_soc_from_mat` said its "whole job is to let a caller check the figures describe the
  population it is about to attach them to". It cannot do that, and now says so with the counts.
- `EducationProfile` told callers to check `reported_for_soc` at the point of use. It now says
  the check does not work, that the distribution is deliberately unpublished, and where to read
  why.
- `_aggregate_education` is correct about the step it takes and now records that the aggregate's
  own figures may in turn be measured over something broader.

`web/lib/types.ts` documents `reported_for_soc` as something to "check at the point of use
rather than assuming it matches", and `PROVENANCE.md`'s D6 row names national education
attainment as a thing this source is used for. Both are now wrong. Both are outside this
change's ownership.

## What would change the answer

The Census occupation code the figure was measured for. One field, which the API does not send,
which would turn "268 occupations are wrong and you cannot tell which" into "these 268 are
labelled, and the other 402 are theirs". That alone would make a restricted version publishable.

Better, and not much harder: American Community Survey PUMS directly. It would fix all three
faults at once — the true measured population is in the file rather than inferred, it can be
restricted to workers who entered recently rather than everyone currently employed, which is the
ambiguity no amount of labelling fixes, and it can be restricted to California, which is the
scope every other figure on these pages already uses.

Until then, the honest treatment of the 60 occupations whose stated category most workers do not
hold is to qualify the category — it is a national assignment of a typical entry route, not a
rule — rather than to answer it with a different occupation's numbers.
