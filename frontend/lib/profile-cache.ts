/**
 * User profile cache — SWR + localStorage persistence.
 *
 * Combines Profile (resume embedding, resume_exists) and DiscoverStats (job ratings).
 * - SWR with revalidateOnMount: false
 * - Optimistic updates on job rating
 * - localStorage backup for instant load on revisit
 *
 * Invalidate on: resume upload/process, compute taste, reset ratings.
 */

import useSWR, { mutate as globalMutate } from 'swr'
import { profileApi, discoverApi } from './api'
import type { Profile, DiscoverStats } from './types'

const STORAGE_KEY_PREFIX = 'mcf-profile-'

export type UserProfile = Profile & { stats: DiscoverStats }

function getStorageKey(userId: string): string {
  return `${STORAGE_KEY_PREFIX}${userId}`
}

function getProfileKey(userId: string | null): string[] | null {
  if (!userId) return null
  return ['user-profile', userId]
}

/** Read cached profile from localStorage (backup). */
export function getStoredProfile(userId: string | null): UserProfile | undefined {
  if (typeof window === 'undefined' || !userId) return undefined
  try {
    const raw = localStorage.getItem(getStorageKey(userId))
    if (!raw) return undefined
    const parsed = JSON.parse(raw) as UserProfile
    if (parsed && typeof parsed.user_id === 'string') return parsed
  } catch {
    // ignore
  }
  return undefined
}

/** Persist profile to localStorage. */
export function saveProfileToStorage(userId: string, data: UserProfile): void {
  if (typeof window === 'undefined') return
  try {
    localStorage.setItem(getStorageKey(userId), JSON.stringify(data))
  } catch {
    // quota exceeded, etc.
  }
}

/** Remove stored profile (e.g. on logout). */
export function clearStoredProfile(userId: string): void {
  if (typeof window === 'undefined') return
  try {
    localStorage.removeItem(getStorageKey(userId))
  } catch {
    // ignore
  }
}

async function fetchUserProfile(userId: string): Promise<UserProfile> {
  const [profile, stats] = await Promise.all([
    profileApi.get(),
    discoverApi.getStats(),
  ])
  const combined: UserProfile = { ...profile, stats }
  saveProfileToStorage(userId, combined)
  return combined
}

/**
 * useUserProfile — SWR hook for profile + stats.
 *
 * - revalidateOnMount: false — avoids refetch on every mount
 * - fallbackData from localStorage for instant load
 * - Persists to localStorage on fetch success
 */
export function useUserProfile(userId: string | null) {
  const key = getProfileKey(userId)
  const fallback = userId ? getStoredProfile(userId) : undefined

  const swr = useSWR<UserProfile>(
    key,
    key ? ([, id]: [string, string]) => fetchUserProfile(id) : null,
    {
      revalidateOnMount: false,
      revalidateOnFocus: false,
      revalidateIfStale: true,
      fallbackData: fallback,
      onSuccess: (data) => {
        if (userId && data) saveProfileToStorage(userId, data)
      },
    },
  )

  return swr
}

/**
 * Optimistic update when user rates a job.
 * Immediately updates stats in cache; API call happens separately.
 */
export function optimisticUpdateStats(
  userId: string | null,
  interactionType: 'interested' | 'not_interested',
) {
  if (!userId) return
  const key = getProfileKey(userId)
  if (!key) return

  globalMutate(
    key,
    (prev: UserProfile | undefined) => {
      if (!prev?.stats) return prev
      const next: UserProfile = {
        ...prev,
        stats: {
          ...prev.stats,
          [interactionType]: prev.stats[interactionType] + 1,
          total_rated: prev.stats.total_rated + 1,
          unrated: Math.max(0, prev.stats.unrated - 1),
        },
      }
      saveProfileToStorage(userId, next)
      return next
    },
    { revalidate: false },
  )
}

/**
 * Invalidate profile cache — force refetch.
 * Call after: resume upload, resume process, compute taste, reset ratings.
 */
export function invalidateProfile(userId: string | null): void {
  if (!userId) return
  const key = getProfileKey(userId)
  if (key) globalMutate(key)
}
