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
}: {
  label: string;
  value: string | null;
  note?: string;
  lang: Lang;
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
