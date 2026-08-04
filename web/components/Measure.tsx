import { dict, type Lang } from "@/lib/i18n";

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
}) {
  const t = dict(lang);
  return (
    <div className="measure">
      <dt>{label}</dt>
      {value === null ? (
        <dd className="unreported" title={t.notReportedLong}>
          {t.notReported}
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
