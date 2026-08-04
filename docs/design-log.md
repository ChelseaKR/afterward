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
- Program length is sparsely populated (`weeks` is often null); worth quantifying before
  designing a duration filter around it.
