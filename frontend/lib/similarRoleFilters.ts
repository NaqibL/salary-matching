import type { SimilarJob } from '@/lib/types'

/**
 * Client-side filters for the salary checker's "similar roles" list.
 *
 * Pure functions only — applied to the already-fetched top-N results, never
 * triggering a new API call. The salary benchmark (P25/P50/P75, percentile)
 * is always computed from the unfiltered set.
 */

export interface SimilarRoleFilters {
  /** Selected `inferred_seniority` values (normalised via `normaliseSeniority`). Empty = any. */
  seniority: string[]
  /** Hide historical (closed) listings. */
  activeOnly: boolean
  /** Hide listings with neither `salary_min` nor `salary_max`. */
  hasSalary: boolean
  /** Keep only roles whose `min_years_experience` is known and >= this value. `null` = any. */
  minYears: number | null
}

export const EMPTY_FILTERS: SimilarRoleFilters = {
  seniority: [],
  activeOnly: false,
  hasSalary: false,
  minYears: null,
}

/** Options for the "min years" select; `null` means no constraint. */
export const MIN_YEARS_OPTIONS: ReadonlyArray<{ value: number | null; label: string }> = [
  { value: null, label: 'Any experience' },
  { value: 0, label: '0+ yrs' },
  { value: 1, label: '1+ yrs' },
  { value: 2, label: '2+ yrs' },
  { value: 3, label: '3+ yrs' },
  { value: 5, label: '5+ yrs' },
  { value: 8, label: '8+ yrs' },
]

export interface SeniorityOption {
  /** Normalised key used for matching and state. */
  value: string
  /** Display label (as it first appears in the results). */
  label: string
  /** Number of jobs in the (unfiltered) list carrying this seniority. */
  count: number
}

export function normaliseSeniority(raw: string | null | undefined): string | null {
  const s = raw?.trim().toLowerCase()
  return s ? s : null
}

/** Distinct seniority values present in `jobs`, in order of first appearance. */
export function seniorityOptions(jobs: ReadonlyArray<SimilarJob>): SeniorityOption[] {
  const map = new Map<string, SeniorityOption>()
  for (const job of jobs) {
    const key = normaliseSeniority(job.inferred_seniority)
    if (!key) continue
    const existing = map.get(key)
    if (existing) {
      existing.count += 1
    } else {
      map.set(key, { value: key, label: job.inferred_seniority!.trim(), count: 1 })
    }
  }
  return Array.from(map.values())
}

export function hasActiveFilters(f: SimilarRoleFilters): boolean {
  return f.seniority.length > 0 || f.activeOnly || f.hasSalary || f.minYears != null
}

export function jobHasSalary(job: SimilarJob): boolean {
  return job.salary_min != null || job.salary_max != null
}

export function jobIsActive(job: SimilarJob): boolean {
  return job.is_active !== false
}

export function matchesFilters(job: SimilarJob, f: SimilarRoleFilters): boolean {
  if (f.activeOnly && !jobIsActive(job)) return false
  if (f.hasSalary && !jobHasSalary(job)) return false
  if (f.minYears != null) {
    const yrs = job.min_years_experience
    if (yrs == null || yrs < f.minYears) return false
  }
  if (f.seniority.length > 0) {
    const key = normaliseSeniority(job.inferred_seniority)
    if (!key || !f.seniority.includes(key)) return false
  }
  return true
}

/** Apply `filters` to `jobs`, preserving order. Returns the same array when no filter is set. */
export function applySimilarRoleFilters(
  jobs: SimilarJob[],
  filters: SimilarRoleFilters,
): SimilarJob[] {
  if (!hasActiveFilters(filters)) return jobs
  return jobs.filter((job) => matchesFilters(job, filters))
}

/** Toggle a seniority value in/out of the selection (immutable). */
export function toggleSeniority(f: SimilarRoleFilters, value: string): SimilarRoleFilters {
  const key = normaliseSeniority(value)
  if (!key) return f
  const seniority = f.seniority.includes(key)
    ? f.seniority.filter((s) => s !== key)
    : [...f.seniority, key]
  return { ...f, seniority }
}
