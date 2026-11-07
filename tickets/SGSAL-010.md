---
id: SGSAL-010
project: salary-matching
title: UI — client-side filters on similar roles cards
status: done
priority: low
type: feature
labels: [frontend, salary-checker, ux]
created: 2026-06-13
updated: 2026-11-08
---

> **Shipped** in 16c7bb5 (client-side filters on the top-20 similar-roles results). Ticket status reconciled 2026-11-08.

## Summary

Add client-side filtering of the already-fetched top-20 similar-roles results by seniority, active-only, min experience, has-salary. No backend changes needed for v1.

## Context

- Surface: salary checker similar-roles section
- Agent: frontend-agent
- Data already returned in the API response — purely frontend filtering

## Acceptance Criteria

- [x] Filter chips/toggles: seniority, active-only, min experience, has-salary
- [x] Filters apply client-side on the existing result set (no re-fetch)
- [x] Filter state resets when the user submits a new salary check
- [x] Works on mobile

## Notes

- No backend changes for v1 — filter on data already present in the response payload
