---
id: SGSAL-012
project: salary-matching
title: "[Personal] Filters on matches page"
status: todo
priority: low
type: feature
labels: [frontend, backend, matching, personal-use]
created: 2026-06-13
updated: 2026-06-13
---

## Summary

Add filter UI to the matches page (`/matches`) — seniority chips, min-years range, salary slider, employment type chips. Data is already in the DB.

## Context

- Surface: `frontend/app/matches/page.tsx` — personal use only, hidden from nav
- Needs: filter params on matching API + filter panel component
- Agent: frontend-agent (UI) + matching-agent (API params)

## Acceptance Criteria

- [ ] Filter panel on matches page: seniority chips, min-years range, salary slider, employment type chips
- [ ] Filter params passed to matching API
- [ ] Results re-fetch on filter change

## Notes

- Personal use only — do not expose or promote to general users
