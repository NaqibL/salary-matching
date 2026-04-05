'use client'

import { createContext, useContext, type ReactNode } from 'react'
import {
  useUserProfile,
  invalidateProfile,
  optimisticUpdateStats,
  type UserProfile,
} from '@/lib/profile-cache'

type ProfileContextValue = {
  profile: UserProfile | null | undefined
  isLoading: boolean
  isValidating: boolean
  mutate: () => void
  invalidateProfile: () => void
  optimisticUpdateStats: (type: 'interested' | 'not_interested') => void
  userId: string | null
}

const ProfileContext = createContext<ProfileContextValue | null>(null)

export function ProfileProvider({
  userId,
  children,
}: {
  userId: string | null
  children: ReactNode
}) {
  const { data: profile, isLoading, isValidating, mutate } = useUserProfile(userId)

  const value: ProfileContextValue = {
    profile: profile ?? null,
    isLoading,
    isValidating,
    mutate,
    invalidateProfile: () => invalidateProfile(userId),
    optimisticUpdateStats: (type) => optimisticUpdateStats(userId, type),
    userId,
  }

  return (
    <ProfileContext.Provider value={value}>
      {children}
    </ProfileContext.Provider>
  )
}

export function useProfileContext(): ProfileContextValue {
  const ctx = useContext(ProfileContext)
  if (!ctx) {
    throw new Error('useProfileContext must be used within ProfileProvider')
  }
  return ctx
}
