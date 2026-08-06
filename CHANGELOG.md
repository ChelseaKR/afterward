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

### Fixed

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

### Known limitations

- Occupation titles and program descriptions render in English on Spanish pages. The
  controlled vocabularies (education, experience, training type) are translated; the
  open-ended text is not.
- Whether California's own ETPL lists programs the federal file omits is unresolved; the
  state publishes no bulk export.
- 1,430 programs publish no usable website link. Most never filed one; eight filed something
  that was not a URL, and those are now dropped rather than rendered.
