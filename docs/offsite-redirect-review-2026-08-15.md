# The addresses that answer from somewhere else — 2026-08-15

`docs/soft-404-provider-links-2026-08-05.md` closed with a queue it could not act on: 69
provider URLs, on 109 program pages, that answer 200 from a domain the federal record does not
name. Three of them are hijacked. Roughly fifty are ordinary rebrands. From the redirect alone
they are the same event, so the whole class was published as a working "Provider's website"
link — the three hijacked ones included.

This is that queue, worked.

---

## What was live while the queue was open

Fetched from the site on 2026-08-15, snapshot `2026-08-07`:

```
$ curl https://afterward.chelseakr.com/data/programs/f69dffd6-31e5-11f1-ac14-00155dd2f085.json
"provider_link": { "href": "http://www.giligiacollege.com", "linked": true,
                   "reason": "redirected_offsite", "notice": null }
```

Four Giligia College pages, one East Valley College page and one Hollywood Cultural College
page carried a live link to a domain somebody else controls. A Californian reading a program
page to decide whether to spend a year and several thousand dollars was being handed it.

Two other things the same fetch showed, both worth recording because neither is in any issue:

- **The published dataset contains no `soft_not_found` and no `domain_for_sale` decisions at
  all.** The title detector this project built on 2026-08-05 — 20 URLs on 23 program pages —
  has never had an effect on anything a reader sees. `data/interim/link-checks.json` is still
  the 2026-08-04 run, and an `alive` verdict is cached for 30 days, so re-running
  `make link-check` today would not re-ask most of them either. The repair exists, is tested,
  and has never run against published data: the same shape as #28.
- The links published on 2026-08-15 were read on **2026-08-04**. Every sentence the site
  prints about them carries that date, which is the design working, but the gap is worth
  knowing when reading the counts below.

## What separates a rebrand from a hijack

Not the redirect, and not how alike the two names look. Whoever holds a lapsed domain can
point it anywhere and can register something that looks like the school's name. What they
cannot do is put a line in the federal ETPL feed, get into the `.edu` zone, or take over a
registrable domain the institution still holds. So the rule is corroboration from a source
outside the old domain's control, and there are four of them
(`src/afterward/sources/link_review.py`):

| Rule | What it says | Why a hijack cannot satisfy it |
|---|---|---|
| `registry` | The destination is inside the same `.edu`/`.gov` registrable domain the filed URL was already inside | `.edu` is restricted to accredited U.S. postsecondary institutions; one registrable domain there is one institution |
| `feed` | The destination **host** is filed as a program URL by another ETPL record naming the same provider | The feed is filed by providers to the state and published by U.S. DOL |
| `accredited_name` | The destination is an `.edu` whose name continues the filed one | Name continuity counts only in a zone that cannot be entered by buying a lapsed `.com` |
| `review` | A person opened it and wrote down what they found, with evidence and a date | — |

`review` is the only rule that can conclude *not* the provider: "this is somebody else's
website now" is a judgement about content, and no signal available to a fetch makes it. It is
also the only rule that can rescue a rebrand the other three do not reach.

Anything none of them reaches is **unresolved**, and unresolved is published as unresolved:
the URL as filed, in plain text, with a dated sentence saying the address now goes somewhere
this project could not confirm belongs to the provider. Not linked.

That asymmetry is the opposite of the one the rest of the link checker runs on, where the harm
to avoid is calling a working school dead, and it is deliberate. Here the filed address does
not reach the school either way. The reader loses a link that was going somewhere else
regardless; what they gain is not being handed one.

The `feed` rule is indexed by host rather than by registrable domain, which matters on this
corpus: Butte College files `butte.curriqunet.com`, and that says nothing about
`cuesta.curriqunet.com`. The `registry` rule is restricted to `.edu` and `.gov` for the same
kind of reason: two unrelated schools on one website builder share a registrable domain and
nothing else.

## The queue, worked

69 URLs, 30 distinct filed-host → destination pairs, 109 program pages.

| Resolution | Pairs | URLs | Program pages |
|---|---:|---:|---:|
| Same provider | 21 | 53 | 86 |
| For sale | 5 | 12 | 14 |
| Not the provider | 3 | 3 | 6 |
| Unresolved | 1 | 1 | 3 |

**29 of the 30 pairs are classified.** Eleven by the three automatic rules, eighteen by hand,
with the evidence for each recorded in `src/afterward/sources/provider-link-review.json`.

### Not the provider

| Filed | Now serves | Pages |
|---|---|---:|
| `giligiacollege.com` | `seinquote.com`, an Indonesian gambling site | 4 |
| `eastvalleycollege.com` | `mechanicaljungle.com`, an Indonesian lottery site | 1 |
| `hollywoodculturalcollege.com` | `stopglaucomajhu.org`, a Baltimore glaucoma-screening charity | 1 |

None of these was fetched to reach this document. They were opened once, by hand, during the
2026-08-05 review; the destinations here are what the checker recorded on 2026-08-04. A
hijacked domain is hostile territory and there is nothing further to learn from it.

The third is the one worth dwelling on. `stopglaucomajhu.org` is a real charity running a real
screening programme. It is not a scam, it is not malware, and it is not a rebrand of a Los
Angeles college — which is exactly why no rule short of a person looking could have told it
from `moler.org` → `moler.edu`.

### For sale

`dronitek.com`, `aselbeauty.com`, `intechcollege.com`, `catruckschool.com` (all → HugeDomains
or expireddomains.com) and `maiquelascosmetology.net` (→ an Unstoppable Domains listing). In
every case the destination URL names the filed domain as the thing being sold. These reuse the
sentence the title detector already had for that situation: the address answered, an
advertisement is what answered, and the reader is told to look the school up by name.

A lapsed domain is still not a closed school. Nothing published here says otherwise.

### Unresolved

One: `nevadahelpdesk.tech` → `nevadahelpdesk.ai`, 3 program pages. The names match exactly and
it is probably a rebrand. Nothing corroborates it — the company site LinkedIn lists as official
still points its training link at the `.tech` address and never mentions the `.ai` one, the
destination was registered in March 2026 behind a privacy-redacted registration on different
nameservers, and no third party mentions it. Anyone can register a matching name in an open
zone, including whoever took the old one. It stays unresolved, and its three pages print the
address and say so.

### Same provider

Eleven pairs corroborated automatically (`sdsu.edu` internally; `aaa-institute.com`,
`lemoorecollege.edu`, `egace.egusd.net`, `butte.curriqunet.com` by the feed; `bamasf.edu`,
`lacareercollege.edu`, `moler.edu`, `heavyequipmentcollege.edu`, `airstreamsrenewables.edu`,
`cryrop.edu` by name in the accredited zone) and ten by hand, each against a source that is not
the destination's own claim about itself: EDUCAUSE `.edu` registry records for
`angelesuniversity.edu` (whose administrative contact is at `angelescollege.edu`) and
`palladium.edu`; a college's own accreditation evidence file for the eLumen catalogue; the
colleges' own committee pages for the CurriQunet catalogues; the district's adult-education
page for `aemusd.com`; the county office of education for `rcoe.us`; a Better Business Bureau
record showing the same address under a new business name for `1on1truckacademy.com`; 211LA
for `avadulted.org`; a California business filing's principal address for `untouchableaa.com`.

`angelescollege.edu` → `angelesuniversity.edu` is the useful one to look at. It is a real
rename, and the automatic rules correctly refused it: `angelesuniversity` does not continue
`angelescollege`, it merely shares a word, and a shared word is something a hijack can arrange.
It took a registry record to settle, which is what the ledger is for.

## What a reader sees now

- 86 pages: unchanged. The link they had, going where it went.
- 20 pages: the address in plain text and a dated sentence — 6 saying it leads somewhere
  unrelated, 14 saying it is being advertised for sale.
- 3 pages: the address in plain text and a dated sentence saying we could not confirm the
  destination is the provider's.

No page says a provider is gone. Every sentence is about what this project observed on a date.

## Two gates, because the code was never the problem

The classifier was not what published three hijacked domains. What published them is that the
artifact in production was built by a pipeline older than the code describing it, and nothing
in the file said so — the same failure as #28, which is why both gates read artifacts rather
than source:

- `scripts/provider_link_check.py` refuses a dataset in which any off-site redirect is linked
  without `redirect: "same_provider"` recorded on it. `null` there is the shape of every
  dataset built before this review, and it is refused. Wired into `make dataset-verify`, so it
  runs before anything is packaged for a release.
- `scripts/publish_preflight.py` reads the **built pages** and refuses to publish if any
  program page carries an `href` to an address the review rejected. It is not enough to check
  the input to a renderer.

Run today, against the working dataset — the one production is serving — the first gate refuses
it, naming 129 links. That is the correct answer and it will stay the answer until the dataset
is rebuilt.

## What this does not fix

The code change reaches nobody until a new dataset is built and published:
`make data` → `make dataset-publish` → the dispatch-only deploy workflow. Until then the live
site keeps serving the 2026-08-07 asset, hijacked links included.

Worth doing in the same pass, and separately from this change: clear `data/raw/link-cache` and
re-run `make link-check`, so the 2026-08-05 title detector finally reads the corpus it was
written for. Ten soft 404s and ten domain-sale listings on 23 program pages are still published
as working links today, and a warm cache is the only reason.
