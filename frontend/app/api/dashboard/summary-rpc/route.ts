/**
 * Dashboard summary via Supabase RPC (get_dashboard_summary).
 * Use when DB is Supabase Postgres. Bypasses FastAPI.
 * Cache: 5 min s-maxage + stale-while-revalidate.
 */
import { NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'

const CACHE_SECONDS = 300 // 5 min, matches rpc_result_cache TTL

export async function GET() {
  const { data, error } = await supabase.rpc('get_dashboard_summary')
  if (error) {
    return NextResponse.json({ detail: error.message }, { status: 502 })
  }
  return NextResponse.json(data, {
    headers: {
      'Cache-Control': `public, s-maxage=${CACHE_SECONDS}, stale-while-revalidate`,
    },
  })
}
