import type { PropsWithChildren } from "react"
import { renderHook, waitFor } from "@testing-library/react"
import { QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import api from "@/api/client"
import { createQueryClient } from "@/app/queryClient"
import { AuthProvider, useAuth } from "@/contexts/AuthContext"
import { currentUserQueryKey, currentUserQueryOptions } from "@/api/hooks/users"
import { testUser } from "@/tests/mocks/handlers"

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
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })

  afterEach(() => {
    vi.restoreAllMocks()
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
    const queryClient = createQueryClient()
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

    queryClient.clear()
  })

  it("falls through to network fetch when cache is empty (factory queryFn invoked)", async () => {
    // No pre-populated cache — bridged effect should invoke factory's
    // queryFn → fetchCurrentUser → api.get("/users/me", ...). Behavior
    // matches pre-W134 useProfileSync auto-fetch path (single network
    // call, not two; factory dedups concurrent calls).
    const queryClient = createQueryClient()

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

    queryClient.clear()
  })

  it("populates queryClient cache after a network fetch (cache-write side effect)", async () => {
    // Wave 134 SW1 closing-the-loop assertion: after the bridged auto-fetch
    // fires (cache empty → network → user state), the SAME queryClient
    // cache slot is populated for any future consumer (e.g. a sibling
    // useQuery(currentUserQueryOptions()) mounted later) — no separate
    // re-fetch needed.
    const queryClient = createQueryClient()

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

    queryClient.clear()
  })
})
