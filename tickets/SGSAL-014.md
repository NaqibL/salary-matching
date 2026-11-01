---
id: SGSAL-014
project: salary-matching
title: "[Personal] Experience level on candidate profile"
status: todo
priority: low
type: feature
labels: [backend, frontend, matching, personal-use]
created: 2026-06-13
updated: 2026-06-13
---

## Summary

Add `target_seniority` and `years_experience` to the candidate profile — DB, API, and UI — with a soft boost/penalty in the matching pipeline.

## Context

- Surface: `/profile` — personal use only, hidden from nav
- Agent: db-agent (schema) + matching-agent (pipeline boost) + frontend-agent (UI)

## Acceptance Criteria

- [ ] `target_seniority` and `years_experience` added to profile DB table
- [ ] Fields exposed via profile API
- [ ] Profile UI (`/profile`) updated with inputs for these fields
- [ ] Soft boost/penalty applied in matching pipeline based on these values

## Notes

- Personal use only — do not expose or promote to general users
- Schema migration required for DB fields
