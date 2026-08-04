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
- Three-way job outlook filter, surfacing the 219 programs training for occupations the
  state projects will shrink.
- Coverage reporting as a published artifact rather than a debug log.
- Accessibility audit over the built pages, failing the build on any axe violation.
- Offline build path and a committed 60-program fixture, so CI does not depend on a
  government endpoint being reachable.
- Mechanical provenance check enforcing this project's clean-room constraint.

### Known limitations

- Occupation titles and program descriptions render in English on Spanish pages. The
  controlled vocabularies (education, experience, training type) are translated; the
  open-ended text is not.
- Colour contrast is unverified in a real browser. The audit runs in jsdom, which has no
  layout engine.
- Whether California's own ETPL lists programs the federal file omits is unresolved; the
  state publishes no bulk export.
