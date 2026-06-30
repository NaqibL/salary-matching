'use client'

import { useState } from 'react'
import Image from 'next/image'
import { Layout } from '../components/layout'
import NavUserActions from '../components/NavUserActions'
import { Card, CardBody } from '@/components/design'
import SupportOverlay from './SupportOverlay'

const KOFI_USERNAME = 'naqibl'

export default function SupportPage() {
  const [overlayOpen, setOverlayOpen] = useState(false)

  return (
    <Layout userSlot={<NavUserActions />}>

      {/* ── Title ─────────────────────────────────────────────────────────── */}
      <div className="text-center mb-10 mt-4">
        <div className="text-5xl mb-4">🧋</div>
        <h1 className="text-4xl font-bold tracking-tight text-slate-900 mb-3">
          Support the project
        </h1>
        <p className="text-lg text-slate-500">
          Make job hunting less stressful.
        </p>
      </div>

      {/* ── Two-column: story + costs ─────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8 max-w-3xl mx-auto">

        {/* Story */}
        <Card>
          <CardBody className="space-y-4">
            <p className="text-xl font-semibold text-slate-800">👋 Hey, I'm Luqman</p>
            <p className="text-base text-slate-600 leading-relaxed">
              I couldn't find a decent source for Singapore salaries, so I started collecting them myself.
            </p>
            <p className="text-base text-slate-600 leading-relaxed">
              The site costs me about $55/month to run, and I don't hide anything behind a paywall.
            </p>
            <p className="text-base text-slate-600 leading-relaxed">
              If this saved you time, helped you negotiate a better offer, or made your job search
              a little less confusing — maybe spon me one teh peng ❤️
            </p>
            <p className="text-base text-slate-500 italic">
              Either way, thanks for using the site.
            </p>
          </CardBody>
        </Card>

        {/* Costs */}
        <Card>
          <CardBody>
            <p className="text-xl font-semibold text-slate-800 mb-5">💸 My monthly costs</p>
            <ul className="space-y-1 text-base">
              <li className="flex justify-between py-3 border-b border-slate-100">
                <span className="text-slate-700">🖥️ API server</span>
                <span className="font-medium text-slate-500">~$15/mo</span>
              </li>
              <li className="flex justify-between py-3 border-b border-slate-100">
                <span className="text-slate-700">🗄️ Database</span>
                <span className="font-medium text-slate-500">~$25/mo</span>
              </li>
              <li className="flex justify-between py-3 border-b border-slate-100">
                <span className="text-slate-700">🤖 LLM job enrichment</span>
                <span className="font-medium text-slate-500">~$15/mo</span>
              </li>
              <li className="flex justify-between pt-3 font-semibold text-slate-800 text-lg">
                <span>Total</span>
                <span>~$55/mo</span>
              </li>
            </ul>
          </CardBody>
        </Card>

      </div>

      {/* ── Support Me button ─────────────────────────────────────────────── */}
      <div className="max-w-3xl mx-auto">
        <button
          onClick={() => setOverlayOpen(true)}
          className="w-full flex items-center justify-center gap-3 rounded-2xl bg-amber-400 hover:bg-amber-500 active:bg-amber-600 px-6 py-5 text-xl font-bold text-amber-950 shadow-md transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400 focus-visible:ring-offset-2"
        >
          <span>Support Me!</span>
          <span className="flex items-center gap-2 opacity-70">
            <Image src="/kofi_symbol.png" alt="Ko-fi" width={24} height={24} className="size-6 object-contain" />
            <Image src="/paynow_logo.png" alt="PayNow" width={24} height={24} className="size-6 object-contain" />
          </span>
        </button>
      </div>

      <SupportOverlay open={overlayOpen} onClose={() => setOverlayOpen(false)} />
    </Layout>
  )
}
