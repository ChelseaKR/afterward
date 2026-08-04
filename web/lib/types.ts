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
 * How the join reached the occupation attached to a program.
 *
 * `"exact"` — the program's own SOC code is one California publishes, so every figure on the
 * occupation is that occupation's own.
 *
 * `"soc_broad_group"` — California publishes nothing for the program's code and reports that
 * work only inside its parent category in the occupation classification. The figures are the
 * parent's, over a population that *contains* the program's occupation and others besides.
 *
 * `"bls_hybrid_occupation"` — the same weaker claim, arrived at differently: the target is not
 * a classification code at all but a federal publication bucket, defined as the union of
 * several named occupations the federal statistics cannot estimate separately.
 *
 * The two aggregate kinds are not interchangeable with `"exact"`, and a consumer that cannot
 * tell them apart will present a wider group's numbers as though they described the one job
 * the program trains for. Anything rendering these figures has to say which it is showing.
 */
export type MatchKind = "exact" | "soc_broad_group" | "bls_hybrid_occupation";

/**
 * The provenance of one program-to-occupation attachment, written on every attachment.
 *
 * `entry_level_education_withheld` separates two absences that would otherwise both arrive as
 * a null `entry_level_education` and mean opposite things. True means California *did* publish
 * a typical-entry credential and this project declined to attach it, because a credential
 * assigned to a union of occupations is a different answer rather than an approximate one —
 * a master's degree read off a mental-health-counsellor aggregate is simply wrong about a
 * community-college substance-use certificate. False means there was nothing published to
 * attach. Only the second is the provider's silence, and the withheld case must never borrow
 * the interface's "not reported" explanation.
 */
export interface OccupationMatch {
  kind: MatchKind;
  /** The program's own codes that landed on this occupation, so the claim can be audited. */
  program_soc_codes: string[];
  entry_level_education_withheld: boolean;
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
 *
 * `match` is required rather than optional for the same reason. The pipeline writes it on
 * every attachment without exception, and making it optional here would let a page reach for
 * the figures while skipping the one field that says how much they are worth.
 */
export interface ProgramOccupation extends OccupationSummary {
  region: OccupationRegion | null;
  match: OccupationMatch;
}

/**
 * One skill O*NET associates with an occupation, as served by CareerOneStop (PROVENANCE D6).
 *
 * `importance` is the rating exactly as published, and null means the source rated the skill
 * for this occupation without giving a number — absence of a rating, never a rating of zero.
 * A zero would rank the skill below every skill genuinely judged unimportant, which is the
 * same collapse this file exists to prevent for wages and openings.
 *
 * The number arrives with no scale attached: the record says `4.12` and nothing about what
 * 4.12 is out of. Consumers can therefore honour the *order* the ratings give but must not
 * present the figure as a score, a percentage, or a proportion of any maximum.
 */
export interface OccupationSkill {
  name: string;
  importance: number | null;
}

/**
 * An occupation O*NET's own related-occupation list names for this one.
 *
 * The pipeline keeps only entries this dataset can open a page for, so every row here is a
 * live link rather than a title with nothing behind it.
 */
export interface OnetRelatedOccupation {
  soc_code: string;
  title: string;
}

/**
 * How `Occupation.related` was arrived at. The two are different claims, not two routes to
 * the same one, and anything rendering the list has to say which it is showing.
 *
 * `"onet"` — O*NET's own list: a judgement about the work itself, that someone doing this
 * job could plausibly do that one. Kept in O*NET's order, which is its relevance ranking.
 *
 * `"soc_major_group"` — occupations whose SOC code starts with the same two digits. That is
 * a statement about how the classification files the work, not about the work, and it is the
 * weaker of the two. Ordered by projected openings.
 *
 * Null when neither source produced a list, in which case `related` is empty.
 */
export type RelatedSource = "onet" | "soc_major_group";

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
  /**
   * Plain-language account of what the work is, from the federal source. Null for the
   * occupations that source has no entry for; the key is always written, so "no description
   * published" and "this record predates the field" stay distinguishable.
   */
  description: string | null;
  /** Most important first, as the pipeline sorts them. Empty when none were published. */
  skills: OccupationSkill[];
  related_onet: OnetRelatedOccupation[];
  /**
   * The U.S. Department of Labor's Bright Outlook designation, e.g. "Rapid Growth" or
   * "Rapid Growth; Numerous Job Openings". Null means the Department did not designate this
   * occupation — which is not the same as designating it poorly. It rests on *national*
   * projections, so it can disagree with the California figures beside it, and it is the
   * Department's assessment rather than this project's.
   */
  bright_outlook: string | null;
  related_source: RelatedSource | null;
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
  /**
   * Short name of the published EDD labour-market area this program's city sits in
   * ("Fresno MSA"), or null when California's own area titles name no such city.
   *
   * Null means unplaced, which is a third state distinct from both "not reported" and any
   * area — 1,741 of 3,266 programs are in it. An unplaced program is never attributed to a
   * nearby area, however obvious the geography looks.
   */
  a: string | null;
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
