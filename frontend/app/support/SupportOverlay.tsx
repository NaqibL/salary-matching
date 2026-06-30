'use client'

import { useEffect } from 'react'
import Image from 'next/image'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'

const KOFI_USERNAME = 'naqibl'

interface SupportOverlayProps {
  open: boolean
  onClose: () => void
}

export default function SupportOverlay({ open, onClose }: SupportOverlayProps) {
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => { document.body.style.overflow = '' }
  }, [open])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    if (open) window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  return (
    <div
      className={cn(
        'fixed inset-0 z-50 flex items-center justify-center',
        'transition-opacity duration-300 ease-out',
        open ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
      )}
      style={{ backgroundColor: '#fdf8f0' }}
      role="dialog"
      aria-modal="true"
      aria-label="Support the project"
    >
      {/* Close button */}
      <button
        onClick={onClose}
        className="absolute top-5 right-5 p-2 rounded-full text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
        aria-label="Close"
      >
        <X className="size-6" />
      </button>

      {/* ── Three-column layout ─────────────────────────────────────────── */}
      <div className="w-full h-full flex items-center justify-center gap-8 px-8 md:px-16">

        {/* Left — Ko-fi */}
        <div className="flex flex-col items-center gap-4 flex-1 max-w-xs">
          {/* Placeholder for artist art */}
          <div className="w-40 h-40 rounded-2xl bg-amber-100 border-2 border-dashed border-amber-300 flex items-center justify-center text-amber-400 text-xs text-center px-4">
            Artist art<br />coming soon
          </div>
          <a
            href={`https://ko-fi.com/${KOFI_USERNAME}`}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-center gap-2 w-full rounded-xl bg-[#FF5E5B] hover:bg-[#e54e4b] active:bg-[#cc4542] px-5 py-3.5 text-sm font-semibold text-white shadow-sm transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#FF5E5B] focus-visible:ring-offset-2"
          >
            <Image src="/kofi_symbol.png" alt="" width={20} height={20} className="size-5 object-contain" aria-hidden />
            Buy me a teh peng
          </a>
        </div>

        {/* Centre — Teh peng hero */}
        <div className="flex flex-col items-center flex-1 max-w-xs">
          {/* Placeholder for teh peng illustration */}
          <div
            className="w-52 h-64 rounded-2xl bg-amber-50 border-2 border-dashed border-amber-200 flex items-center justify-center text-amber-300 text-xs text-center px-4"
            style={{ transform: 'rotate(-6deg)' }}
          >
            Teh peng illustration<br />coming soon
          </div>
        </div>

        {/* Right — PayNow */}
        <div className="flex flex-col items-center gap-2 flex-1 max-w-xs">
          {/* Placeholder for chibi */}
          <div className="w-20 h-20 rounded-full bg-slate-100 border-2 border-dashed border-slate-300 flex items-center justify-center text-slate-400 text-xs text-center">
            Chibi<br />TBD
          </div>
          {/* PayNow QR */}
          <div className="relative">
            <img
              src="/paynow_qr.png"
              alt="PayNow QR code"
              className="size-40 object-contain rounded-xl border border-slate-200 shadow-sm"
            />
          </div>
          <p className="text-xs font-medium text-slate-500">Scan to PayNow</p>
        </div>

      </div>
    </div>
  )
}
