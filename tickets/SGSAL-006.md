---
id: SGSAL-006
project: salary-matching
title: UI — recruiter caveat about inflated postings
status: done
priority: medium
type: feature
labels: [frontend, salary-checker, ux]
created: 2026-06-13
updated: 2026-06-13
---

## Summary

Recruiters inflate MCF salary listings 10–20% above what employers actually offer. Surfacing this caveat builds user trust through honesty rather than hiding a known data quality issue.

## Context

- Surface: salary checker results component
- Agent: frontend-agent
- Estimated effort: ~1 hour

## Acceptance Criteria

- [ ] Muted inline note beneath the salary result band reads: *"Posted ranges may be 10–20% above what employers actually offer."*
- [ ] Note is visually subordinate (muted colour, smaller text) — does not compete with the main result

## Notes

- From feedback review 2026-06-02 — insider knowledge from a recruiter, confirmed as SHIP IT
