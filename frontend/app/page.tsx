'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Scale, Loader2, ArrowRight, BarChart2 } from 'lucide-react'
import { lowballApi } from '@/lib/api'
import type { LowballResult } from '@/lib/types'
import { Layout } from './components/layout'
import NavUserActions from './components/NavUserActions'

type FormState = 'idle' | 'loading' | 'result'

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

const fmt = (v: number) => `$${v.toLocaleString()}`

export default function HomePage() {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [salary, setSalary] = useState('')
  const [state, setState] = useState<FormState>('idle')
  const [result, setResult] = useState<LowballResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setState('loading')
    try {
      const salaryValue = salary ? parseInt(salary, 10) : undefined
      const data = await lowballApi.check(title, description, salaryValue)
      setResult(data)
      setState('result')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
      setState('idle')
    }
  }

  const reset = () => {
    setState('idle')
    setResult(null)
    setError(null)
    setSalary('')
  }

  return (
    <Layout userSlot={<NavUserActions />}>
      <div className="max-w-2xl mx-auto py-12 flex flex-col gap-10">

        {/* Heading */}
        <div className="flex flex-col gap-3">
          <div className="flex size-12 items-center justify-center rounded-2xl bg-violet-100 dark:bg-violet-950/50">
            <Scale className="size-6 text-violet-600 dark:text-violet-400" />
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
            Know your market value
          </h1>
          <p className="text-base text-slate-500 dark:text-slate-400 leading-relaxed">
            Paste a job title and description to see the salary range from live Singapore listings.
            Add an offered salary to check if you&apos;re being lowballed.
          </p>
        </div>

        {/* Form */}
        {state !== 'result' && (
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div>
              <label className="block text-sm font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
                Job title
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
                placeholder="e.g. Senior Software Engineer"
                className="w-full rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2.5 text-sm text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-violet-500"
              />
            </div>

            <div>
              <label className="block text-sm font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
                Job description
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={6}
                required
                minLength={20}
                placeholder="Paste the full job description here…"
                className="w-full rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2.5 text-sm text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-violet-500 resize-y leading-relaxed"
              />
              {description.length > 0 && description.length < 20 && (
                <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
                  At least 20 characters needed — paste the full job description for accurate results.
                </p>
              )}
            </div>

            <div>
              <label className="block text-sm font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
                Offered salary{' '}
                <span className="font-normal text-slate-400">— SGD / month, optional</span>
              </label>
              <input
                type="number"
                value={salary}
                onChange={(e) => setSalary(e.target.value)}
                min={100}
                placeholder="e.g. 5000"
                className="w-48 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2.5 text-sm text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-violet-500"
              />
            </div>

            {error && (
              <p className="rounded-lg bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 px-4 py-2.5 text-sm text-red-600 dark:text-red-400">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={state === 'loading'}
              className="self-start flex items-center gap-2 rounded-xl bg-violet-600 hover:bg-violet-700 disabled:opacity-60 text-white px-6 py-3 text-sm font-semibold transition-all shadow-sm hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:ring-offset-2"
            >
              {state === 'loading'
                ? <><Loader2 className="w-4 h-4 animate-spin" /> Analysing…</>
                : <><Scale className="w-4 h-4" />{salary ? 'Check my offer' : 'Get market rates'}</>
              }
            </button>
          </form>
        )}

        {/* Result */}
        {state === 'result' && result && (() => {
          const hasMarket = result.market_p25 != null && result.market_p50 != null && result.market_p75 != null
          const hasSalary = result.offered_salary != null
          return (
            <div className="flex flex-col gap-5">
              <div className="rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-6 flex flex-col gap-4">
                <p className={`text-2xl font-bold tracking-tight ${VERDICT_COLORS[result.verdict]}`}>
                  {VERDICT_LABELS[result.verdict]}
                </p>

                {hasSalary && result.percentile != null && (
                  <p className="text-sm text-slate-600 dark:text-slate-400">
                    Your offer of <strong className="text-slate-800 dark:text-slate-200">{fmt(result.offered_salary!)}/mo</strong> is at the{' '}
                    <strong className="text-slate-800 dark:text-slate-200">{result.percentile}th percentile</strong> of {result.total_matched} similar roles.
                  </p>
                )}

                {hasMarket && (
                  <div className="flex gap-8 pt-1">
                    {[
                      { label: 'P25', value: result.market_p25! },
                      { label: 'Median', value: result.market_p50! },
                      { label: 'P75', value: result.market_p75! },
                    ].map(({ label, value }) => (
                      <div key={label} className="text-center">
                        <p className="text-xs text-slate-500 dark:text-slate-400 uppercase tracking-wide mb-1">{label}</p>
                        <p className="text-lg font-bold text-slate-800 dark:text-slate-200">{fmt(value)}</p>
                      </div>
                    ))}
                  </div>
                )}

                {result.verdict === 'insufficient_data' && (
                  <p className="text-sm text-slate-500 dark:text-slate-400">
                    Only {result.salary_coverage} of {result.total_matched} matched jobs had disclosed salaries — need at least 5 to compute percentiles.
                  </p>
                )}
              </div>

              <div className="flex items-center gap-4">
                <Link
                  href="/lowball"
                  className="flex items-center gap-1.5 text-sm font-semibold text-violet-600 dark:text-violet-400 hover:underline"
                >
                  Full analysis with similar roles <ArrowRight className="size-3.5" />
                </Link>
                <button
                  onClick={reset}
                  className="text-sm text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 transition-colors"
                >
                  ← Check another
                </button>
              </div>
            </div>
          )
        })()}

        {/* Dashboard link */}
        <Link
          href="/dashboard"
          className="flex items-center gap-2 text-sm text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors self-start"
        >
          <BarChart2 className="size-4" />
          Explore market trends
        </Link>

      </div>
    </Layout>
  )
}
