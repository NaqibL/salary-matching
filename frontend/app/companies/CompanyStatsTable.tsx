'use client'

import Link from 'next/link'
import { ArrowDown, Building2 } from 'lucide-react'
import type { CompanyStatsRow, CompanyStatsSort, RoleFamilyRow } from '@/lib/types'
import { monthYear } from '@/lib/repost'
import { familyLabel } from '@/lib/roleFamilies'
import { RoleMixBar } from './RoleMixBar'

const fmtMoney = (v: number | null) => (v == null ? '—' : `$${(v / 1000).toFixed(1)}k`)
const pct = (num: number, den: number) => (den ? Math.round((num / den) * 100) : 0)

function SortHeader({
  label,
  value,
  current,
  onSort,
  className = '',
}: {
  label: string
  value: CompanyStatsSort
  current: CompanyStatsSort
  onSort: (s: CompanyStatsSort) => void
  className?: string
}) {
  const active = current === value
  return (
    <th className={`px-3 py-2 font-medium ${className}`} aria-sort={active ? 'descending' : 'none'}>
      <button
        type="button"
        onClick={() => onSort(value)}
        className={`inline-flex items-center gap-1 hover:text-indigo-600 dark:hover:text-indigo-400 ${
          active ? 'text-indigo-600 dark:text-indigo-400' : ''
        }`}
      >
        {label}
        {active && <ArrowDown size={12} aria-hidden />}
      </button>
    </th>
  )
}

function companyFacts(r: CompanyStatsRow): string {
  const parts = [`across ${r.family_count} role ${r.family_count === 1 ? 'family' : 'families'}`]
  if (r.multi_company_count > 0) parts.push('ads also under other names')
  return parts.join(' · ')
}

export function CompanyStatsTable({
  rows,
  sort,
  onSort,
  familyRows,
  selectedFamily,
}: {
  rows: CompanyStatsRow[]
  sort: CompanyStatsSort
  onSort: (s: CompanyStatsSort) => void
  familyRows?: RoleFamilyRow[]
  selectedFamily?: string
}) {
  const openingsLabel = selectedFamily ? `${familyLabel(selectedFamily, familyRows)} openings` : 'Openings'
  const openingsOf = (r: CompanyStatsRow) => (selectedFamily ? r.family_active_count ?? 0 : r.active_count)

  return (
    <>
      {/* Desktop table */}
      <div className="hidden md:block overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="text-left text-xs text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-700">
            <tr>
              <th className="px-3 py-2 font-medium">Company</th>
              <SortHeader label={openingsLabel} value="openings" current={sort} onSort={onSort} className="text-right" />
              <SortHeader label="Repost rate" value="repost_rate" current={sort} onSort={onSort} />
              <SortHeader label="Median salary" value="median_salary" current={sort} onSort={onSort} className="text-right" />
              <th className="px-3 py-2 font-medium">Role mix</th>
              <th className="px-3 py-2 font-medium whitespace-nowrap">Tracked since</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {rows.map((r) => {
              const rate = pct(r.reposted_count, r.active_count)
              return (
                <tr key={r.company_key} className="text-slate-700 dark:text-slate-200">
                  <td className="px-3 py-2.5 max-w-[20rem]">
                    <Link
                      href={`/company/${encodeURIComponent(r.company)}`}
                      className="font-medium hover:text-indigo-600 dark:hover:text-indigo-400 truncate block"
                      title={r.company}
                    >
                      {r.company}
                    </Link>
                    <div className="text-xs text-slate-400 dark:text-slate-500">{companyFacts(r)}</div>
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums">
                    {openingsOf(r).toLocaleString()}
                    {!selectedFamily && r.distinct_postings < r.active_count && (
                      <div className="text-xs text-slate-400">{r.distinct_postings.toLocaleString()} distinct</div>
                    )}
                  </td>
                  <td className="px-3 py-2.5 min-w-[9rem]">
                    <div className="flex items-center gap-2" title={`${r.reposted_count.toLocaleString()} of ${r.active_count.toLocaleString()} live postings seen before`}>
                      <div className="h-1.5 flex-1 rounded-full bg-slate-100 dark:bg-slate-800">
                        <div className="h-full rounded-full bg-indigo-400 dark:bg-indigo-500" style={{ width: `${rate}%` }} />
                      </div>
                      <span className="tabular-nums text-xs w-8 text-right">{rate}%</span>
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums">
                    {fmtMoney(r.median_salary)}
                    {r.salary_sample > 0 && <div className="text-xs text-slate-400">{r.salary_sample.toLocaleString()} with pay</div>}
                  </td>
                  <td className="px-3 py-2.5 min-w-[8rem]">
                    <RoleMixBar counts={r.role_family_counts} total={r.active_count} familyRows={familyRows} />
                  </td>
                  <td className="px-3 py-2.5 whitespace-nowrap text-slate-500 dark:text-slate-400">{monthYear(r.first_seen) || '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Mobile cards */}
      <div className="md:hidden space-y-2">
        {rows.map((r) => {
          const rate = pct(r.reposted_count, r.active_count)
          return (
            <Link
              key={r.company_key}
              href={`/company/${encodeURIComponent(r.company)}`}
              className="block rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-4 py-3"
            >
              <div className="flex items-center gap-2">
                <Building2 size={14} className="shrink-0 text-slate-400" aria-hidden />
                <span className="flex-1 truncate font-medium text-slate-800 dark:text-slate-200">{r.company}</span>
                <span className="tabular-nums text-sm text-slate-600 dark:text-slate-300">{openingsOf(r).toLocaleString()}</span>
              </div>
              <div className="mt-1.5 flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
                <span>
                  {rate}% reposted · {fmtMoney(r.median_salary)} median
                </span>
                <span>{monthYear(r.first_seen)}</span>
              </div>
              <div className="mt-2">
                <RoleMixBar counts={r.role_family_counts} total={r.active_count} familyRows={familyRows} height={6} />
              </div>
            </Link>
          )
        })}
      </div>
    </>
  )
}
