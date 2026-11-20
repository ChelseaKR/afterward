# Afterward Accessibility Conformance Report

**WCAG Edition.** Accessibility Conformance Report (ACR), based on the VPAT® 2.5 Rev WCAG
edition.

VPAT® is a registered service mark of the Information Technology Industry Council (ITI).

## Product information

- **Name of product/version:** Afterward (afterward.chelseakr.com), web front end version
  0.1.0 (`web/package.json`), evaluated on branch `a11y/acr-2026-11` built from `origin/main`
  at `df2f69e` plus that branch's fixes.
- **Report date:** 2026-11-19.
- **Product description:** A free, public, static website, in English and Spanish, that lists
  California training programs reported under WIOA, what the federal record says happened to
  the people who took them, and the state's own projection for the occupation each one leads
  to. There is no account, no sign-in, no payment and no form that sends anything anywhere.
  Search, filtering, comparing and saving a shortlist all happen in the reader's browser.
- **Contact information:** Open an issue with the accessibility template at
  <https://github.com/ChelseaKR/afterward/issues/new?template=accessibility.md>. No account
  details or personal information are needed to describe a problem.
- **Notes:**
  - **This report describes the site as it will be once branch `a11y/acr-2026-11` is merged
    and deployed.** Six problems found during this evaluation are fixed on that branch (see
    "Changes made for this report"). Until it is deployed, the live site still has them, and
    the remarks below for 1.4.10, 1.4.11, 2.4.6, 2.4.11 and 4.1.3 are not yet true of it.
  - The site's own target is WCAG 2.2 AAA, and its build gates run every axe-core rule. This
    report covers Level A and AA only, which is what an ACR asks for. What the gates prove
    and what they cannot is recorded in [docs/wcag-2.2-aaa-conformance.md](../wcag-2.2-aaa-conformance.md).
  - **No one has yet tested this site with a screen reader** (VoiceOver, NVDA, JAWS or
    TalkBack), or in Safari or Firefox. Where a criterion depends on what assistive
    technology actually announces, the remark says what was verified by automation and code
    reading and what still needs a person. The steps for that person are in Appendix A.
  - The Spanish pages are machine-translated and have not been reviewed by a native speaker;
    every Spanish page says so. That is a language-quality limit, not a WCAG criterion, and it
    does not change any row below.
  - The site renders one colour palette. It does not switch to a dark palette when the
    operating system asks for one, so "light and dark" testing below produced identical
    results. The dark tokens are still checked analytically by `npm run contrast`.
  - Pages that need JavaScript: search, filters, comparison and the saved list are
    client-side. With JavaScript off, the search page says so and links to the occupation
    and provider indexes, which, like every program, occupation and provider page, are
    static HTML.
- **Evaluation methods used:**
  - The repository's own gates, run on the evaluated build: `npm run a11y` (axe-core 4.14,
    every rule, 22 pages in both languages, jsdom); `npm run a11y:rendered` (axe-core, every
    rule, Chromium, the search results and comparison table in both languages, print media);
    `npm run contrast` (every text pairing at 7:1 from the design system's own tokens, in both
    palettes).
  - Gates added on this branch and now part of `npm run verify`: reflow at 320 CSS px for
    every page template in both languages; keyboard reachability of every sideways-scrolling
    table at that width; a keyboard walk of the search page with four programs in the sticky
    comparison tray, on a 1280px and a 320px screen, failing on any control that lands
    entirely behind the tray; and 3:1 non-text contrast for every focus ring and form-field
    border colour the stylesheet uses.
  - A one-off Chromium (Playwright 1.63) evaluation of 24 pages — every public template in
    both languages, plus the root language chooser and the not-found page — and of the search
    page's interactive states (results, programs selected for comparison, comparison open,
    a program saved, no results), at 1280×900 in light and dark colour-scheme emulation and at
    320×640: axe-core with the WCAG 2.0, 2.1 and 2.2 A and AA tags; a Tab walk recording the
    focus order, whether each stop shows an indicator and whether it is hidden; horizontal
    overflow at 320 CSS px; the WCAG 1.4.12 text-spacing overrides, checked for clipped text;
    and the contrast of every focus indicator and control border against its background.
  - Reading the source of every page template and interactive component for the criteria
    automation cannot decide.
  - Not used: screen readers, Safari, Firefox, mobile devices, voice control, switch access,
    or any participant with a disability.

## Applicable standards/guidelines

This report covers the degree of conformance for the following accessibility standard:

| Standard/Guideline | Included in report |
| --- | --- |
| [Web Content Accessibility Guidelines 2.2](https://www.w3.org/TR/WCAG22/) | Level A (Yes), Level AA (Yes), Level AAA (No) |

WCAG 2.2 includes every success criterion of WCAG 2.0 and 2.1 (except 4.1.1, which 2.2
removed; it is listed below for readers who need a 2.0 or 2.1 answer), so this report also
answers for those versions at the same levels.

## Terms

- **Supports:** The functionality of the product has at least one method that meets the
  criterion without known defects or meets with equivalent facilitation.
- **Partially Supports:** Some functionality of the product does not meet the criterion.
- **Does Not Support:** The majority of product functionality does not meet the criterion.
- **Not Applicable:** The criterion is not relevant to the product.
- **Not Evaluated:** The product has not been evaluated against the criterion. This can only
  be used in WCAG Level AAA criteria.

## WCAG 2.2 Report

### Table 1: Success Criteria, Level A

| Criteria | Conformance Level | Remarks and Explanations |
| --- | --- | --- |
| 1.1.1 Non-text Content (Level A) | Supports | The site has no content images. The wage-range chart on occupation and program pages is an SVG marked `aria-hidden`, because the table directly below it carries every value with headers. The "×" that removes a program from the comparison tray has an accessible name ("Remove … from comparison"). axe image and SVG rules pass on all 24 pages. How the chart's omission and the "×" buttons sound is in Appendix A. |
| 1.2.1 Audio-only and Video-only (Prerecorded) (Level A) | Not Applicable | No audio or video. |
| 1.2.2 Captions (Prerecorded) (Level A) | Not Applicable | No audio or video. |
| 1.2.3 Audio Description or Media Alternative (Prerecorded) (Level A) | Not Applicable | No audio or video. |
| 1.3.1 Info and Relationships (Level A) | Supports | Headings, lists, landmarks (`header`, `nav`, `main`, `footer`, a named search form and named regions), data tables with `th scope` for rows and columns, `fieldset`/`legend` for the checkbox groups, `dl` for each program's figures, and native `details`/`summary` disclosures. "Not reported" is text, not only a colour or a blank. axe structure rules pass on all pages and states. Whether the reading order of a result card makes sense aloud is in Appendix A. |
| 1.3.2 Meaningful Sequence (Level A) | Supports | Visual order follows the DOM. The filters panel collapses on a phone with `details`, not CSS reordering, so what is seen and what is read stay in the same order. Checked with the Tab walk and by reading the layout CSS. |
| 1.3.3 Sensory Characteristics (Level A) | Supports | Instructions refer to controls by name, not by shape, colour, size or position. Checked by reading the strings in `web/lib/i18n.ts`. |
| 1.4.1 Use of Color (Level A) | Supports | Shrinking occupations, programs that reported nothing and the strongest figure in a comparison are each said in words or marked with text for screen readers as well as colour or weight. Links in running text are underlined (axe `link-in-text-block` passes). |
| 1.4.2 Audio Control (Level A) | Not Applicable | No audio. |
| 2.1.1 Keyboard (Level A) | Supports | Every control is a native link, button, input, select, checkbox or `summary`. The Tab walk reached every one on every template. On a narrow screen, wide tables scroll inside their own box; the ten tables with no link in them now take keyboard focus so they can be scrolled with the arrow keys, and are named regions labelled by the heading above them (fixed on this branch; before it, nine of them could not be scrolled without a mouse on a 320px screen). Nothing needs a mouse, drag or hover. |
| 2.1.2 No Keyboard Trap (Level A) | Supports | The Tab walk cycled through every page and state without being held. The site has no modal dialogs or embedded widgets. |
| 2.1.4 Character Key Shortcuts (Level A) | Not Applicable | No keyboard shortcuts. |
| 2.2.1 Timing Adjustable (Level A) | Supports | No time limits. "Copy link" shows "Link copied" for two seconds and then returns to its label; nothing the reader needs to do is timed. The root page redirects to `/en/` immediately (a zero-second redirect, which the criterion allows), and the live site answers `/` with a server redirect instead. |
| 2.2.2 Pause, Stop, Hide (Level A) | Not Applicable | Nothing moves, blinks, scrolls or updates on its own. The result count changes only when the reader changes the search. |
| 2.3.1 Three Flashes or Below Threshold (Level A) | Supports | Nothing flashes. Animations are turned off for readers who ask for reduced motion. |
| 2.4.1 Bypass Blocks (Level A) | Supports | "Skip to main content" is the first focusable element on every language page and moves to `main`. Every page also has landmarks. |
| 2.4.2 Page Titled (Level A) | Supports | Every template has its own title naming the page and the site, in the page's language (for example, "Every training provider \| Afterward", and each program's title names the program, provider and city). |
| 2.4.3 Focus Order (Level A) | Partially Supports | Focus order follows the reading order on every template (Tab walk). One exception: removing a program from the comparison tray with its "×" button, or pressing "Clear" in the tray or the saved-list bar, removes the control that has focus. Chromium continues from the same place in the page on the next Tab; other browsers and screen readers may send focus back to the top of the page. Not fixed on this branch; see the summary of remaining gaps. |
| 2.4.4 Link Purpose (In Context) (Level A) | Supports | Link text names its destination: program, provider and occupation names, "How this site gets its figures…", and outbound links that say whose site they open. No "click here" or "read more" links. |
| 2.5.1 Pointer Gestures (Level A) | Not Applicable | Nothing uses multipoint or path-based gestures. |
| 2.5.2 Pointer Cancellation (Level A) | Supports | All controls are native elements that act on release. |
| 2.5.3 Label in Name (Level A) | Supports | Visible labels are the start of each accessible name: a result's checkbox shows "Compare" and is named "Compare: [program name]". The "×" remove buttons show a symbol, not a text label. The "show more" button's visible text and name are now the same words (changed on this branch). |
| 2.5.4 Motion Actuation (Level A) | Not Applicable | Nothing responds to device motion. |
| 3.1.1 Language of Page (Level A) | Supports | `<html lang="en">` or `lang="es"` on every page. The root chooser and the not-found page are English pages with each Spanish passage marked `lang="es"`. |
| 3.2.1 On Focus (Level A) | Supports | Focus never changes context, opens anything, or submits anything. |
| 3.2.2 On Input (Level A) | Supports | Changing a filter, the sort order or the search text updates the result list in place and the address bar's query string; it does not navigate, open a window or move focus. The language switch is a link. |
| 3.2.6 Consistent Help (Level A) | Supports | The help the site offers is in the footer of every language page, in the same order (shared layout): "How complete this data is", the privacy and analytics notice with its opt-out, and the link to the project on GitHub, where problems are reported. There is no contact form, chat or phone number. |
| 3.3.1 Error Identification (Level A) | Not Applicable | No input can be in error: the search box accepts any text, and every other control offers fixed choices. A search that finds nothing says so and names the filters that would bring results back. |
| 3.3.2 Labels or Instructions (Level A) | Supports | Every input and select has a visible `label`; checkbox groups have a `legend`; filters that hide programs explain what they hide beside the control (`aria-describedby`). |
| 3.3.7 Redundant Entry (Level A) | Not Applicable | No multi-step process and nothing the reader is asked to enter twice. |
| 4.1.1 Parsing (Obsolete and removed) (Level A) | Supports | Removed in WCAG 2.2. For WCAG 2.0 and 2.1, the W3C notes this criterion is always satisfied for content written in HTML. |
| 4.1.2 Name, Role, Value (Level A) | Supports | Native elements throughout. Save buttons expose their state with `aria-pressed`; comparison checkboxes with `checked`/`disabled`; disclosures with `details`/`summary`. axe passes on all pages and on every interactive state listed under evaluation methods. What VoiceOver and NVDA actually announce for these has not been heard (Appendix A). |

### Table 2: Success Criteria, Level AA

| Criteria | Conformance Level | Remarks and Explanations |
| --- | --- | --- |
| 1.2.4 Captions (Live) (Level AA) | Not Applicable | No live audio or video. |
| 1.2.5 Audio Description (Prerecorded) (Level AA) | Not Applicable | No video. |
| 1.3.4 Orientation (Level AA) | Supports | No orientation lock. Layout tested at 320 and 1280 CSS px wide. |
| 1.3.5 Identify Input Purpose (Level AA) | Not Applicable | The site collects no information about the reader. The only text input is a search box. |
| 1.4.3 Contrast (Minimum) (Level AA) | Supports | Lowest text contrast measured by axe across all 24 pages and every search state: 7.01:1. `npm run contrast` holds 36 named text pairings at 7:1 or above (the AAA level) from the design system's tokens. |
| 1.4.4 Resize Text (Level AA) | Supports | Text is sized in `rem`. Every template reflows without loss at 320 CSS px, which is 1280px at 400% zoom, so 200% is covered. |
| 1.4.5 Images of Text (Level AA) | Supports | No images of text on any page. (The link-preview image other sites show for a shared link is not part of the page.) |
| 1.4.10 Reflow (Level AA) | Supports | Every page template, in both languages, fits a 320 CSS px screen with no sideways scrolling; this is now a build gate. Wide data tables (comparison, provider, occupation, coverage and CTDL tables) scroll inside their own box, which the criterion allows for two-dimensional data. Fixed on this branch: the search page was 403px wide in English and 432px in Spanish (the region select was as wide as its longest option, and a long program name pushed each card wider), and the CTDL page was 411px (a list of long technical terms and a bare web address). |
| 1.4.11 Non-text Contrast (Level AA) | Supports | Focus rings the site draws are now `--primary-80`: 4.54:1 on the page and 3.70:1 on the grey panels. They were `--primary-60`, 2.87:1 and 2.34:1 (fixed on this branch). Select and search-box borders are now 4.70:1 on the page and 3.83:1 on the filter panel; the selects were 2.76:1 (fixed on this branch). Both are now checked by `npm run contrast`. The design system's own button focus ring is 15.85:1 or more. Links, inputs and checkboxes use the browser's default focus ring and checkbox; Chromium's is a two-colour ring, while Safari's and Firefox's have not been measured (Appendix A). The coloured left rules on callouts and cards are decoration: the same information is in their text. |
| 1.4.12 Text Spacing (Level AA) | Supports | With the 1.4.12 overrides applied (line height 1.5, letter spacing 0.12em, word spacing 0.16em, paragraph spacing 2em), no text was clipped or overlapped on any of the 24 pages, at 1280 or 320 CSS px. |
| 1.4.13 Content on Hover or Focus (Level AA) | Supports | The site shows no content of its own on hover or focus. Two disabled controls carry a `title`, which the browser shows and which the criterion excludes; the reason they are disabled is also said aloud in the tray when the comparison limit is reached. |
| 2.4.5 Multiple Ways (Level AA) | Supports | Search, the occupation index, the provider index, links between related program, provider and occupation pages, and a sitemap. |
| 2.4.6 Headings and Labels (Level AA) | Supports | Headings name their sections; labels name their controls. Fixed on this branch: the button that shows more results was labelled "+ 50", which a screen reader reads as a number; it now reads "Show 50 more programs" ("Ver 50 programas más"). |
| 2.4.7 Focus Visible (Level AA) | Supports | Every one of the stops in the Tab walk, on every page and state, showed a focus indicator (the site's own outline, the design system's, or the browser's default). |
| 2.4.11 Focus Not Obscured (Minimum) (Level AA) | Supports | The comparison tray is sticky at the bottom of the screen and up to 408px tall. Before this branch, tabbing put three filter selects entirely behind it on a desktop, and most of the result list behind it on a phone. The page now reserves scroll space the height of the tray while it is shown, and a build gate tabs through the search page with four programs selected, at 1280 and 320 CSS px, and fails on any control hidden behind it. Nothing else on the site is sticky or fixed. |
| 2.5.7 Dragging Movements (Level AA) | Not Applicable | Nothing is dragged. |
| 2.5.8 Target Size (Minimum) (Level AA) | Supports | axe `target-size` passes on all 24 pages and every search state in Chromium. Links inside sentences are exempt. |
| 3.1.2 Language of Parts (Level AA) | Supports | Program names, descriptions and provider names come from an English-only federal feed; on Spanish pages each is marked `lang="en"` wherever it is shown, and a source test (`web/lib/englishFeedText.test.ts`) holds every place they render to it. Occupation titles with no published Spanish name are marked the same way. |
| 3.2.3 Consistent Navigation (Level AA) | Supports | One shared layout: the same masthead, navigation, language switch and footer, in the same order, on every page of a language. |
| 3.2.4 Consistent Identification (Level AA) | Supports | The same functions have the same names throughout (for example, "Compare", "Save", "Copy link to this search"). |
| 3.3.3 Error Suggestion (Level AA) | Not Applicable | No input can be in error (see 3.3.1). |
| 3.3.4 Error Prevention (Legal, Financial, Data) (Level AA) | Not Applicable | No transactions, submissions or stored records. The saved list lives only in the reader's browser. |
| 3.3.8 Accessible Authentication (Minimum) (Level AA) | Not Applicable | No sign-in. |
| 4.1.3 Status Messages (Level AA) | Supports | The result count is a polite live region; the occupation and provider index filters announce how many rows match; turning analytics off or on announces the new state. Fixed on this branch: "Link copied" changed only the button's text, which is not announced, and now also goes to a status region; the "comparison is full" message used to arrive in a live region created at the same moment, which many screen readers skip, and that region is now always present. All of these use `role="status"` or `aria-live` in markup verified by tests; whether each is actually spoken has not been heard (Appendix A). |

### Table 3: Success Criteria, Level AAA

Not included in this report. The site's own AAA work is described in
[docs/wcag-2.2-aaa-conformance.md](../wcag-2.2-aaa-conformance.md).

## Changes made for this report

On branch `a11y/acr-2026-11`, each with a test that failed before the change:

1. **Reflow (1.4.10).** The search page no longer widens past a 320px screen
   (`web/app/globals.css`: grid items may shrink, and result-card controls wrap under a long
   name), and the CTDL page's term lists and bare web address now wrap. Gate:
   `web/scripts/a11y-rendered.mjs`, every page template in both languages at 320 CSS px.
2. **Keyboard-scrollable tables (2.1.1).** The ten tables with no link inside take keyboard
   focus, as regions named by their headings. Gates: axe `scrollable-region-focusable` at 320
   CSS px in the same script, and `focus-order-semantics` in `npm run a11y`.
3. **Focus not obscured (2.4.11).** The comparison tray reserves scroll space its own height
   (`web/components/Compare.tsx`). Tests: `web/components/Compare.a11y.test.tsx` and the
   keyboard walk in `web/scripts/a11y-rendered.mjs`.
4. **Non-text contrast (1.4.11).** Focus rings `--primary-60` → `--primary-80`; select and
   search-box borders `--gray-60` → `--gray-70`. Gate: `web/scripts/contrast-audit.mjs`, which
   now also fails if any ring or field-border colour in the stylesheet is unchecked.
5. **Status messages (4.1.3).** "Link copied" is announced; the comparison-limit message's live
   region is always present. Tests: `web/components/SearchApp.a11y.test.tsx`,
   `web/components/Compare.a11y.test.tsx`.
6. **Labels (2.4.6).** "+ 50" → "Show 50 more programs". Test:
   `web/components/SearchApp.a11y.test.tsx`.

## Appendix A: what a person still needs to check

About 2 to 3 hours for one tester who already uses the assistive technology. Use the live site
after this branch is deployed. In each step, the thing to listen or look for is in *italics*.

1. **VoiceOver with Safari on macOS** (about 45 minutes), English and then Spanish.
   - Home (`/en/`): Tab from the top. *The first stop is "Skip to main content"; pressing it lands
     in the main content.* Read the page with VO+A. *The not-affiliated notice is read before
     the masthead; Spanish pages read the machine-translation notice in Spanish with its
     English sentence in an English voice.*
   - Type a word in the search box. *The new result count is spoken once, politely, without
     reading the whole list.* Type a word that finds nothing. *"No programs match these filters." and the
     suggested filters are reachable and make sense.*
   - Tick "Compare" on four results. *Each is announced as a checkbox with the program's name
     and its state. On the fourth, "Comparison is full. Remove one to add another." is spoken.* Tab on. *The
     focused control is never hidden behind the dark tray at the bottom of the screen.*
   - Press "×" on a tray item. *Where does focus go, and is that somewhere sensible?* (This is
     the open 2.4.3 item.) Then "Clear".
   - Press "Save" on a result. *Announced as a toggle button, "pressed"/"not pressed".* Press
     "Copy a link to these" and "Copy link to this search". *"Link copied" is spoken.*
   - Press "Show N more programs". *The name is read in full; focus stays on the button or
     moves somewhere predictable.*
   - Open a program page. Use the rotor's headings list. *Headings form a sensible outline.*
     Move through the figures. *Each figure is read with its label; an unreported figure is
     read as "Not reported", never as zero or silence.* Find the wage table. *The chart above
     it is skipped and the table's row and column headers are read with each value.*
   - In the Spanish site, open the same program. *The program name and description are read
     in an English voice.*
2. **NVDA with Firefox on Windows** (about 45 minutes): repeat step 1, plus the occupation
   index's "Filter this list" box. *The count of matching rows is spoken after typing.* Open
   the comparison. *The table is announced with its dimensions; the best value in each row is
   identified in words.*
3. **Keyboard only, no screen reader, in Safari and Firefox** (about 20 minutes). *Every
   control shows a visible focus ring that you can find easily on white and on the grey filter
   panel* (1.4.11 for the browsers' own default rings). On a phone-width window (or 400% zoom),
   Tab to the tables on `/en/outcomes-coverage/` and `/en/ctdl/` and use the arrow keys. *The
   table scrolls sideways.* With a screen reader on, *each is announced as a region with the
   heading above it as its name.*
4. **TalkBack with Chrome on Android, or VoiceOver on iPhone** (about 30 minutes): the search,
   compare, save and program-page steps from 1, by swiping. *Every control can be reached and
   activated; the tray does not cover what has focus; nothing needs a two-finger gesture.*
5. **Text spacing and zoom in Safari** (about 10 minutes): zoom to 400% on the search page and
   a program page. *No sideways scrolling except inside tables; nothing overlaps.*

Record anything that fails as an issue with the accessibility template, naming the page, the
browser and the assistive technology.
