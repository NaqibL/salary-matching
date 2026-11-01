---
id: SGSAL-007
project: salary-matching
title: UI — fix mobile JD wall-of-text in similar-roles cards
status: done
priority: medium
type: bug
labels: [frontend, salary-checker, mobile, ux]
created: 2026-06-13
updated: 2026-06-13
---

## Summary

The expanded job description in similar-roles cards renders as an unstyled wall of text on mobile. Needs basic text formatting and a scrollable container.

## Context

- Surface: similar-roles card component in `frontend/app/components/`
- Agent: frontend-agent
- Estimated effort: ~1 hour
- Only affects historical listings — active listings have no description, so the "show more" expand never appears for them

## Acceptance Criteria

- [ ] JD text wrapped in `whitespace-pre-wrap`
- [ ] `text-sm` and `leading-relaxed` applied for readability
- [ ] `max-h-48 overflow-y-auto` to contain long descriptions in a scrollable box
- [ ] Tested on mobile viewport

## Notes

- From feedback review 2026-06-02 — confirmed as SHIP IT
