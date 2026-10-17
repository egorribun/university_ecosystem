import { QueryClient } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { RouterContext } from "@/router"
import { testUser } from "@/tests/mocks/handlers"
import { useAuthStore } from "@/stores/useAuthStore"
import { Route } from "../_admin"

type BeforeLoadArgs = Parameters<NonNullable<typeof Route.options.beforeLoad>>[0]

const initialStoreState = {
  user: null,
  loading: true,
  pendingMfa: null,
  authOperation: false,
}

const requestAuth = (role?: string): RouterContext["auth"] =>
  role
    ? { isAuth: true, user: { role }, loading: false }
    : { isAuth: false, user: null, loading: false }

async function runBeforeLoad(auth: RouterContext["auth"]): Promise<string> {
  const beforeLoad = Route.options.beforeLoad
  if (!beforeLoad) throw new Error("admin route beforeLoad is unavailable")

  try {
    await beforeLoad({
      context: {
        auth,
        queryClient: new QueryClient(),
      },
      location: { href: "/admin/notifications" },
    } as unknown as BeforeLoadArgs)
    return "allow"
  } catch (error) {
    const target = (error as { options?: { to?: string } }).options?.to
    if (target === "/dashboard" || target === "/login") return target
    throw error
  }
}

afterEach(() => {
  vi.unstubAllEnvs()
  useAuthStore.setState(initialStoreState)
})

describe("admin route beforeLoad auth source", () => {
  it.each([
    ["student", "/dashboard"],
    ["teacher", "/dashboard"],
    ["admin", "allow"],
  ])("uses verified SSR request context for %s", async (role, expected) => {
    vi.stubEnv("SSR", true)
    useAuthStore.setState(initialStoreState)

    await expect(runBeforeLoad(requestAuth(role))).resolves.toBe(expected)
  })

  it("redirects an anonymous SSR request to login", async () => {
    vi.stubEnv("SSR", true)
    useAuthStore.setState(initialStoreState)

    await expect(runBeforeLoad(requestAuth())).resolves.toBe("/login")
  })

  it("fails closed when an unauthenticated SSR context carries an admin user", async () => {
    vi.stubEnv("SSR", true)
    useAuthStore.setState(initialStoreState)

    await expect(
      runBeforeLoad({
        isAuth: false,
        user: { ...testUser, role: "admin" },
        loading: false,
      })
    ).resolves.toBe("/login")
  })

  it("keeps the client pending while Zustand is loading despite a settled context", async () => {
    vi.stubEnv("SSR", false)
    useAuthStore.setState(initialStoreState)

    await expect(runBeforeLoad(requestAuth("student"))).resolves.toBe("allow")
  })

  it("uses current client Zustand auth when RouterContext is stale", async () => {
    vi.stubEnv("SSR", false)
    useAuthStore.setState({
      user: { ...testUser, role: "admin" },
      loading: false,
    })

    await expect(runBeforeLoad(requestAuth())).resolves.toBe("allow")
  })

  it("does not trust stale admin RouterContext over a non-admin client store", async () => {
    vi.stubEnv("SSR", false)
    useAuthStore.setState({ user: { ...testUser, role: "student" }, loading: false })

    await expect(runBeforeLoad(requestAuth("admin"))).resolves.toBe("/dashboard")
  })
})
