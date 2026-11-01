'use client'

import { useCallback } from 'react'
import { SlidersHorizontal, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  EMPTY_FILTERS,
  MIN_YEARS_OPTIONS,
  hasActiveFilters,
  toggleSeniority,
  type SeniorityOption,
  type SimilarRoleFilters,
} from '@/lib/similarRoleFilters'

interface SimilarRoleFilterBarProps {
  filters: SimilarRoleFilters
  onChange: (next: SimilarRoleFilters) => void
  seniorityOptions: SeniorityOption[]
  shownCount: number
  totalCount: number
}

const PILL_BASE =
  'inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium whitespace-nowrap transition-colors ' +
  'focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1 dark:focus-visible:ring-offset-slate-800'
const PILL_OFF =
  'border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
const PILL_ON =
  'border-indigo-600 bg-indigo-600 text-white hover:bg-indigo-700 dark:border-indigo-500 dark:bg-indigo-500 dark:hover:bg-indigo-400'

export default function SimilarRoleFilterBar({
  filters,
  onChange,
  seniorityOptions,
  shownCount,
  totalCount,
}: SimilarRoleFilterBarProps) {
  const active = hasActiveFilters(filters)

  const handleMinYears = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      const v = e.target.value
      onChange({ ...filters, minYears: v === '' ? null : Number(v) })
    },
    [filters, onChange],
  )

  return (
    <div
      role="group"
      aria-label="Filter similar roles"
      className="mb-3 rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800"
    >
      {/* Row 1: toggles + experience select + count/clear */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <div className="flex flex-nowrap items-center gap-1.5">
          <SlidersHorizontal className="mr-0.5 size-4 shrink-0 text-slate-400 dark:text-slate-500" />
          <button
            type="button"
            aria-pressed={filters.activeOnly}
            onClick={() => onChange({ ...filters, activeOnly: !filters.activeOnly })}
            className={cn(PILL_BASE, filters.activeOnly ? PILL_ON : PILL_OFF)}
          >
            Active only
          </button>
          <button
            type="button"
            aria-pressed={filters.hasSalary}
            onClick={() => onChange({ ...filters, hasSalary: !filters.hasSalary })}
            className={cn(PILL_BASE, filters.hasSalary ? PILL_ON : PILL_OFF)}
          >
            Has salary
          </button>
          <select
            aria-label="Minimum years of experience"
            value={filters.minYears ?? ''}
            onChange={handleMinYears}
            className={cn(
              'h-[26px] rounded-full border py-0 pl-2.5 pr-7 text-xs font-medium',
              'focus:outline-none focus:ring-2 focus:ring-indigo-500',
              filters.minYears != null ? PILL_ON : PILL_OFF,
            )}
          >
            {MIN_YEARS_OPTIONS.map((opt) => (
              <option key={opt.label} value={opt.value ?? ''}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <div className="ml-auto flex items-center gap-2 text-xs text-slate-400 dark:text-slate-500">
          <span className="tabular-nums">
            {shownCount} of {totalCount} shown
          </span>
          {active && (
            <button
              type="button"
              onClick={() => onChange(EMPTY_FILTERS)}
              className="inline-flex items-center gap-0.5 font-medium text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300 transition-colors"
            >
              <X className="size-3" />
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Row 2: seniority chips (only values present in the current results) */}
      {seniorityOptions.length > 0 && (
        <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
          <span className="mr-0.5 text-xs text-slate-400 dark:text-slate-500">Seniority</span>
          {seniorityOptions.map((opt) => {
            const selected = filters.seniority.includes(opt.value)
            return (
              <button
                key={opt.value}
                type="button"
                aria-pressed={selected}
                onClick={() => onChange(toggleSeniority(filters, opt.value))}
                className={cn(PILL_BASE, selected ? PILL_ON : PILL_OFF)}
              >
                {opt.label}
                <span
                  className={cn(
                    'ml-1 tabular-nums',
                    selected ? 'text-indigo-100' : 'text-slate-400 dark:text-slate-500',
                  )}
                >
                  {opt.count}
                </span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
