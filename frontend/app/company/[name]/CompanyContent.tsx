'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'
import useSWR from 'swr'
import { companiesApi } from '@/lib/api'
import type { CompanyJob, CompanyPayRow, CompanyProfile, CompanyStatsResponse } from '@/lib/types'
import { monthYear, payUnit } from '@/lib/repost'
import { familyLabel } from '@/lib/roleFamilies'
import { adPayText, count, industryText, money, payText, plural, postedText, spreadText } from '@/lib/companyFormat'
import { Layout } from '@/app/components/layout'
import NavUserActions from '@/app/components/NavUserActions'

/** Pay is shown once this many open ads state a salary. */
const MIN_ADS_FOR_PAY = 3
const ROLES_SHOWN = 20
const JOB_TYPES_SHOWN = 8
const PER = { '/mo': 'a month', '/day': 'a day', '/hr': 'an hour' } as const

const linkCls = 'text-slate-900 underline decoration-slate-400 underline-offset-4 hover:decoration-slate-900'
const h2Cls = 'text-lg font-semibold text-slate-900'

function Shell({ children, backHref = '/companies' }: { children: React.ReactNode; backHref?: string }) {
  return (
    <Layout userSlot={<NavUserActions />}>
      <div className="max-w-3xl">
        <Link href={backHref} className={`text-[15px] ${linkCls}`}>
          Back to companies
        </Link>
        {children}
      </div>
    </Layout>
  )
}

// ---------------------------------------------------------------------------
// Not found: offer the nearest names instead of a dead end
// ---------------------------------------------------------------------------

function NotFound({ name }: { name: string }) {
  const { data, isLoading } = useSWR<CompanyStatsResponse>(
    ['company-suggest', name],
    () => companiesApi.getStats({ q: name, agency: 'all', min_active: 1, limit: 5 }),
    { revalidateOnFocus: false },
  )
  const suggestions = data?.rows ?? []
  return (
    <Shell>
      <h1 className="mt-4 text-2xl font-semibold text-slate-900 sm:text-3xl">No company called “{name}”</h1>
      {isLoading ? (
        <p className="mt-3 text-slate-600">Looking for similar names…</p>
      ) : suggestions.length > 0 ? (
        <>
          <p className="mt-3 text-slate-900">Did you mean:</p>
          <ul className="mt-2 space-y-2">
            {suggestions.map((r) => (
              <li key={r.company_key}>
                <Link href={`/company/${encodeURIComponent(r.company)}`} className={linkCls}>
                  {r.company}
                </Link>
                <span className="ml-2 text-sm text-slate-600">{plural(r.active_count, 'open role', 'open roles')}</span>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="mt-3 text-slate-900">
          No company with open roles has a name like that. Company names here are the ones written on the job ads.
        </p>
      )}
    </Shell>
  )
}

// ---------------------------------------------------------------------------
// Open roles: one row per distinct ad title + pay, newest first
// ---------------------------------------------------------------------------

type RoleGroup = { job: CompanyJob; copies: number }

function groupRoles(jobs: CompanyJob[]): RoleGroup[] {
  const groups = new Map<string, RoleGroup>()
  for (const job of jobs) {
    const key = `${(job.title ?? '').trim().toLowerCase()}|${job.salary_min ?? ''}|${job.salary_max ?? ''}`
    const seen = groups.get(key)
    if (seen) seen.copies += 1
    else groups.set(key, { job, copies: 1 })
  }
  return Array.from(groups.values())
}

function RoleRow({ group }: { group: RoleGroup }) {
  const { job, copies } = group
  const kind = (job.employment_types ?? []).find((t) => !/^(full time|permanent)$/i.test(t))
  const details = [
    adPayText(job.salary_min, job.salary_max),
    job.min_years_experience != null && job.min_years_experience > 0
      ? `asks for ${job.min_years_experience}+ ${job.min_years_experience === 1 ? 'year' : 'years'}`
      : null,
    kind ?? null,
    postedText(job.first_seen_at) ? `posted ${postedText(job.first_seen_at)}` : null,
  ].filter(Boolean)
  const title = job.title ?? 'Untitled ad'
  return (
    <li className="border-b border-slate-200 py-3">
      {job.job_url ? (
        <a href={job.job_url} target="_blank" rel="noopener noreferrer" className={`font-medium break-words ${linkCls}`}>
          {title}
        </a>
      ) : (
        <span className="font-medium break-words text-slate-900">{title}</span>
      )}
      {copies > 1 && <span className="ml-2 text-sm text-slate-600">{copies} open ads</span>}
      <div className="mt-1 text-sm text-slate-700">{details.join(' · ')}</div>
    </li>
  )
}

// ---------------------------------------------------------------------------
// Pay by job type
// ---------------------------------------------------------------------------

function payCell(row: CompanyPayRow): { main: string; sub: string | null } | null {
  const main = payText(row.salary_p50)
  if (!main || row.salary_sample < MIN_ADS_FOR_PAY) return null
  const spread = spreadText(row.salary_p25, row.salary_p75)
  return { main, sub: spread ? `most ads ${spread}` : null }
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function CompanyContent({ companyName, initialFamily = '' }: { companyName: string; initialFamily?: string }) {
  const { data: profile, error, isLoading } = useSWR<CompanyProfile | null>(
    `company-profile-${companyName}`,
    () => companiesApi.getProfile(companyName),
    { revalidateOnFocus: false },
  )
  const [familyFilter, setFamilyFilter] = useState(initialFamily)
  const [showAll, setShowAll] = useState(false)
  const [allJobTypes, setAllJobTypes] = useState(false)
  const backHref = initialFamily ? `/companies?family=${encodeURIComponent(initialFamily)}` : '/companies'

  const jobs = profile?.active_jobs
  const roleGroups = useMemo(
    () => groupRoles((jobs ?? []).filter((j) => !familyFilter || j.role_family === familyFilter)),
    [jobs, familyFilter],
  )

  if (isLoading) {
    return (
      <Shell backHref={backHref}>
        <p className="mt-4 py-8 text-slate-600">Loading {companyName}…</p>
      </Shell>
    )
  }
  if (error) {
    return (
      <Shell backHref={backHref}>
        <h1 className="mt-4 text-2xl font-semibold text-slate-900 sm:text-3xl">{companyName}</h1>
        <p className="mt-3 text-slate-900">This company could not be loaded. Please try again in a minute.</p>
      </Shell>
    )
  }
  if (!profile) return <NotFound name={companyName} />

  const isAgency = !!profile.stats?.is_agency
  const industry = industryText(profile.stats?.ssic_description)
  const open = profile.active_count
  // `?? []`: a response cached from before this page shipped has no per-job-type rows
  const payRows = profile.pay_by_family ?? []
  const reposted = profile.top_reposted ?? []
  const listed = (profile.active_jobs ?? []).length

  const overallSpread = spreadText(profile.salary_p25, profile.salary_p75)
  const showOverallPay = !isAgency && profile.salary_p50 != null && profile.salary_p50 > 0 && profile.salary_sample_size >= MIN_ADS_FOR_PAY
  const per = PER[payUnit(profile.salary_p50 ?? 0)]

  // Job types with enough ads to state a pay figure go in the table; the rest are named in one line.
  const pricedRows = payRows.filter((row) => payCell(row))
  const otherRows = payRows.filter((row) => !payCell(row))
  const tableRows = allJobTypes ? pricedRows : pricedRows.slice(0, JOB_TYPES_SHOWN)

  const visibleGroups = showAll ? roleGroups : roleGroups.slice(0, ROLES_SHOWN)
  const selectFamily = (family: string) => {
    setFamilyFilter(family)
    setShowAll(false)
    document.getElementById('open-roles')?.scrollIntoView({ block: 'start' })
  }

  return (
    <Shell backHref={backHref}>
      <h1 className="mt-4 break-words text-2xl font-semibold text-slate-900 sm:text-3xl">{profile.company_name}</h1>
      <p className="mt-1 text-base text-slate-700">
        {[isAgency ? 'Recruitment agency' : industry, open > 0 ? plural(open, 'open role', 'open roles') : 'No open roles right now']
          .filter(Boolean)
          .join(' · ')}
      </p>

      {isAgency && (
        <p className="mt-4 max-w-2xl text-slate-900">
          A recruitment agency advertises roles for other employers. The employer is usually not named in the ad.
        </p>
      )}
      {showOverallPay && (
        <p className="mt-4 max-w-2xl text-slate-900">
          {overallSpread ? (
            <>
              Most of its open ads pay <strong className="font-semibold">{overallSpread}</strong> {per}. The middle is{' '}
              <strong className="font-semibold">{money(profile.salary_p50!)}</strong>.
            </>
          ) : (
            <>
              Its open ads typically pay <strong className="font-semibold">{money(profile.salary_p50!)}</strong> {per}.
            </>
          )}{' '}
          <span className="text-slate-600">From {plural(profile.salary_sample_size, 'open ad', 'open ads')} that state a salary.</span>
        </p>
      )}

      {/* Pay by job type */}
      {open > 0 && pricedRows.length > 0 && (
        <section className="mt-8">
          <h2 className={h2Cls}>Pay by job type</h2>
          <table className="mt-2 w-full text-[15px]">
            <thead>
              <tr className="border-b border-slate-300 text-left text-sm text-slate-600">
                <th scope="col" className="py-2 pr-3 font-normal">
                  Job type
                </th>
                <th scope="col" className="py-2 pl-3 text-right font-normal">
                  Open roles
                </th>
                <th scope="col" className="py-2 pl-3 text-right font-normal">
                  Typical pay
                </th>
              </tr>
            </thead>
            <tbody>
              {tableRows.map((row) => {
                const pay = payCell(row)!
                return (
                  <tr key={row.role_family} className="border-b border-slate-200 align-baseline">
                    <td className="py-2.5 pr-3">
                      <button
                        type="button"
                        onClick={() => selectFamily(row.role_family)}
                        className={`text-left ${linkCls} ${familyFilter === row.role_family ? 'font-semibold' : ''}`}
                      >
                        {familyLabel(row.role_family)}
                      </button>
                    </td>
                    <td className="py-2.5 pl-3 text-right tabular-nums text-slate-900">{count(row.open_count)}</td>
                    <td className="py-2.5 pl-3 text-right tabular-nums">
                      <span className="whitespace-nowrap text-slate-900">{pay.main}</span>
                      {pay.sub && <span className="block whitespace-nowrap text-sm text-slate-600 sm:ml-2 sm:inline">{pay.sub}</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {!allJobTypes && pricedRows.length > JOB_TYPES_SHOWN && (
            <button type="button" onClick={() => setAllJobTypes(true)} className={`mt-3 text-[15px] ${linkCls}`}>
              Show all {count(pricedRows.length)} job types
            </button>
          )}
          <p className="mt-3 max-w-2xl text-sm text-slate-600">
            Advertised salaries in this company&rsquo;s open ads. Typical pay is the middle ad; “most ads” covers the middle half.
          </p>
        </section>
      )}
      {open > 0 && otherRows.length > 0 && (
        <p className={`max-w-2xl text-[15px] text-slate-700 ${pricedRows.length > 0 ? 'mt-3' : 'mt-8'}`}>
          {pricedRows.length > 0 ? 'Also hiring: ' : 'Hiring: '}
          {otherRows.map((row, i) => (
            <span key={row.role_family}>
              {i > 0 && ', '}
              <button type="button" onClick={() => selectFamily(row.role_family)} className={`text-left ${linkCls}`}>
                {familyLabel(row.role_family)}
              </button>{' '}
              ({count(row.open_count)})
            </span>
          ))}
          . Too few of these ads state a salary to give a typical figure.
        </p>
      )}

      {/* Open roles */}
      <section className="mt-8 scroll-mt-20" id="open-roles">
        <h2 className={h2Cls}>
          {familyFilter ? `Open roles in ${familyLabel(familyFilter)}` : 'Open roles'}
          {open > 0 && !familyFilter && <span className="font-normal text-slate-600"> ({count(open)})</span>}
        </h2>
        {open === 0 ? (
          <p className="mt-2 text-slate-900">
            No open roles right now. {plural(profile.total_count, 'ad', 'ads')} seen from this company
            {profile.first_seen ? ` since ${monthYear(profile.first_seen)}` : ''}.
          </p>
        ) : (
          <>
            {familyFilter && (
              <p className="mt-1 text-[15px]">
                <button type="button" onClick={() => selectFamily('')} className={linkCls}>
                  Show all {count(open)} open roles
                </button>
              </p>
            )}
            {listed < open && (
              <p className="mt-1 text-sm text-slate-600">
                Listing the newest {count(listed)} of {count(open)}.
              </p>
            )}
            <ul className="mt-2 border-t border-slate-300">
              {visibleGroups.map((g) => (
                <RoleRow key={g.job.job_uuid} group={g} />
              ))}
            </ul>
            {roleGroups.length === 0 && <p className="mt-2 text-slate-900">None of the newest {count(listed)} ads are in this job type.</p>}
            {!showAll && roleGroups.length > ROLES_SHOWN && (
              <button type="button" onClick={() => setShowAll(true)} className={`mt-4 text-[15px] ${linkCls}`}>
                Show {count(roleGroups.length - ROLES_SHOWN)} more
              </button>
            )}
          </>
        )}
      </section>

      {/* Ads posted more than once */}
      {reposted.length > 0 && (
        <section className="mt-8">
          <h2 className={h2Cls}>Ads posted more than once</h2>
          <p className="mt-1 max-w-2xl text-sm text-slate-600">
            Open ads whose exact text was posted before. This can mean ongoing hiring, high turnover, or an agency re-running a
            client&rsquo;s role.
          </p>
          <ul className="mt-2 border-t border-slate-300">
            {reposted.map((r) => (
              <li key={r.canonical_job_uuid} className="border-b border-slate-200 py-3">
                <span className="font-medium break-words text-slate-900">{r.title ?? 'Untitled ad'}</span>
                <div className="mt-1 text-sm text-slate-700">
                  Posted {count(r.repost_count)} times{monthYear(r.first_posted) ? ` since ${monthYear(r.first_posted)}` : ''}
                  {r.distinct_companies >= 2 && <> · under {r.distinct_companies} company names</>}
                  {' · '}
                  {adPayText(r.latest_salary_min, r.latest_salary_max)}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </Shell>
  )
}
