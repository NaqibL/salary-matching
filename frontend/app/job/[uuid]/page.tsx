'use client'

import { useParams, useRouter } from 'next/navigation'
import useSWR from 'swr'
import { ArrowLeft, Building2, MapPin, ExternalLink } from 'lucide-react'
import { jobsApi } from '@/lib/api'
import { getJobDetailKey } from '@/lib/job-prefetch'
import { Layout } from '@/app/components/layout'
import NavUserActions from '@/app/components/NavUserActions'
import { Card, CardBody, PageHeader } from '@/components/design'
import { Button } from '@/components/ui/button'
import type { JobDetail } from '@/lib/types'
import AuthGate from '@/app/components/AuthGate'

function JobDetailContent() {
  const params = useParams()
  const router = useRouter()
  const uuid = params.uuid as string

  const { data: job, error, isLoading } = useSWR<JobDetail>(
    getJobDetailKey(uuid),
    () => jobsApi.getJobDetail(uuid),
    { revalidateOnFocus: false }
  )

  if (error) {
    return (
      <Layout userSlot={<NavUserActions />}>
        <div className="space-y-4">
          <Button variant="ghost" size="sm" onClick={() => router.back()}>
            <ArrowLeft className="size-4" />
            Back
          </Button>
          <Card className="border-slate-200 dark:border-slate-700">
            <CardBody>
              <p className="text-slate-600 dark:text-slate-400">
                Job not found or failed to load.
              </p>
            </CardBody>
          </Card>
        </div>
      </Layout>
    )
  }

  if (isLoading || !job) {
    return (
      <Layout userSlot={<NavUserActions />}>
        <div className="space-y-4">
          <div className="h-8 w-32 animate-pulse rounded bg-slate-200 dark:bg-slate-700" />
          <div className="h-64 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />
        </div>
      </Layout>
    )
  }

  return (
    <Layout userSlot={<NavUserActions />}>
      <PageHeader
        title={job.title}
        subtitle={job.company_name ?? 'Company'}
        action={
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={() => router.back()}>
              <ArrowLeft className="size-4" />
              Back
            </Button>
            {job.job_url && (
              <a
                href={job.job_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
              >
                View on MyCareersFuture
                <ExternalLink size={14} />
              </a>
            )}
          </div>
        }
      />
      <Card className="border-slate-200 dark:border-slate-700">
        <CardBody className="space-y-4">
          <div className="flex flex-wrap gap-4 text-sm text-slate-600 dark:text-slate-400">
            {job.company_name && (
              <span className="flex items-center gap-1.5">
                <Building2 size={16} className="shrink-0" />
                {job.company_name}
              </span>
            )}
            {job.location && (
              <span className="flex items-center gap-1.5">
                <MapPin size={16} className="shrink-0" />
                {job.location}
              </span>
            )}
          </div>
          {job.skills && job.skills.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                Skills
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {job.skills.map((s) => (
                  <span
                    key={s}
                    className="px-2 py-0.5 bg-indigo-50 text-indigo-700 text-xs font-medium rounded-md dark:bg-indigo-900/30 dark:text-indigo-300"
                  >
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}
        </CardBody>
      </Card>
    </Layout>
  )
}

export default function JobDetailPage() {
  return (
    <AuthGate>
      {() => <JobDetailContent />}
    </AuthGate>
  )
}
