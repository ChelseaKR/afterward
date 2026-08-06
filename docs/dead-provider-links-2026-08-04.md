# Dead provider links — 2026-08-04

> **Superseded in part.** This document is left as the measurement it was, including the
> parts the code no longer matches. Two of them have since been answered by
> [`soft-404-provider-links-2026-08-05.md`](soft-404-provider-links-2026-08-05.md): the soft
> 404s this pass could not see are now detected from the page's own `<title>` — 20 URLs on 23
> pages, measured — and the HEAD-then-GET sequence described under "Manners" is now a single
> GET, for the reasons Control 4 below already implies. The floor this document warned about
> is lower than it was, and is still a floor.

Every program record from source D1 may carry a `program_url`, which the site renders as
**"Provider's website →"**. That link is an assertion this project makes on a reader's
behalf, and the federal feed does not maintain it. This is a measurement of how many of
those assertions are false, how confident we can be about each one, and what to do about it.

Deliverable: `src/camino/sources/link_check.py`, a standalone, importable module. Nothing
else in the repository was modified, no build was run, and nothing here changes what the
live site publishes today. Integration is a separate decision, and this document ends with a
recommendation rather than a change.

Measured against `data/processed/programs.json`, snapshot 2026-08-04: 3,266 California
programs, of which **1,836 carry a provider link** across **1,016 distinct URLs**.

---

## Headline

| | URLs | Program pages |
|---|---|---|
| Provider links in the snapshot | 1,016 | 1,836 |
| **Alive** — something answered and there is a page there | 769 | 1,339 |
| **Dead** — DNS has never heard of the host, or the server says the page is not there | **134** | **334** |
| **Indeterminate** — a host that is plainly there, or a failure we cannot pin on it | 113 | 163 |
| `http://` links with a *verified* `https` equivalent | 178 | 475 |

**334 program pages, 18.2% of every page that shows a provider link, point at something this
project can demonstrate is broken.** As a share of all 3,266 programs, 10.2%.

A further **163 pages could not be judged at all** and are deliberately left alone. That
number is the point of the exercise: a two-valued checker would have called most of them
dead, and would have been wrong about an unknown fraction of them.

The figure is also a **floor, not a total** — see "What the alive column hides".

---

## What "dead" was allowed to mean

The checker answers in three values, not two.

| Verdict | Reasons | What it rests on |
|---|---|---|
| `alive` | `ok`, `redirected_to_site_root`, `redirected_offsite` | A 2xx arrived. |
| `dead` | `dns_failure`, `not_found` (404), `gone` (410) | Either DNS has never heard of the host, or the host itself states the page is not there. |
| `indeterminate` | `forbidden` (403), `method_not_allowed` (405), `rate_limited` (429), `server_error` (5xx), `other_client_error` (other 4xx), `timeout`, `tls_failure`, `protocol_error`, `too_many_redirects`, `connection_failed` | A host that is demonstrably present, or a failure we cannot pin on the provider rather than on ourselves. |

The third row is the whole argument. A 403 means "not for robots"; it is a statement about
the requester, not about the page. A 405 means the server dislikes the *method*. A timeout
means slow. A persistent 500 means broken, which is a different claim from gone. An expired
certificate means the door is broken on a building that is still standing. None of those is
evidence that a school's website has ceased to exist, and **publishing "this link is dead"
about a working provider is a harm this project has no way to detect after the fact** — the
reader simply never sees the school.

`connection_failed` — the host resolves but the socket will not open — started out in the
`dead` row and was moved after the data came back. See "the one demonstrated false positive"
below; it is the only classification decision in this module that was changed by contact with
the corpus.

Three further design choices exist for the same reason:

1. **Nothing negative is believed on a HEAD alone.** Every non-2xx HEAD gets a second
   opinion from a GET before it is classified. Plenty of hosts answer HEAD with 403, 405 or
   even 404 for pages that GET perfectly well — measured below, 33 of the 769 live URLs do
   exactly that.
2. **A 2xx is not automatically an unqualified "ok".** A deep path that ends up at the site
   root, or on another domain entirely, is still `alive` but is flagged, because those are
   the shapes a quietly-retired page takes. See "What the alive column hides" below.
3. **An unchecked URL is not a dead URL.** There is no `Verdict` member meaning "not
   checked". A URL nobody read has no result at all, and `verdict_for()` / `is_dead()`
   return `None` for it. Absence never becomes a value — the same rule the `-1` suppression
   sentinel gets everywhere else in this codebase.

### Manners

These are mostly small colleges and adult schools on shared hosting, not CDNs.

- The project's own `USER_AGENT` from `dol_etp`, unchanged. No browser impersonation. A host
  that wants to refuse this client is entitled to recognise it and do so — which is exactly
  why a refusal is classified `indeterminate` rather than `dead`.
- HEAD before GET; GET streamed and closed unread, so nobody serves a body nobody looks at.
- Concurrency is **across** providers and never within one: URLs are grouped by site and each
  site is handed to a single worker as a unit, one request at a time, 1s apart.
- Retries only for what is plausibly transient (timeouts, connection and DNS failures,
  protocol errors, 408/425/429/5xx). 403, 404, 405 and 410 are decisions and are never
  repeated. `Retry-After` is honoured, and a host asking for longer than this client will
  hold is answered by going away, not by waiting.
- On-disk cache keyed by URL, so a rebuild does not re-ask 1,000 providers whether they still
  exist. TTLs are asymmetric — `alive` 30 days, `dead` 7 days, `indeterminate` 1 day —
  because acting on a stale `dead` hides a provider that has come back, which is the costlier
  mistake.

**Measured cost of the whole run: 1,493 HTTP requests for 1,016 URLs — 1.47 per URL, at most
8 for any single one — in under 8 minutes at 10 workers.**

---

## Results

### By reason

| Reason | Verdict | URLs | Pages |
|---|---|---|---|
| `ok` | alive | 699 | 1,221 |
| `not_found` (404) | **dead** | 111 | 171 |
| `dns_failure` | **dead** | 23 | 163 |
| `redirected_offsite` | alive (flagged) | 66 | 113 |
| `forbidden` (403) | indeterminate | 85 | 111 |
| `tls_failure` | indeterminate | 18 | 30 |
| `server_error` (5xx) | indeterminate | 3 | 7 |
| `timeout` | indeterminate | 3 | 6 |
| `other_client_error` (409) | indeterminate | 1 | 5 |
| `redirected_to_site_root` | alive (flagged) | 4 | 5 |
| `rate_limited` (429) | indeterminate | 2 | 3 |
| `connection_failed` | indeterminate | 1 | 1 |
| `gone` (410) | dead | 0 | 0 |

The 18 `tls_failure` results are worth one line, because they are not this client being
fussy. Spot-checked with `openssl s_client`: `www.extension.ucr.edu` serves a certificate for
`*.ucx.ucr.edu`, `seie.sonoma.edu` one for `*.prod.acquia-sites.com`, and `mvla.net` one
naming only `www.mvla.net`. Those are genuine hostname mismatches, and a reader with a
browser gets a full-page security interstitial. The sites are up; the door is broken. That is
a real defect worth reporting, and it is still not the claim "this page is gone" — hence
`indeterminate`.

### Worst offenders

| Pages | Reason | URL | Provider(s) |
|---|---|---|---|
| **126** | `dns_failure` | `http://www.laadulted.com` | Abram Friedman Occupational Center, East LA Occupational Center, East LA Skills Center and other LAUSD adult centres |
| 22 | 404 | `https://www.paloverde.edu/future-students/default.aspx` | Palo Verde College |
| 13 | 404 | `http://www.paloverde.edu/future-students/programs-certs/default.aspx` | Palo Verde College |
| 8 | 404 | `http://WWW.LAVERNE.EDU/EXTENDEDLEARNING` | University of La Verne |
| 7 | `dns_failure` | `http://www.trainingcenters.org` | Machinist Career College |
| 4 | 404 | `https://cryrop.org/Adult-Students/Programs/index.html` | Colton Redlands Yucaipa ROP |
| 4 | 404 | `https://mdae.mdusd.org/ctec` | Mt. Diablo Adult Education |
| 4 | 404 | `https://www.kccd.edu/…/21st-century-energy-center/about` | Kern Community College District |
| 4 | 404 | `https://www.lassencollege.edu/…/Tuition-and-Fees.aspx` | Lassen Community College |
| 3 | `dns_failure` | `http://colusacountyadultschool.org` | Colusa County Office of Education |

The distribution is extremely top-heavy: **one dead domain accounts for 126 of the 334
affected pages (37.7%)**, and the top four URLs account for 169 (50.6%). Two providers —
LAUSD adult education and Palo Verde College — account for 164 pages, 49.1% of the whole
problem.

Note what the LAUSD case actually is. Those are **real, operating schools**. Their old shared
domain lapsed; this project's own results show LAUSD adult education answering today at
`adulted.lausd.org`, which is where a *different* record's URL (`http://wearedace.org`, 6
pages) now redirects. The link is dead. The provider is not. Nothing in this module infers
the successor, and nothing should — but a human can, and 126 pages is worth a human's
half-hour.

### What the `alive` column hides

A soft 404 — "page not found" served with HTTP 200 — cannot be detected without fetching and
interpreting the body, and is reported `alive`. That limitation is real and was measured
rather than assumed:

- **`http://laadulted.com`** (the bare domain, 13 pages) resolves, returns **HTTP 200**, and
  serves a domain-parking stub that redirects to `/lander`. Classified `alive`/`ok`. It is
  the same defunct LAUSD domain as the 126-page entry above, and it is functionally dead.
- Of the **66 URLs (113 pages) flagged `redirected_offsite`**, a hand review found **12 URLs
  / 17 pages landing on a domain-sale or unrelated commercial page** while returning 200:
  seven `dronitek.com` paths and `www.aselbeauty.com` now redirect to
  `hugedomains.com/domain_profile.cfm?d=…`; `www.intechcollege.com` and
  `www.catruckschool.com` to `expireddomains.com`; `www.giligiacollege.com` to
  `seinquote.com`; `www.eastvalleycollege.com` to an unrelated blog.
- The other 54 offsite redirects are legitimate: catalogue vendors
  (`westhillscollege.com` → `westhillslemoore.elumenapp.com`, `curricunet.com` →
  `cuesta.curriqunet.com`), rebrands (`ces.sdsu.edu` → `globalcampus.sdsu.edu`,
  `moler.org` → `moler.edu`), and district consolidations (`wearedace.org` →
  `adulted.lausd.org`).

So **`redirected_offsite` is a review queue, not a verdict** — which is why the module flags
it and still calls it `alive`. Roughly **30 further pages are functionally dead behind an
HTTP 200** and no status-code check of any kind would find them. The honest total is
therefore "at least 334", not "exactly 334".

### And four of the dead links are typing errors, not lapsed domains

Four `dns_failure` hosts are misspellings in the federal record rather than domains that went
away: `https://www.uclaextension.ed` (missing the `u`), `https://www.uxcaextension.edu`
(`ucla` transposed), `http://www.academics.lmu.eduextension` (two fields run together), and
`https://wwww.untouchableapprentice.com` (four `w`s). Four pages. In the UCLA cases the
intended target is unambiguous — `https://www.uclaextension.edu/` is alive on 26 other pages
in this same corpus. These want correcting, not suppressing, and correcting them is a
judgement about intent rather than a measurement, so this module does not attempt it.

---

## `http://` that answers on `https://`

257 of the 1,016 URLs (788 pages) are plain `http`. Upgrading them is free for the reader and
strictly safer, so the checker looks for a *verified* https equivalent — never a guessed one.

| | URLs | Pages |
|---|---|---|
| `http://` links | 257 | 788 |
| …with a verified `https` equivalent | **178** | **475** |
| …of which the site already redirects to https by itself | 162 | — |
| …of which needed a direct probe of the https variant | 16 | — |
| `http://` links that are alive and offer no https at all | 29 | 60 |
| `http://` links that are dead or indeterminate | 50 | 253 |

Two details worth keeping:

- 162 of the 178 upgrades cost **no extra request**: the site already 301s `http` → `https`,
  so the redirect target is the evidence. Only 16 needed the https variant asked directly.
- **No dead `http` URL turned out to be alive on `https`.** The upgrade is a transport
  improvement for links that already work, not a repair for broken ones.

An upgrade is only offered when the https answer stays on the provider's own site. An https
URL that lands somewhere else is a different destination, not a safer one.

---

## False-positive risk assessment

A wrong `dead` verdict hides a real school from someone trying to enrol, and nothing
downstream can distinguish it from a true one. So the dead set was attacked with five
independent controls rather than trusted.

### Control 1 — repeatability

Every URL classified dead was re-read from a **cold cache, with a fresh client and a 40s
timeout** (up from 25s), in a separate process at a later time.

| | |
|---|---|
| Dead URLs re-examined | 135 |
| Still dead on the second pass | **135** |
| Flipped to alive or indeterminate | **0** |

(135 rather than 134: the second pass ran before `connection_failed` was reclassified.)

### Control 2 — the provider's own front page

For each dead URL the site root was checked independently. If the root answers normally and
the deep path 404s, the server is plainly talking to us and the 404 is a real statement about
that page. If the root is *also* refused, our client may simply be filtered and the 404 is
not trustworthy evidence.

| | URLs |
|---|---|
| 404 whose front page is **alive** — server answering us normally | **102** |
| 404 whose front page also 404s — the site serves 404 for everything | 7 |
| 404 whose front page is `indeterminate` (403) — **weaker evidence** | 2 |
| DNS failure whose front page is also dead — consistent, same host | 22 |
| DNS failure at a redirect target while the starting host is alive | 1 |

**92% of the 404s are corroborated by a live front page on the same host.** The two weak ones
are `WWW.LAVERNE.EDU/EXTENDEDLEARNING` and a Squarespace-hosted PDF; the La Verne case was
then confirmed by hand — `http://www.laverne.edu/extendedlearning` in lower case returns 200
and redirects to `/extended-learning/`, while the record's all-caps path genuinely 404s
against a case-sensitive server. Real 404, caused by how the URL was typed.

### Control 3 — an independent resolver

Every host behind a DNS failure was re-queried against **8.8.8.8, 1.1.1.1 and 9.9.9.9**
rather than the local resolver, so a broken resolver on this machine could not manufacture 22
dead providers.

| | |
|---|---|
| Distinct host names behind the 23 DNS failures | 22 |
| Resolvable by any of three public resolvers | **0** |

That includes both worst offenders: `www.laadulted.com` (126 pages) and
`www.trainingcenters.org` (7 pages) are unknown to all three. `adulted.sanjuan.edu`, the
redirect target that makes `https://www.sanjuan.edu/sunrisetc` dead, is likewise unknown to
all three while `www.sanjuan.edu` itself resolves fine — which is why the classifier tests
DNS on the host that actually failed rather than the one the request started from.

### Control 4 — what a HEAD-only checker would have got wrong

One bare HEAD, no retries, no GET fallback, against each of the 769 URLs this run called
alive.

| | URLs | Pages |
|---|---|---|
| Live URLs a bare HEAD does not report as alive | 33 | 67 |
| …404 on HEAD, 200 on GET — **would have been called dead** | 8 | 9 |
| …403 or 405 on HEAD — would have been downgraded to indeterminate | 12 | 43 |
| …transport failure on the single HEAD — would have been indeterminate | 13 | 15 |

Two honest caveats. The HEAD-only pass used a single attempt, so the 13 transport failures
overstate HEAD's specific fault. And all 8 of the "404 on HEAD, 200 on GET" URLs turn out to
be the parked `dronitek.com` and `aselbeauty.com` domains — so in *this* snapshot the GET
fallback did not actually rescue a genuine provider page. It is insurance that did not need
to pay out this time. The 12 URLs (43 pages) it kept out of `indeterminate` include
`cpe.ucdavis.edu` certificate programs and Merced County Office of Education's ROP pages,
which is a smaller but real benefit.

### Control 5 — cross-check against the browser-User-Agent audit

The prior adversarial audit that motivated this work used a browser User-Agent and a 12s
timeout and reported **173 dead URLs across 347 pages**. This run, with the project's honest
User-Agent, reports **134 dead across 334 pages**, plus 113 URLs / 163 pages it declines to
judge.

The page counts land within 4% of each other while 39 fewer URLs are called dead. That is the
expected signature: the big offenders are the same, and the difference is almost entirely
403 / TLS / 5xx / timeout results being classified as "unknown" instead of "gone". **The
honest User-Agent is not materially inflating the dead count** — if it were being filtered
into false 404s, the page total would have moved up, not stayed flat. (This is a coarse
comparison against a summary, not a per-URL diff.)

### The one demonstrated false positive

`http://www.ueicollege.com` — 1 URL, 1 page — was initially classified
`dead` / `connection_failed` after six consecutive `ENETUNREACH` failures. It is not dead. At
the same moment, on the same machine, `curl` fetched it (301), `nc` opened TCP to both of its
A records, a raw Python socket connected to both, and httpx itself fetched it successfully
when given the IP address with a `Host` header. Only httpx-given-the-hostname failed, and it
failed reproducibly. **The failure was ours.**

That is why `connection_failed` was moved from `dead` to `indeterminate`. It is the only
classification changed after seeing the data, it costs one page out of 335, and it removes
the only measured false positive from the dead set. A name DNS has never heard of is evidence
about a provider; a socket that would not open is evidence about a socket.

### Residual risk

After that change, every one of the 334 pages rests on one of exactly two things:

- **NXDOMAIN confirmed by three independent public resolvers** (163 pages), or
- **the provider's own server returning 404, while demonstrably answering us normally on the
  same host** (171 pages, corroborated by a live front page in 102 of 111 cases).

The weakest evidence in the set is the two 404s whose own front page returned 403 — 9 pages.
Eight of those nine are the La Verne case, confirmed by hand above, leaving **one page (0.3%)
resting on evidence nobody has corroborated a second way**. Everything else is either
NXDOMAIN across three resolvers or a 404 from a server that was demonstrably answering us.

So the residual false-positive risk on the 334 pages is **low — on the order of a single
page, well under 1%** — and there is now a known mechanism (Control 2, the front-page check)
for finding the weak ones rather than guessing at them.

Three caveats that no amount of re-checking removes:

1. **A verdict is a point-in-time observation.** Sites come back. This is why the cache TTL
   for `dead` is 7 days and for `alive` 30 — the stale verdict that hides a returning
   provider is the costlier one.
2. **One machine, one network, one moment.** A network-level block would show up as mass
   failure; 75.7% of URLs came back alive, which rules that out. The `ueicollege.com` case
   shows the residual per-host version of the same risk is real but rare — one URL in 1,016.
3. **Errors run much larger in the other direction.** At least 30 pages return HTTP 200 and
   are functionally dead (the parked `laadulted.com` bare domain, the `hugedomains.com` and
   `expireddomains.com` redirects). Soft 404s are not detectable at this cost, and **334 is a
   floor.**

---

## Recommendation: suppress, annotate, or neither

The question stops being binary as soon as the classes are kept apart. Each one wants a
different answer, and lumping them together is what makes it feel like a choice between two
bad options.

| Class | URLs / pages | Recommendation |
|---|---|---|
| `dns_failure` | 23 / 163 | **Suppress the hyperlink.** There is no destination. Keep the URL visible as plain, non-clickable text with the observation and its date, because it is the federal record's own value and a reader may want to try the Internet Archive. |
| `not_found`, `gone` | 111 / 171 | **Do not link the dead path.** For the 102 of 111 whose front page answers, link *that* instead, labelled as the provider's website rather than as the program page. Strictly better than either suppressing or annotating. |
| `indeterminate` | 113 / 163 | **Change nothing.** Render exactly as today. |
| `redirected_to_site_root` | 4 / 5 | **Relabel, do not suppress.** "Provider's home page", not a link that implies it reaches the program. |
| `redirected_offsite` | 66 / 113 | **Review queue for a human.** No automatic rule separates a catalogue vendor from a domain squatter. |
| `http` with a verified `https` equivalent | 178 / 475 | **Swap it.** No annotation, no reader-visible change beyond the scheme. |

### Why suppression, and not annotation alone, for the conclusive classes

A link is an assertion. This codebase already refuses to publish assertions it cannot
support — `clean_rate` drops a rate whose units it cannot verify, `clean_earnings` refuses a
figure too small to be a quarter's pay, `reconcile_rate` drops a zero the record's own counts
contradict, and the `-1` sentinel never becomes a number. "Provider's website →" pointing at
a 404 is the same category of error, and it deserves the same treatment: do not publish the
claim, and say why it is missing.

Annotation alone — keeping the link and warning that it may be broken — pushes the work onto
the reader and still spends their click. For someone deciding where to spend a year of their
life, that is the wrong trade.

Suppression alone, with nothing said, is dishonest in the other direction: it hides that the
federal record contains a URL at all, and it makes the dataset look thinner than it is.

**So: suppress the hyperlink, annotate the absence, and never annotate anything that was not
established.**

### The `indeterminate` class is where the discipline actually shows

113 URLs on 163 pages could not be judged, and the correct engineering decision is to do
nothing to them. Most are 403s from real institutions — `cpe.ucdavis.edu` certificate
programs, `fresnocitycollege.edu`, `careertraining.sdsu.edu`, `reedleycollege.edu`. Hanging a
"we could not reach this page" label on a working UC Davis certificate page, on the strength
of a bot filter, would be a false statement about a named institution printed next to its
WIOA outcome figures. A two-valued checker would have done exactly that to all 163 pages.

### The wording rule

Whatever is shown must be a statement about **our observation**, not about the provider, and
must carry the date — a verdict has a shelf life.

- Correct: *"We could not reach this page when we checked on 4 August 2026."*
- Wrong: *"This provider's website is down."* / *"Broken link."*

The first is true and checkable. The second is a claim about a named business that this
project cannot support.

### The invariant, restated as a build rule

Link checking needs the network. CI has none and builds from the committed fixture, so the
check has to be advisory data attached during `make data`, never a build gate. That means the
dataset carries **three** states per link, not two: checked-and-broken, checked-and-fine, and
**not checked** — and a build with no link data must render exactly as the site renders
today. `verdict_for()` and `is_dead()` return `None` for an unchecked URL precisely so that
the rendering layer is forced to have a branch for it and cannot default a gap into a verdict.

### One note on scope

The top four URLs account for 169 of the 334 affected pages. A hand-written override table
with four entries would fix half the problem in an afternoon — but identifying a provider's
successor domain is a judgement about *identity*, not a measurement, and this module
deliberately does not attempt it. It reports what it saw and leaves that call to a person.

---

## Using the module

```python
from pathlib import Path

from camino.sources.link_check import LinkCheckCache, build_client, check_urls, is_dead

cache = LinkCheckCache(Path("data/raw/link-cache"))
with build_client() as client:
    checks = check_urls(urls, client=client, cache=cache)

# True / False / None -- None means "never checked", and must not render as either.
is_dead(checks, program.program_url)
```

- `check_urls` returns a mapping containing only URLs that were actually read.
- `verdict_for`, `is_dead` and `upgrade_for` all return `None` for an unchecked URL, and
  `None` for a program that has no URL at all.
- `summarise(checks, pages_per_url=...)` reproduces every count in this document.
- `check_url` raises `ValueError` on anything that is not an absolute http(s) URL — a
  malformed string is a caller bug, not a dead link, and must not be recorded as one.
- The cache is safe to delete; it only costs a re-check.
