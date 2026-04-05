/**
 * Job detail prefetch utilities using SWR.
 * Use for: initial top-10 prefetch, hover prefetch on job cards.
 */
import { mutate } from 'swr'
import { jobsApi } from './api'
import type { JobDetail } from './types'

export const JOB_DETAIL_SWR_KEY_PREFIX = 'job-detail-'

export function getJobDetailKey(jobUuid: string): string {
  return `${JOB_DETAIL_SWR_KEY_PREFIX}${jobUuid}`
}

/** Prefetch job detail into SWR cache. Safe to call multiple times. */
export async function prefetchJobDetail(jobUuid: string): Promise<void> {
  const key = getJobDetailKey(jobUuid)
  try {
    const data = await jobsApi.getJobDetail(jobUuid)
    mutate(key, data, { revalidate: false })
  } catch {
    // Non-fatal; job page will fetch on demand
  }
}

/** Prefetch top N job details. Call when matches page loads. */
export async function prefetchJobDetailsTopN(
  jobUuids: string[],
  n: number = 10
): Promise<void> {
  const toPrefetch = jobUuids.slice(0, n)
  await Promise.all(toPrefetch.map((uuid) => prefetchJobDetail(uuid)))
}
