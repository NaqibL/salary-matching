'use client'

import { usePathname } from 'next/navigation'

interface PageTransitionProps {
  children: React.ReactNode
}

/**
 * Wraps page content with a fade-in animation on mount/route change.
 * Uses pathname as key to trigger animation on navigation.
 */
export default function PageTransition({ children }: PageTransitionProps) {
  const pathname = usePathname()

  return (
    <div key={pathname} className="animate-fade-in">
      {children}
    </div>
  )
}
