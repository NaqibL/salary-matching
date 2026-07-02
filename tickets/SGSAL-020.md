---
id: SGSAL-020
project: salary-matching
title: Donation page — help keep the site alive
status: in-progress
priority: low
type: feature
labels: [frontend, monetisation]
created: 2026-06-29
updated: 2026-06-30
---

## Summary

A public `/support` page explaining the project with a full-screen donation overlay (Ko-fi + PayNow). Designed to feel personal and illustrated, not transactional.

## UX flow

```
/support (landing)
  └── "Support Me!" button
        └── Full-screen overlay (no navigation)
              ├── Ko-fi button — left ("Buy me a teh peng")
              ├── Teh peng illustration — centre, tilted (artist asset)
              └── PayNow QR + chibi — right (artist assets)
```

## What's done

- [x] `/support` page built — centred title + tagline, two-column story/costs layout, amber "Support Me!" button
- [x] Button has Ko-fi symbol (left) and PayNow logo (right) flanking the text, equal-width slots for symmetry
- [x] `SupportOverlay` component — full-screen takeover, Escape to close, white/cream background
- [x] Overlay has three-column layout: Ko-fi button left, tilted teh peng placeholder centre, PayNow QR + chibi placeholder right
- [x] `kofi_symbol.png` and `paynow_logo.png` added to `/public`
- [x] Page accessible at `/support` directly — no auth required

## What's remaining

- [ ] Add `/support` link to sidebar (currently hidden — waiting until page is fully polished before exposing to users)
- [ ] Commission artist drawings: teh peng illustration (centre hero, tilted), chibi of Luqman (above PayNow QR with "Thank you!")
- [ ] Replace teh peng placeholder with real illustration asset
- [ ] Replace chibi placeholder with real artist asset
- [ ] Source a styled/modified PayNow QR to replace the plain `paynow_qr.png`
- [ ] Overlay background — white/cream for now, may revisit once art assets arrive

## Design decisions

- Overlay style: full-screen takeover (gives artwork room to breathe)
- Button: amber, not full-width, logos flanking the text
- Background: `#fdf8f0` (warm white/cream) — single variable, easy to swap
- Nav: sidebar only (not mobile bottom bar), added only when page is ready for public eyes

## Notes

- See `.claude/donation-page.md` for full design doc
- Page is live on prod via URL — just not linked anywhere yet
