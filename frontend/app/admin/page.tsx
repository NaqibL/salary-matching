'use client'

import { AdminCachePanel } from './AdminCachePanel'
import AuthGate from '@/app/components/AuthGate'
import { PageHeader } from '@/components/design'
import Link from 'next/link'

export default function AdminPage() {
  return (
    <AuthGate>
      {(session) => (
        <div className="container mx-auto max-w-3xl space-y-6 px-4 py-8">
          <PageHeader
            title="Cache Admin"
            subtitle="View cache stats, clear keys, and force revalidation."
          />
          <div className="flex gap-2">
            <Link
              href="/dashboard"
              className="text-sm text-muted-foreground hover:text-foreground"
            >
              ← Dashboard
            </Link>
          </div>
          <AdminCachePanel />
        </div>
      )}
    </AuthGate>
  )
}
