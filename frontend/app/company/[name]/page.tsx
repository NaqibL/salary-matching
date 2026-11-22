'use client'

import { Suspense } from 'react'
import { useParams, useSearchParams } from 'next/navigation'
import CompanyContent from './CompanyContent'

function CompanyPageInner() {
  const params = useParams()
  const family = useSearchParams().get('family') ?? ''
  const name = decodeURIComponent(params.name as string)
  // keyed so moving between companies starts from that link's job type, not the last one viewed
  return <CompanyContent key={`${name}|${family}`} companyName={name} initialFamily={family} />
}

export default function CompanyPage() {
  return (
    <Suspense fallback={null}>
      <CompanyPageInner />
    </Suspense>
  )
}
