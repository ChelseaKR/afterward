# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Data pipeline joining California's WIOA-reported training programs to the state's
  long-term occupational employment projections. 3,266 programs from 584 providers, 97.6%
  matched to an occupation.
- Statewide benchmark from the federal scorecard, so a program's rate can be read against
  California's own figures.
- Bilingual (English/Spanish) static site built with the California Design System: search
  with filters, program detail, and occupation detail.
- Three-way job outlook filter, surfacing the 518 programs training for occupations the
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
  not publish (not yet wired into the pipeline).
- A CareerOneStop client for occupation descriptions, O*NET skill ratings and O*NET related
  occupations. Optional: the build runs unchanged without credentials.

### Fixed

- Programs summarise across every occupation they feed, not just the first. The count of
  programs training for declining occupations was understated by more than half (219 against
  518), and hundreds of detail pages named the wrong job.
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

### Known limitations

- Occupation titles and program descriptions render in English on Spanish pages. The
  controlled vocabularies (education, experience, training type) are translated; the
  open-ended text is not.
- Whether California's own ETPL lists programs the federal file omits is unresolved; the
  state publishes no bulk export.
- 1,430 programs publish no usable website link. Most never filed one; eight filed something
  that was not a URL, and those are now dropped rather than rendered.
