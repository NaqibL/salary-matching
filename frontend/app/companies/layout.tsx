import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Companies hiring in Singapore | Lowball',
  description: 'Who is hiring in Singapore, how many roles are open, and what their ads pay.',
}

export default function SectionLayout({ children }: { children: React.ReactNode }) {
  return children
}
