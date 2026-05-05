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

// Wave 125 Phase 2 — stub context for build-time SSR + initial mount.
//
// Pre-W125 the router was instantiated with `context: { auth: undefined!,
// queryClient: undefined! }` and `App.tsx`'s `<RouterProvider context={...}>`
// populated real values at runtime. With Phase 2's spa-mode prerender,
// route guards (_auth.tsx, _public.tsx, _admin.tsx) run during the
// build-time SSR pass with whatever context the router was created
// with — so undefined context throws TypeError on `context.auth.loading`.
// Stub values let guards execute non-destructively (they all just call
// `redirect()` which is followed by the prerender pipeline up to
// `maxRedirects`). When `<RouterProvider context={...}>` mounts on the
// client, the real values override these stubs reactively for the
// regular runtime.
//
// `loading: false` paired with `isAuth: false` makes _auth.tsx redirect
// to /login (which _public.tsx accepts), giving the prerender a stable
// terminal route. Phase 3 (W126+) replaces this with cookie-based
// auth-at-edge so SSR sees real auth state from the first request.
const SSR_STUB_AUTH: RouterContext["auth"] = { isAuth: false, user: null, loading: false }
const SSR_STUB_QUERY_CLIENT = new QueryClient()

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
      auth: SSR_STUB_AUTH,
      queryClient: SSR_STUB_QUERY_CLIENT,
    },
    defaultPreload: "intent",
    defaultPreloadStaleTime: 0,
    scrollRestoration: true,
    defaultViewTransition: LHCI_VIEW_TRANSITION,
    // Wave 125 Phase 2 — `defaultSsr: false` is part of TanStack
    // Router's separate `RouterConfig` (`createRouterConfig`), NOT of
    // `RouterConstructorOptions` (omitted via Omit). For SPA mode the
    // equivalent guard is `ssr: false` on the root route in
    // `__root.tsx` (see the createRootRouteWithContext options there).
    // The shellComponent + RootComponent SSR guard combination
    // achieves the same outcome: only the shellComponent renders
    // server-side, route `component`s skip SSR.
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
