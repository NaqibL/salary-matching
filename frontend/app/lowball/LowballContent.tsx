'use client'

import { useState } from 'react'
import { lowballApi } from '@/lib/api'
import type { LowballResult, SimilarJob } from '@/lib/types'
import { Layout } from '../components/layout'
import NavUserActions from '../components/NavUserActions'
import { Card, CardBody } from '@/components/design'
import { Input } from '@/components/ui/input'
import {
  Scale,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Loader2,
  CheckCircle2,
  FileText,
  TrendingUp,
  Search,
} from 'lucide-react'

// ---------------------------------------------------------------------------
// Salary bar — offered is optional; omit to show market range only
// ---------------------------------------------------------------------------

function SalaryBar({
  offered,
  p25,
  p50,
  p75,
}: {
  offered?: number
  p25: number
  p50: number
  p75: number
}) {
  const anchor = offered ?? p50
  const low = Math.min(anchor, p25) * 0.85
  const high = Math.max(anchor, p75) * 1.15
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
        {offered != null && (
          <div
            className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-3 h-3 rounded-full bg-white border-2 border-slate-700 dark:border-slate-200 shadow"
            style={{ left: pct(offered) }}
          />
        )}
      </div>
      <div
        className="relative mt-1 text-xs text-slate-500 dark:text-slate-400"
        style={{ height: '16px' }}
      >
        <span className="absolute -translate-x-1/2" style={{ left: pct(p25) }}>
          P25
        </span>
        <span className="absolute -translate-x-1/2" style={{ left: pct(p50) }}>
          P50
        </span>
        <span className="absolute -translate-x-1/2" style={{ left: pct(p75) }}>
          P75
        </span>
        {offered != null && (
          <span
            className="absolute -translate-x-1/2 font-semibold text-slate-700 dark:text-slate-300"
            style={{ left: pct(offered) }}
          >
            You
          </span>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Similar jobs table
// ---------------------------------------------------------------------------

function SimilarJobsTable({ jobs }: { jobs: SimilarJob[] }) {
  const [open, setOpen] = useState(false)
  const fmt = (v: number | null) => (v != null ? `$${v.toLocaleString()}` : '—')

  return (
    <div className="mt-4">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 text-sm font-medium text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100"
      >
        {open ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        {open ? 'Hide' : 'Show'} similar jobs ({jobs.length})
      </button>

      {open && (
        <div className="mt-3 overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-700">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 dark:bg-slate-800 text-xs text-slate-500 dark:text-slate-400 uppercase tracking-wide">
              <tr>
                <th className="px-3 py-2 text-left">Title</th>
                <th className="px-3 py-2 text-left">Company</th>
                <th className="px-3 py-2 text-right">Salary range</th>
                <th className="px-3 py-2 text-right">Similarity</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
              {jobs.map((j) => (
                <tr key={j.job_uuid} className="bg-white dark:bg-slate-900">
                  <td className="px-3 py-2 max-w-xs">
                    {j.job_url ? (
                      <a
                        href={j.job_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1 text-indigo-600 dark:text-indigo-400 hover:underline truncate"
                      >
                        {j.title}
                        <ExternalLink className="w-3 h-3 shrink-0" />
                      </a>
                    ) : (
                      <span className="truncate">{j.title}</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-400 truncate max-w-[140px]">
                    {j.company_name ?? '—'}
                  </td>
                  <td className="px-3 py-2 text-right text-slate-700 dark:text-slate-300 whitespace-nowrap">
                    {j.salary_min != null
                      ? j.salary_max != null
                        ? `${fmt(j.salary_min)} – ${fmt(j.salary_max)}`
                        : fmt(j.salary_min)
                      : '—'}
                  </td>
                  <td className="px-3 py-2 text-right text-slate-500 dark:text-slate-400">
                    {(j.similarity_score * 100).toFixed(1)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Verdict display config
// ---------------------------------------------------------------------------

const VERDICT_CONFIG = {
  lowballed: {
    label: 'You may be lowballed',
    color: 'text-red-600 dark:text-red-400',
    bg: 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800',
  },
  below_median: {
    label: 'Below market median',
    color: 'text-amber-600 dark:text-amber-400',
    bg: 'bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800',
  },
  at_median: {
    label: 'Around market median',
    color: 'text-green-600 dark:text-green-400',
    bg: 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800',
  },
  above_median: {
    label: 'Above market rate',
    color: 'text-green-600 dark:text-green-400',
    bg: 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800',
  },
  insufficient_data: {
    label: 'Not enough data',
    color: 'text-slate-600 dark:text-slate-400',
    bg: 'bg-slate-50 dark:bg-slate-800 border-slate-200 dark:border-slate-700',
  },
  market_data: {
    label: 'Pay range for similar roles',
    color: 'text-indigo-600 dark:text-indigo-400',
    bg: 'bg-indigo-50 dark:bg-indigo-900/20 border-indigo-200 dark:border-indigo-800',
  },
}

// ---------------------------------------------------------------------------
// How it works sidebar panel
// ---------------------------------------------------------------------------

const HOW_IT_WORKS = [
  {
    icon: FileText,
    step: '1',
    title: 'Paste the job title and description',
    detail: 'Include the full JD so we can find the most similar active roles.',
  },
  {
    icon: TrendingUp,
    step: '2',
    title: 'Optionally enter an offered salary',
    detail: 'If you have an offer, enter the monthly SGD amount to see where it sits.',
  },
  {
    icon: Search,
    step: '3',
    title: 'See the market pay range',
    detail: 'We show P25/P50/P75 from similar live listings, and your percentile if you entered a salary.',
  },
]

function HowItWorksPanel() {
  return (
    <div className="space-y-4">
      <Card className="border-t-4 border-t-indigo-500 dark:border-t-indigo-400">
        <CardBody>
          <p className="mb-5 text-sm font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider">
            How it works
          </p>
          <ol className="space-y-5">
            {HOW_IT_WORKS.map(({ icon: Icon, step, title, detail }) => (
              <li key={step} className="flex gap-3">
                <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-indigo-50 dark:bg-indigo-950/50 text-xs font-bold text-indigo-600 dark:text-indigo-400">
                  {step}
                </div>
                <div>
                  <p className="text-sm font-medium text-slate-800 dark:text-slate-200">{title}</p>
                  <p className="mt-0.5 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
                    {detail}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </CardBody>
      </Card>

      <Card>
        <CardBody>
          <p className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider">
            What we analyse
          </p>
          <ul className="space-y-2.5">
            {[
              'Job title and responsibilities',
              'Required skills and seniority',
              'Industry and company type',
              'Salary data from active MCF listings',
            ].map((item) => (
              <li key={item} className="flex items-start gap-2 text-sm text-slate-600 dark:text-slate-400">
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-indigo-500 dark:text-indigo-400" />
                {item}
              </li>
            ))}
          </ul>
        </CardBody>
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

type PageState = 'form' | 'loading' | 'result'

export function LowballContent() {
  const [state, setState] = useState<PageState>('form')
  const [jobDesc, setJobDesc] = useState('')
  const [salary, setSalary] = useState('')
  const [result, setResult] = useState<LowballResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setState('loading')
    try {
      const salaryValue = salary ? parseInt(salary, 10) : undefined
      const data = await lowballApi.check(jobDesc, salaryValue)
      setResult(data)
      setState('result')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
      setState('form')
    }
  }

  const reset = () => {
    setState('form')
    setResult(null)
    setError(null)
  }

  const fmt = (v: number) => `$${v.toLocaleString()}`

  return (
    <Layout userSlot={<NavUserActions />}>

      {/* ── Page header ──────────────────────────────────────────────────── */}
      <div className="-mx-4 lg:-mx-8 px-4 lg:px-8 pt-10 pb-10 mb-8 bg-gradient-to-br from-violet-50/60 via-white to-slate-50 dark:from-violet-950/15 dark:via-slate-900 dark:to-slate-900 border-b border-slate-200/70 dark:border-slate-800">
        <div className="flex items-center gap-3 mb-3">
          <div className="flex size-11 items-center justify-center rounded-xl bg-violet-100 dark:bg-violet-950/50">
            <Scale className="size-5 text-violet-600 dark:text-violet-400" />
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
            Salary Checker
          </h1>
        </div>
        <p className="text-base text-slate-500 dark:text-slate-400 leading-relaxed max-w-xl">
          Paste a job title and description to see the market pay range for similar active roles
          in Singapore. Optionally enter an offered salary to see where it sits.
        </p>
      </div>

      {/* ── Form state ───────────────────────────────────────────────────── */}
      {state === 'form' && (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-6 items-start">
          {/* Left: form */}
          <Card>
            <CardBody>
              <form onSubmit={handleSubmit} className="space-y-6">
                <div>
                  <label className="block text-sm font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
                    Job title and description
                  </label>
                  <p className="mb-2 text-xs text-slate-400 dark:text-slate-500">
                    Include the job title and full description for the most accurate results.
                  </p>
                  <textarea
                    value={jobDesc}
                    onChange={(e) => setJobDesc(e.target.value)}
                    rows={9}
                    required
                    minLength={20}
                    placeholder="e.g. Senior Software Engineer — We are looking for…"
                    className="w-full rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2.5 text-sm text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-y leading-relaxed"
                  />
                </div>

                <div>
                  <label className="block text-sm font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
                    Offered salary{' '}
                    <span className="font-normal text-slate-400">(SGD / month — optional)</span>
                  </label>
                  <p className="mb-2 text-xs text-slate-400 dark:text-slate-500">
                    Enter your offered salary to see how it compares to market rates.
                  </p>
                  <Input
                    type="number"
                    value={salary}
                    onChange={(e) => setSalary(e.target.value)}
                    min={100}
                    placeholder="e.g. 5000"
                    className="max-w-xs"
                  />
                </div>

                {error && (
                  <p className="rounded-lg bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 px-4 py-2.5 text-sm text-red-600 dark:text-red-400">
                    {error}
                  </p>
                )}

                <button
                  type="submit"
                  className="flex items-center gap-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-3 text-sm font-semibold transition-all shadow-sm hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2"
                >
                  <Scale className="w-4 h-4" />
                  {salary ? 'Check my offer' : 'Get market rates'}
                </button>
              </form>
            </CardBody>
          </Card>

          {/* Right: info panel */}
          <HowItWorksPanel />
        </div>
      )}

      {/* ── Loading state ─────────────────────────────────────────────────── */}
      {state === 'loading' && (
        <Card>
          <CardBody>
            <div className="flex flex-col items-center justify-center py-16 gap-3 text-slate-500 dark:text-slate-400">
              <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
              <p className="text-sm font-medium">Analysing market data…</p>
              <p className="text-xs text-slate-400 dark:text-slate-500">
                Searching similar active listings
              </p>
            </div>
          </CardBody>
        </Card>
      )}

      {/* ── Result state ──────────────────────────────────────────────────── */}
      {state === 'result' && result && (() => {
        const cfg = VERDICT_CONFIG[result.verdict]
        const hasMarketData =
          result.market_p25 != null &&
          result.market_p50 != null &&
          result.market_p75 != null
        const hasSalary = result.offered_salary != null

        return (
          <div className="space-y-5">
            {/* Verdict / market card */}
            <div className={`rounded-2xl border p-6 ${cfg.bg}`}>
              <p className={`text-3xl font-bold tracking-tight ${cfg.color}`}>
                {cfg.label}
              </p>

              {hasSalary && result.percentile != null && (
                <p className="mt-2 text-base text-slate-600 dark:text-slate-400">
                  Your offered salary ({fmt(result.offered_salary!)}/mo) is at the{' '}
                  <strong className="text-slate-800 dark:text-slate-200">
                    {result.percentile}th percentile
                  </strong>{' '}
                  of {result.total_matched} similar roles
                </p>
              )}

              {result.verdict === 'market_data' && !hasSalary && (
                <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
                  Based on {result.salary_coverage} of {result.total_matched} matched roles with
                  disclosed salary
                </p>
              )}

              {result.verdict === 'insufficient_data' && (
                <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
                  Only {result.salary_coverage} of {result.total_matched} matched jobs had
                  disclosed salaries — need at least 5 to compute percentiles.
                </p>
              )}

              {hasMarketData && (
                <>
                  <div className="mt-6 grid grid-cols-3 gap-4 max-w-sm">
                    <div className="text-center">
                      <p className="text-xs text-slate-500 dark:text-slate-400 uppercase tracking-wide">
                        P25
                      </p>
                      <p className="mt-1 text-lg font-bold text-slate-800 dark:text-slate-200">
                        {fmt(result.market_p25!)}
                      </p>
                    </div>
                    <div className="text-center">
                      <p className="text-xs text-slate-500 dark:text-slate-400 uppercase tracking-wide">
                        Median
                      </p>
                      <p className="mt-1 text-lg font-bold text-slate-800 dark:text-slate-200">
                        {fmt(result.market_p50!)}
                      </p>
                    </div>
                    <div className="text-center">
                      <p className="text-xs text-slate-500 dark:text-slate-400 uppercase tracking-wide">
                        P75
                      </p>
                      <p className="mt-1 text-lg font-bold text-slate-800 dark:text-slate-200">
                        {fmt(result.market_p75!)}
                      </p>
                    </div>
                  </div>
                  <SalaryBar
                    offered={hasSalary ? result.offered_salary! : undefined}
                    p25={result.market_p25!}
                    p50={result.market_p50!}
                    p75={result.market_p75!}
                  />
                </>
              )}
            </div>

            {/* Coverage note — only show separately when salary was provided */}
            {hasSalary && (
              <p className="text-xs text-slate-400 dark:text-slate-500 px-1">
                Based on {result.salary_coverage} of {result.total_matched} matched jobs with
                disclosed salary
              </p>
            )}

            {/* Similar jobs */}
            {result.similar_jobs.length > 0 && (
              <Card>
                <CardBody>
                  <SimilarJobsTable jobs={result.similar_jobs} />
                </CardBody>
              </Card>
            )}

            <button
              onClick={reset}
              className="rounded-xl border border-slate-200 dark:border-slate-700 px-5 py-2.5 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
            >
              ← Check another role
            </button>
          </div>
        )
      })()}
    </Layout>
  )
}
