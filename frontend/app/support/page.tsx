'use client'

import { useState } from 'react'
import Image from 'next/image'
import { Mail, Linkedin, Github } from 'lucide-react'
import { Layout } from '../components/layout'
import NavUserActions from '../components/NavUserActions'
import { Card, CardBody } from '@/components/design'
import SupportOverlay from './SupportOverlay'

const KOFI_USERNAME = 'naqibl'

const CONTACT_EMAIL = 'lookmannaqib@gmail.com'
const CONTACT_LINKEDIN = 'https://www.linkedin.com/in/luqman-naqib/'
const CONTACT_GITHUB = 'https://github.com/NaqibL/'

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
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8 max-w-5xl mx-auto">

        {/* Story */}
        <Card>
          <CardBody className="space-y-4">
            <p className="text-xl font-semibold text-slate-800">Hey, I'm Luqman</p>
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
                <span className="text-slate-700">API server</span>
                <span className="font-medium text-slate-500">~$15/mo</span>
              </li>
              <li className="flex justify-between py-3 border-b border-slate-100">
                <span className="text-slate-700">Database</span>
                <span className="font-medium text-slate-500">~$25/mo</span>
              </li>
              <li className="flex justify-between py-3 border-b border-slate-100">
                <span className="text-slate-700">LLM job enrichment</span>
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
      <div className="flex justify-center">
        <button
          onClick={() => setOverlayOpen(true)}
          className="flex items-center justify-between gap-8 rounded-2xl bg-amber-400 hover:bg-amber-500 active:bg-amber-600 px-8 py-5 text-xl font-bold text-amber-950 shadow-md transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400 focus-visible:ring-offset-2 min-w-80"
        >
          <div className="w-16 flex items-center justify-center">
            <Image src="/kofi_symbol.png" alt="Ko-fi" width={36} height={36} className="size-9 object-contain" />
          </div>
          <span>Support Me!</span>
          <div className="w-24 flex items-center justify-center">
            <Image src="/paynow_logo.png" alt="PayNow" width={96} height={48} className="w-24 h-auto object-contain" />
          </div>
        </button>
      </div>

      {/* ── Contact Me ────────────────────────────────────────────────────── */}
      <div className="mt-6 flex items-center justify-center gap-4 text-slate-400">
        <a href={`mailto:${CONTACT_EMAIL}`} title={CONTACT_EMAIL} className="hover:text-slate-600 transition-colors">
          <Mail className="size-5" />
        </a>
        <a href={CONTACT_LINKEDIN} target="_blank" rel="noopener noreferrer" title="LinkedIn" className="hover:text-slate-600 transition-colors">
          <Linkedin className="size-5" />
        </a>
        <a href={CONTACT_GITHUB} target="_blank" rel="noopener noreferrer" title="GitHub" className="hover:text-slate-600 transition-colors">
          <Github className="size-5" />
        </a>
      </div>

      <SupportOverlay open={overlayOpen} onClose={() => setOverlayOpen(false)} />
    </Layout>
  )
}
