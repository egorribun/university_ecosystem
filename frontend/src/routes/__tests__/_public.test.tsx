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
import { AsyncLocalStorage } from "node:async_hooks"
import { render, screen, waitFor, act } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  isRedirect,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { LazyMotion, domAnimation } from "framer-motion"

import { PublicLayout, Route } from "../_public"
import type { RouterContext } from "@/router"
import { useAuthStore } from "@/stores/useAuthStore"
import { testUser } from "@/tests/mocks/handlers"

type PublicBeforeLoadArgs = Parameters<NonNullable<typeof Route.options.beforeLoad>>[0]

const requestAuth = (role?: string): RouterContext["auth"] =>
  role
    ? { isAuth: true, user: { role }, loading: false }
    : { isAuth: false, user: null, loading: false }

async function runPublicBeforeLoad(
  auth: RouterContext["auth"],
  {
    queryClient = new QueryClient(),
    redirect,
  }: { queryClient?: QueryClient; redirect?: unknown } = {}
): Promise<string> {
  const beforeLoad = Route.options.beforeLoad
  if (!beforeLoad) throw new Error("public route beforeLoad is unavailable")

  try {
    await beforeLoad({
      context: { auth, queryClient },
      location: { href: "/login", search: { redirect } },
    } as unknown as PublicBeforeLoadArgs)
    return "allow"
  } catch (error) {
    if (isRedirect(error)) {
      const target = error.headers.get("Location") ?? error.options.to
      if (typeof target === "string") return target
    }
    throw error
  }
}

describe("public route beforeLoad auth source", () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
    useAuthStore.setState({ user: null, loading: true, pendingMfa: null, authOperation: false })
  })

  it("redirects an authenticated SSR request even when the shared store is cold", async () => {
    vi.stubEnv("SSR", true)
    useAuthStore.setState({ user: null, loading: true })

    await expect(runPublicBeforeLoad(requestAuth("student"))).resolves.toBe("/dashboard")
  })

  it("allows an anonymous SSR request despite an authenticated shared store", async () => {
    vi.stubEnv("SSR", true)
    useAuthStore.setState({ user: testUser, loading: false })

    await expect(runPublicBeforeLoad(requestAuth())).resolves.toBe("allow")
  })

  it("ignores an SSR user when the request is not authenticated", async () => {
    vi.stubEnv("SSR", true)
    useAuthStore.setState({ user: testUser, loading: false })

    await expect(
      runPublicBeforeLoad({ isAuth: false, user: { role: "admin" }, loading: false })
    ).resolves.toBe("allow")
  })

  it("allows a pending SSR request despite an authenticated shared store", async () => {
    vi.stubEnv("SSR", true)
    useAuthStore.setState({ user: testUser, loading: false })

    await expect(
      runPublicBeforeLoad({ isAuth: true, user: { role: "student" }, loading: true })
    ).resolves.toBe("allow")
  })

  it("keeps interleaved SSR request routers independent of the shared store", async () => {
    vi.stubEnv("SSR", true)
    useAuthStore.setState({ user: testUser, loading: false })
    const anonymous = requestAuth()
    const authenticated = requestAuth("student")
    const storage = new AsyncLocalStorage<RouterContext["auth"]>()
    const previousGetter = globalThis.__ssrAuthGetter__
    const { getRouter } = await import("@/router")
    globalThis.__ssrAuthGetter__ = () => storage.getStore()

    try {
      const runRequest = (auth: RouterContext["auth"]) =>
        storage.run(auth, async () => {
          const context = getRouter().options.context
          await Promise.resolve()
          const decision = await runPublicBeforeLoad(context.auth, {
            queryClient: context.queryClient,
          })
          return { context, decision }
        })
      const [first, second] = await Promise.all([runRequest(anonymous), runRequest(authenticated)])

      expect(first.context.auth).toBe(anonymous)
      expect(second.context.auth).toBe(authenticated)
      expect(first.context.queryClient).not.toBe(second.context.queryClient)
      expect([first.decision, second.decision]).toEqual(["allow", "/dashboard"])
    } finally {
      globalThis.__ssrAuthGetter__ = previousGetter
      storage.disable()
    }
  })

  it("checks absolute redirects against each interleaved SSR request's own origin", async () => {
    vi.stubEnv("SSR", true)
    const storage = new AsyncLocalStorage<{ auth: RouterContext["auth"]; origin: string }>()
    vi.stubGlobal("__ssrAuthGetter__", () => storage.getStore()?.auth)
    vi.stubGlobal("__ssrOriginGetter__", () => storage.getStore()?.origin)
    const { getRouter } = await import("@/router")

    try {
      const runRequest = (origin: string) =>
        storage.run({ auth: requestAuth("student"), origin }, async () => {
          const context = getRouter().options.context
          await Promise.resolve()
          return runPublicBeforeLoad(context.auth, {
            queryClient: context.queryClient,
            redirect: "https://first.example/events?tab=1#section",
          })
        })

      await expect(
        Promise.all([runRequest("https://first.example"), runRequest("https://second.example")])
      ).resolves.toEqual(["/events?tab=1#section", "/dashboard"])
    } finally {
      storage.disable()
    }
  })

  it.each([
    ["/events?tab=1#section", "/events?tab=1#section"],
    ["https://app.example/events?tab=1#section", "/events?tab=1#section"],
    ["/schedules/../events?tab=1#section", "/events?tab=1#section"],
    ["/events/my%20events", "/events/my%20events"],
  ])("preserves a safe SSR redirect %s", async (destination, expected) => {
    vi.stubEnv("SSR", true)
    vi.stubGlobal("__ssrOriginGetter__", () => "https://app.example")
    useAuthStore.setState({ user: null, loading: true })

    await expect(
      runPublicBeforeLoad(requestAuth("student"), { redirect: destination })
    ).resolves.toBe(expected)
  })

  it.each([
    undefined,
    null,
    "",
    "events",
    "//evil.test/path",
    "/\\evil.test/path",
    "/\t/evil.test/path",
    "https://evil.test/path",
    "https://user@app.example/events",
    "javascript:alert(1)",
    "http://",
    "/events/%ZZ",
    "https://app.example//evil.test/path",
    "/%2Fevil.test/path",
    "/events%2F..%2Flogin",
    "/events%5cpath",
    "/%256cogin",
    "/events%0Apath",
    "/events%7Fpath",
    "/login",
    "https://app.example/login",
    "/LOGIN?redirect=/events",
    "/register",
    "/forgot-password",
    "/reset-password",
    "/reset-password/token",
    "/%2e%2e/login",
    "/%6cogin",
  ])("falls back for unsafe or looping SSR redirect %s", async (destination) => {
    vi.stubEnv("SSR", true)
    vi.stubGlobal("__ssrOriginGetter__", () => "https://app.example")

    await expect(
      runPublicBeforeLoad(requestAuth("student"), { redirect: destination })
    ).resolves.toBe("/dashboard")
  })

  it("rejects absolute SSR redirects when the request origin is unavailable", async () => {
    vi.stubEnv("SSR", true)
    vi.stubGlobal("__ssrOriginGetter__", undefined)

    await expect(
      runPublicBeforeLoad(requestAuth("student"), {
        redirect: "https://app.example/events?tab=1#section",
      })
    ).resolves.toBe("/dashboard")
  })

  it("preserves relative SSR redirects when the request origin is unavailable", async () => {
    vi.stubEnv("SSR", true)
    vi.stubGlobal("__ssrOriginGetter__", undefined)

    await expect(
      runPublicBeforeLoad(requestAuth("student"), { redirect: "/events?tab=1#section" })
    ).resolves.toBe("/events?tab=1#section")
  })

  it.each([
    ["/events?tab=1#section", "/events?tab=1#section"],
    ["https://evil.test/path", "/dashboard"],
    ["/%2e%2e/login", "/dashboard"],
  ])(
    "returns a sanitized SSR location for %s from an actual server router load",
    async (destination, expected) => {
      vi.stubEnv("SSR", true)
      vi.stubGlobal("__ssrOriginGetter__", () => "https://app.example")
      vi.stubGlobal("__ssrAuthGetter__", () => requestAuth("student"))
      const { getRouter } = await import("@/router")
      const router = getRouter()
      router.update({
        isServer: true,
        origin: "https://app.example",
        context: router.options.context,
        history: createMemoryHistory({
          initialEntries: [`/login?redirect=${encodeURIComponent(destination)}`],
        }),
      })

      await router.load()

      const result = router._serverResult
      expect(result?.type).toBe("redirect")
      if (result?.type !== "redirect") throw new Error("server router did not redirect")
      expect(result.redirect.status).toBe(307)
      expect(result.redirect.headers.get("Location")).toBe(expected)
    }
  )

  it("does not redirect a pending or anonymous SSR request with a redirect parameter", async () => {
    vi.stubEnv("SSR", true)

    await expect(runPublicBeforeLoad(requestAuth(), { redirect: "/events" })).resolves.toBe("allow")
    await expect(
      runPublicBeforeLoad(
        { isAuth: true, user: { role: "student" }, loading: true },
        { redirect: "/events" }
      )
    ).resolves.toBe("allow")
  })

  it("uses live client state as it changes even when router context is stale", async () => {
    vi.stubEnv("SSR", false)
    const staleAuth = requestAuth("student")
    useAuthStore.setState({ user: null, loading: true })
    await expect(runPublicBeforeLoad(staleAuth)).resolves.toBe("allow")

    useAuthStore.setState({ user: testUser, loading: false })
    await expect(runPublicBeforeLoad(requestAuth(), { redirect: "/events" })).resolves.toBe(
      "/dashboard"
    )

    useAuthStore.setState({ user: null, loading: false })
    await expect(runPublicBeforeLoad(staleAuth)).resolves.toBe("allow")
  })
})

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
