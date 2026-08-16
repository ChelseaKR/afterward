# The links that answered and were not pages — 2026-08-05

`docs/dead-provider-links-2026-08-04.md` measured 334 program pages whose only onward link was
demonstrably broken, and closed with a warning it could not act on:

> A soft 404 — "page not found" served with HTTP 200 — cannot be detected without fetching and
> interpreting the body, and is reported `alive`. … **334 is a floor.**

This is that measurement, and the change that acts on it. It re-reads every provider URL the
2026-08-04 pass called `alive` and asks each one what it says it is.

---

## What the site publishes today

From `web/public/data/coverage.json`, snapshot 2026-08-04, the dataset now live:

| | Program pages |
|---|---|
| Carry a provider link | 1,836 |
| …the link answered (`alive`) | 1,326 |
| …we could not reach it (`dead`) | 333 |
| …could not be judged (`indeterminate`) | 177 |
| Published as a link | 1,654 |
| …upgraded to https | 473 |
| …sent to the provider's front page because the filed page 404s | 151 |
| Published without a link, URL as plain text | 182 |

That is the 2026-08-04 recommendation working as intended. The gap is entirely inside the
1,326-page `alive` column.

## What the alive column turned out to hide

Every URL in that column that appears on a program page — 767 of them, on 1,326 pages — was
re-read on 2026-08-05 with a plain GET, one request per URL, one at a time per site, 767
requests in 132 seconds. Content types: 755 HTML, 10 PDF, 2 `text/plain`.

**20 of the 767 were not pages at all. They sit under 23 program pages, every one of which
publishes a confident "Provider's website →" link today.**

| What it really is | URLs | Pages | What the page called itself |
|---|---|---|---|
| The provider's own "page not found" screen, served 200 | 10 | 11 | `Not Found`, `404 Error`, `404 - Elk Grove Unified School District`, `Page Not Found \| Maiquela's Cosmetology Academy` |
| A listing offering the domain for sale | 10 | 12 | `AselBeauty.com is for sale \| HugeDomains`, `DronitEk.com is for sale \| HugeDomains`, `intechcollege.com — Buy this expired domain \| ED.com` |

By provider: Springboard (2 pages), Elk Grove Adult and Community Education (4), Butte College
(3), Maiquela's Cosmetology Academy (2); Dronitek (7), Asel Beauty (2), InTech College (2),
CA Truck School (1).

Twelve of the 20 were already flagged `redirected_offsite` — the review queue the previous
document created and left for a human. Eight were plain `ok`, with no signal of any kind: the
same URL, the same host, HTTP 200, and a "page not found" screen. **No status-code check of
any strength would have found those eight.**

### Two things also found, and deliberately not acted on

- **16 URLs answer HTTP 202 with a SiteGround bot-check interstitial** — a bare meta-refresh
  to `/.well-known/sgcaptcha/`, no title, no text. A reader's browser passes it and reaches the
  school. They stay `alive`.
- **`http://laadulted.com` (13 pages), `nhlearninggroup.com` (3 pages) and `www.emras.edu`
  (7 pages)** are functionally dead behind a 200 — a 114-byte JavaScript redirect to a parking
  lander, and the string `NGINX Proxy - Ready`. They are **not** detected, and that is a
  decision rather than an oversight: the only thing distinguishing them from the 16 captcha
  interstitials above is that they are equally empty, and any rule broad enough to catch them
  catches 16 working providers with it. Emptiness is not evidence. These 23 pages remain a
  known floor.

## The detector, and why it is this narrow

Only the `<title>` is read, and reading stops at `</title>` — a **median of 529 characters**
per provider, under 1 KB for more than half of the 755 HTML responses, capped at 64 KB.

Two patterns, each anchored to a whole title segment rather than searched for inside one:

- `SOFT_NOT_FOUND_TITLES` — the page states it does not exist.
- `DOMAIN_FOR_SALE_TITLES` — the page offers the address for sale.

Every branch of both is a string a real California provider served on 2026-08-05. Nothing was
invented.

**Precision, measured: 695 of the 755 HTML responses yielded a readable title under the cap.
The patterns fired on 20 of them. All 20 were reviewed by hand and all 20 are true positives.
Zero false positives.**

Four choices worth stating, all in the same direction — a wrong `dead` hides a real school
from someone trying to enrol, and nothing downstream can tell it from a true one:

1. **Title only, not `<h1>`.** All 20 detections fire on the title alone; the `h1` added
   nothing on this corpus and is where page furniture lives.
2. **Whole segments, not substrings.** "Web Server Administration: 404 Handling" is a course,
   not a 404.
3. **Truncation fails towards `alive`.** 32 of the 755 push `</title>` past the cap. A title
   nobody read is a title nobody matched: the cap can cost a detection, never manufacture one.
4. **No hostname allowlist.** A list of domain marketplaces is a guess about who is in that
   business and rots the day a new one opens. A page saying it is selling the address is that
   page's own statement about itself — the only kind of evidence this module accepts.

## What changes for a reader

The two findings want different answers, so they get them.

**Soft 404 → treated exactly as the 404 it is.** All four hosts answer normally at their root
(checked: Elk Grove Adult and Community Education, Butte College, Springboard, Maiquela's
Cosmetology Academy), so all 11 pages gain a working link to the provider's home page, labelled
as such, with the existing dated sentence. The reader's situation is identical to a hard 404 —
the filed page is not there and the school is — so the wording is identical too.

**For sale → no link, and its own sentence.** There is no front page to offer; the whole
address is merchandise, and asking a parking host for its root would only produce a second
sales listing. The URL is kept as plain text and carries a new notice:

> When we checked on 2026-08-05, this web address served a page offering the domain for sale
> rather than the provider's site. Searching for the provider by name, or telephoning it, is
> more likely to reach it.

"We could not reach this page" would have been wrong twice over here. It is false — the address
answered perfectly well, and an advertisement is what answered — and it invites a reader to try
again, which is the one thing that cannot work. A lapsed domain is also **not** a closed
school: the LAUSD adult centres behind this dataset's largest dead domain are open and
teaching at a different address, and nothing published says otherwise.

## HEAD is gone

Reading a title needs a GET, and the module used to send a HEAD first and confirm anything
negative with a GET. Sending the GET alone is not a compromise, it is strictly better on the
module's own terms:

- The 2026-08-04 audit measured **33 of 769 live URLs whose HEAD disagreed with their GET**, 8
  of them answering HEAD with 404 for a page that GETs perfectly well. The HEAD-then-GET second
  opinion existed only to survive that class of defect. Asking the way a reader asks makes it
  unreachable instead.
- It costs **fewer** requests, not more. That pass spent 1,546 requests on 1,067 URLs. At least
  231 of those URLs — every `dead` and `indeterminate` result except the 23 that short-circuited
  on DNS — spent a HEAD that then had to be repeated as a GET. One GET per URL removes every one
  of them, and the 767-URL re-read this document is based on took 767 requests and 132 seconds.
- The body is bounded and stopped at `</title>`; nothing else is read at all. A non-2xx
  response and a non-HTML body are still closed unread, because neither could settle anything.

## Reproducing this

Nothing here runs in CI and nothing here is a build gate — the check needs a thousand third
parties to be reachable, and CI has no network. It is the same explicitly-invoked pass as
before:

```
make link-check     # afterward check-links; writes data/interim/link-checks.json
make data           # afterward build; picks the report up
```

The detector itself is tested offline against the exact titles quoted above
(`tests/test_link_check.py::TestWhatA200SaysItIs`), and the shapes that must survive it
untouched are tested beside them (`TestTitlesThatMeanNothing`).

## What is still not detected

- The 23 pages of empty-bodied parking stubs and unconfigured proxies described above.
- 6 pages whose links redirect to an unrelated live site: `giligiacollege.com` → an Indonesian
  gambling site (4 pages), `eastvalleycollege.com` → an Indonesian lottery site (1),
  `hollywoodculturalcollege.com` → a Baltimore glaucoma-screening charity (1). These are real,
  working, well-formed pages; nothing mechanical separates them from the ~50 legitimate
  rebrands and catalogue vendors in the same `redirected_offsite` class
  (`moler.org` → `moler.edu`, `ces.sdsu.edu` → `globalcampus.sdsu.edu`,
  `westhillscollege.com` → `westhillslemoore.elumenapp.com`). They remain a review queue for a
  human, which is what the previous document concluded and this one does not improve on.

Both are named here so the next person measures the remainder rather than rediscovering it.

---

## 2026-08-15 — the second of those is answered, and the first is not

The `redirected_offsite` queue is worked in
[docs/offsite-redirect-review-2026-08-15.md](offsite-redirect-review-2026-08-15.md). Two things
in this document are now out of date and are corrected there rather than rewritten here:

- "nothing mechanical separates them" was the right conclusion about the *redirect*, and the
  wrong conclusion about the *record*. What separates them is corroboration from a source the
  holder of a lapsed domain does not control, and three such sources exist in what this
  project already has.
- The queue is no longer published optimistically. Until 2026-08-15 every member of this class
  — including the three hijacked domains named above — was published as a confident
  "Provider's website" link. Only a corroborated destination is linked now.

The parking-stub half of this section stands unchanged, for the reason it gives: emptiness is
not evidence.
