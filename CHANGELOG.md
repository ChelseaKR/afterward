# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

### Fixed

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

### Known limitations

- The national education-attainment distribution is published on 3,250 of the 3,266 program
  pages **against a written decision not to publish it**
  (`docs/education-attainment-not-shipped-2026-08-05.md`). 1,695 of the 5,514
  program-occupation rows sit on a distribution measured for a broader group than the
  occupation named, and nothing on the page says so. Withdrawing the block is a behaviour
  change and has not been made.
- Program descriptions render in English on Spanish pages, and so do the occupation titles
  for the 70 of 670 occupations Mi Próximo Paso does not carry. The controlled vocabularies
  (education, experience, training type) are translated, and the other 600 occupations use
  the Department of Labor's own Spanish title and description. Nothing is machine-translated.
  The About page's "known limitations" copy still says all occupation titles are English and
  contradicts its own sources section forty lines above; correcting user-facing Spanish is
  not a documentation change and is left to the i18n workstream.
- Whether California's own ETPL lists programs the federal file omits is unresolved; the
  state publishes no bulk export.
- 1,430 programs filed no usable website link. Most never filed one; eight filed something
  that was not a URL, and those are now dropped rather than rendered. 1,612 render no
  clickable link once the dead ones are excluded, and the About page still reports 1,430
  under the sentence "no working website link".
