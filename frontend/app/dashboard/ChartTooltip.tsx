'use client'

type TooltipEntry = {
  name?: string
  value?: number | string
  color?: string
  dataKey?: string | number
  payload?: Record<string, unknown>
}

export interface ChartTooltipProps {
  active?: boolean
  payload?: TooltipEntry[]
  label?: string | number
  labelFormatter?: (label: string) => string
  /** Replace the default rows with rows derived from the hovered data point. */
  rows?: (row: Record<string, unknown>) => Array<{ label: string; value: string }>
  /** Extra rows appended after the series rows. */
  extra?: (row: Record<string, unknown>) => Array<{ label: string; value: string }>
}

/** Tailwind-styled tooltip so it follows dark mode (Recharts' default is white-only). */
export function ChartTooltip({ active, payload, label, labelFormatter, rows, extra }: ChartTooltipProps) {
  if (!active || !payload || payload.length === 0) return null
  const row = payload[0]?.payload ?? {}
  const shown = label != null ? (labelFormatter ? labelFormatter(String(label)) : String(label)) : null
  const body = rows
    ? rows(row)
    : payload
        .filter((p) => p.value != null)
        .map((p) => ({
          label: p.name ?? String(p.dataKey ?? ''),
          value: typeof p.value === 'number' ? p.value.toLocaleString() : String(p.value),
        }))
  const more = extra ? extra(row) : []
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-md dark:border-slate-700 dark:bg-slate-800">
      {shown && <div className="mb-1 font-medium text-slate-800 dark:text-slate-100">{shown}</div>}
      {[...body, ...more].map((r) => (
        <div key={r.label} className="flex items-center justify-between gap-4 text-slate-600 dark:text-slate-300">
          <span>{r.label}</span>
          <span className="tabular-nums font-medium text-slate-800 dark:text-slate-100">{r.value}</span>
        </div>
      ))}
    </div>
  )
}

export const TICK = { fontSize: 11, fill: 'currentColor' }
export const CHART_TEXT = 'text-slate-500 dark:text-slate-400'
export const VIZ_1 = 'var(--viz-1, #2a78d6)'
export const VIZ_8 = 'var(--viz-8, #e34948)'
export const VIZ_OTHER = 'var(--viz-other, #cbd5e1)'

export function fmtMoney(v: number | null | undefined): string {
  return v == null ? '—' : `$${Math.round(v).toLocaleString()}`
}

export function pct(part: number | null | undefined, whole: number | null | undefined): number | null {
  if (part == null || !whole) return null
  return (100 * part) / whole
}

export function fmtPct(v: number | null, digits = 0): string {
  return v == null ? '—' : `${v.toFixed(digits)}%`
}

export function fmtDelta(v: number | null): string {
  if (v == null) return '—'
  const r = Math.round(v)
  return r > 0 ? `+${r.toLocaleString()}` : r.toLocaleString()
}
