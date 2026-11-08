'use client'

import useSWR from 'swr'
import { BarChart2, Database } from 'lucide-react'
import { dashboardApi } from '@/lib/api'
import type { MarketStats, RoleFamilyRow } from '@/lib/types'
import { Layout } from '../components/layout'
import NavUserActions from '../components/NavUserActions'
import { Card, CardBody, EmptyState } from '@/components/design'
import { DASHBOARD_SWR_CONFIG } from '@/lib/swr-config'
import { DashboardErrorBoundary } from './DashboardErrorBoundary'
import { MarketSummary } from './MarketSummary'
import { JobsOverTimeChart } from './JobsOverTimeChart'
import { JobTypesTable } from './JobTypesTable'
import { SeniorityTable } from './SeniorityTable'
import { SkillsChart } from './SkillsChart'
import { PostedBeforeSection } from './PostedBeforeSection'
import type { JobsPostedRemovedPoint } from './JobsOverTimeChart'

const TRACKED_SINCE = 'Mar 2026'

const SECTIONS = [
  { id: 'this-week', label: 'This week' },
  { id: 'job-types', label: 'Job types' },
  { id: 'skills', label: 'Skills' },
  { id: 'posted-before', label: 'Posted before' },
]

export interface DashboardContentProps {
  initialStats: MarketStats | null
  initialJobsOverTime: JobsPostedRemovedPoint[] | null
  /** Total postings tracked since the first crawl, for the subtitle. */
  trackedTotal?: number | null
}

function Section({ id, title, sub, children }: { id: string; title: string; sub?: string; children: React.ReactNode }) {
  return (
    <section id={id} className="scroll-mt-20 space-y-4">
      <div>
        <h2 className="text-lg font-semibold leading-tight text-slate-900 dark:text-slate-100">{title}</h2>
        {sub && <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{sub}</p>}
      </div>
      {children}
    </section>
  )
}

function asOf(iso: string | null | undefined): string | null {
  if (!iso) return null
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? null : d.toLocaleDateString('en-SG', { day: 'numeric', month: 'short', year: 'numeric' })
}

/**
 * Public market dashboard (SGSAL-030). Four sections in the order a job seeker asks the
 * questions: how is the market this week, what does my kind of job pay and is it growing,
 * which skills are asked for, how much of what I see is repeated ad text. One scroll, no tabs;
 * every number reads from the market_stats view and says its scope.
 */
export function DashboardContent({ initialStats, initialJobsOverTime, trackedTotal }: DashboardContentProps) {
  const { data: stats, error, isLoading } = useSWR<MarketStats>('dashboard-market-stats', dashboardApi.getMarketStats, {
    ...DASHBOARD_SWR_CONFIG,
    fallbackData: initialStats ?? undefined,
  })
  const { data: familyRows = [] } = useSWR<RoleFamilyRow[]>('dashboard-role-families', dashboardApi.getRoleFamilies, DASHBOARD_SWR_CONFIG)

  const ready = !!stats?.totals
  const updated = asOf(stats?.computed_at)

  return (
    <Layout userSlot={<NavUserActions />}>
      <DashboardErrorBoundary>
        <div className="-mx-4 lg:-mx-8 px-4 lg:px-8 pt-10 pb-8 mb-6 bg-gradient-to-br from-indigo-50/60 via-white to-slate-50 dark:from-indigo-950/15 dark:via-slate-900 dark:to-slate-900 border-b border-slate-200/70 dark:border-slate-800">
          <div className="flex items-center gap-3">
            <div className="flex size-11 items-center justify-center rounded-xl bg-indigo-100 dark:bg-indigo-950/50">
              <BarChart2 className="size-5 text-indigo-600 dark:text-indigo-400" />
            </div>
            <div>
              <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-100">Dashboard</h1>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Every MyCareersFuture and Careers@Gov ad since {TRACKED_SINCE}
                {trackedTotal ? ` · ${trackedTotal.toLocaleString()} tracked` : ''}
                {stats?.totals ? ` · ${stats.totals.live.toLocaleString()} live` : ''}
                {updated ? ` · updated ${updated}` : ' · updated daily'}
              </p>
            </div>
          </div>
          <nav aria-label="Sections" className="mt-4 flex gap-2 overflow-x-auto text-xs">
            {SECTIONS.map((s) => (
              <a
                key={s.id}
                href={`#${s.id}`}
                className="shrink-0 rounded-full border border-slate-200 dark:border-slate-700 px-3 py-1 text-slate-600 dark:text-slate-300 hover:border-indigo-300 hover:text-indigo-700 dark:hover:text-indigo-300"
              >
                {s.label}
              </a>
            ))}
          </nav>
        </div>

        {!ready && isLoading ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="h-24 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />
              ))}
            </div>
            <div className="h-72 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />
          </div>
        ) : !ready ? (
          <Card className="border-slate-200 dark:border-slate-700">
            <CardBody>
              <EmptyState
                icon={Database}
                message={error ? "Couldn't load the dashboard" : 'No dashboard data yet'}
                description={error ? 'Try again in a minute.' : 'Market figures appear after the first daily crawl.'}
              />
            </CardBody>
          </Card>
        ) : (
          <div className="space-y-10">
            <Section id="this-week" title="This week">
              <MarketSummary stats={stats} />
              <JobsOverTimeChart fallbackData={initialJobsOverTime} />
            </Section>

            <Section
              id="job-types"
              title="Job types"
              sub="Live ads, pay and how fast each type is being posted · pay is the median advertised monthly base, SGD · new = ads first seen in the last 7 days. Click a job type to see who is hiring for it."
            >
              <div className="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
                <Card className="border-slate-200 dark:border-slate-700">
                  <CardBody>
                    <JobTypesTable families={stats!.families} familyRows={familyRows} />
                  </CardBody>
                </Card>
                <Card className="border-slate-200 dark:border-slate-700 self-start">
                  <CardBody>
                    <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">Pay by seniority</h3>
                    <p className="text-xs text-slate-400 dark:text-slate-500 mb-3">
                      live ads whose text states a level · median advertised monthly base, SGD
                    </p>
                    <SeniorityTable />
                  </CardBody>
                </Card>
              </div>
            </Section>

            <Section id="skills" title="Most requested skills">
              <Card className="border-slate-200 dark:border-slate-700">
                <CardBody>
                  <SkillsChart familyRows={familyRows} />
                </CardBody>
              </Card>
            </Section>

            <Section
              id="posted-before"
              title="Posted before"
              sub="How much of the market is the same ad text posted again. A repeat can mean ongoing hiring, high turnover or an agency re-running a client role."
            >
              <PostedBeforeSection stats={stats!} familyRows={familyRows} />
            </Section>

            <p className="text-xs text-slate-400 dark:text-slate-500 border-t border-slate-200 dark:border-slate-800 pt-4">
              Source: every MyCareersFuture and Careers@Gov ad since {TRACKED_SINCE}, updated daily. Salary figures are the median
              advertised monthly base of ads with a compliant range. &ldquo;Posted before&rdquo; means the exact ad text was posted
              earlier, under any company name. &ldquo;Recruitment agency&rdquo; is a registration fact: SSIC 78, or a
              recruitment-agency name confirmed by its registration.
            </p>
          </div>
        )}
      </DashboardErrorBoundary>
    </Layout>
  )
}
