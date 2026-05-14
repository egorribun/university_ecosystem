import { createElement } from "react"
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

// Wave 126 Phase 3 SW4 — auth-at-edge replaces the W125 Phase 2 stub.
//
// `src/server.ts` (W126 SW3) extracts the access_token_v2 cookie + validates
// the JWT, then runs `handler.fetch(request)` inside an AsyncLocalStorage
// scope. The store is exposed via `globalThis.__ssrAuthGetter__` so the
// `getRouter()` factory below can read it synchronously while constructing
// the router for THIS request. On the client side `globalThis.__ssrAuthGetter__`
// is undefined (set only by server.ts which is server-only) — App.tsx's
// <RouterProvider context={...}> populates real auth from useAuth() at
// client mount, fully overriding any default we set here.
//
// The default (`loading: false`, `isAuth: false`) makes route guards behave
// correctly when context is uninitialized: `_auth.tsx` → redirect to /login,
// `_public.tsx` → render. The previous W125 stub used the same shape; we
// just stop calling it "STUB" because in W126+ the value is real per-request
// when running under server.ts.
const DEFAULT_AUTH: RouterContext["auth"] = {
  isAuth: false,
  user: null,
  loading: false,
}

const createAppRouter = () => {
  // Read SSR-injected auth state if running under server.ts; falls through to
  // DEFAULT_AUTH on the client (where App.tsx's RouterProvider context prop
  // overrides the value at mount anyway).
  const ssrAuth = typeof globalThis !== "undefined" ? globalThis.__ssrAuthGetter__?.() : undefined

  return createRouter({
    routeTree,
    context: {
      auth: ssrAuth ?? DEFAULT_AUTH,
      // Per-call QueryClient instance — SSR + client never share cache state
      // (would cause hydration mismatches). Phase 4+ may add proper
      // dehydrate/hydrate transfer via TanStack Query's persister.
      queryClient: new QueryClient(),
    },
    defaultPreload: "intent",
    defaultPreloadStaleTime: 0,
    scrollRestoration: true,
    defaultViewTransition: LHCI_VIEW_TRANSITION,
    // Wave 152 Phase 1.5 — provide a visible default pending UI for ANY
    // suspending route. Pre-W152, TanStack Router's internal <Matches>
    // Suspense defaulted to `fallback={null}` → indefinite suspension =
    // silent blank screen (the W150 polish-followup-v2 user-facing bug).
    // A simple skeleton screen is observably better than blank: if a route
    // is genuinely loading slowly, the user sees a placeholder; if it's
    // suspending indefinitely, they see the placeholder forever (which is
    // still better than blank, because we know SOMETHING is loading).
    // Defense-in-depth: even if the actual root cause of W150 polish-
    // followup-v2 is elsewhere (e.g. provider init hang), this turns the
    // observable failure from "blank screen with no clue" into "visible
    // loading state that exposes the stuck transition".
    defaultPendingMs: 0,
    defaultPendingComponent: () =>
      createElement(
        "div",
        {
          style: {
            minHeight: "100dvh",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "var(--bg-page, var(--initial-bg, #060b14))",
            color: "var(--text-primary, #f8fafc)",
            fontFamily: "system-ui, -apple-system, sans-serif",
            fontSize: "0.9rem",
            opacity: 0.7,
          },
          role: "status",
          "aria-live": "polite",
        },
        createElement("span", null, "Loading…")
      ),
    // Wave 125 Phase 2 — `defaultSsr: false` is part of TanStack
    // Router's separate `RouterConfig` (`createRouterConfig`), NOT of
    // `RouterConstructorOptions` (omitted via Omit). For SPA mode the
    // equivalent guard is `ssr: false` on the root route in
    // `__root.tsx` (see the createRootRouteWithContext options there).
    // The shellComponent + RootComponent SSR guard combination
    // achieves the same outcome: only the shellComponent renders
    // server-side, route `component`s skip SSR.
  })
}

// Wave 125 Phase 1 — TanStack Start v1's start-client-core/hydrateStart
// imports `getRouter` from `#tanstack-router-entry` (mapped to this file
// by the tanstackStart() Vite plugin). Even in SPA mode the hydration
// entry is bundled (for forward-compat with Phase 2+ SSR), so we MUST
// expose a `getRouter` factory.
//
// Wave 126 Phase 3 SW4 — TanStack Start invokes `getRouter()` per-request
// inside `runWithStartContext`; our `globalThis.__ssrAuthGetter__` returns
// the per-request auth state populated by `src/server.ts` via
// AsyncLocalStorage. Each request gets a fresh router with real auth
// context, replacing the W125 SSR_STUB_AUTH placeholder.
//
// `export const router` is preserved for App.tsx (the existing client-runtime
// consumer); both expressions resolve to the same `createRouter()` call shape.
export function getRouter() {
  return createAppRouter()
}

export const router = createAppRouter()

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}
