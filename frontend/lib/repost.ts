import type { PostingOccurrence, SimilarJob } from './types'

/** First guesses (SGSAL-024); tune from the backfill's reposts_365d distribution. */
export const REPOST_AMBER_MIN = 6

export type RepostTone = 'none' | 'slate' | 'amber'

type GroupFacts = Pick<SimilarJob, 'repost_count' | 'reposts_365d' | 'distinct_companies' | 'first_posted'>

export function repostTone(j: GroupFacts): RepostTone {
  const n = j.repost_count ?? 1
  if (n < 2) return 'none'
  if ((j.distinct_companies ?? 1) >= 2) return 'amber'
  if ((j.reposts_365d ?? 0) >= REPOST_AMBER_MIN) return 'amber'
  return 'slate'
}

/** Chip copy. A plain sentence that names the fact; never a judgement (SGSAL-028). */
export function repostLabel(j: GroupFacts): string {
  const n = j.repost_count ?? 1
  const companies = j.distinct_companies ?? 1
  if (companies >= 2) return `Same ad under ${companies} company names`
  if ((j.reposts_365d ?? 0) >= REPOST_AMBER_MIN) return `Posted ${n} times this year`
  const since = monthYear(j.first_posted)
  return since ? `Posted ${n} times since ${since}` : `Posted ${n} times`
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** "Mar 2026" from an ISO date; '' when missing/invalid. */
export function monthYear(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`
}

/** "Mar 4, 2026" */
export function fullDate(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()}`
}

/** MCF ads sometimes put an hourly or daily rate in the salary fields; label by magnitude. */
export function payUnit(max: number): '/hr' | '/day' | '/mo' {
  if (max < 100) return '/hr'
  if (max < 500) return '/day'
  return '/mo'
}

export function salaryRangeText(min: number | null | undefined, max: number | null | undefined): string | null {
  const fmt = (v: number) => `$${v.toLocaleString()}`
  const lo = min && min > 0 ? min : null
  const hi = max && max > 0 ? max : null
  if (lo == null && hi == null) return null
  const unit = payUnit(hi ?? lo!)
  if (lo != null && hi != null) return `${fmt(lo)} – ${fmt(hi)}${unit}`
  if (lo != null) return `From ${fmt(lo)}${unit}`
  return `Up to ${fmt(hi!)}${unit}`
}

/** Oldest vs newest salaried occurrence. null when fewer than 2 have a salary. */
export function salaryMovement(occ: PostingOccurrence[]): string | null {
  const withSalary = occ.filter(o => o.salary_min != null || o.salary_max != null)
  if (withSalary.length < 2) return null
  // occurrences arrive newest-first
  const newest = withSalary[0]
  const oldest = withSalary[withSalary.length - 1]
  const a = salaryRangeText(oldest.salary_min, oldest.salary_max)
  const b = salaryRangeText(newest.salary_min, newest.salary_max)
  if (!a || !b) return null
  return a === b ? 'Same range every time' : `Range moved from ${a.replace('/mo', '')} to ${b}`
}
