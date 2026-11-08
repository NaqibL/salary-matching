# Dashboard + Companies v3 — information design

**Date:** 2026-11-08 · **Scope:** `/dashboard`, `/companies`, `/company/[name]` · **Status:** design, not code
**Numbers:** brief figures as of 8 Nov 2026; the live page showed 70,011 live / 20,754 new this week at review time.

## Summary (five decisions)

1. **One scroll, no tabs.** Four sections in the order a job seeker asks the questions: This week → Job types → Skills → Posted before. The time-range switch leaves the header and lives inside the one chart that uses it.
2. **Summary strip goes to six tiles with week-over-week deltas**: live ads, new this week, closed this week, median advertised monthly base, share posted before, share from agencies. Pipeline counts stay on admin.
3. **A sortable "Job types" table replaces five charts** (MCF category + drilldown, employment type, position level, salary histogram, role-family bar): 24 rows × live ads, median pay, 4-week change, share posted before. It answers three of the four 10-second questions on one screen.
4. **A "Posted before" section replaces the 20-row reposts table**: three fact tiles, share-by-job-type bar, times-posted histogram, direct-vs-agency bar. No ad text and no company is named on the dashboard.
5. **Companies: a three-way segmented control (Employers · Recruitment agencies · All, default Employers)** replaces the checkbox; the table gains a "Posted before" column and the openings floor becomes job-type-scoped when a job type is chosen.

Cut outright: active-jobs area chart, skills trend, MCF-category chart and drilldown, employment-type pie, position-level bar, salary histogram, dashboard reposts table, profile position-level and employment-type mini charts.

---

## 1. Dashboard

### Why one scroll and not tabs

The owner floated "another tab" (complaint 3). Recommendation: no tabs. (a) The four questions are read in sequence, and tabs would hide the answer unique to Lowball — how much of the market is repeats. (b) Tabs plus a global time-range switch keep today's ambiguity, where the switch silently affects only some charts (complaint 5). (c) At 390 px a tab bar costs a line and gains nothing over a chip row of anchors. Instead: a sticky anchor row under the header (`This week · Job types · Skills · Posted before`), horizontally scrollable on phones.

**Time-range switch:** removed from the header (complaint 5). It becomes a `30d · 90d · 365d` control inside the "Ads added and removed" card only, default 90d. Every other number is fixed-scope and says so.

### Section A — "This week" (summary strip + one chart)

**Summary strip: six tiles**, 2 × 3 on phones, 6 × 1 from `lg`. Answers complaint 2 with numbers a visitor can use rather than pipeline counts. Deltas are plain text under the value; no green/red (more ads is not "good").

| # | Value | Label | Sublabel (scope words) | Source |
|---|---|---|---|---|
| 1 | 68,211 | Live ads | "open today · +1,200 vs 7 days ago" | `active_jobs_over_time` (already fetched): today minus the point 7 days back |
| 2 | 20,754 | New this week | "first seen in the last 7 days · 21,300 the week before" | `new_this_week` (exists) + new `new_prev_week` |
| 3 | 24,950 | Closed this week | "taken down in the last 7 days · a closed ad was up 29 days on median" | new: `count(*)` where `is_active = false and last_seen_at >= now - 7d`; median from D3 |
| 4 | $4,000 | Median advertised monthly base | "live ads with a compliant range · SGD" | totals row of the job-types aggregate (§1B) |
| 5 | 37% | Posted before | "25,167 live ads repeat an earlier ad text" | totals row: `live_reposts / live` |
| 6 | 34% | From recruitment agencies | "of live ads · SSIC 78 registration" | totals row: `live_agency / live` |

Dropped tiles: "Companies hiring" moves to the Companies page header, where it is the subject; "Postings tracked since Mar 2026" becomes the page subtitle: *"Every MyCareersFuture and Careers@Gov ad since Mar 2026 — 716,225 tracked, 68,211 live. Updated daily."* (hygiene: it is context, not a metric).

**Chart A1 — Ads added and removed.** Form: paired daily bars (exists). Fields: `added_count`, `removed_count` per day. Sort: by date. Colour: `--viz-1` added, `--viz-8` removed (unchanged). Headline: "Ads added and removed per day". Sublabel: "last {30|90|365} days · one bar per day". Legend kept (two series). Local range control as above.

**Cut: "Total active jobs" area chart.** A near-flat 68–70k line; the live tile's 7-day delta carries the information (complaint 5).

**Mobile (390 px), first viewport:** page title + subtitle, then tiles 1–4 (two rows of two). Tiles 5–6 and chart A1 arrive on the first scroll. Nothing else above the fold.

### Section B — "Job types" (the new centrepiece)

**Form: ranked table with inline bars.** One table; the bar sits inside the "Live ads" column, so there is one axis. 24 Jev families; `other` is shown last, greyed, never sorted into the top.

| Column | Field | Rendering |
|---|---|---|
| Job type | `role_family` display name | text; row links to `/companies?family=…` |
| Live ads | `live` | number + inline bar (`--viz-1`, width ∝ live) |
| Median advertised monthly base | `median_salary` | "$8,250"; "—" when `salary_n < 30` |
| 4-week change | `(new_28d − new_prev_28d) / new_prev_28d` | "+12%" / "−8%" in text colour; "—" when `new_prev_28d < 50` |
| Posted before | `live_reposts / live` | "21%" |
| From agencies | `live_agency / live` | "50%"; hidden below `md` |

Default sort: live ads desc; any header sorts; sort is URL state (`?sort=`). Colour rule: one colour for the bar, no per-family hues — 24 hues carry no meaning (the "no rainbow" rule). Headline: "Job types". Sublabel: "Live ads, pay and how fast each type is being posted · pay is the median advertised monthly base, SGD · change compares new ads in the last 4 weeks with the 4 weeks before". Tooltip "Posted before": "Live ads whose exact text was posted earlier, under any company name". Tooltip "4-week change": "Ads first seen in the last 28 days vs the previous 28 days".

Why it earns its place: it answers "what does my kind of job pay", "which job types are growing or shrinking" and "how much is repeats" at one glance — the informativeness complaint 2 asks for. It replaces "Active jobs by role family" (counts without pay or change), "Jobs by category (MCF industry)" and its drilldown (a second taxonomy for the same question — hygiene), the employment-type pie, the position-level bar and the salary histogram (none answers a brief question; the checker does distributions properly).

**Keep "Pay by seniority"** as a compact 8-row table beside (desktop) or under (phone) the job-types table. Form: table. Fields: level, live ads, median advertised monthly base (existing seniority endpoint). Sort: fixed ladder Intern → Director. Headline: "Pay by seniority". Sublabel: "live ads whose description states a level · median advertised monthly base, SGD". Drops today's two-axis chart (one axis per chart — hygiene).

**Backend ask (one aggregate, 1 h cache, <2 s):** `GROUP BY role_family` over live jobs (`is_active`) left-joined to `posting_groups` on `content_hash` and to `company_stats` on `company_key`: `live = count(*)`; `median_salary = percentile_cont(0.5)` of `salary_mid` where the range is compliant; `salary_n`; `live_reposts = count where repost_count >= 2`; `live_agency = count where is_agency`; `live_multi_company = count where distinct_companies >= 2`. Plus, over all jobs regardless of `is_active` (uses `idx_jobs_posted_or_seen_date`): `new_28d = count where first_seen_at >= now - 28d`; `new_prev_28d = count where first_seen_at in [now - 56d, now - 28d)`. Return a totals row; tiles 4–6 and §2 read from it.

**Mobile (390 px):** list rows — name on line 1; "3,200 live · $8,250 · +12% · 21% posted before" on line 2; the inline bar spans the row. Sort via a small select above the list.

### Section C — "Skills"

**Keep "Most requested skills"**, reduced to the top 10, with the existing job-type select; preselect the family when the visitor arrives from a job-types row (`?family=`). Form: horizontal bar, `--viz-1`, sorted desc. Headline: "Most requested skills". Sublabel: "live ads that name the skill · {job type or 'all job types'} · extracted from the ad text". It stays because it is the one chart a job seeker acts on. Hygiene: the "all types" default shows "Customer Service, Microsoft Office"; copy under the select reads "Pick a job type for a useful list".

**Cut "Skills trend"** (complaint 4): twelve weeks of eight generic skills is flat lines with nothing to act on.

### Section D — "Posted before"

See §2. Last because it is the "how much is noise" answer and the most editorial.

### Final section list

1. This week — six tiles + added/removed chart (local range switch)
2. Job types — ranked table + pay by seniority
3. Skills — top-10 bar with job-type select
4. Posted before — three tiles + three charts (§2)

Footer line (hygiene): "Source: every MyCareersFuture and Careers@Gov ad since Mar 2026, updated daily. Salary figures are the median advertised monthly base of ads with a compliant range. 'Posted before' means the exact ad text was posted earlier, under any company name. 'Recruitment agency' is a registration fact (SSIC 78)."

---

## 2. "Posted before" view (replaces "Ads posted again and again")

Name: **"Posted before"** — plain, a fact, no judgement. Not "Reposts" (jargon), never "Spam".

The 20-row table fails because the top of the distribution is one restaurant template and one recruiter's twelve title variants (complaint 3); any ranking of individual ad texts will surface them. The insight is in shares and distributions. Six facts, in order:

| # | Fact | Form | Fields / aggregate | Copy |
|---|---|---|---|---|
| D1 | 37% of live ads repeat an earlier text | tile | totals row: `live_reposts / live` | value "37%" · label "Live ads posted before" · sublabel "25,167 of 68,211 live ads · same text posted earlier" |
| D2 | 5% appear under 2+ company names | tile | totals row: `live_multi_company / live` | value "5%" · label "Same ad, several company names" · sublabel "3,683 live ads · 1,687 distinct texts" |
| D3 | A closed ad stayed up 29 days | tile | `percentile_cont(0.5)` of `(last_seen_at − first_seen_at)` over jobs with `is_active = false and last_seen_at >= now - 30d` | value "29 days" · label "How long an ad stays up" · sublabel "median · ads closed in the last 30 days" |
| D4 | Repeats concentrate in F&B, construction, retail; least in data, banking, IT infra | horizontal bar, 24 rows | §1B aggregate: `live_reposts / live` per family; sort desc; `other` last | headline "Share of live ads posted before, by job type" · sublabel "live ads · dotted line = all job types, 37%" · bar `--viz-1`, reference line in text colour labelled "all types 37%" · tooltip "5,900 of 11,800 live F&B ads" |
| D5 | Most texts are posted once; 3k texts are posted 11+ times | vertical bar, 5 buckets | `GROUP BY bucket(repost_count)` over `posting_groups where active_count > 0`, buckets 1 / 2 / 3–5 / 6–10 / 11+; `texts = count(*)`, `live_ads = sum(active_count)` | headline "How many times the same ad text has been posted" · sublabel "ad texts with a live copy · the 3,000 texts posted 11+ times account for 4,462 live ads" · bar `--viz-1`, value labels on bars (42.5k · 8.3k · 7.5k · 3.1k · 3.0k) |
| D6 | Direct employers and agencies repeat at the same rate | horizontal bar, 2 rows | `GROUP BY is_agency` over live jobs joined to `posting_groups` and `company_stats`: `live`, `live_reposts` | headline "Posted before, by who placed the ad" · rows "Direct employers 37.5%", "Recruitment agencies 35.7%" · sublabel "share of each group's live ads · agency = SSIC 78 registration" · both bars `--viz-1` (same measure, no contrast colour) |

Layout: D1–D3 in one row (1 + 2 on phones), D4 full width, D5 and D6 side by side (stacked on phones). No ad title, no company name, no "spam"/"template"/"recruiter" wording. Closing line: "See any company's own repeats on its profile (Repeat postings)". Complaint 1 ("do we care about recruitment companies") is answered here with data rather than a toggle: D6 shows reposting is market-wide.

**The 20-row table** is removed from the dashboard; the endpoint stays for the profile's "Repeat postings" list, the right scope for named rows.

**Mobile (390 px):** D1–D3 tiles, then D4 as a 24-row list with a thin bar each, then D5 and D6.

---

## 3. Companies page

### What the live page actually shows

With agencies hidden, the default list is led by high-volume direct-sales and outsourcing firms that post the same text under several names (the fact line "some ads also appear under other company names" sits on 25 of the top 100). Hiding SSIC-78 companies does not produce the list the owner expected, which is why the checkbox felt unsatisfying (complaint 1). The fix is partly the control and partly the columns.

### Agencies: segmented control, default Employers

Replace the checkbox with a three-way segmented control under the title, before the search box: **Employers · Recruitment agencies · All**, default **Employers**. (a) A segment is seen at a glance where the checkbox was not noticed (complaint 1); (b) agencies become a first-class view — 301 of 1,002 companies with 10+ openings and 34% of ads is too much of the market to only hide; (c) the wording implies no judgement.

Summary strip under the control, always naming both halves. Employers: *"676 employers · 15,493 openings · 296 recruitment agencies in the 'Recruitment agencies' view"*. Agencies: *"296 recruitment agencies · N openings · SSIC 78 registration"*. All: *"972 companies · N openings · 296 are recruitment agencies"*. Tooltip: the agency definition from §4.

Name search ignores the segment (searches everyone) as today; the control is disabled while a query is typed.

### Table changes

| Column | Change | Why |
|---|---|---|
| Company | keep, with fact lines | content rule: facts |
| Openings | keep; sublabel "N distinct ads" when `distinct_postings < active_count` | gives the owner's instinct a number without a label (complaint 1) |
| Hires mainly | keep | — |
| **Posted before** (new) | `reposted_count / active_count` as "%"; "—" under 5 openings; sortable both ways; tooltip as in §4 | the honest proxy for "do I care about this poster" — a fact, not a tag |
| Median advertised monthly base · {job type} | keep when a job type is chosen; renamed from "Median advertised salary" | content rule: salary wording |

Default sort stays Openings desc; sort is URL state; row click → profile. Hygiene fix: when a job type is chosen, the "10+ / 3+ / any openings" floor applies to that job type's openings, not company-wide (today the Data & AI view lists companies with one data opening under "10+ openings").

Filters: keep search, job type, industry, minimum openings. On phones the three selects collapse behind a "Filters (2)" button; search and the segmented control stay visible.

**Mobile (390 px), first viewport:** title + subtitle, segmented control, search, strip line, the first two company cards. Card line 2 becomes "Hires mainly · 21% posted before" (+ "median $X/mo" when a job type is chosen).

### Profile page

- Tile 2 label → "Median advertised monthly base"; sublabel "across all live roles · N ads" (content rule). Still hidden for agencies with the existing sublabel.
- Tile 4 "Reposted ads" → label "Posted before", value "1 in 26", sublabel "of live ads · typical company 1 in 3".
- Move "What they hire for" above "Latest openings" (the mix is the summary, the list is the detail).
- Cut the "Position levels" and "Employment types" mini charts (hygiene: MCF fields that answer no question and duplicate the openings list's chips).
- "Repeat postings" list stays: named rows are appropriate at company scope.

---

## 4. Copy sheet

Titles, sublabels and tooltips are given per element above; this is the shared vocabulary.

- Salary, always **"Median advertised monthly base"**; sublabel ends "SGD" or "/mo"; scope "live ads with a compliant range".
- Repeats, always **"Posted before"**; tooltip "Live ads whose exact text was posted earlier, under any company name".
- Agencies, always **"Recruitment agency"**; tooltip "Registered under SSIC 78 (employment agencies), or a recruitment-style name confirmed by its registration".
- Time scopes, always explicit: "open today", "first seen in the last 7 days", "taken down in the last 7 days", "last 4 weeks vs the 4 weeks before", "last 12 months", "since Mar 2026".
- Change: "+12% vs the 4 weeks before"; header "4-week change", never "growing"/"declining". Deltas in text colour, no green/red.
- Small samples: "—" with the threshold in the tooltip ("fewer than 30 ads with a compliant range").
- Banned words: spam, suspicious, fake, template, recruiter-driven, flooding.

---

## 5. Do not build

- Dashboard tabs or a separate `/reposts` route.
- Any ranked list of most-reposted ad texts or companies on the dashboard — it will always be one template ad.
- A "mostly reposts" / "high-volume poster" tag on companies — the column is the fact; a tag is a judgement.
- Per-family colours on 24-row charts.
- MCF categories on the dashboard — role families only; MCF industry stays a filter on Companies.
- A skills-over-time line in any form.
- Per-request queries over `jobs` outside the aggregates above.
- Deltas on anything except tiles 1–2 (deltas on shares are noise at a weekly cadence).

---

## 6. Ordered build list

| # | Item | Effort | Depends on |
|---|---|---|---|
| 1 | **Cuts + header**: remove active-jobs area chart, MCF-category chart and drilldown, employment pie, position bar, salary histogram, skills trend, dashboard reposts table; move the range switch into the added/removed card; add the anchor row; subtitle with the tracked count | S | — |
| 2 | **Job-types aggregate** endpoint (`GET /api/dashboard/job-types`, 1 h cache): the GROUP BY in §1B with a totals row, plus the D5 buckets and D6 split in the same response | M | — |
| 3 | **Job types table** (sortable, inline bar, row links, mobile list) + "Pay by seniority" as a table | L | 2 |
| 4 | **Summary strip v3**: six tiles with deltas; new aggregates `new_prev_week`, `closed_7d`, `median_days_up_30d`; tiles 4–6 from (2) | M | 2 |
| 5 | **Posted before section**: tiles D1–D3, bars D4–D6 | M | 2, 4 |
| 6 | **Companies segmented control** replacing the checkbox; strip copy; URL param `who=employers|agencies|all`; job-type-scoped openings floor | M | — |
| 7 | **Companies "Posted before" column** + "N distinct ads" sublabel + sort | S | 6 |
| 8 | **Profile cleanups**: labels, section order, drop two mini charts | S | — |
| 9 | **Skills**: top 10, family preselect from `?family=`, helper copy | S | 3 |
| 10 | Copy sweep against §4 across all three pages; bump the checker "what's new" banner key | S | all |

Ship 1 → 2 → 3 first: after those three the dashboard already answers all four 10-second questions.
