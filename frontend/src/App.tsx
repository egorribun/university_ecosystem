import { Suspense } from "react"
import { RouterProvider } from "@tanstack/react-router"
import { AppProviders } from "./AppProviders"
import { router } from "./router"
import { useAuth } from "./contexts/AuthContext"
import { queryClient } from "./app/queryClient"

/**
 * Inner app — injects auth context into router
 */
function InnerApp() {
  const auth = useAuth()

  // Check for forced bootstrap error (used in E2E tests)
  if (
    typeof window !== "undefined" &&
    (window as typeof window & { __APP_BOOTSTRAP_FORCE_ERROR__?: boolean })
      .__APP_BOOTSTRAP_FORCE_ERROR__
  ) {
    throw new Error("Bootstrap failed")
  }

  return (
    <Suspense>
      <RouterProvider
        router={router}
        context={{
          auth: {
            isAuth: auth.isAuth,
            user: auth.user ? { role: auth.user.role ?? "student" } : null,
            loading: auth.loading,
          },
          queryClient,
        }}
      />
    </Suspense>
  )
}

export default function App() {
  return (
    <AppProviders>
      <InnerApp />
    </AppProviders>
  )
}
