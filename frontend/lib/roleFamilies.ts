import type { RoleFamilyRow } from './types'

export const OTHER_FAMILY = 'other'

/** Fallback labels when the role-families endpoint has not loaded. Keys = role_families.key. */
export const FAMILY_LABELS: Record<string, string> = {
  other: 'Other',
  software_engineering: 'Software Engineering',
  data_ai_analytics: 'Data, AI & Analytics',
  it_infra_support_security: 'IT Infrastructure, Support & Security',
  sales_business_dev: 'Sales & Business Development',
  marketing_comms: 'Marketing & Communications',
  finance_accounting: 'Finance & Accounting',
  banking_financial_services: 'Banking & Financial Services',
  legal_compliance_cosec: 'Legal, Compliance & Corporate Secretarial',
  human_resources: 'Human Resources',
  admin_office_support: 'Admin & Office Support',
  customer_service: 'Customer Service',
  operations_strategy_pm: 'Operations, Strategy & Project Management',
  procurement_supply_chain_logistics: 'Procurement, Supply Chain & Logistics',
  warehouse_drivers_delivery: 'Warehouse, Drivers & Delivery',
  engineering_manufacturing: 'Engineering & Manufacturing',
  trades_technicians: 'Trades & Technicians',
  construction_architecture_property: 'Construction, Architecture & Property',
  healthcare_allied: 'Healthcare & Allied Health',
  education_social_services: 'Education & Social Services',
  fnb_hospitality: 'F&B & Hospitality',
  retail_beauty: 'Retail & Beauty',
  cleaning_security_general_labour: 'Cleaning, Security & General Labour',
  creative_design: 'Creative & Design',
  science_research_lab: 'Science, Research & Lab',
}

/**
 * Colour follows the entity: every family maps to one of eight validated categorical
 * slots (dataviz reference palette, fixed order), grouped by sector so the 24 families
 * never need a ninth hue. The slot is exposed as a CSS variable (`--viz-1..8`, defined in
 * globals.css with light and dark steps) with the light hex as fallback.
 */
export const FAMILY_SLOT: Record<string, number> = {
  // 1 blue — tech
  software_engineering: 1,
  data_ai_analytics: 1,
  it_infra_support_security: 1,
  // 2 orange — commercial & creative
  sales_business_dev: 2,
  marketing_comms: 2,
  creative_design: 2,
  // 3 aqua — finance & legal
  finance_accounting: 3,
  banking_financial_services: 3,
  legal_compliance_cosec: 3,
  // 4 yellow — business support & operations
  human_resources: 4,
  admin_office_support: 4,
  customer_service: 4,
  operations_strategy_pm: 4,
  // 5 magenta — health, education & science
  healthcare_allied: 5,
  education_social_services: 5,
  science_research_lab: 5,
  // 6 green — logistics
  procurement_supply_chain_logistics: 6,
  warehouse_drivers_delivery: 6,
  // 7 violet — engineering, trades & construction
  engineering_manufacturing: 7,
  trades_technicians: 7,
  construction_architecture_property: 7,
  // 8 red — service & frontline
  fnb_hospitality: 8,
  retail_beauty: 8,
  cleaning_security_general_labour: 8,
}

const SLOT_LIGHT_HEX = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948']

export function familyLabel(key: string, rows?: RoleFamilyRow[]): string {
  return rows?.find((r) => r.role_family === key)?.display_name ?? FAMILY_LABELS[key] ?? key
}

/** CSS colour for a family: a `--viz-N` variable with the light hex as fallback; neutral for "other". */
export function familyColor(key: string): string {
  const slot = FAMILY_SLOT[key]
  if (!slot) return 'var(--viz-other, #cbd5e1)'
  return `var(--viz-${slot}, ${SLOT_LIGHT_HEX[slot - 1]})`
}

/** Top-N families by count plus an aggregated "other" slice. */
export function topFamilies(
  counts: Record<string, number>,
  n = 3,
): Array<{ key: string; count: number }> {
  const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1])
  const top = sorted.slice(0, n).map(([key, count]) => ({ key, count }))
  const rest = sorted.slice(n).reduce((s, [, c]) => s + c, 0)
  if (rest > 0) top.push({ key: OTHER_FAMILY, count: rest })
  return top
}
