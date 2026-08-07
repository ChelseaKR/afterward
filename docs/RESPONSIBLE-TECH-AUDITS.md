# Responsible-Tech Audits: afterward

Instantiates the portfolio's RESPONSIBLE-TECH-FRAMEWORK for this repository. Written
2026-08-07. This is an honest record of what exists, what was decided, and what has not been
done; it makes no claim a gate does not enforce or a document does not show.

## Applicability

- **A Ethics:** applies (findings below).
- **B Bias:** applies (the site orders and filters information about real providers;
  findings below).
- **C Privacy:** applies, and is unusually short: the product collects nothing.
- **D Transparency:** applies (findings below).
- **E Accessibility:** applies (gates live in CI; the honest coverage record is
  `docs/wcag-2.2-aaa-conformance.md`).
- **F Security:** applies (declarations below).
- **AI evaluation:** N/A. There is no LLM, no model, no prompt, no retrieval, and no
  generation surface anywhere in the product. The pipeline is deterministic parsing and
  joining of public government data; the site is a static export of its output. Development
  was AI-assisted, which is disclosed in the README and is a fact about tooling, not about
  the product.
- **EU AI Act:** not an AI system. Nothing here performs machine inference. No
  classification exercise is needed beyond this sentence, and writing one anyway would
  overstate what the software is.
- **I18N:** applies and is implemented (EN/ES ship together; `docs/I18N.md`,
  `docs/adr/0002-bilingual-strings-in-typed-modules.md`).

## A. Ethics

**What the product does to the world:** it lets a Californian see, for free and without an
account, the outcome data their state and the federal government already publish about
training programs that cost months and thousands of dollars. The asymmetry it corrects is
real: the incumbent portal puts the training list behind an account, and the outcome data
lives in a federal file no Californian is expected to find.

**Commitments enforced in code rather than intended:**

- A withheld or suppressed outcome is `null`, never `0`. WIOA suppresses small-cohort cells
  to protect the people in them; rendering a suppression as a zero would defame a real
  provider. This is the most-tested behavior in the codebase.
- "Not reported" and "reported as zero" stay visually distinct everywhere they appear.
- The site looks official because it uses the state's open-source design system, so a
  non-affiliation notice sits in the banner landmark of every page, in both languages, and
  DISCLAIMER.md forbids demoting it to the footer.
- Nothing here is advice, and DISCLAIMER.md says so in plain language.

**Monetization:** a Ko-fi link. No ads, no affiliate links, no lead generation, no data
sale. A training-program search site that sold leads to providers would be a conflict of
interest; this one has no commercial relationship with anything it lists.

**Open item:** none tracked. The consequence scan above is current as of 2026-08-07.

## B. Bias

**Where ranking or ordering judgment exists:**

- Search ordering and filters operate on government-reported fields (cost, length, outcome
  measures, occupation outlook), not on any scoring model of this project's invention.
- The outlook browse deliberately surfaces shrinking occupations first. That is a values
  choice, on the record: the 538 programs training for occupations the state projects will
  shrink are exactly the ones a prospective student most needs to see coming.
- More than a third of programs report no outcomes at all. The bias risk is a reader
  treating "no data" as "bad program"; the interface keeps those apart (see A above), and
  coverage.json publishes the gap as a first-class artifact instead of hiding it.

**What the product does not do:** it displays no demographic data, profiles no user, and
ranks no people. The federal outcome measures are aggregate; source suppression is
preserved, never reversed.

**Residual risk, stated:** the underlying outcomes are self-reported by providers to the
state and by the state to the federal government. This project reproduces them and says so
(DISCLAIMER.md); it cannot verify them.

## C. Privacy (DPIA-style)

**Data inventory of the running product:** empty. No accounts, no cookies set by the
application, no analytics, no server logs of this project's own (the site is static files on
S3 behind CloudFront), and no personally identifiable information in the dataset. Search
runs entirely client-side against a downloaded index, and the shortlist stores nothing but
program ids in the visitor's own `localStorage`; neither sends anything anywhere.

**Data subjects in the dataset:** none identifiable. The dataset is aggregate program-level
government data; small cohorts are suppressed at source, that suppression is preserved, and
no attempt is made to re-identify anyone (SECURITY.md commits to this).

**Consequence:** there is no lawful-basis analysis, retention schedule, or deletion
procedure to write, because there is no personal data to hold. That absence is the design.

## D. Transparency

- Every source, access date, and licensing term: `PROVENANCE.md`, with a mechanical
  `make provenance-check` enforcing the project's clean-room constraint on every build.
- What the data cannot say: `DISCLAIMER.md`, in plain language.
- What is missing from the data: `coverage.json`, shipped beside the data it describes.
- Why things are the way they are: `docs/design-log.md` (dated, append-only, figures not
  retro-edited) and `docs/adr/`.
- What changed: `CHANGELOG.md`.

## E. Accessibility

Target is WCAG 2.2 AAA, enforced by four automated gates (axe with every rule enabled
including the sixteen off-by-default ones, a rendered-DOM axe pass, a browser pass for
enhanced contrast and target size, and an analytic token-contrast audit). Two of the
judgment-only AAA criteria and every human assistive-technology control are recorded as
open, not passed, in `docs/wcag-2.2-aaa-conformance.md`, which is the authoritative honest
record: what automation proves, what it found, and what no tool can check. No human
screen-reader walkthrough has been performed, and no phrase in this repo claims one has.

## F. Security

- **Attack surface:** static pre-rendered HTML and JSON. No server, no database, no
  authentication, no server-side input handling. The realistic risks are supply-chain (Python and npm
  trees), untrusted upstream feed content rendered on pages, and the build pipeline itself;
  SECURITY.md scopes reporting accordingly and enables GitHub private vulnerability
  reporting.
- **Supply chain:** uv.lock and package-lock.json committed; pip-audit blocks `make verify`;
  bandit runs on every build; all GitHub Actions pinned to full commit SHAs; Dependabot
  maintains all three ecosystems; gitleaks runs on push, PR, and weekly schedule (history
  verified clean, 125 commits, before the workflow was added).
- **Deploy:** OIDC only, no static AWS keys anywhere; the deploy role trusts exactly one
  repository environment and can touch exactly one bucket and one distribution; deploys are
  dispatch-only and refuse to run without a green CI conclusion on the exact commit.
- **Data integrity:** the deploy workflow refuses fixture-shaped datasets, verifies a
  checksum, requires manifest/on-disk agreement, and smoke-tests the published snapshot
  end-to-end.
