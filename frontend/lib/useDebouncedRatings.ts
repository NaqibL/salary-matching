/**
 * Debounced rating submissions for Discover page.
 *
 * Batches ratings: flush on 5 items OR 2 seconds (whichever first).
 * - Optimistic UI: caller handles immediately (remove from list, update stats)
 * - Background sync: this hook queues and syncs to API
 * - Invalidates match cache after each batch sync
 */

import { useCallback, useRef, useEffect } from 'react'
import { api, revalidateMatches } from './api'

const BATCH_SIZE = 5
const BATCH_DELAY_MS = 500

type RatingItem = { jobUuid: string; interactionType: string }

export function useDebouncedRatings(options?: {
  onFlushError?: () => void
  onFlushSuccess?: () => void
}) {
  const onFlushErrorRef = useRef(options?.onFlushError)
  onFlushErrorRef.current = options?.onFlushError
  const onFlushSuccessRef = useRef(options?.onFlushSuccess)
  onFlushSuccessRef.current = options?.onFlushSuccess
  const queueRef = useRef<RatingItem[]>([])
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const flushInProgressRef = useRef(false)

  const flush = useCallback(async () => {
    if (flushInProgressRef.current || queueRef.current.length === 0) return

    const batch = [...queueRef.current]
    queueRef.current = []

    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }

    flushInProgressRef.current = true
    try {
      await Promise.all(
        batch.map(({ jobUuid, interactionType }) =>
          api.post(`/api/jobs/${jobUuid}/interact`, null, {
            params: { interaction_type: interactionType },
          }),
        ),
      )
      await revalidateMatches()
      onFlushSuccessRef.current?.()
    } catch {
      onFlushErrorRef.current?.()
    } finally {
      flushInProgressRef.current = false
    }
  }, [])

  const queueRating = useCallback(
    (jobUuid: string, interactionType: string) => {
      queueRef.current.push({ jobUuid, interactionType })

      if (queueRef.current.length >= BATCH_SIZE) {
        flush()
        return
      }

      if (queueRef.current.length === 1) {
        timerRef.current = setTimeout(flush, BATCH_DELAY_MS)
      }
    },
    [flush],
  )

  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current)
      }
      if (queueRef.current.length > 0) {
        flush()
      }
    }
  }, [flush])

  return { queueRating, flush }
}
