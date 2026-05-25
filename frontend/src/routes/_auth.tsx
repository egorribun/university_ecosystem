import { createFileRoute, Outlet } from "@tanstack/react-router"
import { useAuthStore } from "@/stores/useAuthStore"
import { evaluateAuthGuard } from "./guards"

export const Route = createFileRoute("/_auth")({
  // Wave 128 SW2 — flip `ssr: false` → `ssr: true` so /dashboard
  // (W128 SW3) can opt INTO server-rendered component, and W127 SW6
  // annotations on /map + /activity (`ssr: 'data-only'`) finally
  // take effect (they were silently ignored under the more-restrictive
  // `false` parent). Per TanStack Start v1 SSR inheritance contract:
  // a child can ONLY make MORE restrictive (`false > 'data-only' >
  // true`). With parent now `true`, children opt DOWN to 'data-only'
  // (map + activity) or `false` (8 siblings that haven't been
  // SSR-audited yet — see explicit `ssr: false` annotations on
  // messenger.*, profile, settings, news.*, events.*, schedule).
  //
  // W127 SW1 hoisted AppProviders + ThemeProvider + AuthProvider into
  // __root.tsx RootComponent so MainLayout becomes SSR-safe. W128 SW1
  // bridges AuthProvider to RouterContext.auth via readSsrAuthHint so
  // Navbar renders with role-only stub on cold-load /dashboard.
  ssr: true,
  // Wave 174 SW1 — read live Zustand state instead of stale
  // `context.auth.*`. Pre-W152 Phase 1.7, App.tsx had
  // `<RouterProvider router={router} context={useAuth()}>` which made
  // RouterProvider re-render with fresh context every time useAuth()
  // returned a new value. W152 Phase 1.7 switched App.tsx to
  // `return <StartClient />` which internally invokes hydrateStart →
  // <Await><RouterProvider /></Await> WITHOUT a reactive context prop.
  // Result: `context.auth` was permanently stuck at DEFAULT_AUTH
  // (`isAuth: false`) on the client → every post-login navigate()
  // re-evaluated beforeLoad with stale context → redirect back to
  // /login. `useAuthStore.getState()` is a plain JS call (safe outside
  // React render phase) and reads from the source of truth that
  // useProfileSync syncs to via useAuthStore.setState (line 1099-1109).
  // Wave 179 SW8 — beforeLoad logic extracted to pure function
  // `evaluateAuthGuard` at `./guards.ts` for unit testability (closes
  // W174 §Honesty #4-routeGuards). All branches (loading + VITE_LHCI
  // bypass + unauth redirect with search.redirect) preserved exactly —
  // see guards.ts for full rationale + __tests__/guards.test.ts for
  // 11 unit tests covering the decision tree.
  beforeLoad: ({ location }) => evaluateAuthGuard(useAuthStore.getState(), location),
  component: () => <Outlet />,
})
