'use client'

import Link from 'next/link'
import type { MarketStats } from '@/lib/types'
import { Card } from '@/components/design'
import { fmtDelta, fmtMoney, fmtPct, pct } from './ChartTooltip'

export const AGENCY_SCOPE = 'SSIC 78 registration or a confirmed recruitment-agency name'

interface Tile {
  key: string
  label: string
  value: string
  sub: string
  href?: string
  title?: string
}

/**
 * Six numbers a job seeker can use (SGSAL-030): how big the market is today, how fast it turns
 * over, what it pays, and how much of it is repeats or agency-placed. Deltas are plain text in
 * the text colour: more ads is not "good" or "bad". Pipeline counts live on /admin.
 */
export function MarketSummary({ stats }: { stats: MarketStats | null | undefined }) {
  const t = stats?.totals
  if (!t) return null

  const liveDelta = t.live_7d_ago != null ? t.live - t.live_7d_ago : null
  const tiles: Tile[] = [
    {
      key: 'live',
      label: 'Live ads',
      value: t.live.toLocaleString(),
      sub: liveDelta != null ? `open today · ${fmtDelta(liveDelta)} vs 7 days ago` : 'open today',
    },
    {
      key: 'new',
      label: 'New this week',
      value: (t.new_7d ?? 0).toLocaleString(),
      sub:
        t.new_prev_7d != null
          ? `first seen in the last 7 days · ${t.new_prev_7d.toLocaleString()} the week before`
          : 'first seen in the last 7 days',
    },
    {
      key: 'days',
      label: 'How long an ad stays up',
      value: t.median_days_up != null ? `${Math.round(t.median_days_up)} days` : '—',
      sub: 'median · ads closed in the last 30 days',
    },
    {
      key: 'pay',
      label: 'Median advertised monthly base',
      value: fmtMoney(t.median_salary),
      sub: 'live ads with a compliant range · SGD',
      title: 'Each ad counts as the midpoint of its advertised range; ranges whose top is more than double the bottom are left out.',
    },
    {
      key: 'reposts',
      label: 'Posted before',
      value: fmtPct(pct(t.live_reposts, t.live)),
      sub: `${(t.live_reposts ?? 0).toLocaleString()} live ads repeat an earlier ad text`,
      href: '#posted-before',
      title: 'Live ads whose exact text was posted earlier, under any company name. See the "Posted before" section.',
    },
    {
      key: 'agency',
      label: 'From recruitment agencies',
      value: fmtPct(pct(t.live_agency, t.live)),
      sub: `of live ads · ${AGENCY_SCOPE}`,
    },
  ]

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
      {tiles.map((tile) => {
        const body = (
          <>
            <div className="text-xs text-slate-500 dark:text-slate-400">{tile.label}</div>
            <div className="mt-1 text-2xl font-semibold tabular-nums text-slate-900 dark:text-slate-100">{tile.value}</div>
            <div className="mt-1 text-[11px] leading-snug text-slate-400 dark:text-slate-500">{tile.sub}</div>
          </>
        )
        return (
          <Card
            key={tile.key}
            size="compact"
            title={tile.title}
            className={`border-slate-200 dark:border-slate-700 ${tile.href ? 'hover:border-indigo-300 dark:hover:border-indigo-700' : ''}`}
          >
            {tile.href ? (
              <Link href={tile.href} className="block focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 rounded">
                {body}
                <div className="mt-1 text-[11px] font-medium text-indigo-600 dark:text-indigo-400">See the breakdown ↓</div>
              </Link>
            ) : (
              body
            )}
          </Card>
        )
      })}
    </div>
  )
}
