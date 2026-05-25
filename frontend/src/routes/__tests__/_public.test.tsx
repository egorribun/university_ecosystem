/**
 * Wave 178 SW1 — Approach 1 extension regression test (closes W177 §Honesty #2).
 *
 * Verifies the reactive `useEffect` in `_public.tsx`'s `PublicLayout`
 * redirects authed users away from ALL child routes under /_public/ via a
 * single layout-level mechanism.
 *
 * The standard `renderWithRouter` helper builds a FLAT route tree (per its
 * docstring caveat at `src/tests/helpers/renderWithRouter.tsx` lines 50-54)
 * and does NOT exercise layout routes — so this suite builds a CUSTOM tree
 * with `PublicLayout` as the parent layout, three representative child
 * routes (/forgot-password, /register, /reset-password/$token) as
 * children, and /dashboard as a sibling root-level route.
 *
 * Initial state: useAuthStore.user = null + loading = true (matches the
 * Zustand store's initial state at useAuthStore.ts:22-26). After mount,
 * we call `useAuthStore.setState({ user: testUser, loading: false })`
 * inside `act()` to simulate AuthProvider's useProfileSync settling
 * /users/me + populating the store. The PublicLayout's useEffect observes
 * the user transition null→set and fires `navigate({ to: "/dashboard",
 * replace: true })`. We assert that the /dashboard marker becomes visible.
 *
 * `afterEach` resets `useAuthStore` to its initial shape to match the
 * cross-test pollution discipline established in Login.test.tsx:65-70
 * (W177 SW2 pattern).
 *
 * Negative case: unauth user stays on /forgot-password (useEffect's
 * `if (user)` branch is false → no navigate).
 */
import { render, screen, waitFor, act } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { LazyMotion, domAnimation } from "framer-motion"

import { PublicLayout } from "../_public"
import { useAuthStore } from "@/stores/useAuthStore"
import { testUser } from "@/tests/mocks/handlers"

async function renderPublicChild(initialPath: string) {
  const rootRoute = createRootRoute({ component: () => <Outlet /> })
  const publicLayout = createRoute({
    getParentRoute: () => rootRoute,
    id: "_public",
    component: PublicLayout,
  })
  const forgotChild = createRoute({
    getParentRoute: () => publicLayout,
    path: "/forgot-password",
    component: () => <div>Forgot child</div>,
  })
  const registerChild = createRoute({
    getParentRoute: () => publicLayout,
    path: "/register",
    component: () => <div>Register child</div>,
  })
  const resetChild = createRoute({
    getParentRoute: () => publicLayout,
    path: "/reset-password/$token",
    component: () => <div>Reset child</div>,
  })
  const dashboardRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/dashboard",
    component: () => <div>Welcome!</div>,
  })

  const routeTree = rootRoute.addChildren([
    publicLayout.addChildren([forgotChild, registerChild, resetChild]),
    dashboardRoute,
  ])

  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: 0, gcTime: Number.POSITIVE_INFINITY },
      mutations: { retry: 0 },
    },
  })

  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [initialPath] }),
  })
  await router.load()

  return render(
    <QueryClientProvider client={client}>
      <LazyMotion features={domAnimation}>
        <RouterProvider router={router as never} />
      </LazyMotion>
    </QueryClientProvider>
  )
}

describe("PublicLayout reactive redirect (W178 SW1, W177 §Honesty #2)", () => {
  afterEach(() => {
    // Wave 177 SW2 pattern (Login.test.tsx:65-70) — reset useAuthStore
    // between tests so prior-test user state doesn't bleed into the next
    // test's render and fire the W178 useEffect on mount. Match the
    // initial state from useAuthStore.ts:22-26 (loading:true optimistic).
    useAuthStore.setState({
      user: null,
      loading: true,
      pendingMfa: null,
      authOperation: false,
    })
  })

  it.each([
    ["/forgot-password", "Forgot child"],
    ["/register", "Register child"],
    ["/reset-password/sample-token-123", "Reset child"],
  ])("redirects authed user away from %s to /dashboard", async (initialPath, childMarker) => {
    await renderPublicChild(initialPath)

    // Initial render: useAuthStore.user is null + loading is true →
    // PublicLayout's useEffect short-circuits → child route renders.
    expect(screen.getByText(childMarker)).toBeInTheDocument()
    expect(screen.queryByText("Welcome!")).not.toBeInTheDocument()

    // Simulate AuthProvider's useProfileSync settling /users/me →
    // setUser populates the store. PublicLayout's useEffect observes
    // the user transition null→testUser → fires navigate to /dashboard.
    act(() => {
      useAuthStore.setState({ user: testUser, loading: false })
    })

    await waitFor(() => expect(screen.getByText("Welcome!")).toBeInTheDocument())
  })

  it("leaves unauth user on /forgot-password (negative case)", async () => {
    await renderPublicChild("/forgot-password")

    // user=null + loading=true → no redirect.
    expect(screen.getByText("Forgot child")).toBeInTheDocument()
    expect(screen.queryByText("Welcome!")).not.toBeInTheDocument()
  })
})
