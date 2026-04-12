'use client'

import { useEffect } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Menu, X, Briefcase, BarChart2, HelpCircle, Bookmark, Home, Scale, User } from 'lucide-react'
import { cn } from '@/lib/utils'

const navLinks = [
  { href: '/', label: 'Home', icon: Home },
  { href: '/matches', label: 'Matches', icon: Briefcase },
  { href: '/saved', label: 'Saved', icon: Bookmark },
  { href: '/dashboard', label: 'Dashboard', icon: BarChart2 },
  { href: '/lowball', label: 'Lowball', icon: Scale },
  { href: '/how-it-works', label: 'How it works', icon: HelpCircle },
  { href: '/profile', label: 'Profile', icon: User },
]

export interface MobileNavProps {
  open: boolean
  onToggle: () => void
  userSlot?: React.ReactNode
}

export default function MobileNav({ open, onToggle, userSlot }: MobileNavProps) {
  const pathname = usePathname()

  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [open])

  useEffect(() => {
    if (open) onToggle()
  // eslint-disable-next-line react-hooks/exhaustive-deps -- close menu on route change only
  }, [pathname])

  return (
    <>
      <button
        type="button"
        onClick={onToggle}
        className="lg:hidden p-2 -m-2 rounded-lg text-slate-600 hover:bg-slate-100 hover:text-slate-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-2 transition-colors"
        aria-label={open ? 'Close menu' : 'Open menu'}
        aria-expanded={open}
        aria-controls="mobile-nav-panel"
      >
        {open ? <X className="size-6" aria-hidden /> : <Menu className="size-6" aria-hidden />}
      </button>

      <div
        id="mobile-nav-panel"
        role="dialog"
        aria-modal="true"
        aria-label="Mobile navigation"
        className={cn(
          'fixed inset-0 z-50 lg:hidden',
          'transition-opacity duration-300 ease-out',
          open ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
        )}
      >
        <div
          className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm"
          onClick={onToggle}
          aria-hidden
        />

        <div
          className={cn(
            'absolute top-0 left-0 w-72 max-w-[85vw] h-full bg-white shadow-lg',
            'flex flex-col',
            'transition-transform duration-300 ease-out',
            open ? 'translate-x-0' : '-translate-x-full'
          )}
        >
          <div className="flex items-center justify-between p-4 border-b border-slate-200">
            <Link
              href="/"
              onClick={onToggle}
              className="text-lg font-semibold text-slate-900 hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-2 rounded-lg transition-colors"
            >
              MCF
            </Link>
            <button
              type="button"
              onClick={onToggle}
              className="p-2 -m-2 rounded-lg text-slate-600 hover:bg-slate-100 hover:text-slate-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-2 transition-colors"
              aria-label="Close menu"
            >
              <X className="size-6" aria-hidden />
            </button>
          </div>

          <nav className="flex-1 p-4 space-y-1 overflow-y-auto" aria-label="Mobile navigation">
            {navLinks.map(({ href, label, icon: Icon }) => {
              const isActive = pathname === href
              return (
                <Link
                  key={href}
                  href={href}
                  onClick={onToggle}
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
      </div>

      <nav
        className="lg:hidden fixed bottom-0 left-0 right-0 z-40 bg-white border-t border-slate-200"
        aria-label="Bottom navigation"
      >
        <div className="flex items-center justify-around h-16 px-2">
          {navLinks.map(({ href, label, icon: Icon }) => {
            const isActive = pathname === href
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  'flex flex-col items-center justify-center gap-1 min-w-0 flex-1 py-2 px-2 rounded-lg',
                  'text-xs font-medium transition-colors',
                  'hover:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-2',
                  isActive
                    ? 'text-slate-900'
                    : 'text-slate-500 hover:text-slate-700'
                )}
                aria-current={isActive ? 'page' : undefined}
              >
                <Icon className="size-5 shrink-0" aria-hidden />
                <span className="truncate">{label}</span>
              </Link>
            )
          })}
        </div>
      </nav>
    </>
  )
}
