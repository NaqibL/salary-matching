'use client'

import Link from 'next/link'
import { ArrowDown, Building2 } from 'lucide-react'
import type { CompanyStatsRow, CompanyStatsSort, RoleFamilyRow } from '@/lib/types'
import { familyLabel } from '@/lib/roleFamilies'
import { AgencyTag } from '@/app/components/AgencyTag'

const fmtMoney = (v: number | null | undefined) => (v == null ? '—' : `$${v.toLocaleString()}`)

/** Below this many openings a repeat share is not worth showing. */
const MIN_FOR_SHARE = 5

export const POSTED_BEFORE_TIP = 'Live ads whose exact text was posted earlier, under any company name'

export function postedBeforePct(r: CompanyStatsRow): number | null {
  if (r.active_count < MIN_FOR_SHARE) return null
  return Math.round((100 * r.reposted_count) / r.active_count)
}

function SortHeader({
  label,
  value,
  current,
  onSort,
  className = '',
  title,
}: {
  label: string
  value: CompanyStatsSort
  current: CompanyStatsSort
  onSort: (s: CompanyStatsSort) => void
  className?: string
  title?: string
}) {
  const active = current === value
  return (
    <th className={`px-3 py-2 font-medium ${className}`} aria-sort={active ? 'descending' : 'none'} title={title}>
      <button
        type="button"
        onClick={() => onSort(value)}
        className={`inline-flex items-center gap-1 text-left hover:text-indigo-600 dark:hover:text-indigo-400 ${
          active ? 'text-indigo-600 dark:text-indigo-400' : ''
        }`}
      >
        {label}
        {active && <ArrowDown size={12} aria-hidden />}
      </button>
    </th>
  )
}

/** "Healthcare & Allied Health (62%)", or "Mixed · 25 job types" for agencies / very wide spreads. */
export function hiresMainly(r: CompanyStatsRow, familyRows?: RoleFamilyRow[]): string {
  const share = r.top_family_share ?? 0
  const concentrated = !!r.top_family && r.top_family !== 'other' && share >= 0.3
  if (!concentrated || (r.is_agency && share < 0.6)) {
    return `Mixed · ${r.family_count} job ${r.family_count === 1 ? 'type' : 'types'}`
  }
  return `${familyLabel(r.top_family!, familyRows)} (${Math.round(share * 100)}%)`
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
  const familyName = selectedFamily ? familyLabel(selectedFamily, familyRows) : null
  const openingsOf = (r: CompanyStatsRow) => (selectedFamily ? r.family_active_count ?? 0 : r.active_count)
  const showSalary = !!selectedFamily

  return (
    <>
      {/* Desktop table */}
      <div className="hidden md:block overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="text-left text-xs text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-700">
            <tr>
              <th className="px-3 py-2 font-medium">Company</th>
              <SortHeader
                label={familyName ? `${familyName} openings` : 'Openings'}
                value="openings"
                current={sort}
                onSort={onSort}
                className="text-right"
                title="Live ads"
              />
              {!selectedFamily && (
                <SortHeader
                  label="Distinct ads"
                  value="distinct"
                  current={sort}
                  onSort={onSort}
                  className="text-right"
                  title="Live ads with different text. A company that posts one ad text under many listings has fewer distinct ads than openings."
                />
              )}
              <SortHeader label="Posted before" value="repost_rate" current={sort} onSort={onSort} className="text-right" title={POSTED_BEFORE_TIP} />
              <th className="px-3 py-2 font-medium">Hires mainly</th>
              {showSalary && (
                <SortHeader
                  label={`Median advertised monthly base · ${familyName}`}
                  value="median_salary"
                  current={sort}
                  onSort={onSort}
                  className="text-right"
                  title="Median of the advertised monthly base salaries of this company's live ads for the chosen job type, SGD"
                />
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {rows.map((r) => {
              const share = postedBeforePct(r)
              return (
                <tr key={r.company_key} className="text-slate-700 dark:text-slate-200">
                  <td className="px-3 py-2.5 max-w-[24rem]">
                    <div className="flex items-center gap-2 min-w-0">
                      <Link
                        href={`/company/${encodeURIComponent(r.company)}`}
                        className="font-medium hover:text-indigo-600 dark:hover:text-indigo-400 truncate"
                        title={r.company}
                      >
                        {r.company}
                      </Link>
                      {r.is_agency && <AgencyTag />}
                    </div>
                    {r.multi_company_count > 0 && (
                      <div className="text-xs text-slate-400 dark:text-slate-500">
                        {r.multi_company_count.toLocaleString()} of their ads also appear under other company names
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{openingsOf(r).toLocaleString()}</td>
                  {!selectedFamily && (
                    <td className="px-3 py-2.5 text-right tabular-nums">
                      {r.distinct_postings.toLocaleString()}
                    </td>
                  )}
                  <td className="px-3 py-2.5 text-right tabular-nums" title={share == null ? `Shown from ${MIN_FOR_SHARE} openings` : `${r.reposted_count.toLocaleString()} of ${r.active_count.toLocaleString()} live ads`}>
                    {share == null ? <span className="text-slate-400">—</span> : `${share}%`}
                  </td>
                  <td className="px-3 py-2.5 text-slate-600 dark:text-slate-300">{hiresMainly(r, familyRows)}</td>
                  {showSalary && (
                    <td className="px-3 py-2.5 text-right tabular-nums">
                      {(r.family_salary_sample ?? 0) >= 3 ? (
                        <>
                          {fmtMoney(r.family_median_salary)}
                          <span className="text-xs text-slate-400"> /mo</span>
                          <div className="text-xs text-slate-400">{r.family_salary_sample} ads</div>
                        </>
                      ) : (
                        <span className="text-slate-400" title="Fewer than 3 ads with a disclosed salary">—</span>
                      )}
                    </td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Mobile cards */}
      <div className="md:hidden space-y-2">
        {rows.map((r) => {
          const share = postedBeforePct(r)
          return (
            <Link
              key={r.company_key}
              href={`/company/${encodeURIComponent(r.company)}`}
              className="block rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-4 py-3"
            >
              <div className="flex items-center gap-2">
                <Building2 size={14} className="shrink-0 text-slate-400" aria-hidden />
                <span className="flex-1 truncate font-medium text-slate-800 dark:text-slate-200">{r.company}</span>
                <span className="tabular-nums text-sm text-slate-600 dark:text-slate-300">{openingsOf(r).toLocaleString()} open</span>
              </div>
              <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
                {r.is_agency && <AgencyTag />}
                <span>{hiresMainly(r, familyRows)}</span>
                {share != null && <span title={POSTED_BEFORE_TIP}>{share}% posted before</span>}
                {showSalary && (r.family_salary_sample ?? 0) >= 3 && <span>median {fmtMoney(r.family_median_salary)}/mo</span>}
              </div>
            </Link>
          )
        })}
      </div>
    </>
  )
}
