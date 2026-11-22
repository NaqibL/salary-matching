import Link from 'next/link'
import { Layout } from './components/layout'

export const metadata = { title: 'Page not found | Lowball' }

const linkCls = 'text-slate-900 underline decoration-slate-400 underline-offset-4 hover:decoration-slate-900'

export default function NotFound() {
  return (
    <Layout>
      <div className="max-w-3xl">
        <h1 className="text-2xl font-semibold text-slate-900 sm:text-3xl">Page not found</h1>
        <p className="mt-3 text-slate-900">There is nothing at this address.</p>
        <ul className="mt-4 space-y-2">
          <li>
            <Link href="/" className={linkCls}>
              Check a salary
            </Link>
          </li>
          <li>
            <Link href="/companies" className={linkCls}>
              Look up a company
            </Link>
          </li>
        </ul>
      </div>
    </Layout>
  )
}
