import Link from "next/link";
import { notFound } from "next/navigation";

import {
  gapRows,
  getCtdlCoverage,
  getCtdlValidation,
  findingRows,
  hasUnacceptedFindings,
  measureRows,
  propertyRows,
  severityCounts,
  snapshotAgreement,
  type Severity,
} from "@/lib/ctdl";
import { getCoverage } from "@/lib/data";
import { count, percent } from "@/lib/format";
import { LANGUAGES, type Copy, type Lang, dict, feedTextLang, isLang } from "@/lib/i18n";

export function generateStaticParams() {
  return LANGUAGES.map((lang) => ({ lang }));
}

export async function generateMetadata({ params }: { params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  if (!isLang(lang)) return {};
  const t = dict(lang);
  return { title: `${t.ctdlTitle} | ${t.siteName}`, description: t.ctdlLede };
}

const REPO = "https://github.com/ChelseaKR/afterward";
const RELEASES_URL = `${REPO}/releases`;
const ISSUES_URL = `${REPO}/issues`;
const EXPORT_SOURCE_URL = `${REPO}/blob/main/src/afterward/ctdl/export.py`;
const PROVENANCE_URL = `${REPO}/blob/main/PROVENANCE.md`;
const COVERAGE_STATEMENT_URL = "/ctdl/ctdl-coverage.json";
const VALIDATION_STATEMENT_URL = "/ctdl/ctdl-validation.json";

/**
 * The published definition each mapping decision rests on.
 *
 * Links to the primary text rather than a paraphrase of it, for the same reason the coverage
 * page links the regulations rather than summarising them: this is the part of the page a
 * reader cannot check against the data, so it has to be checkable against the source. English
 * only, because Credential Engine publishes it that way.
 */
const MAPPING_CITATIONS: { id: string; label: string; url: string }[] = [
  {
    id: "learning-program",
    label:
      "ceterms:LearningProgram — \"Set of learning opportunities that leads to an outcome, " +
      "usually a credential like a degree or certificate\". Every record here is a " +
      "state-listed training program; ceterms:Course is for a single structured sequence, " +
      "which the source does not distinguish, so it is never used",
    url: "https://credreg.net/ctdl/terms/LearningProgram",
  },
  {
    id: "offered-by",
    label:
      "ceterms:offeredBy — \"Agent that offers the resource\". Chosen over ceterms:ownedBy, " +
      "whose definition is an enforceable claim or legal title: the training list asserts " +
      "that a provider offers a program and says nothing about title",
    url: "https://credreg.net/ctdl/terms/offeredBy",
  },
  {
    id: "occupation-type",
    label:
      "ceterms:occupationType — a credential alignment whose usage note names SOC among the " +
      "expected frameworks. The alignment carries the code the source filed, and a title " +
      "only where this dataset matched that exact code",
    url: "https://credreg.net/ctdl/terms/occupationType",
  },
  {
    id: "estimated-cost",
    label:
      "ceterms:estimatedCost — a cost profile with a price and a currency. Emitted only " +
      "where the source total is complete, because a total with a suppressed component is a " +
      "floor and the price property cannot say \"at least\"",
    url: "https://credreg.net/ctdl/terms/estimatedCost",
  },
  {
    id: "relevant-dataset",
    label:
      "qdata:relevantDataSet — \"Data Set on which earnings or employment data is based\", " +
      "which names ceterms:LearningProgram in its own domain rather than relying on a " +
      "subclass relation",
    url: "https://credreg.net/qdata/terms/relevantDataSet",
  },
  {
    id: "metric",
    label:
      "qdata:Metric and qdata:Observation — what is being measured, and the value observed " +
      "for it. Counts carry a value, earnings carry a median with a currency, and rates " +
      "carry a percentage, which is why the source's 0–1 fractions are multiplied by 100",
    url: "https://credreg.net/qdata/terms/Metric",
  },
  {
    id: "ctid",
    label:
      "About the CTID — \"Each CTID is made up of a standard UUID v4 prefixed with ce-\". " +
      "This export uses a v5 so that re-exporting the same data reproduces the same " +
      "identifiers, which is the one thing a v4 cannot do, and publishes the warning that " +
      "results",
    url: "https://credreg.net/ctdl/ctid",
  },
  {
    id: "aggregate-data",
    label:
      "Schema-Development issue #1080, filed from this project: ceterms:aggregateData did " +
      "not list ceterms:LearningProgram. The maintainers' answer settled the design — the " +
      "Registry no longer accepts aggregateData for publishing, and the supported pattern " +
      "is the data-set profile this export now uses",
    url: "https://github.com/CredentialEngine/Schema-Development/issues/1080",
  },
];

const SEVERITY_LABELS: Record<Severity, keyof Copy> = {
  ERROR: "ctdlSeverityError",
  WARNING: "ctdlSeverityWarning",
  INFO: "ctdlSeverityInfo",
  UNVERIFIABLE: "ctdlSeverityUnverifiable",
};

/** The five projected measures, using the labels the outcomes-coverage page already carries. */
const MEASURE_LABELS: Record<string, keyof Copy> = {
  median_earnings: "coverageMeasureEarnings",
  credentials_earned: "coverageMeasureCredentials",
  employed_q2: "coverageMeasureEmployedQ2",
  completion_rate: "coverageMeasureCompletionRate",
  employment_rate_q2: "coverageMeasureEmploymentRate",
};

/** Each dropped source field's name and the reason it is dropped, both translated. */
const GAP_LABELS: Record<string, { label: keyof Copy; why: keyof Copy }> = {
  outcome_measures: { label: "ctdlGapOutcomeMeasures", why: "ctdlGapOutcomeMeasuresWhy" },
  program_length: { label: "ctdlGapProgramLength", why: "ctdlGapProgramLengthWhy" },
  program_format: { label: "ctdlGapProgramFormat", why: "ctdlGapProgramFormatWhy" },
  instructional_program_code: {
    label: "ctdlGapInstructionalProgramCode",
    why: "ctdlGapInstructionalProgramCodeWhy",
  },
  program_location: { label: "ctdlGapProgramLocation", why: "ctdlGapProgramLocationWhy" },
  provider_category: { label: "ctdlGapProviderCategory", why: "ctdlGapProviderCategoryWhy" },
  wioa_funded_cost: { label: "ctdlGapWioaFundedCost", why: "ctdlGapWioaFundedCostWhy" },
  occupation_projections: {
    label: "ctdlGapOccupationProjections",
    why: "ctdlGapOccupationProjectionsWhy",
  },
};

/**
 * A count of records, formatted for prose.
 *
 * Same helper and the same reasoning as the coverage and methodology pages: everything passed
 * here is the size of a set the export walked, so it is a number that is always present.
 */
function tally(value: number, lang: Lang): string {
  return count(value, lang) ?? String(value);
}

/** A share, or nothing at all where there was no denominator to divide by. */
function share(value: number | null, lang: Lang): string {
  return percent(value, lang) ?? "";
}

/**
 * What the CTDL export carries, what it drops, and what an outside validator made of it.
 *
 * This page exists because a mapping nobody can check is a claim rather than a demonstration.
 * Three things keep it honest, and all three are the same rules the rest of this site follows:
 *
 * 1. Every figure is read from a statement the export produced while it ran. Nothing here
 *    computes a number and nothing here types one, so the page cannot say something the
 *    export did not count.
 * 2. The omissions get the same treatment as the coverage. The export drops eight things the
 *    source record says, and each is counted, named, and paired with the CTDL term that would
 *    have carried it — so a reader can tell a limit of the vocabulary from a limit of this
 *    export, which is the distinction a coverage page is most tempted to blur.
 * 3. The validator's findings are published whichever way they came out, including the
 *    warning on every entity in the graph, and including the fact that the validator could
 *    not judge the outcome-statistics layer at all.
 *
 * And it says four times, near the top, that none of this has been published to the Credential
 * Registry — because a page full of correct-looking CTDL is exactly the thing somebody could
 * mistake for a registry record.
 */
export default async function CtdlPage({ params }: { params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();

  const t = dict(lang);
  const coverage = getCtdlCoverage();
  const validation = getCtdlValidation();
  const snapshots = snapshotAgreement(coverage.snapshot_date, getCoverage().snapshot_date);
  const scope = validation.validator_scope;
  const gaps = gapRows(coverage);
  const unaccepted = hasUnacceptedFindings(validation);

  /** The snapshot this export describes, restated beside every block of figures. */
  const stamp = <p className="compare-note">{t.ctdlStamp(coverage.snapshot_date)}</p>;

  const sections: { id: string; label: string }[] = [
    { id: "contains", label: t.ctdlCoverageHeading },
    { id: "not-carried", label: t.ctdlGapsHeading },
    { id: "validation", label: t.ctdlValidationHeading },
    { id: "mapping", label: t.ctdlMappingHeading },
    { id: "get", label: t.ctdlGetHeading },
    { id: "corrections", label: t.ctdlCiteHeading },
  ];

  return (
    <div className="shell detail about">
      <p>
        <Link href={`/${lang}/`} prefetch={false}>
          ← {t.backToSearch}
        </Link>
      </p>

      <h1>{t.ctdlTitle}</h1>
      <p className="lede">{t.ctdlLede}</p>
      <p>{t.ctdlWhy}</p>

      {/* The boundary statement, above everything it qualifies rather than below it. */}
      <h2 id="boundary">{t.ctdlBoundaryHeading}</h2>
      <ul className="limits panel">
        <li>{t.ctdlBoundaryRegistry}</li>
        <li>{t.ctdlBoundaryEndorsement}</li>
        <li>{t.ctdlBoundaryCtids}</li>
        <li>{t.ctdlBoundaryDemo}</li>
      </ul>

      {snapshots.agree ? null : (
        <p className="compare-note">
          {t.ctdlSnapshotMismatch(snapshots.exportSnapshot, snapshots.siteSnapshot)}
        </p>
      )}

      <h2 id="on-this-page">{t.onThisPage}</h2>
      <nav className="jump-nav" aria-label={t.ctdlTitle}>
        <ul>
          {sections.map((section) => (
            <li key={section.id}>
              <a href={`#${section.id}`}>{section.label}</a>
            </li>
          ))}
        </ul>
      </nav>

      <h2 id="contains">{t.ctdlCoverageHeading}</h2>
      <p>{t.ctdlCoverageIntro}</p>

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">{t.ctdlEntityColumn}</th>
              <th scope="col" style={{ textAlign: "right" }}>
                {t.ctdlEntityCountColumn}
              </th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(coverage.entities).map(([term, total]) => (
              <tr key={term}>
                <th scope="row" style={{ fontWeight: 400 }}>
                  <code>{term}</code>
                </th>
                <td className="num">{tally(total, lang)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {stamp}

      <h3>{t.ctdlPropertiesHeading}</h3>
      <p>{t.ctdlPropertiesIntro}</p>

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">{t.ctdlPropertyColumn}</th>
              <th scope="col" style={{ textAlign: "right" }}>
                {t.ctdlPropertyCountColumn}
              </th>
              <th scope="col" style={{ textAlign: "right" }}>
                {t.ctdlPropertyShareColumn}
              </th>
            </tr>
          </thead>
          <tbody>
            {propertyRows(coverage).map((row) => (
              <tr key={row.term}>
                <th scope="row" style={{ fontWeight: 400 }}>
                  <code>{row.term}</code>
                </th>
                {/* Counts over a set the export walked: a zero here is a real zero. */}
                <td className="num">{tally(row.count, lang)}</td>
                <td className="num">{share(row.share, lang)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {stamp}

      <h3>{t.ctdlMeasuresHeading}</h3>
      <p>{t.ctdlMeasuresIntro}</p>

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">{t.ctdlMeasureColumn}</th>
              <th scope="col" style={{ textAlign: "right" }}>
                {t.ctdlMeasureCountColumn}
              </th>
              <th scope="col" style={{ textAlign: "right" }}>
                {t.ctdlMeasureShareColumn}
              </th>
            </tr>
          </thead>
          <tbody>
            {measureRows(coverage).map((row) => {
              const label = MEASURE_LABELS[row.field];
              return (
                <tr key={row.field}>
                  <th scope="row" style={{ fontWeight: 400 }}>
                    {label === undefined ? <code>{row.field}</code> : (t[label] as string)}
                  </th>
                  <td className="num">{tally(row.count, lang)}</td>
                  <td className="num">{share(row.share, lang)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {stamp}

      <h2 id="not-carried">{t.ctdlGapsHeading}</h2>
      <p>{t.ctdlGapsIntro}</p>
      <p>{t.ctdlGapsReading}</p>

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">{t.ctdlGapColumn}</th>
              <th scope="col" style={{ textAlign: "right" }}>
                {t.ctdlGapProgramsColumn}
              </th>
              <th scope="col">{t.ctdlGapTermColumn}</th>
            </tr>
          </thead>
          <tbody>
            {gaps.map((gap) => {
              const labels = GAP_LABELS[gap.key];
              return (
                <tr key={gap.key}>
                  <th scope="row" style={{ fontWeight: 400 }}>
                    {labels === undefined ? <code>{gap.key}</code> : (t[labels.label] as string)}
                  </th>
                  <td className="num">{tally(gap.reported_in_source, lang)}</td>
                  <td>
                    {gap.ctdl_term === "" ? (
                      t.ctdlGapNoTerm
                    ) : (
                      <code lang={feedTextLang(lang)}>{gap.ctdl_term}</code>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {stamp}

      <ul className="limits">
        {gaps.map((gap) => {
          const labels = GAP_LABELS[gap.key];
          if (labels === undefined) return null;
          return (
            <li key={gap.key}>
              <strong>{t[labels.label] as string}.</strong> {t[labels.why] as string}
            </li>
          );
        })}
      </ul>
      <p>{t.ctdlCostFloor(tally(coverage.not_projected.cost_total_incomplete.reported_in_source, lang))}</p>

      <h2 id="validation">{t.ctdlValidationHeading}</h2>
      <p>{t.ctdlValidationIntro(validation.tool.name, validation.tool.version)}</p>
      <p>{t.ctdlValidationEntities(tally(validation.entities_validated, lang))}</p>

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">{t.ctdlValidationSeverityColumn}</th>
              <th scope="col" style={{ textAlign: "right" }}>
                {t.ctdlValidationCountColumn}
              </th>
            </tr>
          </thead>
          <tbody>
            {/* Every severity the validator defines, zeroes included. A table listing only
                what happened cannot be read as "no errors", only as "no errors mentioned". */}
            {severityCounts(validation).map((row) => (
              <tr key={row.severity}>
                <th scope="row" style={{ fontWeight: 400 }}>
                  {t[SEVERITY_LABELS[row.severity]] as string}
                </th>
                <td className="num">{tally(row.count, lang)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {stamp}

      <p>{unaccepted ? t.ctdlValidationUnaccepted : t.ctdlValidationResult}</p>

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">{t.ctdlFindingCodeColumn}</th>
              <th scope="col">{t.ctdlValidationSeverityColumn}</th>
              <th scope="col" style={{ textAlign: "right" }}>
                {t.ctdlFindingCountColumn}
              </th>
              <th scope="col" style={{ textAlign: "right" }}>
                {t.ctdlFindingEntitiesColumn}
              </th>
              <th scope="col">{t.ctdlFindingStateColumn}</th>
            </tr>
          </thead>
          <tbody>
            {findingRows(validation).map((row) => (
              <tr key={row.code}>
                <th scope="row" style={{ fontWeight: 400 }}>
                  <code lang={feedTextLang(lang)}>{row.code}</code>
                </th>
                <td>{t[SEVERITY_LABELS[row.severity as Severity]] as string}</td>
                <td className="num">{tally(row.count, lang)}</td>
                <td className="num">{tally(row.entities, lang)}</td>
                <td>{row.accepted ? t.ctdlFindingAccepted : t.ctdlFindingUnaccepted}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {stamp}
      <p>{t.ctdlFindingsNote}</p>

      <h3 id="scope">{t.ctdlScopeHeading}</h3>
      <p>
        {t.ctdlScopeBody(
          tally(scope.classes_in_validator_schema, lang),
          tally(scope.classes_emitted, lang),
          tally(scope.properties_in_validator_schema, lang),
          tally(scope.properties_emitted, lang),
        )}
      </p>
      <p>{t.ctdlScopeUnjudged}</p>
      <dl className="panel">
        <dt>{t.ctdlScopeClassesLabel}</dt>
        <dd>
          <code lang={feedTextLang(lang)}>
            {scope.classes_not_in_validator_schema.join(", ")}
          </code>
        </dd>
        <dt>{t.ctdlScopePropertiesLabel}</dt>
        <dd>
          <code lang={feedTextLang(lang)}>
            {scope.properties_not_in_validator_schema.join(", ")}
          </code>
        </dd>
      </dl>
      <p>{t.ctdlScopeCaveat}</p>

      <h2 id="mapping">{t.ctdlMappingHeading}</h2>
      <p>{t.ctdlMappingIntro}</p>
      <p className="compare-note">{t.ctdlMappingCitationsNote}</p>
      <ul className="limits">
        {MAPPING_CITATIONS.map((citation) => (
          <li key={citation.id}>
            <a href={citation.url} rel="noopener noreferrer" lang={feedTextLang(lang)}>
              {citation.label}
            </a>
          </li>
        ))}
      </ul>
      <p>
        <a href={EXPORT_SOURCE_URL} rel="noopener noreferrer">
          {t.ctdlExportSourceLink} →
        </a>
      </p>

      <h2 id="get">{t.ctdlGetHeading}</h2>
      <p>{t.ctdlGetIntro}</p>
      <p>{t.ctdlGetStatements}</p>
      <ul className="limits">
        <li>
          <a href={COVERAGE_STATEMENT_URL}>{t.ctdlGetCoverageFile}</a>
        </li>
        <li>
          <a href={VALIDATION_STATEMENT_URL}>{t.ctdlGetValidationFile}</a>
        </li>
      </ul>
      <p>{t.ctdlGetReproduce}</p>
      <p>
        {t.ctdlGetReleases}{" "}
        <a href={RELEASES_URL} rel="noopener noreferrer">
          {RELEASES_URL}
        </a>
      </p>
      <p>
        <a href={PROVENANCE_URL} rel="noopener noreferrer">
          {t.aboutProvenanceLink} →
        </a>
      </p>

      <h2 id="corrections">{t.ctdlCiteHeading}</h2>
      <p>{t.ctdlCiteBody}</p>
      <p>
        <a href={ISSUES_URL} rel="noopener noreferrer">
          {t.aboutCorrectionsLink} →
        </a>
      </p>

      <p className="browse-more">
        <Link href={`/${lang}/outcomes-coverage/`} prefetch={false}>
          {t.coverageTitle} →
        </Link>
      </p>
    </div>
  );
}
