---
id: SGSAL-005
project: salary-matching
title: UI — label salary figures as "Monthly base salary (SGD)"
status: done
priority: medium
type: feature
labels: [frontend, salary-checker, ux]
created: 2026-06-13
updated: 2026-06-13
---

## Summary

Users don't know that salary figures are monthly base in SGD. Without a label, the core output is ambiguous. Add a clear label near the salary input and benchmark result band.

## Context

- Surface: salary checker (`/`) — the primary public-facing page
- Agent: frontend-agent
- Estimated effort: ~1 hour

## Acceptance Criteria

- [ ] `"Monthly base salary (SGD)"` label appears near the salary input field
- [ ] Same label (or equivalent) appears near the benchmark result band / output
- [ ] Label is legible on mobile

## Notes

- From feedback review 2026-06-02 — confirmed as SHIP IT
