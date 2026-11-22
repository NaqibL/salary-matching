import type { Metadata } from 'next'

export function generateMetadata({ params }: { params: { name: string } }): Metadata {
  let name = params.name
  try {
    name = decodeURIComponent(params.name)
  } catch {}
  return {
    title: `${name}: open roles and pay | Lowball`,
    description: `Open roles at ${name} and what its job ads pay, by job type.`,
  }
}

export default function CompanyLayout({ children }: { children: React.ReactNode }) {
  return children
}
