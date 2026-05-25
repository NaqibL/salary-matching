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
}
