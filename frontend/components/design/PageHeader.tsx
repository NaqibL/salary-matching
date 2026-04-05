import * as React from "react"
import { cn } from "@/lib/utils"

export interface PageHeaderProps {
  /** Main page title */
  title: string
  /** Optional subtitle or description */
  subtitle?: string
  /** Slot for action buttons (e.g. primary CTA) */
  action?: React.ReactNode
  /** Additional class names for the root element */
  className?: string
}

/**
 * PageHeader - Page-level header with title, subtitle, and optional action slot.
 *
 * @example
 * ```tsx
 * <PageHeader
 *   title="Dashboard"
 *   subtitle="View your job match analytics"
 *   action={<Button>Export</Button>}
 * />
 * ```
 *
 * @example
 * ```tsx
 * <PageHeader
 *   title="Job Matches"
 *   subtitle="Based on your resume and preferences"
 * />
 * ```
 */
export function PageHeader({ title, subtitle, action, className }: PageHeaderProps) {
  return (
    <header
      className={cn(
        "flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between",
        "mb-6 md:mb-8",
        className
      )}
      aria-labelledby="page-title"
    >
      <div className="min-w-0 flex-1">
        <h1
          id="page-title"
          className="text-2xl font-semibold leading-tight text-slate-900 dark:text-slate-100 sm:text-3xl"
        >
          {title}
        </h1>
        {subtitle && (
          <p className="mt-1 text-base leading-relaxed text-slate-600 dark:text-slate-400">
            {subtitle}
          </p>
        )}
      </div>
      {action && (
        <div className="mt-4 shrink-0 sm:mt-0 sm:ml-4">{action}</div>
      )}
    </header>
  )
}
