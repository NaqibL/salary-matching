'use client'

import { useState, useCallback } from 'react'
import Link from 'next/link'
import Sidebar from './Sidebar'
import MobileNav from './MobileNav'

export interface LayoutProps {
  children: React.ReactNode
  userSlot?: React.ReactNode
}

export default function Layout({ children, userSlot }: LayoutProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const onToggle = useCallback(() => setMobileMenuOpen((o) => !o), [])

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col lg:flex-row">
      <Sidebar userSlot={userSlot} />

      <header className="lg:hidden sticky top-0 z-30 flex items-center justify-between h-14 px-4 bg-white border-b border-slate-200 shrink-0">
        <Link
          href="/"
          className="text-lg font-semibold text-slate-900 hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-2 rounded-lg transition-colors"
          aria-label="MCF Job Matcher home"
        >
          MCF
        </Link>
        <MobileNav
          open={mobileMenuOpen}
          onToggle={onToggle}
          userSlot={userSlot}
        />
      </header>

      <main className="flex-1 min-w-0 lg:min-h-screen">
        <div className="w-full max-w-[1280px] mx-auto px-4 lg:px-8 py-6 lg:py-8 pb-24 lg:pb-8">
          {children}
        </div>
      </main>
    </div>
  )
}
