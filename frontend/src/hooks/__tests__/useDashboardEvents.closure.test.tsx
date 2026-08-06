import { QueryClient } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"
import type { Event } from "@/types/Event"

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }))

vi.mock("@/api/client", () => ({ default: { get: mockGet } }))

import { createDashboardEventsQueryOptions, dashboardEventsQueryKey } from "../useDashboardEvents"

const event = (id: string, starts_at?: string) =>
  ({
    id,
    starts_at,
    title: id,
  }) as unknown as Event

const context = (client: QueryClient, signal?: AbortSignal) => ({
  client,
  queryKey: dashboardEventsQueryKey,
  signal: signal ?? new AbortController().signal,
  meta: undefined,
})

describe("useDashboardEvents closure", () => {
  it("normalizes, filters, sorts, and caps successful event responses", async () => {
    const client = new QueryClient()
    const options = createDashboardEventsQueryOptions(client)
    mockGet.mockResolvedValueOnce({
      status: 200,
      data: {
        items: [event("late", "2026-02-02"), null, event("missing"), event("early", "2026-01-01")],
      },
    })

    const out = await options.queryFn(context(client))
    expect(out.items.map((item) => item.id)).toEqual(["early", "late"])
    expect(mockGet).toHaveBeenCalledWith(
      "/events",
      expect.objectContaining({
        params: { is_active: true, limit: 50 },
        etagCacheKey: "dashboard:events",
      })
    )
    const request = mockGet.mock.calls[0]?.[1] as { validateStatus: (status: number) => boolean }
    expect(request.validateStatus(200)).toBe(true)
    expect(request.validateStatus(399)).toBe(true)
    expect(request.validateStatus(400)).toBe(false)
  })

  it("returns the cached snapshot for 304 and uses an empty snapshot without cache", async () => {
    const client = new QueryClient()
    const options = createDashboardEventsQueryOptions(client)
    const previous = { items: [event("cached", "2026-01-01")] }
    client.setQueryData(dashboardEventsQueryKey, previous)

    mockGet.mockResolvedValueOnce({ status: 304, data: undefined })
    await expect(options.queryFn(context(client))).resolves.toEqual(previous)

    client.removeQueries({ queryKey: dashboardEventsQueryKey })
    mockGet.mockResolvedValueOnce({ status: 304, data: undefined })
    await expect(options.queryFn(context(client))).resolves.toEqual({ items: [] })
  })

  it("falls back after non-aborted errors and rethrows abort/no-cache errors", async () => {
    const client = new QueryClient()
    const options = createDashboardEventsQueryOptions(client)
    const fallback = { items: [event("fallback", "2026-01-01")] }
    client.setQueryData(dashboardEventsQueryKey, fallback)
    mockGet.mockRejectedValueOnce(new Error("temporary"))
    await expect(options.queryFn(context(client))).resolves.toEqual(fallback)

    client.removeQueries({ queryKey: dashboardEventsQueryKey })
    const aborted = new Error("aborted")
    const controller = new AbortController()
    controller.abort()
    mockGet.mockRejectedValueOnce(aborted)
    await expect(options.queryFn(context(client, controller.signal))).rejects.toBe(aborted)

    const uncached = new Error("uncached")
    mockGet.mockRejectedValueOnce(uncached)
    await expect(options.queryFn(context(client))).rejects.toBe(uncached)
  })

  it("exposes stable query options and select/placeholder transforms", () => {
    const client = new QueryClient()
    const options = createDashboardEventsQueryOptions(client)
    const snapshot = { items: [event("one")] }
    expect(options.queryKey).toBe(dashboardEventsQueryKey)
    expect(options.select(snapshot)).toEqual(snapshot.items)
    expect(options.placeholderData(snapshot)).toBe(snapshot)
    expect(options.placeholderData(undefined)).toBeUndefined()
    expect(options.staleTime).toBe(120_000)
    expect(options.gcTime).toBe(1_800_000)
  })
})
