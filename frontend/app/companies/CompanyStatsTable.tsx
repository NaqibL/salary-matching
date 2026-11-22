'use client'

import Link from 'next/link'
import type { CompanyStatsRow } from '@/lib/types'
import { count, payText } from '@/lib/companyFormat'

export type CompanyListSort = 'openings' | 'median_salary'

/** Pay is shown once this many of the company's open ads state a salary. */
export const MIN_ADS_FOR_PAY = 3

type Pay = { text: string; ads: number } | null

function SortButton({
  label,
  value,
  current,
  onSort,
}: {
  label: string
  value: CompanyListSort
  current: CompanyListSort
  onSort: (s: CompanyListSort) => void
}) {
  const active = current === value
  return (
    <button
      type="button"
      onClick={() => onSort(value)}
      aria-pressed={active}
      className={`rounded-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500 ${
        active ? 'font-semibold text-slate-900' : 'text-slate-600 underline decoration-slate-300 underline-offset-4 hover:text-slate-900'
      }`}
    >
      {label}
      {active && <span aria-hidden> ↓</span>}
    </button>
  )
}

export function CompanyStatsTable({
  rows,
  sort,
  onSort,
  selectedFamily,
}: {
  rows: CompanyStatsRow[]
  sort: CompanyListSort
  onSort: (s: CompanyListSort) => void
  selectedFamily?: string
}) {
  const openRoles = (r: CompanyStatsRow) => (selectedFamily ? r.family_active_count ?? 0 : r.active_count)
  const pay = (r: CompanyStatsRow): Pay => {
    const median = selectedFamily ? r.family_median_salary : r.median_salary
    const ads = (selectedFamily ? r.family_salary_sample : r.salary_sample) ?? 0
    const text = payText(median)
    return text && ads >= MIN_ADS_FOR_PAY ? { text, ads } : null
  }
  // carry the chosen job type into the profile, so it opens on that company's roles of the same type
  const profileHref = (r: CompanyStatsRow) =>
    `/company/${encodeURIComponent(r.company)}${selectedFamily ? `?family=${encodeURIComponent(selectedFamily)}` : ''}`
  const nameCls = 'font-medium text-slate-900 underline decoration-slate-300 underline-offset-4 hover:decoration-slate-900'

  return (
    <>
      {/* Wide screens: three columns */}
      <table className="hidden w-full text-[15px] md:table">
        <thead>
          <tr className="border-b border-slate-300 text-left text-sm">
            <th scope="col" className="py-2 pr-4 font-normal text-slate-600">
              Company
            </th>
            <th scope="col" className="w-40 py-2 pl-4 text-right font-normal" aria-sort={sort === 'openings' ? 'descending' : 'none'}>
              <SortButton label="Open roles" value="openings" current={sort} onSort={onSort} />
            </th>
            <th scope="col" className="w-56 py-2 pl-4 text-right font-normal" aria-sort={sort === 'median_salary' ? 'descending' : 'none'}>
              <SortButton label="Typical pay" value="median_salary" current={sort} onSort={onSort} />
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const p = pay(r)
            return (
              <tr key={r.company_key} className="border-b border-slate-200 align-baseline">
                <td className="py-2.5 pr-4">
                  <Link href={profileHref(r)} className={nameCls}>
                    {r.company}
                  </Link>
                  {r.is_agency && <span className="ml-2 text-sm text-slate-500">Recruitment agency</span>}
                </td>
                <td className="py-2.5 pl-4 text-right tabular-nums text-slate-900">{count(openRoles(r))}</td>
                <td className="py-2.5 pl-4 text-right tabular-nums">
                  {p ? (
                    <>
                      <span className="text-slate-900">{p.text}</span>
                      <span className="ml-2 inline-block w-16 text-left text-sm text-slate-500">{count(p.ads)} ads</span>
                    </>
                  ) : (
                    <span className="text-sm text-slate-500">Too few ads state pay</span>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>

      {/* Narrow screens: the same three facts, stacked */}
      <div className="md:hidden">
        <div className="flex items-center gap-4 border-b border-slate-300 pb-2 text-sm">
          <span className="text-slate-600">Sort by</span>
          <SortButton label="Open roles" value="openings" current={sort} onSort={onSort} />
          <SortButton label="Typical pay" value="median_salary" current={sort} onSort={onSort} />
        </div>
        <ul>
          {rows.map((r) => {
            const p = pay(r)
            return (
              <li key={r.company_key} className="border-b border-slate-200 py-3">
                <Link href={profileHref(r)} className={`${nameCls} break-words`}>
                  {r.company}
                </Link>
                {r.is_agency && <span className="ml-2 text-sm text-slate-500">Recruitment agency</span>}
                <div className="mt-1 text-sm text-slate-700">
                  {count(openRoles(r))} open {openRoles(r) === 1 ? 'role' : 'roles'}
                  {p ? (
                    <>
                      {' · '}
                      {p.text} <span className="text-slate-500">from {count(p.ads)} ads</span>
                    </>
                  ) : null}
                </div>
              </li>
            )
          })}
        </ul>
      </div>
    </>
  )
}
