---
id: SGSAL-009
project: salary-matching
title: Dashboard — seniority breakdowns + skills trends from llm_fields_json
status: done
priority: medium
type: feature
labels: [frontend, dashboard, analytics]
created: 2026-06-13
updated: 2026-11-08
---

> **Shipped** in 6082f2d (dashboard: seniority, top-skills, skills-trend and role-family analytics). Ticket status reconciled 2026-11-08.

## Summary

Extend the market dashboard (`/dashboard`) with seniority breakdowns and skills trend data now that `llm_fields_json` (canonical skills, inferred seniority) is available in the DB from LLM cleaning.

## Context

- Surface: `/dashboard` — public-facing
- Agent: frontend-agent
- Data already in DB via `llm_fields_json` column populated during crawl embed

## Acceptance Criteria

- [x] Seniority breakdown chart — distribution of job postings by inferred seniority (junior/mid/senior/lead)
- [x] Skills trends — top N canonical skills by volume, ideally over time
- [x] No backend schema changes required — query `llm_fields_json` via existing storage methods or a new read-only method

## Notes

- `llm_fields_json` contains `canonical_skills` and `inferred_seniority` fields
- These are LLM hints — not authoritative, but sufficient for aggregate trends
