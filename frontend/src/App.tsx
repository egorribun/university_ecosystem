import { StartClient } from "@tanstack/react-start/client"

// Wave 127 SW1 — App.tsx is now a thin client-entry mount. AppProviders +
// ThemeProvider were hoisted to __root.tsx RootComponent so they're available
// during SSR. Auth context is populated by router.ts createAppRouter() which
// reads globalThis.__ssrAuthGetter__ on server (W126 SW4 pattern); on client
// it falls back to DEFAULT_AUTH and AuthProvider in __root.tsx (which mounts
// inside the router tree) reads useAuthStore directly for real-time updates.
//
// Wave 152 Phase 1 — REMOVED outer `<Suspense>` wrapper around RouterProvider.
// It caused two symptoms that the W150 polish-followup-v2 debug pass missed:
//
//   (1) DEV-MODE hydration mismatch: `npm run dev` SSR pipeline emits the route
//       tree directly inside `<div id="root">` (no App-level Suspense markers),
//       but the client added Suspense markers (`<!--$--><!--/$-->`) from this
//       wrapper → React 19 hydration error #418 "server rendered HTML didn't
//       match the client". Phase 0 Empirical verified via unminified error
//       message: server tree `<div class="flex min-h-dvh flex-col">` vs client
//       expected `<Suspense>` at the App level.
//
//   (2) PRODUCTION silent blank: with no `fallback` prop the Suspense rendered
//       `null` while RouterProvider's route chain mounted. If anything in the
//       route tree (auth, lazy chunk, query) triggered Suspense even briefly,
//       the user saw a blank screen. Per W150 polish-followup hypothesis #7
//       (App.tsx:24 `<Suspense fallback={null}>` defaults to invisible). The
//       wrapper was redundant — TanStack Router has its own internal Suspense
//       boundaries for `lazy:` routes, and AuthProvider in __root.tsx renders
//       children unconditionally (AuthContext.tsx:145 — no `initializing` gate).
//
// Wave 152 Phase 1.7 — ADOPTED TanStack Start v1's official `<StartClient />`
// client entry per the W125 design doc deferral: "Phase 3 (W126+) may switch
// to <StartClient /> + hydrateRoot + auth-at-edge." Pre-W152, main.tsx mounted
// `<App>` with `<RouterProvider router={router} />` directly. That bypassed
// TanStack Start's `hydrateStart()` flow which is responsible for aligning
// the client router state with the server's prerendered TSR stream (the
// `self.$_TSR.router = ...` payload visible in the production HTML). The
// bypass produced two consequences traced via the user's reproducible blank
// /login screen + chrome-devtools-mcp `evaluate_script` timeouts:
//   • Client router state initialised from a fresh `createRouter()` while the
//     SSR-emitted `$_TSR.router` manifest entries (`s:"pending"`, `ssr:!1`)
//     were never consumed — TanStack Router's <Matches> then sat in an
//     ambiguous pending state.
//   • The pending state combined with Matches' internal `<Suspense
//     fallback={null}>` rendered nothing visible, and downstream chunks
//     (auth provider chain) ran synchronously enough to wedge V8 main thread
//     before any console/diagnostic output could land — DevTools wouldn't
//     even open on the wedged renderer.
// `<StartClient />` internally calls `hydrateStart()` → resolves the router
// against the SSR stream → renders <Await> → <RouterProvider>. This is the
// canonical TanStack Start v1 SPA-mode client entry shape; previously the
// project shipped a hand-rolled equivalent that diverged structurally.
//
// Bootstrap-error gate preserved for E2E tests (`__APP_BOOTSTRAP_FORCE_ERROR__`
// is set by tests/e2e/* fixtures to verify ErrorBoundary mounting).
export default function App() {
  if (
    typeof window !== "undefined" &&
    (window as typeof window & { __APP_BOOTSTRAP_FORCE_ERROR__?: boolean })
      .__APP_BOOTSTRAP_FORCE_ERROR__
  ) {
    throw new Error("Bootstrap failed")
  }

  return <StartClient />
}
