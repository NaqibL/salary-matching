---
id: SGSAL-016
project: salary-matching
title: UI + Backend — seniority dropdown on salary checker input
status: done
priority: medium
type: feature
labels: [frontend, backend, salary-checker, embeddings]
created: 2026-06-16
updated: 2026-11-08
depends_on: []
blocks: []
---

> **Shipped** in 99da0d9 (seniority field on `/api/lowball/check` + checker dropdown). Ticket status reconciled 2026-11-08.

## Summary

Add an optional seniority dropdown to the salary checker input form. The selected value is appended to the job text before embedding, steering the cosine similarity toward jobs at that seniority tier — so the returned similar roles and salary percentiles reflect the chosen level.

## Motivation

The salary checker currently embeds `Job Title + Description` only. A "Senior Data Analyst" and "Junior Data Analyst" share similar descriptions and often collapse to the same embedding neighbourhood. Appending `Seniority: Senior` to the query text nudges the vector toward stored job embeddings that also carry that seniority line, narrowing percentiles to the right tier.

## Seniority values

Dropdown options: `Intern`, `Entry`, `Junior`, `Mid`, `Senior`, `Lead`, `Manager`, `Director`

- `Intern` needs both lines in the query — existing embeddings only have `Role Type: Internship`
  (from `_extract_role_types`); future embeddings (after llm_cleaner update on 2026-06-16) will also
  have `Seniority: Intern`. Append both for maximum coverage.
- All others map directly to `Seniority: {value}`, matching `inferred_seniority` in stored embeddings.

Dropdown is optional — no selection means current behaviour (no seniority line appended).

## Changes required

### Backend — `src/mcf/api/routes/lowball.py`

1. Add `seniority: str | None = Field(default=None)` to `LowballCheckRequest`
2. In `check_lowball`, after building `job_text`, append the right line based on seniority:
   ```python
   job_text = f"Job Title: {body.title}\nDescription: {description_text}"
   if body.seniority == "Intern":
       job_text += "\nRole Type: Internship\nSeniority: Intern"
   elif body.seniority:
       job_text += f"\nSeniority: {body.seniority}"
   ```
   Intern appends both lines for compatibility: older embeddings only have `Role Type: Internship`;
   newer embeddings (post 2026-06-16 crawls) will also have `Seniority: Intern`.

### Frontend — `frontend/lib/api.ts`

Add `seniority?: string` param to `lowballApi.check()` and include it in the request body:
```ts
check: async (title, description, salary?, companyName?, seniority?, topK = 20)
// body: { ..., seniority: seniority ?? null }
```

### Frontend — `frontend/app/lowball/LowballContent.tsx`

1. Add `const [seniority, setSeniority] = useState('')` 
2. Add a `<select>` in the first form grid row (alongside Job title / Company), labelled "Seniority (optional)"
3. Pass `seniority || undefined` to `lowballApi.check()`
4. Include `seniority` in the `reset()` handler

## Notes

- The Next.js route handler (`frontend/app/api/lowball/check/route.ts`) is a passthrough — no changes needed
- No input validation needed on backend beyond the existing Pydantic model; unknown values are silently ignored (they just append an unhelpful line to the text)
- Could add a validate enum if desired: `Literal["Intern","Entry","Junior","Mid","Senior","Lead","Manager","Director"]`
