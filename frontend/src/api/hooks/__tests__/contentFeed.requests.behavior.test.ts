import { QueryClient } from "@tanstack/react-query"
import { HttpResponse, http } from "msw"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { isAbortError } from "@/api/client"
import type { PaginatedNews } from "@/api/generated"
import type { NewsItem } from "@/api/news"
import { eventsListQueryKey, prefetchEventsListQuery } from "@/api/hooks/events"
import { newsListQueryKey, prefetchNewsListQuery } from "@/api/hooks/news"
import { createQueryClient } from "@/app/queryClient"
import { acceptBrowserSessionGeneration, getSessionEpoch } from "@/stores/sessionEpoch"
import { useAuthStore } from "@/stores/useAuthStore"
import { testUser } from "@/tests/mocks/handlers"
import { server } from "@/tests/mocks/server"
import type { Event } from "@/types/Event"
import type { PaginatedResponse } from "@/types/Pagination"

const event: Event = {
  id: "d95523b3-d2c2-4187-9aac-df229f6e0033",
  title: "Campus research seminar",
  created_at: "2026-09-01T09:00:00Z",
  created_by: testUser.id,
  starts_at: "2026-10-05T10:00:00Z",
  ends_at: "2026-10-05T11:00:00Z",
  is_active: true,
  is_registered: true,
}

const article: NewsItem = {
  id: "cb96b565-6cb8-421d-bfb2-ad6b5b9fab35",
  title: "Library opening hours",
  content: "The library is open until 20:00 on weekdays.",
  created_at: "2026-09-01T09:00:00Z",
  image_url_optimized: null,
  is_liked: true,
}

const page = <T>(item: T): PaginatedResponse<T> => ({
  items: [item],
  total: 1,
  limit: 12,
  cursor: null,
  next_cursor: null,
  has_more: false,
})

const deferred = () => {
  let resolve!: () => void
  const promise = new Promise<void>((accept) => {
    resolve = accept
  })
  return { promise, resolve }
}

const feeds = [
  {
    name: "events",
    url: "*/api/v1/events",
    key: eventsListQueryKey({ language: "en" }),
    prefetch: (client: QueryClient) => prefetchEventsListQuery(client, { language: "en" }),
    response: page(event),
    expectedPage: page(event),
  },
  {
    name: "news",
    url: "*/api/v1/news",
    key: newsListQueryKey({ language: "en" }),
    prefetch: (client: QueryClient) => prefetchNewsListQuery(client, { language: "en" }),
    response: { items: [article], has_more: false, next_cursor: null } satisfies PaginatedNews,
    expectedPage: page(article),
  },
]

const clients: QueryClient[] = []
const queryClient = () => {
  const client = createQueryClient()
  client.setDefaultOptions({ queries: { retry: false, gcTime: Infinity } })
  clients.push(client)
  return client
}

beforeEach(() => {
  localStorage.clear()
  acceptBrowserSessionGeneration()
  useAuthStore.setState({ user: testUser, loading: false })
})

afterEach(() => {
  for (const client of clients.splice(0)) client.clear()
  useAuthStore.setState({ user: null, loading: true })
  localStorage.clear()
  acceptBrowserSessionGeneration()
})

describe.each(feeds)("$name requests across profile confirmation", (feed) => {
  it("reports a session cancellation when prefetch starts before identity confirmation", async () => {
    useAuthStore.getState().setLoading(true)
    const client = queryClient()

    await feed.prefetch(client)

    const state = client.getQueryState(feed.key)
    expect(state?.status).toBe("error")
    expect(state?.data).toBeUndefined()
    expect(state?.error).toBeInstanceOf(DOMException)
    expect(isAbortError(state?.error)).toBe(true)
    expect(state?.error?.message).toBe("Session changed")
  })

  it("discards an in-flight personalized response while the same account is being rechecked", async () => {
    let requestStarted = false
    const release = deferred()
    server.use(
      http.get(feed.url, async () => {
        requestStarted = true
        await release.promise
        return HttpResponse.json(feed.response)
      })
    )
    const client = queryClient()
    const epoch = getSessionEpoch()
    const pending = feed.prefetch(client)
    try {
      await vi.waitFor(() => expect(requestStarted).toBe(true), { timeout: 1000, interval: 10 })

      // A same-account refresh temporarily removes confirmed identity without
      // ending the cache lifetime. The response still needs an owner check.
      useAuthStore.getState().setLoading(true)
      expect(getSessionEpoch()).toBe(epoch)
      release.resolve()
      await pending

      const state = client.getQueryState(feed.key)
      expect(state?.status).toBe("error")
      expect(state?.data).toBeUndefined()
      expect(state?.error).toBeInstanceOf(DOMException)
      expect(isAbortError(state?.error)).toBe(true)
      expect(state?.error?.message).toBe("Session changed")

      useAuthStore.getState().setLoading(false)
      await feed.prefetch(client)
      expect(client.getQueryState(feed.key)?.status).toBe("success")
      expect(client.getQueryData(feed.key)).toEqual({
        pages: [feed.expectedPage],
        pageParams: [null],
      })
    } finally {
      release.resolve()
      await pending
    }
  })
})
