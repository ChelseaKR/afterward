/**
 * Shapes emitted by the Python pipeline (see src/camino/build.py).
 *
 * Every outcome number is `number | null`. Null means the measure was withheld or never
 * reported, which is not the same as zero, and the type system is the first line of defence
 * against collapsing that distinction.
 */

export interface OccupationSummary {
  soc_code: string | null;
  title: string | null;
  median_annual_wage: number | null;
  total_job_openings: number | null;
  percent_change: number | null;
  entry_level_education: string | null;
}

export interface RegionalProjection extends OccupationSummary {
  area_type: string | null;
  area_name: string | null;
  median_hourly_wage: number | null;
}

/**
 * The published EDD area a program's city was placed in.
 *
 * `Program.region` is `ProgramArea | null`, and the null is load-bearing: it means the city
 * is not one EDD names, so no regional figure is claimed for this program anywhere. It does
 * not mean "statewide", and it does not mean "region unknown but probably nearby". Roughly
 * half of California's programs are in that state, so consumers must render it rather than
 * treat it as an edge case.
 */
export interface ProgramArea {
  area_name: string | null;
  /** The area title without its county gloss, for labelling a figure inline. */
  area_short_name: string | null;
  area_type: string | null;
  /** How the area was decided, emitted so the claim can be audited rather than trusted. */
  matched_on: string | null;
}

/**
 * One occupation's own published row for the single area its program sits in.
 *
 * Reached as `ProgramOccupation.region`, and null there is a *different* fact from a null
 * `Program.region`: the area is known, but EDD publishes no row for this occupation in it.
 * Both are distinct again from a row that exists with a null measure inside it, which is a
 * figure withheld or suppressed. None of the three is zero.
 */
export interface OccupationRegion {
  area_name: string | null;
  area_type: string | null;
  median_annual_wage: number | null;
  median_hourly_wage: number | null;
  total_job_openings: number | null;
  percent_change: number | null;
}

export interface RelatedOccupation {
  soc_code: string | null;
  title: string | null;
  median_annual_wage: number | null;
  total_job_openings: number | null;
  percent_change: number | null;
}

/**
 * An occupation as embedded in a program record.
 *
 * The inherited figures stay statewide by design: a program's graduates do not necessarily
 * work in the county where they trained. `region` carries the one area row that applies to
 * the program carrying it, so a page can show both and say which is which.
 *
 * Deliberately not folded into `OccupationSummary`: the rows in `Occupation.regions` share
 * that base and have no `region` of their own, and giving them a field the pipeline never
 * writes would be a lie the compiler then enforces.
 */
export interface ProgramOccupation extends OccupationSummary {
  region: OccupationRegion | null;
}

export interface Occupation extends OccupationSummary {
  period: string | null;
  median_hourly_wage: number | null;
  numeric_change: number | null;
  base_employment: number | null;
  projected_employment: number | null;
  work_experience: string | null;
  job_training: string | null;
  regions: RegionalProjection[];
  related: RelatedOccupation[];
}

export interface ProgramOutcomes {
  total_served: number | null;
  total_exited: number | null;
  total_completed: number | null;
  completion_rate: number | null;
  credentials_earned: number | null;
  median_earnings: number | null;
  employment_rate_q2: number | null;
  employed_q2: number | null;
  employed_q4: number | null;
  reported: boolean;
}

export interface Program {
  uuid: string;
  provider_name: string | null;
  program_name: string | null;
  description: string | null;
  program_format: string | null;
  program_url: string | null;
  entity_type: string | null;
  cip_code: string | null;
  soc_codes: string[];
  location: {
    city: string | null;
    state: string | null;
    zip: string | null;
    lat: number | null;
    lon: number | null;
  };
  /** Null when this program's city could not be placed in a published EDD area. */
  region: ProgramArea | null;
  length: { weeks: number | null; hours: number | null };
  cost: {
    tuition: number | null;
    supplies: number | null;
    total_out_of_pocket: number | null;
    total_is_complete: boolean;
    wioa_funded_cost: number | null;
  };
  outcomes: ProgramOutcomes;
  occupations: ProgramOccupation[];
}

/** Compact search-index row. Keys are short because this file ships to every visitor. */
export interface SearchEntry {
  i: string;
  n: string | null;
  p: string | null;
  c: string | null;
  $: number | null;
  /** True when a cost component was suppressed, making `$` a floor rather than a total. */
  $partial: boolean;
  w: number | null;
  s: string[];
  o: string[];
  g: number | null;
  wage: number | null;
  op: number | null;
  cr: number | null;
  er: number | null;
  me: number | null;
  r: boolean;
}

export interface SearchIndex {
  snapshot_date: string;
  state: string;
  programs: SearchEntry[];
}

export interface StateBenchmark {
  state: string;
  completion_rate: number | null;
  employment_rate_q2: number | null;
  median_earnings: number | null;
  credential_rate: number | null;
  total_exited: number | null;
  total_completed: number | null;
}

export interface PeerMedian {
  median: number | null;
  reporting: number;
}

export interface Coverage {
  snapshot_date: string;
  state_benchmark: StateBenchmark | null;
  /** Median of each measure across CA programs that reported it — the like-for-like peer. */
  peer_medians: Record<"completion_rate" | "employment_rate_q2" | "median_earnings", PeerMedian>;
  total_programs: number;
  programs_with_any_outcome: number;
  programs_with_median_earnings: number;
  programs_with_employment_rate: number;
  programs_with_completion_rate: number;
  programs_matched_to_occupation: number;
  distinct_providers: number;
  distinct_occupations_matched: number;
  outcome_coverage_pct: number;
  occupation_match_pct: number;
}
