'use client'

import { ChevronDown, Repeat } from 'lucide-react'
import type { SimilarJob } from '@/lib/types'
import { repostLabel, repostTone } from '@/lib/repost'

interface Props {
  job: SimilarJob
  expanded: boolean
  onToggle: () => void
}

/** Chip-row button: "Posted N times since Mon YYYY" / "Same ad under N company names". Hidden for single postings. */
export function RepostBadge({ job, expanded, onToggle }: Props) {
  const tone = repostTone(job)
  if (tone === 'none') return null
  const cls =
    tone === 'amber'
      ? 'bg-amber-50 text-amber-800 border-amber-200 hover:bg-amber-100 dark:bg-amber-900/30 dark:text-amber-300 dark:border-amber-800'
      : 'bg-slate-100 text-slate-600 border-slate-200 hover:bg-slate-200 dark:bg-slate-700 dark:text-slate-300 dark:border-slate-600'
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={expanded}
      className={`flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full border transition-colors ${cls}`}
    >
      <Repeat className="w-3 h-3" />
      {repostLabel(job)}
      <ChevronDown className={`w-3 h-3 transition-transform ${expanded ? 'rotate-180' : ''}`} />
    </button>
  )
}
