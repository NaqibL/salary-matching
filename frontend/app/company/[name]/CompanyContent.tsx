'use client'

import { useState } from 'react'
import Link from 'next/link'
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
  History,
  TrendingUp,
  Clock,
  ExternalLink,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import { companiesApi } from '@/lib/api'
import type { CompanyProfile, CompanyJob } from '@/lib/types'
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
  if (!min && !max) return ''
  if (min && max) return `$${(min / 1000).toFixed(1)}k–$${(max / 1000).toFixed(1)}k`
  if (min) return `from $${(min / 1000).toFixed(1)}k`
  return `up to $${(max! / 1000).toFixed(1)}k`
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

  return (
    <div className={`flex items-start justify-between gap-3 py-3 border-b border-slate-100 dark:border-slate-800 last:border-0 ${muted ? 'opacity-60' : ''}`}>
      <div className="min-w-0">
        <Link
          href={`/job/${job.job_uuid}`}
          className="text-sm font-medium text-slate-800 dark:text-slate-200 hover:text-indigo-600 dark:hover:text-indigo-400 truncate block"
        >
          {job.title}
        </Link>
        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-slate-500 dark:text-slate-400">
          {salary && <span>{salary}</span>}
          {seniority && <span>{seniority}</span>}
          {et && <span>{et}</span>}
          {job.min_years_experience != null && (
            <span>{job.min_years_experience}+ yrs</span>
          )}
        </div>
      </div>
      <div className="shrink-0 flex items-center gap-2">
        {recency && (
          <span className="text-xs text-slate-400 dark:text-slate-500 whitespace-nowrap flex items-center gap-1">
            <Clock size={11} />
            {recency}
          </span>
        )}
        {job.job_url && (
          <a
            href={job.job_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-slate-400 hover:text-indigo-500"
          >
            <ExternalLink size={13} />
          </a>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function CompanyContent({ companyName }: { companyName: string }) {
  const [showClosed, setShowClosed] = useState(false)

  const { data: profile, error, isLoading } = useSWR<CompanyProfile>(
    `company-profile-${companyName}`,
    () => companiesApi.getProfile(companyName),
    { revalidateOnFocus: false },
  )

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

  const posLevels = Object.entries(profile.position_levels)
    .sort((a, b) => b[1] - a[1])
    .map(([name, value]) => ({ name, value }))
  const empTypes = Object.entries(profile.employment_types)
    .sort((a, b) => b[1] - a[1])
    .map(([name, value]) => ({ name, value }))

  const showCharts = profile.total_count >= 3
  const showSalary =
    profile.salary_p25 != null &&
    profile.salary_p50 != null &&
    profile.salary_p75 != null &&
    profile.salary_sample_size >= 3

  return (
    <Layout userSlot={<NavUserActions />}>
      <div className="space-y-6">
        {/* Header */}
        <PageHeader
          title={profile.company_name}
          subtitle={`${profile.active_count} active opening${profile.active_count !== 1 ? 's' : ''} · ${profile.total_count} total seen`}
        />

        {/* Stat row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            {
              icon: <Briefcase size={18} className="text-indigo-500" />,
              label: 'Active openings',
              value: profile.active_count,
            },
            {
              icon: <History size={18} className="text-slate-400" />,
              label: 'Total seen',
              value: profile.total_count,
            },
            {
              icon: <TrendingUp size={18} className="text-emerald-500" />,
              label: 'Median salary',
              value: profile.salary_p50 != null
                ? `$${(profile.salary_p50 / 1000).toFixed(1)}k/mo`
                : '—',
            },
            {
              icon: <Clock size={18} className="text-amber-500" />,
              label: 'Avg min exp',
              value: profile.avg_min_experience != null
                ? `${profile.avg_min_experience} yrs`
                : '—',
            },
          ].map(({ icon, label, value }) => (
            <Card key={label} size="compact">
              <CardBody>
                <div className="flex items-center gap-2 mb-1">{icon}</div>
                <p className="text-xl font-semibold text-slate-800 dark:text-slate-100">{value}</p>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{label}</p>
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

        {/* Active openings */}
        <Card>
          <CardBody>
            <h2 className="text-base font-semibold text-slate-700 dark:text-slate-300 mb-3 flex items-center gap-2">
              <Briefcase size={16} />
              Active openings
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

        {/* Hiring patterns */}
        {showCharts && (posLevels.length > 0 || empTypes.length > 0) && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {posLevels.length > 0 && (
              <Card>
                <CardBody>
                  <h2 className="text-base font-semibold text-slate-700 dark:text-slate-300 mb-4">
                    Position levels
                  </h2>
                  <ResponsiveContainer width="100%" height={180}>
                    <BarChart
                      data={posLevels}
                      layout="vertical"
                      margin={{ top: 0, right: 16, bottom: 0, left: 0 }}
                    >
                      <XAxis type="number" hide />
                      <YAxis
                        type="category"
                        dataKey="name"
                        width={110}
                        tick={{ fontSize: 12, fill: 'currentColor' }}
                        className="text-slate-600 dark:text-slate-400"
                      />
                      <Tooltip
                        formatter={(v: number) => [v, 'jobs']}
                        contentStyle={{ fontSize: 12 }}
                      />
                      <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                        {posLevels.map((_, i) => (
                          <Cell key={i} fill={i === 0 ? '#6366f1' : '#c7d2fe'} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </CardBody>
              </Card>
            )}
            {empTypes.length > 0 && (
              <Card>
                <CardBody>
                  <h2 className="text-base font-semibold text-slate-700 dark:text-slate-300 mb-4">
                    Employment types
                  </h2>
                  <ResponsiveContainer width="100%" height={180}>
                    <BarChart
                      data={empTypes}
                      layout="vertical"
                      margin={{ top: 0, right: 16, bottom: 0, left: 0 }}
                    >
                      <XAxis type="number" hide />
                      <YAxis
                        type="category"
                        dataKey="name"
                        width={110}
                        tick={{ fontSize: 12, fill: 'currentColor' }}
                        className="text-slate-600 dark:text-slate-400"
                      />
                      <Tooltip
                        formatter={(v: number) => [v, 'jobs']}
                        contentStyle={{ fontSize: 12 }}
                      />
                      <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                        {empTypes.map((_, i) => (
                          <Cell key={i} fill={i === 0 ? '#10b981' : '#a7f3d0'} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </CardBody>
              </Card>
            )}
          </div>
        )}

        {/* Top skills */}
        {profile.top_skills.length > 0 && (
          <Card>
            <CardBody>
              <h2 className="text-base font-semibold text-slate-700 dark:text-slate-300 mb-3">
                Top skills
              </h2>
              <div className="flex flex-wrap gap-2">
                {profile.top_skills.map(([skill, count]) => (
                  <span
                    key={skill}
                    className="px-2.5 py-1 rounded-full bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 text-xs font-medium"
                  >
                    {skill} ×{count}
                  </span>
                ))}
              </div>
            </CardBody>
          </Card>
        )}

        {/* Recently closed */}
        {profile.recent_closed.length > 0 && (
          <Card>
            <CardBody>
              <button
                type="button"
                onClick={() => setShowClosed((v) => !v)}
                className="w-full flex items-center justify-between text-base font-semibold text-slate-700 dark:text-slate-300"
              >
                <span className="flex items-center gap-2">
                  <History size={16} />
                  Recently closed
                  <span className="text-xs font-normal text-slate-400">
                    ({profile.recent_closed.length})
                  </span>
                </span>
                {showClosed ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </button>
              {showClosed && (
                <div className="mt-3">
                  {profile.recent_closed.map((job) => (
                    <JobRow key={job.job_uuid} job={job} muted />
                  ))}
                </div>
              )}
            </CardBody>
          </Card>
        )}
      </div>
    </Layout>
  )
}
