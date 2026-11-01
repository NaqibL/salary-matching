---
id: SGSAL-013
project: salary-matching
title: "[Personal] Richer job cards on matches"
status: todo
priority: low
type: feature
labels: [frontend, matching, personal-use]
created: 2026-06-13
updated: 2026-06-13
---

## Summary

Add experience badge, seniority tag, and skill chips to the `JobCard` component on the matches page. Data is already returned in the API response.

## Context

- Surface: `JobCard` component — matches page only
- Agent: frontend-agent

## Acceptance Criteria

- [ ] Experience badge (e.g. "3+ yrs") on JobCard
- [ ] Seniority tag (junior/mid/senior/lead) on JobCard
- [ ] Skill chips from `canonical_skills` on JobCard

## Notes

- Personal use only — do not expose or promote to general users
