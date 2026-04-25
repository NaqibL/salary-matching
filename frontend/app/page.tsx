'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { BarChart2, Scale, Briefcase, ArrowRight, Loader2 } from 'lucide-react'
import { dashboardApi, lowballApi } from '@/lib/api'
import type { LowballResult } from '@/lib/types'
import { Layout } from './components/layout'
import NavUserActions from './components/NavUserActions'
import { Card, CardBody } from '@/components/design'
import { Skeleton } from '@/components/ui/skeleton'
import { isSupabaseConfigured } from '@/lib/supabase'

type ActiveJobsPoint = { date: string; active_count: number }

function formatDate(d: string) {
  return new Date(d).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

const tools = [
  {
    icon: Scale,
    title: 'Salary Search',
    description:
      'See the pay range for any role in Singapore — instantly, from live MCF data. Check if an offer is competitive.',
    href: '/lowball',
    auth: false,
    iconColor: 'text-violet-600 dark:text-violet-400',
    iconBg: 'bg-violet-50 dark:bg-violet-950/50',
    accentBorder: 'border-t-violet-500 dark:border-t-violet-400',
  },
  {
    icon: BarChart2,
    title: 'Market Dashboard',
    description:
      'Explore salary distributions, hiring trends by category and seniority, and active job counts — updated daily from live MCF data.',
    href: '/dashboard',
    auth: false,
    iconColor: 'text-indigo-600 dark:text-indigo-400',
    iconBg: 'bg-indigo-50 dark:bg-indigo-950/50',
    accentBorder: 'border-t-indigo-500 dark:border-t-indigo-400',
  },
  {
    icon: Briefcase,
    title: 'Resume Matching',
    description:
      'Upload your resume to get roles ranked by relevance. Rate jobs to build a taste profile that improves over time.',
    href: '/matches',
    auth: true,
    iconColor: 'text-emerald-600 dark:text-emerald-400',
    iconBg: 'bg-emerald-50 dark:bg-emerald-950/50',
    accentBorder: 'border-t-emerald-500 dark:border-t-emerald-400',
  },
]

function HeroSalaryChecker() {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [salary, setSalary] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<LowballResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const fmt = (v: number) => `$${v.toLocaleString()}`

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const salaryValue = salary ? parseInt(salary, 10) : undefined
      const data = await lowballApi.check(title, description, salaryValue)
      setResult(data)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  const VERDICT_LABELS: Record<string, string> = {
    lowballed: 'You may be lowballed',
    below_median: 'Below market median',
    at_median: 'Around market median',
    above_median: 'Above market rate',
    insufficient_data: 'Not enough data',
    market_data: 'Pay range for similar roles',
  }
  const VERDICT_COLORS: Record<string, string> = {
    lowballed: 'text-red-600 dark:text-red-400',
    below_median: 'text-amber-600 dark:text-amber-400',
    at_median: 'text-green-600 dark:text-green-400',
    above_median: 'text-green-600 dark:text-green-400',
    insufficient_data: 'text-slate-500 dark:text-slate-400',
    market_data: 'text-violet-600 dark:text-violet-400',
  }

  return (
    <section className="-mx-4 lg:-mx-8 px-4 lg:px-8 pt-10 pb-10 bg-gradient-to-br from-violet-50/60 via-white to-slate-50 dark:from-violet-950/15 dark:via-slate-900 dark:to-slate-900 border-b border-slate-200/70 dark:border-slate-800 mb-8">
      <div className="max-w-2xl">
        <div className="flex items-center gap-3 mb-2">
          <div className="flex size-10 items-center justify-center rounded-xl bg-violet-100 dark:bg-violet-950/50">
            <Scale className="size-5 text-violet-600 dark:text-violet-400" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
            Know your market value
          </h1>
        </div>
        <p className="mb-6 text-sm text-slate-500 dark:text-slate-400 leading-relaxed">
          Enter a job title and description to see the pay range from live Singapore listings. Optionally enter an offer to see where you stand.
        </p>

        {!result ? (
          <form onSubmit={handleSubmit} className="flex flex-col gap-3">
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              placeholder="Job title, e.g. Senior Software Engineer"
              className="w-full rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2.5 text-sm text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-violet-500"
            />
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              required
              minLength={20}
              placeholder="Paste the job description here…"
              className="w-full rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2.5 text-sm text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-violet-500 resize-y"
            />
            <div className="flex items-center gap-3 flex-wrap">
              <input
                type="number"
                value={salary}
                onChange={(e) => setSalary(e.target.value)}
                min={100}
                placeholder="Offered salary (SGD/mo, optional)"
                className="rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2 text-sm text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-violet-500 w-64"
              />
              <button
                type="submit"
                disabled={loading}
                className="flex items-center gap-2 rounded-lg bg-violet-600 hover:bg-violet-700 disabled:opacity-60 text-white px-5 py-2 text-sm font-semibold transition-all shadow-sm"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Scale className="w-4 h-4" />}
                {salary ? 'Check my offer' : 'Get market rates'}
              </button>
            </div>
            {error && (
              <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
            )}
          </form>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-4">
              <span className={`text-lg font-bold ${VERDICT_COLORS[result.verdict]}`}>
                {VERDICT_LABELS[result.verdict]}
              </span>
              {result.offered_salary != null && result.percentile != null && (
                <span className="text-sm text-slate-500 dark:text-slate-400">
                  {fmt(result.offered_salary)}/mo · {result.percentile}th percentile
                </span>
              )}
            </div>
            {result.market_p25 != null && (
              <div className="flex gap-6">
                {[
                  { label: 'P25', value: result.market_p25 },
                  { label: 'Median', value: result.market_p50 },
                  { label: 'P75', value: result.market_p75 },
                ].map(({ label, value }) => value != null && (
                  <div key={label} className="text-center">
                    <p className="text-xs text-slate-500 dark:text-slate-400 uppercase tracking-wide">{label}</p>
                    <p className="text-base font-bold text-slate-800 dark:text-slate-200">{fmt(value)}</p>
                  </div>
                ))}
              </div>
            )}
            <div className="flex items-center gap-4">
              <Link
                href="/lowball"
                className="text-sm font-semibold text-violet-600 dark:text-violet-400 hover:underline flex items-center gap-1"
              >
                See full analysis <ArrowRight className="size-3" />
              </Link>
              <button
                onClick={() => { setResult(null); setTitle(''); setDescription(''); setSalary('') }}
                className="text-sm text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
              >
                ← Check another
              </button>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}

export default function HomePage() {
  const [activeJobs, setActiveJobs] = useState<ActiveJobsPoint[]>([])
  const [activeCount, setActiveCount] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      dashboardApi.getActiveJobsOverTimePublic(30).then(setActiveJobs).catch(() => null),
      dashboardApi.getSummaryPublic().then((s) => setActiveCount(s.active_jobs)).catch(() => null),
    ]).finally(() => setLoading(false))
  }, [])

  return (
    <Layout userSlot={<NavUserActions />}>
      <div className="flex flex-col gap-10">

        {/* ── Hero salary checker ──────────────────────────────────────────── */}
        <HeroSalaryChecker />

        {/* ── Tools ────────────────────────────────────────────────────────── */}
        <section>
          <div className="mb-8">
            <h2 className="text-2xl font-semibold text-slate-900 dark:text-slate-100">
              What you can do
            </h2>
            <p className="mt-1.5 text-sm text-slate-500 dark:text-slate-400">
              Three tools to help you navigate the Singapore job market.
            </p>
          </div>

          <div className="grid gap-5 sm:grid-cols-3">
            {tools.map(({ icon: Icon, title, description, href, auth, iconColor, iconBg, accentBorder }) => (
              <Link key={href} href={href} className="group block">
                <Card
                  className={`h-full border-t-4 ${accentBorder} transition-all hover:shadow-lg hover:-translate-y-0.5`}
                >
                  <CardBody className="flex flex-col gap-4">
                    <div className={`flex size-10 items-center justify-center rounded-xl ${iconBg}`}>
                      <Icon className={`size-5 ${iconColor}`} />
                    </div>
                    <div className="flex-1">
                      <p className="text-base font-semibold text-slate-900 dark:text-slate-100">
                        {title}
                      </p>
                      <p className="mt-1.5 text-sm leading-relaxed text-slate-500 dark:text-slate-400">
                        {description}
                      </p>
                    </div>
                    <div className="flex items-center justify-between pt-1">
                      {auth && isSupabaseConfigured ? (
                        <span className="text-xs text-slate-400 dark:text-slate-500">
                          Sign in required
                        </span>
                      ) : (
                        <span />
                      )}
                      <span
                        className={`flex items-center gap-1 text-xs font-semibold ${iconColor} opacity-0 transition-opacity group-hover:opacity-100`}
                      >
                        Open <ArrowRight className="size-3" />
                      </span>
                    </div>
                  </CardBody>
                </Card>
              </Link>
            ))}
          </div>
        </section>

        {/* ── Live data ────────────────────────────────────────────────────── */}
        <section className="pb-2">
          <div className="mb-6 flex items-start justify-between gap-4">
            <div>
              <h2 className="text-2xl font-semibold text-slate-900 dark:text-slate-100">
                Live job market
              </h2>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                Active listings tracked over the last 30 days.
              </p>
            </div>
            {!loading && activeCount !== null && (
              <div className="shrink-0 text-right">
                <p className="text-3xl font-bold tabular-nums text-slate-900 dark:text-slate-100">
                  {activeCount.toLocaleString()}
                </p>
                <p className="text-xs text-slate-500 dark:text-slate-400">active now</p>
              </div>
            )}
          </div>

          <Card>
            <CardBody>
              {loading ? (
                <Skeleton className="h-52 w-full rounded-lg" />
              ) : activeJobs.length > 0 ? (
                <div className="h-52">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={activeJobs} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                      <defs>
                        <linearGradient id="homeActiveGradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="rgb(99,102,241)" stopOpacity={0.18} />
                          <stop offset="95%" stopColor="rgb(99,102,241)" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgb(226,232,240)" />
                      <XAxis
                        dataKey="date"
                        tickFormatter={formatDate}
                        fontSize={11}
                        tick={{ fill: 'rgb(148,163,184)' }}
                      />
                      <YAxis fontSize={11} tick={{ fill: 'rgb(148,163,184)' }} width={40} />
                      <Tooltip
                        formatter={(v: number) => [v.toLocaleString(), 'Active jobs']}
                        labelFormatter={formatDate}
                        contentStyle={{ fontSize: 12 }}
                      />
                      <Area
                        type="monotone"
                        dataKey="active_count"
                        stroke="rgb(99,102,241)"
                        strokeWidth={2}
                        fill="url(#homeActiveGradient)"
                        dot={false}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <div className="flex h-52 items-center justify-center text-sm text-slate-400">
                  No data available
                </div>
              )}
            </CardBody>
          </Card>
        </section>

      </div>
    </Layout>
  )
}
