import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, renderHook, waitFor } from "@testing-library/react"
import { HttpResponse, http } from "msw"
import type { PropsWithChildren } from "react"
import { describe, expect, it } from "vitest"

import { resetEtagCache } from "@/api/client"
import { dashboardEventsQueryKey, useDashboardEvents } from "@/hooks/useDashboardEvents"
import type { Event } from "@/types/Event"
import { testEvents } from "@/tests/mocks/handlers"
import { server } from "@/tests/mocks/server"

const SHARED_DASHBOARD_ETAG = '"dashboard-events-shared"'

const cloneEvents = (source: Event[], label: string, offset: number): Event[] =>
  source.map((event, index) => ({
    ...event,
    id: event.id + offset + index,
    title: `${label} event ${index + 1}`,
    title_en: `${label} event ${index + 1}`,
    description: `${label} description ${index + 1}`,
    description_en: `${label} description ${index + 1}`,
  }))

describe("useDashboardEvents", () => {
  it("fetches fresh events after resetEtagCache when a new user signs in", async () => {
    const baseEvents = testEvents.slice(0, 3)
    const firstUserEvents = cloneEvents(baseEvents, "First user", 0)
    const secondUserEvents = cloneEvents(baseEvents, "Second user", 100)
    let activeSnapshot = firstUserEvents

    server.use(
      http.get("*/events", ({ request }) => {
        if (request.headers.get("if-none-match") === SHARED_DASHBOARD_ETAG) {
          return new HttpResponse(null, {
            status: 304,
            headers: { ETag: SHARED_DASHBOARD_ETAG },
          })
        }

        return HttpResponse.json(
          {
            items: activeSnapshot,
            total: activeSnapshot.length,
            limit: 50,
            cursor: null,
            next_cursor: null,
            has_more: false,
          },
          { headers: { ETag: SHARED_DASHBOARD_ETAG } }
        )
      })
    )

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )

    const { result } = renderHook(() => useDashboardEvents(), { wrapper })

    await waitFor(() => expect(result.current.data).toEqual(firstUserEvents))

    activeSnapshot = secondUserEvents
    resetEtagCache()

    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: dashboardEventsQueryKey })
    })

    await waitFor(() => expect(result.current.data).toEqual(secondUserEvents))
  })
})




