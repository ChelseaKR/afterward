# Design log

Dated record of what was decided, from which inputs, and why. Kept so the project's design
lineage is auditable rather than asserted. See [PROVENANCE.md](../PROVENANCE.md) for the
clean-room constraint this log supports.

---

## 2026-08-04 — Phase 0: scaffold and data audit

### Inputs consulted

- CalJOBS (caljobs.ca.gov) and the EDD Eligible Training Provider List page — to characterise
  the incumbent experience.
- U.S. DOL TrainingProviderResults.gov — to establish which WIOA outcome measures are public.
- data.ca.gov CKAN API, EDD organisation — to inventory California's published labor market data.
- Governor's office release on the Career Passport pilot (2026-06-17) and the C2C brief — to
  fix this project's scope as *navigation*, distinct from a credential wallet.

No New Jersey workforce product, repository, or documentation was consulted. See PROVENANCE.md.

### What the audit found

The three risks named in the pre-work plan resolved better than expected.

**1. Programs already carry SOC codes — no crosswalk needed.** The plan assumed a
CIP → SOC crosswalk would be required to connect training programs to occupations, and
budgeted for the join being lossy. The federal ETP records carry up to three SOC codes per
program directly (`field_program_soc_occ_1..3`), so the crosswalk is unnecessary for the
primary join. **97.6% of California programs (3,189 of 3,266) match an EDD occupation
projection.** The NCES crosswalk is dropped from the plan; it may return later only as a
fallback for the 77 unmatched programs.

**2. Outcome coverage is ~63%, better than the ~44% first estimate.** Counting any headline
measure rather than earnings alone: 2,057 of 3,266 programs report at least one outcome.
Broken down: completion rate 2,047; Q2 employment rate 1,766; median earnings 1,432. Cost
data is present for all 3,266.

**3. No scraping required.** The public site trainingproviderresults.gov is backed by an
unauthenticated read-only Elasticsearch endpoint (`cxsearch.dol.gov/etp`) serving the same
public data. The pipeline reads it with `search_after` pagination and a deliberate inter-page
pause. This removes the ETPL-extraction fragility the plan flagged as its top risk. The
CalJOBS guest-path extraction spike was not needed and is dropped for now; California's own
ETPL may still list programs absent from the federal file, which is a question for Phase 1.

### Decisions

**D1 — Suppressed values are `null`, never `0`.** The feed uses `-1` (and empty string) for
withheld or unreported measures; WIOA suppresses small-cohort cells to protect participant
privacy. Conflating that with a reported zero would misstate a real provider's performance.
The sentinel is mapped at parse time, the distinction is carried through to the emitted JSON,
and it is the single most-tested behaviour in the codebase.

**D2 — Coverage is a published artifact, not a debug log.** `coverage.json` ships with the
dataset and the gaps are stated in the README. A tool that concealed its own blind spots
would be worse than the portal it critiques.

**D3 — Programs reference occupations, not embed them.** The first build embedded each
matched occupation, including its full regional wage array, in every program record: 89 MB.
Emitting a six-field summary and keeping the full record once in `occupations.json` brought
it to 6.5 MB. This matters because the target is static files on a phone.

**D4 — Statewide projection is the default, regional retained.** A program's graduates do
not necessarily work in the county where they trained, so the statewide row is the headline
and regional rows stay available under `regions` for later geographic filtering.

**D5 — Resolve data URLs through CKAN by dataset slug.** EDD re-publishes these files under
fresh resource ids each projection cycle; a pinned URL would rot silently. The pipeline looks
up the current resource at fetch time.

**D6 — `make provenance-check` runs inside `make verify`.** The clean-room constraint is
enforced mechanically rather than by memory. An early run caught the guard scanning `.venv`
and false-positiving on the SPDX licence name "Standard ML of New Jersey", which is why the
scan now excludes vendored directories.

### Open questions carried into Phase 1

- Does California's own ETPL list programs the federal file omits? If so, by how many?
- `occupations.json` is 9.1 MB; it likely needs splitting per-occupation for the site.
- 584 distinct providers across 3,266 programs — provider-name normalisation is unverified
  and may be inflating that count.
- Program length turned out to be near-complete (`weeks` present for 3,254 of 3,266), so a
  duration filter is safe to design around. Resolved on the day it was raised.

---

## 2026-08-04 (later) — Front end, and what building it exposed

### D7 — The site says it is not a government site, in the banner

Using the California Design System means the pages look official at a glance. The
non-affiliation notice therefore sits in permanent chrome on every page, in both languages,
not in footer small print. The first accessibility audit proved why placement matters: the
notice was originally outside every landmark, so a screen reader user navigating by landmark
would have skipped the one sentence telling them this is not a state website. It now lives
inside the banner.

### D8 — Absence gets a designed state

The design system fixes the palette and type, so the design work went into the information
design instead. A withheld measure renders as an explicit, italicised "Not reported" with a
tooltip explaining that it may have been suppressed to protect a small cohort's privacy —
never as 0, `$0`, `0%`, or a dash. A program that reported nothing gets a full explanatory
panel rather than a blank card, because that absence is one of the more useful things a
prospective student can learn.

### D9 — Statewide benchmark, because a bare rate is unreadable

Nobody knows whether "45% employed" is good. The DOL `etp_scorecard_states` index publishes
California's own aggregate, so every program measure is now shown against it.

**California's statewide figures: 71% completion, 27% employed at two quarters, $16,979
median earnings, across 664,260 exits.** The 27% is strikingly low and is itself an argument
for the product. The UI notes that beating a low average is a floor, not a guarantee.

A comparison is only drawn when both sides exist. Calling an unreported program
"below average" would be an accusation rather than a fact.

### D10 — Translate the data's controlled vocabularies, not just the chrome

Translating the interface while leaving the data in English produces pages that read
"Normalmente requiere: Associate's degree". Education (9 values), work experience (4), and
job training (7) are closed lists, so they are translated, with unknown values falling
through to the source text so gaps stay visible.

**Known limitation:** occupation titles (764) and program descriptions (thousands) are
open-ended and remain in English. A Spanish page is therefore not yet fully Spanish. Machine
translation of occupation titles is the obvious next step and needs review by a Spanish
speaker before it ships — an incorrect job title is worse than an English one.

### Still open

- Does California's own ETPL list programs the federal file omits? Unresolved. The federal
  file has 3,266 California programs; CalJOBS is the authoritative state list and was not
  extracted, because the federal endpoint made scraping unnecessary for everything else.
- Colour contrast is unverified. The audit runs in jsdom, which has no layout engine, so
  contrast is reported as needing review rather than counted as passing. Requires a browser
  before any public launch.

### One finding worth surfacing in the product

**219 California programs train people for occupations the state itself projects will
shrink.** Both halves of that sentence are public today and neither is discoverable next to
the other. It is the clearest single argument for why this join should exist, and it should
be a first-class view rather than a statistic buried in a report.
