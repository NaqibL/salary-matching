import { Building2 } from 'lucide-react'

export const AGENCY_TOOLTIP =
  'Registered as an employment agency (SSIC 78). Posts roles on behalf of other employers.'

/** "Recruitment agency" tag. Shown only for companies registered under SSIC 78 (SGSAL-028). */
export function AgencyTag({ size = 'xs' }: { size?: 'xs' | 'sm' }) {
  const pad = size === 'sm' ? 'px-2.5 py-1 text-sm' : 'px-2 py-0.5 text-xs'
  return (
    <span
      title={AGENCY_TOOLTIP}
      className={`inline-flex items-center gap-1 rounded-full border font-medium bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-700 dark:text-slate-300 dark:border-slate-600 ${pad}`}
    >
      <Building2 className={size === 'sm' ? 'w-3.5 h-3.5' : 'w-3 h-3'} aria-hidden />
      Recruitment agency
    </span>
  )
}
