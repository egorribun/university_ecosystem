import {
  dehydrate,
  QueryClient,
  QueryClientProvider,
  type UseQueryResult,
} from "@tanstack/react-query"
import { act, cleanup, renderHook, waitFor } from "@testing-library/react"
import { del, get } from "idb-keyval"
import { http, HttpResponse } from "msw"
import type { PropsWithChildren } from "react"
import { renderToString } from "react-dom/server"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import "@/api/client"
import * as sdk from "@/api/generated/sdk.gen"
import { idbPersister, persistOptions, setQueryCacheIdentity } from "@/app/queryClient"
import i18n from "@/i18n/config"
import type { Event } from "@/types/Event"
import type { UserState } from "@/types/Auth"
import { useAuthStore } from "@/stores/useAuthStore"
import {
  acceptBrowserSessionGeneration,
  invalidateSessionEpoch,
  rotateBrowserSession,
} from "@/stores/sessionEpoch"
import { server } from "@/tests/mocks/server"
import * as eventHooks from "../events"

type PageParams = {
  language: "en" | "ru"
  sort: "newest_desc" | "popular" | "upcoming"
  cursor: string | null
  category?: "lecture" | "seminar"
  dateRange?: "today" | "week" | "month"
  dateAnchor?: string
  upcomingAfter?: string
}
type Page = {
  items: Event[]
  total: null
  limit: number
  cursor: string | null
  next_cursor: string | null
  has_more: boolean
}
type PageHook = (params: PageParams, options?: unknown) => UseQueryResult<Page, Error>

const pageHook = () => {
  const candidate = (eventHooks as typeof eventHooks & { useMyEventsPageQuery?: PageHook })
    .useMyEventsPageQuery
  expect(candidate).toBeTypeOf("function")
  return candidate!
}

const setIdentity = (id: string | null) => {
  acceptBrowserSessionGeneration()
  invalidateSessionEpoch()
  useAuthStore.setState({ user: id === null ? null : ({ id } as UserState), loading: false })
}

const makeEvent = (id: string, count: number): Event => ({
  id,
  title: `Event ${id}`,
  created_at: "2026-01-01T00:00:00Z",
  created_by: "owner",
  ends_at: "2026-12-10T11:00:00Z",
  starts_at: "2026-12-10T10:00:00Z",
  is_active: true,
  is_registered: true,
  participant_count: count,
  my_qr_token: null,
})

const firstPage = (items: Event[] = [makeEvent("event-a", 4)]): Page => ({
  items,
  total: null,
  limit: 12,
  cursor: null,
  next_cursor: null,
  has_more: false,
})

const params: PageParams = { language: "en", sort: "newest_desc", cursor: null }

const makeWrapper = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return { client, wrapper }
}

beforeEach(() => {
  localStorage.clear()
  setIdentity("account-a")
})

afterEach(async () => {
  cleanup()
  vi.restoreAllMocks()
  setIdentity(null)
  localStorage.clear()
  await i18n.changeLanguage("en")
})

describe("AUD-260 bounded My Events query", () => {
  it("requests the frozen locale and real popular order without HTTP cache or persistence", async () => {
    await i18n.changeLanguage("ru")
    const seen: { url?: URL; cacheControl?: string | null; language?: string | null } = {}
    server.use(
      http.get("*/events/my/page", ({ request }) => {
        seen.url = new URL(request.url)
        seen.cacheControl = request.headers.get("cache-control")
        seen.language = request.headers.get("accept-language")
        return HttpResponse.json(firstPage([makeEvent("popular", 37)]))
      })
    )
    const hook = pageHook()
    const { client, wrapper } = makeWrapper()
    const { result } = renderHook(() => hook({ ...params, sort: "popular" }), { wrapper })
    await waitFor(() => expect(result.current.data?.items[0]?.participant_count).toBe(37))
    expect(result.current.data?.total).toBeNull()
    expect(seen.url?.searchParams.get("limit")).toBe("12")
    expect(seen.url?.searchParams.get("sort")).toBe("popular")
    expect(seen.url?.searchParams.get("lang")).toBe("en")
    expect(seen.language).toBe("en")
    expect(seen.cacheControl).toMatch(/\bno-store\b/iu)
    const query = client.getQueryCache().getAll()[0]!
    expect(query.meta?.persist).toBe(false)
    expect(query.gcTime).toBe(0)
    expect(persistOptions.dehydrateOptions?.shouldDehydrateQuery?.(query)).toBe(false)
    client.clear()
  })

  it("does not accept an existing legacy account snapshot as a page", async () => {
    localStorage.setItem("events:my:en:account-a", JSON.stringify([makeEvent("legacy", 3)]))
    server.use(http.get("*/events/my/page", () => new Promise(() => undefined)))
    const hook = pageHook()
    const { client, wrapper } = makeWrapper()
    const { result } = renderHook(() => hook(params), { wrapper })
    expect(result.current.data).toBeUndefined()
    expect(result.current.isPending).toBe(true)
    client.clear()
  })

  it("sends the complete frozen upcoming-page context", async () => {
    let requested: URL | undefined
    server.use(
      http.get("*/events/my/page", ({ request }) => {
        requested = new URL(request.url)
        return HttpResponse.json({
          ...firstPage(),
          cursor: "cursor-one",
          next_cursor: "cursor-two",
          has_more: true,
        })
      })
    )
    const hook = pageHook()
    const { client, wrapper } = makeWrapper()
    const { result } = renderHook(
      () =>
        hook({
          language: "ru",
          sort: "upcoming",
          cursor: "cursor-one",
          category: "seminar",
          dateRange: "week",
          dateAnchor: "2026-10-28",
          upcomingAfter: "2026-10-28T12:30:00.000Z",
        }),
      { wrapper }
    )
    await waitFor(() => expect(result.current.data?.next_cursor).toBe("cursor-two"))
    expect(Object.fromEntries(requested!.searchParams)).toEqual({
      limit: "12",
      sort: "upcoming",
      lang: "ru",
      cursor: "cursor-one",
      category: "seminar",
      date_range: "week",
      date_anchor: "2026-10-28",
      upcoming_after: "2026-10-28T12:30:00.000Z",
    })
    client.clear()
  })

  it.each([
    ["array", () => [makeEvent("bad", 1)]],
    ["known total", () => ({ ...firstPage(), total: 1 })],
    ["wrong limit", () => ({ ...firstPage(), limit: 13 })],
    ["wrong cursor", () => ({ ...firstPage(), cursor: "different" })],
    ["missing continuation", () => ({ ...firstPage(), has_more: true })],
    ["unexpected continuation", () => ({ ...firstPage(), next_cursor: "next" })],
    ["malformed item", () => ({ ...firstPage(), items: [{ id: "bad" }] })],
    [
      "malformed item description",
      () => ({
        ...firstPage(),
        items: [{ ...makeEvent("bad", 1), description: 123 }],
      }),
    ],
    [
      "malformed item date",
      () => ({
        ...firstPage(),
        items: [{ ...makeEvent("bad", 1), starts_at: "not-a-date" }],
      }),
    ],
    ["more than one page", () => ({ ...firstPage(), items: Array(13).fill(makeEvent("x", 1)) })],
  ])("rejects malformed page: %s", async (_name, body) => {
    // These deliberately violate the published response contract, so inject
    // them at the SDK boundary rather than bypassing the global MSW validator.
    vi.spyOn(sdk, "myEventsPageApiV1EventsMyPageGet").mockResolvedValue({
      status: 200,
      data: body(),
    } as never)
    const hook = pageHook()
    const { client, wrapper } = makeWrapper()
    const { result } = renderHook(() => hook(params), { wrapper })
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.data).toBeUndefined()
    client.clear()
  })

  it("rejects a 304 without an exact cached page", async () => {
    server.use(http.get("*/events/my/page", () => new HttpResponse(null, { status: 304 })))
    const hook = pageHook()
    const { client, wrapper } = makeWrapper()
    const { result } = renderHook(() => hook(params), { wrapper })
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.data).toBeUndefined()
    client.clear()
  })

  it.each([199, 304, 500])("rejects SDK responses with status %i", async (status) => {
    vi.spyOn(sdk, "myEventsPageApiV1EventsMyPageGet").mockResolvedValue({
      status,
      data: firstPage(),
    } as never)
    const hook = pageHook()
    const { client, wrapper } = makeWrapper()
    const { result } = renderHook(() => hook(params), { wrapper })
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.data).toBeUndefined()
    client.clear()
  })

  it("rejects a continuation that repeats the requested cursor", async () => {
    vi.spyOn(sdk, "myEventsPageApiV1EventsMyPageGet").mockResolvedValue({
      status: 200,
      data: { ...firstPage(), cursor: "same", next_cursor: "same", has_more: true },
    } as never)
    const hook = pageHook()
    const { client, wrapper } = makeWrapper()
    const { result } = renderHook(() => hook({ ...params, cursor: "same" }), { wrapper })
    await waitFor(() => expect(result.current.isError).toBe(true))
    client.clear()
  })

  it("does not let caller options persist or reuse data from a previous page", async () => {
    server.use(http.get("*/events/my/page", () => HttpResponse.json(firstPage())))
    const hook = pageHook()
    const { client, wrapper } = makeWrapper()
    const { result } = renderHook(
      () =>
        hook(params, {
          gcTime: 300_000,
          meta: { persist: true },
          placeholderData: firstPage([makeEvent("foreign", 2)]),
        }),
      { wrapper }
    )
    expect(result.current.data).toBeUndefined()
    await waitFor(() => expect(result.current.data?.items[0]?.id).toBe("event-a"))
    const query = client.getQueryCache().getAll()[0]!
    expect(query.meta?.persist).toBe(false)
    expect(query.gcTime).toBe(0)
    client.clear()
  })

  it("excludes the actual My page from the account IndexedDB snapshot", async () => {
    rotateBrowserSession()
    setIdentity("account-a")
    setQueryCacheIdentity("account-a")
    server.use(
      http.get("*/events/my/page", () =>
        HttpResponse.json(firstPage([{ ...makeEvent("private", 2), my_qr_token: "page-marker" }]))
      )
    )
    const hook = pageHook()
    const { client, wrapper } = makeWrapper()
    client.setQueryData(["users", "me"], { id: "account-a" })
    client.setQueryData(["public-example"], { value: "present" })
    const { result } = renderHook(() => hook(params), { wrapper })
    try {
      await waitFor(() => expect(result.current.data?.items[0]?.id).toBe("private"))
      await idbPersister.persistClient({
        timestamp: Date.now(),
        buster: "1.0.0",
        clientState: dehydrate(client, { shouldDehydrateQuery: () => true }),
      })
      const saved = await get<{ clientState: { queries: Array<{ queryKey: unknown[] }> } }>(
        "reactQuery:v2:account-a"
      )
      expect(
        saved?.clientState.queries.some((query) => query.queryKey[0] === "public-example")
      ).toBe(true)
      expect(saved?.clientState.queries.some((query) => query.queryKey[1] === "my-page-v2")).toBe(
        false
      )
      expect(JSON.stringify(saved)).not.toContain("page-marker")
    } finally {
      client.clear()
      await del("reactQuery:v2:account-a")
      setQueryCacheIdentity(null)
    }
  })

  it("does not expose a warm page after the same account enters a new session", async () => {
    let release!: () => void
    const pending = new Promise<void>((resolve) => {
      release = resolve
    })
    let count = 0
    server.use(
      http.get("*/events/my/page", async () => {
        count += 1
        if (count === 1) return HttpResponse.json(firstPage([makeEvent("old-session", 1)]))
        await pending
        return HttpResponse.json(firstPage([makeEvent("new-session", 2)]))
      })
    )
    const hook = pageHook()
    const { client, wrapper } = makeWrapper()
    const { result, rerender } = renderHook(() => hook(params), { wrapper })
    await waitFor(() => expect(result.current.data?.items[0]?.id).toBe("old-session"))
    act(() => {
      invalidateSessionEpoch()
      rerender()
    })
    expect(result.current.data).toBeUndefined()
    await waitFor(() => expect(count).toBe(2))
    await act(async () => release())
    await waitFor(() => expect(result.current.data?.items[0]?.id).toBe("new-session"))
    await waitFor(() => expect(client.getQueryCache().getAll()).toHaveLength(1))
    client.clear()
  })

  it("hides a warm page when another tab changes the session generation", async () => {
    server.use(http.get("*/events/my/page", () => HttpResponse.json(firstPage())))
    const hook = pageHook()
    const { client, wrapper } = makeWrapper()
    const { result, rerender } = renderHook(() => hook(params), { wrapper })
    await waitFor(() => expect(result.current.data?.items[0]?.id).toBe("event-a"))
    act(() => {
      localStorage.setItem(
        "ecosystem.session.generation.v1",
        JSON.stringify({ nonce: "different-session", hash: null })
      )
      rerender()
    })
    expect(result.current.data).toBeUndefined()
    client.clear()
  })

  it("guards a queued request both before sending and after its response", async () => {
    let release!: (response: unknown) => void
    const response = new Promise<unknown>((resolve) => {
      release = resolve
    })
    const spy = vi
      .spyOn(sdk, "myEventsPageApiV1EventsMyPageGet")
      .mockImplementation(() => response as never)
    const hook = pageHook()
    const { client, wrapper } = makeWrapper()
    renderHook(() => hook(params, { enabled: false }), { wrapper })
    const query = client.getQueryCache().getAll()[0]!
    const queryFn = query.options.queryFn
    expect(queryFn).toBeTypeOf("function")
    if (typeof queryFn !== "function") throw new Error("Expected a page query function")
    const run = () => Promise.resolve(queryFn({ signal: new AbortController().signal } as never))

    const inFlight = run()
    expect(spy).toHaveBeenCalledOnce()
    invalidateSessionEpoch()
    release({ status: 200, data: firstPage() })
    await expect(inFlight).rejects.toMatchObject({ name: "AbortError" })
    await expect(run()).rejects.toMatchObject({ name: "AbortError" })
    expect(spy).toHaveBeenCalledOnce()
    client.clear()
  })

  it("withholds a warm page selected after its session is invalidated", async () => {
    vi.spyOn(sdk, "myEventsPageApiV1EventsMyPageGet")
      .mockResolvedValueOnce({ status: 200, data: firstPage() } as never)
      .mockImplementation(() => new Promise(() => undefined) as never)
    const hook = pageHook()
    const { client, wrapper } = makeWrapper()
    const { result } = renderHook(() => hook(params), { wrapper })
    await waitFor(() => expect(result.current.data?.items[0]?.id).toBe("event-a"))
    const queryKey = client.getQueryCache().getAll()[0]!.queryKey
    act(() => {
      invalidateSessionEpoch()
      client.setQueryData(queryKey, firstPage([makeEvent("stale-update", 3)]))
    })
    await waitFor(() => expect(result.current.data).toBeUndefined())
    client.clear()
  })

  it("does not fetch private pages during server rendering", () => {
    const spy = vi.spyOn(sdk, "myEventsPageApiV1EventsMyPageGet")
    const hook = pageHook()
    const { client } = makeWrapper()
    function Probe() {
      const query = hook(params)
      return <div>{query.data?.items.length ?? "pending"}</div>
    }
    vi.stubGlobal("window", undefined)
    try {
      expect(
        renderToString(
          <QueryClientProvider client={client}>
            <Probe />
          </QueryClientProvider>
        )
      ).toContain("pending")
      expect(spy).not.toHaveBeenCalled()
    } finally {
      vi.unstubAllGlobals()
      client.clear()
    }
  })

  it("does not publish an old owner's delayed page after account change", async () => {
    let release!: () => void
    const pending = new Promise<void>((resolve) => {
      release = resolve
    })
    let count = 0
    server.use(
      http.get("*/events/my/page", async () => {
        count += 1
        if (count === 1) {
          await pending
          return HttpResponse.json(firstPage([makeEvent("account-a", 1)]))
        }
        return HttpResponse.json(firstPage([makeEvent("account-b", 2)]))
      })
    )
    const hook = pageHook()
    const { client, wrapper } = makeWrapper()
    const { result } = renderHook(() => hook(params), { wrapper })
    await waitFor(() => expect(count).toBe(1))
    act(() => setIdentity("account-b"))
    await waitFor(() => expect(result.current.data?.items[0]?.id).toBe("account-b"))
    await act(async () => release())
    expect(result.current.data?.items[0]?.id).toBe("account-b")
    client.clear()
  })
})
