'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { supabase, isSupabaseConfigured } from '@/lib/supabase'
import { clearStoredProfile } from '@/lib/profile-cache'
import type { Session } from '@supabase/supabase-js'

export default function NavUserActions() {
  const [session, setSession] = useState<Session | null | undefined>(undefined)

  useEffect(() => {
    if (!isSupabaseConfigured) return
    supabase.auth.getSession().then(({ data }) => setSession(data.session))
    const { data: listener } = supabase.auth.onAuthStateChange((_e, s) => setSession(s))
    return () => listener.subscription.unsubscribe()
  }, [])

  if (!isSupabaseConfigured) return null
  // Still loading
  if (session === undefined) return null

  if (!session) {
    return (
      <Link
        href="/matches"
        className="text-sm font-medium text-slate-400 hover:text-slate-900 dark:hover:text-white transition-colors"
      >
        Sign In
      </Link>
    )
  }

  const handleSignOut = async () => {
    const userId = session.user.id
    await supabase.auth.signOut()
    clearStoredProfile(userId)
  }

  return (
    <button
      onClick={handleSignOut}
      className="text-sm text-slate-400 hover:text-slate-900 dark:hover:text-white transition-colors"
      title="Sign out"
    >
      Sign out
    </button>
  )
}
