import type { PropsWithChildren } from "react"
import { act, cleanup, renderHook, waitFor } from "@testing-library/react"
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import api from "@/api/client"
import { createQueryClient } from "@/app/queryClient"
import { AuthProvider, useAuth } from "@/contexts/AuthContext"
import { currentUserQueryKey, currentUserQueryOptions } from "@/api/hooks/users"
import { testUser } from "@/tests/mocks/handlers"
import { useAuthStore } from "@/stores/useAuthStore"
import { acceptBrowserSessionGeneration } from "@/stores/sessionEpoch"

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

  it("consumes SSR-prefetched cache without a duplicate /users/me network call", async () => {
    // Simulate the SSR loader pattern:
    //   loader: ({ context }) =>
    //     context.queryClient.ensureQueryData(currentUserQueryOptions())
    // — populated BEFORE AuthProvider mounts. The bridged auto-fetch
    // effect should read this cache instead of triggering a network call.
    const queryClient = createOwnedClient()
    queryClient.setQueryData(currentUserQueryKey, testUser)

    const getSpy = vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/auth/session/signing-key") {
        return Promise.resolve({ data: { signing_key: "session-key" } } as any)
      }
      // Any /users/me call is a regression — bridge should consume cache.
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

    // Wait for AuthProvider to surface the cached user.
    await waitFor(() => {
      expect(result.current.user?.id).toBe(testUser.id)
    })

    // Critical assertion: cached data was consumed; no /users/me fetch fired.
    const userMeCalls = getSpy.mock.calls.filter(([url]) => url === "/users/me")
    expect(userMeCalls).toHaveLength(0)
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
})
