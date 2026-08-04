# The next step — 2026-08-04

The site tells a Californian that a program exists, what it costs, and what happened to the
people who took it. Then it stops. The only onward link is **"Provider's website →"**, and
for 334 program pages that link is dead
([dead-provider-links-2026-08-04.md](dead-provider-links-2026-08-04.md)).

Every program on this site is on California's Eligible Training Provider List — that list is
what the federal feed behind source D1 describes. Under federal rules that means there is a
route by which somebody else may pay for it. The site has never mentioned it.

This document establishes what that route actually is, from primary sources; determines
whether the CareerOneStop American Job Center finder can be reached with this project's
credentials (**it can** — the earlier 404s were a route-shape problem, diagnosed below);
measures how well it covers the places our programs are; and recommends what the site should
say.

Deliverable: `src/camino/sources/local_help.py` and `tests/test_local_help.py`, both new and
standalone. **Nothing else in the repository was modified**, no build was run, and nothing
here changes what the live site publishes today. Integration is a separate decision.

---

## Headline

| | |
|---|---|
| American Job Centers CareerOneStop holds for California | **183** (85 comprehensive, 98 affiliate) |
| Requests needed to fetch all of them | **1** |
| Cities in our program data | 227 |
| Cities with a center within 10 / 25 / 50 miles | **184 / 224 / 227** |
| Cities with a *comprehensive* center within 10 / 25 / 50 miles | 147 / 213 / 223 |
| Median distance from a city to its nearest center | **4.0 miles** |
| Program pages that could carry a real office within 25 miles | **3,234 of 3,266 (99.0%)** |
| Centers with a published phone number and opening hours | 183 / 183 |

The locator is reachable, complete, and close enough to almost everywhere we publish a
program that "here is where to ask" is a real sentence rather than an aspiration.

The funding path is more delicate, and the rest of this document is mostly about the
delicacy: **nothing on this site can determine whether a person gets funded**, and the
single largest risk this feature carries is that a page implies otherwise and someone takes
a morning off work for a "no".

---

## Part 1 — How a Californian actually gets a WIOA-funded training seat

Everything in this section is from the Code of Federal Regulations (title 20, parts 678, 680
and 681, the WIOA title I regulations) or from California EDD's own pages. Section numbers
are given so each claim can be checked; the module carries the same citations as data, so
they reach the page attached to the sentence they support rather than sitting in a comment.

### 1.1 The instrument is an Individual Training Account

> "Training services for eligible individuals are typically provided by training providers
> who receive payment for their services through an ITA. The ITA is a payment agreement
> established on behalf of a participant with a training provider."
> — [20 CFR 680.300](https://www.ecfr.gov/current/title-20/section-680.300)

An ITA is not a grant a person applies for and receives. It is an agreement between a local
workforce board and a provider, made on that person's behalf, and it may be paid in
instalments rather than up front (same section). That distinction matters for the wording:
somebody does not "get an ITA", they are *referred* with one.

### 1.2 An ITA can only pay a provider on the state list — which is where our data comes from

> "An ETP: (a) Is the only type of entity that receives funding for training services … through
> an individual training account; (b) Must be included on the State list of eligible training
> providers and programs…"
> — [20 CFR 680.410](https://www.ecfr.gov/current/title-20/section-680.410)

This is the load-bearing fact for the whole feature. The federal ETP scorecard (source D1)
publishes the ETA-9171 performance report, which states file for the programs on their
Eligible Training Provider List. So every program this project publishes was on California's
ETPL as of that report.

**But only as of that report.** Initial eligibility runs for one year and providers must
reapply ([20 CFR 680.450, 680.460](https://www.ecfr.gov/current/title-20/section-680.450)),
and a provider can be removed for supplying inaccurate information
([680.480](https://www.ecfr.gov/current/title-20/section-680.480)). The honest sentence is
"was listed when the state last reported", not "is eligible for funding" — which is exactly
what `local_help.etpl_listing_note()` produces, and why it takes the snapshot date as an
argument instead of hard-coding one.

Two further traps in the same area:

- **Eligibility attaches to a program, not a school.** A listed provider can offer unlisted
  programs. 680.410(c) requires the entity to "provide a program of training services", and
  the state list is of "eligible training providers **and programs**" throughout subpart D.
- **Some training is outside the ETPL entirely.** On-the-job training, customized training,
  incumbent worker training and transitional jobs are explicitly *not* subject to ETPL
  requirements ([20 CFR 680.530](https://www.ecfr.gov/current/title-20/section-680.530)) and
  are funded by contract rather than ITA
  ([680.320](https://www.ecfr.gov/current/title-20/section-680.320)). Our data does not cover
  those, so the site must not imply that the ETPL is the whole of what a job center can fund.

### 1.3 Who can be served at all

Before any of the training-specific tests, there is a general eligibility floor. California
states it as three items — from the WIOA Title I Eligibility Technical Assistance Guide
(attachment 1 to EDD directive WSD24-04): "Age", "Selective Service System Registration (as
applicable)", "Authorization to work in the United States".

The part worth putting on a page is *when* the third is checked:

> "Many services provided through the WIOA Title I Adult, Dislocated Worker, and Youth
> programs may be delivered without proof of the participant's work authorization. Staff does
> not need to verify work authorization until the participant is moving into services that
> require such authorization."

The guide then lists what a local area may deliver without verifying it, including career
assessments, development of an individual employment plan, one-on-one case management, career
planning, basic skills education "including English language instruction", "[a]ssistance in
completing paperwork to finalize work authorization", and referrals for transport, childcare,
food, housing and medical assistance.

For a bilingual California site this is not a footnote. A reader who assumes the door is shut
will not walk through it, and a great deal of what is behind that door is open before the
question is ever asked. `local_help.STEPS` carries this as its own step.

### 1.4 Who decides, and on what

Not the state, not the provider, and emphatically not this site. The determination is made
at a one-stop center:

> "…an individual must at a minimum receive either an interview, evaluation, or assessment,
> and career planning or any other method through which the one-stop center or partner can
> obtain enough information to make an eligibility determination…"
> — [20 CFR 680.220(a)](https://www.ecfr.gov/current/title-20/section-680.220)

The substance of the decision is three findings plus a fit test
([20 CFR 680.210](https://www.ecfr.gov/current/title-20/section-680.210)). Training services
may be made available to adults and dislocated workers who a center determines are:

1. "Unlikely or unable to obtain or retain employment that leads to economic
   self-sufficiency … through career services";
2. "In need of training services" to get there; and
3. "Have the skills and qualifications to participate successfully in training services".

and who select a program "directly linked to the employment opportunities in the local area
or the planning region, or in another area to which the individuals are willing to commute
or relocate", and who cannot get grant assistance elsewhere (680.210(b)–(c)).

Two useful details. There is **no federally required minimum time in career services** before
training (680.220(c)) — a local area may still have one. And a recent assessment can be
reused rather than repeated (680.220(a)).

### 1.5 Priority is a legal requirement, and it runs one way

For the **adult** funding stream:

> "…priority for individualized career services … and training services funded with title I
> adult funds must be given to recipients of public assistance, other low-income individuals,
> and individuals who are basic skills deficient … in the local area."
> — [20 CFR 680.600(a)](https://www.ecfr.gov/current/title-20/section-680.600)

Priority does **not** mean exclusion — 680.600(c) says so explicitly — and the criteria for
applying it are set by states and local areas (680.600(b)). It does **not** apply to
dislocated worker funds ([680.610](https://www.ecfr.gov/current/title-20/section-680.610)).

Separately, veterans and eligible spouses have priority of service across programs funded by
the U.S. Department of Labor, meaning "the right to take precedence over non-covered persons
in obtaining services"
([20 CFR 1010.200](https://www.ecfr.gov/current/title-20/section-1010.200)), and centers are
required to identify covered persons at the point of entry
([1010.300](https://www.ecfr.gov/current/title-20/section-1010.300)).

California turns this into an explicit order that job center staff must work. From EDD
directive WSD24-06, *Adult Program Priority of Service* (Nov. 2024), restating TEGL 19-16:

1. Veterans and eligible spouses who are **also** recipients of public assistance, other
   low-income individuals, or individuals who are basic skills deficient;
2. Recipients of public assistance, other low-income individuals, or individuals who are
   basic skills deficient;
3. Veterans and eligible spouses not in one of WIOA's priority groups;
4. **Priority populations established by the Governor and/or the Local Board**;
5. Everyone else.

Tier 4 is another place the 45 areas diverge. The directive also notes that priority status
"is established at the time of eligibility determination and does not change during the
period of participation" — so what a person says at the first appointment is what counts.

Practical consequence for the wording: a person should be told to *say* these things, because
the priority only operates if the center knows. That is a step, not a disclaimer.

### 1.6 WIOA money is the last money in, not the first

> "WIOA funding for training is limited to participants who: (1) Are unable to obtain grant
> assistance from other sources to pay the costs of their training; or (2) Require assistance
> beyond that available under grant assistance from other sources…"
> — [20 CFR 680.230(a)](https://www.ecfr.gov/current/title-20/section-680.230)

Centers "must consider the availability of other sources of grants … such as Temporary
Assistance for Needy Families (TANF), State-funded training funds, and Federal Pell Grants,
so that WIOA funds supplement other sources" (680.230(b)). Importantly, a Pell application
does **not** have to be resolved first: a participant "may enroll in WIOA-funded training
while his/her application for a Pell Grant is pending as long as the one-stop center has made
arrangements with the training provider" (680.230(c)).

### 1.7 There is money beyond tuition, and most people do not know to ask

Supportive services — "[l]inkages to community services", "[a]ssistance with transportation",
"[a]ssistance with child care and dependent care", "[a]ssistance with housing" and more — may
be provided to people participating in career or training services who are "[u]nable to obtain
supportive services through other programs"
([20 CFR 680.900](https://www.ecfr.gov/current/title-20/section-680.900),
[680.910](https://www.ecfr.gov/current/title-20/section-680.910)).

Needs-related payments are a separate thing again: adults must "[b]e unemployed", "[n]ot
qualify for, or have ceased qualifying for, unemployment compensation", and "[b]e enrolled in
a program of training services"
([680.940](https://www.ecfr.gov/current/title-20/section-680.940)).

For someone weighing a program whose real barrier is childcare or a bus fare, this is the part
of the system that decides the outcome, and it is invisible from anywhere on the public web
that this project has found.

### 1.8 The obligation to fund has one explicit escape clause

> "Unless the program has exhausted training funds for the program year, the one-stop center
> must refer the individual to the selected provider, and establish an ITA…"
> — [20 CFR 680.340(c)](https://www.ecfr.gov/current/title-20/section-680.340)

That clause is the honest caveat, and it comes from the regulation rather than from hedging.
Once eligible and having chosen, a person has a right to a referral — until the local area's
money for the year has run out. Nothing on a static site can know which side of that line a
given office is on today.

California says the same thing to its own staff, more bluntly than any federal source found.
From the WIOA Title I Eligibility TAG §2.4:

> "The WIOA is not an entitlement program and although an individual may meet program
> eligibility criteria it does not mean that they are guaranteed services. This is because
> funding for WIOA programs is not unlimited. Local Boards must offer services to all eligible
> applicants when funding is available."

`local_help.NOT_AN_ENTITLEMENT` carries this, **paraphrased rather than quoted**. The
promissory-language check in the tests refuses the word "guaranteed" even inside a negation,
and that turned out to be the right call rather than an over-zealous one: a reader skimming a
block of official-looking prose takes the word and drops the "not", and a negation is the
first thing lost in translation. The module says the same thing without the word.

### 1.9 California specifics

**45 local workforce development areas.** EDD's own Eligible Training Provider List page
publishes a "Local Workforce Development Area ETPL Coordinator List"; counting its rows on
2026-08-04 gives exactly 45 areas (Alameda, Anaheim, Contra Costa, Foothill, Fresno, Golden
Sierra, Humboldt, Imperial, Kern Inyo Mono, Kings, Los Angeles City, Los Angeles County,
Pacific Gateway, Madera, Merced, Mother Lode, Monterey, North Bay, North Central Counties
Consortium, NoRTEC, NOVA, Oakland, Orange, Richmond, Riverside, Sacramento, Santa Ana, Santa
Barbara, San Benito, San Bernardino County, South Bay, Santa Cruz, San Diego, SELACO, San
Francisco, San Joaquin, San Jose, San Luis Obispo, Solano, Sonoma, Stanislaus, Tulare,
Verdugo, Ventura, Yolo). That page is also the only place found that names a human contact
per area, with an email address and a phone number.

**The ETPL is administered by EDD and searched through CalJOBS.** EDD's page: "The training
providers on this list are funded through WIOA to help cover training costs", and the search
instructions route through CalJOBS, where "the programs eligible for WIOA funding will display
a green checkmark".

> ⚠️ **`etpl.edd.ca.gov` is dead.** The standalone ETPL search host that older references
> point at does not resolve in DNS at all (checked 2026-08-04). Anything this project links
> for "check the current listing" must go to the EDD page or CalJOBS, not there. Likewise
> `americasjobcenter.ca.gov` does not resolve. Adding either would be adding to the very
> problem this work exists to fix.

**America's Job Centers of California (AJCC)** are the state's branding of the federal
one-stop system. Federal rules distinguish a *comprehensive* center — "a physical location
where job seeker and employer customers can access the programs, services, and activities of
all required one-stop partners", with "at least one title I staff person physically present"
([20 CFR 678.305](https://www.ecfr.gov/current/title-20/section-678.305)) — from an
*affiliated site*, which "does not need to provide access to every required one-stop partner
program" ([678.310](https://www.ecfr.gov/current/title-20/section-678.310)). Both are worth
listing; the type is worth labeling.

**EDD delegates its own office finding to CareerOneStop.** From EDD's Office Locator page:
"To find an AJCC near you, visit CareerOneStop's American Job Center Finder." It adds a
warning worth reproducing: "EDD staff provide employment services to the public, but may not
be physically present at each AJCC location. Please contact an office before visiting to
confirm EDD staff availability."

That single sentence resolves the "which source?" question for this project. Using
CareerOneStop's finder is not a workaround for the absence of a state dataset; it is what the
state itself tells people to use.

### 1.10 What varies by local area — measured, not asserted

First, the federal permission slip. Caps are authorized by
[20 CFR 680.310](https://www.ecfr.gov/current/title-20/section-680.310), **not** by the
consumer-choice section: "the State or Local WDB may impose limits on ITAs, such as
limitations on the dollar amount and/or duration". Two things in the same section are worth a
reader knowing:

- Limits may be "based on the needs identified in the IEP" for one participant, or a flat
  "maximum amount applicable to all ITAs" — so "the cap" may not even be a single number
  (680.310(b)).
- A cap is not necessarily the end of it: "An individual may select training that costs more
  than the maximum amount available for ITAs under a State or local policy when other sources
  of funds are available to supplement the ITA" (680.310(d)).

Other things federal rules hand to the local board: supportive-service caps
([680.920](https://www.ecfr.gov/current/title-20/section-680.920)), whether training outside
the local area or the state is approved
([680.520](https://www.ecfr.gov/current/title-20/section-680.520)), extra ETPL criteria and
higher performance bars ([680.430(e)](https://www.ecfr.gov/current/title-20/section-680.430)),
and needs-related payment levels for adults
([680.970](https://www.ecfr.gov/current/title-20/section-680.970)).

And one that is not a dollar figure but decides the whole determination. The 680.210(a)(1)
test turns on "economic self-sufficiency", which federal rules do not define. California's TAG
§5.3 hands it down: "Local Boards must set criteria for determining whether employment leads
to self-sufficiency. At a minimum, such criteria must provide that self-sufficiency means
employment that pays at least 100 percent of the lower living standard income level (LLSIL)
established for a Local Area." A floor, set locally, often set higher.

Now the numbers. Ten California boards' published ITA policies, read on 2026-08-04
(San Diego, Imperial, San Bernardino, Orange and Fresno read directly for this document;
the remainder from the parallel research pass, each with a verbatim cap sentence):

| Local board | ITA cap | Duration |
|---|---|---|
| Alameda County WDB (2017 — stale) | $5,000; $7,500 combined | 2 years |
| San Benito County WDB (undated page) | $5,000 | ≤12 months |
| San Diego Workforce Partnership | $7,000 | ≤24 months |
| Pacific Gateway (Long Beach) | $7,500 | 12 months, extendable to 18 |
| Fresno Regional WDB | $7,500 non-sector / $10,000 sector / $5,000 truck-bus | 12 months |
| Riverside County WDB | $8,000 | not stated |
| San Luis Obispo County WDB | $8,000 over two years | 2 years |
| Orange County WDB | $10,000 **lifetime** | ≤24 months |
| Imperial County WDB | $14,000 **lifetime** | 12 months |
| San Bernardino County WDB | **not published** — set annually by board action | set annually |

**A 2.8× spread, from $5,000 to $14,000**, plus one board whose number is not written down
anywhere a jobseeker could find it. A sweep of the other thirty-five areas turned up no
published figure for most of them, which is its own finding: for a majority of California, the
amount is simply not discoverable without ringing up and asking.

Three of them in full, because the conditions matter as much as the number:

| Local board | ITA cap | Duration | Other local conditions |
|---|---|---|---|
| San Diego Workforce Partnership (eff. 2025-09-01) | "The maximum amount of an ITA shall not exceed $7,000.00, or the actual cost of the program, whichever is less." | Short-term (≤12 months) preferred; "[l]ong-term trainings cannot exceed 24 months" | Training "must be linked to employment opportunities in the local area" |
| Imperial County WDB | ITAs "may not exceed fourteen thousand ($14,000) dollars, per enrolled individual" — and that is a **lifetime** cap across multiple awards | "Maximum training time will be twelve (12) months" | Exceeding either cap requires written authorization; funds may not pay for failed classes or failed test attempts |
| San Bernardino County WDB (eff. 2019-10-16) | Not published in the policy: "The WDB will establish a maximum dollar amount and duration … on an annual basis." | Set annually, same clause | "Priority for vocational training must be in WDB-established demand industries"; "Priority for training will be given to San Bernardino County residents" |

Beyond the money, the local conditions are gates in their own right. Fresno ties the dollar
amount mechanically to its Demand Occupation List and requires a waiver with labor-market
research attached for anything off it. Orange County requires a Director-signed waiver for an
off-list occupation. Pacific Gateway maintains a **local ETPL narrower than the state's** and
funds only programs on both. San Diego requires local approval on top of state listing.

That is the concrete content of "it varies": a lifetime rather than per-course limit in one
area, a residency preference in another, an occupation gate in a third, and a 2.8× spread in
the headline number. It is why the site can describe the mechanism but must never quote a
figure — and why the most useful question a reader can carry into an office is "what is it
here?".

One caution on method: several California workforce sites (`workforce.org`,
`ivworkforce.com`, `rivcoworkforce.org`, LA County's AJCC site) answer 403 to programmatic
fetchers while serving the same PDFs to a browser. Any automated survey of California ITA
policy will systematically under-report, and this one is no exception — Los Angeles City and
County, the two largest areas by far, could not be read at all.

---

## Part 2 — The center locator

### 2.1 Why the earlier probes returned 404

`/v1/AJCFinder/…` and `/v1/ajcfinder/…` both 404 when called with two or three path segments.
The endpoint is real; the route is **positional and takes ten arguments after the user id**:

```
GET /v1/ajcfinder/{userId}/{location}/{radius}/{centerType}/{youthServices}
        /{workersServices}/{businessServices}/{sortColumns}/{sortDirections}
        /{startRecord}/{limitRecord}
```

With any segment missing, no route matches and the framework answers 404 — which reads as
"no such endpoint" rather than "wrong arity". That is the entire explanation.

Confirmed working with this project's credentials on 2026-08-04. The route is
case-insensitive — `/v1/AJCFinder/…` answers identically — so capitalization was never the
problem. Two sibling endpoints also answer: `/v1/ajcfinder/{userId}` (every center in the
country, 2,146 of them) and `/v1/ajcfinder/{userId}/{jobCenterId}` (one center's detail).
`tests/test_local_help.py` carries a regression asserting the full segment list, so the
misdiagnosis cannot recur silently.

### 2.2 What comes back

`location` accepts a ZIP (`95814`), a `city, state` pair (`los angeles, ca`, percent-encoded),
or a bare state code. A state code returns the whole state: `CA` gives 183 centers, and every
California center found by probing border ZIP codes was already in that set. So **one request
covers the state**, and the module ranks locally by great-circle distance instead of asking
the endpoint 227 times. Cross-checked against the API's own distance figure for Coalinga →
Mendota: CareerOneStop says 42.3 miles, the local computation says 42.2.

Completeness of the 183 California records:

| Field | Populated |
|---|---|
| Name, address, phone, opening hours, coordinates | 183 / 183 |
| Website | 174 / 183 |
| General email address | 110 / 183 |
| Veterans' representative stated | 183 / 183 (87 yes) |
| Lists "Getting Skills and Education" among its services | 164 / 183 |

A border ZIP search returns out-of-state centers (Blythe's nearest are in Arizona). That is
correct, not a bug — but they are not centers that can open a *California* ITA, so anything
published for a Californian filters on state. The module documents this and exposes the field
to filter on.

**The per-center detail endpoint is deliberately not used.** It carries a "Language
Capability" field that would matter more to this project's Spanish-speaking readers than
almost anything else on the page — but in a random ten-center sample, nine were blank. 183
extra requests to publish a field that is usually missing, where a blank renders as
"languages: none", is the unknown-as-absent error this codebase exists to prevent, bought at
the cost of being a worse guest on a public endpoint. If that field is ever populated
consistently, this decision should be revisited; it is a data-quality judgement, not a
principle.

### 2.3 Coverage against the 227 cities

Measured with `local_help.measure_coverage` against `data/processed/programs.json`, snapshot
2026-08-04. All 227 cities carry coordinates, so nothing here is "unknown" being counted as
"uncovered".

| Within | Cities with any center | Cities with a comprehensive center |
|---|---|---|
| 10 miles | 184 / 227 (81.1%) | 147 / 227 (64.8%) |
| 25 miles | **224 / 227 (98.7%)** | 213 / 227 (93.8%) |
| 50 miles | 227 / 227 (100%) | 223 / 227 (98.2%) |

Median distance from a city to its nearest center: **4.0 miles**.

Weighted by program page rather than by city — which is what a reader actually experiences,
since Los Angeles has 262 programs and Coalinga has few:

| Within | Program pages with any center | With a comprehensive center |
|---|---|---|
| 10 miles | 2,897 / 3,266 (88.7%) | 2,595 (79.5%) |
| 25 miles | **3,234 / 3,266 (99.0%)** | 3,142 (96.2%) |
| 50 miles | 3,266 / 3,266 (100%) | 3,221 (98.6%) |

The eight worst-served cities, nearest center in miles: Coalinga 38.7, South Lake Tahoe 36.5,
Lemoore 26.7, Paso Robles 24.1, Truckee 23.7, Placerville 23.6, Napa 21.4, Escondido 20.5.

Distances are straight-line. In the Central Valley that is close to road distance; over the
Sierra it is not, and South Lake Tahoe's 36.5 miles is a mountain pass. Anything rendered
should say "about", or omit the number and simply order the list.

### 2.4 Graceful degradation

`fetch_centers()` returns `None` with no credentials and makes no request, exactly like the
occupation client — CI has none and must still build. It also returns `None` when the endpoint
cannot be read, and an **empty tuple** when the endpoint answered and held nothing. Those are
different facts: "we could not check" is not "California has no job centers", and a consumer
renders them differently. Responses cache to disk keyed on the exact request, so a narrower
earlier read can never be served as the answer to a wider one.

---

## Part 3 — What to ask before committing

Fourteen questions, in `local_help.QUESTIONS`, each carrying the rule that makes it worth
asking. They are split by who can answer, because sending someone to a job center to ask about
a syllabus wastes the appointment.

**To the training provider** — five questions:

1. *Is this program on California's ETPL right now?* Eligibility is granted per program, not
   per school, and it is time-limited and renewed (20 CFR 680.410, 680.450).
2. *What does the price include, and what will I still have to buy?* Providers report tuition
   and supplies as separate figures and either can be missing (20 CFR 680.490), so the cost on
   our page may be a floor. Exam and licensing fees are often outside both.
3. *What exactly do I hold at the end, who issues it, and does an employer or licensing board
   recognize it?* A listed program must lead to a credential, employment, or measurable
   progress toward one (20 CFR 680.420) — and a school's certificate of completion and a state
   license are very different things to be holding.
4. *If I stop partway, what do I owe?* An ITA is a payment agreement and may be paid in
   instalments (20 CFR 680.300), so the answer involves the provider and the center together,
   and is a question for before enrolling.
5. *When does the next cohort start and how many hours a week?* Needs-related payments require
   being unemployed **and** enrolled (20 CFR 680.940), so the timetable and the money question
   are the same question.

**To the America's Job Center** — nine questions:

6. *Which funding stream would I be served under — adult, dislocated worker, or youth?* The
   statutory priority applies to adult funds only (680.600, 680.610); out-of-school youth aged
   16–24 can be served by ITAs from youth funds (20 CFR 681.550).
7. *Is this occupation one this local area funds training for?* The program must be linked to
   local employment opportunities (680.210(b)), and priority goes to credentials aligned with
   in-demand sectors (680.340(f)). San Bernardino's policy makes this explicit.
8. *What is the most this area will put into an ITA, and would that cover this program?* Caps
   are local policy (680.310(a)), ranging $5,000–$14,000 across the ten published policies
   found — and a cap need not be the end of it, since training above it is allowed where other
   funds make up the difference (680.310(d)).
9. *Are there training funds left for this program year?* The referral obligation holds
   "[u]nless the program has exhausted training funds for the program year" (680.340(c)). This
   is the one answer a website can never know, and it decides everything.
10. *What should I apply for first — Pell, or anything else?* WIOA is last money in
    (680.230(a)); enrolling with a Pell application pending is allowed if arranged in advance
    (680.230(c)).
11. *Can you help with transport, child care, or living costs while I train?* Supportive
    services and needs-related payments are separate from tuition (680.900, 680.940) and are
    worth raising in the same conversation.
12. *What should I bring, and how long does a determination take?* The determination rests on
    an interview, evaluation or assessment and career planning that the center must document
    (680.220); there is no federal minimum waiting period, so the answer is local.
13. *How does this area define employment that supports a person?* The whole determination
    turns on "economic self-sufficiency" (680.210(a)(1)), which federal rules leave undefined
    and California requires each board to set — at least 100% of the local lower living
    standard income level, often higher.
14. *Can I use this for a program in another county, or another state?* Allowed for programs
    on the state list, subject to local procedure, and across state lines where state and
    local policies permit (680.520). Worth asking anywhere the nearest program is a long
    drive — which in California is a lot of places.

One more belongs on the page rather than in a person's mouth: **say if you receive public
assistance, are on a low income, are basic skills deficient, or are a veteran or an eligible
spouse.** The priority only operates if the center knows (680.600, 1010.300), and California
fixes priority status at the moment of the eligibility determination (WSD24-06) — so it is
the first appointment or nothing.

---

## Part 4 — Recommendation: what the site should say

### 4.1 The shape

A block at the end of every program page, after the outcomes and before the footer, with
three parts:

1. **One sentence naming the possibility.** "Programs on California's Eligible Training
   Provider List can be paid for through an Individual Training Account, arranged by a local
   workforce board." Not "you may qualify for free training".
2. **The nearest one to three America's Job Centers**, by name, address, phone and hours, with
   the comprehensive ones labeled. Phone first: it is the only contact channel populated for
   all 183, and EDD itself advises contacting before visiting.
3. **The questions**, collapsed by default, split by audience.

And running underneath all three, never collapsible and never in the footer:

> Whether a person can have a program paid for is decided by their local workforce
> development board and the America's Job Center staff who interview them — not by this site,
> and not by the training provider. California has 45 local workforce development areas and
> each sets its own policies, so the answer can differ between two people in neighboring
> counties. Nothing here is a promise of funding or a determination of eligibility.

That is `local_help.WHO_DECIDES`, and it is a **field of the value `funding_guidance()`
returns**, not a separate constant. Three module constants would let a template render the
steps and forget the sentence. A field cannot be forgotten, and `tests/test_local_help.py`
asserts that the steps cannot be obtained without it.

### 4.2 The wording rules, and why they are tested

`tests/test_local_help.py::TestWording` scans every published string for phrasings that turn
a description of a public program into a promise to one reader — "you qualify", "guarantee",
"free training", "at no cost to you", "we will pay", "apply here". It is a tripwire rather
than an exhaustive filter: anyone adding a sentence that trips it has to come here and argue
for it. That is the point.

It has already earned its place. The California TAG's own sentence — "it does not mean that
they are guaranteed services" — tripped it, and the right fix was to paraphrase rather than to
loosen the check: a skimming reader takes the word and drops the "not", and a negation is the
first thing lost in translation.

Four specific things the copy must never do:

- **Never say a program *is* WIOA-funded.** It is *listed*, and listing is a precondition, not
  an outcome. `etpl_listing_note(snapshot_date)` exists so the claim is stamped with the date
  it was true and carries "can lapse … may not be listed today".
- **Never quote a dollar cap.** They range 2.8× across the ten published policies found, one
  board does not publish one at all, and 680.310(d) means a cap is not even a hard ceiling.
- **Never imply the ETPL is the whole of what a center can fund.** On-the-job and customized
  training are outside it (680.530) and may be the better answer for some readers.
- **Never imply the door is shut on work authorization.** Verification is service-gated, and
  assessments, an employment plan, case management, English instruction and referrals all sit
  on the open side of that gate (CA TAG §3.3).

### 4.3 What is deliberately *not* recommended

- **An eligibility quiz or checker.** Every input to the real determination — self-sufficiency,
  need, ability to succeed, local demand, other available grants, this year's remaining funds —
  is a judgement made by a person with information this site does not have. A checker would be
  a wrong answer delivered confidently, and it would be believed.
- **Linking the dead hosts.** `etpl.edd.ca.gov` and `americasjobcenter.ca.gov` do not resolve.
  Link EDD's ETPL page, EDD's Office Locator, and CalJOBS.
- **Publishing the per-center "Language Capability" field.** Nine of ten sampled were blank.
- **Fetching centers per city at build time.** 227 requests where 1 will do.

### 4.4 Work this leaves open

- **Spanish.** The module carries English only. Site copy lives in `web/lib/i18n.ts` as a
  typed EN/ES pair, and these strings belong there. They need a reviewer rather than a
  translator: a hedge that survives in English and evaporates in Spanish ("puede" doing the
  work of both "may" and "can") turns a description into a promise for the readers least able
  to absorb the cost of a wasted trip. This is the single highest-risk piece of remaining work.
- **Wiring into `build.py`.** `local_help.places_from_programs()` and `nearest_centers()` are
  the intended seam; nothing was changed.
- **Cadence.** Center records carry a `LastUpdated` date, so a quarterly refresh alongside the
  ETP snapshot is enough. Data as of 2026-08-04.
- **Naming the local board.** The most useful single fact — *which* of the 45 areas a person
  is in — is not in the center records. EDD's coordinator table names a contact per area, and
  a county-to-area mapping would close the gap. Not attempted here; it needs a source that
  can be cited, not a guess from geography.
- **Trade Adjustment Assistance.** 20 CFR 680.210(c) names TAA as one of the "other sources"
  a center must consider, and there are reports that its authority to certify new petitions
  lapsed in 2022. EDD's own TAA page still describes an active petition process, so the two
  do not agree and **nothing about TAA is asserted here or in the module.** If the site ever
  mentions it, someone has to settle that first.
- **A statewide count of AJCCs.** No primary, dated EDD or CWDB source giving one was found;
  "more than 200" circulates without a traceable origin. CareerOneStop's finder holds 183 for
  California, and the honest move is to publish what the finder returns rather than a round
  number nobody can source.

---

## Sources

| Source | URL | Accessed | Used for |
|---|---|---|---|
| 20 CFR part 680 (WIOA title I adult and dislocated worker) | `https://www.ecfr.gov/current/title-20/part-680` | 2026-08-04 | ITAs, eligibility, priority, ETPL, supportive services |
| 20 CFR part 678 (one-stop delivery system) | `https://www.ecfr.gov/current/title-20/part-678` | 2026-08-04 | Comprehensive vs affiliate centers |
| 20 CFR part 681 (youth) | `https://www.ecfr.gov/current/title-20/part-681` | 2026-08-04 | ITAs for out-of-school youth |
| 20 CFR part 1010 (priority of service for veterans) | `https://www.ecfr.gov/current/title-20/part-1010` | 2026-08-04 | Veterans' priority |
| CA EDD — Eligible Training Provider List | `https://edd.ca.gov/en/jobs_and_training/Eligible_Training_Provider_List/` | 2026-08-04 | 45 local areas; ETPL search route; coordinator contacts |
| CA EDD — Office Locator | `https://edd.ca.gov/en/Office_Locator/` | 2026-08-04 | EDD's referral to CareerOneStop; staffing caveat |
| CA EDD — WIOA Title I Eligibility Technical Assistance Guide (WSD24-04, attachment 1) | `https://edd.ca.gov/siteassets/files/jobs_and_training/pubs/wsd24-04att1.docx` | 2026-08-04 | General eligibility; work-authorization gating; self-sufficiency/LLSIL; "not an entitlement" |
| CA EDD — Adult Program Priority of Service (WSD24-06) | `https://edd.ca.gov/siteassets/files/jobs_and_training/pubs/wsd24-06.pdf` | 2026-08-04 | The five-tier priority order; status fixed at determination |
| CareerOneStop Web API — AJCFinder (source D6) | `https://api.careeronestop.org/v1/ajcfinder/...` | 2026-08-04 | 183 California centers |
| San Diego Workforce Partnership — ITA & ATA policy | `https://workforce.org/wp-content/uploads/2025/08/ITA_ATA-Policy_Rev_July-2025.pdf` | 2026-08-04 | $7,000 cap; duration limits |
| Imperial County WDB — ITA policy | `https://www.ivworkforce.com/assets/policies/individual-training-account-ita-policy---june-12,-2023.pdf` | 2026-08-04 | $14,000 lifetime cap; 12-month limit |
| San Bernardino County WDB — policy WDB 2 | `https://workforce.sbcounty.gov/wp-content/uploads/sites/104/WDBoard/WDBPolicies/WDB2-INDIVIDUAL-TRAINING-ACCOUNT.pdf` | 2026-08-04 | Unpublished cap; demand-industry and residency priority |
| Orange County WDB — ITA policy | `https://workforce.ocgov.com/sites/cid/files/2024-02/ITA%20Policy%20Combined.pdf` | 2026-08-04 | $10,000 lifetime cap; 24-month limit; off-list waiver |
| Fresno Regional WDB — ITA amount and duration (PB 04-10 Rev B) | `https://frwdb.net/wp-content/uploads/2022/01/PB_04_10-Rev-B-ITA-Amount-and-Duration.pdf` | 2026-08-04 | Sector-dependent caps; demand-occupation gate |
| Five further California board ITA policies (Alameda, San Benito, Pacific Gateway, Riverside, San Luis Obispo) | see §1.10 | 2026-08-04 | The $5,000–$14,000 range |

The eCFR links resolve for a human reader; eCFR redirects automated clients to an
interstitial, so a link checker will flag every one of them. That is a property of eCFR, not
of the links.

*Note on verification:* every regulation quoted here was read from the eCFR API
(`/api/versioner/v1/full/{date}/title-20.xml?part=…`), not from a search summary. The EDD
directives were read from EDD's own PDF and DOCX files, and the five board policies quoted
were read from the boards' own documents. The five additional caps in §1.10's range table
come from a parallel research pass and are recorded with their verbatim cap sentences; the
`$5,000–$14,000` range does not depend on any of them individually.

*Known gap:* Los Angeles City and Los Angeles County — between them by far the largest share
of California's programs and population — publish ITA policies that could not be retrieved by
any method attempted. The range above is therefore a sample, not a census.
