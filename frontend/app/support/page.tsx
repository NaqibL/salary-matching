'use client'

import Image from 'next/image'
import { Instagram } from 'lucide-react'
import { Layout } from '../components/layout'
import NavUserActions from '../components/NavUserActions'
import { Card, CardBody } from '@/components/design'

const KOFI_USERNAME = 'naqibl'
const ARTIST_INSTAGRAM = 'https://www.instagram.com/fishflops_art'

export default function SupportPage() {
  return (
    <Layout userSlot={<NavUserActions />} fullWidth>

      {/* ── Vertically center on desktop, no leftover scroll ─────────────────── */}
      <div className="lg:min-h-[calc(100vh-4rem)] lg:flex lg:flex-col lg:justify-center lg:overflow-hidden">

      {/* ── Teh peng + Ko-fi, story + costs, PayNow QR ──────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-[auto_1fr_1.4fr] gap-8 items-center">

        {/* Left — teh peng image + Ko-fi button stacked */}
        <div className="flex flex-col items-center justify-center gap-6">
          <Image
            src="/teh_peng.png"
            alt="Iced teh peng"
            width={1969}
            height={3268}
            className="w-64 md:w-96 h-auto object-contain"
            style={{ transform: 'rotate(-30deg)' }}
          />
          <a
            href={`https://ko-fi.com/${KOFI_USERNAME}`}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-center gap-3 rounded-full bg-[#FF5E5B] hover:bg-[#e54e4b] active:bg-[#cc4542] px-10 py-4 text-lg font-bold text-white shadow-md transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#FF5E5B] focus-visible:ring-offset-2 w-full lg:translate-x-6 lg:-translate-y-5"
          >
            <Image src="/kofi_symbol.png" alt="" width={26} height={26} className="size-[26px] object-contain" aria-hidden />
            Buy me a teh peng
          </a>
        </div>

        {/* Middle — story + costs stacked, centered */}
        <div className="space-y-7 max-w-md mx-auto lg:translate-x-14">
          <Card className="p-7">
            <CardBody className="space-y-4 text-center">
              <p className="text-xl font-semibold text-slate-800 flex items-center justify-center gap-2">
                Ello, I'm Luqman
                <Image src="/cat_emoji.png" alt="" width={72} height={72} className="size-[72px] object-contain" aria-hidden />
              </p>
              <p className="text-base text-slate-600 leading-relaxed">
                This started as a passion project to help my friends and I navigate the job market coming out of uni.
              </p>
              <p className="text-base text-slate-600 leading-relaxed">
                Turns out it's helped a lot more people than I thought, and I hope to keep it running long term.
              </p>
              <p className="text-base text-slate-600 leading-relaxed">
                The site costs me about $55/month, and I'm not putting anything behind a paywall.
              </p>
              <p className="text-xs text-slate-500 italic whitespace-nowrap">
                If it helped you, even just a little, maybe spon me one teh peng ❤️
              </p>
            </CardBody>
          </Card>

          <Card className="p-7">
            <CardBody className="text-center">
              <p className="text-xl font-semibold text-slate-800 mb-5">💸 My monthly costs</p>
              <ul className="space-y-1.5 text-base max-w-xs mx-auto">
                <li className="flex justify-between py-2.5 border-b border-slate-100">
                  <span className="text-slate-700">API server</span>
                  <span className="font-medium text-slate-500">~$15/mo</span>
                </li>
                <li className="flex justify-between py-2.5 border-b border-slate-100">
                  <span className="text-slate-700">Database</span>
                  <span className="font-medium text-slate-500">~$25/mo</span>
                </li>
                <li className="flex justify-between py-2.5 border-b border-slate-100">
                  <span className="text-slate-700">Daily data processing</span>
                  <span className="font-medium text-slate-500">~$15/mo</span>
                </li>
                <li className="flex justify-between pt-2.5 font-semibold text-slate-800 text-lg">
                  <span>Total</span>
                  <span>~$55/mo</span>
                </li>
              </ul>
            </CardBody>
          </Card>
        </div>

        {/* Right — PayNow QR */}
        <div className="flex items-center justify-center lg:-mr-16 lg:translate-y-14">
          <Image
            src="/qr_with_thank_you.png"
            alt="Scan to PayNow — thank you"
            width={2683}
            height={2325}
            className="w-full max-w-2.5xl h-auto object-contain"
          />
        </div>

        {/* Artist credit — same grid, so it shares the exact column tracks as the text card above */}
        <a
          href={ARTIST_INSTAGRAM}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-center gap-1.5 text-sm text-slate-400 hover:text-slate-600 transition-colors mt-4 lg:mt-6 lg:col-start-2 lg:translate-x-14"
        >
          <Instagram className="size-4" aria-hidden />
          credits to the GOAT for the art
        </a>

      </div>

      </div>
    </Layout>
  )
}
