'use client'

import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Upload, RefreshCw, ThumbsUp, Bookmark } from 'lucide-react'

const TUTORIAL_STORAGE_KEY = 'mcf_has_seen_tutorial'
const TUTORIAL_STEP_KEY = 'mcf_tutorial_step'

export function getTutorialStep(): number {
  if (typeof window === 'undefined') return 0
  const step = localStorage.getItem(TUTORIAL_STEP_KEY)
  return step ? parseInt(step, 10) : 1
}

export function setTutorialStep(step: number): void {
  if (typeof window === 'undefined') return
  localStorage.setItem(TUTORIAL_STEP_KEY, String(step))
}

export function hasSeenTutorial(): boolean {
  if (typeof window === 'undefined') return false
  return !!localStorage.getItem(TUTORIAL_STORAGE_KEY)
}

export function completeTutorial(): void {
  if (typeof window === 'undefined') return
  localStorage.setItem(TUTORIAL_STORAGE_KEY, '1')
  localStorage.removeItem(TUTORIAL_STEP_KEY)
}

export function dismissTutorialStep(step: number): void {
  if (typeof window === 'undefined') return
  if (step >= 4) {
    completeTutorial()
  } else {
    setTutorialStep(step + 1)
  }
}

export type TutorialStep = 1 | 2 | 3 | 4

interface TutorialModalProps {
  step: TutorialStep
  onClose: () => void
  onUploadClick?: () => void
}

const STEP_CONTENT: Record<
  TutorialStep,
  { title: string; body: string; icon: React.ElementType; primaryLabel: string; primaryAction?: 'upload' | 'viewSaved' }
> = {
  1: {
    title: 'Upload your resume',
    body: 'Upload your resume so we can match you with relevant jobs. We analyze your skills and experience to find the best fits.',
    icon: Upload,
    primaryLabel: 'Upload Resume',
    primaryAction: 'upload',
  },
  2: {
    title: 'Replace & Re-process',
    body: 'Replace: Use when you\'ve updated your resume with new experience or skills. Re-process: Use if matches seem off or you\'ve changed your profile — we\'ll re-analyze your resume.',
    icon: RefreshCw,
    primaryLabel: 'Got it',
  },
  3: {
    title: 'Rate jobs to train your taste',
    body: 'Rate jobs as Interested or Not Interested. This trains your Taste Profile so we can recommend jobs that match your preferences.',
    icon: ThumbsUp,
    primaryLabel: 'Got it',
  },
  4: {
    title: 'Your saved jobs',
    body: 'Jobs you mark as Interested are saved. Find them anytime in the Saved tab when you\'re ready to apply.',
    icon: Bookmark,
    primaryLabel: 'View Saved',
    primaryAction: 'viewSaved',
  },
}

export function TutorialModal({ step, onClose, onUploadClick }: TutorialModalProps) {
  const router = useRouter()
  const content = STEP_CONTENT[step]
  const Icon = content.icon

  const handlePrimary = () => {
    if (content.primaryAction === 'upload' && onUploadClick) {
      onUploadClick()
      dismissTutorialStep(step)
      onClose()
    } else if (content.primaryAction === 'viewSaved') {
      completeTutorial()
      onClose()
      router.push('/saved')
    } else {
      dismissTutorialStep(step)
      onClose()
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40">
      <div className="max-w-md w-full rounded-xl border border-slate-200 bg-white p-6 shadow-lg dark:border-slate-700 dark:bg-slate-800">
        <div className="flex items-center gap-3 mb-4">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-400">
            <Icon className="size-5" />
          </div>
          <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">{content.title}</h3>
        </div>
        <p className="mb-6 text-sm leading-relaxed text-slate-600 dark:text-slate-400">{content.body}</p>
        <div className="flex gap-3">
          {step > 1 && (
            <Button variant="outline" onClick={onClose} className="flex-1">
              Skip
            </Button>
          )}
          <Button onClick={handlePrimary} className={step > 1 ? 'flex-1' : 'w-full'}>
            {content.primaryLabel}
          </Button>
        </div>
        <p className="mt-4 text-center text-xs text-slate-400 dark:text-slate-500">
          Step {step} of 4
        </p>
      </div>
    </div>
  )
}
