/**
 * Focused API/query contracts used by mutation testing.
 *
 * These cases deliberately exercise defensive branches that are easy to miss
 * in normal happy-path tests: malformed hydrated query data, SSR globals,
 * cancellation after an AbortSignal flips, and endpoint-context preservation.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import type { PropsWithChildren } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  activityGet: vi.fn(),
  allEvents: vi.fn(),
  myEvents: vi.fn(),
  getEvent: vi.fn(),
  createEvent: vi.fn(),
  uploadEvent: vi.fn(),
  createNews: vi.fn(),
  deleteNews: vi.fn(),
  getNews: vi.fn(),
  listNews: vi.fn(),
  updateNews: vi.fn(),
  uploadNews: vi.fn(),
  subscribe: vi.fn(),
  storePendingMutation: vi.fn(),
}))

vi.mock("@/api/client", () => ({ default: { get: mocks.activityGet } }))

vi.mock("@/api/generated/sdk.gen", () => ({
  allEventsApiV1EventsGet: (...args: unknown[]) => mocks.allEvents(...args),
  myEventsApiV1EventsMyGet: (...args: unknown[]) => mocks.myEvents(...args),
  getEventApiV1EventsEventIdGet: (...args: unknown[]) => mocks.getEvent(...args),
}))

vi.mock("@/api/generated", () => ({
  createEventApiV1EventsPost: mocks.createEvent,
  uploadEventImageApiV1EventsUploadImagePost: mocks.uploadEvent,
  createNewsApiV1NewsPost: mocks.createNews,
  deleteNewsApiV1NewsIdDelete: mocks.deleteNews,
  getNewsApiV1NewsIdGet: mocks.getNews,
  newsListApiV1NewsGet: mocks.listNews,
  updateNewsApiV1NewsIdPatch: mocks.updateNews,
  uploadNewsImageApiV1NewsUploadImagePost: mocks.uploadNews,
  adminGetUserTopicsApiV1PushAdminTopicsUserIdGet: vi.fn(),
  adminUpdateUserTopicsApiV1PushAdminTopicsUserIdPut: vi.fn(),
  checkScheduleAndGenerateApiV1NotificationsCheckSchedulePost: vi.fn(),
  clearNotificationsApiV1NotificationsDelete: vi.fn(),
  unsubscribeApiV1PushUnsubscribePost: vi.fn(),
  getPushTopicsApiV1PushTopicsGet: vi.fn(),
  getVapidPublicKeyApiV1PushVapidPublicKeyGet: vi.fn(),
  listNotificationsApiV1NotificationsGet: vi.fn(),
  markAllReadApiV1NotificationsReadAllPost: vi.fn(),
  markReadSingleApiV1NotificationsNotifIdReadPatch: vi.fn(),
  listNotificationDeadLetters: vi.fn(),
  purgeNotificationDeadLetters: vi.fn(),
  retryNotificationDeadLetters: vi.fn(),
  subscribeApiV1PushSubscribePost: (...args: unknown[]) => mocks.subscribe(...args),
  sendTestApiV1PushTestPost: vi.fn(),
}))

vi.mock("@/sw/offline", () => ({ storePendingMutation: mocks.storePendingMutation }))

import { activitySummaryOptions, ActivitySummaryUnavailableError } from "@/api/hooks/activity"
import { eventsListQueryKey, useEventsListQuery, useMyEventsQuery } from "@/api/hooks/events"
import { uploadEventImage } from "@/api/events"
import { fetchNewsItem, parseNewsList } from "@/api/news"
import { saveSubscription } from "@/api/notifications"
import { enqueueOfflineMutation } from "@/api/offlineMutationQueue"

const makeClient = () =>
  new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  })

const wrapperFor = (client: QueryClient) => {
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return Wrapper
}

const makeEvent = (id: string) =>
  ({
    id,
    title: `Event ${id}`,
    created_at: "2026-01-15T10:00:00.000Z",
    starts_at: "2026-01-20T10:00:00.000Z",
    ends_at: "2026-01-20T12:00:00.000Z",
  }) as never

const makeNews = (overrides: Record<string, unknown> = {}) => ({
  id: "00000000-0000-0000-0000-000000000001",
  title: "News",
  content: "Content",
  created_at: "2026-01-15T10:00:00.000Z",
  image_url_optimized: null,
  ...overrides,
})

const runActivity = (client: QueryClient) => {
  const options = activitySummaryOptions({ period: "30d", language: "en" })
  return options.queryFn?.({
    queryKey: options.queryKey,
    signal: new AbortController().signal,
    meta: undefined,
    client,
  } as never)
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.unstubAllGlobals()
  mocks.storePendingMutation.mockResolvedValue(undefined)
  window.localStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
  window.localStorage.clear()
})

describe("activity summary defensive contracts", () => {
  it("keeps the stable unavailable error message when every fallback feed fails", async () => {
    mocks.activityGet.mockRejectedValue(new Error("offline"))

    await expect(runActivity(makeClient())).rejects.toEqual(
      expect.objectContaining({
        name: "ActivitySummaryUnavailableError",
        message: "All activity summary sources are unavailable",
      } satisfies Partial<ActivitySummaryUnavailableError>)
    )
  })

  it("does not fan out when a generic request fails after its signal is aborted", async () => {
    const controller = new AbortController()
    mocks.activityGet.mockImplementationOnce(async () => {
      controller.abort()
      throw new Error("request aborted")
    })
    const options = activitySummaryOptions({ period: "30d", language: "en" })

    await expect(
      options.queryFn?.({
        queryKey: options.queryKey,
        signal: controller.signal,
        meta: undefined,
        client: makeClient(),
      } as never)
    ).rejects.toThrow("request aborted")
    expect(mocks.activityGet).toHaveBeenCalledOnce()
  })

  it("returns healthy fallback feeds when attendance is the only failed feed", async () => {
    mocks.activityGet
      .mockRejectedValueOnce(new Error("summary unavailable"))
      .mockRejectedValueOnce(new Error("attendance unavailable"))
      .mockResolvedValueOnce({ data: { average: 4.5 } })
      .mockResolvedValueOnce({ data: { score: 82 } })

    await expect(runActivity(makeClient())).resolves.toEqual({
      attendance: null,
      grades: { average: 4.5 },
      participation: { score: 82 },
    })
  })
})

describe("events query defensive contracts", () => {
  it("normalizes runtime-invalid activity filters instead of leaking strings", () => {
    expect(
      eventsListQueryKey({ language: "ru", is_active: "active" as unknown as boolean })[2].is_active
    ).toBeNull()
  })

  it("returns an empty page for a 304 cache object with no pages array", async () => {
    const client = makeClient()
    const filters = { language: "ru", is_active: true as const }
    // Keep the observer's own infinite-data shape valid, while making only
    // the cache lookup used by the 304 branch return a malformed hydrated
    // value. Installing the spy after the network mock starts avoids
    // interfering with TanStack Query's own `pages.length` invariant.
    client.setQueryData(eventsListQueryKey(filters), { pages: [], pageParams: [] })
    mocks.allEvents.mockImplementationOnce(async () => {
      vi.spyOn(client, "getQueryData").mockReturnValue({} as never)
      return { status: 304, data: undefined }
    })

    const { result } = renderHook(() => useEventsListQuery(filters), {
      wrapper: wrapperFor(client),
    })
    await waitFor(() => expect(mocks.allEvents).toHaveBeenCalledOnce())
    await waitFor(() => expect(result.current.isFetching).toBe(false))
    expect(result.current.pagination).toEqual({
      items: [],
      total: 0,
      limit: 12,
      cursor: null,
      next_cursor: null,
      has_more: false,
    })
  })

  it("treats an undefined last page as terminal in the hook's callback", () => {
    const client = makeClient()
    renderHook(() => useEventsListQuery({ language: "ru" }, { enabled: false }), {
      wrapper: wrapperFor(client),
    })
    const query = client.getQueryCache().find({ queryKey: eventsListQueryKey({ language: "ru" }) })
    const getNextPageParam = (query?.options as { getNextPageParam?: (page: unknown) => unknown })
      .getNextPageParam
    expect(getNextPageParam).toEqual(expect.any(Function))
    expect(getNextPageParam?.(undefined)).toBeNull()
  })

  it("keeps pagination null when hydrated query data has no pages", () => {
    const client = makeClient()
    const filters = { language: "ru" }
    client.setQueryData(eventsListQueryKey(filters), { pages: [], pageParams: [] })
    const { result } = renderHook(() => useEventsListQuery(filters, { enabled: false }), {
      wrapper: wrapperFor(client),
    })
    expect(result.current.pagination).toBeNull()
  })

  it("rejects status 199 in the my-events validateStatus contract", async () => {
    mocks.myEvents.mockResolvedValue({ status: 200, data: [] })
    const client = makeClient()
    const { result } = renderHook(() => useMyEventsQuery({ language: "ru", userId: "u-1" }), {
      wrapper: wrapperFor(client),
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const config = mocks.myEvents.mock.calls[0]?.[0] as {
      validateStatus: (status: number) => boolean
    }
    expect(config.validateStatus(199)).toBe(false)
    expect(config.validateStatus(200)).toBe(true)
    expect(config.validateStatus(399)).toBe(true)
    expect(config.validateStatus(400)).toBe(false)
  })

  it("recomputes the my-events placeholder when the user id changes", () => {
    const first = [makeEvent("first")]
    const second = [makeEvent("second")]
    window.localStorage.setItem("events:my:ru:u-first", JSON.stringify(first))
    window.localStorage.setItem("events:my:ru:u-second", JSON.stringify(second))
    const client = makeClient()
    const { result, rerender } = renderHook(
      ({ userId }: { userId: string }) =>
        useMyEventsQuery({ language: "ru", userId }, { enabled: false }),
      { initialProps: { userId: "u-first" }, wrapper: wrapperFor(client) }
    )

    expect(result.current.data).toEqual(first)
    rerender({ userId: "u-second" })
    expect(result.current.data).toEqual(second)
  })

  it("recomputes the events placeholder when the language changes", () => {
    const first = [makeEvent("ru-event")]
    const second = [makeEvent("en-event")]
    window.localStorage.setItem("events:list:ru:active", JSON.stringify(first))
    window.localStorage.setItem("events:list:en:active", JSON.stringify(second))
    const client = makeClient()
    const { result, rerender } = renderHook(
      ({ language }: { language: string }) =>
        useEventsListQuery({ language, is_active: true }, { enabled: false }),
      { initialProps: { language: "ru" }, wrapper: wrapperFor(client) }
    )

    expect(result.current.events).toEqual(first)
    rerender({ language: "en" })
    expect(result.current.events).toEqual(second)
  })
})

describe("news/event API response-context contracts", () => {
  it("includes the event upload endpoint in validation failures", async () => {
    mocks.uploadEvent.mockResolvedValue({ data: { url: "   " } })
    await expect(uploadEventImage(new File(["x"], "event.png"))).rejects.toMatchObject({
      name: "ApiResponseValidationError",
      message: expect.stringContaining("POST /api/v1/events/upload_image"),
    })
  })

  it("preserves the news item schema default and list context", () => {
    expect(parseNewsList([makeNews()])).toEqual([
      expect.objectContaining({ is_liked: false, likes_count: 0, comments_count: 0 }),
    ])
    expect(() => parseNewsList([{ id: "invalid" }])).toThrow(
      "Invalid API response for GET /api/v1/news"
    )
  })

  it("parses non-304 item responses and exposes exact status boundaries", async () => {
    mocks.getNews.mockResolvedValue({ status: 200, data: makeNews({ id: "not-a-uuid" }) })
    await expect(fetchNewsItem("news-1")).rejects.toThrow(
      "Invalid API response for GET /api/v1/news/{id}"
    )

    mocks.getNews.mockResolvedValue({ status: 304, data: undefined })
    await fetchNewsItem("news-304")
    const config = mocks.getNews.mock.calls.at(-1)?.[0] as {
      validateStatus: (status: number) => boolean
    }
    expect(config.validateStatus(199)).toBe(false)
    expect(config.validateStatus(200)).toBe(true)
    expect(config.validateStatus(299)).toBe(true)
    expect(config.validateStatus(300)).toBe(false)
    expect(config.validateStatus(304)).toBe(true)
  })
})

describe("push subscription SSR contract", () => {
  it("does not touch navigator while serializing a subscription on the server", async () => {
    vi.stubGlobal("navigator", undefined)
    mocks.subscribe.mockResolvedValue({ data: { endpoint: "https://push.example/x" } })

    await saveSubscription({
      endpoint: "https://push.example/x",
      keys: { p256dh: "p", auth: "a" },
    } as PushSubscriptionJSON)

    expect(mocks.subscribe).toHaveBeenCalledWith({
      body: {
        endpoint: "https://push.example/x",
        keys: { p256dh: "p", auth: "a" },
        user_agent: undefined,
      },
    })
  })
})

describe("offline mutation service-worker contracts", () => {
  it("does not read service-worker readiness when no controller exists", async () => {
    const register = vi.fn()
    const serviceWorker = {
      controller: null,
      get ready(): Promise<unknown> {
        throw new Error("ready must not be read without a controller")
      },
    }
    vi.stubGlobal("navigator", { serviceWorker })

    await expect(
      enqueueOfflineMutation({ url: "/api/v1/events/1", method: "PATCH", payload: {} })
    ).resolves.toBeUndefined()
    expect(register).not.toHaveBeenCalled()
  })

  it("does not access a missing sync property before posting a fallback message", async () => {
    const postMessage = vi.fn()
    const getSync = vi.fn(() => {
      throw new Error("sync must not be read when unsupported")
    })
    const ready = new Proxy(
      {},
      {
        has: (_target, property) => property !== "sync",
        get: (target, property, receiver) => {
          if (property === "sync") return getSync()
          return Reflect.get(target, property, receiver)
        },
      }
    )
    vi.stubGlobal("navigator", {
      serviceWorker: { controller: { postMessage }, ready: Promise.resolve(ready) },
    })

    await enqueueOfflineMutation({ url: "/api/v1/news/1", method: "PATCH", payload: {} })
    expect(getSync).not.toHaveBeenCalled()
    expect(postMessage).toHaveBeenCalledOnce()
  })
})
