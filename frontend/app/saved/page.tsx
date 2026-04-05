'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import { jobsApi } from '@/lib/api'
import type { Match } from '@/lib/types'
import AuthGate from '../components/AuthGate'
import { useProfileContext } from '../components/ProfileProvider'
import { Layout } from '../components/layout'
import NavUserActions from '../components/NavUserActions'
import { PageHeader, Card, CardBody, EmptyState, LoadingState } from '@/components/design'
import { MatchCard } from '../components/JobCard'
import { toast } from 'sonner'
import { Bookmark } from 'lucide-react'

function SavedPageContent() {
  const { invalidateProfile } = useProfileContext()
  const [jobs, setJobs] = useState<Match[]>([])
  const [loading, setLoading] = useState(true)
  const [removingUuids, setRemovingUuids] = useState<Set<string>>(new Set())
  const jobsRef = useRef<Match[]>([])
  jobsRef.current = jobs

  const loadJobs = useCallback(async () => {
    setLoading(true)
    try {
      const { jobs: data } = await jobsApi.getInterested()
      setJobs(data)
    } catch {
      toast.error('Failed to load saved jobs. Is the API server running?')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadJobs()
  }, [loadJobs])

  const handleRemove = useCallback(async (uuid: string) => {
    const jobToRestore = jobsRef.current.find((j) => j.job_uuid === uuid)
    setRemovingUuids((prev) => new Set(prev).add(uuid))
    setJobs((prev) => prev.filter((j) => j.job_uuid !== uuid))
    try {
      await jobsApi.markInteraction(uuid, 'not_interested')
      invalidateProfile()
      toast.success('Removed from saved')
    } catch {
      if (jobToRestore) {
        setJobs((prev) => [...prev, jobToRestore])
      }
      toast.error('Failed to remove')
    } finally {
      setRemovingUuids((prev) => {
        const next = new Set(prev)
        next.delete(uuid)
        return next
      })
    }
  }, [invalidateProfile])

  return (
    <Layout userSlot={<NavUserActions />}>
      <PageHeader
        title="Saved Jobs"
        subtitle="Jobs you marked as Interested — easy to find when you're ready to apply"
      />

      {loading ? (
        <LoadingState variant="matches" count={5} />
      ) : jobs.length === 0 ? (
        <Card className="border-slate-200 dark:border-slate-700">
          <CardBody>
            <EmptyState
              icon={Bookmark}
              message="No saved jobs yet"
              description="When you mark a job as Interested in Resume or Taste matches, it will appear here for easy access."
            />
          </CardBody>
        </Card>
      ) : (
        <div className="space-y-4">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {jobs.length} saved {jobs.length === 1 ? 'job' : 'jobs'}
          </p>
          {jobs.map((job) => (
            <div key={job.job_uuid} className="transition-shadow hover:shadow-md">
              <MatchCard
                match={job}
                mode="saved"
                onInteraction={handleRemove}
                loading={removingUuids.has(job.job_uuid)}
              />
            </div>
          ))}
        </div>
      )}
    </Layout>
  )
}

export default function SavedPage() {
  return (
    <AuthGate>
      {() => <SavedPageContent />}
    </AuthGate>
  )
}
