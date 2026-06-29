/**
 * @fileoverview Tests for users.ts API hook exports (queryFn execution).
 *
 * Complements `ssrFactories.test.ts` (which tests factory shape only) with
 * queryFn execution tests that mock `fetchCurrentUser` and verify signal
 * forwarding and error propagation.
 *
 * Coverage:
 *   - currentUserQueryKey: static cache key (re-verified for completeness)
 *   - currentUserQueryOptions().queryFn: delegates to fetchCurrentUser
 *     with signal, propagates errors
 */
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import type { PropsWithChildren } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// ── Mock the fetchCurrentUser helper ────────────────────────────────────────
const fetchCurrentUserMock = vi.hoisted(() => vi.fn())
vi.mock("@/hooks/auth/useProfileSync", () => ({
  fetchCurrentUser: fetchCurrentUserMock,
}))

import { currentUserQueryKey, currentUserQueryOptions } from "@/api/hooks/users"

// ── Helpers ─────────────────────────────────────────────────────────────────
const makeWrapper = (queryClient: QueryClient) => {
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return Wrapper
}

const createQueryClient = () =>
  new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })

const USER_STUB = {
  id: "user-1",
  full_name: "Jane Doe",
  email: "jane@example.com",
  role: "student",
  group_id: "g1",
}

afterEach(() => {
  vi.restoreAllMocks()
})

// ── currentUserQueryKey ─────────────────────────────────────────────────────
describe("currentUserQueryKey", () => {
  it("is the static tuple ['users', 'me']", () => {
    expect(currentUserQueryKey).toEqual(["users", "me"])
  })

  it("matches currentUserQueryOptions().queryKey reference identity", () => {
    expect(currentUserQueryOptions().queryKey).toBe(currentUserQueryKey)
  })
})

// ── currentUserQueryOptions queryFn execution ───────────────────────────────
describe("currentUserQueryOptions queryFn execution", () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = createQueryClient()
  })

  it("fetches current user via fetchCurrentUser and returns data", async () => {
    fetchCurrentUserMock.mockResolvedValueOnce(USER_STUB)

    const { result } = renderHook(
      () => {
        return useQuery(currentUserQueryOptions())
      },
      { wrapper: makeWrapper(queryClient) }
    )

    expect(result.current.isLoading).toBe(true)

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual(USER_STUB)
  })

  it("forwards the AbortSignal to fetchCurrentUser", async () => {
    fetchCurrentUserMock.mockResolvedValueOnce(USER_STUB)

    const { result } = renderHook(
      () => {
        return useQuery(currentUserQueryOptions())
      },
      { wrapper: makeWrapper(queryClient) }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(fetchCurrentUserMock).toHaveBeenCalledWith({
      signal: expect.any(AbortSignal),
    })
  })

  it("enters error state when fetchCurrentUser fails", async () => {
    fetchCurrentUserMock.mockRejectedValueOnce(new Error("401 Unauthorized"))

    const { result } = renderHook(
      () => {
        return useQuery(currentUserQueryOptions())
      },
      { wrapper: makeWrapper(queryClient) }
    )
    await waitFor(() => expect(result.current.isError).toBe(true))

    //("401 Unauthorized")
  })
})
