'use client'

import { useEffect, useMemo, useState } from 'react'
import useSWR from 'swr'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Layers, Sparkles, TrendingUp, Users } from 'lucide-react'
import { dashboardApi } from '@/lib/api'
import type { RoleFamilyRow, SeniorityBreakdownRow, SkillsTrendRow, TopSkillRow } from '@/lib/types'
import { EmptyState } from '@/components/design'
import { DASHBOARD_SWR_CONFIG } from '@/lib/swr-config'

// ── Constants ─────────────────────────────────────────────────────────────────

const TREND_WEEKS = 12
const TREND_POOL = 8 // skills fetched for the trend (backend cap)
const TREND_DEFAULT = 5 // lines shown by default
const TOP_SKILLS_SHOWN = 20
const TOP_SKILLS_FETCHED = 25

const COLOR_JOBS = 'rgb(99, 102, 241)' // indigo — counts, matches the category chart
const COLOR_SALARY = 'rgb(16, 185, 129)' // emerald — salary, matches the salary chart

// Fixed-order categorical palette for the trend lines. Color follows the skill's
// slot in the top-8 pool, never its rank among the visible lines, so toggling a
// line never repaints the others.
const SERIES_COLORS = [
  'rgb(99, 102, 241)',
  'rgb(16, 185, 129)',
  'rgb(245, 158, 11)',
  'rgb(244, 63, 94)',
  'rgb(14, 165, 233)',
  'rgb(139, 92, 246)',
  'rgb(13, 148, 136)',
  'rgb(161, 98, 7)',
]

const TICK = { fontSize: 11, fill: 'currentColor' }
const CARD = 'rounded-xl border border-slate-200 bg-white p-6 shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-800'
const CHART_TEXT = 'text-slate-500 dark:text-slate-400'

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtMoney(v: number | null | undefined): string {
  return v == null ? '—' : `$${(v / 1000).toFixed(1)}k`
}

function fmtWeek(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

type TooltipEntry = {
  name?: string
  value?: number | string
  color?: string
  dataKey?: string | number
  payload?: Record<string, unknown>
}

interface ChartTooltipProps {
  active?: boolean
  payload?: TooltipEntry[]
  label?: string | number
  labelFormatter?: (label: string) => string
  /** Extra rows derived from the hovered data point (e.g. median salary). */
  extra?: (row: Record<string, unknown>) => Array<{ label: string; value: string }>
}

/** Tailwind-styled tooltip so it follows dark mode (Recharts' default is white-only). */
function ChartTooltip({ active, payload, label, labelFormatter, extra }: ChartTooltipProps) {
  if (!active || !payload || payload.length === 0) return null
  const row = payload[0]?.payload ?? {}
  const extras = extra ? extra(row) : []
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-md dark:border-slate-700 dark:bg-slate-900">
      {label != null && (
        <div className="mb-1 font-medium text-slate-900 dark:text-slate-100">
          {labelFormatter ? labelFormatter(String(label)) : String(label)}
        </div>
      )}
      <div className="space-y-0.5">
        {payload.map((p, i) => (
          <div key={`${p.dataKey ?? p.name ?? i}`} className="flex items-center gap-2 text-slate-600 dark:text-slate-300">
            <span className="inline-block size-2 rounded-sm" style={{ backgroundColor: p.color }} />
            <span>{p.name}</span>
            <span className="ml-auto pl-3 font-medium tabular-nums text-slate-900 dark:text-slate-100">
              {typeof p.value === 'number' ? p.value.toLocaleString() : p.value}
            </span>
          </div>
        ))}
        {extras.map((e) => (
          <div key={e.label} className="flex items-center gap-2 text-slate-600 dark:text-slate-300">
            <span className="inline-block size-2" />
            <span>{e.label}</span>
            <span className="ml-auto pl-3 font-medium tabular-nums text-slate-900 dark:text-slate-100">{e.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function ChartSkeleton({ className = 'h-full' }: { className?: string }) {
  return <div className={`w-full animate-pulse rounded-lg bg-slate-100 dark:bg-slate-700 ${className}`} />
}

const medianExtra = (row: Record<string, unknown>) => [
  { label: 'Median salary', value: fmtMoney(row.median_salary as number | null) },
]

// ── Component ─────────────────────────────────────────────────────────────────

export function MarketInsightsCharts() {
  const [roleFamily, setRoleFamily] = useState<string>('')
  const [selectedSkills, setSelectedSkills] = useState<string[] | null>(null)

  const seniority = useSWR<SeniorityBreakdownRow[]>(
    'dashboard-seniority-breakdown',
    dashboardApi.getSeniorityBreakdown,
    DASHBOARD_SWR_CONFIG
  )
  const roleFamilies = useSWR<RoleFamilyRow[]>(
    'dashboard-role-families',
    dashboardApi.getRoleFamilies,
    DASHBOARD_SWR_CONFIG
  )
  const topSkills = useSWR<TopSkillRow[]>(
    ['dashboard-top-skills', roleFamily],
    () => dashboardApi.getTopSkills(TOP_SKILLS_FETCHED, roleFamily || null),
    DASHBOARD_SWR_CONFIG
  )
  // The trend pool is always the overall top skills (independent of the role
  // family filter) — same SWR key as the unfiltered bar chart, so it dedupes.
  const topSkillsAll = useSWR<TopSkillRow[]>(
    ['dashboard-top-skills', ''],
    () => dashboardApi.getTopSkills(TOP_SKILLS_FETCHED, null),
    DASHBOARD_SWR_CONFIG
  )

  const trendPool = useMemo(
    () => (topSkillsAll.data ?? []).slice(0, TREND_POOL).map((s) => s.skill),
    [topSkillsAll.data]
  )
  const trendPoolKey = trendPool.join(',').toLowerCase()

  const trend = useSWR<SkillsTrendRow[]>(
    trendPool.length ? ['dashboard-skills-trend', trendPoolKey] : null,
    () => dashboardApi.getSkillsTrend(trendPool, TREND_WEEKS),
    DASHBOARD_SWR_CONFIG
  )

  // Default selection: the first N skills of the pool, once it is known.
  useEffect(() => {
    if (selectedSkills === null && trendPool.length) {
      setSelectedSkills(trendPool.slice(0, TREND_DEFAULT))
    }
  }, [trendPool, selectedSkills])

  const visibleSkills = selectedSkills ?? []

  // Pivot [{week, skill, jobs}] -> [{week, [skill]: jobs, ...}] for the line chart.
  const trendData = useMemo(() => {
    const byWeek = new Map<string, Record<string, number | string>>()
    for (const r of trend.data ?? []) {
      const row = byWeek.get(r.week) ?? { week: r.week }
      row[r.skill] = r.jobs
      byWeek.set(r.week, row)
    }
    return Array.from(byWeek.values()).sort((a, b) => String(a.week).localeCompare(String(b.week)))
  }, [trend.data])

  const toggleSkill = (skill: string) => {
    setSelectedSkills((prev) => {
      const cur = prev ?? []
      if (cur.includes(skill)) return cur.length > 1 ? cur.filter((s) => s !== skill) : cur
      return [...cur, skill]
    })
  }

  const seniorityData = seniority.data ?? []
  const skillsData = (topSkills.data ?? []).slice(0, TOP_SKILLS_SHOWN)
  const familiesData = roleFamilies.data ?? []
  const classifiedJobs = useMemo(() => familiesData.reduce((s, r) => s + r.jobs, 0), [familiesData])
  const selectedFamily = familiesData.find((f) => f.role_family === roleFamily)

  return (
    <section className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold leading-tight text-slate-900 dark:text-slate-100">
          Seniority &amp; skills
        </h2>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Extracted from job descriptions by an LLM. Covers active listings where extraction succeeded;
          medians are monthly base salary over disclosed ranges.
        </p>
      </div>

      {/* ── Seniority: two small multiples sharing one category axis ─────────── */}
      <div className={CARD}>
        <div className="mb-4 flex items-center gap-2">
          <Users className="size-4 text-indigo-600 dark:text-indigo-400" />
          <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300">Jobs and median salary by seniority</h3>
        </div>
        {seniority.isLoading ? (
          <ChartSkeleton className="h-[260px]" />
        ) : seniorityData.length === 0 ? (
          <EmptyState
            icon={Users}
            message="No seniority data yet"
            description="Seniority is inferred during the embed step; it will appear once jobs have been processed."
            className="py-8"
          />
        ) : (
          <div className={`grid gap-6 md:grid-cols-2 ${CHART_TEXT}`}>
            <div>
              <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
                Active jobs
              </div>
              <div className="h-[240px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={seniorityData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.15} vertical={false} />
                    <XAxis dataKey="seniority" tick={TICK} interval={0} />
                    <YAxis tick={TICK} tickFormatter={(v: number) => v.toLocaleString()} width={48} />
                    <Tooltip cursor={{ fill: 'currentColor', fillOpacity: 0.06 }} content={<ChartTooltip extra={medianExtra} />} />
                    <Bar dataKey="jobs" name="Jobs" fill={COLOR_JOBS} radius={[4, 4, 0, 0]} maxBarSize={36} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div>
              <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
                Median monthly salary
              </div>
              <div className="h-[240px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={seniorityData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.15} vertical={false} />
                    <XAxis dataKey="seniority" tick={TICK} interval={0} />
                    <YAxis tick={TICK} tickFormatter={(v: number) => fmtMoney(v)} width={48} />
                    <Tooltip
                      cursor={{ fill: 'currentColor', fillOpacity: 0.06 }}
                      content={
                        <ChartTooltip
                          extra={(row) => [
                            { label: 'Median salary', value: fmtMoney(row.median_salary as number | null) },
                            { label: 'Jobs', value: Number(row.jobs ?? 0).toLocaleString() },
                          ]}
                        />
                      }
                    />
                    <Bar dataKey="median_salary" name="Median salary" fill={COLOR_SALARY} radius={[4, 4, 0, 0]} maxBarSize={36} legendType="none" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* ── Top skills (with role-family filter) ──────────────────────────── */}
        <div className={CARD}>
          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2">
              <Sparkles className="size-4 text-indigo-600 dark:text-indigo-400" />
              <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300">Most requested skills</h3>
            </div>
            <select
              aria-label="Filter skills by role family"
              value={roleFamily}
              onChange={(e) => setRoleFamily(e.target.value)}
              className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
            >
              <option value="">All role families</option>
              {familiesData.map((f) => (
                <option key={f.role_family} value={f.role_family}>
                  {f.display_name}
                </option>
              ))}
            </select>
          </div>
          {selectedFamily && (
            <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
              {selectedFamily.display_name} · {selectedFamily.jobs.toLocaleString()} classified jobs
            </p>
          )}
          <div className={`h-[520px] w-full ${CHART_TEXT}`}>
            {topSkills.isLoading ? (
              <ChartSkeleton />
            ) : skillsData.length === 0 ? (
              <EmptyState
                icon={Sparkles}
                message="No skills data"
                description={
                  roleFamily
                    ? 'No classified jobs with extracted skills in this role family yet.'
                    : 'Skills are extracted during the embed step; they will appear once jobs have been processed.'
                }
                className="h-full py-8"
              />
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={skillsData} layout="vertical" margin={{ left: 8, right: 24, top: 4, bottom: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.15} horizontal={false} />
                  <XAxis type="number" tick={TICK} tickFormatter={(v: number) => v.toLocaleString()} />
                  <YAxis type="category" dataKey="skill" width={150} tick={{ ...TICK, fontSize: 10 }} interval={0} />
                  <Tooltip cursor={{ fill: 'currentColor', fillOpacity: 0.06 }} content={<ChartTooltip extra={medianExtra} />} />
                  <Bar dataKey="jobs" name="Jobs" fill={COLOR_JOBS} radius={[0, 4, 4, 0]} barSize={16} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* ── Role families ─────────────────────────────────────────────────── */}
        <div className={CARD}>
          <div className="mb-4 flex items-center gap-2">
            <Layers className="size-4 text-indigo-600 dark:text-indigo-400" />
            <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300">Active jobs by role family</h3>
          </div>
          {familiesData.length > 0 && (
            <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
              {classifiedJobs.toLocaleString()} active jobs classified so far — classification is still being backfilled.
            </p>
          )}
          <div className={`h-[520px] w-full ${CHART_TEXT}`}>
            {roleFamilies.isLoading ? (
              <ChartSkeleton />
            ) : familiesData.length === 0 ? (
              <EmptyState
                icon={Layers}
                message="Role families not classified yet"
                description="Role family classification is being backfilled; this chart fills in as jobs are labelled."
                className="h-full py-8"
              />
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={familiesData} layout="vertical" margin={{ left: 8, right: 24, top: 4, bottom: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.15} horizontal={false} />
                  <XAxis type="number" tick={TICK} tickFormatter={(v: number) => v.toLocaleString()} />
                  <YAxis type="category" dataKey="display_name" width={150} tick={{ ...TICK, fontSize: 10 }} interval={0} />
                  <Tooltip cursor={{ fill: 'currentColor', fillOpacity: 0.06 }} content={<ChartTooltip extra={medianExtra} />} />
                  <Bar dataKey="jobs" name="Jobs" fill={COLOR_JOBS} radius={[0, 4, 4, 0]} barSize={16} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>

      {/* ── Skills trend ──────────────────────────────────────────────────────── */}
      <div className={CARD}>
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <TrendingUp className="size-4 text-indigo-600 dark:text-indigo-400" />
              <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300">Skills trend</h3>
            </div>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Jobs posted per week mentioning each skill, last {TREND_WEEKS} weeks (top {TREND_POOL} skills overall).
            </p>
          </div>
          {trendPool.length > 0 && (
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="Skills shown">
              {trendPool.map((skill, i) => {
                const on = visibleSkills.includes(skill)
                return (
                  <button
                    key={skill}
                    type="button"
                    aria-pressed={on}
                    onClick={() => toggleSkill(skill)}
                    className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-2 ${
                      on
                        ? 'border-transparent bg-slate-100 text-slate-900 dark:bg-slate-700 dark:text-slate-100'
                        : 'border-slate-200 text-slate-500 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-700/50'
                    }`}
                  >
                    <span
                      className="inline-block size-2 rounded-full"
                      style={{ backgroundColor: SERIES_COLORS[i % SERIES_COLORS.length], opacity: on ? 1 : 0.35 }}
                    />
                    {skill}
                  </button>
                )
              })}
            </div>
          )}
        </div>
        <div className={`h-[300px] w-full sm:h-[340px] ${CHART_TEXT}`}>
          {topSkillsAll.isLoading || trend.isLoading ? (
            <ChartSkeleton />
          ) : trendData.length === 0 ? (
            <EmptyState
              icon={TrendingUp}
              message="No trend data"
              description="Weekly skill counts will appear once jobs with extracted skills have been posted."
              className="h-full py-8"
            />
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trendData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.15} vertical={false} />
                <XAxis dataKey="week" tick={TICK} tickFormatter={fmtWeek} />
                <YAxis tick={TICK} tickFormatter={(v: number) => v.toLocaleString()} width={48} />
                <Tooltip content={<ChartTooltip labelFormatter={(l) => `Week of ${fmtWeek(l)}`} />} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                {trendPool.map((skill, i) =>
                  visibleSkills.includes(skill) ? (
                    <Line
                      key={skill}
                      type="monotone"
                      dataKey={skill}
                      name={skill}
                      stroke={SERIES_COLORS[i % SERIES_COLORS.length]}
                      strokeWidth={2}
                      dot={false}
                      activeDot={{ r: 4, strokeWidth: 2, stroke: 'white' }}
                      isAnimationActive={false}
                    />
                  ) : null
                )}
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </section>
  )
}

export default MarketInsightsCharts
