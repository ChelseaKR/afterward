import { dict, type Lang } from "@/lib/i18n";

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
   */
  benchmark?: { formatted: string; programBeatsState: boolean | null };
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
          {benchmark ? (
            <small title={t.benchmarkNote}>
              {t.vsState}: {benchmark.formatted}
              {benchmark.programBeatsState !== null && (
                <>
                  {" · "}
                  {benchmark.programBeatsState ? t.vsStateAbove : t.vsStateBelow}
                </>
              )}
            </small>
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
