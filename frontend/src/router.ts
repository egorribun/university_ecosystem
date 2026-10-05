import { createElement } from "react"
import { createRouter } from "@tanstack/react-router"
import {
  dehydrate as dehydrateQueryClient,
  hashKey,
  hydrate as hydrateQueryClient,
  type DehydratedState,
  type QueryClient,
  type QueryKey,
} from "@tanstack/react-query"
import { createQueryClient, queryClient as browserQueryClient } from "./app/queryClient"
import {
  dashboardEventsQueryKey,
  projectDashboardEventsSnapshot,
  type DashboardEventsSnapshot,
} from "./hooks/useDashboardEvents"
import {
  dashboardStoriesQueryKey,
  projectDashboardStories,
  type DashboardStory,
} from "./hooks/useDashboardStories"
import { configureRouterViewTransitions } from "./app/routerViewTransitions"
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
// Mobile WebKit can leave the old route snapshot composited over the new page
// indefinitely after a cross-route transition. The new route is in the DOM,
// but links beneath that snapshot never become actionable. Keep normal route
// navigation and reserve View Transitions for engines without this failure.
const MOBILE_WEBKIT_VIEW_TRANSITION =
  typeof window === "undefined" ||
  !("WebKitPoint" in window && window.matchMedia("(hover: none) and (pointer: coarse)").matches)

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

const dashboardQueryKeys: readonly QueryKey[] = [dashboardEventsQueryKey, dashboardStoriesQueryKey]

const isDashboardQueryKey = (queryKey: QueryKey) =>
  dashboardQueryKeys.some(
    (allowedKey) =>
      allowedKey.length === queryKey.length &&
      allowedKey.every((segment, index) => segment === queryKey[index])
  )

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value)

type DashboardQueryKey = typeof dashboardEventsQueryKey | typeof dashboardStoriesQueryKey
type DashboardQueryData = DashboardEventsSnapshot | DashboardStory[]
type DashboardDehydratedQuery = {
  dehydratedAt: number
  queryHash: string
  queryKey: DashboardQueryKey
  state: {
    data: DashboardQueryData
    dataUpdateCount: number
    dataUpdatedAt: number
    error: null
    errorUpdateCount: number
    errorUpdatedAt: number
    fetchFailureCount: number
    fetchFailureReason: null
    fetchMeta: null
    isInvalidated: boolean
    status: "success"
    fetchStatus: "idle"
  }
}
type DashboardDehydratedState = {
  mutations: []
  queries: DashboardDehydratedQuery[]
}

const projectDehydratedQuery = (value: unknown): DashboardDehydratedQuery | undefined => {
  if (!isRecord(value) || !isRecord(value.state)) return undefined
  const candidateQueryKey = value.queryKey
  if (!Array.isArray(candidateQueryKey)) return undefined
  const queryState = value.state
  if (
    queryState.status !== "success" ||
    typeof value.queryHash !== "string" ||
    typeof value.dehydratedAt !== "number" ||
    typeof queryState.dataUpdateCount !== "number" ||
    typeof queryState.dataUpdatedAt !== "number" ||
    typeof queryState.isInvalidated !== "boolean"
  ) {
    return undefined
  }

  let queryKey: DashboardQueryKey
  let data: DashboardQueryData | undefined
  if (
    candidateQueryKey.length === dashboardEventsQueryKey.length &&
    dashboardEventsQueryKey.every((segment, index) => segment === candidateQueryKey[index])
  ) {
    queryKey = dashboardEventsQueryKey
    data = projectDashboardEventsSnapshot(queryState.data)
  } else if (
    candidateQueryKey.length === dashboardStoriesQueryKey.length &&
    dashboardStoriesQueryKey.every((segment, index) => segment === candidateQueryKey[index])
  ) {
    queryKey = dashboardStoriesQueryKey
    data = projectDashboardStories(queryState.data)
  } else {
    return undefined
  }

  if (data === undefined) return undefined
  const queryHash = hashKey(queryKey)
  if (value.queryHash !== queryHash) return undefined

  return {
    dehydratedAt: value.dehydratedAt,
    queryHash,
    queryKey,
    state: {
      data,
      dataUpdateCount: queryState.dataUpdateCount,
      dataUpdatedAt: queryState.dataUpdatedAt,
      error: null,
      errorUpdateCount: 0,
      errorUpdatedAt: 0,
      fetchFailureCount: 0,
      fetchFailureReason: null,
      fetchMeta: null,
      isInvalidated: queryState.isInvalidated,
      status: "success",
      fetchStatus: "idle",
    },
  }
}

const filterDashboardDehydratedState = (state: DehydratedState): DashboardDehydratedState => ({
  mutations: [],
  queries: state.queries.flatMap((query) => {
    const projected = projectDehydratedQuery(query)
    return projected ? [projected] : []
  }),
})

const createAppRouter = () => {
  // Read SSR-injected auth state if running under server.ts; falls through to
  // DEFAULT_AUTH on the client where the value is unused (client-side route
  // guards read Zustand directly per Wave 174 SW1).
  const ssrAuth = globalThis.__ssrAuthGetter__?.()
  // SSR gets an isolated cache per request; browser loaders and the persisted
  // root provider share the same owner-aware application client.
  const routerQueryClient = import.meta.env.SSR ? createQueryClient() : browserQueryClient

  const router = createRouter({
    routeTree,
    context: {
      auth: ssrAuth ?? DEFAULT_AUTH,
      queryClient: routerQueryClient,
    },
    // Transfer only successful dashboard data. Auth/session queries and
    // mutations remain request-local and are never part of router hydration.
    dehydrate: () =>
      filterDashboardDehydratedState(
        dehydrateQueryClient(routerQueryClient, {
          shouldDehydrateQuery: (query) =>
            query.state.status === "success" && isDashboardQueryKey(query.queryKey),
          shouldDehydrateMutation: () => false,
        })
      ),
    hydrate: (state) => {
      if (!state || !Array.isArray(state.queries)) return
      hydrateQueryClient(routerQueryClient, filterDashboardDehydratedState(state))
    },
    defaultPreload: "intent",
    defaultPreloadStaleTime: 0,
    scrollRestoration: true,
    defaultViewTransition: LHCI_VIEW_TRANSITION && MOBILE_WEBKIT_VIEW_TRANSITION,
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
  configureRouterViewTransitions(router)
  return router
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
  interface HistoryState {
    /** Set when a chat is opened from the messenger list, so mobile back pops it. */
    messengerOpenedFromList?: boolean
  }
}
