import { useEffect, type PropsWithChildren } from "react"
import { act, cleanup, renderHook, waitFor } from "@testing-library/react"
import { QueryClientProvider, useQuery, type QueryClient } from "@tanstack/react-query"
import { hydrateRoot, type Root } from "react-dom/client"
import { renderToString } from "react-dom/server"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import api from "@/api/client"
import { createQueryClient, setQueryCacheIdentity } from "@/app/queryClient"
import { AuthProvider, useAuth } from "@/contexts/AuthContext"
import { currentUserQueryKey, currentUserQueryOptions } from "@/api/hooks/users"
import { testUser } from "@/tests/mocks/handlers"
import { useAuthStore } from "@/stores/useAuthStore"
import { acceptBrowserSessionGeneration } from "@/stores/sessionEpoch"
import { getRouter, type RouterContext } from "@/router"

type SsrAuthGetter = (() => RouterContext["auth"] | undefined) | undefined

declare global {
  var __ssrAuthGetter__: SsrAuthGetter
}

const snapshotStorage = (storage: Storage): Array<[string, string]> => {
  const entries: Array<[string, string]> = []
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index)
    if (key !== null) entries.push([key, storage.getItem(key)!])
  }
  return entries
}
const restoreStorage = (storage: Storage, entries: Array<[string, string]>) => {
  storage.clear()
  for (const [key, value] of entries) storage.setItem(key, value)
}

/**
 * Wave 134 SW1 — Bridge mechanism integration tests.
 *
 * Asserts the cache-identity invariant introduced by the bridge:
 *
 *   useProfileSync's auto-fetch effect now calls
 *     queryClient.fetchQuery(currentUserQueryOptions())
 *   instead of fetchCurrentUser({signal}) directly.
 *
 * When an SSR loader pre-populates the cache via
 *   context.queryClient.ensureQueryData(currentUserQueryOptions())
 * the bridged effect must consume that cache (within staleTime) — NOT fire
 * a duplicate /users/me network call.
 *
 * Closes W133 §Honesty probe #3 + #4 (disjoint-cache risk between SSR
 * loaders and useProfileSync's auto-fetch effect — duplicated network
 * calls hitting the backend twice on cold-load of /dashboard, /profile,
 * /settings, /schedule).
 *
 * The factory's queryFn delegates to the SAME `fetchCurrentUser` function
 * used pre-W134, so retry-on-500-with-cleared-cache + cache-envelope
 * header logic is preserved (covered by AuthContext.requests.test.tsx).
 */

describe("Wave 134 SW1 — useProfileSync bridge", () => {
  let savedAuth: ReturnType<typeof useAuthStore.getState>
  let savedLocal: Array<[string, string]>
  let savedSession: Array<[string, string]>
  let savedSsrAuthGetter: SsrAuthGetter
  let clients: QueryClient[]
  let operations: Array<Promise<PromiseSettledResult<unknown>>>
  const track = <T,>(promise: Promise<T>): Promise<T> => {
    operations.push(
      promise.then(
        (value) => ({ status: "fulfilled" as const, value }),
        (reason: unknown) => ({ status: "rejected" as const, reason })
      )
    )
    return promise
  }
  const createOwnedClient = () => {
    const client = createQueryClient()
    clients.push(client)
    return client
  }

  beforeEach(() => {
    savedAuth = useAuthStore.getState()
    savedLocal = snapshotStorage(localStorage)
    savedSession = snapshotStorage(sessionStorage)
    savedSsrAuthGetter = globalThis.__ssrAuthGetter__
    clients = []
    operations = []
    // A previous authenticated fixture must not invalidate a newly prefetched
    // client when the next AuthProvider starts its independent cold bootstrap.
    useAuthStore.setState(useAuthStore.getInitialState(), true)
    localStorage.clear()
    sessionStorage.clear()
    acceptBrowserSessionGeneration()

    // Preserve native crypto while owning every pending persistence primitive.
    const subtle = window.crypto.subtle
    const importKey = subtle.importKey.bind(subtle)
    const deriveKey = subtle.deriveKey.bind(subtle)
    const encrypt = subtle.encrypt.bind(subtle)
    const decrypt = subtle.decrypt.bind(subtle)
    const verify = subtle.verify.bind(subtle)
    vi.spyOn(subtle, "importKey").mockImplementation((...args) =>
      track(Reflect.apply(importKey, subtle, args) as Promise<CryptoKey>)
    )
    vi.spyOn(subtle, "deriveKey").mockImplementation((...args) => track(deriveKey(...args)))
    vi.spyOn(subtle, "encrypt").mockImplementation((...args) => track(encrypt(...args)))
    vi.spyOn(subtle, "decrypt").mockImplementation((...args) => track(decrypt(...args)))
    vi.spyOn(subtle, "verify").mockImplementation((...args) => track(verify(...args)))
  })

  afterEach(async () => {
    const failures: unknown[] = []
    const attempt = (action: () => void) => {
      try {
        action()
      } catch (error) {
        failures.push(error)
      }
    }
    try {
      attempt(cleanup)
      for (const client of clients) {
        try {
          await client.cancelQueries()
        } catch (error) {
          failures.push(error)
        }
      }
      await act(async () => {
        let drained = 0
        while (drained < operations.length) {
          const batch = operations.slice(drained)
          drained = operations.length
          for (const outcome of await Promise.all(batch)) {
            if (outcome.status === "rejected") failures.push(outcome.reason)
          }
        }
      })
    } finally {
      for (const client of clients) attempt(() => client.clear())
      attempt(() => vi.restoreAllMocks())
      attempt(() => useAuthStore.setState(savedAuth, true))
      attempt(() => restoreStorage(localStorage, savedLocal))
      attempt(() => restoreStorage(sessionStorage, savedSession))
      attempt(() => {
        globalThis.__ssrAuthGetter__ = savedSsrAuthGetter
      })
      attempt(acceptBrowserSessionGeneration)
    }
    if (failures.length) throw new AggregateError(failures, "Auth bridge cleanup failed")
  })

  it("queryKey shape matches across both definition sites", () => {
    // useProfileSync.ts:58 + api/hooks/users.ts:52 both export the same
    // tuple — cache identity is unified at the queryKey level. If either
    // site drifts, the bridge breaks silently (different cache slots).
    expect(currentUserQueryKey).toEqual(["users", "me"])
    expect(currentUserQueryOptions().queryKey).toEqual(currentUserQueryKey)
  })

  it("rejects a current-user cache without a matching committed owner", async () => {
    // A query value alone does not establish which authenticated session owns
    // it. The browser must fetch the current profile instead of trusting this
    // orphaned cache row.
    const queryClient = createOwnedClient()
    const unownedProfile = { ...testUser, id: "unowned-cache-profile" }
    setQueryCacheIdentity(null)
    queryClient.setQueryData(currentUserQueryKey, unownedProfile)

    const getSpy = vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/auth/session/signing-key") {
        return Promise.resolve({ data: { signing_key: "session-key" } } as any)
      }
      if (url === "/users/me") {
        return Promise.resolve({ data: testUser } as any)
      }
      throw new Error(`Unexpected url: ${url}`)
    })

    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>
        <AuthProvider>{children}</AuthProvider>
      </QueryClientProvider>
    )

    const { result } = renderHook(() => useAuth(), { wrapper })
    expect(result.current.user?.id).not.toBe(unownedProfile.id)
    await waitFor(() => {
      expect(result.current.user?.id).toBe(testUser.id)
      expect(queryClient.getQueryData<{ id: string }>(currentUserQueryKey)?.id).toBe(testUser.id)
    })

    const userMeCalls = getSpy.mock.calls.filter(([url]) => url === "/users/me")
    expect(userMeCalls).toHaveLength(1)
  })

  it.each([
    ["a primitive", 42],
    ["an object without an id", { email: "orphan@example.invalid" }],
    ["an unsupported boolean id", { id: true, email: "orphan@example.invalid" }],
    ["a numeric id from another owner", { id: 42, email: "orphan@example.invalid" }],
  ])("does not expose %s from the current-user cache", async (_shape, cachedValue) => {
    setQueryCacheIdentity(null)
    const queryClient = createOwnedClient()
    queryClient.setQueryData(currentUserQueryKey, cachedValue, { updatedAt: 0 })
    const profileObservations: unknown[] = []
    const getSpy = vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") return Promise.resolve({ data: testUser } as any)
      if (url === "/auth/session/signing-key") {
        return Promise.resolve({ data: { signing_key: "session-key" } } as any)
      }
      throw new Error(`Unexpected url: ${url}`)
    })
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>
        <AuthProvider>{children}</AuthProvider>
      </QueryClientProvider>
    )

    const { result } = renderHook(
      () => {
        const { user } = useAuth()
        const profile = useQuery({ ...currentUserQueryOptions(), enabled: false })
        useEffect(() => {
          profileObservations.push(profile.data)
        }, [profile.data])
        return { user }
      },
      { wrapper }
    )

    await waitFor(() => expect(result.current.user?.id).toBe(testUser.id))
    expect(queryClient.getQueryData(currentUserQueryKey)).toEqual(testUser)
    expect(profileObservations.some((profile) => profile === cachedValue)).toBe(false)
    expect(getSpy.mock.calls.filter(([url]) => url === "/users/me")).toHaveLength(1)
  })

  it("falls through to network fetch when cache is empty (factory queryFn invoked)", async () => {
    // No pre-populated cache — bridged effect should invoke factory's
    // queryFn → fetchCurrentUser → api.get("/users/me", ...). Behavior
    // matches pre-W134 useProfileSync auto-fetch path (single network
    // call, not two; factory dedups concurrent calls).
    const queryClient = createOwnedClient()

    const getSpy = vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") {
        return Promise.resolve({ data: testUser } as any)
      }
      if (url === "/auth/session/signing-key") {
        return Promise.resolve({ data: { signing_key: "session-key" } } as any)
      }
      throw new Error(`Unexpected url: ${url}`)
    })

    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>
        <AuthProvider>{children}</AuthProvider>
      </QueryClientProvider>
    )

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.user?.id).toBe(testUser.id)
    })

    // /users/me called exactly once via the factory's queryFn delegation
    // path — preserves pre-W134 single-fetch behaviour.
    const userMeCalls = getSpy.mock.calls.filter(([url]) => url === "/users/me")
    expect(userMeCalls).toHaveLength(1)
  })

  it("populates queryClient cache after a network fetch (cache-write side effect)", async () => {
    // Wave 134 SW1 closing-the-loop assertion: after the bridged auto-fetch
    // fires (cache empty → network → user state), the SAME queryClient
    // cache slot is populated for any future consumer (e.g. a sibling
    // useQuery(currentUserQueryOptions()) mounted later) — no separate
    // re-fetch needed.
    const queryClient = createOwnedClient()

    vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") {
        return Promise.resolve({ data: testUser } as any)
      }
      if (url === "/auth/session/signing-key") {
        return Promise.resolve({ data: { signing_key: "session-key" } } as any)
      }
      throw new Error(`Unexpected url: ${url}`)
    })

    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>
        <AuthProvider>{children}</AuthProvider>
      </QueryClientProvider>
    )

    renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      const cached = queryClient.getQueryData(currentUserQueryKey)
      expect(cached).toBeDefined()
      expect((cached as any)?.id).toBe(testUser.id)
    })
  })

  it("keeps request-only profile data out of transfer and hydrates behind the owner barrier", async () => {
    const requestProfile = {
      ...testUser,
      id: "request-only-profile-id",
      email: "request-only-profile@example.invalid",
    }
    const browserProfile = {
      ...testUser,
      id: "browser-confirmed-profile-id",
      email: "browser-confirmed-profile@example.invalid",
    }
    let browserRequestStarted = false
    let resolveBrowserResponse: ((value: { data: typeof browserProfile }) => void) | undefined
    const browserResponse = new Promise<{ data: typeof browserProfile }>((resolve) => {
      resolveBrowserResponse = resolve
    })
    let usersMeCallCount = 0
    const profileReads: Array<{
      authUserId: string | null
      cacheProfileId: string | null
    }> = []
    const getSpy = vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") {
        usersMeCallCount += 1
        if (usersMeCallCount === 1) return Promise.resolve({ data: requestProfile } as any)
        browserRequestStarted = true
        return browserResponse as any
      }
      if (url === "/auth/session/signing-key") {
        return Promise.resolve({ data: { signing_key: "session-key" } } as any)
      }
      throw new Error(`Unexpected url: ${url}`)
    })

    vi.stubEnv("SSR", true)
    const requestAuth: RouterContext["auth"] = {
      isAuth: true,
      user: { role: "student" },
      loading: false,
    }
    globalThis.__ssrAuthGetter__ = () => requestAuth
    const serverRouter = getRouter()
    const serverClient = serverRouter.options.context.queryClient
    clients.push(serverClient)
    const secondRequestClient = getRouter().options.context.queryClient
    clients.push(secondRequestClient)
    expect(serverClient).not.toBe(secondRequestClient)
    await serverClient.ensureQueryData(currentUserQueryOptions())
    expect(serverClient.getQueryData(currentUserQueryKey)).toEqual(requestProfile)

    const ProfileRouteShell = ({
      assertRequestCache = false,
    }: {
      assertRequestCache?: boolean
    }) => {
      const { user } = useAuth()
      const currentProfile = useQuery({
        ...currentUserQueryOptions(),
        enabled: false,
      })
      if (assertRequestCache && currentProfile.data?.id !== requestProfile.id) {
        throw new Error("The server profile route did not read its request-scoped profile cache")
      }
      useEffect(() => {
        profileReads.push({
          authUserId: user?.id ?? null,
          cacheProfileId: currentProfile.data?.id ?? null,
        })
      }, [currentProfile.data?.id, user?.id])
      return <main data-testid="profile-route-shell">Authenticated profile route</main>
    }
    const routeTree = (
      <QueryClientProvider client={serverClient}>
        <AuthProvider>
          <ProfileRouteShell assertRequestCache />
        </AuthProvider>
      </QueryClientProvider>
    )
    const serverMarkup = renderToString(routeTree)
    expect(getSpy.mock.calls.filter(([url]) => url === "/users/me")).toHaveLength(1)
    expect(serverMarkup).toContain("profile-route-shell")
    expect(serverMarkup).not.toContain(requestProfile.id)
    expect(serverMarkup).not.toContain(requestProfile.email)

    const transferred = await serverRouter.options.dehydrate?.()
    if (!transferred) throw new Error("Expected the request router's dehydration result")
    expect(
      transferred.queries.some(
        (query) => JSON.stringify(query.queryKey) === JSON.stringify(currentUserQueryKey)
      )
    ).toBe(false)
    const transferJson = JSON.stringify(transferred)
    expect(transferJson).not.toContain(requestProfile.id)
    expect(transferJson).not.toContain(requestProfile.email)

    vi.stubEnv("SSR", false)
    globalThis.__ssrAuthGetter__ = undefined
    setQueryCacheIdentity(null)
    const browserClient = createOwnedClient()
    expect(browserClient.getQueryData(currentUserQueryKey)).toBeUndefined()

    const container = document.createElement("div")
    container.id = "root"
    container.setAttribute("data-ssr-auth", "authenticated:student")
    container.innerHTML = serverMarkup
    document.body.appendChild(container)
    const hydrationErrors: unknown[] = []
    let root: Root | undefined
    const browserTree = (
      <QueryClientProvider client={browserClient}>
        <AuthProvider>
          <ProfileRouteShell />
        </AuthProvider>
      </QueryClientProvider>
    )

    try {
      await act(async () => {
        root = hydrateRoot(container, browserTree, {
          onRecoverableError: (error) => hydrationErrors.push(error),
        })
      })
      await waitFor(() => expect(browserRequestStarted).toBe(true))
      expect(
        hydrationErrors.map((error) => (error instanceof Error ? error.message : String(error)))
      ).toEqual([])
      expect(profileReads.some(({ cacheProfileId }) => cacheProfileId === requestProfile.id)).toBe(
        false
      )

      // Keep the browser request pending through hydration so the test can
      // distinguish an actual markup mismatch from a deliberately immediate
      // auth response racing React's hydration commit.
      await act(async () => {
        resolveBrowserResponse?.({ data: browserProfile })
        await browserResponse
      })
      await waitFor(() => {
        expect(browserClient.getQueryData<{ id: string }>(currentUserQueryKey)?.id).toBe(
          browserProfile.id
        )
        expect(profileReads.some(({ authUserId }) => authUserId === browserProfile.id)).toBe(true)
        expect(container.querySelector('[data-testid="profile-route-shell"]')).not.toBeNull()
      })
      expect(
        hydrationErrors.map((error) => (error instanceof Error ? error.message : String(error)))
      ).toEqual([])

      // A stale server-owned profile introduced into the active browser cache
      // after owner B is confirmed must close the subtree before a committed
      // consumer can observe it.
      await act(async () => {
        browserClient.setQueryData(currentUserQueryKey, requestProfile)
      })
      await waitFor(() => {
        expect(container.querySelector('[data-testid="profile-route-shell"]')).toBeNull()
      })
      expect(
        profileReads.some(
          ({ authUserId, cacheProfileId }) =>
            authUserId === browserProfile.id && cacheProfileId === requestProfile.id
        )
      ).toBe(false)
      expect(profileReads.some(({ cacheProfileId }) => cacheProfileId === requestProfile.id)).toBe(
        false
      )
      expect(getSpy.mock.calls.filter(([url]) => url === "/users/me")).toHaveLength(2)
    } finally {
      if (root) {
        await act(async () => {
          resolveBrowserResponse?.({ data: browserProfile })
          await browserResponse
          root?.unmount()
        })
      } else {
        resolveBrowserResponse?.({ data: browserProfile })
        await browserResponse
      }
      container.remove()
    }
  })
})
