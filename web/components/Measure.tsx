import { dict, type Lang } from "@/lib/i18n";

/*
 * TODO(i18n): `benchmarkPopulation` belongs in `web/lib/i18n.ts` beside every other
 * user-facing string, under exactly that name. It lives here only because that file was
 * owned by a concurrent change when this landed, and the alternative — leaving the statewide
 * median on screen with no visible statement of what it pools — is the defect this change
 * exists to remove. Both languages are complete so no page ships half-translated.
 *
 * `vsStateAbove` and `vsStateBelow` are now unused and should be deleted from `i18n.ts` in
 * the same pass. See the note on `Measure`'s `benchmark` prop for why.
 */
const BENCHMARK_POPULATION: Record<Lang, string> = {
  en:
    "That median pools every California program that reported this measure, whatever its " +
    "length, credential, or field, and leaves out the ones that reported nothing. It is a " +
    "reference point, not a rating of this program.",
  es:
    "Esa mediana agrupa todos los programas de California que reportaron esta medida, sin " +
    "importar su duración, credencial o campo, y deja fuera los que no reportaron nada. Es " +
    "un punto de referencia, no una calificación de este programa.",
};

/**
 * The same measure as published for one named area, shown beneath the headline figure.
 *
 * `area` is the area's own name, not a translated label: it is the entire point of the line
 * that a reader can tell this number from the statewide one above it, and the only reliable
 * way to do that is to say whose number it is.
 *
 * `value` is `string | null` on the same terms as the headline: null is an empty cell inside
 * a row that does exist, and it renders as "Not reported" rather than disappearing. A local
 * wage the state declined to publish is itself worth seeing, and it is never a zero.
 */
export interface RegionalFigure {
  area: string;
  value: string | null;
  /** Longer explanation of where the figure comes from, for the title attribute. */
  title?: string;
  /**
   * Why a null `value` is missing. Defaults to the provider-reporting explanation used
   * everywhere else on the page, which would be wrong here: a blank regional cell is the
   * state's gap, not the training provider's, and blaming the provider for it would be a
   * small false accusation repeated on every page that has one.
   */
  unreportedTitle?: string;
}

/** Renders one regional line. Kept out of the branch below so both cases can use it. */
function Regional({ figure, lang }: { figure: RegionalFigure; lang: Lang }) {
  const t = dict(lang);
  return (
    // The headline's not-reported treatment italicises its whole `dd`; the regional line is
    // a separate claim and is set upright either way.
    <small title={figure.title} style={{ fontStyle: "normal" }}>
      {figure.area}:{" "}
      {figure.value === null ? (
        <span className="unreported" title={figure.unreportedTitle ?? t.notReportedLong}>
          {t.notReported}
        </span>
      ) : (
        figure.value
      )}
    </small>
  );
}

/**
 * A single measure, with the not-reported case handled once so no page can get it wrong.
 *
 * `value` is the already-formatted string, or null when the underlying measure was withheld
 * or never reported. Null renders as an explicit, italicised "Not reported" with a title
 * explaining why — never as 0, $0, 0%, or a bare dash.
 */
export function Measure({
  label,
  value,
  note,
  lang,
  benchmark,
  regional,
}: {
  label: string;
  value: string | null;
  note?: string;
  lang: Lang;
  /**
   * Optional statewide comparison. A rate on its own is unreadable — nobody knows whether
   * 45% employed is good — so where California publishes a statewide figure for the same
   * measure, it is shown next to the program's.
   *
   * `programBeatsState` is accepted and deliberately not rendered. It used to decide between
   * "Better than typical" and "Worse than typical" beside the figure, and that verdict has
   * been withdrawn: see the block comment above the rendering below. The field stays in the
   * type only so the program page keeps compiling; delete it from `compare()` in
   * `app/[lang]/programs/[id]/page.tsx` and from here in the same pass.
   *
   * `ownCohort` false drops the median line entirely, for the 98 programs whose provider
   * filed a cohort covering a whole institution or a group of sibling courses. Their own
   * figures still show — they are real — but setting a statewide per-program median beside
   * them is an invitation to a comparison the numbers cannot answer, and the invitation is
   * the assessment. Optional, and absent reads as attributable, only because the caller is
   * owned elsewhere: `compare()` in the program page should pass
   * `ownCohort: outcomes.cohort.attributable`, at which point this can become required.
   */
  benchmark?: { formatted: string; programBeatsState: boolean | null; ownCohort?: boolean };
  /**
   * Optional same-measure figure for the area this program sits in. Subordinate to the
   * headline on purpose: statewide stays the headline because graduates do not necessarily
   * work where they trained. It renders in both branches, since a suppressed statewide wage
   * is no reason to hide a published local one.
   */
  regional?: RegionalFigure;
}) {
  const t = dict(lang);
  return (
    <div className="measure">
      <dt>{label}</dt>
      {value === null ? (
        <dd className="unreported" title={t.notReportedLong}>
          {t.notReported}
          {regional ? <Regional figure={regional} lang={lang} /> : null}
        </dd>
      ) : (
        <dd>
          {value}
          {note ? <small>{note}</small> : null}
          {/*
            * The median, and what it pools. No adjective.
            *
            * This used to end in "Better than typical" or "Worse than typical", which is the
            * one place on the site that graded a named business, and it was not a
            * like-for-like comparison. The pool is every reporting California program,
            * unsegmented, and completion falls steadily with length in the shipped data:
            * 97% at four weeks or under (n=153), 91% at 5-12 (n=396), 85% at 13-26 (n=596),
            * 80% at 27-52 (n=588), 78% beyond a year (n=214). A 72-week college pathway was
            * therefore being judged against a median held up by short certificate courses.
            *
            * Segmenting the peer group instead would fix the arithmetic, and it is the right
            * long-term answer, but it changes nothing about three further problems with
            * printing a verdict at all. The measures are self-reported by the provider and
            * this project states plainly that it does not verify them (DISCLAIMER.md). The
            * pool is self-selected: a median over the programs willing to file a number is
            * not "typical". And 247 of the 1,563 pages carrying a "worse than typical" rest
            * on a cohort of 25 people or fewer, where the difference between 78% and 85% can
            * be two students. Against the pooled median, 88 programs were told they are
            * worse than typical while sitting at or above the median for their own length,
            * and 114 were told they are better while sitting at or below it — the verdict is
            * simply reversed for about one in ten of them.
            *
            * Cohort attributability, added since, removes a fourth: 98 of those pages carry
            * figures their provider filed against a whole institution. Withdrawing the
            * verdict outright covers those and the 1,465 others in the same stroke. The
            * median line that remains is still an invitation to compare, so it is suppressed
            * outright where the cohort is not the program's — see `benchmark.ownCohort`.
            *
            * So the figure and the median both stay, and the sentence that says what the
            * median is made of moves out of a `title` attribute — unreachable on a phone,
            * and the audit's finding was precisely that nobody hovers it — into visible
            * text. A reader can still draw the comparison. The site no longer draws it for
            * them on evidence that cannot carry it.
            */}
          {benchmark && benchmark.ownCohort !== false ? (
            <>
              <small>
                {t.vsState}: {benchmark.formatted}
              </small>
              <small>{BENCHMARK_POPULATION[lang]}</small>
            </>
          ) : null}
          {regional ? <Regional figure={regional} lang={lang} /> : null}
        </dd>
      )}
    </div>
  );
}

/** Compact variant for result cards. */
export function Fact({
  label,
  value,
  lang,
}: {
  label: string;
  value: string | null;
  lang: Lang;
}) {
  const t = dict(lang);
  return (
    <div className="fact">
      <dt>{label}</dt>
      {value === null ? (
        <dd className="unreported" title={t.notReportedLong}>
          {t.notReported}
        </dd>
      ) : (
        <dd>{value}</dd>
      )}
    </div>
  );
}
