'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import { matchesApi, profileApi, taxonomyApi } from '@/lib/api'
import { prefetchJobDetailsTopN } from '@/lib/job-prefetch'
import { useDebouncedValue } from '@/lib/hooks/useDebouncedValue'
import { useProfileContext } from './ProfileProvider'
import { useRatingsQueue } from './RatingsQueueProvider'
import type { Match } from '@/lib/types'
import { MatchCard } from './JobCard'
import { RoleClusterSelect } from './RoleClusterSelect'
import {
  Card,
  CardBody,
  EmptyState,
  LoadingState,
} from '@/components/design'
import { Button } from '@/components/ui/button'
import Spinner from './Spinner'
import { toast } from 'sonner'
import { RefreshCw, Sparkles } from 'lucide-react'
import { TutorialModal, getTutorialStep, hasSeenTutorial } from './TutorialModal'

const JOBS_PER_PAGE = 25

const TIER_OPTIONS = [
  { value: 'T1_Entry', label: 'Entry Level' },
  { value: 'T2_Junior', label: 'Junior' },
  { value: 'T3_Senior', label: 'Senior' },
  { value: 'T4_Management', label: 'Management' },
]

interface Filters {
  maxDaysOld: number | null
  roleClusters: number[]
  predictedTiers: string[]
  salaryMin: number | null
  salaryMax: number | null
}

export default function ResumeTab() {
  const { profile, invalidateProfile, optimisticUpdateStats } = useProfileContext()
  const { queueRating } = useRatingsQueue()
  const stats = profile?.stats ?? null
  const [jobs, setJobs] = useState<Match[]>([])
  const [candidateTier, setCandidateTier] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [computing, setComputing] = useState(false)
  const [ratingUuids, setRatingUuids] = useState<Set<string>>(new Set())
  const [localFilters, setLocalFilters] = useState<Filters>({ maxDaysOld: null, roleClusters: [], predictedTiers: [], salaryMin: null, salaryMax: null })
  const debouncedFilters = useDebouncedValue(localFilters, 300)
  const [roleTaxonomy, setRoleTaxonomy] = useState<Array<{ id: number; name: string }>>([])

  useEffect(() => {
    taxonomyApi.getClusters().then(setRoleTaxonomy).catch(() => {})
  }, [])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [sessionOffset, setSessionOffset] = useState(0)
  const [showTutorialStep3, setShowTutorialStep3] = useState(false)
  const [showTutorialStep4, setShowTutorialStep4] = useState(false)
  const sessionRef = useRef<{ sessionId: string | null; sessionOffset: number }>({ sessionId: null, sessionOffset: 0 })

  useEffect(() => {
    if (hasSeenTutorial()) return
    const step = getTutorialStep()
    if (step === 3 && jobs.length > 0) {
      setShowTutorialStep3(true)
    }
  }, [jobs.length])

  useEffect(() => {
    if (hasSeenTutorial()) return
    const step = getTutorialStep()
    if (step === 4 && (stats?.interested ?? 0) > 0) {
      setShowTutorialStep4(true)
    }
  }, [stats?.interested])

  const loadJobs = useCallback(
    async (append = false) => {
      if (append) {
        setLoadingMore(true)
      } else {
        setLoading(true)
      }
      try {
        const { sessionId: sid, sessionOffset: off } = sessionRef.current
        const offset = append ? off : 0
        const data = await matchesApi.get(
          'resume',
          true,
          JOBS_PER_PAGE,
          offset,
          debouncedFilters.maxDaysOld ?? undefined,
          true,
          append ? (sid ?? undefined) : undefined,
          debouncedFilters.roleClusters.length > 0 ? debouncedFilters.roleClusters : undefined,
          debouncedFilters.predictedTiers.length > 0 ? debouncedFilters.predictedTiers : undefined,
        )
        if (!append) {
          sessionRef.current = { sessionId: data.session_id, sessionOffset: JOBS_PER_PAGE }
          setSessionId(data.session_id)
          setSessionOffset(JOBS_PER_PAGE)
          setJobs(data.matches)
          if (data.candidate_tier) setCandidateTier(data.candidate_tier)
          prefetchJobDetailsTopN(data.matches.map((m) => m.job_uuid), 10)
        } else {
          sessionRef.current = { ...sessionRef.current, sessionOffset: off + JOBS_PER_PAGE }
          setSessionOffset((prev) => prev + JOBS_PER_PAGE)
          setJobs((prev) => [...prev, ...data.matches])
        }
        setHasMore(data.has_more)
      } catch {
        toast.error('Failed to load jobs. Is the API server running?')
      } finally {
        setLoading(false)
        setLoadingMore(false)
      }
    },
    [debouncedFilters.maxDaysOld, debouncedFilters.roleClusters, debouncedFilters.predictedTiers],
  )

  useEffect(() => {
    loadJobs()
  }, [loadJobs])

  const rate = useCallback((uuid: string, interactionType: string) => {
    const type = interactionType as 'interested' | 'not_interested'
    setRatingUuids((prev) => new Set(prev).add(uuid))
    setJobs((prev) => prev.filter((j) => j.job_uuid !== uuid))
    optimisticUpdateStats(type)
    queueRating(uuid, type)
    setRatingUuids((prev) => {
      const next = new Set(prev)
      next.delete(uuid)
      return next
    })
  }, [optimisticUpdateStats, queueRating])

  const handleComputeTaste = async () => {
    setComputing(true)
    try {
      const result = await profileApi.computeTaste()
      toast.success(
        `Taste profile updated from ${result.interested} interested jobs! Switch to Taste tab for personalised recommendations.`,
        { duration: 5000 },
      )
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail || 'Failed to update taste profile')
    } finally {
      setComputing(false)
    }
  }

  const handleResetRatings = async () => {
    if (!confirm('Reset all your ratings and taste profile? This cannot be undone.')) return
    try {
      const result = await profileApi.resetRatings()
      toast.success(
        `Reset complete: ${result.interactions_deleted} ratings, taste profile cleared.`,
        { duration: 4000 },
      )
      invalidateProfile()
      loadJobs()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail || 'Reset failed')
    }
  }

  const handleLoadMore = useCallback(() => loadJobs(true), [loadJobs])

  const handleRefresh = useCallback(() => {
    sessionRef.current = { sessionId: null, sessionOffset: 0 }
    setSessionId(null)
    setSessionOffset(0)
    loadJobs(false)
  }, [loadJobs])

  const interested = stats?.interested ?? 0
  const hasEnoughRatings = interested >= 3

  const displayedJobs = jobs.filter((j) => {
    if (localFilters.salaryMin != null && (j.salary_min == null || j.salary_min < localFilters.salaryMin)) return false
    if (localFilters.salaryMax != null && (j.salary_min == null || j.salary_min > localFilters.salaryMax)) return false
    return true
  })
  const salaryFilterActive = localFilters.salaryMin != null || localFilters.salaryMax != null

  return (
    <div className="space-y-6">
      <Card className="border-slate-200 dark:border-slate-700">
        <CardBody>
        <p className="mb-4 rounded-lg bg-violet-50 px-4 py-3 text-sm text-violet-700 dark:bg-violet-900/20 dark:text-violet-300">
          Top unrated resume matches are shown below (25 at a time). Rate each one to train your taste profile.
          Once you have enough ratings, click <strong>Update Taste Profile</strong> then use the <strong>Taste</strong> tab
          for personalised recommendations.
        </p>
        <div className="flex flex-col gap-4 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
            <div className="flex gap-8">
              <div>
                <div key={stats?.interested} className="stat-pop text-2xl font-semibold tabular-nums text-emerald-600 dark:text-emerald-400">
                  {stats?.interested ?? '—'}
                </div>
                <div className="text-sm text-slate-500 dark:text-slate-400">Interested</div>
              </div>
              <div>
                <div key={stats?.not_interested} className="stat-pop text-2xl font-semibold tabular-nums text-rose-500 dark:text-rose-400">
                  {stats?.not_interested ?? '—'}
                </div>
                <div className="text-sm text-slate-500 dark:text-slate-400">Not Interested</div>
              </div>
              <div>
                <div key={stats?.total_rated} className="stat-pop text-2xl font-semibold tabular-nums text-slate-600 dark:text-slate-400">
                  {stats?.total_rated ?? '—'}
                </div>
                <div className="text-sm text-slate-500 dark:text-slate-400">Rated</div>
              </div>
              {candidateTier && (
                <div>
                  <div className="text-sm font-semibold text-indigo-600 dark:text-indigo-400">
                    {candidateTier.replace('T1_', '').replace('T2_', '').replace('T3_', '').replace('T4_', '')}
                  </div>
                  <div className="text-sm text-slate-500 dark:text-slate-400">Your Level</div>
                </div>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={handleResetRatings}
                className="text-xs font-medium text-slate-400 transition-colors hover:text-amber-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-2 rounded-lg dark:text-slate-500 dark:hover:text-amber-500"
                title="Clear all ratings and taste profile (for testing)"
              >
                Reset for testing
              </button>
              <Button
                onClick={handleComputeTaste}
                disabled={computing || !hasEnoughRatings}
                title={
                  !hasEnoughRatings
                    ? `Mark at least 3 jobs as Interested first (${interested}/3)`
                    : 'Rebuild your taste profile from current ratings'
                }
                className="bg-violet-600 hover:bg-violet-700"
              >
                {computing && <Spinner size="sm" variant="light" />}
                {computing ? 'Updating…' : 'Update Taste Profile'}
              </Button>
            </div>
            {!hasEnoughRatings && (
              <p className="text-xs text-slate-400 w-full sm:w-auto">
                {3 - interested} more Interested {3 - interested === 1 ? 'job' : 'jobs'} needed
              </p>
            )}
          </div>
        </CardBody>
      </Card>

      <Card className="overflow-visible border-slate-200 dark:border-slate-700">
        <CardBody>
          <div className="flex flex-col gap-6 sm:flex-row sm:flex-wrap sm:items-end">
            <div className="w-32">
              <label className="mb-2 block text-sm font-medium text-slate-700 dark:text-slate-300">
                Max Days Old
              </label>
              <input
                type="number"
                placeholder="No limit"
                min={1}
                value={localFilters.maxDaysOld ?? ''}
                onChange={(e) => {
                  const val = e.target.value
                  const parsed = val ? parseInt(val, 10) : null
                  setLocalFilters({
                    ...localFilters,
                    maxDaysOld: parsed != null && !Number.isNaN(parsed) && parsed > 0 ? parsed : null,
                  })
                }}
                className="w-full rounded-lg border border-slate-300 px-4 py-2 text-sm transition-colors focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
            <div className="w-36">
              <label className="mb-2 block text-sm font-medium text-slate-700 dark:text-slate-300">
                Min Salary (SGD/mo)
              </label>
              <input
                type="number"
                placeholder="No limit"
                min={0}
                value={localFilters.salaryMin ?? ''}
                onChange={(e) => {
                  const val = e.target.value
                  const parsed = val ? parseInt(val, 10) : null
                  setLocalFilters({ ...localFilters, salaryMin: parsed != null && !Number.isNaN(parsed) ? parsed : null })
                }}
                className="w-full rounded-lg border border-slate-300 px-4 py-2 text-sm transition-colors focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
            <div className="w-36">
              <label className="mb-2 block text-sm font-medium text-slate-700 dark:text-slate-300">
                Max Salary (SGD/mo)
              </label>
              <input
                type="number"
                placeholder="No limit"
                min={0}
                value={localFilters.salaryMax ?? ''}
                onChange={(e) => {
                  const val = e.target.value
                  const parsed = val ? parseInt(val, 10) : null
                  setLocalFilters({ ...localFilters, salaryMax: parsed != null && !Number.isNaN(parsed) ? parsed : null })
                }}
                className="w-full rounded-lg border border-slate-300 px-4 py-2 text-sm transition-colors focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
          </div>

          <div className="mt-6 flex flex-col gap-4 border-t border-slate-100 pt-5 dark:border-slate-700 sm:flex-row sm:gap-6">
              <div className="flex-1">
                <RoleClusterSelect
                  options={roleTaxonomy}
                  selected={localFilters.roleClusters}
                  onChange={(ids) => setLocalFilters({ ...localFilters, roleClusters: ids })}
                />
              </div>

              <div className="sm:w-48">
                <label className="mb-2 block text-sm font-medium text-slate-700 dark:text-slate-300">
                  Experience Level
                  {localFilters.predictedTiers.length > 0 && (
                    <button
                      type="button"
                      onClick={() => setLocalFilters({ ...localFilters, predictedTiers: [] })}
                      className="ml-2 text-xs font-normal text-violet-500 hover:text-violet-700"
                    >
                      Clear
                    </button>
                  )}
                </label>
                <div className="flex flex-wrap gap-2">
                  {TIER_OPTIONS.map(({ value, label }) => {
                    const selected = localFilters.predictedTiers.includes(value)
                    return (
                      <button
                        key={value}
                        type="button"
                        onClick={() => {
                          const next = selected
                            ? localFilters.predictedTiers.filter((t) => t !== value)
                            : [...localFilters.predictedTiers, value]
                          setLocalFilters({ ...localFilters, predictedTiers: next })
                        }}
                        className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                          selected
                            ? 'bg-violet-600 text-white'
                            : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-700 dark:text-slate-300 dark:hover:bg-slate-600'
                        }`}
                      >
                        {label}
                      </button>
                    )
                  })}
                </div>
              </div>
            </div>
        </CardBody>
      </Card>

      {loading && jobs.length === 0 ? (
        <LoadingState variant="matches" count={5} />
      ) : !loading && jobs.length === 0 ? (
        <Card className="border-slate-200 dark:border-slate-700">
          <CardBody>
            <EmptyState
              icon={Sparkles}
              message="All current matches have been rated!"
              description="Run mcf crawl-incremental to pull new jobs, or lower your filters above."
              action={
                <Button variant="outline" onClick={handleRefresh}>
                  <RefreshCw className="size-4" />
                  Refresh
                </Button>
              }
            />
          </CardBody>
        </Card>
      ) : (
        <div className="relative">
          {loading && jobs.length > 0 && (
            <div className="absolute inset-0 z-10 flex justify-center pt-8 bg-white/70 rounded-xl dark:bg-slate-900/70">
              <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 shadow-sm dark:border-slate-700 dark:bg-slate-800">
                <Spinner size="sm" />
                <span className="text-sm text-slate-600 dark:text-slate-400">Updating matches…</span>
              </div>
            </div>
          )}
          <div className="space-y-4">
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Showing <strong className="text-slate-700 dark:text-slate-300">{displayedJobs.length}</strong> unrated {displayedJobs.length === 1 ? 'job' : 'jobs'}
              {salaryFilterActive && (
                <span className="ml-2 text-violet-600 dark:text-violet-400">(salary filter active — only jobs with disclosed salary in range)</span>
              )}
            </p>
            {displayedJobs.map((job) => (
              <div
                key={job.job_uuid}
                className="transition-shadow hover:shadow-md"
              >
                <MatchCard
                  match={job}
                  mode="resume"
                  onInteraction={rate}
                  loading={ratingUuids.has(job.job_uuid)}
                />
              </div>
            ))}

            <div className="flex flex-wrap justify-center gap-4 pt-4">
              <Button
                onClick={handleLoadMore}
                disabled={loadingMore || !hasMore}
                title={!hasMore ? 'No more matches available' : 'Load next 25 jobs'}
              >
                {loadingMore && <Spinner size="sm" variant="light" />}
                {loadingMore ? 'Loading…' : hasMore ? 'Load more' : 'No more matches'}
              </Button>
              <Button variant="outline" onClick={handleRefresh}>
                <RefreshCw className="size-4" />
                Refresh
              </Button>
            </div>
          </div>
        </div>
      )}

      {showTutorialStep3 && (
        <TutorialModal step={3} onClose={() => setShowTutorialStep3(false)} />
      )}
      {showTutorialStep4 && (
        <TutorialModal step={4} onClose={() => setShowTutorialStep4(false)} />
      )}
    </div>
  )
}
