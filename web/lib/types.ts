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

export interface Occupation extends OccupationSummary {
  period: string | null;
  median_hourly_wage: number | null;
  numeric_change: number | null;
  base_employment: number | null;
  projected_employment: number | null;
  work_experience: string | null;
  job_training: string | null;
  regions: RegionalProjection[];
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
  length: { weeks: number | null; hours: number | null };
  cost: {
    tuition: number | null;
    supplies: number | null;
    total_out_of_pocket: number | null;
    wioa_funded_cost: number | null;
  };
  outcomes: ProgramOutcomes;
  occupations: OccupationSummary[];
}

/** Compact search-index row. Keys are short because this file ships to every visitor. */
export interface SearchEntry {
  i: string;
  n: string | null;
  p: string | null;
  c: string | null;
  $: number | null;
  w: number | null;
  s: string[];
  o: string | null;
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

export interface Coverage {
  snapshot_date: string;
  state_benchmark: StateBenchmark | null;
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
