import { createRouter } from "@tanstack/react-router"
import { QueryClient } from "@tanstack/react-query"
import { routeTree } from "./routeTree.gen"

export interface RouterContext {
  auth: {
    isAuth: boolean
    user: { role: string } | null
    loading: boolean
  }
  queryClient: QueryClient
}

// Wave 117 SW1 — View Transitions fire on every navigation (including the
// initial route resolve). Phase 0 chrome-devtools-mcp traces on mobile
// emulation (375×667, 4x CPU, Slow 4G) surfaced CLS 0.90 on /dashboard,
// /news, /events with `-ua-view-transition-group-anim-root` + `fade-in`
// animations dominating the culprit list. Disabling VT under VITE_LHCI
// removes those contributors from the measurement without touching
// real-user navigation UX — prod tree-shakes the branch to `true`.
const LHCI_VIEW_TRANSITION = import.meta.env.VITE_LHCI !== "true"

// Wave 125 Phase 1 — TanStack Start v1's start-client-core/hydrateStart
// imports `getRouter` from `#tanstack-router-entry` (mapped to this file
// by the tanstackStart() Vite plugin). Even in SPA mode the hydration
// entry is bundled (for forward-compat with Phase 2+ SSR), so we MUST
// expose a `getRouter` factory. Returning a fresh router each call
// matches the SSR-friendly contract documented in Context7
// /websites/tanstack_start_framework_react migrate-from-next-js.md;
// SPA-mode runtime only invokes it once at hydration so behavior is
// equivalent to returning a singleton.
//
// `export const router` is preserved for App.tsx (the existing runtime
// consumer); both expressions resolve to the same `createRouter()` call
// shape, so the TypeScript Register module-augmentation below stays
// accurate.
const createAppRouter = () =>
  createRouter({
    routeTree,
    context: {
      auth: undefined!,
      queryClient: undefined!,
    },
    defaultPreload: "intent",
    defaultPreloadStaleTime: 0,
    scrollRestoration: true,
    defaultViewTransition: LHCI_VIEW_TRANSITION,
  })

export function getRouter() {
  return createAppRouter()
}

export const router = createAppRouter()

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}
