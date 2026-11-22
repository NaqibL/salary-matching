'use client'

import { Suspense, useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import useSWR from 'swr'
import { companiesApi } from '@/lib/api'
import type { CompanyAgencyFilter, CompanyStatsResponse } from '@/lib/types'
import { FAMILY_LABELS, familyLabel } from '@/lib/roleFamilies'
import { count } from '@/lib/companyFormat'
import { Layout } from '@/app/components/layout'
import NavUserActions from '@/app/components/NavUserActions'
import { CompanyStatsTable, MIN_ADS_FOR_PAY, type CompanyListSort } from './CompanyStatsTable'

const PAGE = 100
const MAX_ROWS = 200 // API ceiling

const fieldCls =
  'h-10 rounded-md border border-slate-400 bg-white px-3 text-[15px] text-slate-900 placeholder-slate-500 focus:border-slate-900 focus:outline-none focus:ring-1 focus:ring-slate-900'

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

function CompaniesExplorer() {
  const router = useRouter()
  const sp = useSearchParams()

  const family = sp.get('family') ?? ''
  // Recruitment agencies are hidden unless asked for. `who=` is the older form of the same switch.
  const showAgencies = sp.get('agencies') === 'show' || sp.get('who') === 'all' || sp.get('who') === 'agency'
  const sort: CompanyListSort = sp.get('sort') === 'median_salary' ? 'median_salary' : 'openings'
  const [query, setQuery] = useState(sp.get('q') ?? '')
  const q = useDebounced(query.trim(), 300)
  const [limit, setLimit] = useState(PAGE)

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(sp.toString())
    next.delete('who')
    next.delete('min_active')
    next.delete('category')
    if (value) next.set(key, value)
    else next.delete(key)
    const qs = next.toString()
    router.replace(qs ? `/companies?${qs}` : '/companies', { scroll: false })
  }
  useEffect(() => {
    if ((sp.get('q') ?? '') !== q) setParam('q', q)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q])
  useEffect(() => setLimit(PAGE), [family, showAgencies, sort, q])

  const familyOptions = Object.keys(FAMILY_LABELS)
    .filter((key) => key !== 'other')
    .map((key) => ({ key, label: familyLabel(key) }))
    .sort((a, b) => a.label.localeCompare(b.label))
  const familyName = family ? familyLabel(family) : ''

  // A name search looks at every company, agencies included, so a searched name is always found.
  const agency: CompanyAgencyFilter = q || showAgencies ? 'all' : 'direct'
  const params = { family, q, agency, min_active: 1, sort, limit } as const
  const { data, isLoading, error } = useSWR<CompanyStatsResponse>(
    ['companies-stats', JSON.stringify(params)],
    () => companiesApi.getStats(params),
    { revalidateOnFocus: false, keepPreviousData: true },
  )

  const rows = data?.rows ?? []
  const total = data?.total_matching ?? 0
  const who = agency === 'direct' ? (total === 1 ? 'employer' : 'employers') : total === 1 ? 'company' : 'companies'
  const openRoles = data?.summary.openings ?? 0

  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-semibold text-slate-900 sm:text-3xl">Companies</h1>
      <p className="mt-1 text-base text-slate-700">
        {familyName ? `Who is hiring for ${familyName}, and what they advertise.` : 'Who is hiring in Singapore, and what they advertise.'}
      </p>

      <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
        <input
          type="search"
          aria-label="Search for a company"
          placeholder="Search for a company"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className={`${fieldCls} w-full sm:w-72`}
        />
        <select aria-label="Job type" className={`${fieldCls} w-full sm:w-72`} value={family} onChange={(e) => setParam('family', e.target.value)}>
          <option value="">All job types</option>
          {familyOptions.map((f) => (
            <option key={f.key} value={f.key}>
              {f.label}
            </option>
          ))}
        </select>
        <label className={`flex min-h-10 items-center gap-2 text-[15px] ${q ? 'text-slate-400' : 'text-slate-900'}`}>
          <input
            type="checkbox"
            className="h-5 w-5 rounded border-slate-500 text-slate-900 focus:ring-slate-900"
            checked={!showAgencies && !q}
            disabled={!!q}
            onChange={(e) => setParam('agencies', e.target.checked ? '' : 'show')}
          />
          Hide recruitment agencies and firms hiring for clients
        </label>
      </div>

      <div className="mt-6" aria-live="polite">
        {isLoading && !data && <p className="py-8 text-slate-600">Loading companies…</p>}
        {error && !data && <p className="py-8 text-slate-900">The company list could not be loaded. Please try again in a minute.</p>}

        {data && rows.length === 0 && (
          <p className="py-8 text-slate-900">
            {q ? (
              <>
                No company with open roles matches “{q}”{familyName ? ` in ${familyName}` : ''}. Try a shorter part of the name.
              </>
            ) : (
              <>No companies have open roles for this job type right now.</>
            )}
          </p>
        )}

        {data && rows.length > 0 && (
          <>
            <p className="mb-3 text-[15px] text-slate-700">
              {q ? (
                <>
                  {count(total)} {who} matching “{q}”
                </>
              ) : (
                <>
                  {count(total)} {who}
                  {familyName ? ` hiring for ${familyName}` : ' hiring'} · {count(openRoles)} open {openRoles === 1 ? 'role' : 'roles'}
                </>
              )}
              {rows.length < total && <> · showing the first {count(rows.length)}</>}
            </p>

            <CompanyStatsTable rows={rows} sort={sort} onSort={(s) => setParam('sort', s === 'openings' ? '' : s)} selectedFamily={family || undefined} />

            {rows.length < total && limit < MAX_ROWS && (
              <button
                type="button"
                onClick={() => setLimit(MAX_ROWS)}
                className="mt-4 text-[15px] text-slate-900 underline decoration-slate-400 underline-offset-4 hover:decoration-slate-900"
              >
                Show {count(Math.min(MAX_ROWS, total) - rows.length)} more
              </button>
            )}

            <p className="mt-6 max-w-2xl text-sm text-slate-600">
              Typical pay is the middle advertised monthly salary across the company&rsquo;s full-time open ads
              {familyName ? ` for ${familyName}` : ''}, shown when at least {MIN_ADS_FOR_PAY} state a salary. Hourly,
              part-time and internship pay is left out.
              {sort === 'median_salary' && ' Companies are ranked by pay only when 10 or more of their ads state a salary; the rest follow.'}
            </p>
          </>
        )}
      </div>
    </div>
  )
}

export default function CompaniesPage() {
  return (
    <Layout userSlot={<NavUserActions />}>
      <Suspense fallback={<p className="py-8 text-slate-600">Loading companies…</p>}>
        <CompaniesExplorer />
      </Suspense>
    </Layout>
  )
}
