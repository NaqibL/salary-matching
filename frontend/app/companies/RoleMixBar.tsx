'use client'

import type { RoleFamilyRow } from '@/lib/types'
import { familyColor, familyLabel, topFamilies } from '@/lib/roleFamilies'

/**
 * Stacked mini bar: top three role families plus "other". Colour follows the family
 * (see lib/roleFamilies.ts); a 2px surface gap separates segments so neighbours that
 * share a slot stay distinguishable. The tooltip names every segment with its count.
 */
export function RoleMixBar({
  counts,
  total,
  familyRows,
  height = 8,
}: {
  counts: Record<string, number>
  total: number
  familyRows?: RoleFamilyRow[]
  height?: number
}) {
  if (!total) return null
  const slices = topFamilies(counts, 3)
  const title = slices.map((s) => `${familyLabel(s.key, familyRows)}: ${s.count}`).join(' · ')
  return (
    <div
      className="flex w-full gap-[2px] overflow-hidden rounded-full"
      style={{ height }}
      title={title}
      role="img"
      aria-label={`Role mix: ${title}`}
    >
      {slices.map((s) => (
        <div
          key={s.key}
          className="rounded-sm"
          style={{ width: `${(s.count / total) * 100}%`, backgroundColor: familyColor(s.key) }}
        />
      ))}
    </div>
  )
}
