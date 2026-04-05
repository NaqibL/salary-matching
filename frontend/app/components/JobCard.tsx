'use client'

import * as React from 'react'
import Link from 'next/link'
import { Building2, MapPin, ExternalLink } from 'lucide-react'
import type { Match } from '@/lib/types'
import { prefetchJobDetail } from '@/lib/job-prefetch'

// ─── Helpers ──────────────────────────────────────────────────────────────────

export function getDaysAgo(dateStr?: string): number | null {
  if (!dateStr) return null
  const ms = Date.now() - new Date(dateStr).getTime()
  return Math.max(0, Math.floor(ms / (1000 * 60 * 60 * 24)))
}

function RecencyBadge({ daysAgo }: { daysAgo: number | null }) {
  if (daysAgo === null) return null
  const label =
    daysAgo === 0 ? 'Today' : daysAgo === 1 ? '1 day ago' : `${daysAgo} days ago`
  const cls =
    daysAgo <= 7
      ? 'bg-emerald-100 text-emerald-700'
      : daysAgo <= 30
        ? 'bg-amber-100 text-amber-700'
        : 'bg-slate-100 text-slate-600'
  return (
    <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${cls}`}>{label}</span>
  )
}

// ─── Match card ───────────────────────────────────────────────────────────────

interface MatchCardProps {
  match: Match
  onInteraction?: (uuid: string, type: string) => void
  loading?: boolean
  mode: 'resume' | 'taste' | 'saved'
}

function ScoreBadge({ score }: { score: number }) {
  const pct = (score * 100).toFixed(0)
  const cls =
    score >= 0.75
      ? 'bg-emerald-500/10 text-emerald-700 border-emerald-200'
      : score >= 0.55
        ? 'bg-amber-500/10 text-amber-700 border-amber-200'
        : 'bg-slate-100 text-slate-600 border-slate-200'
  return (
    <div className={`shrink-0 px-3 py-1.5 rounded-full border text-sm font-semibold tabular-nums ${cls}`}>
      {pct}% match
    </div>
  )
}

export const MatchCard = React.memo(function MatchCard({ match, onInteraction, loading, mode }: MatchCardProps) {
  const daysAgo = getDaysAgo(match.last_seen_at)
  const handleMouseEnter = React.useCallback(() => {
    prefetchJobDetail(match.job_uuid)
  }, [match.job_uuid])

  return (
    <div
      className={`rounded-xl border shadow-sm overflow-hidden transition-all
        bg-white border-slate-200 dark:bg-slate-800 dark:border-slate-700
        ${loading ? 'opacity-40 pointer-events-none' : 'hover:shadow-md'}
        ${
          match.similarity_score >= 0.75
            ? 'ring-1 ring-emerald-200/50 dark:ring-emerald-800/50'
            : match.similarity_score >= 0.55
              ? 'ring-1 ring-amber-200/50 dark:ring-amber-800/50'
              : ''
        }`}
      onMouseEnter={handleMouseEnter}
    >
      <div className="p-6">
        <div className="flex items-start justify-between gap-4 mb-4">
          <div className="flex-1 min-w-0">
            <Link
              href={`/job/${match.job_uuid}`}
              prefetch={true}
              className="text-xl font-semibold text-slate-900 hover:text-indigo-600 transition-colors line-clamp-2 dark:text-slate-100 dark:hover:text-indigo-400 block"
            >
              {match.title}
            </Link>

            <div className="flex flex-wrap items-center gap-2 mt-2 text-slate-500 text-sm dark:text-slate-400">
              {match.company_name && (
                <span className="flex items-center gap-1.5">
                  <Building2 size={14} className="shrink-0" />
                  {match.company_name}
                </span>
              )}
              {match.location && (
                <span className="flex items-center gap-1.5">
                  <MapPin size={14} className="shrink-0" />
                  {match.location}
                </span>
              )}
              <RecencyBadge daysAgo={daysAgo} />
              {match.role_name && (
                <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-indigo-50 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300">
                  {match.role_name}
                </span>
              )}
              {match.predicted_tier && (
                <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300">
                  {match.predicted_tier.replace('T1_', '').replace('T2_', '').replace('T3_', '').replace('T4_', '')}
                </span>
              )}
            </div>
          </div>
          <ScoreBadge score={match.similarity_score} />
        </div>

        {/* Score breakdown (resume mode) */}
        {mode === 'resume' &&
          match.semantic_score !== undefined &&
          match.skills_overlap_score !== undefined && (
            <div className="flex gap-3 text-xs text-slate-400 mb-3">
              <span>Semantic: {(match.semantic_score * 100).toFixed(1)}%</span>
              <span>Skills: {(match.skills_overlap_score * 100).toFixed(1)}%</span>
            </div>
          )}

        {/* Matched skills */}
        {match.matched_skills && match.matched_skills.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-3">
            {match.matched_skills.slice(0, 6).map((s) => (
              <span
                key={s}
                className="px-2 py-0.5 bg-emerald-50 text-emerald-700 text-xs font-medium rounded-md"
              >
                {s}
              </span>
            ))}
            {match.matched_skills.length > 6 && (
              <span className="text-xs text-slate-400">+{match.matched_skills.length - 6}</span>
            )}
          </div>
        )}

        {/* Taste / saved mode skills */}
        {(mode === 'taste' || mode === 'saved') && match.job_skills && match.job_skills.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-3">
            {match.job_skills.slice(0, 6).map((s) => (
              <span
                key={s}
                className="px-2 py-0.5 bg-violet-50 text-violet-700 text-xs font-medium rounded-md"
              >
                {s}
              </span>
            ))}
          </div>
        )}

        {match.job_url && (
          <a
            href={match.job_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-sm font-medium text-indigo-600 hover:text-indigo-700 transition-colors dark:text-indigo-400 dark:hover:text-indigo-300"
          >
            View job posting
            <ExternalLink size={14} />
          </a>
        )}
      </div>

      {mode === 'saved' ? (
        onInteraction && (
          <div className="border-t border-slate-100 dark:border-slate-700">
            <button
              onClick={() => onInteraction(match.job_uuid, 'not_interested')}
              className="w-full flex items-center justify-center gap-2 py-3 text-sm font-medium transition-colors
                bg-slate-100 text-slate-700 hover:bg-rose-50 hover:text-rose-600 dark:bg-slate-700 dark:text-slate-300 dark:hover:bg-rose-900/30 dark:hover:text-rose-400"
            >
              <span className="text-base leading-none">✕</span>
              Remove from saved
            </button>
          </div>
        )
      ) : (
        onInteraction && (
          <div className="border-t border-slate-100 flex dark:border-slate-700">
            <button
              onClick={() => onInteraction(match.job_uuid, 'not_interested')}
              className="flex-1 flex items-center justify-center gap-2 py-3 text-sm font-medium transition-colors
                bg-slate-100 text-slate-700 hover:bg-rose-50 hover:text-rose-600 dark:bg-slate-700 dark:text-slate-300 dark:hover:bg-rose-900/30 dark:hover:text-rose-400"
            >
              <span className="text-base leading-none">✕</span>
              Not Interested
            </button>
            <button
              onClick={() => onInteraction(match.job_uuid, 'interested')}
              className="flex-1 flex items-center justify-center gap-2 py-3 text-sm font-medium
                bg-emerald-600 text-white hover:bg-emerald-700 transition-colors"
            >
              <span className="text-base leading-none">✓</span>
              Interested
            </button>
          </div>
        )
      )}
    </div>
  )
})
