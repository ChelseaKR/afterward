# WCAG 2.2 AAA: what is automated, and what cannot be

Updated 2026-08-07. This site targets **WCAG 2.2 level AAA**. This note records what the
automated gates actually prove, and — more usefully — what they cannot.

## The four gates

| Gate | Covers | Where it runs |
| --- | --- | --- |
| `npm run a11y` | Every axe-core rule, including the sixteen axe disables by default | jsdom, 22 pages, both languages |
| `npm run a11y:rendered` | Every axe-core rule, against the DOM `a11y` cannot see | Chromium, search results + comparison table, both languages |
| `npm run a11y:browser` | `color-contrast-enhanced` (1.4.6 AAA) and `target-size` (2.5.8 AA) | Chromium, light **and** dark |
| `npm run contrast` | 1.4.6 analytically, from the design system's own tokens | Node, both schemes |

Two gates cover contrast because they fail differently. The analytical one resolves tokens
and computes exact ratios, but only for pairings someone thought to list — it passed while
36 real elements failed, because none of them were on its list. The browser one checks every
rendered element and catches what the list forgot, but only on the pages it loads. Neither
alone is coverage.

`npm run a11y` reads the static export, which on `/en/` and `/es/` is the chrome around an
empty result list — everything `SearchApp.tsx` shows is fetched from `search-index.json` and
rendered after hydration, so it was never in the document jsdom parses, and neither was the
comparison table, which does not exist until a reader selects two programs and opens it
(#29). `npm run a11y:rendered` (`scripts/a11y-rendered.mjs`) serves the built `out/` itself on
a free port, waits for the result list to actually populate, audits it with every axe rule,
then selects two programs, opens the comparison, and audits again with the table in the DOM.
Because it serves itself it needs no separately-started server and runs as part of `verify`.

`npm run a11y` now enables every rule axe ships. Running axe unconfigured is **not** "all the
checks": sixteen rules are off unless asked for, including `color-contrast-enhanced` (AAA
1.4.6), `identical-links-same-purpose` (AAA 2.4.9), `meta-refresh-no-exceptions` (AAA 2.2.4)
and `target-size` (2.2 AA 2.5.8). This audit reported "no violations" for months while those
sat switched off.

## What automation found here

Raising the bar from AA to AAA on 2026-08-05 surfaced real defects, not paperwork:

- The shrinking-occupation callout and both warning badges set near-black on saturated fills —
  5.47:1 and 6.37:1 at 12px. These carry the warnings this site treats as load-bearing, and a
  caveat that is hard to read is a caveat that does not work.
- The design system's primary button was white on `--primary-70`: 4.6:1 at 18px/600, which
  WCAG does not count as large text, so the threshold was 7:1 and not 4.5:1.
- Regulation citation links sat on a panel rather than the page — 5.72:1, not the 7.02:1 the
  same colour reaches on white. Those are the links a reader uses to check a claim about
  someone else's money against the actual rule.
- The not-reported grey was 6.63:1. It is the most repeated string on the site.
- The first run of `npm run a11y:rendered` (#29) found two defects in a region no gate had
  ever rendered before: the design system's own `:is(button, a.button):where(:hover)` rule
  outranks `.compare-open`'s un-hovered background on specificity, so hovering or focusing
  "Compare these" (which is also the state a click leaves it in) swapped in a teal background
  under text still fixed dark, failing `color-contrast`. And the sticky selection tray and
  the comparison table both used "Side by side" as their region's accessible name, failing
  `landmark-unique` — invisible before because nothing rendered both regions in the same
  document to compare them against each other.

## What no tool can check, and what was done instead

These AAA criteria are judgements. They are listed so their absence is a decision on record
rather than a gap nobody noticed.

- **1.4.8 Visual Presentation** — line length, justification, and user-settable colours. The
  measure is capped at 62ch and text is never justified; user-settable colour is not offered.
- **2.4.9 Link Purpose (Link Only)** — axe's rule catches identical text pointing at different
  places, which passes. Whether "Provider's website →" is self-describing out of context is a
  human call; it is judged to be, given its heading.
- **3.1.3 Unusual Words / 3.1.5 Reading Level** — the site defines WIOA, ITA, ETPL and SOC in
  place, and the About page states the data's limits in plain language. Reading level is not
  measured; claiming a grade level from an automated score would be a worse statement than
  making none.
- **2.2.3 No Timing / 2.2.4 Interruptions** — nothing here times out, refreshes, or interrupts.
  `meta-refresh-no-exceptions` is enabled and passes.
- **1.2.6 Sign Language / 1.2.8 Media Alternative** — no audio or video exists on this site.
- **2.3.2 Three Flashes** — nothing animates.
- **3.1.2 Language of Parts** (level AA, below this site's AAA bar, and still worth recording
  here) — axe ships `valid-lang`, which checks that a `lang` attribute's *value* is real. No
  rule, in axe or anywhere else, detects that an attribute is *missing*, so `npm run a11y`
  reported zero violations while every Spanish program page carried an unmarked English `<h1>`
  and an unmarked English description paragraph — the two longest, most consequential passages
  on the page, read to a Spanish-set synthesiser as English words in Spanish phonemes. Found by
  reading rendered output rather than by any gate (issue #27). `program_name`, `description`
  and `provider_name` have no Spanish counterpart in the feed at all, for any program, and are
  now wrapped in `lang="en"` at every render site — program and provider pages, an occupation's
  program list, search results, and the comparison table — via `feedTextLang()` in
  `web/lib/i18n.ts`. Occupation titles were already handled per-occupation by
  `occupationTitleLang()`, which checks the 70 of 670 with no published Spanish name. A source-
  scan test (`web/lib/englishFeedText.test.ts`) asserts every known render site of the first
  three fields carries the guard, which is the part 3.1.2 itself cannot be made to check.

## Known limits of the coverage

- The gates run against a sample of pages, not all 49,000. The templates are shared, so a
  template fault appears on the sampled page; a data-dependent one might not. The sample is
  22 named pages and `npm run a11y -- --list` prints it. Until 2026-08-15 it was whichever of
  those 22 happened to exist: the list was filtered by `existsSync` before use, so a route
  renamed, removed, or not emitted in one language left the sample and the gate reported no
  violations over what was left, saying nothing. A page on the list that is not in the build
  now fails the run. Covered by `web/scripts/a11y-audit.test.ts`.
- `npm run a11y:browser` needs a separately-started server, so it is not part of `verify` and
  must be run deliberately after a build. `npm run a11y:rendered` does not share this limit —
  it serves `out/` itself — and is part of `verify`.
- `a11y:browser` discovers its three detail pages by following the first qualifying link it
  finds, and until 2026-08-15 dropped any it could not find — the same silent shrinking of
  the sample as above, one script over. That was not hypothetical here: it looked for a
  program page under `/en/programs/`, there is no such index (programs are reached from the
  client-rendered search results and from provider and occupation pages), the lookup returned
  the 404 template with no program links on it, and so **the site's densest template was
  never audited by this pass and every run still reported a clean result.** It is now scouted
  from a provider page, which does link programs, and a template this pass cannot reach fails
  the run. It stays the weaker of the two guards: which program gets audited is whichever the
  provider page links first, not a pinned page the way the 22 named ones are.
- `a11y:rendered` covers the result list and the comparison table with two programs selected.
  It does not cover: the "no results" empty state, a card in its saved (`aria-pressed`) state,
  the shortlist bar that appears on first save, or the comparison with more than two programs
  selected. Each is a real state a reader reaches; none has been in an audited document yet.
- No gate tests with an actual screen reader, and no automated tool does.
