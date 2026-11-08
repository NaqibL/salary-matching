'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Sparkles } from 'lucide-react'
import { dashboardApi } from '@/lib/api'
import type { RoleFamilyRow, TopSkillRow } from '@/lib/types'
import { EmptyState } from '@/components/design'
import { DASHBOARD_SWR_CONFIG } from '@/lib/swr-config'
import { CHART_TEXT, ChartTooltip, TICK, VIZ_1, fmtMoney } from './ChartTooltip'

const SHOWN = 10

/** Top-10 skills named in live ads, narrowed by job type. The one chart a job seeker acts on. */
export function SkillsChart({ familyRows, initialFamily = '' }: { familyRows: RoleFamilyRow[]; initialFamily?: string }) {
  const [family, setFamily] = useState(initialFamily)
  const { data, isLoading } = useSWR<TopSkillRow[]>(
    ['dashboard-top-skills', family],
    () => dashboardApi.getTopSkills(25, family || null),
    DASHBOARD_SWR_CONFIG,
  )
  const rows = (data ?? []).slice(0, SHOWN)
  const selected = familyRows.find((f) => f.role_family === family)

  return (
    <div>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between mb-3">
        <p className="text-xs text-slate-500 dark:text-slate-400">
          live ads that name the skill · {selected ? selected.display_name : 'all job types'} · read from the ad text
        </p>
        <select
          aria-label="Job type"
          value={family}
          onChange={(e) => setFamily(e.target.value)}
          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
        >
          <option value="">All job types</option>
          {familyRows
            .filter((f) => f.role_family !== 'other')
            .map((f) => (
              <option key={f.role_family} value={f.role_family}>
                {f.display_name}
              </option>
            ))}
        </select>
      </div>
      {!family && <p className="mb-2 text-xs text-slate-400 dark:text-slate-500">Pick a job type to narrow the list.</p>}
      <div className={`h-[340px] w-full ${CHART_TEXT}`}>
        {isLoading && !data ? (
          <div className="h-full w-full animate-pulse rounded-lg bg-slate-100 dark:bg-slate-700" />
        ) : rows.length === 0 ? (
          <EmptyState icon={Sparkles} message="No skills data" description="Skills are read from ad text during processing." className="h-full py-8" />
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 24, top: 4, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.15} horizontal={false} />
              <XAxis type="number" tick={TICK} tickFormatter={(v: number) => v.toLocaleString()} />
              <YAxis type="category" dataKey="skill" width={150} tick={{ ...TICK, fontSize: 11 }} interval={0} />
              <Tooltip
                cursor={{ fill: 'currentColor', fillOpacity: 0.06 }}
                content={
                  <ChartTooltip
                    rows={(row) => [
                      { label: 'Live ads', value: Number(row.jobs ?? 0).toLocaleString() },
                      { label: 'Median advertised monthly base', value: fmtMoney(row.median_salary as number | null) },
                    ]}
                  />
                }
              />
              <Bar dataKey="jobs" name="Live ads" fill={VIZ_1} radius={[0, 4, 4, 0]} barSize={16} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
