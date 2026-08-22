# Evals for `afterward.ask`

Four committed suites, scored by code from the service's own trace, under
[ADR 0003](../docs/adr/0003-runtime-ai-at-the-edges.md). Cases live in `cases/`, results in
`results/`, the harness in `src/afterward/ask/evals.py`, and its tests in
`tests/test_ask_evals.py`.

```bash
make ask-eval-dry                     # scripted fake over the fixture; proves the harness runs
AFTERWARD_AI_PROVIDER=bedrock AFTERWARD_AI_MODEL=claude-sonnet-4-6 \
  make ask-eval DATASET_DIR=path/to/real/dataset EVAL_OUT=evals/results/<date>-<provider>-<model>.json
```

## The suites

| Suite | Question | The number that matters |
|---|---|---|
| `structuring` | Does the model turn a person's words into the right query, and refuse to guess when the words do not support one? Bilingual, with deliberately vague cases. | `abstention.rate` (refused to guess on the vague cases) and `field_accuracy` |
| `suppression` | **The eval that matters most.** Each case is a program whose ground truth for a measure is null, and the person asks about exactly that measure. | `absence_rendered_as_value_shown`, which must be 0; `shown_said_not_reported`, which should equal the case count |
| `grounding` | What fraction of the claims the model wrote verified against the published JSON? | `verified_rate`, and `withheld_reasons` for the rest |
| `comparability` | Did the narration use a benchmark the site does not use, or put a quarterly figure beside an annual one without both labels? | `invented_benchmark_shown` and `period_unlabelled_shown`, which must be 0 |

Every suite reports two layers where they differ: what the model wrote (`*_by_model`) and what
the reader would have seen after the verifier (`*_shown`). The second is the product. The
first is how much the verifier is doing, and it is published because a verifier that is
doing a great deal is evidence about the prompt, the model, or both.

## What a results file must carry

`provenance.provider`, `model`, `prompt_version`, `commit`, `date`, `dataset_snapshot`,
`is_fixture`, and a `status` of `run` or `not_run`. `tests/test_ask_evals.py` reads every
file under `results/` and fails if one lacks any of these, names the scripted fake as its
provider, or is a `dry_run`. A number without provenance is not a measurement, and a suite
that was not run live is recorded as `not_run` rather than estimated.

## What the cases are built on

The suppression, grounding and comparability cases name programs by uuid from the committed
60-program fixture (`fixtures/data`), which is a subset of the real dataset with the same
ids, so the same case runs hermetically in CI on the fake and live on the real data. The
structuring cases check occupation terms by what they *resolve to* in the dataset, and most
of the expected codes are among the 670 real occupations rather than the fixture's 56; that
suite is therefore meaningful on the real dataset, and `is_fixture` in the provenance says
which a run used.
