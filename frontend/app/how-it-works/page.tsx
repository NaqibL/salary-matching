import Link from 'next/link'
import { BookOpen, ArrowRight } from 'lucide-react'
import { Layout } from '../components/layout'
import NavUserActions from '../components/NavUserActions'
import { Card, CardBody } from '@/components/design'

export const metadata = {
  title: 'How It Works | MCF Job Matcher',
  description: 'Learn how MCF Job Matcher helps you find jobs that fit your resume and preferences.',
}

const steps = [
  {
    num: 1,
    title: 'Upload your resume',
    body: 'Start by uploading your resume (PDF or DOCX). The system extracts your experience, skills, and background to build a profile used to score jobs against your qualifications.',
  },
  {
    num: 2,
    title: 'Rate jobs in the Resume tab',
    body: "You'll see jobs ranked by how well they match your resume. For each job, click Interested or Not Interested. This is the most important step — your ratings train a Taste Profile, a personalised model of what you actually want. Jobs you mark Interested teach it what to look for; Not Interested teaches it what to filter out.",
    callout: {
      heading: 'Why does rating matter?',
      body: 'Resume matching is based on keyword and semantic overlap. Taste matching is based on your demonstrated preferences. The more you rate, the more accurate and personalised the Taste tab becomes.',
    },
  },
  {
    num: 3,
    title: 'Update your Taste Profile',
    body: "After rating at least 3 jobs as Interested, click Update Taste Profile. This builds (or refreshes) your taste model from your ratings. Run it again whenever you've added new ratings to keep recommendations up to date.",
  },
  {
    num: 4,
    title: 'Use the Taste tab for personalised matches',
    body: "Once your taste profile is built, switch to the Taste tab. Here you'll get jobs ranked by demonstrated preference — not just resume overlap — and the quality improves as you continue rating.",
  },
]

export default function HowItWorksPage() {
  return (
    <Layout userSlot={<NavUserActions />}>

      {/* ── Page header ──────────────────────────────────────────────────── */}
      <div className="-mx-4 lg:-mx-8 px-4 lg:px-8 pt-10 pb-10 mb-8 bg-gradient-to-br from-slate-100/80 via-white to-slate-50 dark:from-slate-800/40 dark:via-slate-900 dark:to-slate-900 border-b border-slate-200/70 dark:border-slate-800">
        <div className="flex items-center gap-3 mb-3">
          <div className="flex size-11 items-center justify-center rounded-xl bg-slate-200 dark:bg-slate-700">
            <BookOpen className="size-5 text-slate-600 dark:text-slate-300" />
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
            How it works
          </h1>
        </div>
        <p className="text-base text-slate-500 dark:text-slate-400 leading-relaxed max-w-xl">
          A guide to getting the most out of resume matching and personalised job recommendations.
        </p>
      </div>

      {/* ── Steps ────────────────────────────────────────────────────────── */}
      <div className="max-w-2xl space-y-4">
        {steps.map(({ num, title, body, callout }) => (
          <Card key={num}>
            <CardBody className="flex gap-5">
              <div className="shrink-0 flex size-9 items-center justify-center rounded-full bg-indigo-600 text-white text-sm font-bold">
                {num}
              </div>
              <div className="min-w-0">
                <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100 mb-1.5">
                  {title}
                </h2>
                <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed">{body}</p>
                {callout && (
                  <div className="mt-4 rounded-lg bg-indigo-50 dark:bg-indigo-950/40 border border-indigo-100 dark:border-indigo-900 p-4">
                    <p className="text-sm font-semibold text-indigo-900 dark:text-indigo-200 mb-1">
                      {callout.heading}
                    </p>
                    <p className="text-sm text-indigo-800 dark:text-indigo-300 leading-relaxed">
                      {callout.body}
                    </p>
                  </div>
                )}
              </div>
            </CardBody>
          </Card>
        ))}

        {/* ── Summary ──────────────────────────────────────────────────────── */}
        <Card className="border-t-4 border-t-slate-400 dark:border-t-slate-500">
          <CardBody>
            <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-4">
              Summary
            </h3>
            <ul className="space-y-2.5 text-sm text-slate-600 dark:text-slate-400">
              <li>
                <strong className="text-slate-800 dark:text-slate-200">Resume tab</strong> — rate
                jobs to train your taste profile. New users start here.
              </li>
              <li>
                <strong className="text-slate-800 dark:text-slate-200">Taste tab</strong> — get
                personalised recommendations once you&apos;ve rated enough jobs.
              </li>
              <li>
                <strong className="text-slate-800 dark:text-slate-200">Interested / Not interested</strong> — every
                click helps narrow and improve future recommendations.
              </li>
            </ul>
          </CardBody>
        </Card>

        <div className="pt-2">
          <Link
            href="/matches"
            className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-6 py-3 text-sm font-semibold text-white shadow-sm transition-all hover:bg-indigo-700 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2"
          >
            Get started <ArrowRight className="size-4" />
          </Link>
        </div>
      </div>

    </Layout>
  )
}
