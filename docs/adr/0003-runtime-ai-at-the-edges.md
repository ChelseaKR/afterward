# 0003. Runtime AI at the edges: the published dataset is the only evidence, and a verifier sits before display

## Status

Accepted (2026-08-21). Owner-directed change of direction. Amends the "no AI in the product"
declarations in README.md, `docs/ROADMAP.md`, `docs/RESPONSIBLE-TECH-AUDITS.md` and
`SECURITY.md`, which are rewritten in the same change series. Does not amend ADR 0002: the
static site's bilingual strings stay in typed modules, and nothing in this decision moves a
shipped string into a model.

## Context

Until this decision Afterward contained no model at all. The pipeline is deterministic
parsing and joining of public government data, the site is a static export of its output, and
every public claim said so. `docs/ROADMAP.md` also said when that declaration would stop
being true: "Re-enter scope if any model-backed feature (say, description summarization or a
chat guide) is ever added."

The owner has directed that the product add real AI features at runtime — a grounded
conversational layer that changes what a person can actually do with this data. The case for
it is the case for the site: a Californian deciding whether to spend months and thousands of
dollars on a training program has 3,266 programs, 670 occupations, 28 regions, nine outcome
measures and a ten-year projection to read, and the question they actually have is "I work in
a warehouse in Fresno, I'm 40, what pays more and isn't going away?" A search form cannot take
that question. A language model can — and an ungrounded one would answer it by inventing a
wage, a region, or a completion rate, which is this portfolio's dominant defect: **absence
rendered as a value.** This repository has already met that defect in its own deterministic
code (the competency-based `-1`, the employment numerator that is not the rate's numerator,
the statewide benchmark that is not on the same basis as the programs). A model is a new and
much more fluent way to commit it.

So the decision is not whether the model may speak. It is what the model is allowed to be
evidence *for*, and what stands between it and the reader.

## Decision

Add a separate, optional Python runtime service, `afterward.ask`, that the static site can
call when a person explicitly opts in, and that the site must work without. The service
exposes four capabilities, each bounded the same way:

1. **Conversational exploration, grounded.** A person describes their situation in English
   or Spanish. The model turns that into a *structured query* against the published dataset:
   occupation search terms, a region, a projection direction, earnings and cost limits, the
   outcome measures they care about. The model structures; it does not invent. Occupation
   terms are resolved lexically by the service against the dataset's own titles and
   alternate titles, regions against the dataset's own area names, and anything that does
   not resolve is reported as unresolved — never guessed into a SOC code. The query is run
   deterministically over `programs.json`, `occupations.json` and `coverage.json`, and the
   model is then asked to *narrate* the records it is handed.

2. **Every substantive claim cites a record and is verified before display.** The narration
   is not prose. It is a list of claims, each carrying the record ids it rests on and the
   published numbers it uses. A verifier then checks, programmatically and without a model:
   that every cited id was among the records retrieved; that every declared number matches
   the published field it names, on the published basis; that every numeric token in the
   claim's text traces to a declared number (or to an enumeration or a year); and that no
   claim mentions a measure the record reports as suppressed without saying that it is not
   reported. A claim that fails any check is withheld, and the count of withheld claims is
   shown beside what survived. The reader sees what the data supports and a number for what
   the model said that it did not.

3. **Suppression-faithful by construction, and by eval.** The dataset writes `null` for a
   suppressed or unreported WIOA cell. The evidence the model is handed says "not reported"
   in those positions rather than omitting them, the system prompt says what that means, and
   the verifier refuses a claim that renders one as a zero, a "nobody", or an absence of
   outcome. A committed evaluation suite — cases whose ground truth is suppressed — scores
   exactly this, and it is the eval that matters most.

4. **Comparability-faithful.** The only comparison the model may narrate is the one the site
   already makes: a program's measure against the median of California programs reporting
   the same measure (`coverage.json` → `peer_medians`), with the count the median rests on.
   DOL's statewide aggregate (`state_benchmark`) is not offered to the model as a comparison
   basis at all, and the verifier rejects its figures if they appear. A WIOA median-earnings
   figure is a single quarter's earnings; an EDD occupation wage is annual; the verifier
   requires a claim that uses either to carry its period, and a claim that uses both to
   carry both.

5. **Spanish at runtime, labelled.** Occupation titles and descriptions reach the dataset
   in English (CareerOneStop serves English whatever language is asked for), and O\*NET's Mi
   Próximo Paso covers 600 of the 670. For the 70 it does not, and for provider-filed program
   descriptions, the service can translate on request. The translation is labelled
   AI-translated and unreviewed everywhere it appears; a translation that changes, drops or
   adds any number is withheld by the verifier; and the static catalogue is untouched. Issue
   #32 — native Spanish review of the catalogue — stays open. AI translation is not native
   review and this decision does not claim it is.

6. **Transition pathways.** "From my current job, what related occupations are growing, and
   which California programs lead there?" is answered from the dataset's own SOC codes and
   the related-occupation lists already published on each occupation record
   (`related`, `related_source`). No relation is fabricated: if the dataset carries none, the
   answer says so.

7. **Honest refusals.** When the data cannot answer — a region the projections do not cover,
   an occupation not among the 670, a program with no reported outcomes — the service says so
   and points at what is known. The model never fills the gap, because the gap is never in
   the model's hands: the deterministic layer decides what was found, and the model narrates
   only that.

Consequential choices:

- **Provider and model.** The public `anthropic` SDK; `claude-sonnet-5` is the configurable
  default (`AFTERWARD_AI_MODEL`). Amazon Bedrock is supported through the same SDK
  (`AFTERWARD_AI_PROVIDER=bedrock`, `AFTERWARD_AI_BEDROCK_MODEL`). Credentials come only from
  the environment; no key is ever written to the repository or to any file the service
  creates. Prompt caching is on for the system prompts, which are versioned
  (`PROMPT_VERSION`).
- **Cost is bounded from the first commit.** A per-client rate limit and a hard daily cap
  live in the service; a limited request returns 429 and the deterministic page is
  untouched. The prepared deployment adds reserved concurrency and a budget alarm on top.
- **No personal data is stored.** The service keeps no request body, writes no free text to
  disk or logs, and returns nothing it did not compute for that request. The provider's own
  retention applies while a request is processed, which a deployment must document as a
  subprocessor relationship before the service is exposed publicly.
- **The static site stays static.** With no service configured, every page behaves exactly
  as before and makes zero off-origin requests. With one configured, the site still makes
  none until a person presses the opt-in control; a test proves it.
- **Evaluation is committed, model-independent, and honest about what ran.** Four suites —
  query structuring (bilingual, including underspecified cases scored on refusing to guess),
  suppression faithfulness, citation grounding, and comparability — live in `evals/` with
  their harness. A results file carries provider, model, prompt version, commit and date, and
  a test rejects one that does not. Numbers are committed only from a recorded live run;
  otherwise the status is `not_run`.
- **The clean-room constraint is unchanged and still enforced.** `make provenance-check`
  runs on every PR in this series. The service is designed from California user needs and the
  data already in this repository; it copies no source from any other repository.

## Consequences

- Several public claims become false and are rewritten in the same series: "no model runs
  at build time or runtime" (README, ROADMAP, RESPONSIBLE-TECH-AUDITS), "no user-submitted
  input" and "no server" (SECURITY, RESPONSIBLE-TECH-AUDITS section F), "nothing on this
  site is machine-translated" (two strings in `web/lib/i18n.ts`). Each now reads: none in the
  static site; an optional, opt-in AI service exists under this ADR.
- The AI Evaluation standard moves from N/A to Applies. The eval harness and its results are
  the record.
- The privacy section of `docs/RESPONSIBLE-TECH-AUDITS.md` gains a real data subject for the
  first time: the free text a person types into the opt-in panel. Its handling is stated
  there.
- AI output is labelled AI-generated, unofficial, and not a recommendation from the State of
  California, every time it is shown, in both languages. The non-affiliation notice stays in
  the banner landmark above the masthead and is not moved, demoted or softened by this
  feature.
- **Deployment is a separate decision, not made here.** The static site's CloudFormation
  stack is untouched. A Lambda + Function URL shape for the service is prepared beside it in
  `infra/` with a cost bound and CORS locked to the site origin, and is deliberately not
  applied. Exposing the service publicly needs: the owner's decision on cost envelope, a
  model-access decision (Sonnet 5 is not enabled on this AWS account's Bedrock; Sonnet 4.6
  is), and a subprocessor note for the provider. Until then the service is a local and
  evaluated capability, not a public one.

## Alternatives considered

- **Keep the product model-free.** This was the standing decision and it was sound for what
  the product was. The owner has decided the product should do more, and the data supports
  more than a filter form can ask of it.
- **Let the model answer from the dataset directly** (hand it the JSON and take its prose).
  Rejected: it makes every number in the answer the model's word, and the whole point of this
  site is that no number is anyone's word. The structure → execute → narrate → verify shape
  keeps the dataset as the only evidence.
- **Let the model choose SOC codes or region names itself.** Rejected: a model is exactly
  the kind of component that will produce a plausible SOC code that is not in the 670. Free
  text is resolved lexically by the service against the published vocabulary, and what does
  not resolve is reported, not guessed.
- **Embeddings for retrieval.** Not needed at 670 occupations and 3,266 programs, and it
  would add a second model to explain. Lexical resolution over titles and alternate titles is
  inspectable and has no provider dependency.
- **Machine-translate the static catalogue at build time.** Rejected: it would replace a
  labelled gap with an unlabelled guess on every page, and it would close issue #32 by
  fiat. Runtime translation on request, labelled, leaves the catalogue honest.

## Revisit if

A human review of the prompts, the eval cases, and the Spanish output exists — at which point
the capability can be described as reviewed rather than verified-by-code only. Or if the
verifier's withheld-claim rate in recorded runs stays high enough that the narration is
mostly gaps, which would be evidence the model is not adding what the owner wanted.
