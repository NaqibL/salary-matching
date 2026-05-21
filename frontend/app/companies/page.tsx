'use client'

import { useState } from 'react'
import Link from 'next/link'
import useSWR from 'swr'
import { Building2, Search } from 'lucide-react'
import { companiesApi } from '@/lib/api'
import { Layout } from '@/app/components/layout'
import NavUserActions from '@/app/components/NavUserActions'
import { Card, CardBody, PageHeader } from '@/components/design'

export default function CompaniesPage() {
  const [query, setQuery] = useState('')

  const { data: companies = [], isLoading } = useSWR<string[]>(
    'companies-list',
    companiesApi.list,
    { revalidateOnFocus: false },
  )

  const filtered = query.trim()
    ? companies.filter((c) => c.toLowerCase().includes(query.toLowerCase()))
    : companies

  return (
    <Layout userSlot={<NavUserActions />}>
      <div className="space-y-6">
        <PageHeader
          title="Companies"
          subtitle={isLoading ? 'Loading…' : `${companies.length} companies with active listings`}
        />

        <div className="relative">
          <Search
            size={16}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"
          />
          <input
            type="text"
            placeholder="Search companies…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full pl-9 pr-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm text-slate-800 dark:text-slate-200 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        {isLoading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
            {Array.from({ length: 12 }).map((_, i) => (
              <div key={i} className="h-12 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <Card>
            <CardBody>
              <p className="text-sm text-slate-400 dark:text-slate-500 text-center py-4">
                No companies match &ldquo;{query}&rdquo;
              </p>
            </CardBody>
          </Card>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
            {filtered.map((name) => (
              <Link
                key={name}
                href={`/company/${encodeURIComponent(name)}`}
                className="flex items-center gap-3 px-4 py-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm font-medium text-slate-700 dark:text-slate-300 hover:border-indigo-300 dark:hover:border-indigo-600 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors"
              >
                <Building2 size={15} className="shrink-0 text-slate-400" />
                <span className="truncate">{name}</span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </Layout>
  )
}
