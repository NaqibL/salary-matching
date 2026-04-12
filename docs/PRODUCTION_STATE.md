MCF JOB MATCHER — PRODUCTION STATE
====================================
Last updated: 2026-04-05


WHAT IT IS
----------
A Singapore job aggregator + semantic matcher. Crawls MyCareersFuture (MCF) and
Careers@Gov (CAG), embeds job listings with BGE, and matches them against user
resumes or taste profiles. Hosted on Railway (API) + Vercel (frontend) + Supabase
(Postgres + Auth + Storage).


STACK
-----
Backend  : FastAPI (Python 3.13), uv, src/mcf/
Frontend : Next.js 14 App Router, frontend/
Database : Supabase Postgres + pgvector (prod), DuckDB (local dev)
Auth     : Supabase JWT
Storage  : Supabase Storage (resume PDFs)
CI/CD    : GitHub Actions (daily crawl, re-embed, lint)
Hosting  : Railway (API), Vercel (frontend)


EMBEDDING MODEL
---------------
BAAI/bge-base-en-v1.5
- 768 dimensions (upgraded from bge-small-en-v1.5 / 384-dim)
- Asymmetric setup: queries get "Represent this sentence:" prefix, passages don't
- Embedding text format: "Job Title: X\nRequired Skills: ...\nSeniority: Y, N+ years experience"
- Seniority and years experience baked in at embed time


DATABASE (applied migrations: 001–010)
---------------------------------------
001 : pgvector extension + HNSW index
002 : job_embeddings schema + HNSW (384-dim original)
002_upgrade_embeddings_768 : dropped/recreated embedding columns as vector(768)
003 : rich job fields (salary, employment type, position level, years exp)
004 : embeddings_cache table (content-hash keyed)
005 : dashboard materialized views
006 : Supabase RPC functions for dashboard + matching
007 : cache metadata table
008 : Row-Level Security on public tables
009 : role_cluster (INT) + predicted_tier (TEXT) columns on jobs table
010 : role_clusters_json (INTEGER[]) column on jobs table (multi-label, populated later)

Current job count: ~65,600 active jobs (65,605 with 768-dim embeddings)


CRAWL PIPELINE
--------------
Sources: MyCareersFuture API + Careers@Gov API
Schedule: Daily via GitHub Actions (workflows/daily-crawl.yml)
Flow:
  Phase 1 — Fetch & upsert new/updated jobs (incremental diff)
  Phase 2 — Embed new jobs with BGE-base (768-dim), store in job_embeddings
  Phase 3 — Classify new jobs (role cluster + tier), store in jobs table

Crawl is non-destructive: existing embeddings and classifications are preserved.


CLASSIFICATION MODELS (src/mcf/models/)
----------------------------------------
kmeans_role_v1.pkl (378 KB)
  - K-Means k=35 role clusters, trained on Apr 2026 snapshot (65k jobs)
  - Silhouette: 0.0955 (5-seed mean)
  - Predict latency: ~0.1ms per batch

lr_tier_v1.pkl (25 KB)
  - LogisticRegression experience tier classifier
  - Classes: T1_Entry / T2_Junior / T3_Senior / T4_Management
  - Balanced accuracy: 0.875 (vs 0.698 for the old KNN approach)
  - Predict latency: 0.07ms per 32-job batch

role_taxonomy.json
  - Maps cluster ID (0–34) to human-readable role name

The 35 Role Clusters:
  C00 Drivers & Delivery              C01 Construction Project Management
  C02 Retail & Store Operations       C03 Healthcare Support & Clinic
  C04 Admin & Secretarial             C05 Marketing & Digital Marketing
  C06 Finance & Legal                 C07 Quantity Surveying
  C08 Construction Coordination       C09 F&B Service
  C10 Site Supervision                C11 General Management
  C12 Beauty & Wellness               C13 Kitchen & Culinary (Junior)
  C14 Business Development & Strategy C15 Accounting & Finance Operations
  C16 Operations & Customer Service   C17 Data Science & Research
  C18 Human Resources                 C19 Software Development
  C20 Nursing & Allied Health         C21 F&B Management
  C22 Sales                           C23 Technician & Maintenance
  C24 Cleaning & Facilities           C25 Mechanical & Manufacturing Engineering
  C26 IT Infrastructure & Support     C27 Data Engineering & Cloud / AI (highest paid ~$7k)
  C28 Kitchen & Culinary (Senior)     C29 Design & Architecture
  C30 Software Engineering            C31 Electrical & M&E Engineering
  C32 Early Childhood Education       C33 Business & Data Analysis
  C34 Warehouse & Logistics


MATCHING ALGORITHM (src/mcf/api/services/matching_service.py)
--------------------------------------------------------------
1. Resume embed  : User resume → BGE-base query embedding (768-dim)
2. Query expand  : Rocchio expansion if user has ratings
                   q = 0.7*resume + 0.3*mean(liked) - 0.1*mean(disliked)
3. Pool load     : All active jobs + embeddings loaded into memory (active jobs pool cache, 15min TTL)
4. Scoring       : cosine_similarity * recency_factor * tier_factor
                   recency_factor = max(0.5, 1 - 0.005 * days_old)
                   tier_factor    = 1.05 if job tier == candidate tier, else 1.0
5. Session       : Ranked list stored as match session for paginated Load More
6. Hydrate       : Top-K job UUIDs fetched from jobs table (with role_cluster, predicted_tier)

Taste mode: same pipeline but uses taste-profile embedding instead of resume.
Taste profile = L2_normalize(mean(liked_embeddings) - 0.3 * mean(disliked_embeddings))

Filters available (passed as query params):
  - role_cluster[]   : filter to specific role clusters (multi-select)
  - predicted_tier[] : filter to experience tiers (multi-select)
  - min_similarity   : minimum cosine similarity threshold
  - max_days_old     : maximum job age in days


API ENDPOINTS (src/mcf/api/server.py, ~30 routes)
--------------------------------------------------
Auth
  POST /api/profile/upload-resume    Upload + process resume, create candidate embedding
  GET  /api/profile                  Get profile + resume status
  POST /api/profile/compute-taste    Build taste embedding from ratings
  POST /api/profile/reset-ratings    Clear all interactions + taste profile

Matching
  GET  /api/matches                  Get job matches (resume or taste mode, paginated)
  GET  /api/jobs/taxonomy            Role cluster taxonomy (35 clusters)
  GET  /api/jobs/interested          Jobs user marked as Interested
  GET  /api/jobs/{uuid}              Full job details
  POST /api/jobs/{uuid}/interact     Record interaction (interested/not_interested/etc.)

Dashboard (public, no auth)
  GET  /api/dashboard/summary-public
  GET  /api/dashboard/active-jobs-over-time-public
  GET  /api/dashboard/jobs-by-category-public

Dashboard (authed)
  GET  /api/dashboard/summary
  GET  /api/dashboard/jobs-over-time-posted-and-removed
  GET  /api/dashboard/active-jobs-over-time
  GET  /api/dashboard/jobs-by-category
  GET  /api/dashboard/category-trends
  GET  /api/dashboard/category-stats
  GET  /api/dashboard/jobs-by-employment-type
  GET  /api/dashboard/jobs-by-position-level
  GET  /api/dashboard/salary-distribution
  GET  /api/dashboard/charts-static

Tools
  POST /api/lowball/check            Salary benchmarking against similar jobs
  GET  /api/discover/stats           Interested/Not Interested/Unrated counts
  GET  /api/health                   Health check

Admin (requires crawl secret or admin JWT)
  POST /api/admin/invalidate-pool    Flush active jobs pool cache
  POST /api/admin/invalidate-cache   Flush response/matches cache
  GET  /api/admin/cache-stats        Cache hit rates and size


FRONTEND PAGES (frontend/app/)
-------------------------------
/             Landing page with live job stats
/matches      Main page: Resume Matches + Taste Matches tabs
              - Role Category filter (35 cluster chips, multi-select)
              - Experience Level filter (Entry/Junior/Senior/Management)
              - Min Match % slider
              - Max Days Old input
              - Each job card shows: role name badge, tier badge, recency badge, match %
/saved        Saved (Interested) jobs list
/job/[uuid]   Job detail page with similar jobs + salary checker
/lowball      Salary benchmarking tool (paste job description + offered salary)
/dashboard    Analytics: job counts, trends, category breakdown, salary distribution
/how-it-works Explanation of the matching algorithm
/admin        Cache management + crawl stats (admin only)


CACHING LAYERS
--------------
1. Active jobs pool cache (in-memory, 15min TTL)
   All active job embeddings held in RAM for fast cosine scoring
   ~65k jobs × 768 floats = ~200MB
   Invalidated on crawl completion

2. Match session cache (in-memory)
   Ranked job UUID list per user session
   Enables paginated Load More without re-scoring

3. Response cache (in-memory, TTL varies)
   matches: 15min, job detail: longer TTL
   Invalidated on resume upload or interaction

4. Next.js unstable_cache (Vercel edge, 15min)
   /api/matches route cached by user_id + all params
   Invalidated via /api/revalidate-matches (POST)

5. Embeddings cache (Postgres, indefinite TTL)
   Content-hash keyed: same text always returns cached embedding
   Avoids re-encoding unchanged job descriptions


KNOWN LIMITATIONS / NEXT STEPS
-------------------------------
1. Multi-label role tagging (Priority 2)
   At cosine similarity >= 0.85, ~45% of jobs belong to 2+ clusters
   role_clusters_json column exists (migration 010) but is not yet populated
   Would enable: searching Data Science also surfaces Data Engineering jobs
   Key co-occurring pairs: PM<->SWE, PM<->BD, SWE<->Data

2. Classifiers retrain trigger
   Models trained on Apr 2026 snapshot (65k jobs)
   Suggested: retrain quarterly or when job pool grows >20%
   Scripts: notebooks/experience_clustering_v2.ipynb (tier), data/analysis_roles/ (roles)

3. process-resume button (Re-process in UI)
   Returns 404 in production because Supabase Storage is not configured
   Fix: set SUPABASE_URL + SUPABASE_SERVICE_KEY on Railway to enable storage
   Workaround: users can use Replace (re-upload) instead

4. server.py is a single large file (~900 lines)
   Could be split into FastAPI routers per domain (jobs, profile, dashboard, admin)
   No functional impact, just maintainability


REPO STRUCTURE
--------------
src/mcf/
  api/
    server.py              All FastAPI routes (~30 endpoints)
    config.py              Settings (env vars)
    auth.py                JWT auth dependency
    matches_cache.py       In-memory match cache
    response_cache.py      Decorator-based response cache
    active_jobs_pool_cache.py  In-memory job embedding pool
    services/
      matching_service.py  Core matching logic (Rocchio, scoring, sessions)
  lib/
    classifiers.py         Role cluster + tier classification (lazy-loaded sklearn)
    categories.py          MCF job category constants
    crawler/               HTTP crawler (rate-limited, retry)
    embeddings/
      embedder.py          BGE-base wrapper (embed_resume, embed_query, embed_passage)
      embeddings_cache.py  Content-hash embedding cache
      job_text.py          Job text formatting for embedding
      resume.py            PDF/DOCX text extraction + preprocessing
    pipeline/
      incremental_crawl.py Main crawl pipeline (Phase 1-3)
    sources/
      mcf.py               MyCareersFuture API adapter
      cag.py               Careers@Gov API adapter
    storage/
      base.py              Storage protocol (interface)
      postgres_store.py    Supabase Postgres implementation
      duckdb_store.py      Local DuckDB implementation
  models/
    kmeans_role_v1.pkl     Role cluster model
    lr_tier_v1.pkl         Tier classifier model
    role_taxonomy.json     Cluster ID -> name mapping
  cli/
    cli.py                 CLI (mcf crawl-incremental, mcf re-embed, etc.)

frontend/app/
  page.tsx                 Landing page
  matches/page.tsx         Main matches page
  saved/page.tsx           Saved jobs
  job/[uuid]/page.tsx      Job detail
  lowball/page.tsx         Salary checker
  dashboard/page.tsx       Analytics dashboard
  components/
    JobCard.tsx            Match card (shows role, tier, recency, score)
    ResumeTab.tsx          Resume matches + filters + rating UI
    TasteTab.tsx           Taste match results
    ProfileProvider.tsx    Profile context + SWR
    RatingsQueueProvider.tsx  Batched rating submission

frontend/lib/
  api.ts                   All API calls (matchesApi, jobsApi, profileApi, etc.)
  types.ts                 TypeScript interfaces
  supabase.ts              Supabase client

scripts/migrations/        001–010 SQL migrations (all applied to Supabase)
scripts/backfill_classifications.py  One-time classifier backfill (already run)
data/mcf.duckdb            Local dev database (1.1GB, ~65k jobs)
data/analysis_v2/          Tier model training artifacts (json + png reference)
data/analysis_roles/       Role model training artifacts (json + png reference)
notebooks/experience_clustering_v2.ipynb  Model training notebook
