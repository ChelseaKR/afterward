# Recorded Projections Central responses

Two responses from `https://public.projectionscentral.org/`, saved verbatim on
**2026-09-11** and re-indented with `json.tool --indent 1`, the same one-space JSON this
project writes everywhere else, so a diff of a future re-recording is readable. Nothing else about them has been edited: no row was added, removed, reordered or
corrected, which is the point of recording them at all.

They are read by `tests/test_projections_central.py`. See PROVENANCE.md, source D9.

| file | request | rows |
|---|---|---|
| `nv-longterm-2026-09-11.json` | `GET /Projections/LongTermRestJson/32?items_per_page=1000` | 657, all Nevada |
| `all-states-29-1141-2026-09-11.json` | `GET /Projections/LongTermRestJson/all/29-1141` | the **first 8** of 55, verbatim and in order; the pager is kept whole, so the file says 55 itself |

## Why the second one is here even though no code path asks for it

`all-states-29-1141-2026-09-11.json` is the endpoint this project's adapter deliberately
does **not** use, and it is recorded so the reason is a test rather than a sentence. Its
first row is

    {"Area": " United States", ..., "STFIPS": "0", "OccCode": "29-1141"}

filed at the head of the same array as the states -- the row after it is Alabama -- and
carrying a real measurement of the United States. Any adapter that took the first row, or
that fell back when its own state was absent, would publish it as a state's figure. The
test asserts that the parser refuses it by name.

### Why this one is a slice and the Nevada one is not

**The subset rule: the first eight rows as served, in order, unedited.** No row was
rewritten, reordered or corrected -- the eight that are here are byte-for-byte the eight
that arrived -- and `pager.total_items` is kept at its served value of 55, so the file
states its own incompleteness rather than looking whole.

Eight rather than 55 because the full response names every reporting state, and one of
those names is a string `scripts/provenance_check.py` refuses anywhere in this repository
outside PROVENANCE.md. That check enforces the clean-room constraint and is deliberately
blunt; weakening it to hold a test fixture would be the wrong trade, and a fixture that
happened to include the name would fail `make verify` for a reason that has nothing to do
with the code under test. The eight kept rows carry the whole property being tested: the
national row exists, it is first, it is in the same array, and a state row follows it.

## What the Nevada recording is expected to contain

Derived by the tests from the file rather than restated in them, so a re-recording updates
the expectations by being read:

- 657 rows, every one `STFIPS: "32"`, `Area: "Nevada"`, `BaseYear: "2024"`,
  `ProjYear: "2034"`.
- 649 detailed occupations, 7 broad occupations and one major-group total (`00-0000`).
- One row this pipeline refuses: `45-4029 Logging Workers, All Other`, published as
  `Base: "0", Projected: "0", Change: "0", PercentChange: "25"`. Employment is published to
  the nearest ten, so the zeros are a rounding floor rather than a count, and the row
  contradicts itself.
- No wage column of any kind, and `AvgAnnualOpenings` where this pipeline's records carry a
  ten-year total.

## Re-recording

    curl -s 'https://public.projectionscentral.org/Projections/LongTermRestJson/32?items_per_page=1000' \
      | python3 -m json.tool --indent 1 > tests/fixtures/projections-central/nv-longterm-<date>.json
    curl -s 'https://public.projectionscentral.org/Projections/LongTermRestJson/all/29-1141' \
      | python3 -m json.tool --indent 1 > tests/fixtures/projections-central/all-states-29-1141-<date>.json

`items_per_page` accepts 10, 25, 50, 100 and 1000 and answers **404 "No results found."** to
anything else — the same answer it gives for a state code it has nothing for.
