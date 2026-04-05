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
import { BarChart2, Scale, Briefcase, ArrowRight } from 'lucide-react'
import { dashboardApi } from '@/lib/api'
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
    icon: Scale,
    title: 'Lowball Checker',
    description:
      'Paste a job description and salary offer to instantly see where it sits in the market — ranked by percentile against similar roles.',
    href: '/lowball',
    auth: false,
    iconColor: 'text-violet-600 dark:text-violet-400',
    iconBg: 'bg-violet-50 dark:bg-violet-950/50',
    accentBorder: 'border-t-violet-500 dark:border-t-violet-400',
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

        {/* ── Page title ───────────────────────────────────────────────────── */}
        <section>
          <h1 className="text-2xl font-semibold text-slate-900 dark:text-slate-100">
            MCF Job Matcher
          </h1>
          <p className="mt-2 text-sm text-slate-500 dark:text-slate-400 leading-relaxed max-w-xl">
            A set of tools built on live{' '}
            <a
              href="https://www.mycareersfuture.gov.sg"
              target="_blank"
              rel="noopener noreferrer"
              className="text-slate-600 dark:text-slate-400 underline underline-offset-2 hover:text-slate-900 dark:hover:text-slate-200"
            >
              MyCareersFuture
            </a>{' '}
            data to help you understand the Singapore job market — explore hiring trends,
            check whether a salary offer is competitive, or match your resume to active roles.
          </p>
        </section>

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
