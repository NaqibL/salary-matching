'use client'

import { useMemo } from 'react'
import Link from 'next/link'
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { MarketStats, MarketStatsRow, RoleFamilyRow } from '@/lib/types'
import { OTHER_FAMILY, familyLabel } from '@/lib/roleFamilies'
import { Card, CardBody } from '@/components/design'
import { CHART_TEXT, ChartTooltip, TICK, VIZ_1, VIZ_OTHER, fmtPct, pct } from './ChartTooltip'

const BUCKET_LABEL: Record<string, string> = { '1': 'Once', '2': 'Twice', '3-5': '3–5 times', '6-10': '6–10 times', '11+': '11+ times' }

function fmtK(n: number): string {
  return n >= 10_000 ? `${(n / 1000).toFixed(1)}k` : n.toLocaleString()
}

/**
 * "Posted before" (SGSAL-030): the market-wide facts about repeated ad text, as shares and
 * distributions. No ad title and no company is named here; named rows belong on a company
 * profile. Replaces the 20-row most-reposted table, which any ranking of ad texts turns into
 * one template ad.
 */
export function PostedBeforeSection({ stats, familyRows }: { stats: MarketStats; familyRows?: RoleFamilyRow[] }) {
  const t = stats.totals!
  const share = pct(t.live_reposts, t.live)
  const direct = stats.by_poster.find((p) => p.key === 'direct')
  const agency = stats.by_poster.find((p) => p.key === 'agency')

  const byFamily = useMemo(() => {
    const rows = stats.families
      .filter((f) => f.live > 0)
      .map((f) => ({ key: f.key, name: familyLabel(f.key, familyRows), share: pct(f.live_reposts, f.live) ?? 0, live: f.live, reposts: f.live_reposts ?? 0 }))
    const named = rows.filter((r) => r.key !== OTHER_FAMILY).sort((a, b) => b.share - a.share)
    const other = rows.find((r) => r.key === OTHER_FAMILY)
    return other ? [...named, other] : named
  }, [stats.families, familyRows])

  const buckets = stats.times_posted.map((b: MarketStatsRow) => ({ key: b.key, label: BUCKET_LABEL[b.key] ?? b.key, texts: b.texts ?? 0, live: b.live }))
  const top = stats.times_posted.find((b) => b.key === '11+')

  const tiles = [
    {
      label: 'Live ads posted before',
      value: fmtPct(share),
      sub: `${(t.live_reposts ?? 0).toLocaleString()} of ${t.live.toLocaleString()} live ads · same text posted earlier`,
    },
    {
      label: 'Same ad, several company names',
      value: fmtPct(pct(t.live_multi_company, t.live)),
      sub: `${(t.live_multi_company ?? 0).toLocaleString()} live ads carry text seen under two or more company names`,
    },
    {
      label: 'Direct employers · recruitment agencies',
      value: direct && agency ? `${fmtPct(pct(direct.live_reposts, direct.live))} · ${fmtPct(pct(agency.live_reposts, agency.live))}` : '—',
      sub: 'share of each group’s live ads posted before · both repeat at about the same rate',
    },
  ]

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {tiles.map((tile) => (
          <Card key={tile.label} size="compact" className="border-slate-200 dark:border-slate-700">
            <div className="text-xs text-slate-500 dark:text-slate-400">{tile.label}</div>
            <div className="mt-1 text-2xl font-semibold tabular-nums text-slate-900 dark:text-slate-100">{tile.value}</div>
            <div className="mt-1 text-[11px] leading-snug text-slate-400 dark:text-slate-500">{tile.sub}</div>
          </Card>
        ))}
      </div>

      <Card className="border-slate-200 dark:border-slate-700">
        <CardBody>
          <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">Share of live ads posted before, by job type</h3>
          <p className="text-xs text-slate-400 dark:text-slate-500 mb-3">
            live ads · dotted line = all job types, {fmtPct(share)}
          </p>
          <div className={`w-full ${CHART_TEXT}`} style={{ height: 28 * byFamily.length + 40 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={byFamily} layout="vertical" margin={{ left: 8, right: 40, top: 18, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.15} horizontal={false} />
                <XAxis type="number" domain={[0, 100]} tick={TICK} tickFormatter={(v: number) => `${v}%`} />
                <YAxis type="category" dataKey="name" width={190} tick={{ ...TICK, fontSize: 11 }} interval={0} />
                <Tooltip
                  cursor={{ fill: 'currentColor', fillOpacity: 0.06 }}
                  content={
                    <ChartTooltip
                      rows={(row) => [
                        { label: 'Posted before', value: `${Number(row.reposts).toLocaleString()} of ${Number(row.live).toLocaleString()} live ads` },
                        { label: 'Share', value: fmtPct(Number(row.share)) },
                      ]}
                    />
                  }
                />
                {share != null && (
                  <ReferenceLine
                    x={share}
                    stroke="currentColor"
                    strokeDasharray="4 4"
                    strokeOpacity={0.6}
                    label={{ value: `all types ${fmtPct(share)}`, position: 'top', fontSize: 11, fill: 'currentColor' }}
                  />
                )}
                <Bar dataKey="share" name="Posted before" radius={[0, 4, 4, 0]} barSize={14} isAnimationActive={false}>
                  {byFamily.map((r) => (
                    <Cell key={r.key} fill={r.key === OTHER_FAMILY ? VIZ_OTHER : VIZ_1} />
                  ))}
                  <LabelList dataKey="share" position="right" formatter={(v: number) => `${Math.round(v)}%`} fontSize={11} fill="currentColor" />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </CardBody>
      </Card>

      <Card className="border-slate-200 dark:border-slate-700">
        <CardBody>
          <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">How many times the same ad text has been posted</h3>
          <p className="text-xs text-slate-400 dark:text-slate-500 mb-3">
            ad texts with a live copy
            {top && top.texts != null && (
              <> · the {fmtK(top.texts)} texts posted 11+ times account for {top.live.toLocaleString()} live ads</>
            )}
          </p>
          <div className={`h-[240px] w-full ${CHART_TEXT}`}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={buckets} margin={{ left: 8, right: 16, top: 20, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.15} vertical={false} />
                <XAxis dataKey="label" tick={TICK} interval={0} />
                <YAxis tick={TICK} tickFormatter={(v: number) => fmtK(v)} width={48} />
                <Tooltip
                  cursor={{ fill: 'currentColor', fillOpacity: 0.06 }}
                  content={
                    <ChartTooltip
                      rows={(row) => [
                        { label: 'Ad texts', value: Number(row.texts).toLocaleString() },
                        { label: 'Live ads carrying them', value: Number(row.live).toLocaleString() },
                      ]}
                    />
                  }
                />
                <Bar dataKey="texts" name="Ad texts" fill={VIZ_1} radius={[4, 4, 0, 0]} maxBarSize={56} isAnimationActive={false}>
                  <LabelList dataKey="texts" position="top" formatter={(v: number) => fmtK(v)} fontSize={11} fill="currentColor" />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </CardBody>
      </Card>

      <p className="text-xs text-slate-400 dark:text-slate-500">
        See any company&apos;s own repeated ads on its page under &ldquo;Posted before&rdquo;, from the{' '}
        <Link href="/companies" className="underline hover:text-slate-600 dark:hover:text-slate-300">
          Companies
        </Link>{' '}
        list.
      </p>
    </div>
  )
}
