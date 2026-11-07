# Lowball — Work Summary (April–July 2026)

Chronological record of everything built, shipped, and learned on Lowball (sglowball.vercel.app), technical and non-technical. Source: `git log`, project memory, and planning docs in `.claude/`. Built solo.

**Timeline at a glance:** first commit 2026-04-05 → public launch ~2026-05-31 → Straits Times feature 2026-07-01. ~165 commits over ~3 months.

---

## April 2026 — Prototype and pivot

- **2026-04-05:** Initial commit.
- **2026-04-07:** Product pivot (from an earlier direction to what became the salary/job-matching tool).
- **2026-04-08 to 04-14:** Core build-out — job description ingestion, improved salary search, embedding pipeline fixes, user profile, Supabase auth, WhatsApp/Telegram experiments.
- **2026-04-19 to 04-24:** Data pipeline hardening — daily auto-embedding of unembedded jobs, fixed dashboard chart staleness, prevented transient crawl deactivations from silently deleting embeddings, fixed cross-segment false deactivations, promoted v2 role classifiers (39 reviewed clusters), enabled LLM cleaning in the daily embed workflow.
- **2026-04-20:** Removed credentials accidentally exposed in git history; added `.gitignore` coverage.
- **2026-04-24 to 04-25:** UI iteration on the salary checker — replaced role-category pill grid with a searchable dropdown, replaced collapsible panels with inline job cards, added match-score sorting and expand/collapse on similar-role cards.
- **2026-04-28:** Added an LLM layer (via OpenRouter) for resume parsing.

**Theme:** finding product-market shape. Multiple pivots before settling on "salary checker" as the core hook.

---

## May 2026 — Public launch and hardening

### Product
- **05-10:** Company filter on the salary checker with dual-tab results.
- **05-12:** Upgraded LLM cleaning pass — structured extraction + query-aligned embeddings.
- **05-16:** **Strategic refocus** — simplified the site to center on salary checking as the core feature (matching/resume features demoted to personal-use-only, hidden from nav). Updated `CLAUDE.md` to codify this as product direction.
- **05-17:** Consolidated homepage and `/lowball` into a single experience at `/`. Shipped a **Telegram job digest bot** as a side feature.
- **05-21 to 05-25:** **Companies feature** — browse page, company profile pages (salary range, hiring patterns, skill breakdown), company canonicalization (LLM-assisted dedup of variant company name spellings), exclusion of recruitment agencies from listings.
- **05-25 to 05-26:** Made job detail pages and endpoints publicly accessible (previously gated); removed the Sign In nav link that was funnelling public users into an auth wall; switched salary percentile calculation to use midpoint when both min/max are available.
- **05-29:** Replaced the native `<datalist>` company field with a custom combobox component; cached the company list; filtered low-signal/bloat companies from autocomplete.
- **05-31:** **Public launch.** Rebranded from "SG Salary" to **Lowball**. Added Open Graph meta tags + static OG screenshot for link previews.

### Security / release engineering
- **05-31:** Ran a 4-agent parallel security review before making the repo and site public (`pre-release-checklist.md`). Found and fixed:
  - 6 blockers: exposed DB password in a gitignored file (rotated anyway), missing server-side route guards on owner-only pages, a silent-auth-bypass footgun (`ALLOW_ANONYMOUS_LOCAL` in prod), raw exception text leaking to API clients in two places, no rate limiting on the public salary-check endpoint.
  - 10 warnings and 5 minor issues: open sign-ups on an app with owner-only pages, an unauthenticated CORS-config-disclosure endpoint, debug logging left in, JWT error messages leaking token structure, hardcoded third-party API key fallback, dead duplicate API endpoints, gitignore gaps exposing PII files (resume text, personal job-search notes).
- Removed `axios` (architecture violation — all frontend API calls must go through one client module).

### Product marketing
- Wrote a product-marketing brief (`product-marketing.md`) ahead of launch: positioning against Glassdoor SG (stale, crowdsourced), MOM annual data (too coarse), and LinkedIn Salary (paywalled). Core differentiator: live daily-crawled data + semantic (not keyword) matching, free, Singapore-specific.

**Theme:** this is the month the project went from personal tool to public product — refocus, security hardening, and a real launch.

---

## June 2026 — Reliability crisis, ML investment, and monetization

### Reliability (early June — the hardest technical month)
Public launch immediately surfaced load the local dev setup never exposed. In roughly one week (06-01 to 06-03) the following were diagnosed and fixed, mostly under live production pressure:
- DB connection pool exhaustion — raised pool size twice (30 → 50) to match Supabase Pro's connection limits.
- `hnsw.ef_search` (vector search recall/speed tuning) was being silently dropped by PgBouncer — fixed by wrapping it in `SET LOCAL` inside an explicit transaction (`_transaction_cur` pattern, since reused everywhere a session-scoped setting is needed).
- Rewrote the core HNSW vector query as a subquery to prevent a nested-loop over-scan.
- Binary embedding transfer via the pgvector psycopg2 adapter (`register_vector`) — roughly halved the size and time of loading embeddings, per `scaling-plan.md`'s "quick wins" analysis of a 150k-job, ~550MB in-memory pool.
- Stale-SSL-connection recovery: added a `SELECT 1` probe on every connection checkout, TCP keepalives, and logic to discard (not silently return) unrestorable connections — root-caused a class of intermittent crawl/query failures.
- Thundering-herd guard on cache miss to stop concurrent cold-start requests from causing an OOM.
- `jemalloc` + a response-cache size cap to prevent Railway OOM under load.
- Statement-timeout handling rewritten across ~6 full-table-scan methods so slow legitimate queries don't get killed, while still protecting against runaway queries elsewhere.

### ML / matching quality
- **06-09:** Deployed **v1 of a fine-tuned BGE embedding model** (`NaqibL/bge-base-sgmarket-v1`), trained on 21k+ triplets mined from real SG job listings — replacing the stock `bge-base-en-v1.5` model. Fixed the model's tendency to conflate roles of different seniority under the same title.
  - Eval: 85% pairwise accuracy (170/200), zero ranking inversions — remaining failures were DB coverage gaps, not model errors.
- **06-15:** Deployed **v2** (`NaqibL/bge-base-sgmarket-v2`) — added cross-function hard-negative mining (9,458 confusing pairs mined; ~2,500 actionable) to fix a specific failure mode where the model over-indexed on shared SQL/Python signal and collapsed BI Analyst, Data Analyst, Data Scientist, and ML Engineer into "Data Engineer."
  - Eval: 87.5% pairwise accuracy (+2.5pp over v1). Case study (Shopee BI Analyst): correct-role match score rose from 0.52 to 0.62, and the #1 company match became correct for the first time.
  - Both models pushed publicly to Hugging Face Hub.
- **06-16:** Re-indexed all ~172k job embeddings on v2; added a seniority filter (Intern → Director) to the salary checker that's appended directly to the retrieval query.

### Product / UX polish (informed by direct user feedback)
- **06-02:** Feedback-review session (see `feedback_review_20260602` memory) — four "ship it" items sourced from user feedback plus recruiter insider knowledge on MCF data quality:
  1. Labelled the salary figure explicitly as "Monthly base salary (SGD)" — users didn't know the unit.
  2. Added a recruiter-sourced caveat: posted ranges often run 10–20% above what's actually offered.
  3. Fixed a mobile bug where expanded job descriptions rendered as an unstyled wall of text.
  4. Filtered EP-non-compliant salary ranges (max > 2× min) from the benchmark pool and switched the headline figure to the midpoint of compliant ranges — validated against real MBB (top consulting firm) postings by a recruiter contact.
- **06-02:** Fixed a genuine memory leak — Railway RSS was creeping from ~18GB to ~25GB over a day because cache entries with long TTLs were only evicted on access, not on a schedule. Added a background sweep thread.
- Rewrote README with a proper changelog and stack overview.

### Monetization
- **06-30:** Shipped `/support` — a donation page (Ko-fi + PayNow), then iterated on it extensively the same day (14+ commits: copy, layout, card design, logo sizing) to get from "functional" to something that read as personal and non-corporate rather than a generic donate button. Promoted to a nav tab.

**Theme:** the month the product got tested by real traffic (reliability), got smarter (ML fine-tuning), and got a funding mechanism.

---

## July 2026 — Straits Times feature and post-launch scaling

- **2026-07-01:** **Featured in The Straits Times** — *"Think you've been 'lowballed'? This NUS grad built a tool that lets you compare salary offers,"* by Sherlyn Sim. Covered the founder story (9-month, ~300-application job search post-NUS; a $3,500/mo offer vs. a $5,000 median) alongside expert commentary from Mercuri Urval and Ethos BeathChapman on why SG salary offers have been trending low. Article cites the tool as indexing 200,000+ job postings.
- **2026-07-01 (same day, shipped ahead of the article going live):** **Hot Jobs** (`/hot-jobs`) — a new page surfacing roles paying meaningfully above the median for their peer group, refreshed daily. Built a *separate* clustering system (`hot_jobs_cluster`, k=23 MiniBatchKMeans) rather than reusing the pre-existing 34-cluster matching taxonomy, after determining the two serve incompatible purposes. Added data-quality guardrails after live testing surfaced absurd outliers (e.g. a $215k Quant Trader compared against a $4,800 peer-group median producing a nonsensical +4379% figure) — a salary floor on valid baseline clusters, and a display cap on the "% above market" figure.
- **2026-07-01 (same session):** Infra push alongside the feature — diagnosed a Supabase CPU-starvation issue (instance pinned at 99.96% CPU, even no-op `SET` commands taking 30+ seconds) that had been initially misdiagnosed as a missing-index problem; upgraded Supabase compute tier (Micro → Small); found and dropped an accidental duplicate 770MB HNSW index created during an earlier incident; added company-lookup indexes.
- **2026-07-03:** Fixed hot-jobs scoring to run as a catch-up pass post-crawl; added contact links to the support page.
- **2026-07-05:** Redesigned the support page again and re-added it to the nav.
- **2026-07-07:** Switched to CPU-only PyTorch build (was pulling in an unneeded CUDA build, bloating the deploy).
- **2026-07-09:** Made the daily crawl resilient to a single bad job-detail fetch — previously one flaky upstream request could abort the entire incremental crawl run.
- **Post-press:** wrote a LinkedIn follow-up post (`.claude/plans/linkedin-st-followup.md`) summarizing improvements shipped since the article: Hot Jobs, the fine-tuned matching model (trained on 240k+ real SG listings), and general UX polish — thanking the journalist and acknowledging both positive and critical reader feedback as an input to the roadmap.

**Theme:** press validation, plus proof the product could keep shipping and self-correcting (guardrails caught by testing, not by the plan) under public scrutiny.

---

## Non-technical work threaded throughout

- **Product strategy:** the 05-16 refocus (cutting scope to the salary checker as the single core surface) was a deliberate product decision, not just a code change — documented in `CLAUDE.md` as the standing product direction.
- **Positioning/marketing:** wrote and maintained a product-marketing brief covering target personas (fresh grad, mid-career switcher, technical job seeker), competitive differentiation, and brand voice ("direct, data-driven, no fluff... built by a dev for job seekers, not a VC-backed HR platform").
- **Security/trust:** ran a structured pre-release security review before going public and worked through it to zero blockers.
- **Press/PR:** was interviewed by The Straits Times, gave direct quotes about the personal motivation and the mission of transparent salary data in a culture where discussing salary is taboo. Wrote a public LinkedIn follow-up after the article to sustain the moment and channel feedback into the roadmap.
- **Community/support infrastructure:** built and iterated on a donation page to make the project sustainable, choosing tone and copy carefully to keep it personal rather than corporate.
- **Fundraising/cost management:** `scaling-plan.md` and the DB performance work reflect a recurring discipline of keeping a side project running on ~$5/month (Railway) despite real production traffic — repeatedly choosing the cheapest fix that actually solves the root cause (e.g. compute-tier upgrade only after confirming CPU starvation, not reflexively over-provisioning).

---

## Numbers worth citing

| Metric | Value | Source |
|---|---|---|
| Jobs indexed | 250,000+ | Straits Times article |
| Active listings at any time | ~60,000–70,000 | README |
| Fine-tuned model training data | 240k+ real SG listings (v1+v2 triplets ~27k derived from these) | LinkedIn follow-up post, finetune memory |
| Matching model accuracy | 85% → 87.5% (v1 → v2) | eval memory |
| Memory leak fixed | Railway RSS 18GB → 25GB/day creep eliminated | changelog |
| Monthly infra cost | ~$5/month (Railway Hobby; Supabase/Vercel/GH Actions free tier, later Supabase compute upgrade) | README, db-performance memory |
| Time to press feature | ~3 months from first commit to Straits Times | git log |
| Commits | ~165 | git log |
| Edge requests served | **1.71M+** (as of 2026-07-10, since public launch ~2026-05-31, ~6 weeks) | Vercel dashboard (user-reported) |
| Estimated visits (derived) | ~40,000–115,000, midpoint ~65,000 — **rough estimate only**, see caveat below | Derived from edge requests / assumed 15–40 requests-per-visit |

**On the traffic numbers:** Railway's log/metric retention turned out to be effectively real-time-only (~13 hours visible via CLI, current deployment only ~27h old at time of check) — it could not answer historical usage or confirm the Straits Times-day spike. In the ~13h window it could see, the API was running steady-state at ~10 calls/hour to the salary-check endpoint (0% errors, 2.6–5.9s latency).

**Resume-safe framing:** cite the raw edge-request figure directly rather than the derived visit estimate — *"Served 1.7M+ requests within ~6 weeks of public launch, including a traffic surge from national press coverage (The Straits Times)"* is verifiable; the visit estimate is a rough conversion (doesn't account for bot/crawler traffic, link-preview fetches from social shares, or per-session asset caching) and could be off 2x in either direction.

**Still missing:** a precise unique-visitor count. If wanted later, either enable Vercel Web Analytics (visitor-level tracking, free up to 2,500 events/mo on Hobby) or add first-party request logging on the backend (a `check_log` table) — neither can recover historical data, only track going forward.
