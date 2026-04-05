import * as React from "react"
import { cn } from "@/lib/utils"

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Size variant: default (p-6) or compact (p-4) */
  size?: "default" | "compact"
}

/**
 * Card - Container with optional header, body, and footer sections.
 * Uses 8pt grid spacing. Supports dark mode via semantic tokens.
 *
 * @example
 * ```tsx
 * <Card>
 *   <Card.Header>
 *     <Card.Title>Card Title</Card.Title>
 *   </Card.Header>
 *   <Card.Body>Content here</Card.Body>
 *   <Card.Footer>
 *     <Button>Action</Button>
 *   </Card.Footer>
 * </Card>
 * ```
 *
 * @example
 * ```tsx
 * <Card size="compact" className="max-w-md">
 *   <Card.Body>Compact card with body only</Card.Body>
 * </Card>
 * ```
 */
const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, size = "default", ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "flex flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-md",
        "transition-shadow duration-200 hover:shadow-lg dark:border-slate-700 dark:bg-slate-800",
        "data-[new]:animate-border-pulse",
        size === "default" ? "p-6" : "p-4",
        className
      )}
      {...props}
    />
  )
)
Card.displayName = "Card"

const CardHeader = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "mb-4 border-b border-slate-200 pb-4 dark:border-slate-700 dark:pb-4",
      "[&:last-child]:mb-0 [&:last-child]:border-0 [&:last-child]:pb-0",
      className
    )}
    {...props}
  />
))
CardHeader.displayName = "CardHeader"

const CardTitle = React.forwardRef<
  HTMLHeadingElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
  <h3
    ref={ref}
    className={cn(
      "text-lg font-semibold leading-tight text-slate-900 dark:text-slate-100",
      className
    )}
    {...props}
  />
))
CardTitle.displayName = "CardTitle"

const CardBody = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "flex-1 text-base leading-relaxed text-slate-700 dark:text-slate-300",
      className
    )}
    {...props}
  />
))
CardBody.displayName = "CardBody"

const CardFooter = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "mt-4 flex items-center gap-4 border-t border-slate-200 pt-4 dark:border-slate-700 dark:pt-4",
      className
    )}
    {...props}
  />
))
CardFooter.displayName = "CardFooter"

export { Card, CardHeader, CardTitle, CardBody, CardFooter }
