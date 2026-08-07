# O\*NET Web Services — assessment, 2026-08-04

> **Archival note.** The Python package was renamed `camino` -> `afterward` on
> 2026-08-05. Paths and imports below still say `src/camino/` and `camino.sources.…`
> because this note records what was true on the date in its title; substitute
> `src/afterward/` and `afterward.` when running anything from it.

Read-only assessment of source **D5, O\*NET Web Services (USDOL/ETA)**, which PROVENANCE.md
lists as supplying "tasks, technology skills, work activities, job zones, related occupations"
but which no code has ever read.

Everything below was measured against the live API on 2026-08-04, at `api-v2.onetcenter.org`,
taxonomy **O\*NET-SOC 2019**, database **O\*NET 30.3**, API version 2.0.0 — and against the 670
California occupations in `data/processed/occupations.json`.

Deliverable: `src/camino/sources/onet.py`, a standalone client, with `tests/test_onet.py`.
Integration is a separate step and was not attempted. Nothing outside the three files this
work owns was modified, and no build was run.

---

## Headline

**Integrate it, and integrate the Spanish first.**

O\*NET operates a Spanish-language service, *Mi Próximo Paso*, at `/mpp/`. It is reachable
with this key, needs no separate registration, and serves professionally translated occupation
titles and descriptions for **every California occupation O\*NET holds data for**. The site
currently tells Spanish readers that occupation titles appear in English "porque el estado
solo los publica en ese idioma" — because the state only publishes them in that language. That
is true of the state. It is not true of the federal source the site already depends on.

| | |
|---|---|
| **California occupations with a Spanish title and description** | **600 / 670 (89.6%)** |
| **Spanish coverage of the occupations O\*NET holds data for** | **600 / 600 (100%)** |
| Sampled Spanish titles that were actually English | **0 / 50** |
| Sampled Spanish descriptions missing, untranslated, or part-English | **0 / 50** |

There is **no English/Spanish coverage gap.** The English data tables and Mi Próximo Paso cover
byte-for-byte the same 923 O\*NET occupations. Any occupation this project can show tasks or a
job zone for, it can show in Spanish.

The 70 California occupations with no O\*NET profile at all are 60 residual "…, All Other" /
"Miscellaneous" buckets and 10 EDD broad SOC groups (`31-1120` Home Health and Personal Care
Aides, `29-2010` Clinical Laboratory Technologists and Technicians) that aggregate detailed
occupations rather than naming one. Not one substantive, nameable California occupation is
missing.

**One caveat found late and worth reading before integrating:** a concurrent expansion of the
CareerOneStop client has begun caching `AlternateTitles` and `Tasks`, which are the same
O\*NET content this module also fetches. Section 6.

---

## 1. The real inventory

The starting point is not the documentation. An occupation record is HATEOAS — it links its
own sub-resources by `href`, and guessing paths returns 400 — so the inventory below was read
by following every link from `/online/occupations/29-1141.00/` and fetching each one.

### The occupation record itself

```
code · title · description · sample_of_reported_titles · also_see · bright_outlook ·
tags · updated · summary_contents · details_contents · custom_contents
```

`updated` is more useful than it looks: it dates every content area separately and names its
source. Tasks are Incumbent-sourced from 2021; Technology Skills Analyst-sourced from 2025;
Detailed Work Activities from 2025; Job Titles from 2026. Anything presented to a reader as
"what this job is like today" rests on survey work of varying age, and the record says which.

### The linked sub-resources

Each exists in a `summary/` form (paginated 5 at a time, names and prose) and a `details/`
form (paginated 10 at a time, with ratings). Both accept `start`/`end`; an `end` beyond 1,000
is refused with a 422.

| Sub-resource | What it actually contains |
|---|---|
| Tasks | 27 statements for RNs, each with importance 0–100 and a Core/Supplemental category |
| Technology Skills | 20 UNSPSC categories, each with named products and a hot-technology flag |
| Hot Technologies | 16 named products with the % of job postings mentioning them |
| Work Activities | 32 Generalized Work Activities — "Getting Information", "Documenting/Recording Information" |
| Detailed Work Activities | 37 specific statements — "Record patient medical histories." |
| Work Context | 29 items with response distributions — "Face-to-Face Discussions: 96% every day" |
| Job Zone | one of 1–5, with prose on education, experience, training, examples, and an SVP range |
| Apprenticeship Opportunities | a bare list of RAPIDS occupation titles. No sponsor, no location, no link |
| Skills / Knowledge / Abilities | rated elements on O\*NET's universal scales |
| Education | a frequency distribution of respondent education levels |
| Interests / Work Styles | RIASEC interest codes and personality descriptors |
| Related Occupations | 20 occupations, tiered Primary-Short / Primary-Long / Supplemental |
| Professional Associations | named membership organisations |
| Work Activities Outline (`custom/`) | the GWA → IWA → DWA → task tree, nested, with importance |

### Three service families that are not linked from an occupation record

Found only by reading the service index at `/`, which is worth doing because nothing in an
occupation record points at them:

```
/about/     /database/     /mnm/     /mpp/     /online/     /taxonomy/     /veterans/
```

- **`/database/`** — 46 bulk tables: the O\*NET database itself, one HTTP resource per table,
  paginated up to 1,000 rows. The same content as the per-occupation views, published whole.
  Section 4.
- **`/mnm/`** — My Next Move: the plain-language consumer rewrite.
- **`/mpp/`** — **Mi Próximo Paso**: the same service in Spanish. Section 3.

### 1,016 occupations, of which 923 have any data

Worth stating precisely, because the difference explains every coverage number below.
`/online/occupations/` browses **1,016** codes. The data tables — `job_zones`,
`task_statements`, `software_skills` — each cover exactly **923**, and it is the same 923.

The other 93 have an O\*NET OnLine page and nothing behind it: **77 are "…, All Other" residual
codes** and **16 are military occupations** (`55-1011.00` Air Crew Officers through `55-3019.00`).
They carry zero task rows and zero job-zone rows. A count of "1,016 occupations" is a count of
pages, not of occupations anyone has measured.

### Two things the marketing pages promise that this key does not deliver

- **No rate-limit headers.** No `X-RateLimit-*` of any kind, so there is no published budget to
  spend against. A reason to be more careful, not less.
- **No language negotiation on the English service.** `?lang=es`, `?language=es`, `?locale=es`
  and `Accept-Language: es` all return English from `/online/`. Spanish is a separate service
  at a separate path, not a parameter. This matters: the obvious probe — the one CareerOneStop
  was tested with, where it genuinely failed — returns HTTP 200 with English in the body, which
  reads exactly like "no Spanish available" if you stop there.

---

## 2. What was selected, and what was rejected

The test applied to every item: **does this help a Californian decide whether to spend a year
and thousands of dollars on training?** Anything that only decorates the page was rejected.

### Selected

**Spanish title and description** (`/mpp/careers/{code}/` → `title`, `what_they_do`). Section
3. Not an enhancement; it repairs a defect the site already documents in `web/lib/vocabulary.ts`
and apologises for in `web/lib/i18n.ts`. Nothing else in this project's reach can supply it.

**Spanish job titles** (`also_called`, same request). The only way a reader searching in
Spanish finds anything at all.

**Technology Skills.** Unique to O\*NET — CareerOneStop carries no technology field — and the
most concrete thing here. A nursing programme that never mentions Epic, or an office
programme that teaches no Excel, is visibly weaker preparation, and that is a comparison a
reader can make without a counsellor. O\*NET's own Hot Technology and In Demand flags do the
ranking, so this project asserts no judgement of its own about which tools matter.

**Job Zone.** Also unique to O\*NET. A 1–5 preparation level with prose covering education,
prior experience, *and* on-the-job training — materially more decision-relevant than EDD's
single `entry_level_education` string, because the thing that sinks a training plan is usually
the part that is not the diploma. Job Zone 3 says in as many words that an electrician needs
"three or four years of apprenticeship or several years of vocational training, and often must
have passed a licensing exam." That is the actual answer to "is this one-year certificate
enough?"; "Postsecondary non-degree award" is not.

**Tasks.** The direct answer to "what would I actually be doing", in incumbent-reported
sentences rather than an abstraction. Core/Supplemental is carried through, because "central
to the job" and "sometimes part of the job" are different claims. *See section 6 — CareerOneStop
began serving the same statements today.*

**`sample_of_reported_titles`.** The strongest search improvement available here. The site's
index carries the official SOC title — "Registered Nurses", "Heating, Air Conditioning, and
Refrigeration Mechanics and Installers". Nobody types those. O\*NET publishes what people
actually call the job. Measured effect in section 5. *Also see section 6.*

### Rejected

**Related Occupations / `also_see` — data the site already has.** PROVENANCE.md already credits
D6 with "O\*NET related occupations", and it means it literally: CareerOneStop is a DOL front
end serving O\*NET content. Compared against the CareerOneStop responses cached in
`data/raw/cos-cache/`, over 612 occupations that carry both:

| | |
|---|---|
| CareerOneStop's list identical to O\*NET's Primary tier | **523 (85.5%)** |
| A subset of O\*NET's full 20 | 79 (12.9%) |
| Containing something O\*NET's list does not | 10 (1.6%) |

Fetching this again would spend requests on a public service to receive bytes already on disk.
**Not fetched, and no code in this module reads it.**

**Work Activities.** The one rejection worth arguing. Generalized Work Activities are rated on
a scale shared by all 923 occupations, which is what makes them comparable and also what makes
them useless here: the top four for Registered Nurses are "Assisting and Caring for Others",
"Documenting/Recording Information", "Getting Information" and "Updating and Using Relevant
Knowledge". Three of those four describe almost any job, and a reader choosing between two
programmes learns nothing. Detailed Work Activities *are* concrete ("Record patient medical
histories.") but are a near-restatement of the tasks already selected — the
`custom/work_activities_outline` resource shows the mapping explicitly, each DWA hanging off
the very task statements this client keeps. Carrying both would be one fact printed twice.

**Work Context.** Genuinely interesting — 96% of RNs have face-to-face discussions every day;
exposure to disease; time spent standing — but it describes conditions rather than feeding a
spend-a-year-and-$8,000 decision, and it is 29 items deep per occupation. A candidate for
later, not for this pass.

**Skills, Knowledge, Abilities.** CareerOneStop already supplies O\*NET skill ratings and the
site already renders them.

**Education (`details/education`).** A frequency distribution of what respondents *nationally*
happen to hold. EDD publishes the entry-level education requirement *for California* and the
site shows it. Two different measures under one word, disagreeing on the same page, with the
weaker one national.

**Apprenticeship Opportunities.** The most tempting rejection, because "earn while you learn,
no tuition" is the right answer for many people reading this site. What the endpoint returns is
three strings: `["Registered Nurse", "Registered Nurse (Nof)", "Registered Nurse Resident"]`.
No sponsor, no location, no link, no indication any of it exists in California. On a site whose
whole value is naming real programmes with real reported outcomes, "an apprenticeship title
exists somewhere in the federal registry" is a worse answer than silence. The right source is
DOL's Apprenticeship Finder — a separate integration, and a good candidate for one.

**Interests, Work Styles, Professional Associations.** Career-exploration furniture.

**Bright Outlook.** Already on the page via CareerOneStop.

**Mi Próximo Paso `job_outlook.salary`.** National BLS figures — a $97,550 national median for
RNs against EDD's California median. Two numbers labelled the same thing that are not the same
thing.

**Mi Próximo Paso `on_the_job` — the Spanish task list.** Rejected on quality, and the finding
most at risk of being lost. The Spanish *descriptions* are clean; the Spanish *task strings*
are not, and nothing in the payload distinguishes the good from the bad. Registered Nurses:

> `"información de los pacientes Record 'médicos y los signos vitales."`

Electricians:

> `"Conducto de su lugar, tuberías o tubos, de las particiones dentro designado, paredes, u
> otras áreas encubiertas, y tire de los cables aislados o cables a través del conducto…"`

Heavy Truck Drivers, by contrast, is fluent. Shipping the lot would give a Spanish reader a
page that looks translated and reads as broken — worse than an honest English task list beside
a Spanish title and description. `parse_spanish()` deliberately has no field for it, and a test
asserts the absence.

---

## 3. Spanish — the definitive answer

**Yes. Spanish occupation titles and descriptions are reachable with this key.**

The service is *Mi Próximo Paso*, at `https://api-v2.onetcenter.org/mpp/`. It authenticates
with the same `X-API-Key` header, needs no separate registration, and uses the same O\*NET-SOC
codes as the English service, so it joins to everything this project already has with no
crosswalk.

It is not discoverable from an occupation record. It appears only in the service index at `/`,
beside `/mnm/` and `/veterans/`. Every path that looks right is a 404 —
`/mpp/carreras/29-1141.00/`, `/mnm/espanol/`, `/online/es/occupations/…`. The one that works is
`/mpp/careers/{code}/`: English path segment, Spanish payload.

```
GET /mpp/careers/29-1141.00/

title         "Enfermeros Graduados"
what_they_do  "Evalúan los problemas y necesidades de salud de los pacientes, desarrollan e
               implementan planes de atención de enfermería y mantienen los registros médicos
               de los pacientes. Administran atención de enfermería a pacientes enfermos,
               lesionados, convalecientes o discapacitados…"
also_called   "Enfermero de Personal", "Enfermero Escolar", "Enfermero Responsable", …
```

### Coverage

| | |
|---|---|
| Occupations in Mi Próximo Paso | 923 |
| Occupations in the O\*NET data tables (`job_zones`, `task_statements`, `software_skills`) | 923 |
| Are they the same 923? | **Yes — set-identical** |
| **California occupations with a Spanish record** | **600 / 670 (89.6%)** |
| …as a share of the California occupations O\*NET holds any data for | **600 / 600 (100%)** |
| California occupations with English data but no Spanish | **0** |

This is the cleanest possible result and it took a wrong turn to find. Comparing the Mi Próximo
Paso career list (923) against the O\*NET OnLine *browse* list (1,016) suggests 93 occupations
have English but no Spanish — 58 of them Californian. That is an artefact: those 93 codes have
an OnLine page and no data of any kind. Compared against the tables that actually hold data,
the Spanish coverage is exactly, entirely complete.

The 70 California occupations with no profile break down as:

| | |
|---|---|
| Residual "…, All Other" / "Miscellaneous" buckets | 60 |
| EDD broad SOC groups with no detailed O\*NET occupation | 10 |

The 10: `13-1020` Buyers and Purchasing Agents · `13-2020` Property Appraisers and Assessors ·
`21-1018` Substance Abuse, Behavioral Disorder, and Mental Health Counselors · `25-2052`
Special Education Teachers, Kindergarten and Elementary School · `25-9045` Teaching Assistants,
Except Postsecondary · `29-2010` Clinical Laboratory Technologists and Technicians · `31-1120`
Home Health and Personal Care Aides · `39-7010` Tour and Travel Guides · `51-2028` Electrical,
Electronic, and Electromechanical Assemblers · `53-1047` First-Line Supervisors of
Transportation and Material Moving Workers.

`31-1120` is the one that stings — Home Health and Personal Care Aides is among the largest and
fastest-growing occupations in California. EDD publishes it at the broad-group level; O\*NET
holds `31-1121` Home Health Aides and `31-1122` Personal Care Aides separately. Bridging that is
a SOC-vintage decision `soc_vintage.py` owns, not this module.

### Quality

Fifty California occupations sampled at random, each Spanish record compared to its English
counterpart:

| | |
|---|---|
| Spanish title identical to the English title (i.e. untranslated) | **0 / 50** |
| Spanish description missing | **0 / 50** |
| Spanish description identical to the English description | **0 / 50** |
| Spanish description containing untranslated English fragments | **0 / 50** |

These read as human translations, register-appropriate for a public service:

| English | Spanish |
|---|---|
| First-Line Supervisors of Mechanics, Installers, and Repairers | Supervisores Directos de Mecánicos, Instaladores y Reparadores |
| Helpers—Extraction Workers | Ayudantes de Trabajadores de Ocupaciones Relacionadas con la Extracción |
| Cooks, Short Order | Cocineros de Platos de Preparación Sencilla |
| Electrical and Electronics Drafters | Delineantes de Sistemas Eléctricos y Electrónicos |
| Heavy and Tractor-Trailer Truck Drivers | Conductores de Camión Pesado y Tractocamión |

The task strings are the exception, and only the task strings — see the rejection in section 2.

### What this does not fix

Being precise about the limit, because overclaiming here would be the worst possible outcome:

- **Programme names and provider-filed descriptions stay English.** They come from the DOL ETP
  scorecard (D1), are free text filed by 584 California providers, and no translation exists
  anywhere. `web/lib/i18n.ts`'s `programTextEnglishOnly` must stay on the page — but *the
  clause about occupation titles inside it becomes false*. It currently tells a Spanish reader
  that programme names, programme descriptions **and occupation titles** appear in English
  "porque es el único idioma en que los publican los registros federales y estatales". The
  federal record does publish occupation titles in Spanish. That sentence needs narrowing to
  the two things it is still true of, and `titlesEnglishOnly` needs the same treatment.
- **Wages, growth, openings and outcome measures are unaffected.** Numbers, not text.
- **The 70 uncovered occupations still need an English fallback**, and the reader must be able
  to tell that is what they are seeing. The client returns `es: null` rather than silently
  substituting the English string, so the display layer can say so.

---

## 4. Being a good guest: 61 requests instead of 2,700

Reading tasks, technology skills, job zone and reported titles through the per-occupation
sub-resources costs four requests per occupation — about **2,700** for California's 670, more
with the summary views' 5-per-page default.

The `/database/rows/` service publishes the same content as whole tables:

| Table | Rows | Requests at 1,000/page |
|---|---|---|
| `job_zone_reference` | 4 | 1 |
| `job_zones` | 923 | 1 |
| `sample_of_reported_titles` | 7,953 | 8 |
| `task_statements` | 18,796 | 19 |
| `software_skills` | 31,821 | 32 |
| | | **61** |

**The tables are not a different dataset.** For 29-1141.00, `task_statements` returns the same
27 statements as `details/tasks`, in the **same order** — which matters, because that order is
importance-descending and the bulk table carries no importance column. The client preserves
source order and does not re-sort, so the top task really is the most important one. The
equivalence is recorded in the module docstring and in `parse_tasks`'s docstring so a future
reader does not "improve" it by sorting.

Spanish has no bulk table and is the one thing fetched per occupation: **600 requests**,
serialised, 0.3s apart, cached on disk. A first build costs about 661 requests total; every
build after that costs none, since `data/raw/` is gitignored but persists locally between runs.

Nothing here fetches in parallel. There are no rate-limit headers to spend against, the service
is funded by taxpayers, and `USER_AGENT` is reused from `dol_etp` unchanged so O\*NET can see
exactly who is calling and where to complain.

---

## 5. Coverage over California's 670, measured through the client

Produced by running `fetch_profiles()` over every SOC in `data/processed/occupations.json`.

| Field | n | % of 670 |
|---|---|---|
| Any O\*NET profile | 600 | 89.6% |
| Tasks | 600 | 89.6% |
| Technology skills | 600 | 89.6% |
| …including at least one Hot Technology | 591 | 88.2% |
| Job Zone | 600 | 89.6% |
| Reported job titles | 591 | 88.2% |
| **Spanish title** | **600** | **89.6%** |
| **Spanish description** | **600** | **89.6%** |
| Spanish job titles | 591 | 88.2% |

Median per occupation after the client's caps: 8 tasks, 10 tools, 10 reported titles.

### Job Zone distribution

| Zone | California (600) | Whole database (923) |
|---|---|---|
| 1 | 0 | **0** |
| 2 — Very little to some preparation | 239 | 331 |
| 3 — Medium preparation | 146 | 212 |
| 4 — Considerable preparation | 137 | 226 |
| 5 — Extensive preparation | 78 | 154 |

**Zone 1 is empty across the entire O\*NET database**, which is why the reference table
publishes four rows and labels the lowest "Job Zone 1-2". The client still handles a zone-1
occupation — keeping its number with empty prose rather than promoting it to zone 2 — but that
path is defensive, not observed, and the test says so.

Two-thirds of California's occupations sit in zones 2 and 3, which is exactly the population
this site is for: work reachable through a certificate or an associate's degree rather than a
four-year degree.

### What reported job titles do for search

591 of the 600 occupations (98.5%) gain at least one search term their official title does not
contain. Matching on whole tokens rather than substrings, so these are real hits:

| Query | Occupations it newly reaches |
|---|---|
| `RN` | Registered Nurses |
| `LVN` | Licensed Practical and Licensed Vocational Nurses |
| `CNA` | Nursing Assistants |
| `CMA` | Medical Assistants, Nursing Assistants |
| `EMT` | Emergency Medical Technicians |
| `EKG` | Cardiovascular Technologists and Technicians |
| `HVAC` | Heating, Air Conditioning, and Refrigeration Mechanics; Sheet Metal Workers; +2 |
| `CDL` | Heavy and Tractor-Trailer Truck Drivers; Bus Drivers, School |
| `IT` | Computer and Information Systems Managers; Computer Systems Analysts; +6 |

Every one of those is currently unreachable by that name. Someone who knows precisely what job
they want — which describes most people arriving at a training-programme search — cannot
currently find it, because they know it by its real name and the index only holds the
statistical one.

---

## 6. Overlap with the CareerOneStop client — read before integrating

Found late, from the cache on disk. `data/raw/cos-cache/` has been rewritten today into a
`cache_format: 2` envelope, and the request parameters recorded inside it now include
`alternateOnetTitles: true` and `tasks: true`. In other words a concurrent expansion of the
CareerOneStop client is fetching two of the things this module fetches. Measured over the
cached responses:

| Field | CareerOneStop vs O\*NET | Verdict |
|---|---|---|
| `AlternateTitles` vs `sample_of_reported_titles` | **identical for 596 / 603 (98.8%)**; the other 7 have a few extra titles | same data |
| `Tasks` vs `task_statements` | **identical for 538 / 592 (90.9%)**; 54 are a subset of O\*NET's; **0 contain a task O\*NET lacks** | same data |
| `RelatedOnetTitles` vs `related_occupations` | identical to O\*NET's Primary tier for 523 / 612 (85.5%) | same data |
| Technology skills | **CareerOneStop has no technology field** | O\*NET only |
| Job Zone | **CareerOneStop has no job zone** | O\*NET only |
| Spanish | CareerOneStop returns English for `language=es` | O\*NET only |

Neither client was changed in response to this — that is the integrator's decision, and the
concurrent work may still move. What the integrator needs to know:

- **Take each field from one source, not both.** Tasks and reported titles appear in both.
- **They are not quite interchangeable.** O\*NET's task table carries the Core/Supplemental
  category and CareerOneStop's does not; CareerOneStop's carries a numeric `DataValue`
  importance and O\*NET's bulk table does not (it encodes importance as row order instead).
  O\*NET's task list is a superset in 9% of cases; CareerOneStop's title list is a superset in
  1%.
- **If tasks and titles come from CareerOneStop, this module's bulk reads drop from 61
  requests to 2** (`job_zones` + `job_zone_reference`) **plus 32 for `software_skills`.** The
  600 Spanish requests are unaffected and irreducible.
- **Nothing about the Spanish, technology or job-zone case changes either way.** Those three
  exist nowhere else.

---

## 7. The attribution the site must display

The O\*NET Web Services Data License requires attribution and a link in any product using the
Services. **This is a licence condition, not a courtesy, and it is already owed today** — the
skill ratings, related occupations and descriptions the site publishes via CareerOneStop are
O\*NET content served through a DOL front end.

The exact string the site must display:

> This site incorporates information from O\*NET Web Services by the U.S. Department of Labor,
> Employment and Training Administration (USDOL/ETA). O\*NET® is a trademark of USDOL/ETA.

with a link to <https://services.onetcenter.org/>.

It is `onet.ATTRIBUTION` in code and `onet.ATTRIBUTION_URL` for the link, and it is emitted on
every profile by `OnetProfile.as_dict()` so it travels with the data rather than depending on
someone remembering a footer. A test asserts it survives the round trip to JSON.

Two further conditions worth recording:

- **The ® is part of the string.** O\*NET is a registered trademark of USDOL/ETA; dropping the
  symbol is a trademark-usage problem, not a typographic preference.
- **The notice must not be removed while any O\*NET-derived field is displayed** — including
  the CareerOneStop-sourced ones, so it cannot be scoped to the sections this module feeds.

---

## 8. Recommendation

**Integrate, in this order.**

1. **Spanish titles and descriptions.** The only item here that repairs a documented defect
   rather than adding a feature, for the population `web/lib/i18n.ts` itself identifies as
   "among the least well served by English-only government software". 600 of 670 occupations,
   100% of the ones O\*NET holds data for, zero untranslated in a 50-occupation sample, and
   available from no other source this project can reach.
2. **Reported job titles into the search index.** Cheap, high-recall, and it fixes the case
   where someone who knows exactly what job they want cannot find it because they know it by
   its real name. Source it from whichever client wins section 6.
3. **Job Zone on the occupation page**, beside EDD's entry-level education rather than instead
   of it. They answer different questions.
4. **Technology skills**, which nothing else here can supply.
5. **Tasks**, from one client only.

### Conditions

- **`es: null` must render as a visible English fallback**, never a silent substitution. A page
  that looks Spanish and is not is the failure mode this whole item exists to prevent.
- **Never ship the Spanish task strings.** Section 2.
- **Do not re-fetch related occupations.** The site already has them.
- **Resolve the tasks/titles overlap before both land.** Section 6.
- **The attribution ships with the first O\*NET-derived field to reach the page**, and the
  existing CareerOneStop-derived fields mean it is owed now regardless.
- **Do not present Job Zone as contradicting EDD's education field.** O\*NET rates the
  occupation nationally; EDD reports the California entry requirement. Where they differ, both
  are right about different questions.
- **Add `ONET_API_KEY` to `.env.example`**, with the same "optional; the build works without
  it" note the CareerOneStop credentials carry. It is not there yet.
- **Cache under `data/raw/onet-cache/`**, which `data/raw/` already gitignores.

### What is deliberately not in the module

- No importance figure on tasks. The bulk table publishes none, the row order already encodes
  it, and inventing a rank would assert something O\*NET did not say.
- No re-sorting of tasks to put Core first. It would look tidier and would be a claim.
- No `.01`/`.02` variant handling. `onet_code()` maps to `.00` exactly as the rest of the
  project does; collapsing specialisations onto their base occupation is a decision this module
  does not own, and neither is bridging EDD's broad groups — `soc_vintage.py` owns both.
- No fallback from a missing Spanish record to the English string. That belongs to the display
  layer, where it can be made visible.
- No reading of `related_occupations`, despite it being one of the five things PROVENANCE.md
  lists under D5. Section 2 says why, and PROVENANCE.md's D5 row should be narrowed when this
  is integrated.
