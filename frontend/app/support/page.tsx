'use client'

import { useState } from 'react'
import Image from 'next/image'
import { Layout } from '../components/layout'
import NavUserActions from '../components/NavUserActions'
import SupportOverlay from './SupportOverlay'

export default function SupportPage() {
  const [overlayOpen, setOverlayOpen] = useState(false)

  return (
    <Layout userSlot={<NavUserActions />}>

      {/* ── Title ─────────────────────────────────────────────────────────── */}
      <div className="text-center mb-10 mt-4">
        <h1 className="text-4xl font-bold tracking-tight text-slate-900 mb-2">
          Support the project
        </h1>
        <p className="text-base text-slate-500">
          Make job hunting less stressful.
        </p>
      </div>

      {/* ── Two-column: story + costs ─────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-10 max-w-3xl mx-auto">

        {/* Story */}
        <div className="space-y-3">
          <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
            Why this exists
          </h2>
          <p className="text-sm text-slate-700 leading-relaxed">
            I couldn&apos;t find a decent source for Singapore salaries, so I started collecting them myself.
          </p>
          <p className="text-sm text-slate-700 leading-relaxed">
            The site costs me about $55/month to run, and I don&apos;t hide anything behind a paywall.
          </p>
          <p className="text-sm text-slate-700 leading-relaxed">
            If this saved you some time, helped you negotiate a better offer, or simply made your job
            search a little less confusing — maybe spon me one teh peng ❤️
          </p>
          <p className="text-sm text-slate-700 leading-relaxed">
            Either way, thanks for using the site.
          </p>
        </div>

        {/* Costs */}
        <div className="space-y-3">
          <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
            My monthly costs
          </h2>
          <ul className="space-y-2 text-sm text-slate-600">
            <li className="flex justify-between py-2 border-b border-slate-100">
              <span>API server</span>
              <span className="text-slate-400">~$15/mo</span>
            </li>
            <li className="flex justify-between py-2 border-b border-slate-100">
              <span>Database</span>
              <span className="text-slate-400">~$25/mo</span>
            </li>
            <li className="flex justify-between py-2 border-b border-slate-100">
              <span>LLM job enrichment (daily)</span>
              <span className="text-slate-400">~$15/mo</span>
            </li>
            <li className="flex justify-between py-2 font-semibold text-slate-800">
              <span>Total</span>
              <span>~$55/mo</span>
            </li>
          </ul>
        </div>
      </div>

      {/* ── Support Me button ─────────────────────────────────────────────── */}
      <div className="max-w-3xl mx-auto">
        <button
          onClick={() => setOverlayOpen(true)}
          className="w-full flex items-center justify-center gap-3 rounded-xl bg-amber-400 hover:bg-amber-500 active:bg-amber-600 px-6 py-4 text-base font-semibold text-amber-950 shadow-sm transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400 focus-visible:ring-offset-2"
        >
          <span>Support Me!</span>
          <span className="flex items-center gap-2 opacity-80">
            <Image src="/kofi_symbol.png" alt="Ko-fi" width={20} height={20} className="size-5 object-contain" />
            <Image src="/paynow_logo.png" alt="PayNow" width={20} height={20} className="size-5 object-contain" />
          </span>
        </button>
      </div>

      <SupportOverlay open={overlayOpen} onClose={() => setOverlayOpen(false)} />
    </Layout>
  )
}
