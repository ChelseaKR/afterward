**What does this change, and why?**

---

### Checks

- [ ] `make verify` passes (lint, types, Python tests, provenance)
- [ ] `cd web && npm run verify` passes (types, tests, contrast, build, axe)
- [ ] I ran `make data-offline` rather than `make data` — the fixture is enough for
      everything except pipeline changes, and needs no credentials

### If it touches how a figure is displayed

- [ ] A missing value still renders as "not reported", never as `0`, `—`, or a blank cell
- [ ] Nothing new asserts a program is good or bad — the site publishes figures and their
      limits, and draws no conclusions
- [ ] A comparison is like-for-like, or it is not drawn

Those three are in CONTRIBUTING as the non-negotiable rules, with the reasoning. They are not
style preferences: this site is read by people deciding how to spend a year and several
thousand dollars, and a figure that overstates what is known does them real harm.

### If it touches the interface

- [ ] Works at 390px wide
- [ ] Keyboard-reachable, with a visible focus ring
- [ ] Any new colour pairing is added to `web/scripts/contrast-audit.mjs` — it checks the
      pairings it is told about and nothing else, so a control that is not listed is
      unchecked rather than passing

### If it touches user-facing text

- [ ] Both `en` and `es` in `web/lib/i18n.ts`. The test suite fails an untranslated string,
      but it cannot tell you the Spanish is *good* — say if you are unsure and want review
