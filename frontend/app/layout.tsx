import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { Providers } from './providers'
import PageTransition from './components/PageTransition'

const inter = Inter({ subsets: ['latin'], variable: '--font-inter' })

export const metadata: Metadata = {
  title: 'SG Salary Check',
  description: 'Know your market value — see salary ranges for any role in Singapore from live job listings.',
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
