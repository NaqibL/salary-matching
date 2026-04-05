# Module Index

Quick reference for locating functionality across the codebase.

---

## Backend — API Layer (`src/mcf/api/`)

| Module | File Path | Purpose | Key Exports | Dependencies | Dependents |
|---|---|---|---|---|---|
| FastAPI App | `src/mcf/api/server.py` | Main app, all route handlers, CORS, lifespan | `app` (FastAPI) | `config`, `auth`, `matches_cache`, `response_cache`, `active_jobs_pool_cache`, `matching_service`, all lib modules | CLI, tests, uvicorn |
| Settings | `src/mcf/api/config.py` | Pydantic Settings loaded from env / `.env` | `settings` (Settings) | `pydantic-settings` | Nearly everything |
| Auth | `src/mcf/api/auth.py` | JWT verification, user extraction, FastAPI dependency | `get_current_user`, `verify_token` | `PyJWT`, `settings` | `server.py` |
| Matches Cache | `src/mcf/api/matches_cache.py` | In-memory session cache: `user_id → ranked_job_ids + TTL` | `MatchesCache` | stdlib | `server.py` |
| Response Cache | `src/mcf/api/response_cache.py` | TTL-based cache for dashboard/job list responses | `ResponseCache` | stdlib | `server.py` |
| Active Jobs Pool Cache | `src/mcf/api/active_jobs_pool_cache.py` | Pre-loads all active job embeddings into memory (15min TTL) | `ActiveJobsPoolCache` | `storage`, numpy | `server.py`, `matching_service.py` |
| Matching Service | `src/mcf/api/services/matching_service.py` | Cosine similarity ranking, Rocchio expansion, recency decay | `MatchingService`, `get_matches` | `embedder`, `storage`, numpy, scikit-learn | `server.py` |

---

## Backend — CLI (`src/mcf/cli/`)

| Module | File Path | Purpose | Key Exports | Dependencies | Dependents |
|---|---|---|---|---|---|
| CLI | `src/mcf/cli/cli.py` | Typer CLI: crawl, process-resume, match-jobs, mark-interaction, re-embed | `app` (Typer) | All lib modules, `settings` | `pyproject.toml` entrypoint, `server.py` (webhook) |

---

## Backend — External API Clients (`src/mcf/lib/api/`)

| Module | File Path | Purpose | Key Exports | Dependencies | Dependents |
|---|---|---|---|---|---|
| API Client | `src/mcf/lib/api/client.py` | MCF REST API client + CareersGov (Algolia) client | `MCFClient`, `CareersGovJobSource` | `httpx`, `requests`, `tenacity`, `models` | `mcf_source.py`, `cag_source.py`, `cli.py` |

---

## Backend — Crawler (`src/mcf/lib/crawler/`)

| Module | File Path | Purpose | Key Exports | Dependencies | Dependents |
|---|---|---|---|---|---|
| Crawler | `src/mcf/lib/crawler/crawler.py` | Lists job UUIDs with rate limiting and progress tracking | `Crawler` | `MCFClient`, `tenacity` | `incremental_crawl.py`, `cli.py` |

---

## Backend — Embeddings (`src/mcf/lib/embeddings/`)

| Module | File Path | Purpose | Key Exports | Dependencies | Dependents |
|---|---|---|---|---|---|
| Embedder Protocol | `src/mcf/lib/embeddings/base.py` | `EmbedderProtocol` interface | `EmbedderProtocol` | — | `embedder.py`, `matching_service.py` |
| Embedder | `src/mcf/lib/embeddings/embedder.py` | SentenceTransformers (BGE) wrapper with caching | `Embedder` | `sentence-transformers`, `EmbedderProtocol`, `EmbeddingsCache` | `server.py`, `cli.py`, `matching_service.py` |
| Embeddings Cache | `src/mcf/lib/embeddings/embeddings_cache.py` | LRU + optional DB cache keyed on content hash | `EmbeddingsCache` | `storage`, stdlib | `embedder.py` |
| Resume Parser | `src/mcf/lib/embeddings/resume.py` | PDF/DOCX/TXT/MD extraction, text preprocessing, chunking | `extract_resume_text`, `preprocess_text` | `pypdf`, `python-docx` | `server.py`, `cli.py` |
| Job Text | `src/mcf/lib/embeddings/job_text.py` | Job description text extraction and preprocessing | `extract_job_text` | `lxml`, `BeautifulSoup` | `incremental_crawl.py`, `cli.py` |

---

## Backend — Models (`src/mcf/lib/models/`)

| Module | File Path | Purpose | Key Exports | Dependencies | Dependents |
|---|---|---|---|---|---|
| MCF Models | `src/mcf/lib/models/models.py` | Pydantic models mirroring MCF API response schema | `Job`, `Skill`, `Salary`, `Category`, `Company` | `pydantic` | `client.py`, `server.py`, `storage` |
| Job Detail Models | `src/mcf/lib/models/job_detail.py` | Extended detail models (company info, requirements) | `JobDetail`, `DetailCompany`, `DetailJobStatus` | `pydantic`, `models.py` | `client.py`, `server.py` |

---

## Backend — Sources (`src/mcf/lib/sources/`)

| Module | File Path | Purpose | Key Exports | Dependencies | Dependents |
|---|---|---|---|---|---|
| Source Base | `src/mcf/lib/sources/base.py` | `JobSource` protocol + `NormalizedJob` dataclass | `JobSource`, `NormalizedJob` | — | `mcf_source.py`, `cag_source.py`, `incremental_crawl.py` |
| MCF Source | `src/mcf/lib/sources/mcf_source.py` | MCF job listing implementation | `MCFJobSource` | `client.py`, `base.py` | `incremental_crawl.py`, `cli.py` |
| CAG Source | `src/mcf/lib/sources/cag_source.py` | Careers@Gov (Algolia) implementation | `CareersGovJobSource` | `client.py`, `base.py` | `incremental_crawl.py`, `cli.py` |

---

## Backend — Storage (`src/mcf/lib/storage/`)

| Module | File Path | Purpose | Key Exports | Dependencies | Dependents |
|---|---|---|---|---|---|
| Storage Interface | `src/mcf/lib/storage/base.py` | Abstract base class (~36 methods) for all DB operations | `Storage` | `abc` | Everything that touches data |
| DuckDB Store | `src/mcf/lib/storage/duckdb_store.py` | DuckDB implementation of `Storage` (~2000 lines) | `DuckDBStore` | `duckdb`, `Storage` | `server.py` (when no `DATABASE_URL`) |
| Postgres Store | `src/mcf/lib/storage/postgres_store.py` | PostgreSQL/Supabase implementation of `Storage` | `PostgresStore` | `psycopg2`, `Storage` | `server.py` (when `DATABASE_URL` set) |

---

## Backend — Pipeline (`src/mcf/lib/pipeline/`)

| Module | File Path | Purpose | Key Exports | Dependencies | Dependents |
|---|---|---|---|---|---|
| Incremental Crawl | `src/mcf/lib/pipeline/incremental_crawl.py` | Orchestrates: crawl → normalize → embed → store | `run_incremental_crawl` | `sources`, `embedder`, `storage`, `job_text` | `cli.py`, `server.py` (webhook) |

---

## Backend — Shared (`src/mcf/lib/`)

| Module | File Path | Purpose | Key Exports | Dependencies | Dependents |
|---|---|---|---|---|---|
| Categories | `src/mcf/lib/categories.py` | MCF job category enum | `MCFCategory` | — | `client.py`, `cli.py` |

---

## Frontend — Pages (`frontend/app/`)

| Module | File Path | Purpose | Key Exports | Dependencies | Dependents |
|---|---|---|---|---|---|
| Root Layout | `frontend/app/layout.tsx` | HTML shell, font loading, providers, metadata | default export | `providers.tsx`, `Nav`, `Layout` | All pages |
| Providers | `frontend/app/providers.tsx` | Theme + toast providers wrapper | `Providers` | `next-themes`, `sonner` | `layout.tsx` |
| Home | `frontend/app/page.tsx` | Landing page: feature cards + live job count chart | default export | `api.ts`, `recharts` | — |
| Dashboard | `frontend/app/dashboard/page.tsx` | Public analytics: salary trends, job counts, top employers | default export | `api.ts`, `recharts` | — |
| Matches | `frontend/app/matches/page.tsx` | Resume upload + taste rating matching interface | default export | `ResumeTab`, `TasteTab`, `AuthGate` | — |
| Salary Check | `frontend/app/lowball/page.tsx` | Paste job description to check salary vs market | default export | `api.ts` | — |
| Saved Jobs | `frontend/app/saved/page.tsx` | List of jobs user has saved | default export | `api.ts`, `JobCard` | — |
| Job Detail | `frontend/app/job/[uuid]/page.tsx` | Full job details view | default export | `api.ts`, `types.ts` | — |
| How It Works | `frontend/app/how-it-works/page.tsx` | User-facing documentation page | default export | — | — |
| Admin | `frontend/app/admin/page.tsx` | Cache stats + flush controls (admin only) | default export | `api.ts`, `auth.ts` | — |

---

## Frontend — API Routes (`frontend/app/api/`)

| Module | File Path | Purpose | Key Exports | Dependencies | Dependents |
|---|---|---|---|---|---|
| Matches | `frontend/app/api/matches/route.ts` | Proxy to FastAPI `/api/matches` | `GET`, `POST` | `server-fetch.ts` | `matches/page.tsx` |
| Dashboard Summary | `frontend/app/api/dashboard/*/route.ts` | Dashboard data aggregation from FastAPI | `GET` | `server-fetch.ts` | `dashboard/page.tsx` |
| Lowball | `frontend/app/api/lowball/route.ts` | Proxy to FastAPI `/api/lowball/check` | `POST` | `server-fetch.ts` | `lowball/page.tsx` |
| Webhooks | `frontend/app/api/webhooks/route.ts` | Receives GitHub Actions cron, forwards to Railway | `POST` | `CRON_SECRET` env | GitHub Actions |
| Revalidate | `frontend/app/api/revalidate/route.ts` | Triggers Next.js ISR revalidation after crawl | `POST` | `REVALIDATE_SECRET` | Crawl webhook |

---

## Frontend — Components (`frontend/app/components/`)

| Module | File Path | Purpose | Key Exports | Dependencies | Dependents |
|---|---|---|---|---|---|
| Job Card | `frontend/app/components/JobCard.tsx` | Match card with score badge, salary, company, interaction buttons | `JobCard` | `types.ts`, `api.ts` | `matches/page.tsx`, `saved/page.tsx` |
| Resume Tab | `frontend/app/components/ResumeTab.tsx` | Resume upload form + match results list | `ResumeTab` | `JobCard`, `api.ts`, `SWR` | `matches/page.tsx` |
| Taste Tab | `frontend/app/components/TasteTab.tsx` | Job rating UI + taste match results | `TasteTab` | `JobCard`, `api.ts`, `RatingsQueueProvider` | `matches/page.tsx` |
| Auth Gate | `frontend/app/components/AuthGate.tsx` | Wraps children, shows login prompt if unauthenticated | `AuthGate` | `supabase.ts` | `matches/page.tsx` |
| Profile Provider | `frontend/app/components/ProfileProvider.tsx` | React context for current user profile data | `ProfileProvider`, `useProfileContext` | `supabase.ts`, `api.ts` | `layout.tsx`, multiple pages |
| Ratings Queue | `frontend/app/components/RatingsQueueProvider.tsx` | Batches/debounces job rating API calls | `RatingsQueueProvider`, `useRatingsQueue` | `api.ts`, `useDebouncedRatings` | `TasteTab.tsx` |
| Nav | `frontend/app/components/Nav.tsx` | Top navigation bar | `Nav` | `NavUserActions`, `supabase.ts` | `layout.tsx` |
| Nav User Actions | `frontend/app/components/NavUserActions.tsx` | Auth buttons + user menu in nav | `NavUserActions` | `supabase.ts` | `Nav.tsx` |
| Tutorial Modal | `frontend/app/components/TutorialModal.tsx` | First-time user onboarding overlay | `TutorialModal` | — | `matches/page.tsx` |
| Auth Dashboard Preview | `frontend/app/components/AuthDashboardPreview.tsx` | Teaser shown to unauthenticated users | `AuthDashboardPreview` | — | `matches/page.tsx` |
| Page Transition | `frontend/app/components/PageTransition.tsx` | Fade-in animation wrapper | `PageTransition` | — | Various pages |
| Spinner | `frontend/app/components/Spinner.tsx` | Loading indicator | `Spinner` | — | Multiple |
| Auth Error Boundary | `frontend/app/components/AuthErrorBoundary.tsx` | Catches auth-related render errors | `AuthErrorBoundary` | — | `layout.tsx` |
| Layout | `frontend/app/components/layout/Layout.tsx` | Main page layout (sidebar + content) | `Layout` | `Sidebar`, `MobileNav` | `layout.tsx` |

---

## Frontend — Library (`frontend/lib/`)

| Module | File Path | Purpose | Key Exports | Dependencies | Dependents |
|---|---|---|---|---|---|
| API Client | `frontend/lib/api.ts` | Axios instance + all API call functions grouped by domain | `api`, `jobsApi`, `profileApi`, `dashboardApi`, `adminApi` | `axios`, `supabase.ts`, `types.ts` | All pages and components that fetch data |
| Types | `frontend/lib/types.ts` | TypeScript interfaces for all API data | `Job`, `Match`, `Profile`, `JobDetail`, `InteractionType`, etc. | — | All files that use API data |
| Supabase Client | `frontend/lib/supabase.ts` | Initialises Supabase browser client | `supabase` | `@supabase/supabase-js` | `api.ts`, `AuthGate`, `Nav`, auth pages |
| SWR Config | `frontend/lib/swr-config.ts` | Global SWR fetcher + options | `swrConfig` | `swr`, `api.ts` | `providers.tsx` |
| JWT Verify | `frontend/lib/jwt-verify.ts` | Server-side JWT validation for API routes | `verifyJwt` | `jose` | API route handlers |
| Server Fetch | `frontend/lib/server-fetch.ts` | Authenticated server-side fetch wrapper | `serverFetch` | node fetch, `jwt-verify.ts` | API route handlers |
| Profile Cache | `frontend/lib/profile-cache.ts` | SWR cache key + mutate helpers for user profile | `profileCacheKey`, `mutateProfile` | `swr` | `ProfileProvider`, `ResumeTab` |
| Job Prefetch | `frontend/lib/job-prefetch.ts` | Prefetches job detail on link hover | `prefetchJobDetail` | `api.ts` | `JobCard.tsx` |
| Debounced Ratings | `frontend/lib/useDebouncedRatings.ts` | Custom hook: debounces job ratings before API call | `useDebouncedRatings` | `react` | `RatingsQueueProvider` |
| Utils | `frontend/lib/utils.ts` | `cn()` className helper (clsx + tailwind-merge) | `cn` | `clsx`, `tailwind-merge` | All UI components |
