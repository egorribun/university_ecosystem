import { StrictMode } from "react"
import { renderToString } from "react-dom/server"
import { act, cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router"

import { Route } from "../_auth"
import { evaluateAuthGuard } from "../guards"
import { useAuthStore } from "@/stores/useAuthStore"
import { testUser } from "@/tests/mocks/handlers"

async function createAuthRouter(
  initialPath = "/settings",
  isServer = false,
  loginLoader?: () => Promise<void>
) {
  const root = createRootRoute({ component: () => <Outlet /> })
  const layout = createRoute({
    getParentRoute: () => root,
    id: "_auth",
    beforeLoad: ({ location }) => evaluateAuthGuard(useAuthStore.getState(), location),
    component: Route.options.component,
  })
  const settings = createRoute({
    getParentRoute: () => layout,
    path: "/settings",
    component: () => <h1>Protected settings</h1>,
  })
  const login = createRoute({
    getParentRoute: () => root,
    path: "/login",
    loader: loginLoader,
    component: () => <h1>Login destination</h1>,
  })
  const router = createRouter({
    routeTree: root.addChildren([layout.addChildren([settings]), login]),
    history: createMemoryHistory({ initialEntries: [initialPath] }),
    isServer,
  })
  await router.load()
  return router
}

beforeEach(() => {
  useAuthStore.setState({ user: null, loading: true, pendingMfa: null, authOperation: false })
})

afterEach(() => {
  cleanup()
  useAuthStore.setState({ user: null, loading: true, pendingMfa: null, authOperation: false })
  vi.unstubAllEnvs()
})

describe("Auth layout session settlement", () => {
  it("withholds the protected outlet and redirects when bootstrap settles anonymous", async () => {
    const destination = "/settings?tab=2#security"
    const router = await createAuthRouter(destination)
    render(<RouterProvider router={router as never} />)
    expect(screen.getByRole("heading", { name: "Protected settings" })).toBeVisible()

    act(() => useAuthStore.setState({ loading: false }))

    expect(screen.queryByRole("heading", { name: "Protected settings" })).not.toBeInTheDocument()
    await screen.findByRole("heading", { name: "Login destination" })
    expect(router.state.location.pathname).toBe("/login")
    expect(router.state.location.search).toEqual({ redirect: destination })
  })

  it("redirects a mounted authenticated route after logout without router invalidation", async () => {
    useAuthStore.setState({ user: testUser, loading: false })
    const router = await createAuthRouter()
    render(<RouterProvider router={router as never} />)
    expect(screen.getByRole("heading", { name: "Protected settings" })).toBeVisible()

    act(() => useAuthStore.setState({ user: null }))

    expect(screen.queryByRole("heading", { name: "Protected settings" })).not.toBeInTheDocument()
    await screen.findByRole("heading", { name: "Login destination" })
    expect(router.state.location.search).toEqual({ redirect: "/settings" })
  })

  it("keeps the outlet when bootstrap settles authenticated", async () => {
    const router = await createAuthRouter()
    render(<RouterProvider router={router as never} />)

    act(() => useAuthStore.setState({ user: testUser, loading: false }))

    expect(screen.getByRole("heading", { name: "Protected settings" })).toBeVisible()
    expect(router.state.location.pathname).toBe("/settings")
    expect(screen.queryByRole("heading", { name: "Login destination" })).not.toBeInTheDocument()
  })

  it("keeps the loading outlet while unrelated auth state changes", async () => {
    const router = await createAuthRouter()
    render(<RouterProvider router={router as never} />)

    act(() => useAuthStore.setState({ authOperation: true }))

    expect(screen.getByRole("heading", { name: "Protected settings" })).toBeVisible()
    expect(router.state.location.pathname).toBe("/settings")
  })

  it("preserves the explicit LHCI bypass after anonymous settlement", async () => {
    vi.stubEnv("VITE_LHCI", "true")
    const router = await createAuthRouter()
    render(<RouterProvider router={router as never} />)

    act(() => useAuthStore.setState({ loading: false }))

    expect(screen.getByRole("heading", { name: "Protected settings" })).toBeVisible()
    expect(router.state.location.pathname).toBe("/settings")
  })

  it("preserves the destination through StrictMode bootstrap settlement", async () => {
    const router = await createAuthRouter("/settings?tab=4")
    render(
      <StrictMode>
        <RouterProvider router={router as never} />
      </StrictMode>
    )

    act(() => useAuthStore.setState({ loading: false }))

    await screen.findByRole("heading", { name: "Login destination" })
    expect(router.state.location.search).toEqual({ redirect: "/settings?tab=4" })
  })

  it("uses the current destination when navigation changes during bootstrap", async () => {
    const router = await createAuthRouter("/settings?tab=0")
    render(<RouterProvider router={router as never} />)
    await act(() => router.navigate({ to: "/settings", search: { tab: 4 } }))

    act(() => useAuthStore.setState({ loading: false }))

    await screen.findByRole("heading", { name: "Login destination" })
    expect(router.state.location.search).toEqual({ redirect: "/settings?tab=4" })
  })

  it("retains the first destination and withholds the outlet while login remains pending", async () => {
    let release = () => {}
    const pending = new Promise<void>((resolve) => {
      release = resolve
    })
    const loginLoader = vi.fn(() => pending)
    const destination = "/settings?tab=2#security"
    const router = await createAuthRouter(destination, false, loginLoader)
    render(<RouterProvider router={router as never} />)

    try {
      act(() => useAuthStore.setState({ loading: false }))
      await waitFor(() => expect(loginLoader).toHaveBeenCalledTimes(1))

      expect(screen.queryByRole("heading", { name: "Protected settings" })).not.toBeInTheDocument()
      expect(screen.queryByRole("heading", { name: "Login destination" })).not.toBeInTheDocument()
      expect(router.state.location.pathname).toBe("/login")
      expect(router.state.location.search).toEqual({ redirect: destination })

      await act(async () => release())
      await screen.findByRole("heading", { name: "Login destination" })
      expect(loginLoader).toHaveBeenCalledTimes(1)
      expect(router.state.location.search).toEqual({ redirect: destination })
    } finally {
      await act(async () => release())
    }
  })

  it.each([
    ["anonymous", null],
    ["authenticated", testUser],
  ] as const)("preserves SSR outlet rendering while loading %s", async (_label, user) => {
    useAuthStore.setState({ user, loading: true })
    const router = await createAuthRouter("/settings", true)

    expect(renderToString(<RouterProvider router={router as never} />)).toContain(
      "Protected settings"
    )
    expect(router.state.location.pathname).toBe("/settings")
  })

  it("preserves the beforeLoad anonymous redirect with the intended destination", async () => {
    useAuthStore.setState({ loading: false })
    const router = await createAuthRouter("/settings?tab=2")

    await waitFor(() => expect(router.state.location.pathname).toBe("/login"))
    expect(router.state.location.search).toEqual({ redirect: "/settings?tab=2" })
  })

  it("preserves settled authenticated SSR rendering", async () => {
    useAuthStore.setState({ user: testUser, loading: false })
    const router = await createAuthRouter("/settings", true)

    expect(renderToString(<RouterProvider router={router as never} />)).toContain(
      "Protected settings"
    )
    expect(router.state.location.pathname).toBe("/settings")
  })
})
