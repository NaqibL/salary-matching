'use client'

import { Suspense, useEffect, useMemo, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import useSWR from 'swr'
import { Building2, Search } from 'lucide-react'
import { companiesApi, dashboardApi } from '@/lib/api'
import type { CompanyAgencyFilter, CompanyStatsResponse, CompanyStatsSort, RoleFamilyRow } from '@/lib/types'
import { familyLabel } from '@/lib/roleFamilies'
import { AGENCY_TOOLTIP } from '@/app/components/AgencyTag'
import { Layout } from '@/app/components/layout'
import NavUserActions from '@/app/components/NavUserActions'
import { Card, CardBody, EmptyState, PageHeader } from '@/components/design'
import { CompanyStatsTable, POSTED_BEFORE_TIP } from './CompanyStatsTable'

const MIN_ACTIVE_OPTIONS = [10, 3, 1] as const
const SORTS: CompanyStatsSort[] = ['openings', 'distinct', 'repost_rate', 'median_salary']

/** Who placed the ads. URL param `who`; default direct employers (SGSAL-030). */
const WHO: Array<{ value: CompanyAgencyFilter; label: string; title: string }> = [
  { value: 'direct', label: 'Direct employers', title: 'Companies hiring for themselves' },
  { value: 'agency', label: 'Recruitment agencies', title: AGENCY_TOOLTIP },
  { value: 'all', label: 'All', title: 'Every company with a live ad' },
]

const selectCls =
  'rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-2.5 py-1.5 text-sm text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50'

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
  const category = sp.get('category') ?? ''
  const whoParam = sp.get('who')
  const who: CompanyAgencyFilter = whoParam === 'agency' || whoParam === 'all' ? whoParam : sp.get('agencies') === 'show' ? 'all' : 'direct'
  // Default floor: 10 openings company-wide, 3 within a chosen job type (the floor is type-scoped then).
  const minActive = Number(sp.get('min_active')) || (family ? 3 : 10)
  const [query, setQuery] = useState(sp.get('q') ?? '')
  const q = useDebounced(query.trim(), 300)

  // Default order: with no job type chosen, companies with the most *distinct* ads lead, so one
  // ad text posted under many listings does not top the list; with a job type, that type's openings.
  const defaultSort: CompanyStatsSort = family ? 'openings' : 'distinct'
  const sortParam = sp.get('sort') as CompanyStatsSort | null
  const sort: CompanyStatsSort =
    sortParam && SORTS.includes(sortParam) && (sortParam !== 'median_salary' || family) && (sortParam !== 'distinct' || !family)
      ? sortParam
      : defaultSort

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(sp.toString())
    next.delete('agencies')
    if (value) next.set(key, value)
    else next.delete(key)
    const qs = next.toString()
    router.replace(qs ? `/companies?${qs}` : '/companies', { scroll: false })
  }
  useEffect(() => {
    if ((sp.get('q') ?? '') !== q) setParam('q', q)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q])

  const { data: families = [] } = useSWR<RoleFamilyRow[]>('dashboard-role-families', dashboardApi.getRoleFamilies, {
    revalidateOnFocus: false,
  })

  // A name search looks at everyone (no floor, every poster); otherwise the segmented control decides.
  const agency: CompanyAgencyFilter = q ? 'all' : who
  const effectiveMin = q ? 1 : minActive
  const params = { family, category, q, agency, min_active: effectiveMin, sort, limit: 100 } as const
  const { data, isLoading, error } = useSWR<CompanyStatsResponse>(
    ['companies-stats', JSON.stringify(params)],
    () => companiesApi.getStats(params),
    { revalidateOnFocus: false, keepPreviousData: true },
  )
  // Size of the other half, so the strip always names both (same filters).
  const otherAgency: CompanyAgencyFilter | null = agency === 'direct' ? 'agency' : agency === 'agency' ? 'direct' : null
  const otherParams = { family, category, agency: otherAgency ?? 'agency', min_active: effectiveMin, limit: 1 } as const
  const { data: other } = useSWR<CompanyStatsResponse>(
    otherAgency ? ['companies-stats-other', JSON.stringify(otherParams)] : null,
    () => companiesApi.getStats(otherParams),
    { revalidateOnFocus: false },
  )

  const categories = useMemo(() => {
    const set = new Set<string>(category ? [category] : [])
    for (const r of data?.rows ?? []) for (const c of Object.keys(r.category_counts)) set.add(c)
    return Array.from(set).sort()
  }, [data, category])

  const summary = data?.summary
  const focus = [family && familyLabel(family, families), category].filter(Boolean).join(' · ')
  const subtitle = focus ? `Who is hiring for ${focus}, and what they advertise` : 'Who is hiring in Singapore, and what they advertise'

  const noun = (n: number, a: CompanyAgencyFilter) =>
    a === 'direct' ? `direct employer${n === 1 ? '' : 's'}` : a === 'agency' ? `recruitment agenc${n === 1 ? 'y' : 'ies'}` : `compan${n === 1 ? 'y' : 'ies'}`

  return (
    <div className="space-y-5">
      <PageHeader title="Companies" subtitle={subtitle} />

      {/* Who placed the ads */}
      <div className="flex flex-wrap items-center gap-3">
        <div className={`inline-flex rounded-lg bg-slate-100 p-1 dark:bg-slate-800 ${q ? 'opacity-50' : ''}`} role="group" aria-label="Who placed the ads">
          {WHO.map((opt) => {
            const active = who === opt.value
            return (
              <button
                key={opt.value}
                type="button"
                aria-pressed={active}
                disabled={!!q}
                title={opt.title}
                onClick={() => setParam('who', opt.value === 'direct' ? '' : opt.value)}
                className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 disabled:cursor-not-allowed ${
                  active
                    ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-600 dark:text-slate-100'
                    : 'text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-slate-100'
                }`}
              >
                {opt.label}
              </button>
            )
          })}
        </div>
        {q && <span className="text-xs text-slate-400 dark:text-slate-500">Searching every company</span>}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[12rem]">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" aria-hidden />
          <input
            type="search"
            aria-label="Search companies"
            placeholder="Search a company…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm text-slate-800 dark:text-slate-200 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <select aria-label="Job type" className={selectCls} value={family} onChange={(e) => setParam('family', e.target.value)}>
          <option value="">All job types</option>
          {families
            .filter((f) => f.role_family !== 'other')
            .map((f) => (
              <option key={f.role_family} value={f.role_family}>
                {f.display_name}
              </option>
            ))}
        </select>
        <select aria-label="Industry" className={selectCls} value={category} onChange={(e) => setParam('category', e.target.value)}>
          <option value="">All industries</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <select
          aria-label="Minimum openings"
          className={selectCls}
          value={minActive}
          disabled={!!q}
          onChange={(e) => setParam('min_active', Number(e.target.value) === (family ? 3 : 10) ? '' : e.target.value)}
        >
          {MIN_ACTIVE_OPTIONS.map((n) => (
            <option key={n} value={n}>
              {n === 1 ? 'Any openings' : `${n}+ ${family ? familyLabel(family, families) : ''} openings`.replace(/\s+/g, ' ')}
            </option>
          ))}
        </select>
      </div>

      {/* Summary strip: always names both halves */}
      {summary && summary.companies > 0 && (
        <p className="text-sm text-slate-500 dark:text-slate-400">
          <span className="font-medium text-slate-700 dark:text-slate-200">{summary.companies.toLocaleString()}</span> {noun(summary.companies, agency)} ·{' '}
          <span className="font-medium text-slate-700 dark:text-slate-200">{summary.openings.toLocaleString()}</span> openings
          {otherAgency && other != null && other.total_matching > 0 && (
            <>
              {' '}
              · {other.total_matching.toLocaleString()} {noun(other.total_matching, otherAgency)} in the &ldquo;{WHO.find((w) => w.value === otherAgency)!.label}&rdquo; view
            </>
          )}
          {data && data.rows.length < data.total_matching && <> · showing top {data.rows.length}</>}
        </p>
      )}

      {/* Results */}
      <Card>
        <CardBody>
          {isLoading && !data && <div className="h-48 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />}
          {error && <EmptyState icon={Building2} message="Couldn't load companies" description="Try again later." />}
          {data && data.rows.length === 0 && (
            <EmptyState
              icon={Building2}
              message="No companies match"
              description={minActive > 1 && !q ? 'Lower the minimum openings or clear a filter.' : 'Try a different name or filter.'}
            />
          )}
          {data && data.rows.length > 0 && (
            <CompanyStatsTable
              rows={data.rows}
              sort={sort}
              onSort={(s) => setParam('sort', s === defaultSort ? '' : s)}
              familyRows={families}
              selectedFamily={family || undefined}
            />
          )}
        </CardBody>
      </Card>
      <p className="text-xs text-slate-400 dark:text-slate-500">
        &ldquo;Recruitment agency&rdquo; is a registration fact: SSIC 78 (employment agencies), or a recruitment-agency name
        confirmed by its registration. &ldquo;Posted before&rdquo;: {POSTED_BEFORE_TIP.charAt(0).toLowerCase() + POSTED_BEFORE_TIP.slice(1)}.
        Salary figures are the median advertised monthly base for the chosen job type, SGD. Openings count live ads.
      </p>
    </div>
  )
}

export default function CompaniesPage() {
  return (
    <Layout userSlot={<NavUserActions />}>
      <Suspense fallback={<div className="h-48 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />}>
        <CompaniesExplorer />
      </Suspense>
    </Layout>
  )
}
