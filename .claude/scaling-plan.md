# Scaling Plan — Vector Search Architecture

Current state: 150k jobs, ~4k added/day, in-memory pool cache (~550MB warmup).
Problem: warmup data grows linearly. At 6 months, ~3GB and minutes to warm.

---

## Tonight — Quick wins (do these now)

### 1. Binary embedding transfer
**Impact:** Halves pool warmup size and time immediately.  
**Why:** `get_active_jobs_pool()` casts embeddings to `::text` (JSON), ~6KB/row. Binary float32 is ~3KB/row.  
**How:**
- Install `pgvector` Python package: `uv add pgvector`
- Register the vector type on the connection so psycopg2 receives raw numpy arrays
- Change `e.embedding::text` → `e.embedding` in the pool query
- Remove `json.loads(r[1])` — psycopg2 returns the array directly

```python
# In _cur() / _transaction_cur(), after getting conn:
from pgvector.psycopg2 import register_vector
register_vector(conn)

# In get_active_jobs_pool():
cur.execute("SELECT j.job_uuid, e.embedding, j.last_seen_at FROM ...")
# r[1] is now a numpy array directly — no json.loads needed
```

**File:** `src/mcf/lib/storage/postgres_store.py`

---

### 2. Raise statement_timeout for the app role in Supabase
**Impact:** Removes the need for `SET LOCAL statement_timeout = 0` hacks.  
**Why:** Supabase's default timeout is too short for large queries under load.  
**How:** Run once in Supabase SQL editor:

```sql
ALTER ROLE authenticator SET statement_timeout = '30s';
```

This applies to all connections from your app (Railway uses the `authenticator` role via PgBouncer). Adjust role name if yours differs — check with `SELECT current_user;` in Supabase SQL editor.

---

## This week — Medium-term fix

### 3. Remove the pool cache, rely on HNSW
**Impact:** Eliminates the scaling problem entirely. No memory pressure as jobs grow.  
**Why:** With statement_timeout raised and HNSW working correctly (SET LOCAL fix from tonight's session), the DB query should return top-500 in under 100ms even at 500k+ jobs. The pool cache was a workaround for the timeout, not a fundamental requirement.  
**How:**
- Set `ENABLE_ACTIVE_JOBS_POOL_CACHE=0` in Railway (or remove the var)
- Monitor Supabase query times via the Supabase dashboard (Reports → Query Performance)
- If p95 latency is under 200ms at your traffic level, the pool cache is unnecessary

**Risk:** If HNSW queries are still slow under concurrent load, keep the pool cache but apply the binary transfer fix (step 1) to make warmup fast enough.

---

## Next month — If jobs exceed 500k

### 4. Filter pool to recent active jobs only
**Impact:** Caps pool size regardless of total job count.  
**Why:** Jobs older than 90 days that are still "active" contribute very little to results — users won't apply to stale listings.  
**How:** Add `AND j.last_seen_at >= NOW() - INTERVAL '90 days'` to `get_active_jobs_pool()`.  
This caps the pool at ~4k/day × 90 days = ~360k max, regardless of total DB size.

### 5. Half-precision embeddings (halfvec)
**Impact:** Halves embedding storage and transfer again.  
**Why:** pgvector supports `halfvec` (16-bit float) — minimal accuracy loss for cosine similarity.  
**How:** Migration required — `ALTER TABLE job_embeddings ALTER COLUMN embedding TYPE halfvec(768)`. Requires re-testing match quality first.

---

## Priority order for tonight

1. Run the SQL in Supabase to raise `statement_timeout`
2. Implement binary transfer (pgvector Python package)
3. Redeploy and verify pool warms successfully on startup
4. Check Railway memory metrics — should be lower than current

---

## Context from today's debug session (2026-06-01)

- `ENABLE_ACTIVE_JOBS_POOL_CACHE=1` must be set in Railway env vars
- `_transaction_cur()` added for PgBouncer-safe `SET LOCAL` — use this for any query needing session settings
- Pool warmup disables statement_timeout via `SET LOCAL statement_timeout = 0`
- After binary transfer fix, that hack can be removed if Supabase role timeout is raised
- All HNSW queries now use `SET LOCAL hnsw.ef_search` inside a transaction — previously being silently dropped by PgBouncer
