# 0002. Bilingual strings live in typed TypeScript modules, not gettext catalogs

## Status

Accepted (2026-08-07, recording a choice made at the first release)

## Context

The portfolio's Internationalization standard and its conformance tooling expect string
catalogs in a conventional catalog directory (`locales/`, `i18n/`, or similar), typically
gettext or ICU MessageFormat files with an extraction step.

Afterward shipped English and Spanish together from its first release, but the strings live
in typed TypeScript modules (`web/lib/i18n.ts` and `web/lib/vocabulary.ts`) keyed by locale,
not in catalog files. That was chosen deliberately:

- A missing translation is a compile error, not a runtime fallback. The type system enforces
  key parity between English and Spanish; gettext tooling makes a missing string a silent
  English fallback, which is exactly the failure mode this site refuses.
- A test fails if a Spanish string is left identical to its English original, which catches
  the "copied the key, forgot to translate" case extraction tooling does not.
- Feed text that has no Spanish counterpart (program names, descriptions, provider names) is
  handled as a first-class case: `feedTextLang()` marks it `lang="en"` at every render site
  so a Spanish screen reader does not read English words in Spanish phonemes, and a
  source-scan test asserts the guard is present at every render site (see
  `docs/wcag-2.2-aaa-conformance.md` on SC 3.1.2).

## Decision

Keep the typed-module approach. The Internationalization standard *applies* to this repo and
is *met*, with stronger enforcement than catalog files would give a solo-maintained project;
the divergence is in mechanism, not in outcome. `docs/I18N.md` records the current state.

## Consequences

- The portfolio's mechanical i18n check looks for a catalog directory and will not recognize
  this layout; that check reports a gap here that is a tooling-recognition limit, not a
  missing translation. This ADR is the record a reviewer should land on.
- Translators need to edit a TypeScript file. CONTRIBUTING.md says so and says Spanish
  review is the most valuable outside contribution; the strings are all in one file on
  purpose.

## Revisit if

The site gains a third language, an outside translation workflow that needs standard
tooling, or the string count grows past what one file can carry legibly. ICU MessageFormat
catalogs with a compile-time parity check would be the migration target.
