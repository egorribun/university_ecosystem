import { Suspense } from "react"
import { RouterProvider } from "@tanstack/react-router"
import { router } from "./router"

// Wave 127 SW1 — App.tsx is now a thin RouterProvider mount. AppProviders +
// ThemeProvider were hoisted to __root.tsx RootComponent so they're available
// during SSR. Auth context is populated by router.ts createAppRouter() which
// reads globalThis.__ssrAuthGetter__ on server (W126 SW4 pattern); on client
// it falls back to DEFAULT_AUTH and AuthProvider in __root.tsx (which mounts
// inside the router tree) reads useAuthStore directly for real-time updates.
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

  return (
    <Suspense>
      <RouterProvider router={router} />
    </Suspense>
  )
}
