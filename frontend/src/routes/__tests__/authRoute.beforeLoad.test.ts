import { QueryClient } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { RouterContext } from "@/router"
import { testUser } from "@/tests/mocks/handlers"
import { useAuthStore } from "@/stores/useAuthStore"
import { Route } from "../_auth"

type BeforeLoadArgs = Parameters<NonNullable<typeof Route.options.beforeLoad>>[0]

const initialStoreState = {
  user: null,
  loading: true,
  pendingMfa: null,
  authOperation: false,
}
const location = { href: "http://localhost/events?section=upcoming#today" }

const requestAuth = (role?: string): RouterContext["auth"] =>
  role
    ? { isAuth: true, user: { role }, loading: false }
    : { isAuth: false, user: null, loading: false }

async function runBeforeLoad(auth: RouterContext["auth"]): Promise<{
  destination: string
  redirectSearch: string | null
}> {
  const beforeLoad = Route.options.beforeLoad
  if (!beforeLoad) throw new Error("auth route beforeLoad is unavailable")

  try {
    await beforeLoad({
      context: {
        auth,
        queryClient: new QueryClient(),
      },
      location,
    } as unknown as BeforeLoadArgs)
    return { destination: "allow", redirectSearch: null }
  } catch (error) {
    const options = (error as { options?: { to?: string; search?: { redirect?: string } } }).options
    if (options?.to !== "/login") throw error
    return {
      destination: options.to,
      redirectSearch: typeof options.search?.redirect === "string" ? options.search.redirect : null,
    }
  }
}

afterEach(() => {
  vi.unstubAllEnvs()
  useAuthStore.setState(initialStoreState)
})

describe("authenticated route beforeLoad auth source", () => {
  it("redirects anonymous SSR requests to login with the requested destination", async () => {
    vi.stubEnv("SSR", true)
    vi.stubEnv("VITE_LHCI", "false")
    useAuthStore.setState(initialStoreState)

    await expect(runBeforeLoad(requestAuth())).resolves.toEqual({
      destination: "/login",
      redirectSearch: location.href,
    })
  })

  it("fails closed when an unauthenticated SSR context carries an admin user", async () => {
    vi.stubEnv("SSR", true)
    vi.stubEnv("VITE_LHCI", "false")
    useAuthStore.setState(initialStoreState)

    await expect(
      runBeforeLoad({
        isAuth: false,
        user: { ...testUser, role: "admin" },
        loading: false,
      })
    ).resolves.toEqual({
      destination: "/login",
      redirectSearch: location.href,
    })
  })

  it("allows an authenticated SSR request while the client store is pending", async () => {
    vi.stubEnv("SSR", true)
    vi.stubEnv("VITE_LHCI", "false")
    useAuthStore.setState(initialStoreState)

    await expect(runBeforeLoad(requestAuth("student"))).resolves.toEqual({
      destination: "allow",
      redirectSearch: null,
    })
  })

  it("keeps client auth pending despite settled RouterContext", async () => {
    vi.stubEnv("SSR", false)
    vi.stubEnv("VITE_LHCI", "false")
    useAuthStore.setState(initialStoreState)

    await expect(runBeforeLoad(requestAuth("student"))).resolves.toEqual({
      destination: "allow",
      redirectSearch: null,
    })
  })

  it("uses current client auth instead of stale anonymous RouterContext", async () => {
    vi.stubEnv("SSR", false)
    vi.stubEnv("VITE_LHCI", "false")
    useAuthStore.setState({
      user: { ...testUser, role: "admin" },
      loading: false,
    })

    await expect(runBeforeLoad(requestAuth())).resolves.toEqual({
      destination: "allow",
      redirectSearch: null,
    })
  })

  it("does not trust stale admin RouterContext over an anonymous client store", async () => {
    vi.stubEnv("SSR", false)
    vi.stubEnv("VITE_LHCI", "false")
    useAuthStore.setState({ user: null, loading: false })

    await expect(runBeforeLoad(requestAuth("admin"))).resolves.toEqual({
      destination: "/login",
      redirectSearch: location.href,
    })
  })
})
