'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'
import { ArrowDown, ArrowUp } from 'lucide-react'
import type { MarketStatsRow, RoleFamilyRow } from '@/lib/types'
import { OTHER_FAMILY, familyLabel } from '@/lib/roleFamilies'
import { fmtMoney, fmtPct, pct } from './ChartTooltip'

export const MIN_SALARY_N = 30

type SortKey = 'live' | 'median_salary' | 'new_7d' | 'reposts' | 'agency'

const SORT_LABEL: Record<SortKey, string> = {
  live: 'Live ads',
  median_salary: 'Median advertised monthly base',
  new_7d: 'New this week',
  reposts: 'Posted before',
  agency: 'From agencies',
}

const TIP: Record<SortKey, string> = {
  live: 'Ads open today in this job type',
  median_salary: `Middle value of the advertised monthly base salaries in this job type's live ads, SGD (ranges whose top is more than double the bottom are left out). Shown from ${MIN_SALARY_N} ads.`,
  new_7d: 'Ads in this job type first seen in the last 7 days',
  reposts: 'Live ads whose exact text was posted earlier, under any company name',
  agency: 'Live ads placed by a recruitment agency (registered as an employment agency, or a recruitment-agency name confirmed by its registration)',
}

/**
 * Momentum is shown as this week's new ads, not a 4-week change: role families were only ever
 * classified on active ads, so ads from 4-8 weeks ago that closed unclassified sit in `other`
 * and a period-over-period ratio reads +300% for every family. Revisit once the classifier has
 * covered two full periods (see ticket SGSAL-030).
 */
function fmtNew(r: MarketStatsRow): string {
  return r.new_7d == null ? '—' : r.new_7d.toLocaleString()
}

function medianText(r: MarketStatsRow): string {
  return (r.salary_n ?? 0) >= MIN_SALARY_N ? fmtMoney(r.median_salary) : '—'
}

function sortValue(r: MarketStatsRow, key: SortKey): number {
  switch (key) {
    case 'live':
      return r.live
    case 'median_salary':
      return (r.salary_n ?? 0) >= MIN_SALARY_N && r.median_salary != null ? r.median_salary : -1
    case 'new_7d':
      return r.new_7d ?? -1
    case 'reposts':
      return pct(r.live_reposts, r.live) ?? -1
    case 'agency':
      return pct(r.live_agency, r.live) ?? -1
  }
}

/**
 * The dashboard's centrepiece (SGSAL-030): one row per role family with live ads, pay, momentum
 * and repeat share. One colour for the inline bar; 24 hues would carry no meaning. `other` sits
 * last, greyed, and never sorts into the ranking.
 */
export function JobTypesTable({ families, familyRows }: { families: MarketStatsRow[]; familyRows?: RoleFamilyRow[] }) {
  const [sort, setSort] = useState<SortKey>('live')
  const [desc, setDesc] = useState(true)

  const { rows, other, maxLive } = useMemo(() => {
    const named = families.filter((f) => f.key !== OTHER_FAMILY)
    const sorted = [...named].sort((a, b) => {
      const d = sortValue(b, sort) - sortValue(a, sort)
      return desc ? d : -d
    })
    return {
      rows: sorted,
      other: families.find((f) => f.key === OTHER_FAMILY) ?? null,
      maxLive: Math.max(1, ...families.map((f) => f.live)),
    }
  }, [families, sort, desc])

  const onSort = (key: SortKey) => {
    if (key === sort) setDesc((d) => !d)
    else {
      setSort(key)
      setDesc(true)
    }
  }

  const Header = ({ k, className = '' }: { k: SortKey; className?: string }) => {
    const active = sort === k
    return (
      <th className={`px-3 py-2 font-medium ${className}`} aria-sort={active ? (desc ? 'descending' : 'ascending') : 'none'}>
        <button
          type="button"
          onClick={() => onSort(k)}
          title={TIP[k]}
          className={`inline-flex items-center gap-1 text-left hover:text-indigo-600 dark:hover:text-indigo-400 ${
            active ? 'text-indigo-600 dark:text-indigo-400' : ''
          }`}
        >
          {SORT_LABEL[k]}
          {active && (desc ? <ArrowDown size={12} aria-hidden /> : <ArrowUp size={12} aria-hidden />)}
        </button>
      </th>
    )
  }

  const Row = ({ r, muted = false }: { r: MarketStatsRow; muted?: boolean }) => {
    const name = familyLabel(r.key, familyRows)
    const width = `${Math.max(2, (100 * r.live) / maxLive)}%`
    const tone = muted ? 'text-slate-400 dark:text-slate-500' : 'text-slate-700 dark:text-slate-200'
    return (
      <tr className={tone}>
        <td className="px-3 py-2 font-medium">
          {muted ? (
            <span title="Ads the classifier could not place in a job type">{name}</span>
          ) : (
            <Link href={`/companies?family=${encodeURIComponent(r.key)}`} className="hover:text-indigo-600 dark:hover:text-indigo-400">
              {name}
            </Link>
          )}
        </td>
        <td className="px-3 py-2 min-w-[11rem]">
          <div className="flex items-center gap-2">
            <div className="h-2 flex-1 rounded-sm bg-slate-100 dark:bg-slate-700/60">
              <div
                className="h-2 rounded-sm"
                style={{ width, backgroundColor: muted ? 'var(--viz-other, #cbd5e1)' : 'var(--viz-1, #2a78d6)' }}
              />
            </div>
            <span className="w-14 text-right tabular-nums">{r.live.toLocaleString()}</span>
          </div>
        </td>
        <td className="px-3 py-2 text-right tabular-nums" title={(r.salary_n ?? 0) < MIN_SALARY_N ? `fewer than ${MIN_SALARY_N} ads with a compliant range` : `${(r.salary_n ?? 0).toLocaleString()} ads`}>
          {medianText(r)}
        </td>
        <td className="px-3 py-2 text-right tabular-nums" title="first seen in the last 7 days">
          {fmtNew(r)}
        </td>
        <td className="px-3 py-2 text-right tabular-nums" title={`${(r.live_reposts ?? 0).toLocaleString()} of ${r.live.toLocaleString()} live ads`}>
          {fmtPct(pct(r.live_reposts, r.live))}
        </td>
        <td className="hidden lg:table-cell px-3 py-2 text-right tabular-nums" title={`${(r.live_agency ?? 0).toLocaleString()} of ${r.live.toLocaleString()} live ads`}>
          {fmtPct(pct(r.live_agency, r.live))}
        </td>
      </tr>
    )
  }

  return (
    <>
      {/* Desktop table */}
      <div className="hidden md:block overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="text-left text-xs text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-700">
            <tr>
              <th className="px-3 py-2 font-medium">Job type</th>
              <Header k="live" />
              <Header k="median_salary" className="text-right" />
              <Header k="new_7d" className="text-right" />
              <Header k="reposts" className="text-right" />
              <Header k="agency" className="hidden lg:table-cell text-right" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {rows.map((r) => (
              <Row key={r.key} r={r} />
            ))}
            {other && other.live > 0 && <Row r={other} muted />}
          </tbody>
        </table>
      </div>

      {/* Mobile list: three numbers survive (pay, change, live); the bar carries size. */}
      <div className="md:hidden">
        <div className="flex items-center justify-between gap-2 mb-2 text-xs text-slate-500 dark:text-slate-400">
          <span>Pay is the median advertised monthly base, SGD</span>
          <label className="inline-flex items-center gap-1">
            Sort
            <select
              aria-label="Sort job types"
              className="rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-1.5 py-0.5 text-xs text-slate-700 dark:text-slate-200"
              value={sort}
              onChange={(e) => {
                setSort(e.target.value as SortKey)
                setDesc(true)
              }}
            >
              {(Object.keys(SORT_LABEL) as SortKey[]).map((k) => (
                <option key={k} value={k}>
                  {SORT_LABEL[k]}
                </option>
              ))}
            </select>
          </label>
        </div>
        <ul className="divide-y divide-slate-100 dark:divide-slate-800">
          {[...rows, ...(other && other.live > 0 ? [other] : [])].map((r) => {
            const muted = r.key === OTHER_FAMILY
            return (
              <li key={r.key} className="py-2">
                <div className="flex items-baseline justify-between gap-2">
                  {muted ? (
                    <span className="text-sm text-slate-400">{familyLabel(r.key, familyRows)}</span>
                  ) : (
                    <Link href={`/companies?family=${encodeURIComponent(r.key)}`} className="text-sm font-medium text-slate-800 dark:text-slate-100 truncate">
                      {familyLabel(r.key, familyRows)}
                    </Link>
                  )}
                  <span className="shrink-0 text-xs tabular-nums text-slate-500 dark:text-slate-400">
                    {medianText(r)} · {fmtNew(r)} new · {r.live.toLocaleString()} live
                  </span>
                </div>
                <div className="mt-1 h-1.5 rounded-sm bg-slate-100 dark:bg-slate-700/60">
                  <div
                    className="h-1.5 rounded-sm"
                    style={{ width: `${Math.max(2, (100 * r.live) / maxLive)}%`, backgroundColor: muted ? 'var(--viz-other, #cbd5e1)' : 'var(--viz-1, #2a78d6)' }}
                  />
                </div>
              </li>
            )
          })}
        </ul>
      </div>
    </>
  )
}
