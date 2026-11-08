export interface Job {
  job_uuid: string
  title: string
  company_name: string | null
  location: string | null
  job_url: string | null
  last_seen_at?: string
  skills?: string[]
  interactions?: string[]
}

/** Full job details from GET /api/jobs/:uuid (for prefetch & detail page) */
export interface JobDetail {
  job_uuid: string
  title: string
  company_name: string | null
  location: string | null
  job_url: string | null
  is_active?: boolean
  first_seen_at?: string
  last_seen_at?: string
  skills?: string[]
}

export interface Match {
  job_uuid: string
  title: string
  company_name: string | null
  location: string | null
  job_url: string | null
  similarity_score: number
  semantic_score?: number
  skills_overlap_score?: number
  matched_skills?: string[]
  job_skills?: string[]
  last_seen_at?: string
  role_cluster?: number | null
  role_name?: string | null
  predicted_tier?: string | null
  role_clusters?: number[] | null
  salary_min?: number | null
  salary_max?: number | null
}

export interface TopCompany {
  name: string
  active_count: number
}

export interface CompanyJob {
  job_uuid: string
  title: string
  salary_min: number | null
  salary_max: number | null
  first_seen_at: string | null
  last_seen_at: string
  employment_types: string[]
  position_levels: string[]
  min_years_experience: number | null
  inferred_seniority: string | null
  job_url: string | null
}

export interface CompanyProfile {
  company_name: string
  active_count: number
  total_count: number
  salary_p25: number | null
  salary_p50: number | null
  salary_p75: number | null
  salary_sample_size: number
  avg_min_experience: number | null
  position_levels: Record<string, number>
  employment_types: Record<string, number>
  top_skills: [string, number][]
  active_jobs: CompanyJob[]
  recent_closed: CompanyJob[]
  // SGSAL-026 (absent on older cached responses)
  stats?: CompanyStatsRow | null
  top_reposted?: CompanyReposted[]
}

// --- Company stats (SGSAL-026) ---

export interface CompanyStatsRow {
  company_key: string
  company: string
  active_count: number
  distinct_postings: number
  reposted_count: number
  multi_company_count: number
  max_repost_count: number
  median_salary: number | null
  salary_sample: number
  role_family_counts: Record<string, number>
  family_count: number
  top_family: string | null
  category_counts: Record<string, number>
  total_seen: number
  first_seen: string | null
  last_seen: string | null
  likely_agency: boolean
  family_active_count: number | null
}

export interface CompanyStatsSummary {
  companies: number
  openings: number
  median_salary: number | null
}

export interface CompanyStatsResponse {
  rows: CompanyStatsRow[]
  total_matching: number
  summary: CompanyStatsSummary
}

export interface CompanyReposted {
  canonical_job_uuid: string
  title: string | null
  repost_count: number
  reposts_365d: number
  distinct_companies: number
  first_posted: string | null
  last_posted: string | null
  latest_salary_min: number | null
  latest_salary_max: number | null
}

export type CompanyAgencyFilter = 'all' | 'direct' | 'agency'
export type CompanyStatsSort = 'openings' | 'repost_rate' | 'median_salary'

export interface CompanyStatsParams {
  family?: string
  category?: string
  q?: string
  agency?: CompanyAgencyFilter
  min_active?: number
  sort?: CompanyStatsSort
  limit?: number
}

export interface Profile {
  user_id: string
  profile: any
  resume_path: string
  resume_exists: boolean
}

export interface DiscoverStats {
  interested: number
  not_interested: number
  unrated: number
  total_rated: number
}

export type InteractionType =
  | 'viewed'
  | 'dismissed'
  | 'applied'
  | 'saved'
  | 'interested'
  | 'not_interested'

export type MatchMode = 'resume' | 'taste'

export interface SimilarJob {
  job_uuid: string
  title: string
  company_name: string | null
  location: string | null
  job_url: string | null
  salary_min: number | null
  salary_max: number | null
  similarity_score: number
  is_active?: boolean
  description?: string | null
  min_years_experience?: number | null
  inferred_seniority?: string | null
  canonical_skills?: string[] | null
  // SGSAL-024 posting group facts (absent on older API responses)
  canonical_job_uuid?: string
  repost_count?: number
  active_count?: number
  first_posted?: string | null
  last_posted?: string | null
  reposts_365d?: number
  distinct_companies?: number
  min_salary_seen?: number | null
  max_salary_seen?: number | null
}

export interface HotJob {
  job_uuid: string
  title: string | null
  company_name: string | null
  salary_min: number | null
  salary_max: number | null
  above_market_pct: number | null
  job_url: string | null
  cluster_label: string | null
  categories: string[]
  position_levels: string[]
  inferred_seniority: string | null
  canonical_skills: string[] | null
  posted_date: string | null
}

export interface HotJobsResponse {
  jobs: HotJob[]
  count: number
}

export interface SalarySearchJob {
  job_uuid: string
  title: string
  company_name: string | null
  location: string | null
  job_url: string | null
  salary_min: number | null
  salary_max: number | null
  similarity_score: number
  last_seen_at?: string | null
}

export interface SalarySearchResult {
  jobs: SalarySearchJob[]
  total: number
  market_p25: number | null
  market_p50: number | null
  market_p75: number | null
  salary_coverage: number
}

export interface LowballResult {
  verdict: 'lowballed' | 'below_median' | 'at_median' | 'above_median' | 'insufficient_data' | 'market_data'
  offered_salary: number | null
  percentile: number | null
  market_p25: number | null
  market_p50: number | null
  market_p75: number | null
  salary_coverage: number
  total_matched: number
  similar_jobs: SimilarJob[]
  company_similar_jobs?: SimilarJob[] | null
  total_listings?: number | null
}

// --- Posting groups / reposts (SGSAL-024) ---

export interface PostingOccurrence {
  job_uuid: string
  date: string | null
  company: string | null
  salary_min: number | null
  salary_max: number | null
  is_active: boolean
}

export interface PostingHistory {
  canonical_job_uuid: string
  title: string | null
  repost_count: number
  active_count: number
  first_posted: string | null
  last_posted: string | null
  reposts_90d: number
  reposts_365d: number
  distinct_companies: number
  latest_salary_min: number | null
  latest_salary_max: number | null
  min_salary_seen: number | null
  max_salary_seen: number | null
  occurrences: PostingOccurrence[]
}

export interface MostRepostedRow {
  canonical_job_uuid: string
  title: string | null
  company: string | null
  distinct_companies: number
  repost_count: number
  reposts_in_window: number
  first_posted: string | null
  last_posted: string | null
  latest_salary_min: number | null
  latest_salary_max: number | null
}

// --- Dashboard: LLM-field analytics (seniority / skills / role families) ---

export interface SeniorityBreakdownRow {
  seniority: string
  jobs: number
  median_salary: number | null
}

export interface TopSkillRow {
  skill: string
  jobs: number
  median_salary: number | null
}

export interface SkillsTrendRow {
  /** ISO date of the Monday starting the week */
  week: string
  skill: string
  jobs: number
}

export interface RoleFamilyRow {
  role_family: string
  display_name: string
  jobs: number
  median_salary: number | null
}
