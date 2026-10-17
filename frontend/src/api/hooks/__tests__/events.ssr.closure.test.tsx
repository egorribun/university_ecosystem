/** @vitest-environment node */

import { QueryClient, QueryClientProvider, type InfiniteData } from "@tanstack/react-query"
import { renderToString } from "react-dom/server"
import { afterEach, describe, expect, it, vi } from "vitest"

import { allEventsApiV1EventsGet } from "@/api/generated/sdk.gen"
import { getConfirmedUserId } from "@/stores/authIdentity"
import { useAuthStore } from "@/stores/useAuthStore"
import type { UserState } from "@/types/Auth"
import type { Event } from "@/types/Event"
import type { PaginatedResponse } from "@/types/Pagination"

vi.mock("@/api/generated/sdk.gen", () => ({
  allEventsApiV1EventsGet: vi.fn(),
  myEventsApiV1EventsMyGet: vi.fn(),
}))

import {
  eventsListQueryKey,
  useEventNavigation,
  useEventsListQuery,
  useMyEventsQuery,
} from "@/api/hooks/events"

const clients = new Set<QueryClient>()
const createClient = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  clients.add(client)
  return client
}

afterEach(() => {
  for (const client of clients) client.clear()
  clients.clear()
})

const event = (id: string, title: string): Event => ({
  id,
  title,
  created_by: "10000000-0000-4000-8000-000000000000",
  created_at: "2026-10-01T09:00:00Z",
  starts_at: "2026-10-05T10:00:00Z",
  ends_at: "2026-10-05T11:00:00Z",
  is_active: true,
})

const before = event("10000000-0000-4000-8000-000000000001", "Opening talk")
const current = event("10000000-0000-4000-8000-000000000002", "Workshop")
const after = event("10000000-0000-4000-8000-000000000003", "Closing talk")

const seedNavigation = (client: QueryClient) => {
  // Cursor pages can overlap as a feed changes between requests. Navigation
  // preserves the first occurrence and its title, without creating a loop.
  const data: InfiniteData<PaginatedResponse<Event>, string | null> = {
    pages: [
      {
        items: [before, current],
        total: 3,
        limit: 2,
        cursor: null,
        next_cursor: "next-page",
        has_more: true,
      },
      {
        items: [{ ...before, title: "Updated opening talk" }, after],
        total: 3,
        limit: 2,
        cursor: "next-page",
        next_cursor: null,
        has_more: false,
      },
    ],
    pageParams: [null, "next-page"],
  }
  client.setQueryData(eventsListQueryKey({ language: "en", limit: 2 }), data)
}

function NavigationProbe({ id }: { id: string }) {
  const { prevId, prevTitle, nextId, nextTitle } = useEventNavigation(id)
  return (
    <output>
      {[prevId, prevTitle, nextId, nextTitle].map((value) => value ?? "none").join("|")}
    </output>
  )
}

const renderNavigation = (client: QueryClient, id: string) =>
  renderToString(
    <QueryClientProvider client={client}>
      <NavigationProbe id={id} />
    </QueryClientProvider>
  )

function SsrProbe() {
  const events = useEventsListQuery({ language: "en" }, { enabled: false })
  const mine = useMyEventsQuery({ language: "en", userId: null })
  return <span>{`${events.data === undefined}:${mine.data === undefined}`}</span>
}

describe("events hooks SSR fallbacks", () => {
  it("does not read browser storage while rendering on the server", () => {
    const queryClient = createClient()

    expect(
      renderToString(
        <QueryClientProvider client={queryClient}>
          <SsrProbe />
        </QueryClientProvider>
      )
    ).toContain("<span>true:true</span>")
  })

  it("keeps an authenticated server render free of events data and requests", () => {
    expect(typeof window).toBe("undefined")
    const previousAuth = useAuthStore.getState()
    try {
      useAuthStore.setState({
        user: {
          id: "server-render-user",
          email: "server-render-user@example.test",
          is_active: true,
        } satisfies NonNullable<UserState>,
        loading: false,
      })
      expect(getConfirmedUserId(useAuthStore.getState())).toBe("server-render-user")

      const queryClient = createClient()
      expect(
        renderToString(
          <QueryClientProvider client={queryClient}>
            <SsrProbe />
          </QueryClientProvider>
        )
      ).toContain("<span>true:true</span>")
      expect(allEventsApiV1EventsGet).not.toHaveBeenCalled()
    } finally {
      useAuthStore.setState({ user: previousAuth.user, loading: previousAuth.loading })
    }
  })

  it("derives server-rendered navigation from cached cursor pages in first-seen order", () => {
    const client = createClient()
    seedNavigation(client)

    expect(renderNavigation(client, current.id)).toBe(
      `<output>${before.id}|Opening talk|${after.id}|Closing talk</output>`
    )
    expect(renderNavigation(client, before.id)).toBe(
      `<output>none|none|${current.id}|Workshop</output>`
    )
    expect(renderNavigation(client, after.id)).toBe(
      `<output>${current.id}|Workshop|none|none</output>`
    )
    expect(renderNavigation(client, "10000000-0000-4000-8000-000000000004")).toBe(
      "<output>none|none|none|none</output>"
    )
  })

  it("keeps another server request's cached events out of a direct detail render", () => {
    const populatedRequest = createClient()
    seedNavigation(populatedRequest)
    const directRequest = createClient()
    directRequest.setQueryData(["events", "detail", current.id], current)

    expect(renderNavigation(directRequest, current.id)).toBe("<output>none|none|none|none</output>")
    expect(renderNavigation(populatedRequest, current.id)).toBe(
      `<output>${before.id}|Opening talk|${after.id}|Closing talk</output>`
    )
  })
})
