'use client'

import { useState, useCallback, useRef } from 'react'
import { matchesApi, profileApi } from '@/lib/api'
import { prefetchJobDetailsTopN } from '@/lib/job-prefetch'
import { useProfileContext } from './ProfileProvider'
import { useRatingsQueue } from './RatingsQueueProvider'
import type { Match } from '@/lib/types'
import { MatchCard } from './JobCard'
import {
  Card,
  CardBody,
  EmptyState,
  LoadingState,
} from '@/components/design'
import { Button } from '@/components/ui/button'
import Spinner from './Spinner'
import { toast } from 'sonner'
import { Search, Sparkles } from 'lucide-react'

interface Filters {
  topK: number
  minSimilarity: number
  maxDaysOld: number | null
}

export default function TasteTab() {
  const { profile, invalidateProfile, optimisticUpdateStats } = useProfileContext()
  const { queueRating } = useRatingsQueue()
  const stats = profile?.stats ?? null
  const [matches, setMatches] = useState<Match[]>([])
  const [filters, setFilters] = useState<Filters>({ topK: 25, minSimilarity: 0, maxDaysOld: null })
  const [finding, setFinding] = useState(false)
  const [loadingUuids, setLoadingUuids] = useState<Set<string>>(new Set())
  const [computing, setComputing] = useState(false)
  const matchesRef = useRef<Match[]>([])
  matchesRef.current = matches

  const findMatches = async () => {
    setFinding(true)
    try {
      const data = await matchesApi.get(
        'taste',
        true,
        filters.topK,
        0,
        filters.minSimilarity / 100,
        filters.maxDaysOld ?? undefined,
      )
      setMatches(data.matches)
      prefetchJobDetailsTopN(data.matches.map((m) => m.job_uuid), 10)
      if (data.matches.length === 0) {
        toast.info('No matches found. Try lowering the minimum score filter.')
      } else {
        toast.success(`Found ${data.matches.length} matches`)
      }
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail || 'Failed to find matches')
    } finally {
      setFinding(false)
    }
  }

  const handleComputeTaste = async () => {
    setComputing(true)
    try {
      const result = await profileApi.computeTaste()
      toast.success(
        `Taste profile updated from ${result.interested} interested jobs!`,
        { duration: 4000 },
      )
      invalidateProfile()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail || 'Failed to update taste profile')
    } finally {
      setComputing(false)
    }
  }

  const handleInteraction = useCallback((uuid: string, type: string) => {
    setMatches((m) => m.filter((j) => j.job_uuid !== uuid))
    setLoadingUuids((s) => new Set(s).add(uuid))
    if (type === 'interested' || type === 'not_interested') {
      optimisticUpdateStats(type)
      queueRating(uuid, type)
    }
    const label = type === 'interested' ? 'Interested ✓' : type === 'not_interested' ? 'Not Interested' : type
    toast.success(label, { duration: 1500 })
    setLoadingUuids((s) => {
      const next = new Set(s)
      next.delete(uuid)
      return next
    })
  }, [optimisticUpdateStats, queueRating])

  const interested = stats?.interested ?? 0
  const hasEnoughRatings = interested >= 3

  return (
    <div className="space-y-6">
      <Card className="border-slate-200 dark:border-slate-700">
        <CardBody>
          <p className="rounded-lg bg-violet-50 px-4 py-3 text-sm text-violet-700 dark:bg-violet-900/20 dark:text-violet-300">
            Jobs ranked by your <strong>Taste Profile</strong> — built from your ratings in the Resume tab.
            The more you rate, the better this gets. Add more ratings in Resume, then click{' '}
            <strong>Update Taste Profile</strong>.
          </p>

          <div className="mt-4 flex flex-wrap items-center gap-4">
            <Button
              onClick={handleComputeTaste}
              disabled={computing || !hasEnoughRatings}
              title={
                !hasEnoughRatings
                  ? `Mark at least 3 jobs as Interested in Resume tab first (${interested}/3)`
                  : 'Rebuild your taste profile from current ratings'
              }
              className="bg-violet-600 hover:bg-violet-700"
            >
              {computing && <Spinner size="sm" variant="light" />}
              {computing ? 'Updating…' : 'Update Taste Profile'}
            </Button>
            {!hasEnoughRatings && (
              <span className="text-sm text-slate-500 dark:text-slate-400">
                {3 - interested} more Interested {3 - interested === 1 ? 'job' : 'jobs'} needed (rate in Resume tab)
              </span>
            )}
          </div>

          <div className="mt-6 flex flex-wrap items-end gap-6 border-t border-slate-200 pt-6 dark:border-slate-700">
            <div className="flex-1 min-w-[200px]">
              <label className="mb-2 block text-sm font-medium text-slate-700 dark:text-slate-300">
                Min Match: <span className="font-semibold text-violet-600 dark:text-violet-400">{filters.minSimilarity}%</span>
              </label>
              <input
                type="range"
                min={0}
                max={80}
                step={5}
                value={filters.minSimilarity}
                onChange={(e) => setFilters({ ...filters, minSimilarity: parseInt(e.target.value) })}
                className="w-full accent-violet-600"
              />
            </div>
            <div className="w-24">
              <label className="mb-2 block text-sm font-medium text-slate-700 dark:text-slate-300">
                Results
              </label>
              <input
                type="number"
                min={1}
                max={100}
                value={filters.topK}
                onChange={(e) =>
                  setFilters({ ...filters, topK: parseInt(e.target.value) || 25 })
                }
                className="w-full rounded-lg border border-slate-300 px-4 py-2 text-sm transition-colors focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
            <div className="w-32">
              <label className="mb-2 block text-sm font-medium text-slate-700 dark:text-slate-300">
                Max Days Old
              </label>
              <input
                type="number"
                placeholder="No limit"
                min={1}
                value={filters.maxDaysOld ?? ''}
                onChange={(e) => {
                  const val = e.target.value
                  const parsed = val ? parseInt(val, 10) : null
                  setFilters({
                    ...filters,
                    maxDaysOld: parsed != null && !Number.isNaN(parsed) && parsed > 0 ? parsed : null,
                  })
                }}
                className="w-full rounded-lg border border-slate-300 px-4 py-2 text-sm transition-colors focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
          </div>

          <Button
            onClick={findMatches}
            disabled={finding || !hasEnoughRatings}
            className="mt-6 w-full bg-violet-600 hover:bg-violet-700"
          >
            {finding ? (
              <>
                <Spinner size="sm" variant="light" />
                Finding…
              </>
            ) : (
              'Find Taste Matches'
            )}
          </Button>
        </CardBody>
      </Card>

      {matches.length > 0 ? (
        <div className="space-y-4">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Showing <strong className="text-slate-700 dark:text-slate-300">{matches.length}</strong> matches via <strong>Taste Profile</strong>
          </p>
          {matches.map((m) => (
            <div key={m.job_uuid} className="transition-shadow hover:shadow-md">
              <MatchCard
                match={m}
                mode="taste"
                onInteraction={handleInteraction}
                loading={loadingUuids.has(m.job_uuid)}
              />
            </div>
          ))}
        </div>
      ) : finding ? (
        <LoadingState variant="matches" count={5} />
      ) : (
        <Card className="border-slate-200 dark:border-slate-700">
          <CardBody>
            <EmptyState
              icon={Search}
              message="Find jobs that match your taste"
              description={
                !hasEnoughRatings
                  ? 'Rate at least 3 jobs as Interested in the Resume tab first, then Update Taste Profile.'
                  : 'Click Find Taste Matches above to search for jobs ranked by your preferences.'
              }
              action={
                <Button
                  onClick={findMatches}
                  disabled={!hasEnoughRatings}
                  className="bg-violet-600 hover:bg-violet-700"
                >
                  Find Taste Matches
                </Button>
              }
            />
          </CardBody>
        </Card>
      )}
    </div>
  )
}
