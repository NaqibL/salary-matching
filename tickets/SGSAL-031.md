---
id: SGSAL-031
project: salary-matching
title: Dashboard + Companies v4 — owner still not happy with v3; find out what is missing before redesigning
status: todo
priority: high
type: feature
labels: [frontend, product, dataviz, needs-owner-input]
created: 2026-11-08
updated: 2026-11-08
depends_on: [SGSAL-030]
blocks: []
---

## Summary

After SGSAL-030 shipped (dashboard one-scroll with six tiles, job-types table, "Posted before"
section; companies page with the "Direct employers · Recruitment agencies · All" control), the
owner's verdict on 2026-11-08 was: "i still dont really like it, but let's save it as a ticket for
next time." No specifics were given, so the first step of this ticket is a short conversation, not
code.

## What the owner said across the day (verbatim where possible)

- "the dashboard looks less informative now, with the summary showing less information" (about
  SGSAL-028; v3 added six tiles and the job-types table in response, and the owner still does not
  like the result).
- "the ads posted again and again, show very similar roles ... make another tab for this, or
  something, for better analytics" (v3 answered with the "Posted before" section: shares and
  distributions, no named rows, no tab).
- "dont think the skills trend is very useful" (cut in v3; the top-10 skills list stayed).
- "do we really care about the recruitment companies? maybe a way to toggle them off" (v3 made
  direct employers the default view with a segmented control).
- "be more intentional with the design."

## Questions to ask the owner first (pick answers before any design work)

1. Which page is the problem: the dashboard, the companies page, or both?
2. "Less informative": is it missing a specific number or chart from v2 (MCF category drilldown,
   employment-type split, position-level bar, salary histogram, pipeline counts), or is it the
   density/layout?
3. Repeats: did the owner want the named list back (which ads, which companies) under its own tab,
   rather than only shares and distributions?
4. Does the owner want a separate analytics area (tabs) instead of one scroll?
5. Is the default direct-employers list acceptable when direct-sales firms with many distinct ads
   (ROYAL ORG, HYPERSCAL, AVARON) lead it, or is a curated "well-known employers" view wanted?
6. Any visual preference: more charts, fewer tiles, denser tables, a different hierarchy?

## Known gaps carried from SGSAL-030 (facts, not guesses)

- Per-job-type 4-week change is in `market_stats` but not shown (role families were only
  classified on active ads; see SGSAL-030 "Known limitation").
- Mobile layout of the v3 dashboard and companies page was never visually verified (Chrome
  `resize_window` had no effect on a maximised window).
- Skill names in the Data/AI list (RAG, LLM, ETL) have no plain gloss.
- Long company names truncate while the agency badge wraps.
- Production check of the follow-up commit 09e39fe by `curl` is blocked by the Vercel Security
  Checkpoint page; the first v3 deploy was confirmed in Chrome, the follow-up only by the push.

## Constraints that still apply

Facts not judgements (never "spam"); salary is always "median advertised monthly base";
"Recruitment agency" is a registration fact; no company named in editorial copy; dashboard reads
only `market_stats` (no per-request aggregation over `jobs`); one colour for bars, one axis per
chart (dataviz rules).

## Suggested approach once answers are in

Design agent brief with the owner's answers attached, a PM critique, then implement. Keep the
design agent's spec next to the v3 one
(`docs/superpowers/specs/2026-11-08-dashboard-companies-v3-design.md`) so the delta is explicit.
