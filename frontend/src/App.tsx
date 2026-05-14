import { RouterProvider } from "@tanstack/react-router"
import { router } from "./router"

// Wave 127 SW1 — App.tsx is now a thin RouterProvider mount. AppProviders +
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

  return <RouterProvider router={router} />
}
