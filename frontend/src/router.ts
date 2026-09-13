import { createElement } from "react"
import { createRouter } from "@tanstack/react-router"
import { QueryClient } from "@tanstack/react-query"
import { createQueryClient } from "./app/queryClient"
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
// is undefined (set only by server.ts which is server-only) — the route
// guards in `_auth.tsx`, `_public.tsx`, and `_admin.tsx` now read live state
// from `useAuthStore.getState()` (Wave 174 SW1) since W152 Phase 1.7 removed
// the App.tsx `<RouterProvider context={useAuth()}>` reactive bridge.
//
// Wave 174 SW1 — router context `.auth` is NOW SERVER-ONLY:
//   • On SSR: `globalThis.__ssrAuthGetter__()` returns the per-request auth
//     state from server.ts's AsyncLocalStorage. TanStack Router uses this
//     to render the initial server-matched route's authenticated content.
//   • On client: the route guards' `beforeLoad` reads `useAuthStore.getState()`
//     directly (a plain JS call, safe outside React render phase). The
//     useProfileSync hook syncs its internal state INTO Zustand via
//     `useAuthStore.setState(...)` (useProfileSync.ts:1099-1109), so Zustand
//     is the single source of truth for client-side auth state.
//
// Pre-W174 the route guards read from `context.auth` which got stuck at
// DEFAULT_AUTH on the client (since W152 Phase 1.7 removed the reactive
// context bridge in App.tsx). Result: every post-login client-side navigate()
// re-evaluated beforeLoad against a stale singleton context → user bounced
// back to /login on every navigation, AND login itself never redirected.
//
// The default (`loading: false`, `isAuth: false`) makes route guards behave
// correctly when context is uninitialized on SERVER (no SSR cookie → unauth →
// `_auth.tsx` → redirect to /login, `_public.tsx` → render).
const DEFAULT_AUTH: RouterContext["auth"] = {
  isAuth: false,
  user: null,
  loading: false,
}

const createAppRouter = () => {
  // Read SSR-injected auth state if running under server.ts; falls through to
  // DEFAULT_AUTH on the client where the value is unused (client-side route
  // guards read Zustand directly per Wave 174 SW1).
  const ssrAuth = globalThis.__ssrAuthGetter__?.()

  return createRouter({
    routeTree,
    context: {
      auth: ssrAuth ?? DEFAULT_AUTH,
      // Per-call QueryClient instance — SSR + client never share cache state,
      // while both still use the same offline/retry/cache policy.  Constructing
      // a bare QueryClient here silently diverges from the provider's defaults
      // during SSR loader resolution and causes redundant refetches.
      queryClient: createQueryClient(),
    },
    defaultPreload: "intent",
    defaultPreloadStaleTime: 0,
    scrollRestoration: true,
    defaultViewTransition: LHCI_VIEW_TRANSITION,
    // Wave 152 Phase 1.5 + Wave 153 SW2 — provide a visible default pending
    // UI for ANY suspending route on the CLIENT, but return null during SSR.
    //
    // W152 Phase 1.5 history: pre-W152, TanStack Router's internal <Matches>
    // Suspense defaulted to `fallback={null}` → indefinite suspension =
    // silent blank screen (the W150 polish-followup-v2 user-facing bug).
    // W152 added a visible "Loading…" placeholder via defaultPendingComponent
    // as defense-in-depth — observably better than blank.
    //
    // W153 SW2 fix: but the unconditional fallback rendered DOM inside the
    // SSR'd Suspense boundary (`<div id="root"><!--$--><div ...>Loading…</div>`),
    // and `main.tsx:121-127` `hasRealSsrContent` detection picked up that
    // ELEMENT_NODE → forced hydrateRoot path → client tree (Login form) vs
    // server tree (Loading fallback) → React error #418 hydration mismatch →
    // blank screen on /login in real Chrome since W150-polish-followup-v2.
    //
    // The fix WAS SSR-aware via `import.meta.env.SSR` (Vite literal: `true`
    // in server bundle, `false` in client bundle — DCE eliminates the unused
    // branch entirely). Server bundle returned `null` → Suspense emits only
    // marker comments → main.tsx takes createRoot path. Client bundle kept
    // the visible Loading… UX for in-flight route transitions.
    //
    // W180 polish-v2 (2026-05-21) — REMOVED the SSR-null guard. Post-W156 SW3
    // `hydrateRoot(document)` adoption, `main.tsx hasRealSsrContent` detection
    // (which was the original target of W152 SW2 fix) NO LONGER EXISTS — that
    // logic was stripped in W156 SW3 commit `8faf5f4cb`. The SSR-null guard
    // became LEGACY dead-code that ACTIVELY HARMED hydration on `ssr: 'data-only'`
    // routes (/messenger + /map + /activity per W127 SW6 pattern): server emits
    // null fallback inside `<ClientOnly>` Suspense boundary, client emits the
    // visible Loading div → React #418 element-type mismatch on every page load.
    // The authenticated visual audit surfaced this class-wide finding
    // filter regex fix (3 of 9 SSR routes affected, all `ssr: 'data-only'`).
    // Polish-v2 root-cause via NODE_ENV=development build captured the EXACT
    // unminified React error message + component stack pinpointing this exact
    // defaultPendingComponent fallback as the mismatch source.
    //
    // Fix: return the same visible Loading div on BOTH server + client. Suspense
    // fallback DOM matches → no hydration mismatch. Full SSR routes (which don't
    // suspend at SSR time because loaders pre-fetch via ensureQueryData) never
    // emit this fallback so behavior unchanged for those. `ssr: 'data-only'`
    // routes (which DO suspend at SSR time because route component is client-only
    // via TanStack Start `<ClientOnly>`) now emit consistent fallback → 0 React
    // #418 expected on /messenger + /map + /activity post-fix.
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
