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
- Accessibility audit over the built pages, failing the build on any axe violation.
- Offline build path and a committed 60-program fixture, so CI does not depend on a
  government endpoint being reachable.
- Mechanical provenance check enforcing this project's clean-room constraint.

### Fixed

- Programs summarise across every occupation they feed, not just the first. The count of
  programs training for declining occupations was understated by more than half (219 against
  518), and hundreds of detail pages named the wrong job.
- Statistical aggregates are no longer published as occupations (764 → 670 real ones).
- Wages of exactly zero are treated as unpublished rather than rendered as "$0 a year".
- Partial costs render as "At least $X" instead of presenting a floor as the price.
- The site root is a real language chooser rather than an error shell with no `lang`.

### Known limitations

- Occupation titles and program descriptions render in English on Spanish pages. The
  controlled vocabularies (education, experience, training type) are translated; the
  open-ended text is not.
- Colour contrast is unverified in a real browser. The audit runs in jsdom, which has no
  layout engine.
- Whether California's own ETPL lists programs the federal file omits is unresolved; the
  state publishes no bulk export.
- `median_earnings` is a quarterly WIOA measure displayed near annual occupation wages
  without a period label, which invites a reader to compare two different things.
- The statewide benchmark is not a like-for-like comparison: 91% of programs read as "above
  the California average" on employment, which suggests the statewide figure is computed
  differently from the per-program one.
- `program_url` is rendered without scheme validation; eight values are not absolute URLs.
