'use client'

import { useRef, useState, useCallback } from 'react'
import type { Session } from '@supabase/supabase-js'
import { profileApi } from '@/lib/api'
import { supabase, isSupabaseConfigured } from '@/lib/supabase'
import { clearStoredProfile } from '@/lib/profile-cache'
import AuthGate from '../components/AuthGate'
import { useProfileContext } from '../components/ProfileProvider'
import { Layout } from '../components/layout'
import { PageHeader, Card, CardBody } from '@/components/design'
import { Button } from '@/components/ui/button'
import Spinner from '../components/Spinner'
import { toast } from 'sonner'
import { Upload, CheckCircle2, FileText, LogOut } from 'lucide-react'

function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / (1000 * 60))
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  if (diffMins < 2) return 'just now'
  if (diffHours < 1) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays === 1) return 'yesterday'
  if (diffDays < 7) return `${diffDays}d ago`
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function ProfilePageContent({ session }: { session: Session | null }) {
  const { profile, isLoading, invalidateProfile } = useProfileContext()
  const [processingResume, setProcessingResume] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const onUploadClick = useCallback(() => fileInputRef.current?.click?.(), [])

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const profileData = profile?.profile as any
  const updatedAt: string | undefined = profileData?.updated_at
  const stats = profile?.stats

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    e.target.value = ''
    setProcessingResume(true)
    try {
      await profileApi.uploadResume(file)
      invalidateProfile()
      toast.success('Resume uploaded and ready for matching!')
    } catch (err: unknown) {
      const errObj = err as { response?: { status?: number; data?: { detail?: string } }; message?: string }
      const status = errObj.response?.status
      const detail = errObj.response?.data?.detail
      const msg =
        status === 401
          ? 'Session expired. Please sign in again.'
          : status === 500
            ? (detail || 'Server error processing resume.')
            : detail || 'Upload failed. Try again.'
      toast.error(msg)
    } finally {
      setProcessingResume(false)
    }
  }

  const handleSignOut = async () => {
    if (!session) return
    const userId = session.user.id
    await supabase.auth.signOut()
    clearStoredProfile(userId)
  }

  return (
    <Layout>
      <PageHeader
        title="Profile"
        subtitle="Manage your resume and account"
      />

      <div className="mt-6 space-y-4 max-w-2xl">

        {/* Resume card */}
        <Card>
          <CardBody>
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-4">
              Resume
            </h2>

            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx"
              className="hidden"
              onChange={handleFileUpload}
            />

            {isLoading ? (
              <div className="flex items-center gap-3 text-sm text-slate-500">
                <Spinner size="sm" />
                Loading…
              </div>
            ) : profileData ? (
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-emerald-50 dark:bg-emerald-900/30">
                    <CheckCircle2 className="size-5 text-emerald-600 dark:text-emerald-400" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
                      Embedded and ready for matching
                    </p>
                    {updatedAt && (
                      <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                        Last updated {formatRelativeTime(updatedAt)}
                      </p>
                    )}
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={onUploadClick}
                  disabled={processingResume}
                  className="shrink-0"
                >
                  {processingResume ? (
                    <>
                      <Spinner size="sm" />
                      Updating…
                    </>
                  ) : (
                    <>
                      <Upload className="size-4" />
                      Update Resume
                    </>
                  )}
                </Button>
              </div>
            ) : (
              <div className="flex items-start gap-3">
                <div className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-slate-100 dark:bg-slate-800">
                  <FileText className="size-5 text-slate-400" />
                </div>
                <div className="flex-1">
                  <p className="text-sm font-medium text-slate-900 dark:text-slate-100">No resume uploaded</p>
                  <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                    Upload a PDF or DOCX to start matching with jobs.
                  </p>
                  <Button
                    size="sm"
                    onClick={onUploadClick}
                    disabled={processingResume}
                    className="mt-3"
                  >
                    {processingResume ? (
                      <>
                        <Spinner size="sm" variant="light" />
                        Uploading…
                      </>
                    ) : (
                      <>
                        <Upload className="size-4" />
                        Upload Resume
                      </>
                    )}
                  </Button>
                </div>
              </div>
            )}
          </CardBody>
        </Card>

        {/* Activity card — only when the user has rated jobs */}
        {stats && stats.total_rated > 0 && (
          <Card>
            <CardBody>
              <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-4">
                Activity
              </h2>
              <div className="grid grid-cols-3 gap-4 text-center">
                <div>
                  <p className="text-2xl font-bold text-slate-900 dark:text-slate-100">{stats.interested}</p>
                  <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">Interested</p>
                </div>
                <div>
                  <p className="text-2xl font-bold text-slate-900 dark:text-slate-100">{stats.not_interested}</p>
                  <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">Skipped</p>
                </div>
                <div>
                  <p className="text-2xl font-bold text-slate-900 dark:text-slate-100">{stats.total_rated}</p>
                  <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">Total rated</p>
                </div>
              </div>
            </CardBody>
          </Card>
        )}

        {/* Account card */}
        {isSupabaseConfigured && session && (
          <Card>
            <CardBody>
              <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-4">
                Account
              </h2>
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
                    {session.user.email}
                  </p>
                  <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">Signed in</p>
                </div>
                <Button variant="outline" size="sm" onClick={handleSignOut} className="shrink-0">
                  <LogOut className="size-4" />
                  Sign out
                </Button>
              </div>
            </CardBody>
          </Card>
        )}

      </div>
    </Layout>
  )
}

export default function ProfilePage() {
  return (
    <AuthGate>
      {(session) => <ProfilePageContent session={session} />}
    </AuthGate>
  )
}
