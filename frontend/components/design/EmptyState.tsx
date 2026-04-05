import * as React from "react"
import { cn } from "@/lib/utils"
import type { LucideIcon } from "lucide-react"

export interface EmptyStateProps {
  /** Lucide icon component to display */
  icon: LucideIcon
  /** Primary message shown to the user */
  message: string
  /** Optional secondary description */
  description?: string
  /** Optional CTA (button or link) */
  action?: React.ReactNode
  /** Additional class names for the root element */
  className?: string
}

/**
 * EmptyState - Shown when a list or section has no data.
 * Uses 8pt grid spacing. Supports dark mode.
 *
 * @example
 * ```tsx
 * <EmptyState
 *   icon={Inbox}
 *   message="No jobs yet"
 *   description="Upload your resume to see matches"
 *   action={<Button>Upload Resume</Button>}
 * />
 * ```
 *
 * @example
 * ```tsx
 * <EmptyState
 *   icon={Search}
 *   message="No results found"
 *   action={<Link href="/">Try again</Link>}
 * />
 * ```
 */
export function EmptyState({
  icon: Icon,
  message,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-4 px-4 py-12 text-center",
        "md:gap-6 md:py-16",
        className
      )}
      role="status"
      aria-label={message}
    >
      <div
        className={cn(
          "flex size-12 items-center justify-center rounded-full",
          "bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400"
        )}
      >
        <Icon className="size-6" aria-hidden />
      </div>
      <div className="space-y-1">
        <p className="text-base font-medium text-slate-900 dark:text-slate-100 md:text-lg">
          {message}
        </p>
        {description && (
          <p className="text-sm leading-relaxed text-slate-600 dark:text-slate-400">
            {description}
          </p>
        )}
      </div>
      {action && (
        <div className="mt-2">{action}</div>
      )}
    </div>
  )
}
