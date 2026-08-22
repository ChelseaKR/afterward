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
- **AI evaluation:** applies since 2026-08-21. Until then there was no LLM, no model, no
  prompt, no retrieval, and no generation surface anywhere in the product, and that remains
  true of the static site and every figure on it. By the owner's direction
  (`docs/adr/0003-runtime-ai-at-the-edges.md`) an optional, opt-in runtime service,
  `afterward.ask`, adds a model in bounded roles: it structures a person's question into a
  query the service runs deterministically over the published dataset, and it narrates the
  records it is handed, with every claim verified against the published JSON before display.
  Findings are in section G below. Development was also AI-assisted, which is disclosed in
  the README and is a fact about tooling, not about the product.
- **EU AI Act:** the static site is not an AI system; nothing in it performs machine
  inference. `afterward.ask` is one: a general-purpose model used to structure and narrate
  queries over public aggregate data, with no decision about any person, no profiling, no
  eligibility finding, and every output labelled AI-generated. It does not fall in a
  high-risk category in Annex III (it is not used for access to education or employment
  decisions; it summarises public statistics a person is already free to read). The
  transparency obligation — a person must know they are interacting with an AI system — is
  met by the opt-in control and the label on every output.
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

**Data inventory of the running static site:** empty. No accounts, no cookies set by the
application, no analytics, no server logs of this project's own (the site is static files on
S3 behind CloudFront), and no personally identifiable information in the dataset. Search
runs entirely client-side against a downloaded index, and the shortlist stores nothing but
program ids in the visitor's own `localStorage`; neither sends anything anywhere.

**Data inventory of `afterward.ask`, when deployed (ADR 0003):** one item. The free text a
person types after opting in — which may describe their age, job, city and situation — is
sent to the service and from there to the model provider for the duration of the request.
The service stores no request body, writes no free text to disk or to logs, keeps only
counters (requests per client key, tokens per day) for the cost controls, and returns nothing
it did not compute for that request. The provider's own retention applies while the request
is processed; that is a subprocessor relationship a deployment must name before the service
is exposed publicly, and it has not been named yet because the service is not deployed. The
panel says, beside the input, that what is typed leaves the site and that nothing should be
typed that identifies a person.

**Data subjects in the dataset:** none identifiable. The dataset is aggregate program-level
government data; small cohorts are suppressed at source, that suppression is preserved, and
no attempt is made to re-identify anyone (SECURITY.md commits to this).

**Consequence:** for the static site there is no lawful-basis analysis, retention schedule,
or deletion procedure to write, because there is no personal data to hold. That absence is
the design. For `afterward.ask` the retention schedule is "none, by construction" on this
project's side and "the provider's" on the other, and the deletion procedure is therefore the
provider's; both are to be recorded in the deployment decision.

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

- **Attack surface:** static pre-rendered HTML and JSON. No server behind the site, no
  database, no authentication, no server-side input handling. The realistic risks are
  supply-chain (Python and npm trees), untrusted upstream feed content rendered on pages, and
  the build pipeline itself; SECURITY.md scopes reporting accordingly and enables GitHub
  private vulnerability reporting. `afterward.ask` (ADR 0003) adds a server-side surface that
  accepts free text: prompt injection against the model is assumed and is why the model's
  output is never evidence — every claim is verified against the published JSON by code, and
  the model cannot reach anything but the dataset it is handed; rate limits and a daily cap
  bound cost; CORS is locked to the site origin in the prepared deployment.
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

## G. AI evaluation (`afterward.ask`, ADR 0003)

**What the model is allowed to be evidence for:** nothing. It structures a question into a
query and narrates records; the dataset is the only evidence, and a verifier sits between the
model's output and the reader. A claim is shown only if every record id it cites was among
the records retrieved, every number it declares matches the published field on the published
basis, every numeric token in its text traces to a declared number, and no suppressed measure
is mentioned without being called not reported. Withheld claims are counted and the count is
shown.

**What is evaluated, and how:** four committed suites under `evals/`, run by
`afterward ask-eval`. (a) Query structuring, bilingual, including underspecified inputs scored
on refusing to guess. (b) Suppression faithfulness: cases whose ground truth is a suppressed
cell, scored on whether the narration rendered absence as a value. This is the eval that
matters most, because it is this portfolio's dominant defect. (c) Citation grounding: the
fraction of claims whose citations verify. (d) Comparability: no benchmark the site does not
use, and no unlabelled quarter-beside-annual figure. Results carry provider, model, prompt
version, commit and date; a test rejects a results file without them, and a suite that has
not been run live is recorded as `not_run` rather than estimated.

**Residual risk, stated:** the verifier checks numbers and citations, not tone. A narration
can be faithful to every figure and still lean; the label on every output says it is
AI-generated and not a recommendation, and the eval suites are the review that exists until
a human review of prompts, cases and Spanish output is recorded. Spanish produced by the
model is labelled unreviewed; issue #32 stays open.
