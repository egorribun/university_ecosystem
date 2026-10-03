import { dehydrate, hydrate, keepPreviousData, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, render, renderHook, waitFor } from "@testing-library/react"
import { useLayoutEffect, type PropsWithChildren } from "react"
import { renderToString } from "react-dom/server"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { NewsItem } from "@/api/news"
import type { Event } from "@/types/Event"
import type { UserState } from "@/types/Auth"
import { useAuthStore } from "@/stores/useAuthStore"
import { createQueryClient } from "@/app/queryClient"
import { acceptBrowserSessionGeneration, invalidateSessionEpoch } from "@/stores/sessionEpoch"
import api from "@/api/client"
import { useAuthApi } from "@/hooks/auth/useAuthApi"
import { withExpectedConsole } from "@/tests/strictConsole"
import { useRelatedNews } from "@/hooks/useRelatedNews"
import { useRelatedEvents } from "@/hooks/useRelatedEvents"
import { useArticleNavigation } from "@/hooks/useArticleNavigation"

const requests = vi.hoisted(() => ({ news: vi.fn(), events: vi.fn() }))
vi.mock("@/api/generated/sdk.gen", () => ({
  newsListApiV1NewsGet: requests.news,
  allEventsApiV1EventsGet: requests.events,
  myEventsApiV1EventsMyGet: vi.fn(),
}))
vi.mock("@/api/news", () => ({ fetchNewsItem: vi.fn() }))
vi.mock("@/hooks/auth/useProfileSync", () => ({ fetchCurrentUser: vi.fn() }))
vi.mock("@/push/subscribe", () => ({
  hasPushConsent: () => false,
  releasePushServerBinding: async () => undefined,
  setPushConsent: vi.fn(),
  syncPushForConfirmedIdentity: vi.fn(),
}))

import { newsListQueryKey, prefetchNewsListQuery, useNewsListQuery } from "../news"
import {
  eventsListQueryKey,
  prefetchEventsListQuery,
  useEventNavigation,
  useEventsListQuery,
} from "../events"

const setIdentity = (id: string | null, loading = false) => {
  acceptBrowserSessionGeneration()
  invalidateSessionEpoch()
  useAuthStore.setState({ user: id === null ? null : ({ id } as UserState), loading })
}
const newsItem = (is_liked: boolean): NewsItem =>
  ({ id: "article", title: "Article", is_liked }) as NewsItem
const page = <T,>(items: T[]) => ({
  status: 200,
  data: { items, total: items.length, limit: 12, cursor: null, next_cursor: null, has_more: false },
})
const deferred = <T,>() => {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((accept) => {
    resolve = accept
  })
  return { promise, resolve }
}
const createWrapper = () => {
  const client = createQueryClient()
  client.setDefaultOptions({ queries: { retry: false, gcTime: 0 } })
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return { client, wrapper: Wrapper }
}

beforeEach(() => {
  requests.news.mockReset()
  requests.events.mockReset()
  window.localStorage.clear()
  vi.restoreAllMocks()
  setIdentity("account-a")
})
afterEach(() => {
  cleanup()
  setIdentity(null)
  window.localStorage.clear()
})

describe("personalized list cache isolation", () => {
  it("keeps each account's liked state and offline snapshot separate", async () => {
    const liked = newsItem(true)
    const unliked = newsItem(false)
    requests.news.mockResolvedValueOnce(page([liked])).mockResolvedValueOnce(page([unliked]))
    const { wrapper } = createWrapper()
    const { result, unmount } = renderHook(() => useNewsListQuery({ language: "en" }), { wrapper })
    await waitFor(() => expect(result.current.news).toEqual([liked]))
    await waitFor(() =>
      expect(window.localStorage.getItem("news:list:account:account-a:en")).toBe(
        JSON.stringify([liked])
      )
    )
    expect(window.localStorage.getItem("news:list:en")).toBeNull()

    act(() => setIdentity("account-b"))
    expect(result.current.news).toEqual([])
    await waitFor(() => expect(result.current.news).toEqual([unliked]))
    await waitFor(() =>
      expect(window.localStorage.getItem("news:list:account:account-b:en")).toBe(
        JSON.stringify([unliked])
      )
    )
    unmount()

    setIdentity("account-a")
    requests.news.mockRejectedValue(new Error("offline"))
    const offline = renderHook(() => useNewsListQuery({ language: "en" }), createWrapper())
    await waitFor(() => expect(offline.result.current.isError).toBe(true))
    expect(offline.result.current.news).toEqual([liked])
    expect(window.localStorage.getItem("news:list:account:account-b:en")).toBe(
      JSON.stringify([unliked])
    )
  })

  it("ignores runtime selectors that could retain another account's selected news", async () => {
    const delayed = deferred<ReturnType<typeof page<NewsItem>>>()
    requests.news.mockResolvedValueOnce(page([newsItem(true)])).mockReturnValueOnce(delayed.promise)
    window.localStorage.setItem("news:list:account:account-b:en", JSON.stringify([newsItem(false)]))
    const runtimeOptions = {
      enabled: true,
      select: (data: { pages: Array<{ items: NewsItem[] }> }) => {
        if (data.pages[0]?.items[0]?.is_liked === false) throw new Error("B selector failed")
        return data
      },
    }
    const { result } = renderHook(
      () => useNewsListQuery({ language: "en" }, runtimeOptions),
      createWrapper()
    )
    await waitFor(() => expect(result.current.news).toEqual([newsItem(true)]))
    act(() => setIdentity("account-b"))
    expect(result.current.news).toEqual([newsItem(false)])
    expect(result.current.data?.pages.flatMap((item) => item.items)).toEqual([newsItem(false)])
    await act(async () => delayed.resolve(page([])))
  })

  it("ignores runtime selectors that could retain another account's selected events", async () => {
    const first = [{ id: "event-a", is_registered: true }] as Event[]
    const second = [{ id: "event-b", is_registered: false }] as Event[]
    const delayed = deferred<ReturnType<typeof page<Event>>>()
    requests.events.mockResolvedValueOnce(page(first)).mockReturnValueOnce(delayed.promise)
    window.localStorage.setItem("events:list:account:account-b:en:all", JSON.stringify(second))
    const runtimeOptions = {
      enabled: true,
      select: (data: { pages: Array<{ items: Event[] }> }) => {
        if (data.pages[0]?.items[0]?.is_registered === false) throw new Error("B selector failed")
        return data
      },
    }
    const { result } = renderHook(
      () => useEventsListQuery({ language: "en" }, runtimeOptions),
      createWrapper()
    )
    await waitFor(() => expect(result.current.events).toEqual(first))
    act(() => setIdentity("account-b"))
    expect(result.current.events).toEqual(second)
    expect(result.current.data?.pages.flatMap((item) => item.items)).toEqual(second)
    await act(async () => delayed.resolve(page([])))
  })

  it("does not let an injected previous-data placeholder carry account A into B", async () => {
    const firstEvent = [{ id: "event-a", is_registered: true }] as Event[]
    const secondEvent = [{ id: "event-b", is_registered: false }] as Event[]
    const delayedNews = deferred<ReturnType<typeof page<NewsItem>>>()
    const delayedEvents = deferred<ReturnType<typeof page<Event>>>()
    requests.news
      .mockResolvedValueOnce(page([newsItem(true)]))
      .mockReturnValueOnce(delayedNews.promise)
    requests.events
      .mockResolvedValueOnce(page(firstEvent))
      .mockReturnValueOnce(delayedEvents.promise)
    window.localStorage.setItem("news:list:account:account-b:en", JSON.stringify([newsItem(false)]))
    window.localStorage.setItem("events:list:account:account-b:en:all", JSON.stringify(secondEvent))
    const runtimeOptions = { enabled: true, placeholderData: keepPreviousData }
    const { result } = renderHook(
      () => ({
        news: useNewsListQuery({ language: "en" }, runtimeOptions),
        events: useEventsListQuery({ language: "en" }, runtimeOptions),
      }),
      createWrapper()
    )
    await waitFor(() => expect(result.current.news.news).toEqual([newsItem(true)]))
    await waitFor(() => expect(result.current.events.events).toEqual(firstEvent))
    act(() => setIdentity("account-b"))
    expect.soft(result.current.news.news).toEqual([newsItem(false)])
    expect.soft(result.current.events.events).toEqual(secondEvent)
    await act(async () => {
      delayedNews.resolve(page([]))
      delayedEvents.resolve(page([]))
    })
  })

  it("ignores runtime initial-data injection in favor of confirmed-account snapshots", () => {
    setIdentity("account-b")
    const currentEvent = [{ id: "event-b" }] as Event[]
    window.localStorage.setItem("news:list:account:account-b:en", JSON.stringify([newsItem(false)]))
    window.localStorage.setItem(
      "events:list:account:account-b:en:all",
      JSON.stringify(currentEvent)
    )
    const newsOptions = {
      enabled: false,
      initialData: { pages: [page([newsItem(true)]).data], pageParams: [null] },
    }
    const eventOptions = {
      enabled: false,
      initialData: { pages: [page([{ id: "event-a" }] as Event[]).data], pageParams: [null] },
    }
    const { result } = renderHook(
      () => ({
        news: useNewsListQuery({ language: "en" }, newsOptions),
        events: useEventsListQuery({ language: "en" }, eventOptions),
      }),
      createWrapper()
    )
    expect.soft(result.current.news.news).toEqual([newsItem(false)])
    expect.soft(result.current.events.events).toEqual(currentEvent)
  })

  it("does not let an injected structural-sharing callback retain a previous account", async () => {
    const delayed = deferred<ReturnType<typeof page<NewsItem>>>()
    requests.news.mockResolvedValueOnce(page([newsItem(true)])).mockReturnValueOnce(delayed.promise)
    window.localStorage.setItem("news:list:account:account-b:en", JSON.stringify([newsItem(false)]))
    const runtimeOptions = {
      enabled: true,
      structuralSharing: (previous: unknown, next: unknown) => previous ?? next,
    }
    const { result } = renderHook(
      () => useNewsListQuery({ language: "en" }, runtimeOptions),
      createWrapper()
    )
    await waitFor(() => expect(result.current.news).toEqual([newsItem(true)]))
    act(() => setIdentity("account-b"))
    expect.soft(result.current.news).toEqual([newsItem(false)])
    expect.soft(result.current.data?.pages.flatMap((item) => item.items)).toEqual([newsItem(false)])
    await act(async () => delayed.resolve(page([])))
  })

  it("rejects legacy shared news and events even for a confirmed account", () => {
    window.localStorage.setItem("news:list:en", JSON.stringify([newsItem(true)]))
    window.localStorage.setItem("events:list:en:all", JSON.stringify([{ id: "private-event" }]))
    const { result } = renderHook(
      () => ({
        news: useNewsListQuery({ language: "en" }, { enabled: false }),
        events: useEventsListQuery({ language: "en" }, { enabled: false }),
      }),
      createWrapper()
    )
    expect(result.current.news.news).toEqual([])
    expect(result.current.events.events).toEqual([])
  })

  it("does not adopt legacy news as the fallback for a 304 response", async () => {
    window.localStorage.setItem("news:list:en", JSON.stringify([newsItem(true)]))
    requests.news.mockResolvedValueOnce({ status: 304, data: undefined })
    const { result } = renderHook(() => useNewsListQuery({ language: "en" }), createWrapper())
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.news).toEqual([])
    expect(window.localStorage.getItem("news:list:account:account-a:en")).toBe("[]")
  })

  it.each([null, "ssr-stub", "-1", "lhci-preview", "account-a"])(
    "does not read or write private cache for unresolved identity %s",
    (identity) => {
      setIdentity(identity, identity === "account-a")
      window.localStorage.setItem("news:list:en", JSON.stringify([newsItem(true)]))
      window.localStorage.setItem(
        "news:list:account:account-a:en",
        JSON.stringify([newsItem(true)])
      )
      window.localStorage.setItem("events:list:en:all", JSON.stringify([{ id: "legacy" }]))
      window.localStorage.setItem(
        "events:list:account:account-a:en:all",
        JSON.stringify([{ id: "private" }])
      )
      const { result } = renderHook(
        () => ({
          news: useNewsListQuery({ language: "en" }),
          events: useEventsListQuery({ language: "en" }),
        }),
        createWrapper()
      )
      expect(result.current.news.news).toEqual([])
      expect(result.current.events.events).toEqual([])
      expect(requests.news).not.toHaveBeenCalled()
      expect(requests.events).not.toHaveBeenCalled()
    }
  )

  it("discards a delayed account-A network result after switching to account B", async () => {
    const delayed = deferred<ReturnType<typeof page<NewsItem>>>()
    requests.news
      .mockReturnValueOnce(delayed.promise)
      .mockResolvedValueOnce(page([newsItem(false)]))
    const { result } = renderHook(() => useNewsListQuery({ language: "en" }), createWrapper())
    await waitFor(() => expect(requests.news).toHaveBeenCalledOnce())
    act(() => setIdentity("account-b"))
    await waitFor(() => expect(result.current.news).toEqual([newsItem(false)]))
    await act(async () => delayed.resolve(page([newsItem(true)])))
    expect(result.current.news).toEqual([newsItem(false)])
    expect(window.localStorage.getItem("news:list:account:account-a:en")).toBeNull()
    expect(window.localStorage.getItem("news:list:account:account-b:en")).toBe(
      JSON.stringify([newsItem(false)])
    )
  })

  it("discards a delayed result when the auth lifetime ends with the same user id", async () => {
    const delayed = deferred<ReturnType<typeof page<NewsItem>>>()
    requests.news.mockReturnValueOnce(delayed.promise)
    const { result } = renderHook(() => useNewsListQuery({ language: "en" }), createWrapper())
    await waitFor(() => expect(requests.news).toHaveBeenCalledOnce())
    act(() => invalidateSessionEpoch())
    await act(async () => delayed.resolve(page([newsItem(true)])))
    await waitFor(() => expect(result.current.isFetching).toBe(false))
    expect(result.current.news).toEqual([])
    expect(window.localStorage.getItem("news:list:account:account-a:en")).toBeNull()
  })

  it("fences the storage effect when auth changes after rendering a successful response", async () => {
    requests.news.mockResolvedValueOnce(page([newsItem(true)]))
    const { result } = renderHook(() => {
      const feed = useNewsListQuery({ language: "en" })
      useLayoutEffect(() => {
        if (feed.isSuccess) invalidateSessionEpoch()
      }, [feed.isSuccess])
      return feed
    }, createWrapper())
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(window.localStorage.getItem("news:list:account:account-a:en")).toBeNull()
  })

  it("fences a late storage effect when another tab rotates the session before broadcast", async () => {
    requests.news.mockResolvedValueOnce(page([newsItem(true)]))
    const { result } = renderHook(() => {
      const feed = useNewsListQuery({ language: "en" })
      useLayoutEffect(() => {
        if (feed.isSuccess) {
          window.localStorage.setItem(
            "ecosystem.session.generation.v1",
            JSON.stringify({
              nonce: "other-tab-session",
              hash: null,
            })
          )
        }
      }, [feed.isSuccess])
      return feed
    }, createWrapper())
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(window.localStorage.getItem("news:list:account:account-a:en")).toBeNull()
  })

  it("rejects warm lists on a new mount after remote rotation before the auth broadcast", async () => {
    requests.news.mockResolvedValueOnce(page([newsItem(true)]))
    requests.events.mockResolvedValueOnce(page([{ id: "account-a-event" }]))
    const { wrapper } = createWrapper()
    const useFeeds = () => ({
      news: useNewsListQuery({ language: "en" }),
      events: useEventsListQuery({ language: "en" }),
    })
    const first = renderHook(useFeeds, { wrapper })
    await waitFor(() => expect(first.result.current.news.news).toEqual([newsItem(true)]))
    await waitFor(() =>
      expect(first.result.current.events.events).toEqual([{ id: "account-a-event" }])
    )
    first.unmount()
    window.localStorage.setItem(
      "ecosystem.session.generation.v1",
      JSON.stringify({
        nonce: "remote-login",
        hash: null,
      })
    )
    expect(useAuthStore.getState().user?.id).toBe("account-a")

    const second = renderHook(useFeeds, { wrapper })
    expect(second.result.current.news.news).toEqual([])
    expect(second.result.current.events.events).toEqual([])
    expect(second.result.current.news.data?.pages.flatMap((item) => item.items) ?? []).toEqual([])
    expect(second.result.current.events.data?.pages.flatMap((item) => item.items) ?? []).toEqual([])
    expect(requests.news).toHaveBeenCalledOnce()
    expect(requests.events).toHaveBeenCalledOnce()
  })

  it("rejects new related-item and navigation cache reads after a remote account switch", () => {
    const articles = ["current", "private"].map((id) => ({
      ...newsItem(true),
      id,
      content: "Article text",
      title: `Account A ${id}`,
    }))
    const events = ["current", "private"].map((id) => ({
      id,
      title: `Account A ${id}`,
      is_registered: true,
      my_qr_token: "account-a-qr",
    })) as Event[]
    const { client, wrapper } = createWrapper()
    client.setQueryData(newsListQueryKey({ language: "en" }), {
      pages: [page(articles).data],
      pageParams: [null],
    })
    client.setQueryData(eventsListQueryKey({ language: "en" }), {
      pages: [page(events).data],
      pageParams: [null],
    })
    const useCachedReaders = () => ({
      news: useRelatedNews("current", "general"),
      events: useRelatedEvents("current", "other"),
      articles: useArticleNavigation("current"),
      navigation: useEventNavigation("current"),
    })
    const first = renderHook(useCachedReaders, { wrapper })
    expect(first.result.current.news).toEqual([articles[1]])
    expect(first.result.current.events).toEqual([events[1]])
    expect(first.result.current.articles.nextTitle).toBe("Account A private")
    expect(first.result.current.navigation.nextTitle).toBe("Account A private")
    first.unmount()
    window.localStorage.setItem(
      "ecosystem.session.generation.v1",
      JSON.stringify({
        nonce: "remote-new-account",
        hash: null,
      })
    )

    const second = renderHook(useCachedReaders, { wrapper })
    expect.soft(second.result.current.news).toEqual([])
    expect.soft(second.result.current.events).toEqual([])
    expect
      .soft(second.result.current.articles)
      .toEqual({ prevId: null, nextId: null, prevTitle: null, nextTitle: null })
    expect
      .soft(second.result.current.navigation)
      .toEqual({ prevId: null, nextId: null, prevTitle: null, nextTitle: null })
  })

  it("discards delayed event data from the previous account", async () => {
    const delayed = deferred<ReturnType<typeof page<Event>>>()
    const first = [{ id: "event-a", is_registered: true }] as Event[]
    const second = [{ id: "event-b", is_registered: false }] as Event[]
    requests.events.mockReturnValueOnce(delayed.promise).mockResolvedValueOnce(page(second))
    const { result } = renderHook(() => useEventsListQuery({ language: "en" }), createWrapper())
    await waitFor(() => expect(requests.events).toHaveBeenCalledOnce())
    act(() => setIdentity("account-b"))
    await waitFor(() => expect(result.current.events).toEqual(second))
    await act(async () => delayed.resolve(page(first)))
    expect(result.current.events).toEqual(second)
  })

  it("rejects imperative refetch and prefetch without a confirmed identity", async () => {
    setIdentity(null)
    const { client, wrapper } = createWrapper()
    const { result } = renderHook(
      () => ({
        news: useNewsListQuery({ language: "en" }),
        events: useEventsListQuery({ language: "en" }),
      }),
      { wrapper }
    )
    await act(async () => {
      await Promise.all([
        result.current.news.refetch(),
        result.current.events.refetch(),
        prefetchNewsListQuery(client, { language: "en" }),
        prefetchEventsListQuery(client, { language: "en" }),
      ])
    })
    expect(requests.news).not.toHaveBeenCalled()
    expect(requests.events).not.toHaveBeenCalled()
    expect(result.current.news.news).toEqual([])
    expect(result.current.events.events).toEqual([])
  })

  it("switches the event offline reader to the confirmed account's namespace", () => {
    const first = [{ id: "event-a" }] as Event[]
    const second = [{ id: "event-b" }] as Event[]
    window.localStorage.setItem("events:list:account:account-a:en:all", JSON.stringify(first))
    window.localStorage.setItem("events:list:account:account-b:en:all", JSON.stringify(second))
    const { result } = renderHook(
      () => useEventsListQuery({ language: "en" }, { enabled: false }),
      createWrapper()
    )
    expect(result.current.events).toEqual(first)
    act(() => setIdentity("account-b"))
    expect(result.current.events).toEqual(second)
    act(() => setIdentity(null))
    expect(result.current.events).toEqual([])
    expect(result.current.data).toBeUndefined()
  })

  it("hides the previous feed after production logout fails and local auth is cleared", async () => {
    requests.news.mockResolvedValueOnce(page([newsItem(true)]))
    vi.spyOn(api, "post").mockRejectedValueOnce(new Error("offline logout"))
    const { result } = renderHook(() => {
      const state = useAuthStore()
      const auth = useAuthApi(
        state.user,
        state.setUser,
        vi.fn(),
        () => setIdentity(null),
        vi.fn(),
        false,
        vi.fn(),
        vi.fn()
      )
      return { auth, feed: useNewsListQuery({ language: "en" }) }
    }, createWrapper())
    await waitFor(() => expect(result.current.feed.news).toEqual([newsItem(true)]))

    await withExpectedConsole("error", "Logout failed", async () => {
      await act(async () => result.current.auth.logout())
    })

    expect(useAuthStore.getState().user).toBeNull()
    expect(result.current.feed.news).toEqual([])
    expect(result.current.feed.data).toBeUndefined()
    requests.news.mockRejectedValue(new Error("offline"))
    act(() => setIdentity("account-b"))
    await waitFor(() => expect(result.current.feed.isError).toBe(true))
    expect(result.current.feed.news).toEqual([])
  })

  it("hydrates same-request SSR lists without mismatch and clears them on account confirmation", async () => {
    setIdentity(null)
    requests.news.mockResolvedValueOnce(page([newsItem(true)]))
    requests.events.mockResolvedValueOnce(page([{ id: "server-event" }]))
    const Probe = () => {
      const news = useNewsListQuery({ language: "en" })
      const events = useEventsListQuery({ language: "en" })
      return <span>{`${news.news[0]?.is_liked}:${events.events[0]?.id}`}</span>
    }
    vi.stubGlobal("window", undefined)
    let serverHtml: string
    let snapshot: ReturnType<typeof dehydrate>
    try {
      const serverClient = createQueryClient()
      await Promise.all([
        prefetchNewsListQuery(serverClient, { language: "en" }),
        prefetchEventsListQuery(serverClient, { language: "en" }),
      ])
      snapshot = dehydrate(serverClient)
      serverHtml = renderToString(
        <QueryClientProvider client={serverClient}>
          <Probe />
        </QueryClientProvider>
      )
    } finally {
      vi.unstubAllGlobals()
    }
    expect(serverHtml).toContain("true:server-event")
    const { client, wrapper } = createWrapper()
    hydrate(client, snapshot)
    const container = document.createElement("div")
    document.body.appendChild(container)
    container.innerHTML = serverHtml
    render(<Probe />, { container, hydrate: true, wrapper })
    expect(container.textContent).toBe("true:server-event")
    expect(window.localStorage.getItem("news:list:en")).toBeNull()

    requests.news.mockResolvedValueOnce(page([newsItem(false)]))
    requests.events.mockResolvedValueOnce(page([{ id: "confirmed-event" }]))
    act(() => setIdentity("account-b"))
    await waitFor(() => expect(container.textContent).toBe("false:confirmed-event"))
  })
})
