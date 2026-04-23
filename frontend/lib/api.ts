import axios from 'axios'
import type { Profile, Match, Job, JobDetail, DiscoverStats, MatchMode, LowballResult, SimilarJob, SalarySearchResult } from './types'
import { supabase } from './supabase'

export type { Profile, Match, Job, JobDetail, DiscoverStats, MatchMode, LowballResult, SimilarJob, SalarySearchResult }

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// Debug: log API URL in dev (helps verify Vercel has NEXT_PUBLIC_API_URL set)
if (typeof window !== 'undefined' && !process.env.NEXT_PUBLIC_API_URL) {
  console.warn('[API] NEXT_PUBLIC_API_URL not set — using localhost. Set it in Vercel for production.')
}

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

// Attach the Supabase JWT (if present) to every outgoing request.
// When auth is disabled on the backend the header is simply ignored.
api.interceptors.request.use(async (config) => {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  if (token) {
    config.headers['Authorization'] = `Bearer ${token}`
  }
  // FormData needs multipart/form-data with boundary — let the browser set it
  if (config.data instanceof FormData) {
    delete config.headers['Content-Type']
  }
  return config
})

// Jobs API
export const jobsApi = {
  getJobDetail: async (jobUuid: string) => {
    const response = await api.get(`/api/jobs/${jobUuid}`)
    return response.data as JobDetail
  },

  getInterested: async () => {
    const response = await api.get('/api/jobs/interested')
    return response.data as { jobs: import('./types').Match[] }
  },

  markInteraction: async (jobUuid: string, interactionType: string) => {
    const response = await api.post(`/api/jobs/${jobUuid}/interact`, null, {
      params: { interaction_type: interactionType },
    })
    await revalidateMatches()
    return response.data
  },
}

// Profile API
export const profileApi = {
  get: async () => {
    const response = await api.get('/api/profile')
    return response.data as Profile
  },

  processResume: async () => {
    const response = await api.post('/api/profile/process-resume')
    await revalidateMatches()
    return response.data
  },

  uploadResume: async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)

    // Use fetch for FormData — axios was sending wrong Content-Type (application/x-www-form-urlencoded)
    // which caused ERR_NETWORK. Fetch correctly sets multipart/form-data with boundary.
    const { data } = await supabase.auth.getSession()
    const token = data.session?.access_token
    const headers: Record<string, string> = {}
    if (token) headers['Authorization'] = `Bearer ${token}`

    const res = await fetch(`${API_BASE_URL}/api/profile/upload-resume`, {
      method: 'POST',
      body: formData,
      headers,
      // Don't set Content-Type — browser sets multipart/form-data; boundary=...
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
    const response = await api.post('/api/profile/compute-taste')
    await revalidateMatches()
    return response.data as { ok: boolean; interested: number; not_interested: number; rated_count: number }
  },

  resetRatings: async () => {
    const response = await api.post('/api/profile/reset-ratings')
    return response.data as { interactions_deleted: number; taste_deleted: number; matches_deleted: number }
  },
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

// Taxonomy API
export const taxonomyApi = {
  getClusters: async (): Promise<Array<{ id: number; name: string }>> => {
    const response = await api.get('/api/jobs/taxonomy')
    return response.data.clusters
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
  getStats: async () => {
    const response = await api.get('/api/discover/stats')
    return response.data as DiscoverStats
  },
}

// Dashboard API
// getSummary and getJobsOverTimePostedAndRemoved use Next.js cached routes (/api/dashboard/*)
// for 1h stale-while-revalidate. Other endpoints hit FastAPI directly.
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
  getSummaryPublic: async () => {
    const response = await api.get('/api/dashboard/summary-public')
    return response.data as {
      total_jobs: number
      active_jobs: number
      active_jobs_total: number
      inactive_jobs: number
      by_source: Record<string, number>
      jobs_with_embeddings: number
      jobs_needing_backfill: number
    }
  },
  getJobsOverTimePostedAndRemoved: async (limitDays = 90) => {
    const res = await fetch(
      `/api/dashboard/jobs-over-time-posted-and-removed?limit_days=${limitDays}`
    )
    if (!res.ok) throw new Error('Failed to fetch jobs over time')
    return res.json() as Promise<Array<{
      date: string
      added_count: number
      removed_count: number
    }>>
  },
  getActiveJobsOverTime: async (limitDays = 90) => {
    const res = await fetch(`/api/dashboard/active-jobs-over-time?limit_days=${limitDays}`)
    if (!res.ok) throw new Error('Failed to fetch active jobs over time')
    return res.json() as Promise<Array<{ date: string; active_count: number }>>
  },
  getActiveJobsOverTimePublic: async (limitDays = 30) => {
    const response = await api.get('/api/dashboard/active-jobs-over-time-public', {
      params: { limit_days: limitDays },
    })
    return response.data as Array<{ date: string; active_count: number }>
  },
  getJobsByCategory: async (limitDays = 90, limit = 30) => {
    const res = await fetch(`/api/dashboard/jobs-by-category?limit_days=${limitDays}&limit=${limit}`)
    if (!res.ok) throw new Error('Failed to fetch jobs by category')
    return res.json() as Promise<Array<{ category: string; count: number }>>
  },
  getJobsByCategoryPublic: async (limitDays = 30, limit = 8) => {
    const response = await api.get('/api/dashboard/jobs-by-category-public', {
      params: { limit_days: limitDays, limit },
    })
    return response.data as Array<{ category: string; count: number }>
  },
  getCategoryTrends: async (category: string, limitDays = 90) => {
    const response = await api.get('/api/dashboard/category-trends', {
      params: { category, limit_days: limitDays },
    })
    return response.data as Array<{
      date: string
      active_count: number
      added_count: number
      removed_count: number
    }>
  },
  getCategoryStats: async (category: string) => {
    const response = await api.get('/api/dashboard/category-stats', {
      params: { category },
    })
    return response.data as {
      active_count: number
      top_employment_type: string | null
      top_position_level: string | null
      avg_salary: number | null
      employment_types: Array<{ employment_type: string; count: number }>
      position_levels: Array<{ position_level: string; count: number }>
      salary_buckets: Array<{ bucket: string; count: number }>
    }
  },
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
    jobDescription: string,
    salary?: number,
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
        job_description: jobDescription,
        salary: salary ?? null,
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

export const salaryApi = {
  search: async (
    jobDescription: string,
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
        job_description: jobDescription,
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
