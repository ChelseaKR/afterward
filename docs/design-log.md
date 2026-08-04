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

### D11 — The shrinking-jobs finding is now a control, not a footnote

The earlier entry said the 219 programs training for declining occupations should be a
first-class view. It is: the search page opens with two sentences of context — how many
programs report anything, and how many train for work California expects less of — with a
button that filters to the second. The outlook filter is three-way (any / growing /
shrinking) rather than a hide toggle, because "show me only these" is the interesting
question and a hide-checkbox cannot ask it.

Unknown growth is excluded from *both* the growing and shrinking filters. Treating unknown
as either would put a claim on screen the data cannot support.

### D12 — CI builds from a committed fixture, because DOL refuses CI

The web CI job failed on its first real run: `cxsearch.dol.gov` returns **403 Forbidden** to
GitHub Actions runners. The same query succeeds from a laptop, so this is datacenter-IP or
client filtering, not a malformed request.

The deeper mistake was depending on a third party being reachable at all. CI now builds from
a 60-program fixture committed to the repository, through a `build-offline` path that runs
the same emit code as a real build.

The fixture is **chosen, not sampled**. It contains a program with full outcomes, one that
reported nothing, one with a suppressed measure beside a reported one, a shrinking occupation
and a growing one, a small cohort, and a program with no matching occupation. A green run
against a random 60 rows would prove very little, so tests assert that coverage directly —
if the fixture stops exercising a case, the tests say so rather than CI passing while
testing less.

Two guards worth naming: one test monkeypatches `httpx` to raise on any request, so the
offline path cannot silently regain a network dependency; another asserts no `-1` survived
into the fixture, since that would mean suppression leaked through as real data. Fixture
builds are marked `is_fixture: true` so nobody mistakes 60 rows for California's landscape.

The scheduled freshness job still hits the live sources and is still allowed to fail. That
is now its only purpose: telling us when upstream changed, without blocking anything.

---

## 2026-08-04 (later still) — What an adversarial review found

Two independent reviews were run against the repository and the data. They converged on the
same defects, and the most important one made the project's headline claim wrong.

**The shrinking-jobs number was 219. It should have been 518.** A program can feed up to
three occupations, and 1,588 of California's 3,266 feed more than one — but every surface
read only `occupations[0]`. The shrinking occupation is frequently not the one listed first.
The same bug named the wrong job on hundreds of detail pages: an automotive program showed an
electrical installer's wage because that SOC happened to sort first. Programs now summarise
across every occupation they feed, taking the weakest outlook, and detail pages list all of
them.

**About 94 statistical aggregates were published as though they were jobs.**
`is_detailed_occupation` guessed from the code shape and rejected only major groups
(`XX-0000`); minor groups end `-1000`, `-2000` and slipped through. EDD publishes its own
hierarchy level, and the parser had been reading it into `soc_level` and never using it — the
correct filter was sitting three lines above the broken one. 764 "occupations" became 670 real
ones. This had also poisoned the related-work lists, where aggregates won on openings by
construction; one occupation page offered, as related work, the category containing itself.

**Thirteen occupations rendered "$0 a year".** EDD writes 0 where it publishes no wage,
typically for irregular or hourly-only work. Chemical Engineers do not earn nothing. This was
the suppressed-versus-zero failure arriving by a third route, through data this project had
treated as clean.

**Total cost summed a suppressed component as zero** — the invariant this codebase states in
its own docstrings, violated inside a sum helper, and locked in by a test asserting the wrong
behaviour. Costs now carry a completeness flag and render as "At least $X".

**The site root was an error shell.** `redirect()` under `output: "export"` emits no redirect
at all: an empty body with no `lang` attribute. Visitors without JavaScript got a blank page
at the most-linked URL. The accessibility audit had not been checking the root, which is
precisely why CI called it clean. It checks it now.

The lesson worth keeping: every one of these passed lint, types, 75 tests, and a clean axe
run. Gates catch what they were built to catch. Two of these were found by reading the data
rather than the code, and the null-versus-zero rule turned out to have been broken in three
places nobody had thought to look.

### Still open

- Does California's own ETPL list programs the federal file omits? **Still unresolved, and
  now known to be expensive.** Checked 2026-08-04: `data.gov` publishes no ETPL dataset, and
  EDD's ETPL page offers no bulk download — the state list is reachable only through the
  CalJOBS guest search UI, one query at a time. Answering the question therefore means
  session-based extraction from CalJOBS, which is a separate piece of work with its own
  terms-of-use question. The federal file's 3,266 California programs stand as the spine
  until someone decides that extraction is worth it.
- Colour contrast is unverified. The audit runs in jsdom, which has no layout engine, so
  contrast is reported as needing review rather than counted as passing. Requires a browser
  before any public launch.

### One finding worth surfacing in the product

**219 California programs train people for occupations the state itself projects will
shrink.** Both halves of that sentence are public today and neither is discoverable next to
the other. It is the clearest single argument for why this join should exist, and it should
be a first-class view rather than a statistic buried in a report.
