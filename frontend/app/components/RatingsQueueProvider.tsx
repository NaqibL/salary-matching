'use client'

import { createContext, useContext, useCallback, type ReactNode } from 'react'
import { useDebouncedRatings } from '@/lib/useDebouncedRatings'
import { useProfileContext } from './ProfileProvider'
import { toast } from 'sonner'

type RatingsQueueContextValue = {
  queueRating: (jobUuid: string, interactionType: string) => void
  flush: () => Promise<void>
}

const RatingsQueueContext = createContext<RatingsQueueContextValue | null>(null)

export function RatingsQueueProvider({ children }: { children: ReactNode }) {
  const { invalidateProfile } = useProfileContext()
  const onFlushError = useCallback(() => {
    invalidateProfile()
    toast.error('Some ratings may not have been saved. Please refresh.')
  }, [invalidateProfile])
  const onFlushSuccess = useCallback(() => {
    invalidateProfile()
  }, [invalidateProfile])
  const { queueRating, flush } = useDebouncedRatings({ onFlushError, onFlushSuccess })
  return (
    <RatingsQueueContext.Provider value={{ queueRating, flush }}>
      {children}
    </RatingsQueueContext.Provider>
  )
}

export function useRatingsQueue(): RatingsQueueContextValue {
  const ctx = useContext(RatingsQueueContext)
  if (!ctx) {
    throw new Error('useRatingsQueue must be used within RatingsQueueProvider')
  }
  return ctx
}
