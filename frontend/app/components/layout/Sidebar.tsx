'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Briefcase, BarChart2, HelpCircle, Bookmark, Scale, Home } from 'lucide-react'
import { cn } from '@/lib/utils'

const navLinks = [
  { href: '/', label: 'Home', icon: Home },
  { href: '/matches', label: 'Resume Matching', icon: Briefcase },
  { href: '/saved', label: 'Saved Jobs', icon: Bookmark },
  { href: '/dashboard', label: 'Dashboard', icon: BarChart2 },
  { href: '/lowball', label: 'Lowball Checker', icon: Scale },
  { href: '/how-it-works', label: 'How it works', icon: HelpCircle },
]

export interface SidebarProps {
  userSlot?: React.ReactNode
}

export default function Sidebar({ userSlot }: SidebarProps) {
  const pathname = usePathname()

  return (
    <aside
      className="hidden lg:flex lg:w-60 lg:shrink-0 lg:flex-col lg:sticky lg:top-0 lg:h-screen lg:border-r lg:border-slate-200 lg:bg-white"
      aria-label="Main navigation"
    >
      <div className="flex flex-col h-full">
        <div className="p-6">
          <Link
            href="/"
            className="flex items-center gap-2 text-lg font-semibold text-slate-900 hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-2 rounded-lg transition-colors"
            aria-label="MCF Job Matcher home"
          >
            <span className="text-xl leading-tight">MCF</span>
          </Link>
        </div>

        <nav className="flex-1 px-4 space-y-1" aria-label="Primary navigation">
          {navLinks.map(({ href, label, icon: Icon }) => {
            const isActive = pathname === href
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  'flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-colors',
                  'hover:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-2',
                  isActive
                    ? 'bg-slate-100 text-slate-900'
                    : 'text-slate-600 hover:text-slate-900'
                )}
                aria-current={isActive ? 'page' : undefined}
              >
                <Icon className="size-4 shrink-0" aria-hidden />
                {label}
              </Link>
            )
          })}
        </nav>

        {userSlot && (
          <div className="p-4 border-t border-slate-200">
            {userSlot}
          </div>
        )}
      </div>
    </aside>
  )
}
