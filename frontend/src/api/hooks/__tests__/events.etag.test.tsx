import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, renderHook, waitFor } from "@testing-library/react"
import { HttpResponse, http } from "msw"
import type { PropsWithChildren } from "react"
import { beforeEach, afterEach, describe, expect, it } from "vitest"
import { useAuthStore } from "@/stores/useAuthStore"
import type { UserState } from "@/types/Auth"

import { resetEtagCache } from "@/api/client"
import { useEventsListQuery, type EventsListOrder } from "@/api/hooks/events"
import type { Event } from "@/types/Event"
import { testEvents } from "@/tests/mocks/handlers"
import { server } from "@/tests/mocks/server"

const SHARED_EVENTS_ETAG = '"events-list-shared"'

const cloneEvents = (source: Event[], label: string, offset: number): Event[] =>
  source.map((event, index) => ({
    ...event,
    id: event.id + offset + index,
    title: `${label} list ${index + 1}`,
    title_en: `${label} list ${index + 1}`,
    description: `${label} description ${index + 1}`,
    description_en: `${label} description ${index + 1}`,
  }))

describe("useEventsListQuery", () => {
  beforeEach(() =>
    useAuthStore.setState({ user: { id: "etag-user" } as UserState, loading: false })
  )
  afterEach(() => {
    cleanup()
    useAuthStore.setState({ user: null, loading: true })
  })
  it("keeps date-order requests and ETags separate through the generated client", async () => {
    resetEtagCache()
    const ascending = testEvents.slice(0, 3).map((event, index) => ({
      ...event,
      starts_at: `2027-01-0${index + 1}T10:00:00.000Z`,
      ends_at: `2027-01-0${index + 1}T12:00:00.000Z`,
    }))
    expect(ascending.length).toBeGreaterThanOrEqual(2)
    expect(new Set(ascending.map(({ id }) => id)).size).toBe(ascending.length)
    const descending = [...ascending].reverse()
    const ascTag = '"events-list-asc"'
    const descTag = '"events-list-desc"'
    const requests: Array<{ order: string | null; ifNoneMatch: string | null }> = []
    let releaseAscending: () => void = () => undefined
    const ascendingResponse = new Promise<void>((resolve) => {
      releaseAscending = resolve
    })

    server.use(
      http.get("*/events", async ({ request }) => {
        const order = new URL(request.url).searchParams.get("order")
        const ifNoneMatch = request.headers.get("if-none-match")
        requests.push({ order, ifNoneMatch })
        if (order === "starts_at_asc") await ascendingResponse
        const tag = order === "starts_at_desc" ? descTag : ascTag
        const items = order === "starts_at_desc" ? descending : ascending
        if (ifNoneMatch === tag) {
          return new HttpResponse(null, { status: 304, headers: { ETag: tag } })
        }
        return HttpResponse.json(
          {
            items,
            total: items.length,
            limit: 12,
            cursor: null,
            next_cursor: null,
            has_more: false,
          },
          { headers: { ETag: tag } }
        )
      })
    )

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    })
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
    const initialProps: { order: EventsListOrder } = { order: "starts_at_desc" }
    const { result, rerender, unmount } = renderHook(
      ({ order }: { order: EventsListOrder }) =>
        useEventsListQuery({ language: "ru", is_active: true, order }),
      { initialProps, wrapper }
    )
    const ids = (events: Event[]) => events.map(({ id }) => id)

    try {
      await waitFor(() => expect(ids(result.current.events)).toEqual(ids(descending)))
      expect(requests[0]).toEqual({ order: "starts_at_desc", ifNoneMatch: null })

      rerender({ order: "starts_at_asc" })
      await waitFor(() => expect(requests).toHaveLength(2))
      expect(requests[1]).toEqual({ order: "starts_at_asc", ifNoneMatch: null })
      expect(result.current.data).toBeUndefined()
      expect(result.current.events).toEqual([])
      await act(async () => {
        releaseAscending()
      })
      await waitFor(() => expect(ids(result.current.events)).toEqual(ids(ascending)))

      rerender({ order: "starts_at_desc" })
      await act(async () => {
        await result.current.refetch()
      })
      expect(requests).toHaveLength(3)
      expect(requests[2]).toEqual({ order: "starts_at_desc", ifNoneMatch: descTag })
      expect(ids(result.current.events)).toEqual(ids(descending))
    } finally {
      releaseAscending()
      unmount()
      queryClient.clear()
      resetEtagCache()
    }
  })

  it("forces a revalidation after resetEtagCache for the next user session", async () => {
    const baseEvents = testEvents.slice(0, 4)
    const firstUserEvents = cloneEvents(baseEvents, "First", 0)
    const secondUserEvents = cloneEvents(baseEvents, "Second", 200)
    let activeSnapshot = firstUserEvents

    server.use(
      http.get("*/events", ({ request }) => {
        if (request.headers.get("if-none-match") === SHARED_EVENTS_ETAG) {
          return new HttpResponse(null, {
            status: 304,
            headers: { ETag: SHARED_EVENTS_ETAG },
          })
        }

        return HttpResponse.json(
          {
            items: activeSnapshot,
            total: activeSnapshot.length,
            limit: 12,
            cursor: null,
            next_cursor: null,
            has_more: false,
          },
          { headers: { ETag: SHARED_EVENTS_ETAG } }
        )
      })
    )

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )

    const { result } = renderHook(() => useEventsListQuery({ language: "ru", is_active: true }), {
      wrapper,
    })

    await waitFor(() => expect(result.current.events).toEqual(firstUserEvents))

    activeSnapshot = secondUserEvents
    resetEtagCache()

    await act(async () => {
      await result.current.refetch()
    })

    await waitFor(() => expect(result.current.events).toEqual(secondUserEvents))
  })
})
