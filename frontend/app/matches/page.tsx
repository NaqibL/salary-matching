'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import dynamic from 'next/dynamic'
import type { Session } from '@supabase/supabase-js'
import { profileApi } from '@/lib/api'
import { supabase, isSupabaseConfigured } from '@/lib/supabase'
import AuthGate from '../components/AuthGate'
import { useProfileContext } from '../components/ProfileProvider'
import { RatingsQueueProvider } from '../components/RatingsQueueProvider'
import { Layout } from '../components/layout'
import NavUserActions from '../components/NavUserActions'
import { PageHeader, Card, CardBody, LoadingState } from '@/components/design'
import { Button } from '@/components/ui/button'
import { MatchesErrorBoundary } from '../MatchesErrorBoundary'
import Spinner from '../components/Spinner'
import { TutorialModal, getTutorialStep, hasSeenTutorial } from '../components/TutorialModal'
import { toast } from 'sonner'
import { Upload, RefreshCw, FileWarning } from 'lucide-react'

const LazyResumeTab = dynamic(() => import('../components/ResumeTab'), {
  ssr: false,
  loading: () => <LoadingState variant="matches" count={3} />,
})

const LazyTasteTab = dynamic(() => import('../components/TasteTab'), {
  ssr: false,
  loading: () => <LoadingState variant="matches" count={3} />,
})

type Tab = 'resume' | 'taste'

const TABS = [
  { id: 'resume' as const, label: 'Resume Matches' },
  { id: 'taste' as const, label: 'Taste Matches' },
]

function MatchesHeaderActions({
  profile,
  loadingProfile,
  processingResume,
  onUploadClick,
  onProcessResume,
  onStartTutorial,
}: {
  profile: { profile?: unknown; resume_exists?: boolean } | null | undefined
  loadingProfile: boolean
  processingResume: boolean
  onUploadClick: () => void
  onProcessResume: () => void
  onStartTutorial?: () => void
  fileInputRef?: React.RefObject<HTMLInputElement | null>
}) {
  if (loadingProfile || !isSupabaseConfigured) return null
  const showTutorialButton = onStartTutorial && !hasSeenTutorial()

  return (
    <div className="flex flex-wrap items-center gap-3">
      {showTutorialButton && (
        <Button variant="outline" size="sm" onClick={onStartTutorial} className="text-slate-600 dark:text-slate-400">
          First time? Start tutorial
        </Button>
      )}
      {profile?.profile ? (
        <>
          <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-medium text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">
            Resume ready
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={onUploadClick}
            disabled={processingResume}
            className="text-slate-600 dark:text-slate-400"
          >
            <Upload className="size-4" />
            Replace
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onProcessResume}
            disabled={processingResume}
            className="text-slate-600 dark:text-slate-400"
          >
            <RefreshCw className="size-4" />
            Re-process
          </Button>
        </>
      ) : (
        <Button
          size="sm"
          onClick={onUploadClick}
          disabled={processingResume}
        >
          <Upload className="size-4" />
          {processingResume ? 'Processing…' : 'Upload Resume'}
        </Button>
      )}
      {isSupabaseConfigured && <NavUserActions />}
    </div>
  )
}

function App({ session }: { session: Session | null }) {
  const userId = session?.user?.id ?? (isSupabaseConfigured ? null : 'default')
  const { profile, isLoading: loadingProfile, isValidating, invalidateProfile } = useProfileContext()
  const [tab, setTab] = useState<Tab>('resume')
  const [processingResume, setProcessingResume] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const onUploadClick = useCallback(() => fileInputRef.current?.click?.(), [])
  const handleTabClick = useCallback((id: Tab) => setTab(id), [])

  useEffect(() => {
    if (!userId) return
    if (profile && !isValidating && profile.resume_exists && !profile.profile) {
      setProcessingResume(true)
      profileApi
        .processResume()
        .then(() => {
          invalidateProfile()
        })
        .then(() => toast.success('Resume processed automatically!'))
        .catch((err: unknown) => {
          const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
          toast.error(detail || 'Auto-processing resume failed. Upload your resume to continue.')
        })
        .finally(() => setProcessingResume(false))
    }
  }, [userId, profile?.resume_exists, profile?.profile, isValidating, invalidateProfile])

  const handleProcessResume = async () => {
    setProcessingResume(true)
    try {
      await profileApi.processResume()
      invalidateProfile()
      toast.success('Resume processed!')
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail || 'Failed to process resume')
    } finally {
      setProcessingResume(false)
    }
  }

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    e.target.value = ''

    setProcessingResume(true)
    try {
      await profileApi.uploadResume(file)
      invalidateProfile()
      toast.success('Resume uploaded and processed!')
    } catch (err: unknown) {
      const errObj = err as { response?: { status?: number; data?: { detail?: string } }; message?: string }
      const status = errObj.response?.status
      const detail = errObj.response?.data?.detail
      const msg =
        status === 401
          ? 'Session expired. Please sign in again.'
          : status === 403
            ? 'Access denied. Check your login.'
            : status === 500
              ? (detail || 'Server error. Check Railway logs for details.')
              : detail ||
                (errObj.message?.includes('Network') || !errObj.response
                  ? 'Network error. In Vercel, set NEXT_PUBLIC_API_URL to your Railway URL and redeploy.'
                  : 'Upload failed. Try again.')
      toast.error(msg)
    } finally {
      setProcessingResume(false)
    }
  }

  const needsResume = !loadingProfile && profile && !profile.resume_exists && !profile.profile

  const [tutorialStep, setTutorialStepState] = useState<number | null>(null)
  const [showTutorial, setShowTutorial] = useState(false)

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (hasSeenTutorial()) return
    const step = getTutorialStep()
    if (needsResume && step === 1) {
      setShowTutorial(true)
      setTutorialStepState(1)
    } else if (profile?.profile && step === 2) {
      setShowTutorial(true)
      setTutorialStepState(2)
    } else if (profile?.profile && step === 1) {
      setTutorialStepState(2)
      setShowTutorial(true)
      setTutorialStepState(2)
    }
  }, [needsResume, profile?.profile])

  const handleStartTutorial = useCallback(() => {
    if (needsResume) {
      setTutorialStepState(1)
    } else if (profile?.profile) {
      setTutorialStepState(2)
    } else {
      setTutorialStepState(1)
    }
    setShowTutorial(true)
  }, [needsResume, profile?.profile])

  const handleTutorialClose = useCallback(() => {
    setShowTutorial(false)
    setTutorialStepState(null)
  }, [])

  return (
    <Layout
      userSlot={
        <MatchesHeaderActions
          profile={profile}
          loadingProfile={loadingProfile}
          processingResume={processingResume}
          onUploadClick={onUploadClick}
          onProcessResume={handleProcessResume}
          onStartTutorial={handleStartTutorial}
          fileInputRef={fileInputRef}
        />
      }
    >
      {showTutorial && tutorialStep && tutorialStep <= 2 && (
        <TutorialModal
          step={tutorialStep as 1 | 2}
          onClose={handleTutorialClose}
          onUploadClick={tutorialStep === 1 ? onUploadClick : undefined}
        />
      )}
      <MatchesErrorBoundary>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx"
          className="hidden"
          onChange={handleFileUpload}
        />

        {processingResume && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-white/80 backdrop-blur-sm">
            <div className="flex flex-col items-center gap-4">
              <Spinner size="lg" />
              <p className="text-slate-600 font-medium dark:text-slate-400">Processing resume…</p>
            </div>
          </div>
        )}

        {needsResume && (
          <Card className="mb-6 border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-900/20">
            <CardBody className="flex flex-row items-center gap-4">
              <div className="flex size-10 shrink-0 items-center justify-center rounded-full bg-amber-100 text-amber-600 dark:bg-amber-900/50 dark:text-amber-400">
                <FileWarning className="size-5" />
              </div>
              <p className="text-sm text-amber-800 dark:text-amber-200">
                No resume found. Click <strong>Upload Resume</strong> in the header to get started.
              </p>
            </CardBody>
          </Card>
        )}

        <PageHeader
          title="Job Matches"
          subtitle="Find jobs that fit your resume and preferences"
          action={
            <div className="flex gap-1 rounded-lg bg-slate-100 p-1 dark:bg-slate-700">
              {TABS.map(({ id, label }) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => handleTabClick(id)}
                  className={`px-4 py-2 text-sm font-medium rounded-md transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-2 ${
                    tab === id
                      ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-600 dark:text-slate-100'
                      : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          }
        />

        <RatingsQueueProvider>
          <div className="mt-6">
            {tab === 'resume' && <LazyResumeTab />}
            {tab === 'taste' && <LazyTasteTab />}
          </div>
        </RatingsQueueProvider>
      </MatchesErrorBoundary>
    </Layout>
  )
}

export default function Home() {
  return (
    <AuthGate>
      {(session) => <App session={session} />}
    </AuthGate>
  )
}
