# What the site costs a phone, measured

2026-08-05. Every number here was measured against a build of the full 3,266-program
dataset, with the command that produced it. Sizes are brotli quality 11, because that is what
CloudFront serves; the raw figures a directory listing reports are five to twelve times
larger and describe a hosting bill rather than anything a reader pays.

The headline: the site was spending about 400 KiB of every visitor's data on pages they had
not asked for and mostly would never open. That is fixed. The search index, which is the
thing everyone assumes is the problem, turned out to be second.

## How to reproduce

```
cd web && npm run build                       # static report + first-visit budget
node scripts/transfer-audit.mjs out /en/       # real Chromium, prefetches included
```

`size-report.mjs` reads files. `transfer-audit.mjs` runs a browser, and only the browser can
see a prefetch.

## Before and after

First visit, cold cache, brotli, measured in Chromium:

| Route | Before | After | Saved |
| --- | --- | --- | --- |
| `/en/` (search) | 585,348 | 338,526 | −246,822 (−42%) |
| `/en/programs/<id>/` | 558,768 | 156,885 | −401,883 (−72%) |
| `/en/occupations/<soc>/` | 553,078 | 151,129 | −401,949 (−73%) |
| `/en/providers/` | 543,479 | 200,987 | −342,492 (−63%) |
| `/en/about/` | 551,182 | 149,256 | −401,926 (−73%) |

## What was actually wrong

Next prefetches a `<Link>` when it scrolls into view. The masthead is on all ~9,000 pages, so
its four links are in view immediately on every one of them, and they pointed at four of the
five heaviest routes the site has. Each page template also opens with a "← Back to search"
link, above the fold, pointing at the heaviest route of all.

Costed per page, before the fix:

| Prefetched by every page | Brotli |
| --- | --- |
| `/en/` document | 118,486 |
| `/en/__next.$d$lang.__PAGE__.txt` (its RSC segment) | 110,777 |
| `/en/occupations/` + its segment | 64,385 |
| `/en/providers/` + its segment | 54,882 |
| `/en/paying-for-training/` + its segment | 15,434 |
| JS for those routes | 37,079 |
| **Total** | **~401,000** |

So `/en/about/` — a text page whose own document is 7.7 KiB — cost 538 KiB to open, and 73%
of that was speculative.

Two details make it worse than a straightforward over-eager prefetch:

- **The search route is prefetched from the search page.** The masthead wordmark points at
  `/en/`, so opening `/en/` fetched a second, complete copy of the 3,266-program index the
  browser had already parsed inline. 110,777 bytes, guaranteed wasted, every time.
- **It is invisible to every check the repo had.** `size-report.mjs` measured the export on
  disk. Prefetching is a runtime decision that leaves no trace in a built file, so no amount
  of reading the export could have found this.

The fix is `prefetch={false}` on the masthead links, the back-links, the language chooser and
the 404 routes. Result cards still prefetch: a program page is ~8 KiB and is the thing the
reader is looking at a list of.

## The search index

`web/public/data/search-index.json`, 3,266 rows: 1,232,356 raw, 185,024 gzip −9, 108,666
brotli.

It is loaded **eagerly and inline**, not fetched. `app/[lang]/page.tsx` passes
`getSearchIndex().programs` as a prop to a client component, so React serialises the whole
thing into `/en/index.html` for hydration. Splitting `/en/index.html`:

| Part of `/en/index.html` | Raw | Brotli |
| --- | --- | --- |
| Inline RSC payload (the index) | 1,385,892 | 112,153 |
| Markup, head, everything else | 60,362 | 7,897 |

The copy at `public/data/search-index.json` is uploaded to the CDN and **never requested by
anything**. The only `fetch()` in the client is `Compare.tsx` pulling one program record.

Composition of a first visit to `/en/` (331,673 brotli, static):

| | Brotli |
| --- | --- |
| JavaScript (10 chunks) | 188,851 |
| Inline search index | 112,153 |
| CSS (2 chunks) | 24,336 |
| Markup | 7,897 |

## Per-field cost of the index

Measured by removing one key from all 3,266 rows, re-splicing the payload into the real
`/en/index.html` and re-compressing:

| Field | Raw saved | Gzip saved | Brotli saved |
| --- | --- | --- | --- |
| `n` name | 155,782 | 40,591 | 27,041 |
| `i` uuid | 153,502 | 30,186 | 19,648 |
| `o` occupation titles | 238,624 | 36,715 | 9,936 |
| `$` cost | 36,417 | 12,341 | 8,134 |
| `p` provider | 128,469 | 12,328 | 6,540 |
| `s` SOC codes | 94,348 | 17,259 | 5,760 |
| `me` median earnings | 41,224 | 7,865 | 5,141 |
| `w` weeks | 28,920 | 6,154 | 4,176 |
| `er` employment rate | 38,449 | 5,208 | 3,195 |
| `cr` completion rate | 37,695 | 5,131 | 3,140 |
| `wage` | 50,131 | 10,264 | 2,545 |
| `op` openings | 43,251 | 8,199 | 1,881 |
| `c` city | 66,693 | 5,343 | 1,873 |
| `g` growth | 33,347 | 6,290 | 1,711 |
| `a` area | 79,765 | 5,484 | 952 |
| `$partial` | 62,053 | 2,816 | 610 |
| `at` cohort attributable | 39,295 | 1,550 | 576 |
| `r` outcomes reported | 37,135 | 1,522 | 547 |

Note how cheap `r` and `at` are: 1,123 bytes for the two flags that carry the site's honesty
guarantees. Whatever else is done to this index, there is never a size argument for touching
them.

## Measured and not taken

**Dropping `wage`. Nothing reads it — at all.** Worth 2,545 bytes. Established by deleting
the key from `SearchEntry` and running `tsc --noEmit`: zero errors outside tests, where `s`
produces three, `op` one and `cr` one. `search_entry` in `src/afterward/build.py` computes it
as the best wage down any of the program's paths and no page, sort, filter or comparison has
ever asked for it. Left alone here on purpose: removing a field changes a published data
artifact, that deserves its own decision rather than a footnote in a prefetch change, and
0.75% of a first visit is not a reason to rush it. It is free whenever someone wants it.

**Dropping `s` (SOC codes) from what the client receives.** Worth 5,760 bytes. `s` is read
only by server-side code — `lib/data.ts`, `lib/browse.ts`, the provider page — and by no
`"use client"` module at all, so the client is carrying it for nothing. Not done here because
the only way to strip it is to change the prop type `SearchApp` and `Compare` are written
against, and 1.7% of a first visit does not justify reaching into two components another
change was already touching. Worth doing when those files are next open.

**Columnar or positional rows.** Rejected on the same ground the existing code rejects
interning area names (see the docstring on `search_entry` in `src/afterward/build.py`): a
positional row cannot be read on its own, and a header that ever slipped out of step with its
rows would mislabel every figure silently. Brotli already collapses the repeated key names —
the whole 18-key vocabulary costs far less than moving it would risk.

**Deferring the index until a search begins.** Would take ~111 KiB off the first paint of
`/en/`, and would take it back the moment anyone typed. The people this site is for arrive
intending to search, so this trades a cost everyone pays for a delay at the exact moment they
act — and the same 111 KiB would then be fetched with a five-minute cache lifetime rather
than read out of a document. Not obviously wrong, but it is a product decision rather than an
optimisation, and it needs the no-JavaScript fallback thought through with it.

**Shortening the keys.** They are already one and two characters.

## What now guards this

`size-report.mjs` gained a second report: the brotli transfer of a first visit to one page of
each shape, with a 420 KiB per-route budget that fails the build. `/en/` sits at 324 KiB.
The budget is a ceiling with room to grow, not a ratchet — it is there to catch a dataset
being inlined into a page, which is the mistake this codebase has actually made.

It cannot catch a prefetch regression; nothing static can. `npm run transfer` is the check for
that, and it is the one to run when anything about how the site loads changes.
