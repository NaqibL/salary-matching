# Frontend Components (`frontend/app/components/`)

## Purpose

Shared React components used across multiple pages. This directory contains all non-trivial UI components — from the core job card used in matches/saved views to auth wrappers, context providers, and tab-level feature components. Page-specific micro-components can live inline in their `page.tsx` but anything reused goes here.

## Key Files

| File | Purpose |
|---|---|
| `JobCard.tsx` | Match/saved job card with score badge, salary, company, skills, interaction buttons |
| `ResumeTab.tsx` | Resume upload form + semantic match results list (entire Resume tab on `/matches`) |
| `TasteTab.tsx` | Job rating swipe UI + taste-refined match results (entire Taste tab on `/matches`) |
| `AuthGate.tsx` | Wraps children — shows login CTA if unauthenticated, renders children if authed |
| `ProfileProvider.tsx` | React context provider for current user profile data across all pages |
| `RatingsQueueProvider.tsx` | Batches/debounces job ratings before API flush |
| `Nav.tsx` | Top navigation bar with logo, links, and user actions |
| `NavUserActions.tsx` | Auth buttons + user dropdown in nav |
| `TutorialModal.tsx` | First-run onboarding overlay (shown once per user) |
| `AuthDashboardPreview.tsx` | Preview/teaser UI shown to unauthenticated visitors on matches page |
| `PageTransition.tsx` | Fade-in animation wrapper for page changes |
| `Spinner.tsx` | Reusable loading indicator |
| `AuthErrorBoundary.tsx` | Class component error boundary for auth-related crashes |
| `layout/Layout.tsx` | Main layout shell (sidebar + content area) |
| `layout/Sidebar.tsx` | Desktop sidebar navigation |
| `layout/MobileNav.tsx` | Bottom navigation for mobile viewports |

## Dependencies

| Package | Use |
|---|---|
| `react` | Hooks, context, memo |
| `swr` | Data fetching in tab components |
| `axios` (via `@/lib/api`) | API calls |
| `@supabase/supabase-js` | Auth state in AuthGate, Nav |
| `lucide-react` | Icons |
| `sonner` | Toast notifications |
| `next/dynamic` | Lazy loading heavy tabs |

## Internal Dependencies

- `@/lib/api` — all API calls (never use axios directly in components)
- `@/lib/types` — `Job`, `Match`, `Profile`, `InteractionType`
- `@/lib/supabase` — Supabase client for auth
- `@/lib/utils` — `cn()` className helper
- `@/components/ui/*` — shadcn/ui primitives

## State Management

- **Auth state**: Supabase session via `supabase.auth.getSession()` + `onAuthStateChange` listener in `AuthGate`/`ProfileProvider`
- **Profile data**: React Context (`ProfileProvider`) + SWR cache (`@/lib/profile-cache`)
- **Match results**: SWR in `ResumeTab` and `TasteTab`
- **Ratings queue**: `RatingsQueueProvider` internal state, flushes via debounce

## Testing

No component-level tests currently. Integration tested via smoke tests on the FastAPI side.

## Common Modifications

- **Change job card appearance**: Edit `JobCard.tsx`
- **Add new interaction type**: Update `InteractionType` in `@/lib/types.ts`, add button in `JobCard.tsx`, add handler in API
- **Modify matching UI**: `ResumeTab.tsx` (resume mode) or `TasteTab.tsx` (taste mode)
- **Add new component**: See [Adding a New React Component](../../../.ai/common-tasks.md#adding-a-new-react-component)
