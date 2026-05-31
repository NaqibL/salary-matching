import type { Profile, Match, Job, JobDetail, DiscoverStats, MatchMode, LowballResult, SimilarJob, SalarySearchResult, CompanyProfile, TopCompany } from './types'
import { supabase } from './supabase'

export type { Profile, Match, Job, JobDetail, DiscoverStats, MatchMode, LowballResult, SimilarJob, SalarySearchResult, CompanyProfile, TopCompany }

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

if (typeof window !== 'undefined' && !process.env.NEXT_PUBLIC_API_URL) {
  console.warn('[API] NEXT_PUBLIC_API_URL not set — using localhost. Set it in Vercel for production.')
}

type Params = Record<string, string | number | boolean | null | undefined>

async function apiFetch<T>(
  path: string,
  options: { method?: 'GET' | 'POST'; params?: Params; body?: unknown } = {}
): Promise<T> {
  const { method = 'GET', params, body } = options

  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  let url = `${API_BASE_URL}${path}`
  if (params) {
    const qs = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) {
      if (v != null) qs.append(k, String(v))
    }
    const s = qs.toString()
    if (s) url += `?${s}`
  }

  const res = await fetch(url, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw Object.assign(new Error(err.detail || res.statusText), {
      response: { status: res.status, data: err },
    })
  }

  return res.json()
}

// Jobs API
export const jobsApi = {
  getJobDetail: async (jobUuid: string) =>
    apiFetch<JobDetail>(`/api/jobs/${jobUuid}`),

  getInterested: async () =>
    apiFetch<{ jobs: Match[] }>('/api/jobs/interested'),

  markInteraction: async (jobUuid: string, interactionType: string) => {
    const result = await apiFetch<unknown>(`/api/jobs/${jobUuid}/interact`, {
      method: 'POST',
      params: { interaction_type: interactionType },
    })
    await revalidateMatches()
    return result
  },
}

// Profile API
export const profileApi = {
  get: async () =>
    apiFetch<Profile>('/api/profile'),

  processResume: async () => {
    const result = await apiFetch<unknown>('/api/profile/process-resume', { method: 'POST' })
    await revalidateMatches()
    return result
  },

  uploadResume: async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)

    const { data } = await supabase.auth.getSession()
    const token = data.session?.access_token
    const headers: Record<string, string> = {}
    if (token) headers['Authorization'] = `Bearer ${token}`

    // Don't set Content-Type — browser sets multipart/form-data with boundary
    const res = await fetch(`${API_BASE_URL}/api/profile/upload-resume`, {
      method: 'POST',
      body: formData,
      headers,
    })
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}))
      throw Object.assign(new Error(errBody.detail || res.statusText), {
        response: { status: res.status, data: errBody },
      })
    }
    const result = await res.json()
    await revalidateMatches()
    return result
  },

  computeTaste: async () => {
    const result = await apiFetch<{ ok: boolean; interested: number; not_interested: number; rated_count: number }>(
      '/api/profile/compute-taste',
      { method: 'POST' }
    )
    await revalidateMatches()
    return result
  },

  resetRatings: async () =>
    apiFetch<{ interactions_deleted: number; taste_deleted: number; matches_deleted: number }>(
      '/api/profile/reset-ratings',
      { method: 'POST' }
    ),
}

// Matches API — uses Next.js /api/matches route with 15min cache (user_id + mode).
// Cache invalidated on resume update or job rating via revalidateMatches().
export const matchesApi = {
  get: async (
    mode: MatchMode = 'resume',
    excludeInteracted = true,
    topK = 25,
    offset = 0,
    maxDaysOld?: number,
    excludeRatedOnly = true,
    sessionId?: string,
    roleClusters?: number[],
    predictedTiers?: string[],
  ) => {
    const params = new URLSearchParams({
      mode,
      exclude_interacted: excludeInteracted.toString(),
      top_k: topK.toString(),
      offset: offset.toString(),
    })
    if (excludeRatedOnly) params.append('exclude_rated_only', 'true')
    if (maxDaysOld != null && !Number.isNaN(maxDaysOld) && maxDaysOld > 0) {
      params.append('max_days_old', maxDaysOld.toString())
    }
    if (sessionId) params.append('session_id', sessionId)
    roleClusters?.forEach((c) => params.append('role_cluster', c.toString()))
    predictedTiers?.forEach((t) => params.append('predicted_tier', t))

    const { data } = await supabase.auth.getSession()
    const token = data.session?.access_token
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`

    const res = await fetch(`/api/matches?${params}`, { headers })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw Object.assign(new Error(err.detail || err.error || res.statusText), {
        response: { status: res.status, data: err },
      })
    }
    return res.json() as Promise<{
      matches: Match[]
      total: number
      has_more: boolean
      mode: MatchMode
      session_id: string
      candidate_tier: string | null
    }>
  },
}

// Taxonomy API — proxied through Next.js to avoid direct browser→backend calls
export const taxonomyApi = {
  getClusters: async (): Promise<Array<{ id: number; name: string }>> => {
    const res = await fetch('/api/taxonomy')
    if (!res.ok) return []
    const data = await res.json()
    return data.clusters ?? []
  },
}

/** Invalidate matches cache for current user. Call after resume update or job rating. */
export async function revalidateMatches(): Promise<void> {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  if (!token) return
  await fetch('/api/revalidate-matches', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  }).catch(() => {}) // non-fatal
}

// Discover API
export const discoverApi = {
  getStats: async () =>
    apiFetch<DiscoverStats>('/api/discover/stats'),
}

// Dashboard API
export const dashboardApi = {
  getSummary: async () => {
    const res = await fetch('/api/dashboard/summary')
    if (!res.ok) throw new Error('Failed to fetch dashboard summary')
    return res.json() as Promise<{
      total_jobs: number
      active_jobs: number
      active_jobs_total: number
      inactive_jobs: number
      by_source: Record<string, number>
      jobs_with_embeddings: number
      inactive_jobs_with_embeddings: number
      jobs_needing_backfill: number
    }>
  },
  getSummaryPublic: async () =>
    apiFetch<{
      total_jobs: number
      active_jobs: number
      active_jobs_total: number
      inactive_jobs: number
      by_source: Record<string, number>
      jobs_with_embeddings: number
      jobs_needing_backfill: number
    }>('/api/dashboard/summary-public'),

  getJobsOverTimePostedAndRemoved: async (limitDays = 90) => {
    const res = await fetch(`/api/dashboard/jobs-over-time-posted-and-removed?limit_days=${limitDays}`)
    if (!res.ok) throw new Error('Failed to fetch jobs over time')
    return res.json() as Promise<Array<{ date: string; added_count: number; removed_count: number }>>
  },
  getActiveJobsOverTime: async (limitDays = 90) => {
    const res = await fetch(`/api/dashboard/active-jobs-over-time?limit_days=${limitDays}`)
    if (!res.ok) throw new Error('Failed to fetch active jobs over time')
    return res.json() as Promise<Array<{ date: string; active_count: number }>>
  },
  getActiveJobsOverTimePublic: async (limitDays = 30) =>
    apiFetch<Array<{ date: string; active_count: number }>>(
      '/api/dashboard/active-jobs-over-time-public',
      { params: { limit_days: limitDays } }
    ),
  getJobsByCategory: async (limitDays = 90, limit = 30) => {
    const res = await fetch(`/api/dashboard/jobs-by-category?limit_days=${limitDays}&limit=${limit}`)
    if (!res.ok) throw new Error('Failed to fetch jobs by category')
    return res.json() as Promise<Array<{ category: string; count: number }>>
  },
  getJobsByCategoryPublic: async (limitDays = 30, limit = 8) =>
    apiFetch<Array<{ category: string; count: number }>>(
      '/api/dashboard/jobs-by-category-public',
      { params: { limit_days: limitDays, limit } }
    ),
  getCategoryTrends: async (category: string, limitDays = 90) =>
    apiFetch<Array<{ date: string; active_count: number; added_count: number; removed_count: number }>>(
      '/api/dashboard/category-trends',
      { params: { category, limit_days: limitDays } }
    ),
  getCategoryStats: async (category: string) =>
    apiFetch<{
      active_count: number
      top_employment_type: string | null
      top_position_level: string | null
      avg_salary: number | null
      employment_types: Array<{ employment_type: string; count: number }>
      position_levels: Array<{ position_level: string; count: number }>
      salary_buckets: Array<{ bucket: string; count: number }>
    }>('/api/dashboard/category-stats', { params: { category } }),
  getJobsByEmploymentType: async (limitDays = 90, limit = 20) => {
    const res = await fetch(`/api/dashboard/jobs-by-employment-type?limit_days=${limitDays}&limit=${limit}`)
    if (!res.ok) throw new Error('Failed to fetch jobs by employment type')
    return res.json() as Promise<Array<{ employment_type: string; count: number }>>
  },
  getJobsByPositionLevel: async (limitDays = 90, limit = 20) => {
    const res = await fetch(`/api/dashboard/jobs-by-position-level?limit_days=${limitDays}&limit=${limit}`)
    if (!res.ok) throw new Error('Failed to fetch jobs by position level')
    return res.json() as Promise<Array<{ position_level: string; count: number }>>
  },
  getSalaryDistribution: async () => {
    const res = await fetch('/api/dashboard/salary-distribution')
    if (!res.ok) throw new Error('Failed to fetch salary distribution')
    return res.json() as Promise<Array<{ bucket: string; count: number }>>
  },
  getChartsStatic: async () => {
    const res = await fetch('/api/dashboard/charts-static')
    if (!res.ok) throw new Error('Failed to fetch static chart data')
    return res.json() as Promise<{
      jobs_by_category: Array<{ category: string; count: number }>
      jobs_by_employment_type: Array<{ employment_type: string; count: number }>
      jobs_by_position_level: Array<{ position_level: string; count: number }>
      salary_distribution: Array<{ bucket: string; count: number }>
    }>
  },
}

export const lowballApi = {
  check: async (
    title: string,
    description: string,
    salary?: number,
    companyName?: string,
    topK = 20,
  ): Promise<LowballResult> => {
    const { data } = await supabase.auth.getSession()
    const token = data.session?.access_token
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`

    const res = await fetch('/api/lowball/check', {
      method: 'POST',
      headers,
      body: JSON.stringify({
        title,
        description,
        salary: salary ?? null,
        company_name: companyName ?? null,
        top_k: topK,
      }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Lowball check failed')
    }
    return res.json()
  },
}

export const companiesApi = {
  list: async (): Promise<string[]> => {
    const res = await fetch('/api/companies')
    if (!res.ok) return []
    return res.json()
  },

  aliases: async (): Promise<Record<string, string>> => {
    const res = await fetch('/api/companies/aliases')
    if (!res.ok) return {}
    return res.json()
  },

  getPopular: async (limit = 20): Promise<TopCompany[]> => {
    const res = await fetch(`/api/companies/popular?limit=${limit}`)
    if (!res.ok) return []
    return res.json()
  },

  getProfile: async (name: string): Promise<CompanyProfile> => {
    const res = await fetch(`/api/company/${encodeURIComponent(name)}`)
    if (!res.ok) throw new Error(`Company not found: ${name}`)
    return res.json()
  },
}

export const salaryApi = {
  search: async (
    title: string,
    description: string,
    salaryMin?: number,
    salaryMax?: number,
    topK = 25,
    offset = 0,
  ): Promise<SalarySearchResult> => {
    const { data } = await supabase.auth.getSession()
    const token = data.session?.access_token
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`

    const res = await fetch(`${API_BASE_URL}/api/salary/search`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        title,
        description,
        salary_min: salaryMin ?? null,
        salary_max: salaryMax ?? null,
        top_k: topK,
        offset,
      }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Salary search failed')
    }
    return res.json()
  },
}

/** Supabase RPC API — use when DB is Supabase Postgres (migration 006).
 * Bypasses FastAPI. See docs/SUPABASE_RPC.md */
export const supabaseRpcApi = {
  getDashboardSummary: async () => {
    const { data, error } = await supabase.rpc('get_dashboard_summary')
    if (error) throw error
    return data as {
      total_jobs: number
      active_jobs: number
      active_jobs_total: number
      inactive_jobs: number
      by_source: Record<string, number>
      jobs_with_embeddings: number
      jobs_needing_backfill: number
    }
  },

  getActiveJobsForMatching: async (userId: string, limit = 5000) => {
    const { data, error } = await supabase.rpc('get_active_jobs_for_matching', {
      p_user_id: userId,
      p_limit: limit,
    })
    if (error) throw error
    return (data ?? []).map((r: { job_uuid: string }) => r.job_uuid)
  },
}
