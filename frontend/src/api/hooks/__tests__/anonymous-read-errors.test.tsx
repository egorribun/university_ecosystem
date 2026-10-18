import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, renderHook, waitFor } from "@testing-library/react"
import type { PropsWithChildren } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { anonymousNewsListQueryKey, useNewsListQuery } from "@/api/hooks/news"
import { pageScheduleQueryOptions, scheduleGroupsQueryOptions } from "@/api/hooks/schedule"
import { useAuthStore } from "@/stores/useAuthStore"

const groupId = "00000000-0000-0000-0000-000000000002"
const fetchMock = vi.fn<typeof fetch>()

const makeClient = () =>
  new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } })

const wrapperFor = (client: QueryClient) => {
  function QueryClientWrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }

  return QueryClientWrapper
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal("fetch", fetchMock)
  window.localStorage.clear()
  useAuthStore.setState({ user: null, loading: false })
})

afterEach(() => {
  cleanup()
  useAuthStore.setState({ user: null, loading: true })
  window.localStorage.clear()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("anonymous reads fail closed on HTTP errors", () => {
  it("does not turn an error response body into a news-list result", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          items: [{ id: "private-error-payload", title: "Must not render" }],
          total: 1,
          limit: 12,
          cursor: null,
          next_cursor: null,
          has_more: false,
        }),
        { status: 503 }
      )
    )
    const client = makeClient()
    const { result } = renderHook(() => useNewsListQuery({ language: "en" }, { retry: false }), {
      wrapper: wrapperFor(client),
    })

    await waitFor(() => expect(result.current.isError).toBe(true))

    const key = anonymousNewsListQueryKey({ language: "en" })
    expect(result.current.news).toEqual([])
    expect(client.getQueryData(key)).toBeUndefined()
    expect(client.getQueryCache().find({ queryKey: key })?.meta?.persist).toBe(false)
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it("keeps failed public schedule and groups responses out of query data", async () => {
    fetchMock.mockImplementation(async () => new Response(JSON.stringify([]), { status: 503 }))
    const client = makeClient()
    const groups = scheduleGroupsQueryOptions(true, "en")
    const schedule = pageScheduleQueryOptions(groupId, true, "en")

    await expect(client.fetchQuery({ ...groups, retry: false })).rejects.toThrow(
      "Schedule groups request failed with status 503"
    )
    await expect(client.fetchQuery({ ...schedule, retry: false })).rejects.toThrow(
      "Schedule request failed with status 503"
    )

    expect(client.getQueryState(groups.queryKey)?.status).toBe("error")
    expect(client.getQueryState(schedule.queryKey)?.status).toBe("error")
    expect(client.getQueryData(groups.queryKey)).toBeUndefined()
    expect(client.getQueryData(schedule.queryKey)).toBeUndefined()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
