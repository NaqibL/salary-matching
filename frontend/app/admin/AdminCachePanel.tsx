'use client'

import { useState, useEffect, useCallback } from 'react'
import { supabase } from '@/lib/supabase'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardHeader, CardTitle, CardBody } from '@/components/design'
import { RefreshCw, Trash2, Zap } from 'lucide-react'

type CacheStats = {
  response_cache?: { hits: number; misses: number; hit_rate: number; keys_count: number }
  matches_cache?: { hits: number; misses: number; hit_rate: number; keys_count: number }
}

function getAuthHeaders(): Promise<Record<string, string>> {
  return supabase.auth.getSession().then(({ data }) => {
    const token = data.session?.access_token
    return (token ? { Authorization: `Bearer ${token}` } : {}) as Record<string, string>
  })
}

export function AdminCachePanel() {
  const [stats, setStats] = useState<CacheStats | null>(null)
  const [timestamp, setTimestamp] = useState<string | null>(null)
  const [keyToClear, setKeyToClear] = useState('')
  const [prefixToClear, setPrefixToClear] = useState('matches:')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [actionFeedback, setActionFeedback] = useState<string | null>(null)

  const fetchStats = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const headers = await getAuthHeaders()
      const res = await fetch('/api/admin/cache-stats', { headers })
      const data = await res.json()
      if (!res.ok) {
        setError(data.detail || data.error || `HTTP ${res.status}`)
        setStats(null)
        return
      }
      setStats(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch')
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchTimestamp = useCallback(async () => {
    try {
      const headers = await getAuthHeaders()
      const res = await fetch('/api/admin/cache-timestamp', { headers })
      const data = await res.json()
      if (res.ok) setTimestamp(data.last_updated ?? null)
    } catch {
      setTimestamp(null)
    }
  }, [])

  const forceRevalidate = useCallback(async () => {
    setActionFeedback(null)
    try {
      const headers = await getAuthHeaders()
      const res = await fetch('/api/admin/revalidate-dashboard', {
        method: 'POST',
        headers,
      })
      const data = await res.json()
      if (!res.ok) {
        setActionFeedback(data.error || `HTTP ${res.status}`)
        return
      }
      setActionFeedback('Dashboard revalidated')
      fetchTimestamp()
    } catch (e) {
      setActionFeedback(e instanceof Error ? e.message : 'Failed')
    }
  }, [fetchTimestamp])

  const clearKey = useCallback(async () => {
    if (!keyToClear.trim()) return
    setActionFeedback(null)
    try {
      const headers = await getAuthHeaders()
      const res = await fetch(
        `/api/admin/clear-cache?key=${encodeURIComponent(keyToClear.trim())}`,
        { method: 'DELETE', headers }
      )
      const data = await res.json()
      if (!res.ok) {
        setActionFeedback(data.detail || data.error || `HTTP ${res.status}`)
        return
      }
      setActionFeedback(`Cleared ${data.removed ?? 0} key(s)`)
      fetchStats()
    } catch (e) {
      setActionFeedback(e instanceof Error ? e.message : 'Failed')
    }
  }, [keyToClear, fetchStats])

  const clearPrefix = useCallback(async () => {
    if (!prefixToClear.trim()) return
    setActionFeedback(null)
    try {
      const headers = await getAuthHeaders()
      const res = await fetch(
        `/api/admin/clear-cache?prefix=${encodeURIComponent(prefixToClear.trim())}`,
        { method: 'DELETE', headers }
      )
      const data = await res.json()
      if (!res.ok) {
        setActionFeedback(data.detail || data.error || `HTTP ${res.status}`)
        return
      }
      setActionFeedback(`Cleared ${data.removed ?? 0} key(s)`)
      fetchStats()
    } catch (e) {
      setActionFeedback(e instanceof Error ? e.message : 'Failed')
    }
  }, [prefixToClear, fetchStats])

  useEffect(() => {
    fetchStats()
    fetchTimestamp()
  }, [fetchStats, fetchTimestamp])

  if (error?.includes('403') || error?.toLowerCase().includes('admin')) {
    return (
      <Card>
        <CardBody>
          <p className="text-destructive">Access denied. Admin access required.</p>
          <p className="mt-2 text-sm text-muted-foreground">
            Set ADMIN_USER_IDS in your environment and ensure your user ID is included.
          </p>
        </CardBody>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      {actionFeedback && (
        <p className="rounded-lg bg-muted px-3 py-2 text-sm">{actionFeedback}</p>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <RefreshCw className="size-4" />
            Cache hit rates
          </CardTitle>
        </CardHeader>
        <CardBody>
          {loading ? (
            <p className="text-muted-foreground">Loading…</p>
          ) : stats ? (
            <pre className="overflow-auto rounded-lg bg-muted p-4 text-sm">
              {JSON.stringify(stats, null, 2)}
            </pre>
          ) : (
            <p className="text-muted-foreground">{error || 'No data'}</p>
          )}
          <Button onClick={fetchStats} variant="outline" size="sm" className="mt-2">
            Refresh
          </Button>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Last cache update</CardTitle>
        </CardHeader>
        <CardBody>
          <p className="text-muted-foreground">{timestamp ?? '—'}</p>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Zap className="size-4" />
            Force revalidate dashboard
          </CardTitle>
        </CardHeader>
        <CardBody>
          <Button onClick={forceRevalidate}>Revalidate dashboard-stats</Button>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Trash2 className="size-4" />
            Clear cache
          </CardTitle>
        </CardHeader>
        <CardBody className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Input
              placeholder="Key (exact)"
              value={keyToClear}
              onChange={(e) => setKeyToClear(e.target.value)}
              className="max-w-xs"
            />
            <Button onClick={clearKey} variant="destructive" size="sm">
              Clear key
            </Button>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Input
              placeholder="Prefix (e.g. matches:)"
              value={prefixToClear}
              onChange={(e) => setPrefixToClear(e.target.value)}
              className="max-w-xs"
            />
            <Button onClick={clearPrefix} variant="destructive" size="sm">
              Clear prefix
            </Button>
          </div>
        </CardBody>
      </Card>
    </div>
  )
}
