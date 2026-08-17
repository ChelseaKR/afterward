# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `make live-check`, and a weekly CI job that runs it: the first gate here that reads
  production rather than an artifact on its way there. Every dataset gate this project has
  runs on the way out — `dataset-verify` before packaging, three guards in the deploy
  workflow before uploading, `publish-preflight` before a hand sync — and none of them runs
  unless somebody deploys. That leaves the interval between a repair landing in the
  repository and a person choosing to publish completely unwatched, and it is the interval
  the last two data faults lived in. The provider-link review landed on 2026-08-15 and
  established that `giligiacollege.com` is no longer the college's; it answers 302 to a
  domain now serving an Indonesian slot-gambling page. Every gate here has refused that
  dataset since. On 2026-08-17 the live site was still serving it, on four program pages
  under that college's name, because no deploy had run and nothing else was looking. The new
  check fetches the dataset the site actually serves and runs the same two gates over it —
  imported, not reimplemented — and refuses rather than reports success when it could not
  measure anything: an empty programs list, or the site's two published documents disagreeing
  about how many programs there are.

- `/ctdl/`, in both languages: the CTDL export's own account of itself, so a mapping nobody
  can check stops being a claim. Which classes and properties it fills in and how often, which
  outcome measures become metrics and observations, what an independent validator found, and —
  the half a coverage page is most tempted to leave out — what the source record says that the
  export drops. The coverage statement now counts that second half: eight things the ETPL
  record carries that this projection does not, each with the CTDL term that would have carried
  it where one exists, so a reader can tell a limit of the vocabulary from a limit of this
  export. Three of them turn on the same documented rule (the concept schemes for delivery
  type, agent sector and direct-cost type are served as HTML pages rather than as data, and
  this export emits no concept it cannot check against machine-readable data); four are outcome
  measures the source reports and this export has not projected; one is a refusal rather than
  an omission, because California's occupation projections describe an occupation and hanging
  them off a program would assert that the program leads to that wage. Four boundary statements
  sit above everything they qualify: nothing here has been published to the Credential Registry,
  this is not affiliated with or endorsed by Credential Engine, the identifiers are locally
  derived rather than Registry-assigned, and it is a demonstration of mapping discipline rather
  than a production publication. Every figure on the page is read from a statement the export
  wrote while it ran; the page computes nothing and types nothing. The two statements are
  committed under `web/public/ctdl/` and served at stable URLs, so each refresh arrives as a
  reviewable diff; the 17 MB graph is not committed, and `make ctdl-package` builds it with a
  checksum instead.
- `make ctdl-validate`: the demonstration CTDL export, checked by something that is not
  itself. The export's existing guards were written by the same hand as the export, against
  the same reading of the same schema, so they cannot catch a mistake in that reading. The
  export is now also run through [`ctdl-validate`](https://pypi.org/project/ctdl-validate/),
  a separate published tool with its own vendored copies of Credential Engine's schema
  encodings and a citation for every rule it applies, consumed as a dependency and never
  modified from here. On the 2026-08-07 snapshot: no errors, and one warning on all 5,907
  entities — `CTID_NOT_UUIDV4`, because the locally derived CTIDs are UUIDv5 and the
  published grammar says v4, which is the tension this export already declared in writing,
  arriving from the outside. No domain violation, no range violation, no unresolved
  reference, no inverse mismatch, no undeclared term. Every finding code must be listed in
  `ACCEPTED_CODES` with a reason or the run fails, so an accepted warning stays counted and
  published rather than filtered, and a new class of finding cannot arrive quietly. The scope
  of the result is published with it in `dist/ctdl/ctdl-validation.json`, because a clean run
  over terms nobody checked is not evidence: that tool drives its schema-based checks from
  the core CTDL and CTDL-ASN encodings it vendors, the QData layer publishes its own encoding
  neither of those contains, and so it could judge 4 of the 7 classes and 17 of the 24
  properties this export emits — a term it has never heard of being one it declines to judge,
  not one it approves. Those counts are computed from the emitted document against the
  validator's own schema index.
- `/outcomes-coverage/`, in both languages: how much of California's training outcomes data
  is actually published. California's Eligible Training Provider List exists only as a
  CalJOBS search screen with no export behind it, so there is no public count of how many of
  the state's listed programs carry evidence of what happened to the people who took them.
  This page produces that count from the federal scorecard the same programs are reported
  into: per measure, per provider category as filed, and against the size of the group each
  figure describes. 1,209 of 3,266 programs publish no completion rate, no employment rate,
  and no earnings figure, and 1,167 of those filed no cohort count either, which are two
  different gaps with two different fixes. The measure most often absent is median earnings
  (1,882 of 3,266), and it is the one measure whose absence cohort size does not explain: it
  stays a quarter of programs unpublished in the largest cohort band, where completion has
  fallen to none and employment to 7%. The provider categories with the most empty rows are
  the ones with the most distinct federal reporting obligations, so the page states those
  obligations beside the table and orders the table by size rather than by blank rate. The
  measures also split cleanly by who produces them: every measure the training provider
  supplies is published more often than every measure the state produces by matching a roster
  against wage records, with no overlap at all between the two groups, which locates the gap
  in a records match rather than in anyone's willingness to report. Every figure carries the
  program-year window and the date the federal record was read: the scorecard publishes no
  program-year field anywhere in its data, states the window only in prose on its About page,
  and its data dictionary still names an earlier year, so an undated coverage figure invites a
  correction that would be right.
- Reporting obligations recorded in `PROVENANCE.md` (I7 to I11) with the primary texts: 20 CFR
  677.230(b) is the operative apprenticeship performance exemption, not 680.470; the federal
  suppression rule is a standard with no published numeric threshold; the `-1` sentinel has
  three documented causes rather than two; and California's current directive (WSD25-02)
  exempts registered apprenticeship from performance reporting and nobody else, so a community
  college or public university with a blank row is not using an exemption.
- Portfolio standards conformance pass (2026-08-07), behavior-preserving: every GitHub
  Action pinned to a full commit SHA with its version noted; a gitleaks secret-scan workflow
  (history verified clean first, 125 commits); Dependabot for actions, pip, and npm;
  CODEOWNERS; CITATION.cff; `.python-version`; a pre-commit config mirroring `make lint`;
  a coverage floor (`fail_under = 85`, measured 92%) and an explicit `max-complexity = 10`
  (ruff's own default, now stated); strict pytest flags; the mypy floor raised to the 1.18
  the lockfile already satisfies. New records: `docs/adr/` (0000 process, 0001 Release &
  Versioning N/A, 0002 typed-module i18n), `docs/ROADMAP.md` (metrics ledger and standard
  declarations), `docs/RESPONSIBLE-TECH-AUDITS.md`, `docs/I18N.md`, and README sections for
  development disclosure and standards conformance.

- Data pipeline joining California's WIOA-reported training programs to the state's
  long-term occupational employment projections. 3,266 programs from 584 providers, 99.5%
  matched to an occupation (3,250 of 3,266; the SOC aggregation table below lifted this from
  the 97.6% first reported).
- Statewide benchmark from the federal scorecard, so a program's rate can be read against
  California's own figures.
- Bilingual (English/Spanish) static site built with the California Design System: search
  with filters, program detail, and occupation detail.
- Three-way job outlook filter, surfacing the 538 programs training for occupations the
  state projects will shrink.
- Coverage reporting as a published artifact rather than a debug log.
- Accessibility audit over the built pages, failing the build on any axe violation, plus a
  contrast audit computing real WCAG ratios for every color pairing in both themes.
- Offline build path and a committed 60-program fixture, so CI does not depend on a
  government endpoint being reachable.
- Mechanical provenance check enforcing this project's clean-room constraint.
- Browse indexes for occupations (banded by projected outlook, shrinking first) and
  providers (alphabetical, with how many of each provider's programs report anything).
- Regional wages: 1,525 programs are matched to a published EDD area using EDD's own area
  labels, so a Fresno program can show the Fresno figure. 44% of comparable rows differ from
  the statewide wage by more than 10%.
- Side-by-side comparison of up to four programs, a city filter, and provider pages.
- A build-time data cache with stamp-based invalidation and deep-frozen records, so pages
  cannot corrupt each other's data.
- A SOC aggregation table recovering 61 of the 77 programs whose occupation code EDD does
  not publish. It is wired into the build: 135 program-occupation matches run through an
  aggregate, and all 135 have their entry-level education withheld, because the category BLS
  assigns to an aggregate is not a claim about any one occupation inside it.
- A CareerOneStop client for occupation descriptions, O*NET skill ratings and O*NET related
  occupations. Optional: the build runs unchanged without credentials.
- The funding block says what order to do things in. Every program page now carries "Ask
  before you enroll, not after": under 20 CFR 680.220 a centre has to interview or assess
  somebody before it can find them eligible, and under 680.340 the referral and the account
  come after that — so the call belongs before the enrolment, and someone who has already
  enrolled or paid is told to ask rather than told what will happen, which no regulation read
  for this says. It is a plain paragraph above the offices, not behind the link to the guide.
  The claim and its citations are a new step in `local_help`; `/paying-for-training/` renders
  it, with the regulations beside it, from the next dataset refresh onward.
- `/paying-for-training/` is in the accessibility gate, in both languages. Every one of the
  3,266 program pages links to it and nothing had ever audited it.
- The 32 program pages with no America's Job Center inside the published 25-mile radius name
  the nearest offices anyway, with distance, phone and hours, instead of offering a statewide
  search box. Lemoore's two nearest are 26.7 and 27.0 miles, Coalinga's 38.7 and 39.0, and
  South Lake Tahoe's one at 36.5. Nothing new is fetched: `coverage.json` already publishes
  all 183 centres with coordinates and each program carries its own.
- The comprehensive/affiliate label on an office card is explained in one clause, so a
  federal term of art on the page means something to the reader looking at it.
- A first-visit transfer budget in the build. `size-report.mjs` measured the export on disk,
  which is a hosting bill and not what any reader pays; it now also reports the brotli
  transfer of one page of each shape and fails the build over 420 KiB per route. Alongside
  it, `npm run transfer` drives a real Chromium at the built site and reports what a browser
  actually fetches, prefetches included — the only way to see traffic that no built file
  records.

### Fixed

- A dataset older than the code cannot be packaged or published. `clean_length` shipped on
  2026-08-07 and the dataset release tagged `dataset-2026-08-07` was cut four hours earlier,
  so the deploy on 2026-08-14 published a snapshot in which the twelve California programs
  whose providers filed them as competency-based carried no `competency_based` key at all —
  and twelve named providers' pages read "Length: Not reported" over a fact the federal record
  had stated. That is the third time this shape has landed (#28's row-id leak, #34's provider
  links), and each previous time it was answered with a check written for that one fix.
  `afterward.build.length_integrity_problems` already refuses exactly that record, and answers
  "3,266 problems" when pointed at that release; it runs inside a build, over payloads the
  build just produced, so it can only ever see a dataset that is new by construction.
  `scripts/dataset_shape_check.py` asks the same question of an artifact instead, standard
  library only so the deploy workflow can run it with no Python toolchain, and it now runs on
  both paths a dataset reaches a reader by: `make dataset-verify` before packaging and
  GUARD 1a before the export is built. The row-id check that used to be a Makefile shell
  one-liner moved into it and gained the tests it never had.
- A program that filed a cohort count is no longer told it reported nothing. 42 of
  California's 1,209 silent programs filed a count of the people they served, exited or
  completed; their pages printed that count — "People enrolled 16" — and then, directly
  underneath, "No outcomes reported for this program". Two of the 42 also filed how many
  people were working a year on. `/outcomes-coverage/` has always published the distinction
  (`silentWithACohort` against `silentWithNoRecord`) and the program page was printing the
  wrong half of it, which is a limitation of what this project counts arriving on the page as
  a fact about a named college. The panel now names what is actually absent — no completion
  rate, no employment rate, no earnings figure — where a record exists, and keeps "reported
  nothing" for the 1,167 records that do not.
- A route the app declares and no gate reads is unaudited and unmeasured, not passing. Both
  the accessibility audit and the first-visit transfer budget walked hand-written lists of
  pages, which are claims about a site that changes: adding `app/[lang]/something/page.tsx`
  left both gates green over a sample that had quietly stopped describing what is published,
  and the new page is the one most likely to be carrying a violation because nobody has looked
  at it yet. `web/scripts/routes.mjs` reads the app router's own file tree, which is where a
  route is actually declared and the only place it cannot be declared twice, and both gates
  now fail naming any route their list does not cover — the audit in every language, the
  budget once per template. Two templates were uncovered by the budget when this was written:
  the provider detail page and `/ctdl/`, both table-heavy. The budget also stopped treating a
  page it could not find as a line of output (`(not built)`, then on to the next one), and
  stopped weighing an asset missing from the export as zero bytes, which made the one broken
  build the lightest one it had ever measured.
- Neither accessibility gate can shrink its own sample and still report a pass. `npm run
  a11y` filtered its list of 22 named pages through `existsSync` before using it, so a route
  renamed, removed, or not emitted in one language simply left the sample and the run
  reported no violations over what was left, saying nothing about what it stopped reading.
  A page on the list that is not in the build now fails the run and is named;
  `npm run a11y -- --list` prints the sample without auditing it, and
  `web/scripts/a11y-audit.test.ts` covers both directions.

  `npm run a11y:browser` had the same shape and a live instance of it. It looked for a
  program page by following the first program link on `/en/programs/` — a path that has no
  index behind it, because programs are reached from the client-rendered search results and
  from provider and occupation pages. The request returned the 404 template, which links to
  no program, and `if (href) PAGES.push(...)` dropped the entry: **the densest template on
  the site had never been audited by this pass, on any run, and every run reported a clean
  result.** The program page is now scouted from a provider page, which does link programs,
  and a template this pass cannot reach fails the run instead of leaving the sample. With it
  restored the pass covers 10 pages rather than 9, and `color-contrast-enhanced` and
  `target-size` both pass on the program template in light and dark.

- Competency-based programs are no longer published as programs whose length nobody reported.
  The ETP Scorecard writes `-1` for a suppressed value in every column except the two
  program-length fields, where its data dictionary (v4.0) notes that `-1` means the program
  "was reported as a competency-based program": it finishes when the student can do the work,
  so it has no fixed clock length by design. `clean_measure` was applied to those two fields
  like any other, so 12 of California's 3,266 programs, from 6 providers, rendered as "length
  not reported" and were silently dropped by the length filter. A deliberate design decision
  was published as a provider's failure to answer, which is the error this project exists to
  avoid. `dol_etp.clean_length` now reads the two fields together and returns a `ProgramLength`
  carrying the state; `length.competency_based` ships in `programs.json` and `cb` in the search
  index, written on every record including the false ones, so a consumer can tell "not
  competency-based" from "built before the question existed".

  What the site does with them: the program page, the result card and the comparison table all
  say "Competency-based: no fixed length" through one `lengthText` helper, so the three cannot
  drift apart again. A length cap excludes them, because "six months or less" is a question
  about clock time that these programs decline to answer, and the number it removed is
  disclosed in its own sentence beside the existing one for unreported lengths. They can never
  be marked shortest in a comparison, and they cannot be placed in a length band, which keeps
  them out of the completion-rate mark that band gates. `build.check_length_integrity` refuses
  to emit a `-1` as a duration, or a record that cannot say which state it is in.

  The count that fell out of the fix: with those 12 read correctly, **no California program is
  left that filed no length at all**. Every one either states a length or states that it has
  none. The interface's "this filter also leaves out N programs whose provider reported no
  length" had been describing the competency-based population and nothing else.

- The promise to switch to an official DOL bulk file is resolved rather than left open. DOL
  now publishes one; it was fetched and diffed against the search API on 2026-08-07, and this
  project is staying on the API. The file carries no program identifier of any kind, so there
  is nothing to key the site's program pages by and no join back; its California program set is
  a different, older vintage rather than a superset (646 of the current programs are missing
  from it, 1,635 of its rows have no current counterpart, and it suppresses figures the API
  publishes far more often than the reverse); and it has no program-year column either, so it
  does not close the provenance gap that motivated looking. It does carry `de129`, the actual
  denominator of the published Q2 employment rate, which the API does not publish and which
  reconciles that rate exactly on all 1,801 California rows that have it. The full column diff
  and the recommendation are in `PROVENANCE.md`; nothing here ingests the file.

- A build can no longer publish coverage figures that the dataset it ships contradicts.
  `check_coverage_shape` asked whether `coverage.json` carried the keys the site reads; it
  never asked whether the numbers in them were true of the programs being written out beside
  it. Nothing did. `build_offline` copies the fixture's coverage document through wholesale
  and recomputes only four blocks, so `total_programs`, the three per-measure counts,
  `programs_with_any_outcome` and `outcome_coverage_pct` were carried over untouched —
  regenerating the fixture's programs without regenerating its coverage would have shipped one
  dataset and published another's arithmetic, silently. `check_coverage_counts` now recomputes
  all six from the emitted payloads and refuses the build on any disagreement, naming each one.
  The real build is checked by the same function: its counts come from the parsed
  `Program` objects while the site is served the payloads built from them, and nothing had
  ever asserted that those two describe the same set. Verified to fire — dropping five
  programs from the fixture without touching its coverage now stops the build instead of
  publishing 55 programs under a claim of 60. These are the figures in the footer of all
  ~9,000 pages and the ones quoted where nobody can check them against the data, so a wrong
  one is a false public claim about how much of California's training system reports
  anything, not a rendering bug.
- The suppression sentinel can no longer reach a page. `-1` is how the ETP scorecard says
  "withheld", `clean_measure` maps it to `None` where it enters, and that has always been well
  tested at the source boundary — but nothing checked the other end, the end that publishes.
  `check_outcome_integrity` now runs over every emitted record before anything is written and
  refuses a build carrying a `-1`, a completion or employment rate outside [0, 1], a negative
  headcount, or a negative median earning. It also checks each record's `reported` flag
  against its own three measures: that flag is what the site keys "no outcome data was
  reported" off and what `programs_with_any_outcome` counts, so a record whose flag disagrees
  with its data either hides three published measures behind a "not reported" notice or shows
  that notice's absence over three blanks. Loud rather than clamped: a value corrected here
  would be one this build chose rather than measured. The current 3,266-program dataset passes
  clean, and a genuine reported zero is explicitly not a problem — it is a fact about a real
  cohort, and telling it apart from a suppressed cell is the whole point.
- The site no longer spends ~400 KiB of every visitor's data on pages they did not ask for.
  The masthead links and the "back to search" link at the top of every page were prefetched
  as soon as they scrolled into view, and they point at the four heaviest routes on the site
  — including the search page, which carries the whole 3,266-program index inline. A visitor
  opening `/en/about/`, whose own document is 7.7 KiB compressed, was pulling 538 KiB; on the
  search page itself the wordmark fetched a second complete copy of the index the browser had
  just parsed. First visits now cost 145.8 KiB for `/en/about/` (was 538.3), 153.2 KiB for a
  program page (was 545.7) and 330.6 KiB for the search page (was 571.6), all brotli, cold
  cache, measured in Chromium. Result cards still prefetch: those are ~8 KiB and are what the
  reader came to open. Measurements and the options considered are in
  `docs/payload-audit-2026-08-05.md`.
- Phone numbers on office cards dial what they say. 20 of the 183 centres publish a field
  that is not one ten-digit number — two numbers, a number and an extension, a switchboard
  and an EDD line — and stripping non-digits from the whole field produced `tel:` links for
  twenty- and thirteen-digit numbers that dial nothing, on 778 of the 3,234 program pages
  that name an office, in both languages. Each real number inside the published string is now
  its own link, and what cannot be parsed stays as readable text.
- Three of the nine steps on `/es/paying-for-training/` shipped in English —
  `expect_an_interview`, `what_the_center_decides` and `other_funding_first` — on the page
  about who pays and who decides. The Python tripwire compared the module against the site's
  copy over the program-page subset only, while the guide rendered all nine, so neither half
  of the gap was visible to a test. The check now walks every step.
- Phone links say which office they call. Three offices on one page published three bare
  numbers, and a screen reader announced each as its digits alone (WCAG 2.2 AAA 2.4.9).
- Programs summarise across every occupation they feed, not just the first. The count of
  programs training for declining occupations was understated by more than half (on the
  current snapshot, 229 against 538), and hundreds of detail pages named the wrong job.
- Statistical aggregates are no longer published as occupations (764 → 670 real ones).
- Wages of exactly zero are treated as unpublished rather than rendered as "$0 a year".
- Partial costs render as "At least $X" instead of presenting a floor as the price.
- The site root is a real language chooser rather than an error shell with no `lang`.
- Provider URLs are validated: non-http(s) values are dropped rather than rendered into an
  `href`, closing a latent script-injection sink; bare domains are repaired to https.
- Programs are compared against the median program that reported the same measure, not
  against DOL's statewide aggregate, which is computed on a different basis and made 91% of
  programs read as above average.
- Earnings are labelled as covering a single quarter, so they are not read as a yearly
  salary beside the annual occupation wage.
- Program descriptions no longer ship the feed's own row id (`6091|Covers understanding…`)
  on 3,223 of 3,266 records. The site stripped it in one component, so only readers of the
  page were spared it and every reader of `programs.json` got it.
- CIP codes that lost their zero padding to a float upstream are restored on 239 of 3,266
  records — `1.0505` to `01.0505`, `51.071` to `51.0710`. Bare series (`46`) and four-digit
  families (`12.05`) are widths CIP genuinely publishes and are left exactly as filed.
- A build refuses to emit a `coverage.json` missing anything the site reads from it. One
  snapshot without `state_benchmark` had already removed every statewide comparison from
  2,057 outcome pages with no error, no warning and no visible difference.
- A provider link that answers HTTP 200 is no longer taken at its word. 20 of the 767 links
  that answered were not pages: 10 were the provider's own "page not found" screen served
  with a 200, and 10 were listings offering the domain for sale. Between them they sat under
  23 program pages that published a confident "Provider's website" link into a dead end. The
  soft 404s are now treated as the 404s they are — 11 of those pages gain a working link to
  the provider's home page instead — and a for-sale address is published unlinked, with a
  dated sentence saying what it served and suggesting the reader look the school up by name.
- The side-by-side comparison no longer marks a best completion rate across programs of
  different lengths. Completion is the row length decides: among the 1,947 programs that
  report both a rate and a length and whose figures describe that program alone, the median
  share who finished is 97% at four weeks or less, 91% at 5-12, 85% at 13-26, 80% at 27-52
  and 78% beyond a year. Graded against a smoothed expectation for its own length, the mark
  landed on the weaker of the two programs 10.22% of the time across length bands against
  2.63% within one, and the marked program was the shorter one 60.9% of the time. It is the
  confounding that took "Better than typical" off program pages, arriving two programs at a
  time. The rates are still shown, the mark returns whenever the compared programs are the
  same length, and a sentence says why it is absent when they are not. Employment (+3.26
  points of length error, non-directional) and earnings (+2.96, likewise) keep their marks,
  as do cost and length, which are properties of the course rather than the cohort.
- Documentation that had stopped describing the code. `web/lib/types.ts` told consumers to
  check `reported_for_soc` at the point of use; the field flags none of the 268 occupations
  (40.0%) that carry another group's attainment figures, so the advice was to rely on a check
  that cannot fire. It also told them to de-duplicate CareerOneStop tasks, which the parse now
  does. `PROVENANCE.md` credited O\*NET for the education-attainment distribution, which is a
  BLS measurement over ACS categories. Comments pointing at the pre-rename `src/camino/` and
  `camino.sources.*` now name `src/afterward/`, and the Makefile no longer says the old
  CloudFront distribution serves camino.chelseakr.com — as of 2026-08-05 that host answers 301
  to the matching afterward.chelseakr.com path.
- The last of the pre-rename names that were still shipping. The Python package credited
  "Camino contributors", the npm package was `camino-web` described as the front end for
  Camino, `make dataset-package` wrote `camino-dataset-<date>.tar.gz` onto every GitHub
  release, `deploy_check` identified itself to CloudFront as `camino-deploy-check`, and a
  comment in `web/lib/compare.ts` pointed at `src/camino/build.py`, a path that no longer
  exists. The release tarball rename is safe because `deploy.yml` matches `*.tar.gz` rather
  than the name.
  `STORAGE_KEY` in `web/lib/shortlist.ts` deliberately stays `camino.shortlist.v1`: it names
  data on the reader's own device, and renaming it would not migrate anything — it would make
  every shortlist saved before the rename unreadable, with no error and no way back. The
  historical references are also deliberate and stay: PROVENANCE.md records that the O\*NET
  registration is still under "Camino", and the Makefile, `infra/aws-static-site.yml` and the
  occupation-page comment explain what the old name was and what happened to it. The dated
  research notes in `docs/` are archival and still name `src/camino/` deliverables, as the
  banner in `docs/dead-provider-links-2026-08-04.md` says.

### Known limitations

- **The live site is serving a dataset the gates above now refuse, and only a refresh fixes
  it.** `dataset-2026-08-07` is what production has served since the 2026-08-14 deploy, and it
  predates two things in this repository: `clean_length` (so twelve programs read "Length: Not
  reported" instead of competency-based) and the provider-link review (so 109 program pages
  link an address that answers from another domain, twenty of them hosts the committed review
  recorded as somebody else's live site or as advertised for sale — an Indonesian gambling
  site, an Indonesian lottery site, a Baltimore charity, and five domain listings). Neither is
  fixable from the repository: `make data` reads the DOL endpoint, which refuses CI, so the
  dataset has to be rebuilt on a workstation, republished with `make dataset-publish`, and
  deployed. Until then the deploy workflow refuses that tag, which is the correct behaviour
  and not a substitute for the refresh. The committed `web/public/ctdl/*.json` statements were
  produced from a locally rebuilt 2026-08-07 dataset that does carry the length fix, so
  `snapshot_date` alone does not identify which bytes a statement describes.
- Provider pages are grouped by a slug truncated to 80 characters, so two providers whose
  names agree for that long would be published as one. The longest provider slug in the
  2026-08-07 snapshot is 67 characters and nothing collides today, but nothing checks it
  either; the three slugs that do collide are case and punctuation variants of one name,
  which is the merge the grouping intends.
- Program descriptions and program and provider names render in English on Spanish pages —
  the feed publishes no Spanish counterpart for any of them — and so do the occupation titles
  for the 70 of 670 occupations Mi Próximo Paso does not carry. The controlled vocabularies
  (education, experience, training type) are translated, and the other 600 occupations use
  the Department of Labor's own Spanish title and description. Nothing is machine-translated.
- Whether California's own ETPL lists programs the federal file omits is unresolved; the
  state publishes no bulk export.
- The national education-attainment distribution (`OccupationEducation.distribution`) stays
  in the dataset, parsed and typed, but nothing renders it as of #20
  (`docs/education-attainment-not-shipped-2026-08-05.md`): 268 of the 670 occupations carry a
  distribution byte-identical to another's, with no field that flags which.
