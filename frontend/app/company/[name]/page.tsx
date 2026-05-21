'use client'

import { useParams } from 'next/navigation'
import CompanyContent from './CompanyContent'

export default function CompanyPage() {
  const params = useParams()
  const name = decodeURIComponent(params.name as string)
  return <CompanyContent companyName={name} />
}
