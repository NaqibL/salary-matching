import type { PostingOccurrence, SimilarJob } from './types'

/** First guesses (SGSAL-024); tune from the backfill's reposts_365d distribution. */
export const REPOST_AMBER_MIN = 6
export const REPOST_COMPANIES_AMBER_MIN = 3

export type RepostTone = 'none' | 'slate' | 'amber'

type GroupFacts = Pick<SimilarJob, 'repost_count' | 'reposts_365d' | 'distinct_companies' | 'first_posted'>

export function repostTone(j: GroupFacts): RepostTone {
  const n = j.repost_count ?? 1
  if (n < 2) return 'none'
  if ((j.distinct_companies ?? 1) >= REPOST_COMPANIES_AMBER_MIN) return 'amber'
  if ((j.reposts_365d ?? 0) >= REPOST_AMBER_MIN) return 'amber'
  return 'slate'
}

/** Badge copy. Names the fact; never a judgement. */
export function repostLabel(j: GroupFacts): string {
  const n = j.repost_count ?? 1
  const companies = j.distinct_companies ?? 1
  if (companies >= REPOST_COMPANIES_AMBER_MIN) return `Posted under ${companies} company names`
  if ((j.reposts_365d ?? 0) >= REPOST_AMBER_MIN) return `Reposted ${n}× in 12 months`
  const since = monthYear(j.first_posted)
  return since ? `Reposted ${n}× · since ${since}` : `Reposted ${n}×`
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

export function salaryRangeText(min: number | null | undefined, max: number | null | undefined): string | null {
  const fmt = (v: number) => `$${v.toLocaleString()}`
  if (min != null && max != null) return `${fmt(min)} – ${fmt(max)}/mo`
  if (min != null) return `From ${fmt(min)}/mo`
  if (max != null) return `Up to ${fmt(max)}/mo`
  return null
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
