---
id: SGSAL-029
project: salary-matching
title: Findings page (public what's new) + technical CHANGELOG.md
status: done
priority: medium
type: feature
labels: [frontend, docs, product, trust]
created: 2026-11-08
updated: 2026-11-08
depends_on: [SGSAL-028]
blocks: []
---

## Summary

Owner asked for a "what's new" page for the public and a technical document. A product-review
agent (2026-11-08) argued against a timeline with a technical toggle: build a short findings-led
public page, keep technical detail in the repo, stamp every number with an as-of date, describe
reposting and agencies as counts and definitions (never intent), omit credential history, and
include "Fixed:" entries. Adopted, with one deviation: a small sidebar-footer link in addition to
the dismissible checker banner, because the owner wants the public to find it.

- `/findings`: seven entries (`frontend/content/findings.ts`), newest first, each with date, plain
  headline, one or two paragraphs, at most three figures with as-of dates, one link to the
  technical record; a "How the numbers are made" glossary under the entries.
- `CHANGELOG.md` at the repo root with stable heading anchors; README changelog replaced by a
  pointer.
- Checker banner "New on 8 Nov: …" keyed by release date in localStorage; sidebar footer link.

## Checklist

- [x] Content file, page, glossary
- [x] CHANGELOG.md + README pointer
- [x] Sidebar link + checker banner
- [x] Deployed 15:46 SGT; job-seeker agent read it cold: trusted the site more; five copy edits applied (plain words for median/quartiles and the 2x rule, ACRA wording, frozen-number note, 'test runs'), defensive agency line removed, Straits Times mention dropped as marketing-ish, denominator added to the 45% figure
