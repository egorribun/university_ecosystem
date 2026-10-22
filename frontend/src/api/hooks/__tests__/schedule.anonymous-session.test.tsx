import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, renderHook, waitFor } from "@testing-library/react"
import type { PropsWithChildren } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import api from "@/api/client"
import {
  anonymousScheduleGroupsQueryKey,
  anonymousScheduleQueryKey,
  pageScheduleQueryOptions,
  scheduleGroupsQueryOptions,
} from "@/api/hooks/schedule"
import { scheduleGroupsQueryKey, scheduleQueryKey } from "@/components/schedule/scheduleUtils"
import { useScheduleData } from "@/hooks/useScheduleData"
import { acceptBrowserSessionGeneration } from "@/stores/sessionEpoch"
import { useAuthStore } from "@/stores/useAuthStore"

const groupId = "00000000-0000-0000-0000-000000000002"
const lesson = { id: "lesson-1", group_id: groupId, weekday: "Monday" }
const makeClient = () =>
  new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } })

const wrapperFor = (client: QueryClient) => {
  function ScheduleQueryClientWrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }

  return ScheduleQueryClientWrapper
}

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify([lesson]), { status: 200 }))
  )
})

afterEach(() => {
  cleanup()
  useAuthStore.setState({ user: null, loading: true })
  window.localStorage.clear()
  window.document.cookie = "session_cookie=; Max-Age=0; path=/"
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("anonymous schedule-by-group reads", () => {
  it("uses a separate non-persisted groups key and credentialless fixed endpoint", async () => {
    const groups = [{ id: groupId, name: "Public Group" }]
    const apiGet = vi.spyOn(api, "get")
    const options = scheduleGroupsQueryOptions(true, "en")
    const client = makeClient()

    expect(options.queryKey).toEqual(anonymousScheduleGroupsQueryKey)
    expect(options.queryKey).not.toEqual(scheduleGroupsQueryKey)
    expect(options.meta).toEqual({ persist: false })
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(groups), { status: 200 }))
    )
    await expect(client.fetchQuery({ ...options, retry: false })).resolves.toEqual(groups)

    expect(apiGet).not.toHaveBeenCalled()
    expect(fetch).toHaveBeenCalledTimes(1)
    const call = vi.mocked(fetch).mock.calls[0]
    expect(call).toBeDefined()
    if (!call) throw new Error("anonymous groups request missing")
    const url = new URL(String(call[0]), window.location.origin)
    expect(url.origin).toBe(window.location.origin)
    expect(url.pathname).toBe("/api/v1/groups")
    expect(call[1]).toMatchObject({ credentials: "omit", cache: "no-store" })
    expect(new Headers(call[1]?.headers).get("Accept-Language")).toBe("en")
    expect(new Headers(call[1]?.headers).has("Cookie")).toBe(false)
    expect(new Headers(call[1]?.headers).has("Authorization")).toBe(false)
  })

  it("uses a separate non-persisted cache key and credentialless fixed endpoint", async () => {
    const options = pageScheduleQueryOptions(groupId, true, "en")
    const client = makeClient()
    const apiGet = vi.spyOn(api, "get")

    expect(options.queryKey).toEqual(anonymousScheduleQueryKey(groupId))
    expect(options.queryKey).not.toEqual(scheduleQueryKey(groupId))
    expect(options.meta).toEqual({ persist: false })
    await expect(client.fetchQuery({ ...options, retry: false })).resolves.toEqual([lesson])

    expect(apiGet).not.toHaveBeenCalled()
    expect(fetch).toHaveBeenCalledTimes(1)
    const call = vi.mocked(fetch).mock.calls[0]
    expect(call).toBeDefined()
    if (!call) throw new Error("anonymous schedule request missing")
    const url = new URL(String(call[0]), window.location.origin)
    expect(url.origin).toBe(window.location.origin)
    expect(url.pathname).toBe(`/api/v1/schedule/${groupId}`)
    expect(call[1]).toMatchObject({ credentials: "omit", cache: "no-store" })
    expect(new Headers(call[1]?.headers).get("Accept-Language")).toBe("en")
    expect(new Headers(call[1]?.headers).has("Cookie")).toBe(false)
    expect(new Headers(call[1]?.headers).has("Authorization")).toBe(false)
  })

  it("does not show account A groups or send a successor cookie from a stale tab", async () => {
    const accountAGroup = { id: "00000000-0000-0000-0000-000000000010", name: "Account A" }
    const publicGroup = { id: groupId, name: "Public Group" }
    const client = makeClient()
    const apiGet = vi
      .spyOn(api, "get")
      .mockRejectedValue(new Error("authenticated Axios route used"))
    const generationKey = "ecosystem.session.generation.v1"
    window.localStorage.setItem(
      generationKey,
      JSON.stringify({ nonce: "generation-a", hash: "hash-a" })
    )
    acceptBrowserSessionGeneration()
    window.localStorage.setItem(
      generationKey,
      JSON.stringify({ nonce: "generation-b", hash: "hash-b" })
    )
    window.document.cookie = "session_cookie=successor-account-b; path=/"
    useAuthStore.setState({
      user: { id: "account-a", role: "admin", group_id: null } as never,
      loading: false,
    })
    client.setQueryData(scheduleGroupsQueryKey, [accountAGroup])

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = new URL(String(input), window.location.origin)
        if (url.pathname === "/api/v1/groups") {
          return new Response(JSON.stringify([publicGroup]), { status: 200 })
        }
        if (url.pathname === `/api/v1/schedule/${groupId}`) {
          return new Response("[]", { status: 200 })
        }
        throw new Error(`unexpected anonymous route: ${url.pathname}`)
      })
    )

    const observedGroups: Array<Array<{ id: string; name: string }>> = []
    const { result } = renderHook(
      () => {
        const snapshot = useScheduleData()
        observedGroups.push([...snapshot.groups])
        return snapshot
      },
      { wrapper: wrapperFor(client) }
    )
    await waitFor(() => expect(result.current.groups).toEqual([publicGroup]))

    expect(window.document.cookie).toContain("successor-account-b")
    expect(client.getQueryData(scheduleGroupsQueryKey)).toEqual([accountAGroup])
    expect(client.getQueryData(anonymousScheduleGroupsQueryKey)).toEqual([publicGroup])
    expect(
      client.getQueryCache().find({ queryKey: anonymousScheduleGroupsQueryKey })?.meta?.persist
    ).toBe(false)
    expect(result.current.groups).not.toContain(accountAGroup)
    expect(observedGroups.flat()).not.toContainEqual(accountAGroup)
    expect(apiGet).not.toHaveBeenCalled()
    const groupsCall = vi
      .mocked(fetch)
      .mock.calls.map(
        ([input, init]) => [new URL(String(input), window.location.origin), init] as const
      )
      .find(([url]) => url.pathname === "/api/v1/groups")
    expect(groupsCall).toBeDefined()
    expect(groupsCall?.[1]).toMatchObject({
      method: "GET",
      credentials: "omit",
      cache: "no-store",
    })
    expect(new Headers(groupsCall?.[1]?.headers).has("Cookie")).toBe(false)
    expect(new Headers(groupsCall?.[1]?.headers).has("Authorization")).toBe(false)
  })

  it("keeps the existing authenticated query identity and Axios route by default", async () => {
    const apiGet = vi.spyOn(api, "get").mockResolvedValue({ data: [lesson] } as never)
    const options = pageScheduleQueryOptions(groupId)
    const client = makeClient()

    expect(options.queryKey).toEqual(scheduleQueryKey(groupId))
    expect(options.meta).toBeUndefined()
    await expect(client.fetchQuery({ ...options, retry: false })).resolves.toEqual([lesson])

    expect(apiGet).toHaveBeenCalledWith(`/schedule/${groupId}`, expect.any(Object))
    expect(fetch).not.toHaveBeenCalled()
  })

  it("normalizes malformed successful public directory and lesson payloads to empty lists", async () => {
    const fetchMock = vi.fn(
      async () => new Response(JSON.stringify({ unexpected: "object" }), { status: 200 })
    )
    vi.stubGlobal("fetch", fetchMock)
    const apiGet = vi.spyOn(api, "get")
    const client = makeClient()
    const groups = scheduleGroupsQueryOptions(true, "en")
    const lessons = pageScheduleQueryOptions(groupId, true, "en")

    await expect(client.fetchQuery({ ...groups, retry: false })).resolves.toEqual([])
    await expect(client.fetchQuery({ ...lessons, retry: false })).resolves.toEqual([])

    expect(client.getQueryCache().find({ queryKey: groups.queryKey })?.meta?.persist).toBe(false)
    expect(client.getQueryCache().find({ queryKey: lessons.queryKey })?.meta?.persist).toBe(false)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    const routes = vi
      .mocked(fetch)
      .mock.calls.map(([input]) => new URL(String(input), window.location.origin).pathname)
    expect(routes).toEqual(["/api/v1/groups", `/api/v1/schedule/${groupId}`])
    expect(apiGet).not.toHaveBeenCalled()
  })
})
