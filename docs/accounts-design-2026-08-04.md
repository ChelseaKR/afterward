# Saved programs, saved searches, and whether they need accounts

Design note, 2026-08-04. Nothing here is built.

## The thing to decide first

The site tells every visitor, in both languages, that it is *"Free to use, with no account."* The
README says it twice more. That is not a throwaway line — it is the positioning. This project
exists because California's incumbent workforce portal puts its training list behind a login,
and the opening paragraph of the README says so.

So the question is not "how do we add accounts". It is **"what do users actually need, and how
much of it needs an account at all?"** Those turn out to be very different sizes.

## What people want

Three things, in rough order of how often they will want them:

1. **Keep a shortlist.** I found four programs; I want to look at them again tonight.
2. **Show someone.** My case manager, my partner, the person at the job center. This is a
   decision people make with other people.
3. **Come back to a search.** Medical assisting under $5,000 near Fresno, with outcomes.

Only one of those needs a server, and it is not the one you would guess.

## Most of it does not need an account

**A shortlist is local.** `localStorage` holds it, survives closing the tab, costs nothing, needs
no server, and creates no record of what anyone is considering. Ships in days.

**Sharing is a URL.** The search state is already a handful of values — query, area, city, cost
cap, outlook, sort. Encode them in the query string and the search page becomes shareable,
bookmarkable, and back-button-correct. A shortlist can be a URL too: the ids are short and four
of them fit comfortably. That single change delivers "show someone" *better* than an account
would, because the recipient does not need to sign up to see it.

**A saved search is a bookmark**, once the URL carries the state.

What is left for an account is one thing: **the same shortlist on your phone and the library
computer.** That is real — many users of this site will not own a laptop — but it is one feature,
not the premise, and it does not need to come first.

## Recommendation: local-first, sync later, and design the data model once

**Phase A — no accounts, no server.** URL-encoded search state, `localStorage` shortlist, a share
link. The site stays a pure static export. The "no account" promise stays true. Zero new attack
surface, zero new privacy exposure, zero recurring cost.

**Phase B — optional accounts, only if Phase A proves the need.** Cognito for identity, a small
API for storage, `localStorage` as the source of truth that syncs upward. The account is *purely*
additive: every feature works signed out, and signing in only makes a shortlist follow you. The
day the promise changes from "no account" to "no account required" is a real editorial decision
and should be made deliberately.

If the Phase A data model is a plain serializable object from the start, Phase B is a sync
adapter rather than a rewrite. That is the whole reason to sequence it this way.

## The privacy problem, which is the serious part

A saved shortlist on this site is not a shopping cart. What someone saves reveals, with fair
confidence:

- that they are unemployed or trying to leave their job
- their likely income bracket, from the cost filter they set
- where they live, from the area filter
- **health information**, by inference — someone saving phlebotomy, medical assisting and
  nursing assistant programs is telling you something; someone saving substance-use counselling
  programs is telling you more
- immigration-adjacent signals, from ESL and citizenship-adjacent programs
- financial distress, from filtering to free programs

The users of this site are disproportionately people with less power, and a database of *who is
considering which training* is a genuinely sensitive object. It would be interesting to a
subpoena, a breach, or a future owner of the domain.

This argues for the local-first design on its own merits, independent of engineering effort: **the
safest place to store this is the user's own device, and the safest amount to collect is none.**

If Phase B happens, the non-negotiables:

- **Email only.** No phone number — SMS is PII, costs money, and buys nothing here.
- **No marketing, ever.** The email address authenticates and nothing else. No list, no
  newsletter, no "programs you might like" mail.
- **Deletion that actually deletes**, self-serve, in both languages, without emailing anyone.
  CCPA/CPRA applies squarely: California site, California users, California residents' rights.
- **Publish retention.** An account untouched for N months is deleted, and the number is stated
  on the About page rather than buried in a policy.
- **Store ids, not inferences.** Save `["f6900f55…"]`, never "interested in healthcare".
- **No third-party analytics.** The site has none today; an account must not become the excuse.

## Concrete shape, if Phase B happens

Cognito is the right identity choice here, mostly because the infrastructure is already AWS and
it avoids introducing a second vendor into a project whose whole posture is auditability.

- **Cognito user pool**, email as the only attribute, **passwordless email OTP** rather than
  passwords. No password to store, leak, or reset; no support burden; a much shorter privacy
  policy. The tradeoff is a slower sign-in, which is acceptable for a feature nobody uses daily.
- **Hosted UI is the wrong fit.** It cannot carry the California Design System, and it is
  awkward to make properly bilingual. A custom form against the Cognito SDK is more work but this
  site's whole credibility rests on looking and reading like it belongs to its users.
- **API Gateway (HTTP API) + Lambda + DynamoDB.** One table, `PK = user sub`, `SK = item type`,
  DynamoDB TTL doing retention automatically rather than by cron.
- **The site stays a static export.** The API is called from the browser only when signed in.
  Every page renders identically signed out, which also keeps the SEO story intact — and SEO is
  how anyone finds this at all.
- **The CSP must change**, and that is a real cost. Today it is `connect-src 'self'`, which is a
  strong guarantee. Adding an API origin weakens it, so the origin should be exact and nothing
  else should be added alongside.
- Cost is not a factor: Cognito's free tier is 50,000 monthly actives, and the rest is single
  dollars per month at any plausible scale.

## Recommendations are a separate decision, and they are gated

A recommendation system is not an extension of saved programs — it is the guidance layer, and
this project's own plan gates that pending the severance negotiation, with an explicit go
decision and a re-check of the clean-room posture as the conditions. Saving a shortlist does not
touch that gate. "Programs you might like" does.

Worth saying plainly for when that gate opens: on this dataset, a recommender would be making
consequential suggestions to people about how to spend a year and thousands of dollars, using
outcome data this project states plainly it does not verify, where a third of programs report
nothing at all and 103 carry figures that cannot be attributed to them. Every honesty constraint
the site has built — no verdicts, no comparisons that are not like-for-like, absence rendered as
absence — exists because the data does not support confident claims. A recommender is a confident
claim by construction.

That is not an argument against building one. It is an argument that the interesting problem is
**how a recommender declines to recommend**, and that it should be designed from the coverage
gaps outward rather than from the ranking function inward. The deterministic occupation
adjacency already in the pipeline is a more honest starting point than anything learned.

## What I would build first

The share link. It is a day of work, needs no infrastructure, breaks no promise, and solves the
thing people will actually do with this site — send it to someone who is helping them.
