import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, renderHook, waitFor } from "@testing-library/react"
import { HttpResponse, http } from "msw"
import type { PropsWithChildren } from "react"
import { describe, expect, it } from "vitest"

import { resetEtagCache } from "@/api/client"
import { useEventsListQuery } from "@/api/hooks/events"
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




