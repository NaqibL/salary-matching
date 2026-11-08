---
id: SGSAL-027
project: salary-matching
title: Salary checker — similar-roles cards show open postings first
status: in-progress
priority: high
type: bug
labels: [salary-checker, product, ux]
created: 2026-11-08
updated: 2026-11-08
depends_on: []
blocks: []
---

## Problem

Verified on production 2026-11-08: a Data Analyst check returned 20 similar-role cards, all
closed (last seen Apr–Aug 2026), while 453 companies had open data roles. `check_lowball`
ranks all ~665k historical postings by similarity and shows the top 20; closed history
outnumbers live ads ~10:1. Both external reviews (PM agent, job-seeker agent) ranked this first.

## Fix

Widen the candidate pool to the 500 nearest postings, show open ones first, fill with closed.
Percentile pool unchanged (historical by design). Response adds `open_matched`. Headline and
badge copy made explicit ("{n} closest ads · {open} open now", "{pct}% match").

Spec: `docs/superpowers/specs/2026-11-08-ux-v2-agencies-open-roles-design.md`.
