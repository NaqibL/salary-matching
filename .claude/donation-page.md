# Donation Page — Design Doc

## Current state

Page exists at `/support` (`frontend/app/support/page.tsx`). Currently hidden — not linked from sidebar, mobile nav, or anywhere in the UI.

---

## Intended UX flow

```
/support (landing)
  └── "Support Me!" button
        └── Overlay (opens over the page, no new tab)
              ├── Ko-fi section (link + teh peng image + Ko-fi logo)
              └── PayNow section (modified QR + custom artist art)
```

---

## Landing page (`/support`)

### Layout
```
[ Large title — centred                        ]
[ "Make job hunting less stressful" — centred  ]

[ Short story (left)  |  My Costs (right)      ]

[ ———————— Support Me!  🧋 ▪ PayNow ———————— ]
```

### Content
- Large page title, top centre
- Tagline "Make job hunting less stressful" directly beneath
- Two-column middle: story on the left, costs breakdown on the right
- Full-width "Support Me!" button at the bottom with small inline Ko-fi + PayNow logos (placeholder slots — assets TBD)

### Open questions
- [x] Button style: full-width, rounded rectangle, amber/warm colour

---

## Overlay

Triggered by "Support Me!" button. Opens over the current page (no navigation).

### Layout
```
[                  Full-screen takeover                   ]
[                                                         ]
[ [Buy me a teh peng]    🧋 (tilted)    [PayNow QR art]  ]
[  Ko-fi button left     centre hero    chibi + thank you ]
[                                                         ]
```

- **Left:** Big Ko-fi button, text "Buy me a teh peng"
- **Centre:** Teh peng illustration, tilted slightly — the hero of the overlay
- **Right:** PayNow QR as a designed asset (not a plain QR in a box), chibi version of Luqman sitting on top with a "Thank you!"
- Everything else is artist assets — this is mostly an illustrated experience, not a UI

### Open questions
- [x] Overlay style: **full-screen takeover**
- [x] Layout: Ko-fi button left · teh peng hero centre · PayNow asset right
- [x] Artist drawings: not yet commissioned — use placeholder slots in the build
- [x] Background: white/cream for now (`bg-amber-50` or `bg-white`) — single token, easy to swap once art arrives

---

## Assets

| Asset | Status |
|---|---|
| Ko-fi logo | TBD — to be provided |
| PayNow logo (for CTA button) | TBD — to be provided |
| Teh peng image | TBD — to be provided |
| Modified PayNow QR | TBD — to be provided |
| Artist drawings | TBD — commissioned, coming later |

Current assets in repo:
- `/public/paynow_qr.png` — original PayNow QR (already used on page)

---

## Navigation / discoverability

Currently completely hidden. Decision needed:
- [x] Surface in **sidebar** — bottom slot, separate from the main nav links

---

## Implementation order (proposed)

1. Nail down overlay style + layout (design decisions above)
2. Rebuild landing page layout
3. Build overlay component with placeholder asset slots
4. Wire up "Support Me!" button → overlay
5. Drop in real assets when ready
6. Add link to nav/sidebar/footer
