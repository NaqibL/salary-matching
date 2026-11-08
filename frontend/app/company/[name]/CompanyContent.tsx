'use client'

import useSWR from 'swr'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import {
  Building2,
  Briefcase,
  TrendingUp,
  Clock,
  Repeat,
} from 'lucide-react'
import { companiesApi, dashboardApi } from '@/lib/api'
import type { CompanyProfile, CompanyJob, RoleFamilyRow } from '@/lib/types'
import { monthYear, payUnit, salaryRangeText } from '@/lib/repost'
import { familyColor, familyLabel } from '@/lib/roleFamilies'
import { AgencyTag } from '@/app/components/AgencyTag'
import { Layout } from '@/app/components/layout'
import NavUserActions from '@/app/components/NavUserActions'
import { Card, CardBody, PageHeader } from '@/components/design'

// ---------------------------------------------------------------------------
// Salary bar (same visual as salary checker)
// ---------------------------------------------------------------------------

function SalaryBar({ p25, p50, p75 }: { p25: number; p50: number; p75: number }) {
  const low = p25 * 0.85
  const high = p75 * 1.15
  const range = high - low
  const pct = (v: number) => `${Math.round(((v - low) / range) * 100)}%`

  return (
    <div className="mt-4 mb-2">
      <div className="relative h-6 rounded-full bg-slate-100 dark:bg-slate-700">
        <div
          className="absolute top-0 h-full rounded-full bg-indigo-100 dark:bg-indigo-900/40"
          style={{ left: pct(p25), width: `${Math.round(((p75 - p25) / range) * 100)}%` }}
        />
        <div className="absolute top-0 h-full w-px bg-indigo-400" style={{ left: pct(p25) }} />
        <div className="absolute top-0 h-full w-0.5 bg-indigo-600" style={{ left: pct(p50) }} />
        <div className="absolute top-0 h-full w-px bg-indigo-400" style={{ left: pct(p75) }} />
      </div>
      <div className="relative mt-1 text-xs text-slate-500 dark:text-slate-400" style={{ height: '16px' }}>
        <span className="absolute -translate-x-1/2" style={{ left: pct(p25) }}>P25</span>
        <span className="absolute -translate-x-1/2" style={{ left: pct(p50) }}>P50</span>
        <span className="absolute -translate-x-1/2" style={{ left: pct(p75) }}>P75</span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Job row
// ---------------------------------------------------------------------------

function formatSalary(min: number | null, max: number | null): string {
  const lo = min && min > 0 ? min : null
  const hi = max && max > 0 ? max : null
  if (lo == null && hi == null) return 'salary not stated'
  const unit = payUnit(hi ?? lo!)
  const k = (v: number) => (unit === '/mo' ? `$${(v / 1000).toFixed(1)}k` : `$${v.toLocaleString()}`)
  if (lo != null && hi != null) return `${k(lo)}–${k(hi)}${unit}`
  if (lo != null) return `from ${k(lo)}${unit}`
  return `up to ${k(hi!)}${unit}`
}

/** "EMPLOYMENT AGENCIES (EXCEPT ...)" → "Employment agencies" — SSIC descriptions are shouty and parenthetical. */
function titleCase(raw: string): string {
  const base = raw.split('(')[0].trim()
  if (!base) return ''
  const words = base.toLowerCase().split(/\s+/).map((w, i) => {
    const upper = w.toUpperCase()
    if (/^[a-z]{1,3}$/.test(w) && ['it', 'ai', 'hr', 'ict', 'r&d', 'f&b'].includes(w)) return upper
    return i === 0 ? w.charAt(0).toUpperCase() + w.slice(1) : w
  })
  return words.join(' ')
}

function formatRecency(isoStr: string): string {
  if (!isoStr) return ''
  const days = Math.floor((Date.now() - new Date(isoStr).getTime()) / 86_400_000)
  if (days === 0) return 'today'
  if (days === 1) return '1d ago'
  if (days < 30) return `${days}d ago`
  const months = Math.floor(days / 30)
  return `${months}mo ago`
}

function JobRow({ job, muted = false }: { job: CompanyJob; muted?: boolean }) {
  const salary = formatSalary(job.salary_min, job.salary_max)
  const recency = formatRecency(job.first_seen_at ?? job.last_seen_at)
  const seniority = job.inferred_seniority ?? job.position_levels[0] ?? null
  const et = job.employment_types[0] ?? null

  const titleEl = job.job_url ? (
    <a
      href={job.job_url}
      target="_blank"
      rel="noopener noreferrer"
      className="text-sm font-medium text-slate-800 dark:text-slate-200 hover:text-indigo-600 dark:hover:text-indigo-400 truncate block"
    >
      {job.title}
    </a>
  ) : (
    <span className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate block">
      {job.title}
    </span>
  )

  return (
    <div className={`flex items-start justify-between gap-3 py-3 border-b border-slate-100 dark:border-slate-800 last:border-0 ${muted ? 'opacity-60' : ''}`}>
      <div className="min-w-0">
        {titleEl}
        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-slate-500 dark:text-slate-400">
          {salary && <span>{salary}</span>}
          {seniority && <span>{seniority}</span>}
          {et && <span>{et}</span>}
          {job.min_years_experience != null && (
            <span>{job.min_years_experience}+ yrs</span>
          )}
        </div>
      </div>
      {recency && (
        <div className="shrink-0">
          <span className="text-xs text-slate-400 dark:text-slate-500 whitespace-nowrap flex items-center gap-1">
            <Clock size={11} />
            {recency}
          </span>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function CompanyContent({ companyName }: { companyName: string }) {
  const { data: profile, error, isLoading } = useSWR<CompanyProfile>(
    `company-profile-${companyName}`,
    () => companiesApi.getProfile(companyName),
    { revalidateOnFocus: false },
  )
  const { data: families } = useSWR<RoleFamilyRow[]>('dashboard-role-families', dashboardApi.getRoleFamilies, {
    revalidateOnFocus: false,
  })

  if (isLoading) {
    return (
      <Layout userSlot={<NavUserActions />}>
        <div className="space-y-4">
          <div className="h-10 w-64 animate-pulse rounded bg-slate-200 dark:bg-slate-700" />
          <div className="h-32 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />
          <div className="h-64 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />
        </div>
      </Layout>
    )
  }

  if (error || !profile) {
    return (
      <Layout userSlot={<NavUserActions />}>
        <Card>
          <CardBody>
            <p className="text-slate-500 dark:text-slate-400">
              Company not found or failed to load.
            </p>
          </CardBody>
        </Card>
      </Layout>
    )
  }

  // SGSAL-026: company_stats facts (null until the view has a row for this company)
  const stats = profile.stats ?? null
  const topReposted = profile.top_reposted ?? []
  const familyMix = stats
    ? Object.entries(stats.role_family_counts)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 8)
        .map(([key, value]) => ({ key, name: familyLabel(key, families), value }))
    : []
  const showStatsCharts = !!stats && stats.active_count >= 3
  const isAgency = !!stats?.is_agency
  const industry = stats?.ssic_description ? titleCase(stats.ssic_description) || null : null
  const oneIn = (num: number, den: number) => (num > 0 && den > 0 ? Math.max(1, Math.round(den / num)) : null)
  const repostOneIn = stats ? oneIn(stats.reposted_count, stats.active_count) : null
  const typicalRate = profile.benchmarks?.median_repost_rate ?? null
  const typicalOneIn = typicalRate != null && typicalRate > 0 ? Math.max(1, Math.round(1 / typicalRate)) : null

  const showSalary =
    !profile.stats?.is_agency &&
    profile.salary_p25 != null &&
    profile.salary_p50 != null &&
    profile.salary_p75 != null &&
    profile.salary_sample_size >= 3

  return (
    <Layout userSlot={<NavUserActions />}>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-wrap items-center gap-3">
          <PageHeader
            title={profile.company_name}
            subtitle={[
              industry ?? (isAgency ? 'Employment agency' : 'Employer'),
              `${profile.active_count} open role${profile.active_count !== 1 ? 's' : ''}`,
              stats?.first_seen ? `tracked since ${monthYear(stats.first_seen)}` : null,
            ]
              .filter(Boolean)
              .join(' · ')}
          />
          {isAgency && <AgencyTag size="sm" />}
        </div>

        {/* Stat row */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[
            {
              title: undefined as string | undefined,
              icon: <Briefcase size={18} className="text-indigo-500" />,
              label: 'Open roles',
              value: profile.active_count.toLocaleString(),
              sub: `${profile.total_count.toLocaleString()} postings since ${stats?.first_seen ? monthYear(stats.first_seen) : 'Mar 2026'}`,
            },
            {
              icon: <TrendingUp size={18} className="text-emerald-500" />,
              label: 'Median advertised monthly base',
              value: !isAgency && profile.salary_p50 != null ? `$${profile.salary_p50.toLocaleString()}` : '—',
              sub: isAgency
                ? 'not shown for agencies: roles span many fields'
                : profile.salary_p50 != null
                  ? `across all live roles · ${profile.salary_sample_size.toLocaleString()} ads · SGD`
                  : 'no disclosed salaries',
            },
            {
              icon: <Clock size={18} className="text-amber-500" />,
              label: 'Experience asked',
              value: profile.avg_min_experience != null ? `${profile.avg_min_experience} yrs` : '—',
              sub: 'average minimum in their ads',
            },
            {
              icon: <Repeat size={18} className="text-indigo-400" />,
              label: 'Posted before',
              value: repostOneIn != null ? `1 in ${repostOneIn}` : stats ? 'none' : '—',
              sub:
                typicalOneIn != null
                  ? `of live ads · typical company 1 in ${typicalOneIn}`
                  : 'of live ads were posted before',
              title:
                'Share of this company\'s live ads whose exact text was posted before. Reposting can mean ongoing hiring, high turnover or an agency re-running a client role.',
            },
          ].map(({ icon, label, value, sub, title }) => (
            <Card key={label} size="compact" title={title}>
              <CardBody>
                <div className="flex items-center gap-2 mb-1">{icon}</div>
                <p className="text-xl font-semibold text-slate-800 dark:text-slate-100">{value}</p>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{label}</p>
                {sub && <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-0.5">{sub}</p>}
              </CardBody>
            </Card>
          ))}
        </div>

        {/* Salary overview */}
        {showSalary && (
          <Card>
            <CardBody>
              <h2 className="text-base font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Salary range
              </h2>
              <p className="text-xs text-slate-400 dark:text-slate-500 mb-2">
                Based on {profile.salary_sample_size} posting{profile.salary_sample_size !== 1 ? 's' : ''} with disclosed salary
              </p>
              <div className="flex justify-between text-sm text-slate-600 dark:text-slate-300 mb-1">
                <span>P25 — ${profile.salary_p25!.toLocaleString()}</span>
                <span className="font-medium">P50 — ${profile.salary_p50!.toLocaleString()}</span>
                <span>P75 — ${profile.salary_p75!.toLocaleString()}</span>
              </div>
              <SalaryBar
                p25={profile.salary_p25!}
                p50={profile.salary_p50!}
                p75={profile.salary_p75!}
              />
            </CardBody>
          </Card>
        )}

        {/* Reposting (SGSAL-026) */}
        {stats && (
          <Card>
            <CardBody>
              <h2 className="text-base font-semibold text-slate-700 dark:text-slate-300 mb-1 flex items-center gap-2">
                <Repeat size={16} aria-hidden /> Posted before
              </h2>
              {stats.multi_company_count > 0 && (
                <p className="text-sm text-slate-700 dark:text-slate-200 mb-1">
                  {stats.multi_company_count.toLocaleString()} of their live ads also appear under other company names.
                </p>
              )}
              <p className="text-xs text-slate-400 dark:text-slate-500 mb-3">
                {stats.reposted_count.toLocaleString()} of {stats.active_count.toLocaleString()} live ads were posted before
                {stats.distinct_postings < stats.active_count && (
                  <> · {stats.active_count.toLocaleString()} listings, {stats.distinct_postings.toLocaleString()} distinct ads</>
                )}
                {typicalOneIn != null && <> · typical company: 1 in {typicalOneIn}</>}
              </p>
              {topReposted.length === 0 ? (
                <p className="text-sm text-slate-400 dark:text-slate-500 py-2">None of their live ads has been posted before.</p>
              ) : (
                <div className="divide-y divide-slate-100 dark:divide-slate-800">
                  {topReposted.map((r) => (
                    <div key={r.canonical_job_uuid} className="flex items-start justify-between gap-3 py-2">
                      <div className="min-w-0">
                        <div className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate" title={r.title ?? ''}>
                          {r.title ?? '—'}
                        </div>
                        <div className="text-xs text-slate-500 dark:text-slate-400">
                          Posted {r.repost_count} times, {monthYear(r.first_posted) || '?'} to {monthYear(r.last_posted) || '?'}
                          {r.distinct_companies >= 2 && <> · under {r.distinct_companies} company names</>}
                        </div>
                      </div>
                      <div className="shrink-0 text-xs text-slate-500 dark:text-slate-400 whitespace-nowrap">
                        {salaryRangeText(r.latest_salary_min, r.latest_salary_max) ?? ''}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardBody>
          </Card>
        )}

        {/* What they hire for (SGSAL-026/028) */}
        {showStatsCharts && familyMix.length > 0 && (
          <Card>
            <CardBody>
              <h2 className="text-base font-semibold text-slate-700 dark:text-slate-300 mb-1">What they hire for</h2>
              <p className="text-xs text-slate-400 dark:text-slate-500 mb-3">Live ads by job type</p>
              <ResponsiveContainer width="100%" height={Math.max(160, familyMix.length * 28)}>
                <BarChart data={familyMix} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 0 }}>
                  <XAxis type="number" hide />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={170}
                    tick={{ fontSize: 11, fill: 'currentColor' }}
                    className="text-slate-600 dark:text-slate-400"
                  />
                  <Tooltip formatter={(v: number) => [v, 'live ads']} contentStyle={{ fontSize: 12 }} />
                  <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                    {familyMix.map((d) => (
                      <Cell key={d.key} fill={familyColor(d.key)} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </CardBody>
          </Card>
        )}

        {/* Latest openings */}
        <Card>
          <CardBody>
            <h2 className="text-base font-semibold text-slate-700 dark:text-slate-300 mb-3 flex items-center gap-2">
              <Briefcase size={16} />
              Latest openings
              <span className="ml-auto text-xs font-normal text-slate-400">
                {profile.active_jobs.length} role{profile.active_jobs.length !== 1 ? 's' : ''}
              </span>
            </h2>
            {profile.active_jobs.length === 0 ? (
              <p className="text-sm text-slate-400 dark:text-slate-500 py-4 text-center">
                No active listings right now.
              </p>
            ) : (
              profile.active_jobs.map((job) => <JobRow key={job.job_uuid} job={job} />)
            )}
          </CardBody>
        </Card>



      </div>
    </Layout>
  )
}
