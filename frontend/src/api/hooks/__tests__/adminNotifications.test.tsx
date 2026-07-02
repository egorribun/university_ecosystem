/**
 * @fileoverview Tests for adminNotifications.ts API hook exports.
 *
 * Coverage:
 *   - adminDeadLetterQueueQueryKey: static cache key
 *   - adminDeadLetterQueueQueryOptions(): staleTime, gcTime, queryFn shape,
 *     signal forwarding to fetchDeadLetterQueue
 *   - useAdminDeadLetterQueueQuery(): success, loading, error, enabled states
 *   - invalidateAdminDeadLetterQueue(): invalidation helper
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import type { PropsWithChildren } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// ── Mock the fetchDeadLetterQueue helper ────────────────────────────────────
const fetchMock = vi.hoisted(() => vi.fn())
vi.mock("@/api/notifications", () => ({
  fetchDeadLetterQueue: fetchMock,
}))

import {
  adminDeadLetterQueueQueryKey,
  adminDeadLetterQueueQueryOptions,
  invalidateAdminDeadLetterQueue,
  useAdminDeadLetterQueueQuery,
} from "@/api/hooks/adminNotifications"

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

const DEAD_LETTER_STUB = {
  items: [
    {
      id: "dl-1",
      notification_id: "n-1",
      error: "delivery_failed",
      created_at: "2026-06-28T10:00:00Z",
    },
  ],
  total: 1,
}

afterEach(() => {
  vi.restoreAllMocks()
})

// ── adminDeadLetterQueueQueryKey ────────────────────────────────────────────
describe("adminDeadLetterQueueQueryKey", () => {
  it("is the static tuple ['admin', 'notifications', 'dead-letter']", () => {
    expect(adminDeadLetterQueueQueryKey).toEqual(["admin", "notifications", "dead-letter"])
  })

  it("matches adminDeadLetterQueueQueryOptions().queryKey reference identity", () => {
    expect(adminDeadLetterQueueQueryOptions().queryKey).toBe(adminDeadLetterQueueQueryKey)
  })
})

// ── adminDeadLetterQueueQueryOptions ────────────────────────────────────────
describe("adminDeadLetterQueueQueryOptions", () => {
  it("staleTime is 30_000 (30 seconds)", () => {
    expect(adminDeadLetterQueueQueryOptions().staleTime).toBe(30_000)
  })

  it("gcTime is 5 * 60_000 (5 minutes)", () => {
    expect(adminDeadLetterQueueQueryOptions().gcTime).toBe(5 * 60_000)
  })

  it("queryFn is callable", () => {
    expect(typeof adminDeadLetterQueueQueryOptions().queryFn).toBe("function")
  })
})

// ── useAdminDeadLetterQueueQuery ────────────────────────────────────────────
describe("useAdminDeadLetterQueueQuery", () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = createQueryClient()
  })

  it("fetches dead-letter queue data and returns on success", async () => {
    fetchMock.mockResolvedValueOnce(DEAD_LETTER_STUB)

    const { result } = renderHook(() => useAdminDeadLetterQueueQuery(), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.isLoading).toBe(true)

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual(DEAD_LETTER_STUB)
  })

  it("forwards signal to fetchDeadLetterQueue", async () => {
    fetchMock.mockResolvedValueOnce(DEAD_LETTER_STUB)

    const { result } = renderHook(() => useAdminDeadLetterQueueQuery(), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    // fetchDeadLetterQueue(undefined, signal) — first arg undefined, second is AbortSignal
    expect(fetchMock).toHaveBeenCalledWith(undefined, expect.any(AbortSignal))
  })

  it("enters error state when fetchDeadLetterQueue fails", async () => {
    fetchMock.mockRejectedValueOnce(new Error("500 Internal Server Error"))

    const { result } = renderHook(() => useAdminDeadLetterQueueQuery(), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isError).toBe(true))

    expect(result.current.error?.message).toBe("500 Internal Server Error")
  })

  it("respects the enabled option", async () => {
    const { result } = renderHook(() => useAdminDeadLetterQueueQuery({ enabled: false }), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.fetchStatus).toBe("idle")
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

// ── invalidateAdminDeadLetterQueue ──────────────────────────────────────────
describe("invalidateAdminDeadLetterQueue", () => {
  it("invalidates the dead-letter queue cache slot", async () => {
    const client = new QueryClient()
    const spy = vi.spyOn(client, "invalidateQueries")

    await invalidateAdminDeadLetterQueue(client)

    expect(spy).toHaveBeenCalledWith({
      queryKey: adminDeadLetterQueueQueryKey,
    })
  })

  it("returns the underlying invalidateQueries promise (awaitable)", async () => {
    const client = new QueryClient()
    const result = invalidateAdminDeadLetterQueue(client)
    expect(result).toBeInstanceOf(Promise)
    await expect(result).resolves.toBeUndefined()
  })
})
