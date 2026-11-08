import Link from 'next/link'
import { ArrowUpRight, Lightbulb, Sparkles, Wrench } from 'lucide-react'
import { Layout } from '../components/layout'
import NavUserActions from '../components/NavUserActions'
import { Card, CardBody } from '@/components/design'
import { CHANGELOG_URL, FINDINGS, GLOSSARY, type FindingEntry } from '@/content/findings'

export const metadata = {
  title: 'Findings | Lowball',
  description:
    'What we have learned from tracking every Singapore job ad since March 2026, and what changed on the site as a result.',
}

const KIND: Record<FindingEntry['kind'], { label: string; icon: typeof Lightbulb; cls: string }> = {
  finding: { label: 'Finding', icon: Lightbulb, cls: 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-900/30 dark:text-amber-300 dark:border-amber-800' },
  fixed: { label: 'Fixed', icon: Wrench, cls: 'bg-emerald-50 text-emerald-800 border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-300 dark:border-emerald-800' },
  new: { label: 'New', icon: Sparkles, cls: 'bg-indigo-50 text-indigo-800 border-indigo-200 dark:bg-indigo-900/30 dark:text-indigo-300 dark:border-indigo-800' },
}

function Entry({ e }: { e: FindingEntry }) {
  const k = KIND[e.kind]
  const Icon = k.icon
  return (
    <Card id={e.slug} className="scroll-mt-24">
      <CardBody>
        <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400 mb-2">
          <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-medium ${k.cls}`}>
            <Icon className="size-3" aria-hidden />
            {k.label}
          </span>
          <time>{e.date}</time>
        </div>
        <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 leading-snug">{e.headline}</h2>
        <div className="mt-2 space-y-2 text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
          {e.body.map((p, i) => (
            <p key={i}>{p}</p>
          ))}
        </div>
        {e.figures && e.figures.length > 0 && (
          <dl className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-3">
            {e.figures.map((f) => (
              <div key={f.label} className="rounded-lg bg-slate-50 dark:bg-slate-800/60 px-3 py-2">
                <dd className="text-base font-semibold tabular-nums text-slate-900 dark:text-slate-100">{f.value}</dd>
                <dt className="text-xs text-slate-500 dark:text-slate-400">{f.label}</dt>
                <div className="text-[11px] text-slate-400 dark:text-slate-500 mt-0.5">as of {f.asOf}</div>
              </div>
            ))}
          </dl>
        )}
        {e.changelogAnchor && (
          <a
            href={`${CHANGELOG_URL}#${e.changelogAnchor}`}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-700 dark:text-indigo-400"
          >
            Technical notes
            <ArrowUpRight className="size-3" aria-hidden />
          </a>
        )}
      </CardBody>
    </Card>
  )
}

export default function FindingsPage() {
  return (
    <Layout userSlot={<NavUserActions />}>
      <div className="-mx-4 lg:-mx-8 px-4 lg:px-8 pt-10 pb-10 mb-8 bg-gradient-to-br from-slate-100/80 via-white to-slate-50 dark:from-slate-800/40 dark:via-slate-900 dark:to-slate-900 border-b border-slate-200/70 dark:border-slate-800">
        <div className="flex items-center gap-3 mb-3">
          <div className="flex size-11 items-center justify-center rounded-xl bg-slate-200 dark:bg-slate-700">
            <Lightbulb className="size-5 text-slate-600 dark:text-slate-300" />
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-100">Findings</h1>
        </div>
        <p className="text-base text-slate-500 dark:text-slate-400 leading-relaxed max-w-xl">
          What we have learned from tracking every Singapore job ad since March 2026, and what changed on the site
          because of it. Newest first. Numbers are snapshots with their date; the dashboard has today&apos;s counts.
        </p>
      </div>

      <div className="max-w-2xl space-y-4">
        {FINDINGS.map((e) => (
          <Entry key={e.slug} e={e} />
        ))}
      </div>

      <section className="max-w-2xl mt-10" id="how-the-numbers-are-made">
        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-3">
          How the numbers are made
        </h2>
        <Card>
          <CardBody>
            <dl className="divide-y divide-slate-100 dark:divide-slate-800">
              {GLOSSARY.map((g) => (
                <div key={g.term} className="py-2.5 first:pt-0 last:pb-0">
                  <dt className="text-sm font-medium text-slate-800 dark:text-slate-200">{g.term}</dt>
                  <dd className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed">{g.definition}</dd>
                </div>
              ))}
            </dl>
          </CardBody>
        </Card>
        <p className="mt-4 text-xs text-slate-400 dark:text-slate-500">
          The full technical record, with tickets and design notes, is the{' '}
          <a href={CHANGELOG_URL} target="_blank" rel="noopener noreferrer" className="underline hover:text-slate-600">
            changelog in the public repository
          </a>
          . Questions or corrections: use the contact links in the sidebar, or{' '}
          <Link href="/support" className="underline hover:text-slate-600">
            support the project
          </Link>
          .
        </p>
      </section>
    </Layout>
  )
}
