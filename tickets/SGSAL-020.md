---
id: SGSAL-020
project: salary-matching
title: Donation page — help keep the site alive
status: done
priority: low
type: feature
labels: [frontend, monetisation]
created: 2026-06-29
updated: 2026-06-29
---

## Summary

A simple public page explaining the project and giving visitors a way to donate (Buy Me a Coffee / Ko-fi / Stripe) to cover hosting costs.

## Context

- Surface: `/support` — public-facing, no auth required
- Costs to cover: Railway (~$5/mo API), Supabase (free tier currently), Vercel (free)
- Keeping it honest: not monetising, just covering infra costs

## Approach

### Donation provider

Use **Buy Me a Coffee** or **Ko-fi** — both are zero-setup, link-based, and have embeddable widgets. Stripe is overkill for a personal project.

Recommended: Ko-fi (no platform fee on one-time donations; clean embed).

### Page content

- One paragraph: what the tool does, who built it, why it's free
- What donations cover (Railway compute, crawl storage)
- Embed or button linking to Ko-fi / Buy Me a Coffee profile
- Optional: a small "supporters" shoutout section if donations come in

### Frontend

- New page `frontend/app/support/page.tsx` — static, no API calls
- Link from footer (not nav — keep nav clean) with a subtle "Support" or "☕" label
- Keep it minimal: no animations, no guilt-trip copy

## Acceptance Criteria

- [ ] Donation provider account created (Ko-fi or Buy Me a Coffee)
- [ ] `/support` page live with project description + donation link/embed
- [ ] Footer links to `/support`
- [ ] No auth required, fully public

## Notes

- Don't add to main nav — footer only, so it doesn't distract from the core tool
- Keep the page copy honest and low-pressure
