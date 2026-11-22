/**
 * One set of number/date formats for the companies list and company profiles, so the same
 * figure never appears as "$5.2k" in one place and "$5,200 /mo" in another.
 */
import { payUnit } from './repost'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export const count = (n: number) => n.toLocaleString('en-SG')

export const money = (v: number) => `$${Math.round(v).toLocaleString('en-SG')}`

const round50 = (v: number) => Math.round(v / 50) * 50

/** "$4,850/mo" (or /hr, /day when the ads quote hourly or daily rates). */
export function payText(v: number | null | undefined): string | null {
  if (v == null || v <= 0) return null
  return `${money(v)}${payUnit(v)}`
}

/** "$6,800–$11,450": the middle half of the ads, rounded to $50. null when there is no spread. */
export function spreadText(p25: number | null | undefined, p75: number | null | undefined): string | null {
  if (p25 == null || p75 == null) return null
  const unit = payUnit(p75)
  const lo = unit === '/mo' ? round50(p25) : p25
  const hi = unit === '/mo' ? round50(p75) : p75
  if (lo >= hi) return null
  return `${money(lo)}–${money(hi)}`
}

/** One ad's advertised pay: "$3,000–$5,400/mo", "$3,520/mo", "from $3,000/mo", or "Pay not stated". */
export function adPayText(min: number | null | undefined, max: number | null | undefined): string {
  const lo = min && min > 0 ? min : null
  const hi = max && max > 0 ? max : null
  if (lo == null && hi == null) return 'Pay not stated'
  const unit = payUnit(hi ?? lo!)
  if (lo != null && hi != null) return lo === hi ? `${money(lo)}${unit}` : `${money(lo)}–${money(hi)}${unit}`
  if (lo != null) return `from ${money(lo)}${unit}`
  return `up to ${money(hi!)}${unit}`
}

/** "today", "yesterday", "5 days ago", then "12 Nov" (with the year once it differs). */
export function postedText(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const days = Math.floor((now.getTime() - d.getTime()) / 86_400_000)
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 7) return `${days} days ago`
  const base = `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`
  return d.getUTCFullYear() === now.getUTCFullYear() ? base : `${base} ${d.getUTCFullYear()}`
}

export const plural = (n: number, one: string, many: string) => `${count(n)} ${n === 1 ? one : many}`

/** "FULL BANKS (EXCEPT ...)" -> "Full banks": registry industry names are upper-case and parenthetical. */
export function industryText(raw: string | null | undefined): string | null {
  const base = (raw ?? '').split('(')[0].trim()
  if (!base) return null
  const keepUpper = new Set(['IT', 'AI', 'HR', 'ICT', 'R&D', 'F&B'])
  return base
    .toLowerCase()
    .split(/\s+/)
    .map((w, i) => (keepUpper.has(w.toUpperCase()) ? w.toUpperCase() : i === 0 ? w.charAt(0).toUpperCase() + w.slice(1) : w))
    .join(' ')
}
