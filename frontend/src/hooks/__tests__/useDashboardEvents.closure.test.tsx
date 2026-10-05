import { QueryClient } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"
import type { Event } from "@/types/Event"

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }))

vi.mock("@/api/client", () => ({ default: { get: mockGet } }))

import {
  createDashboardEventsQueryOptions,
  dashboardEventsQueryKey,
  prefetchDashboardEvents,
  projectDashboardEventsSnapshot,
} from "../useDashboardEvents"

const event = (
  id: string,
  starts_at = "2026-01-15T10:00:00.000Z",
  location?: string | null
): Event => ({
  created_at: "2026-01-01T00:00:00.000Z",
  created_by: "event-owner-private-sentinel",
  ends_at: "2026-01-15T11:00:00.000Z",
  is_active: true,
  is_registered: true,
  my_qr_token: "attendance-private-sentinel",
  ...(location === undefined ? {} : { location }),
  id,
  starts_at,
  title: id,
})
const dashboardEvent = (id: string, starts_at: string, location?: string | null) => ({
  id,
  title: id,
  starts_at,
  ...(location === undefined ? {} : { location }),
})

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
        items: [
          event("late", "2026-02-02"),
          null,
          { ...event("missing"), starts_at: undefined } as unknown as Event,
          event("early", "2026-01-01"),
        ],
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

  it("safely sorts truthy non-string start values from an unvalidated API response", async () => {
    const client = new QueryClient()
    const options = createDashboardEventsQueryOptions(client)
    mockGet.mockResolvedValueOnce({
      status: 200,
      data: {
        items: [
          { ...event("numeric-late"), starts_at: 20 } as unknown as Event,
          { ...event("numeric-early"), starts_at: 10 } as unknown as Event,
        ],
      },
    })

    await expect(options.queryFn(context(client))).resolves.toEqual({
      items: [
        expect.objectContaining({ id: "numeric-early" }),
        expect.objectContaining({ id: "numeric-late" }),
      ],
    })
  })

  it("returns the cached snapshot for 304 and uses an empty snapshot without cache", async () => {
    const client = new QueryClient()
    const options = createDashboardEventsQueryOptions(client)
    const previous = { items: [event("cached", "2026-01-01")] }
    client.setQueryData(dashboardEventsQueryKey, previous)

    mockGet.mockResolvedValueOnce({ status: 304, data: undefined })
    await expect(options.queryFn(context(client))).resolves.toEqual({
      items: [dashboardEvent("cached", "2026-01-01")],
    })

    client.removeQueries({ queryKey: dashboardEventsQueryKey })
    mockGet.mockResolvedValueOnce({ status: 304, data: undefined })
    await expect(options.queryFn(context(client))).resolves.toEqual({ items: [] })

    mockGet.mockResolvedValueOnce({
      status: 304,
      data: { items: [event("304-body", "2026-02-01", null)] },
    })
    await expect(options.queryFn(context(client))).resolves.toEqual({
      items: [
        {
          id: "304-body",
          title: "304-body",
          starts_at: "2026-02-01",
          location: null,
        },
      ],
    })
  })

  it("projects valid display fields and rejects malformed cached snapshots", () => {
    expect(
      projectDashboardEventsSnapshot({
        items: [event("projected", "2026-03-01", null)],
      })
    ).toEqual({
      items: [
        {
          id: "projected",
          title: "projected",
          starts_at: "2026-03-01",
          location: null,
        },
      ],
    })
    expect(
      projectDashboardEventsSnapshot({
        items: [{ id: "missing-title", starts_at: "2026-03-01" }],
      })
    ).toBeUndefined()
    expect(
      projectDashboardEventsSnapshot({
        items: [{ id: "bad-location", title: "Bad", starts_at: "2026-03-01", location: 7 }],
      })
    ).toBeUndefined()

    expect(projectDashboardEventsSnapshot({ items: [event("no-location")] })).toEqual({
      items: [dashboardEvent("no-location", "2026-01-15T10:00:00.000Z")],
    })
    expect(
      projectDashboardEventsSnapshot({ items: [event("string-location", "2026-03-01", "Hall A")] })
    ).toEqual({
      items: [dashboardEvent("string-location", "2026-03-01", "Hall A")],
    })

    const validEvent = event("valid")
    const invalidSnapshots: unknown[] = [
      null,
      [],
      {},
      { items: undefined },
      { items: { invalid: true } },
      { items: [null] },
      { items: ["not-an-event"] },
      { items: [{ ...validEvent, id: 7 }] },
      { items: [{ ...validEvent, title: null }] },
      { items: [{ ...validEvent, starts_at: 7 }] },
      { items: [{ ...validEvent, location: false }] },
      { items: [validEvent, { ...validEvent, title: 7 }] },
    ]
    for (const invalidSnapshot of invalidSnapshots) {
      expect(projectDashboardEventsSnapshot(invalidSnapshot)).toBeUndefined()
    }
  })

  it("rejects malformed item collections and prefetches through the canonical options", async () => {
    const client = new QueryClient()
    const options = createDashboardEventsQueryOptions(client)

    mockGet.mockResolvedValueOnce({ status: 200, data: { items: { invalid: true } } })
    await expect(options.queryFn(context(client))).resolves.toEqual({ items: [] })

    mockGet.mockResolvedValueOnce({
      status: 200,
      data: { items: [event("prefetched", "2026-03-01")] },
    })
    await expect(prefetchDashboardEvents(client)).resolves.toBeUndefined()
    expect(client.getQueryData(dashboardEventsQueryKey)).toEqual({
      items: [dashboardEvent("prefetched", "2026-03-01")],
    })
  })

  it("falls back after non-aborted errors and rethrows abort/no-cache errors", async () => {
    const client = new QueryClient()
    const options = createDashboardEventsQueryOptions(client)
    const fallback = { items: [event("fallback", "2026-01-01")] }
    client.setQueryData(dashboardEventsQueryKey, fallback)
    mockGet.mockRejectedValueOnce(new Error("temporary"))
    await expect(options.queryFn(context(client))).resolves.toEqual({
      items: [dashboardEvent("fallback", "2026-01-01")],
    })

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
