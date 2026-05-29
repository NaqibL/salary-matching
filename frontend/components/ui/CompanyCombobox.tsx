'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

interface CompanyComboboxProps {
  companies: string[]
  value: string
  onChange: (val: string) => void
  loading?: boolean
}

export default function CompanyCombobox({
  companies,
  value,
  onChange,
  loading = false,
}: CompanyComboboxProps) {
  const [open, setOpen] = useState(false)
  const [highlightedIndex, setHighlightedIndex] = useState(-1)
  const wrapperRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const filtered =
    value.trim().length > 0
      ? companies
          .filter((c) => c.toLowerCase().includes(value.toLowerCase()))
          .slice(0, 8)
      : []

  // Close on click outside
  useEffect(() => {
    function handleMouseDown(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleMouseDown)
    return () => document.removeEventListener('mousedown', handleMouseDown)
  }, [])

  // Reset highlight when filtered list changes
  useEffect(() => {
    setHighlightedIndex(-1)
  }, [value])

  const selectItem = useCallback(
    (item: string) => {
      onChange(item)
      setOpen(false)
    },
    [onChange]
  )

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (!open || filtered.length === 0) {
        if (e.key === 'ArrowDown' && filtered.length > 0) {
          setOpen(true)
          setHighlightedIndex(0)
          e.preventDefault()
        }
        return
      }

      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault()
          setHighlightedIndex((prev) =>
            prev < filtered.length - 1 ? prev + 1 : prev
          )
          break
        case 'ArrowUp':
          e.preventDefault()
          setHighlightedIndex((prev) => (prev > 0 ? prev - 1 : 0))
          break
        case 'Enter':
          e.preventDefault()
          if (highlightedIndex >= 0) {
            selectItem(filtered[highlightedIndex])
          } else if (filtered.length > 0) {
            selectItem(filtered[0])
          }
          break
        case 'Escape':
          e.preventDefault()
          setOpen(false)
          break
      }
    },
    [open, filtered, highlightedIndex, selectItem]
  )

  const handleFocus = useCallback(() => {
    if (filtered.length > 0) setOpen(true)
  }, [filtered.length])

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      onChange(e.target.value)
      setOpen(e.target.value.trim().length > 0)
    },
    [onChange]
  )

  const handleClear = useCallback(() => {
    onChange('')
    setOpen(false)
    inputRef.current?.focus()
  }, [onChange])

  return (
    <div ref={wrapperRef} className="relative">
      <div className="relative">
        <Input
          ref={inputRef}
          type="text"
          value={value}
          onChange={handleChange}
          onFocus={handleFocus}
          onKeyDown={handleKeyDown}
          disabled={loading}
          placeholder={loading ? 'Loading companies…' : 'e.g. Google'}
          autoComplete="off"
        />
        {value && !loading && (
          <button
            type="button"
            onClick={handleClear}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
            tabIndex={-1}
            aria-label="Clear company"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {open && filtered.length > 0 && (
        <ul
          role="listbox"
          className="absolute top-full left-0 right-0 mt-1 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-lg overflow-hidden z-50"
        >
          {filtered.map((company, index) => (
            <li
              key={company}
              role="option"
              aria-selected={index === highlightedIndex}
              onMouseDown={(e) => {
                // prevent blur from firing before click registers
                e.preventDefault()
                selectItem(company)
              }}
              onMouseEnter={() => setHighlightedIndex(index)}
              className={cn(
                'px-3 py-2 text-sm cursor-pointer',
                index === highlightedIndex
                  ? 'bg-indigo-50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300'
                  : 'text-slate-700 dark:text-slate-300 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 hover:text-indigo-700 dark:hover:text-indigo-300'
              )}
            >
              {company}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
