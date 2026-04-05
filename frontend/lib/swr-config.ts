/**
 * SWR config for dashboard stats.
 * Stats don't change during session; manual refresh only.
 */
export const DASHBOARD_SWR_CONFIG = {
  revalidateOnFocus: false,
  dedupingInterval: 3600000, // 1 hour
  refreshInterval: 0, // manual refresh only
} as const
