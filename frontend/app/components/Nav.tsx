'use client'

import { useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Menu, X } from 'lucide-react'

interface NavProps {
  variant?: 'full' | 'auth'
  rightSlot?: React.ReactNode
}

const navLinks = [
  { href: '/', label: 'Resume Matching' },
  { href: '/dashboard', label: 'Dashboard' },
  { href: '/how-it-works', label: 'How it works' },
  { href: '/admin', label: 'Admin' },
]

export default function Nav({ variant = 'full', rightSlot }: NavProps) {
  const pathname = usePathname()
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <header className="bg-slate-900 sticky top-0 z-10">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 flex items-center justify-between h-14">
        <div className="flex items-center gap-4">
          <Link
            href="/"
            className="text-white font-semibold tracking-tight hover:text-slate-200 transition-colors"
          >
            MCF
          </Link>

          {variant === 'full' && (
            <>
              <nav className="hidden sm:flex items-center gap-8">
                {navLinks.map(({ href, label }) => (
                  <Link
                    key={href}
                    href={href}
                    className={`text-sm font-medium transition-colors ${
                      pathname === href
                        ? 'text-white border-b-2 border-indigo-400 pb-0.5'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    {label}
                  </Link>
                ))}
              </nav>

              <button
                type="button"
                onClick={() => setMobileOpen((o) => !o)}
                className="sm:hidden p-2 text-slate-400 hover:text-white"
                aria-label="Toggle menu"
              >
                {mobileOpen ? <X size={20} /> : <Menu size={20} />}
              </button>
            </>
          )}
        </div>

        <div className="flex items-center gap-3 ml-auto">{rightSlot}</div>
      </div>

      {variant === 'full' && mobileOpen && (
        <div className="sm:hidden border-t border-slate-700 bg-slate-900 px-4 py-3 flex flex-col gap-2">
          {navLinks.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              onClick={() => setMobileOpen(false)}
              className={`py-2 text-sm font-medium ${
                pathname === href ? 'text-white' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {label}
            </Link>
          ))}
        </div>
      )}
    </header>
  )
}
