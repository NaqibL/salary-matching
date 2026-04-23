'use client'

import { useRef, useState, useEffect } from 'react'
import { ChevronDown, Search } from 'lucide-react'

interface Props {
  options: Array<{ id: number; name: string }>
  selected: number[]
  onChange: (ids: number[]) => void
}

export function RoleClusterSelect({ options, selected, onChange }: Props) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
        setSearch('')
      }
    }
    if (open) document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open])

  const filtered = options.filter((o) =>
    o.name.toLowerCase().includes(search.toLowerCase())
  )

  // Selected items float to top within the filtered list
  const sorted = [
    ...filtered.filter((o) => selected.includes(o.id)),
    ...filtered.filter((o) => !selected.includes(o.id)),
  ]

  const toggle = (id: number) => {
    onChange(selected.includes(id) ? selected.filter((s) => s !== id) : [...selected, id])
  }

  const triggerLabel =
    selected.length === 0
      ? 'All Categories'
      : `${selected.length} selected`

  return (
    <div ref={containerRef} className="relative">
      <label className="mb-2 flex items-center justify-between text-sm font-medium text-slate-700 dark:text-slate-300">
        <span>Role Category</span>
        {selected.length > 0 && (
          <button
            type="button"
            onClick={() => onChange([])}
            className="text-xs font-normal text-violet-500 hover:text-violet-700"
          >
            Clear
          </button>
        )}
      </label>

      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 transition-colors hover:border-violet-400 focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
      >
        <span className={selected.length === 0 ? 'text-slate-400 dark:text-slate-500' : ''}>
          {triggerLabel}
        </span>
        <ChevronDown
          size={16}
          className={`ml-2 shrink-0 text-slate-400 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {open && (
        <div className="absolute left-0 right-0 top-full z-50 mt-1 rounded-lg border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-800">
          <div className="flex items-center gap-2 border-b border-slate-100 px-3 py-2 dark:border-slate-700">
            <Search size={14} className="shrink-0 text-slate-400" />
            <input
              autoFocus
              type="text"
              placeholder="Search roles..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="flex-1 bg-transparent text-sm text-slate-700 placeholder-slate-400 focus:outline-none dark:text-slate-200"
            />
          </div>

          <ul className="max-h-56 overflow-y-auto py-1">
            {sorted.length === 0 ? (
              <li className="px-4 py-3 text-sm text-slate-400">No categories match</li>
            ) : (
              sorted.map(({ id, name }) => {
                const isSelected = selected.includes(id)
                return (
                  <li key={id}>
                    <button
                      type="button"
                      onClick={() => toggle(id)}
                      className="flex w-full items-center gap-3 px-4 py-2 text-sm hover:bg-slate-50 dark:hover:bg-slate-700"
                    >
                      <span
                        className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                          isSelected
                            ? 'border-violet-600 bg-violet-600 text-white'
                            : 'border-slate-300 dark:border-slate-500'
                        }`}
                      >
                        {isSelected && (
                          <svg viewBox="0 0 10 8" className="h-2.5 w-2.5 fill-current">
                            <path d="M1 4l3 3 5-6" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                        )}
                      </span>
                      <span className={`text-left ${isSelected ? 'font-medium text-slate-800 dark:text-slate-100' : 'text-slate-600 dark:text-slate-300'}`}>
                        {name}
                      </span>
                    </button>
                  </li>
                )
              })
            )}
          </ul>
        </div>
      )}
    </div>
  )
}
