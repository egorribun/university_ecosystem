/**
 * Wave 179 SW8 — Pure-function extraction of route guard logic.
 *
 * Closes W174 §Honesty #4-routeGuards by enabling unit testing of the
 * synchronous `beforeLoad` decision tree previously inlined in
 * `_auth.tsx` / `_public.tsx` / `_admin.tsx`. Each guard takes a plain
 * `GuardState` (user + loading) — no Zustand subscription, no TanStack
 * Router context — and either throws a `redirect()` or returns void.
 *
 * Route files call these via:
 *
 *   beforeLoad: ({ location }) => evaluateAuthGuard(useAuthStore.getState(), location)
 *   beforeLoad: () => evaluatePublicGuard(useAuthStore.getState())
 *   beforeLoad: () => evaluateAdminGuard(useAuthStore.getState())
 *
 * `redirect()` from `@tanstack/react-router` returns a `RouteRedirect` value
 * designed to be thrown from `beforeLoad` (TanStack catches the throw + applies
 * the navigation). The pure functions preserve this throw-based semantics so
 * route-file refactors are purely mechanical — no behavior change vs the
 * inline blocks.
 *
 * The VITE_LHCI bypass in `evaluateAuthGuard` mirrors W116 SW3 behavior:
 * when `VITE_LHCI=true` (set ONLY by `scripts/run-lhci.mjs` before its own
 * build spawn — NEVER in normal `npm run build`), the guard returns without
 * redirect, allowing LHCI to score authenticated routes' a11y/perf. The
 * branch tree-shakes from production dist because Vite/Rolldown substitutes
 * `import.meta.env.VITE_LHCI` literally at build time.
 *
 * @see _auth.tsx (W174 SW1 + W128 SW2 ssr:true + W179 SW8 refactor)
 * @see _public.tsx (W178 SW1 PublicLayout + W179 SW8 refactor)
 * @see _admin.tsx (W166 SW2 mounted-state + W179 SW8 refactor)
 * @see __tests__/guards.test.ts (10 unit tests covering all branches)
 */

import { redirect, type ParsedLocation } from "@tanstack/react-router"

/**
 * Minimal user shape consumed by guards. Mirrors `useAuthStore`'s `user`
 * field (full type at `@/types/User`) but accepts the loose role check
 * structurally — only `role` is read by `evaluateAdminGuard`. `role` is
 * optional to accept the User type's `role?: string` shape; missing role
 * is treated as non-admin in `evaluateAdminGuard`. Use `null` for
 * unauthenticated state.
 */
export interface GuardUser {
  role?: string
}

export interface GuardState {
  user: GuardUser | null
  loading: boolean
}

/**
 * Wave 179 SW8 — Used by `_auth.tsx beforeLoad` to gate all authenticated
 * routes. Throws redirect to `/login` with TanStack canonical `search.redirect`
 * preserving the user's intended destination (W177 §Honesty #3 +
 * W179 SW4 — `useLoginFlow.ts` reads search.redirect post-auth).
 *
 *  - loading state → returns void (lets initial useProfileSync settle)
 *  - VITE_LHCI bypass → returns void (a11y/perf scoring needs authed render)
 *  - unauth user → throws redirect to /login + search.redirect=location.href
 *  - authed user → returns void (proceeds to route)
 *
 * @param state - GuardState from useAuthStore.getState()
 * @param location - ParsedLocation from beforeLoad {location} arg (TanStack Router)
 */
export function evaluateAuthGuard(state: GuardState, location: ParsedLocation): void {
  if (state.loading) return
  if (import.meta.env.VITE_LHCI === "true") return
  if (!state.user) {
    throw redirect({
      to: "/login",
      search: { redirect: location.href },
    })
  }
}

/**
 * Wave 179 SW8 — Used by `_public.tsx beforeLoad` to gate the 5 public auth
 * routes (/login, /forgot-password, /register, /reset-password,
 * /reset-password/$token). Mirrors W178 SW1's logic: redirect already-authed
 * users to /dashboard (no /login in back-button history).
 *
 *  - loading state → returns void
 *  - authed user → throws redirect to /dashboard
 *  - unauth user → returns void (proceeds to route → form renders)
 *
 * Note: this only fires on INITIAL route mount. Post-mount user transitions
 * (e.g., useProfileSync settling after route already rendered) are caught by
 * the reactive useEffect in `PublicLayout` (W178 SW1 + W179 SW4 redirect).
 *
 * @param state - GuardState from useAuthStore.getState()
 */
export function evaluatePublicGuard(state: GuardState): void {
  if (state.loading) return
  if (state.user) {
    throw redirect({ to: "/dashboard" })
  }
}

/**
 * Wave 179 SW8 — Used by `_admin.tsx beforeLoad` to gate /admin/* routes.
 * Stricter than evaluateAuthGuard: requires authed user AND role === "admin".
 *
 *  - loading state → returns void
 *  - unauth user → throws redirect to /login (no search.redirect — admin pages
 *    typically aren't deep-linked by unauth users in canonical flow)
 *  - authed non-admin user → throws redirect to /dashboard (admin-page-deflect)
 *  - authed admin user → returns void
 *
 * @param state - GuardState from useAuthStore.getState()
 */
export function evaluateAdminGuard(state: GuardState): void {
  if (state.loading) return
  if (!state.user) {
    throw redirect({ to: "/login" })
  }
  if (state.user.role !== "admin") {
    throw redirect({ to: "/dashboard" })
  }
}
