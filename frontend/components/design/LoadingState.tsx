import * as React from "react"
import { cn } from "@/lib/utils"
import { Skeleton } from "@/components/ui/skeleton"

export interface LoadingStateProps {
  /** Layout variant: card, list, table, page, dashboard, or matches */
  variant?: "card" | "list" | "table" | "page" | "dashboard" | "matches"
  /** Number of items to show (for list/table) */
  count?: number
  /** Additional class names for the root element */
  className?: string
}

/**
 * LoadingState - Skeleton screens for common layouts.
 * Uses 8pt grid spacing. Supports dark mode via Skeleton.
 *
 * @example
 * ```tsx
 * <LoadingState variant="card" />
 * ```
 *
 * @example
 * ```tsx
 * <LoadingState variant="list" count={5} />
 * ```
 *
 * @example
 * ```tsx
 * <LoadingState variant="page" className="max-w-6xl mx-auto" />
 * ```
 */
export function LoadingState({
  variant = "card",
  count = 3,
  className,
}: LoadingStateProps) {
  return (
    <div className={cn("animate-pulse", className)}>
      {variant === "card" && <CardSkeleton />}
      {variant === "list" && <ListSkeleton count={count} />}
      {variant === "table" && <TableSkeleton count={count} />}
      {variant === "page" && <PageSkeleton />}
      {variant === "dashboard" && <DashboardSkeleton />}
      {variant === "matches" && <MatchesSkeleton count={count} />}
    </div>
  )
}

function CardSkeleton() {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 dark:border-slate-700 dark:bg-slate-800">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 space-y-2">
          <Skeleton className="h-5 w-3/4" />
          <Skeleton className="h-4 w-1/2" />
        </div>
        <Skeleton className="h-8 w-16 rounded-lg" />
      </div>
      <div className="mt-4 space-y-2">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-4/6" />
      </div>
      <div className="mt-4 flex gap-2">
        <Skeleton className="h-9 flex-1 rounded-lg" />
        <Skeleton className="h-9 flex-1 rounded-lg" />
      </div>
    </div>
  )
}

function ListSkeleton({ count }: { count: number }) {
  return (
    <div className="space-y-4">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="flex gap-4 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800"
        >
          <Skeleton className="size-12 shrink-0 rounded-lg" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-5 w-2/3" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-4 w-1/2" />
          </div>
          <Skeleton className="h-8 w-20 shrink-0 rounded-lg" />
        </div>
      ))}
    </div>
  )
}

function TableSkeleton({ count }: { count: number }) {
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800">
      <div className="flex gap-4 border-b border-slate-200 px-4 py-3 dark:border-slate-700">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-4 w-20" />
      </div>
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="flex gap-4 border-b border-slate-100 px-4 py-4 last:border-0 dark:border-slate-700"
        >
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-4 flex-1" />
          <Skeleton className="h-4 w-20" />
        </div>
      ))}
    </div>
  )
}

function PageSkeleton() {
  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-2">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-4 w-64" />
        </div>
        <Skeleton className="h-9 w-24 rounded-lg" />
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="rounded-xl border border-slate-200 bg-white p-6 dark:border-slate-700 dark:bg-slate-800"
          >
            <Skeleton className="h-10 w-10 rounded-lg" />
            <Skeleton className="mt-4 h-8 w-16" />
            <Skeleton className="mt-1 h-4 w-24" />
          </div>
        ))}
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-6 dark:border-slate-700 dark:bg-slate-800">
        <Skeleton className="h-5 w-3/4" />
        <Skeleton className="mt-4 h-64 w-full rounded-lg" />
      </div>
    </div>
  )
}

function DashboardSkeleton() {
  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-2">
          <Skeleton className="h-8 w-40" />
          <Skeleton className="h-4 w-56" />
        </div>
        <div className="flex gap-1 rounded-lg bg-slate-100 p-1 dark:bg-slate-700">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-8 w-12 rounded-md" />
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <div
            key={i}
            className="rounded-xl border border-slate-200 bg-white p-6 dark:border-slate-700 dark:bg-slate-800"
          >
            <Skeleton className="h-10 w-10 rounded-lg" />
            <Skeleton className="mt-4 h-8 w-16" />
            <Skeleton className="mt-1 h-4 w-20" />
          </div>
        ))}
      </div>

      <div className="space-y-6">
        <div className="rounded-xl border border-slate-200 bg-white p-6 dark:border-slate-700 dark:bg-slate-800">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="mt-4 h-64 w-full rounded-lg" />
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-6 dark:border-slate-700 dark:bg-slate-800">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="mt-4 h-72 w-full rounded-lg" />
        </div>
      </div>
    </div>
  )
}

function MatchesSkeleton({ count = 5 }: { count?: number }) {
  return (
    <div className="space-y-4">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="rounded-xl border border-slate-200 bg-white overflow-hidden dark:border-slate-700 dark:bg-slate-800"
        >
          <div className="p-6">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 space-y-2">
                <Skeleton className="h-6 w-3/4" />
                <div className="flex gap-4">
                  <Skeleton className="h-4 w-24" />
                  <Skeleton className="h-4 w-20" />
                </div>
              </div>
              <Skeleton className="h-8 w-16 rounded-full shrink-0" />
            </div>
            <div className="mt-4 flex gap-2">
              <Skeleton className="h-5 w-16 rounded-md" />
              <Skeleton className="h-5 w-20 rounded-md" />
            </div>
          </div>
          <div className="flex border-t border-slate-100 dark:border-slate-700">
            <Skeleton className="h-12 flex-1" />
            <Skeleton className="h-12 flex-1" />
          </div>
        </div>
      ))}
    </div>
  )
}
