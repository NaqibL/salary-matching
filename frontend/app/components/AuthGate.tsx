'use client'

import { useEffect, useState, useRef } from 'react'
import dynamic from 'next/dynamic'
import type { Session } from '@supabase/supabase-js'
import Link from 'next/link'
import { supabase, isSupabaseConfigured } from '@/lib/supabase'
import { dashboardApi } from '@/lib/api'
import Spinner from './Spinner'
import {
  PageHeader,
  Card,
  CardHeader,
  CardTitle,
  CardBody,
  EmptyState,
} from '@/components/design'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { AuthErrorBoundary } from './AuthErrorBoundary'
import { AuthDashboardPreview } from './AuthDashboardPreview'
import { ProfileProvider } from './ProfileProvider'
import { Database } from 'lucide-react'

const LazyAuthDashboardPreview = dynamic(
  () => import('./AuthDashboardPreview').then((m) => ({ default: m.AuthDashboardPreview })),
  {
    ssr: false,
    loading: () => (
      <div className="space-y-8">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-700" />
          ))}
        </div>
        <div className="h-64 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-700" />
        <div className="h-64 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-700" />
      </div>
    ),
  },
)

interface Props {
  children: (session: Session | null) => React.ReactNode
}

type Summary = {
  total_jobs: number
  active_jobs: number
  jobs_with_embeddings: number
}

/**
 * Wraps the entire app. When Supabase is configured it shows a simple
 * email+password sign-in/sign-up form for unauthenticated visitors.
 * No magic links, no email services. When Supabase is NOT configured
 * (local dev) it passes `session = null` directly through so the app
 * works without any auth setup.
 */
export default function AuthGate({ children }: Props) {
  const [session, setSession] = useState<Session | null | undefined>(undefined)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [isSignUp, setIsSignUp] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [summary, setSummary] = useState<Summary | null>(null)
  const [activeJobsOverTime, setActiveJobsOverTime] = useState<Array<{ date: string; active_count: number }>>([])
  const [jobsByCategory, setJobsByCategory] = useState<Array<{ category: string; count: number }>>([])
  const [dashboardLoaded, setDashboardLoaded] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!isSupabaseConfigured) {
      setSession(null)
      return
    }

    supabase.auth.getSession().then(({ data }) => setSession(data.session))

    const { data: listener } = supabase.auth.onAuthStateChange((_event, s) => {
      setSession(s)
    })
    return () => listener.subscription.unsubscribe()
  }, [])

  useEffect(() => {
    if (!isSupabaseConfigured || session) return
    Promise.all([
      dashboardApi.getSummaryPublic().then((s) => {
        setSummary(s)
        return s
      }),
      dashboardApi.getActiveJobsOverTimePublic(30).then(setActiveJobsOverTime),
      dashboardApi.getJobsByCategoryPublic(30, 8).then((data) =>
        setJobsByCategory((data || []).filter((x) => x.category !== 'Unknown')),
      ),
    ])
      .then(() => setDashboardLoaded(true))
      .catch(() => setDashboardLoaded(true))
  }, [session])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim() || !password) return
    setLoading(true)
    setError('')
    const { error: err } = isSignUp
      ? await supabase.auth.signUp({ email: email.trim(), password })
      : await supabase.auth.signInWithPassword({ email: email.trim(), password })
    setLoading(false)
    if (err) {
      setError(err.message)
    } else {
      setEmail('')
      setPassword('')
    }
  }

  const hasDashboardData = summary || activeJobsOverTime.length > 0 || jobsByCategory.length > 0

  // Still loading auth state
  if (session === undefined) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-slate-50 px-4 dark:bg-slate-900">
        <div className="w-full max-w-sm space-y-4">
          <div className="h-8 w-48 animate-pulse rounded-lg bg-slate-200 dark:bg-slate-700" />
          <div className="h-4 w-64 animate-pulse rounded-lg bg-slate-200 dark:bg-slate-700" />
          <div className="rounded-xl border border-slate-200 bg-white p-6 dark:border-slate-700 dark:bg-slate-800">
            <div className="space-y-4">
              <div className="h-10 animate-pulse rounded-lg bg-slate-200 dark:bg-slate-700" />
              <div className="h-10 animate-pulse rounded-lg bg-slate-200 dark:bg-slate-700" />
              <div className="h-10 animate-pulse rounded-lg bg-slate-200 dark:bg-slate-700" />
            </div>
          </div>
        </div>
      </div>
    )
  }

  // Auth disabled (local dev) or already signed in
  if (!isSupabaseConfigured || session) {
    const userId = session?.user?.id ?? (isSupabaseConfigured ? null : 'default')
    return (
      <ProfileProvider userId={userId}>
        {children(session)}
      </ProfileProvider>
    )
  }

  return (
    <AuthErrorBoundary>
      <div className="min-h-screen flex flex-col">
        <header className="sticky top-0 z-30 flex items-center h-14 px-6 bg-white border-b border-slate-200 dark:bg-slate-900 dark:border-slate-800 shrink-0">
          <Link
            href="/"
            className="text-lg font-semibold text-slate-900 dark:text-slate-100 hover:text-slate-700 dark:hover:text-slate-300 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 rounded-lg"
          >
            MCF
          </Link>
        </header>

        <div className="flex-1 flex flex-col lg:flex-row">
          {/* Left: Hero + Form */}
          <div className="flex min-h-[60vh] flex-col justify-center px-4 py-8 sm:px-6 sm:py-12 lg:w-[40%] lg:px-8 lg:py-16 bg-gradient-to-br from-slate-50 via-indigo-50/20 to-teal-50/30 dark:from-slate-900 dark:via-indigo-950/20 dark:to-slate-900">
            <PageHeader
              title="Find your next role here"
              subtitle="Explore the market or sign in to match your resume."
              action={
                <Link
                  href="/how-it-works"
                  className="text-sm font-medium text-indigo-600 transition-colors hover:text-indigo-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 rounded-lg dark:text-indigo-400 dark:hover:text-indigo-300"
                >
                  How does it work? →
                </Link>
              }
            />

            <div className="mt-8 w-full max-w-sm">
              <Card className="border-slate-200/80 bg-white/90 shadow-sm backdrop-blur-sm dark:border-slate-700 dark:bg-slate-800/90">
                <CardHeader className="mb-4 border-0 pb-0">
                  <CardTitle className="text-slate-900 dark:text-slate-100">
                    {isSignUp ? 'Create account' : 'Sign in'}
                  </CardTitle>
                </CardHeader>
                <CardBody>
                  <form onSubmit={handleSubmit} className="space-y-4">
                    <div className="space-y-2">
                      <label
                        htmlFor="auth-email"
                        className="block text-sm font-medium text-slate-700 dark:text-slate-300"
                      >
                        Email
                      </label>
                      <Input
                        ref={inputRef}
                        id="auth-email"
                        type="email"
                        autoComplete="email"
                        required
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="you@example.com"
                        className="h-10 w-full"
                      />
                    </div>

                    <div className="space-y-2">
                      <label
                        htmlFor="auth-password"
                        className="block text-sm font-medium text-slate-700 dark:text-slate-300"
                      >
                        Password
                      </label>
                      <Input
                        id="auth-password"
                        type="password"
                        autoComplete={isSignUp ? 'new-password' : 'current-password'}
                        required
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="••••••••"
                        className="h-10 w-full"
                      />
                    </div>

                    {error && (
                      <p className="rounded-lg bg-rose-50 px-4 py-2 text-sm text-rose-600 dark:bg-rose-900/30 dark:text-rose-400">
                        {error}
                      </p>
                    )}

                    <Button
                      type="submit"
                      disabled={loading}
                      className="h-10 w-full"
                    >
                      {loading ? (
                        <>
                          <Spinner size="sm" variant="light" />
                          Please wait…
                        </>
                      ) : isSignUp ? (
                        'Sign up'
                      ) : (
                        'Sign in'
                      )}
                    </Button>
                  </form>

                  <p className="mt-6 text-center text-sm text-slate-500 dark:text-slate-400">
                    {isSignUp ? (
                      <>
                        Already have an account?{' '}
                        <button
                          type="button"
                          onClick={() => {
                            setIsSignUp(false)
                            setError('')
                          }}
                          className="font-medium text-indigo-600 transition-colors hover:text-indigo-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 rounded dark:text-indigo-400 dark:hover:text-indigo-300"
                        >
                          Sign in
                        </button>
                      </>
                    ) : (
                      <>
                        Don&apos;t have an account?{' '}
                        <button
                          type="button"
                          onClick={() => {
                            setIsSignUp(true)
                            setError('')
                          }}
                          className="font-medium text-indigo-600 transition-colors hover:text-indigo-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 rounded dark:text-indigo-400 dark:hover:text-indigo-300"
                        >
                          Sign up
                        </button>
                      </>
                    )}
                  </p>
                </CardBody>
              </Card>
            </div>
          </div>

          {/* Right: Dashboard preview */}
          <div className="overflow-auto bg-white/80 px-4 py-8 dark:bg-slate-900/80 lg:w-[60%] lg:px-8 lg:py-12">
            {!dashboardLoaded && !hasDashboardData ? (
              <div className="space-y-8">
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="h-20 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-700" />
                  ))}
                </div>
                <div className="h-64 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-700" />
                <div className="h-64 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-700" />
              </div>
            ) : !hasDashboardData ? (
              <Card className="border-slate-200 dark:border-slate-700">
                <CardBody>
                  <EmptyState
                    icon={Database}
                    message="Live job data will appear when the server is connected"
                    description="Connect the API server and run a crawl to see job market insights here."
                  />
                </CardBody>
              </Card>
            ) : (
              <LazyAuthDashboardPreview
                summary={summary}
                activeJobsOverTime={activeJobsOverTime}
                jobsByCategory={jobsByCategory}
                loading={false}
              />
            )}
          </div>
        </div>
      </div>
    </AuthErrorBoundary>
  )
}
