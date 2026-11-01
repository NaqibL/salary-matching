---
id: SGSAL-010
project: salary-matching
title: UI — client-side filters on similar roles cards
status: todo
priority: low
type: feature
labels: [frontend, salary-checker, ux]
created: 2026-06-13
updated: 2026-06-13
---

## Summary

Add client-side filtering of the already-fetched top-20 similar-roles results by seniority, active-only, min experience, has-salary. No backend changes needed for v1.

## Context

- Surface: salary checker similar-roles section
- Agent: frontend-agent
- Data already returned in the API response — purely frontend filtering

## Acceptance Criteria

- [ ] Filter chips/toggles: seniority, active-only, min experience, has-salary
- [ ] Filters apply client-side on the existing result set (no re-fetch)
- [ ] Filter state resets when the user submits a new salary check
- [ ] Works on mobile

## Notes

- No backend changes for v1 — filter on data already present in the response payload
