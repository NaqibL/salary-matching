import { Layout } from '../components/layout'
import NavUserActions from '../components/NavUserActions'
import { Card, CardBody } from '@/components/design'

export const metadata = {
  title: 'Support the Project | Lowball',
  description: 'Help keep Lowball free and running. Buy me a teh peng.',
}

const KOFI_USERNAME = 'naqibl'

export default function SupportPage() {
  return (
    <Layout userSlot={<NavUserActions />}>

      {/* ── Page header ──────────────────────────────────────────────────── */}
      <div className="-mx-4 lg:-mx-8 px-4 lg:px-8 pt-10 pb-10 mb-8 bg-gradient-to-br from-amber-50/80 via-white to-slate-50 border-b border-slate-200/70">
        <div className="flex items-center gap-3 mb-3">
          <div className="flex size-11 items-center justify-center rounded-xl bg-amber-100 text-2xl">
            🧋
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-900">
            Support the project
          </h1>
        </div>
        <p className="text-base text-slate-500 leading-relaxed max-w-xl">
          I built this because I wanted to make job hunting in Singapore a little less stressful.
        </p>
      </div>

      <div className="max-w-2xl space-y-6">

        {/* ── Solo dev note ────────────────────────────────────────────────── */}
        <Card>
          <CardBody className="space-y-3">
            <p className="text-sm text-slate-700 leading-relaxed">
              I couldn&apos;t find a decent source for Singapore salaries, so I started collecting them myself.
            </p>
            <p className="text-sm text-slate-700 leading-relaxed">
              The site costs me about $55/month to run, and I don&apos;t hide anything behind a paywall.
            </p>
            <p className="text-sm text-slate-700 leading-relaxed">
              If this saved you some time, helped you negotiate a better offer, or simply made your job search
              a little less confusing, maybe spon me one teh peng ❤️
            </p>
            <p className="text-sm text-slate-700 leading-relaxed">
              Either way, thanks for using the site.
            </p>
          </CardBody>
        </Card>

        {/* ── Donation options ─────────────────────────────────────────────── */}
        <div>
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-3">
            Donate
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">

            {/* Ko-fi */}
            <Card className="flex flex-col">
              <CardBody className="flex flex-col flex-1 items-center justify-center gap-3 py-6">
                <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">Ko-fi</p>
                <a
                  href={`https://ko-fi.com/${KOFI_USERNAME}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center justify-center gap-2 w-full rounded-lg bg-[#FF5E5B] px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-[#e54e4b] hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-[#FF5E5B] focus-visible:ring-offset-2"
                >
                  🧋 Buy me a teh peng
                </a>
              </CardBody>
            </Card>

            {/* PayNow */}
            <Card className="flex flex-col">
              <CardBody className="flex flex-col flex-1 items-center justify-center gap-3 py-6">
                <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">PayNow</p>
                <img
                  src="/paynow_qr.png"
                  alt="PayNow QR code"
                  className="size-40 object-contain rounded-lg border border-slate-200"
                />
              </CardBody>
            </Card>

          </div>
        </div>

        {/* ── What it covers ───────────────────────────────────────────────── */}
        <Card>
          <CardBody>
            <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wider mb-3">
              What your support covers
            </h3>
            <ul className="space-y-2 text-sm text-slate-600">
              <li className="flex justify-between">
                <span>API server</span>
                <span className="text-slate-400">~$15/mo</span>
              </li>
              <li className="flex justify-between">
                <span>Database</span>
                <span className="text-slate-400">~$25/mo</span>
              </li>
              <li className="flex justify-between">
                <span>LLM job enrichment (daily)</span>
                <span className="text-slate-400">~$15/mo</span>
              </li>
              <li className="flex justify-between border-t border-slate-100 pt-2 font-medium text-slate-700">
                <span>Total</span>
                <span>~$55/mo</span>
              </li>
            </ul>
          </CardBody>
        </Card>

      </div>
    </Layout>
  )
}
