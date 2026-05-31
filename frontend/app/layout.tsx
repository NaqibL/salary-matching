import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { Providers } from './providers'
import PageTransition from './components/PageTransition'

const inter = Inter({ subsets: ['latin'], variable: '--font-inter' })

export const metadata: Metadata = {
  title: 'Lowball',
  description: 'Know your market value — see salary ranges for any role in Singapore from live job listings.',
  metadataBase: new URL('https://sglowball.vercel.app'),
  openGraph: {
    title: 'Lowball — Singapore Salary Checker',
    description: 'Check if your salary offer is fair. Benchmarks against 135k live MyCareersFuture listings.',
    url: 'https://sglowball.vercel.app',
    siteName: 'Lowball',
    locale: 'en_SG',
    type: 'website',
    images: [{ url: '/og-image.png', width: 1200, height: 630 }],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Lowball — Singapore Salary Checker',
    description: 'Check if your salary offer is fair. Benchmarks against 135k live MyCareersFuture listings.',
    images: ['/og-image.png'],
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <body className="font-sans antialiased">
        <Providers>
          <PageTransition>{children}</PageTransition>
        </Providers>
      </body>
    </html>
  )
}
