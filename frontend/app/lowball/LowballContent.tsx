'use client'

import { useState, useEffect } from 'react'
import { lowballApi, companiesApi } from '@/lib/api'
import type { LowballResult, SimilarJob } from '@/lib/types'
import { Layout } from '../components/layout'
import NavUserActions from '../components/NavUserActions'
import { Card, CardBody } from '@/components/design'
import { Input } from '@/components/ui/input'
import CompanyCombobox from '@/components/ui/CompanyCombobox'
import {
  Scale,
  ExternalLink,
  Loader2,
  CheckCircle2,
  FileText,
  TrendingUp,
  Search,
  Building2,
  MapPin,
  Clock,
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
// Similar job card
// ---------------------------------------------------------------------------

function SimilarJobCard({ job }: { job: SimilarJob }) {
  const [descExpanded, setDescExpanded] = useState(false)
  const fmt = (v: number) => `$${v.toLocaleString()}`
  const score = job.similarity_score
  const scorePct = (score * 100).toFixed(0)
  const isActive = job.is_active !== false

  const scoreCls =
    score >= 0.75
      ? 'bg-emerald-500/10 text-emerald-700 border-emerald-200 dark:text-emerald-400 dark:border-emerald-800'
      : score >= 0.55
        ? 'bg-amber-500/10 text-amber-700 border-amber-200 dark:text-amber-400 dark:border-amber-800'
        : 'bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-700 dark:text-slate-400 dark:border-slate-600'

  const ringCls = isActive
    ? score >= 0.75
      ? 'ring-1 ring-emerald-200/50 dark:ring-emerald-800/50'
      : score >= 0.55
        ? 'ring-1 ring-amber-200/50 dark:ring-amber-800/50'
        : ''
    : ''

  const salaryText =
    job.salary_min != null && job.salary_max != null
      ? `${fmt(job.salary_min)} – ${fmt(job.salary_max)}/mo`
      : job.salary_min != null
        ? `From ${fmt(job.salary_min)}/mo`
        : job.salary_max != null
          ? `Up to ${fmt(job.salary_max)}/mo`
          : null

  return (
    <div
      className={`rounded-xl border overflow-hidden shadow-sm transition-all
        bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700
        ${isActive ? `hover:shadow-md ${ringCls}` : 'opacity-70'}
      `}
    >
      {/* Main content */}
      <div className="p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <p className="text-base font-semibold text-slate-900 dark:text-slate-100 line-clamp-2">
              {job.title}
            </p>

            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 mt-2">
              {job.company_name && (
                <span className="flex items-center gap-1 text-sm text-slate-500 dark:text-slate-400">
                  <Building2 className="w-3.5 h-3.5 shrink-0" />
                  {job.company_name}
                </span>
              )}
              {job.location && (
                <span className="flex items-center gap-1 text-sm text-slate-500 dark:text-slate-400">
                  <MapPin className="w-3.5 h-3.5 shrink-0" />
                  {job.location}
                </span>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-2 mt-2.5">
              {salaryText ? (
                <span className="px-2.5 py-1 text-xs font-bold rounded-full bg-violet-50 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300 tracking-wide">
                  {salaryText}
                </span>
              ) : (
                <span className="text-xs text-slate-400 dark:text-slate-500 italic">No salary listed</span>
              )}
              {job.inferred_seniority && (
                <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">
                  {job.inferred_seniority}
                </span>
              )}
              {job.min_years_experience != null && (
                <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-400">
                  {job.min_years_experience}+ yrs exp
                </span>
              )}
              {!isActive && (
                <span className="flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400">
                  <Clock className="w-3 h-3" />
                  Position closed
                </span>
              )}
            </div>

            {job.canonical_skills && job.canonical_skills.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2.5">
                {job.canonical_skills.slice(0, 8).map((skill) => (
                  <span
                    key={skill}
                    className="px-2 py-0.5 text-xs rounded-md bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-400"
                  >
                    {skill}
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className={`shrink-0 px-3 py-1.5 rounded-full border text-sm font-semibold tabular-nums ${scoreCls}`}>
            {scorePct}%
          </div>
        </div>

        {/* Description */}
        {job.description && (
          <div className="mt-3">
            <p className={`text-sm text-slate-500 dark:text-slate-400 leading-relaxed ${descExpanded ? '' : 'line-clamp-2'}`}>
              {job.description}
            </p>
            {job.description.length > 150 && (
              <button
                onClick={() => setDescExpanded(v => !v)}
                className="mt-1 text-xs font-medium text-indigo-500 hover:text-indigo-700 dark:text-indigo-400 dark:hover:text-indigo-300 transition-colors"
              >
                {descExpanded ? 'Show less' : 'Show more'}
              </button>
            )}
          </div>
        )}
      </div>

      {/* Footer */}
      {isActive && job.job_url?.startsWith('https://') ? (
        <div className="border-t border-slate-100 dark:border-slate-700">
          <a
            href={job.job_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-center gap-1.5 w-full py-2.5 text-sm font-medium
              text-indigo-600 dark:text-indigo-400
              hover:bg-indigo-50 dark:hover:bg-indigo-950/30
              transition-colors"
          >
            View on MyCareersFuture
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        </div>
      ) : !isActive ? (
        <div className="border-t border-slate-100 dark:border-slate-700 px-5 py-2.5 bg-slate-50 dark:bg-slate-800/50">
          <p className="text-xs text-slate-400 dark:text-slate-500">
            Historical listing · salary data still valid for benchmarking
          </p>
        </div>
      ) : null}
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
    title: 'Enter the job title and description',
    detail: 'Enter the title and paste the full JD so we can find the most similar active roles.',
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
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [salary, setSalary] = useState('')
  const [result, setResult] = useState<LowballResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Company autocomplete
  const [companies, setCompanies] = useState<string[]>([])
  const [companyAliases, setCompanyAliases] = useState<Record<string, string>>({})
  const [companyInput, setCompanyInput] = useState('')
  const [activeTab, setActiveTab] = useState<'all' | 'company'>('all')

  // selectedCompany: exact match OR resolved via alias map
  const selectedCompany = companies.includes(companyInput)
    ? companyInput
    : (companyAliases[companyInput] ?? '')

  useEffect(() => {
    companiesApi.list()
      .then(list => setCompanies(list))
      .catch(err => console.error('[companies] failed to load', err))
    companiesApi.aliases()
      .then(map => setCompanyAliases(map))
      .catch(err => console.error('[companies/aliases] failed to load', err))
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setState('loading')
    try {
      const salaryValue = salary ? parseInt(salary, 10) : undefined
      const data = await lowballApi.check(title, description, salaryValue, selectedCompany || undefined)
      setResult(data)
      setActiveTab('all')
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
    setSalary('')
    setActiveTab('all')
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
            Salary Insights
          </h1>
        </div>
        <p className="text-base text-slate-500 dark:text-slate-400 leading-relaxed max-w-xl">
          Explore the pay range for any role in Singapore — powered by live MCF data.
          Enter the job title and description to see market rates, or add an offered salary to check if you're being lowballed.
        </p>
      </div>

      {/* ── Form state ───────────────────────────────────────────────────── */}
      {state === 'form' && (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-6 items-start">
          {/* Left: form */}
          <Card>
            <CardBody>
              <form onSubmit={handleSubmit} className="space-y-6">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
                      Job title
                    </label>
                    <Input
                      type="text"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      required
                      placeholder="e.g. Senior Software Engineer"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
                      Company{' '}
                      <span className="font-normal text-slate-400">(optional)</span>
                    </label>
                    <CompanyCombobox
                      companies={companies}
                      aliasMap={companyAliases}
                      value={companyInput}
                      onChange={setCompanyInput}
                      loading={companies.length === 0}
                    />
                    {selectedCompany && (
                      <p className="mt-1 text-xs text-indigo-600 dark:text-indigo-400 flex items-center gap-1">
                        <Building2 className="w-3 h-3" />
                        Company tab will appear in results
                      </p>
                    )}
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
                    Job description
                  </label>
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    rows={8}
                    required
                    minLength={20}
                    placeholder="Paste the full job description here…"
                    className="w-full rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2.5 text-sm text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-y leading-relaxed"
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

          {/* Right: info panel — hidden on mobile to reduce scroll */}
          <div className="hidden lg:block">
            <HowItWorksPanel />
          </div>
        </div>
      )}

      {/* ── Loading state ─────────────────────────────────────────────────── */}
      {state === 'loading' && (
        <Card>
          <CardBody>
            <div className="flex flex-col items-center justify-center py-16 gap-3 text-slate-500 dark:text-slate-400">
              <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
              <p className="text-sm font-medium">
                Analysing{title ? ` "${title}"` : ' market data'}…
              </p>
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

            {/* Similar jobs — single list or tabbed when company results are available */}
            {result.similar_jobs.length === 0 && result.verdict !== 'insufficient_data' && (
              <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 px-6 py-10 text-center">
                <p className="text-sm font-medium text-slate-600 dark:text-slate-400">No similar roles found</p>
                <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
                  Try adding more detail to the job description, or broaden the title.
                </p>
              </div>
            )}
            {result.similar_jobs.length > 0 && (() => {
              const hasCompanyTab = result.company_similar_jobs != null
              const displayJobs = hasCompanyTab && activeTab === 'company'
                ? result.company_similar_jobs!
                : result.similar_jobs
              const activeCount = displayJobs.filter(j => j.is_active !== false).length
              const totalCount = displayJobs.length

              return (
                <div>
                  <div className="flex items-center justify-between mb-3 gap-4 flex-wrap">
                    <h2 className="text-base font-semibold text-slate-700 dark:text-slate-300">
                      Similar roles
                    </h2>
                    {hasCompanyTab ? (
                      <div className="flex rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden text-sm">
                        <button
                          type="button"
                          onClick={() => setActiveTab('all')}
                          className={`px-3 py-1.5 font-medium transition-colors ${
                            activeTab === 'all'
                              ? 'bg-indigo-600 text-white'
                              : 'text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800'
                          }`}
                        >
                          All matches
                        </button>
                        <button
                          type="button"
                          onClick={() => setActiveTab('company')}
                          className={`px-3 py-1.5 font-medium transition-colors border-l border-slate-200 dark:border-slate-700 ${
                            activeTab === 'company'
                              ? 'bg-indigo-600 text-white'
                              : 'text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800'
                          }`}
                        >
                          {selectedCompany || 'Company'} roles
                        </button>
                      </div>
                    ) : (
                      <span className="text-sm text-slate-400 dark:text-slate-500">
                        {activeCount} active · {totalCount - activeCount} historical
                      </span>
                    )}
                  </div>
                  {hasCompanyTab && (
                    <p className="mb-3 text-sm text-slate-400 dark:text-slate-500">
                      {activeCount} active · {totalCount - activeCount} historical
                    </p>
                  )}
                  {displayJobs.length > 0 ? (
                    <div className="space-y-3">
                      {displayJobs.map((job) => (
                        <SimilarJobCard key={job.job_uuid} job={job} />
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-slate-400 dark:text-slate-500 py-4 text-center">
                      No active listings found for {selectedCompany} matching this role.
                    </p>
                  )}
                  {hasCompanyTab && activeTab === 'company' && selectedCompany && (
                    <div className="mt-3 pt-3 border-t border-slate-100 dark:border-slate-800">
                      <a
                        href={`/company/${encodeURIComponent(selectedCompany)}`}
                        className="text-sm text-indigo-600 dark:text-indigo-400 hover:underline"
                      >
                        View full {selectedCompany} profile →
                      </a>
                    </div>
                  )}
                </div>
              )
            })()}

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
