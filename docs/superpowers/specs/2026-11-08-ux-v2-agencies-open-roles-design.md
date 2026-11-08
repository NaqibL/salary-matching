# UX v2 — open roles first, recruitment-agency labelling, simpler companies and dashboard

**Date:** 2026-11-08 · **Tickets:** SGSAL-027 (checker), SGSAL-028 (companies registry + UX) ·
**Supersedes parts of:** `2026-11-08-companies-page-rework-design.md` (shipped same day)

## Why

Two independent reviews of the shipped companies rework (a product-manager agent and a job-seeker
agent that used the live site) agreed on the same things:

1. The Salary Checker's similar-roles cards are almost all closed postings. Verified on the live
   API: a Data Analyst check returned 20 cards, all inactive, last seen Apr–Aug 2026, while 453
   companies have open data roles. Cause: the checker ranks all 665k historical postings by
   similarity and shows the top 20; history outnumbers live ads ten to one. Design gap, not a bug.
2. Nobody can tell which companies are recruitment agencies. 12 of the 20 companies on the job
   seeker's cards were agencies. The shipped heuristic (10+ role families or an agency-like name)
   is wrong both ways: it flags NUS, NTU, A*STAR and Micron; keyword rules would flag A*STAR,
   MOM, e2i and TalentCorp.
3. MyCareersFuture publishes every posting company's government SSIC code in the job detail the
   crawler already fetches (`postedCompany.ssicCode2020`); employment agencies are SSIC 78xxx.
   The crawler parses and discards it.
4. Per-company repost rate and the role-mix bar are not glanceable; "20×" chips need a click to
   understand; the dashboard's pipeline counts read as "someone's homework".

## Decisions (owner delegated, 2026-11-08)

- **Open roles first** on the checker cards; the percentile pool stays historical.
- **"Recruitment agency" tag only from SSIC 78.** Never from name keywords. Companies without a
  row (CAG/government, or not yet backfilled) are never tagged. Untagged companies that post
  across 12+ role families get a plain fact line "posts across N job types", not a label.
- **"Mostly reposts" is not a public tag.** Repost facts appear on the profile with context.
- **Salary numbers are scope-explicit.** In the companies table a salary column appears only when
  a role family is chosen and is that family's median. On the profile the company-wide median is
  shown only for non-agencies, labelled "across all roles".
- **Agencies hidden by default** on the companies table, with a count and a switch.
- Copy: "Recruitment agency", "Hires mainly", "Median advertised salary", "Repeat postings",
  "Posted 20 times since Mar 2026", "Same ad under 3 company names", "Also posted directly by X",
  "Postings tracked since Mar 2026".
- Parked (separate tickets): merging identical agency ads into one checker card; a job-type
  filter on Hot Jobs.

## SGSAL-027 — checker shows open roles first

`POST /api/lowball/check` (`src/mcf/api/routes/lowball.py`, `check_lowball`):

- Keep `ranked = get_all_embedded_job_ids_ranked(vector, limit=500)` and the percentile pool as
  today (top `top_k*5` with compliant ranges).
- Fetch representative rows for **all 500** hits, dedup, sort by score. Split into `open`
  (`is_active` or `active_count > 0`) and `closed`. Cards = `open[:top_k]` then `closed` to fill
  up to `top_k`. Response adds `open_matched: int` (open postings among the 500 nearest) and
  keeps `total_matched`, `salary_coverage`, `total_listings`.
- Frontend (`LowballContent.tsx`): cards headline becomes "{n} closest ads · {open} open now ·
  {listings} listings including reposts"; the "N similar roles" benchmark line says
  "based on {salary_coverage} ads posted since Mar 2026". Match badge reads "{pct}% match" with
  tooltip "How closely this ad matches your description".

## SGSAL-028 — companies registry and UX v2

### Data

**`companies` table (migration 025):** `company_key TEXT PK` (= `lower(name)` of the posting
company as MCF/CAG reports it), `name`, `uen`, `ssic_code`, `ssic_code_2020`, `ssic_description`,
`employee_count INT`, `source TEXT` ('mcf'|'cag'), `fetched_at TIMESTAMPTZ`. Index on `uen`.

**Crawler:** `NormalizedJob` gains `company_uen`, `company_ssic_code`, `company_ssic_code_2020`,
`company_ssic_description`, `company_employee_count` (all optional). `mcf_source` fills them from
`postedCompany`. `incremental_crawl` calls `store.upsert_company(...)` after
`upsert_new_job_detail` whenever `company_name` is set (CAG rows get `source='cag'`, no SSIC).

**Backfill:** `scripts/backfill_companies.py` — for every `lower(company_name)` with an active
MCF job and no `companies` row, fetch one job detail from MCF (4 req/s, resumable, `--limit`,
`--min-active`), upsert. ≈14.7k companies ≈ 1 h. Then `REFRESH MATERIALIZED VIEW CONCURRENTLY
company_stats`.

**`company_stats` v2 (migration 026, drop + recreate):** per job, join `companies c ON
c.company_key = lower(j.company_name)`; aggregate `ssic_code_2020 = mode()`, `ssic_description =
mode()`, `is_agency = bool_or(c.ssic_code_2020 LIKE '78%' OR (c.ssic_code_2020 IS NULL AND
c.ssic_code LIKE '78%'))`, `top_family_share = top family count / active_count`,
`family_medians jsonb {family: median_salary}` and `family_salary_n jsonb {family: n}` over active
jobs with a salary. `likely_agency` is removed. Everything else unchanged.

**Storage:** `get_company_stats(... agency=...)` filters on `is_agency`; with `family` set, rows
carry `family_median_salary` and `family_salary_sample` from the jsonb. New
`get_agency_company_keys() -> set[str]` (lower names with SSIC 78), `get_posting_group_companies(
canonical_uuids) -> dict[str, list[str]]` (distinct companies from `posting_groups.occurrences`),
`get_company_benchmarks() -> {median_repost_rate}` over companies with 10+ openings,
`upsert_company(...)`, `get_companies_missing_registry(limit) -> [(name, sample_job_uuid)]`.
`get_dashboard_summary` adds `companies_hiring` (count of `company_stats`) and `new_this_week`
(`jobs.first_seen_at >= now() - interval '7 days'`).

### Checker cards (lowball route + `LowballContent.tsx`, `RepostBadge.tsx`, `lib/repost.ts`)

Each similar job gains `is_agency: bool` (company in the agency set) and `direct_employer:
str | null` (for groups with `distinct_companies >= 2`, the first occurrence company that is not
an agency and differs from the card's company). Chips, in this order: "Recruitment agency" (slate,
tooltip "Registered as an employment agency (SSIC 78). Posts roles on behalf of other
employers."), the repost sentence chip (click expands history): "Same ad under N company names"
when N ≥ 2, else "Posted N times this year" when `reposts_365d >= 6`, else "Posted N times since
Mon YYYY"; and "Also posted directly by X" (emerald) when `direct_employer` is set.

### Companies page (`/companies`)

Columns: Company (agency tag; fact line "posts across N job types" when untagged and
`family_count >= 12`), Openings (family openings when a family is selected), Hires mainly
("Healthcare (62%)" from `top_family` + `top_family_share`; agencies: "Mixed · N job types"), and
— only when a family is selected — "Median for {family}" from `family_median_salary` (shown when
`family_salary_sample >= 3`, with "n ads" sublabel). Filters: search, role family, industry, "Show
recruitment agencies" switch (off by default; URL `agencies=show`), minimum openings (10+ / 3+ /
any). Summary strip: "N companies · M openings · K agencies hidden". `RoleMixBar` deleted. Mobile
cards mirror the columns.

### Company profile (`/company/[name]`)

Title row gets the agency tag. Subtitle: "{ssic_description | 'Employer'} · N open roles ·
tracked since Mon YYYY". Tiles: Open roles; Median advertised salary (non-agencies only, sublabel
"across all roles · n ads"); Experience asked; Reposted ads "1 in 4" (sublabel "typical company:
2 in 5", from `benchmarks.median_repost_rate`). "Repeat postings" card: first line "N of their ads
also appear under other company names" when `multi_company_count > 0`, then "X of Y live ads were
posted before · Y listings, Z distinct ads" when they differ, then the list with rows "Posted N
times, Mon to Mon YYYY" and "under K company names". Industries chart removed; "What they hire
for" bars stay; position-level / employment-type charts stay.

### Dashboard and admin

Public summary tiles: Live jobs, New this week, Companies hiring, Postings tracked since Mar 2026
(value `jobs_seen_total`, sublabel "incl. closed"). The searchable / inactive / backlog / backfill
tiles move to `/admin` as a "Pipeline health" panel (same summary endpoint). Most-reposted table:
header "Ads posted again and again · last 12 months", column "Times posted".

## Error handling

- Missing `companies` row → never an agency, no fact line change; profile subtitle falls back to
  "Employer".
- `direct_employer` lookup failure → `null`, chips omitted; never fails the check.
- Backfill: per-company fetch errors are logged and skipped; the script is idempotent.

## Testing

- Smoke: `/api/lowball/check` returns `open_matched`, and the first card is active whenever
  `open_matched > 0`; `/api/companies/stats` rows carry `is_agency`, and with `family` set carry
  `family_median_salary`; `/api/companies/{name}/profile` carries `benchmarks.median_repost_rate`;
  summary carries `companies_hiring` and `new_this_week`.
- Migration tests: `_COMPANY_STATS_VIEW_SQL` == migration 026 text; `companies` DDL constant ==
  migration 025 text.
- `tests/test_repost_copy.ts`-style check is not available (no JS test runner); `tsc --noEmit`.
- Agent checks: code-review agent on the branch diff before merge; job-seeker agent re-tests
  production after deploy with the same tasks as the first review; findings fixed before closing.

## Rollout

Migration 025 + backfill first (background, ~1 h), then migration 026, then code deploy. The
checker fix (SGSAL-027) has no data dependency and ships in the same push.
