import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, renderHook, waitFor } from "@testing-library/react"
import type { PropsWithChildren } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import api from "@/api/client"
import { acceptBrowserSessionGeneration, invalidateSessionEpoch } from "@/stores/sessionEpoch"
import { useAuthStore } from "@/stores/useAuthStore"
import type { UserState } from "@/types/Auth"
import i18n from "@/i18n/config"
import { useDashboardSchedule, type DashboardLesson } from "../useDashboardSchedule"

const groupId = "00000000-0000-0000-0000-000000000001"
const generationStorageKey = "ecosystem.session.generation.v1"
const accountKey = ["dashboard", "schedule", "student", groupId] as const
const anonymousKey = ["dashboard", "anonymous-schedule", groupId] as const
const accountLesson = { id: "private-account-lesson", subject: "Account A" } as DashboardLesson
const publicLesson = {
  id: "public-lesson",
  subject: "Public schedule",
  teacher: "Ada Lovelace",
  room: "A-101",
  lesson_type: "lecture",
  weekday: "monday",
  start_time: "09:00",
  end_time: "10:30",
  parity: "both",
} satisfies DashboardLesson

const makeClient = () =>
  new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } })
const wrapperFor = (client: QueryClient) => {
  function QueryClientWrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }

  return QueryClientWrapper
}
const publishGeneration = (nonce: string, hash: string | null) => {
  const newValue = JSON.stringify({ nonce, hash })
  window.localStorage.setItem(generationStorageKey, newValue)
  window.dispatchEvent(
    new StorageEvent("storage", {
      key: generationStorageKey,
      newValue,
      storageArea: window.localStorage,
    })
  )
}

beforeEach(() => {
  window.localStorage.clear()
  window.localStorage.setItem(
    generationStorageKey,
    JSON.stringify({ nonce: "generation-a", hash: "hash-a" })
  )
  window.document.cookie = "session_cookie=; Max-Age=0; path=/"
  acceptBrowserSessionGeneration()
  invalidateSessionEpoch()
  useAuthStore.setState({ user: { id: "account-a" } as UserState, loading: false })
})

afterEach(() => {
  cleanup()
  useAuthStore.setState({ user: null, loading: true })
  window.localStorage.clear()
  window.document.cookie = "session_cookie=; Max-Age=0; path=/"
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("anonymous Dashboard schedule", () => {
  it("uses a credentialless public key during logout-inflight and never exposes account A schedule data", async () => {
    const client = makeClient()
    client.setQueryData(accountKey, [accountLesson])
    window.document.cookie = "session_cookie=successor-account-b; path=/"
    publishGeneration("generation-b", "hash-b")

    let resolveFetch: ((response: Response) => void) | undefined
    const fetchMock = vi.fn<typeof fetch>(
      () =>
        new Promise<Response>((resolve) => {
          resolveFetch = resolve
        })
    )
    vi.stubGlobal("fetch", fetchMock)
    const apiGet = vi.spyOn(api, "get").mockResolvedValue({ data: [accountLesson] } as never)

    const { result } = renderHook(() => useDashboardSchedule("student", groupId), {
      wrapper: wrapperFor(client),
    })

    expect(result.current.data).toEqual([])
    expect(client.getQueryData(accountKey)).toEqual([accountLesson])
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(apiGet).not.toHaveBeenCalled()

    const call = fetchMock.mock.calls[0]
    expect(call).toBeDefined()
    if (!call) throw new Error("anonymous Dashboard schedule request missing")
    expect(String(call[0])).toBe(`${window.location.origin}/api/v1/schedule/${groupId}`)
    expect(call[1]).toMatchObject({
      credentials: "omit",
      mode: "same-origin",
      cache: "no-store",
    })
    expect(new Headers(call[1]?.headers).get("Accept-Language")).toBe(i18n.language)
    expect(new Headers(call[1]?.headers).has("Cookie")).toBe(false)
    expect(new Headers(call[1]?.headers).has("Authorization")).toBe(false)

    const release = resolveFetch
    if (!release) throw new Error("anonymous Dashboard schedule fetch was not pending")
    await act(async () => {
      release(new Response(JSON.stringify([publicLesson]), { status: 200 }))
    })
    await waitFor(() => expect(result.current.data).toEqual([publicLesson]))

    expect(client.getQueryData(accountKey)).toEqual([accountLesson])
    expect(client.getQueryData(anonymousKey)).toEqual([publicLesson])
    expect(client.getQueryCache().find({ queryKey: anonymousKey })?.meta?.persist).toBe(false)
    expect(apiGet).not.toHaveBeenCalled()
  })

  it("does not dispatch a public request for a legacy numeric group ID", async () => {
    publishGeneration("generation-b", "hash-b")
    const client = makeClient()
    const fetchMock = vi.fn<typeof fetch>()
    vi.stubGlobal("fetch", fetchMock)
    const apiGet = vi.spyOn(api, "get")

    renderHook(() => useDashboardSchedule("student", 42), { wrapper: wrapperFor(client) })

    const anonymousKey = ["dashboard", "anonymous-schedule", 42] as const
    await waitFor(() => expect(client.getQueryState(anonymousKey)?.status).toBe("success"))
    expect(client.getQueryData(anonymousKey)).toEqual([])
    expect(fetchMock).not.toHaveBeenCalled()
    expect(apiGet).not.toHaveBeenCalled()
  })

  it("surfaces an unavailable public schedule without falling back to account data", async () => {
    publishGeneration("generation-b", "hash-b")
    const client = makeClient()
    client.setQueryData(accountKey, [accountLesson])
    const fetchMock = vi.fn<typeof fetch>(async () => new Response("unavailable", { status: 503 }))
    vi.stubGlobal("fetch", fetchMock)
    const apiGet = vi.spyOn(api, "get")

    renderHook(() => useDashboardSchedule("student", groupId), { wrapper: wrapperFor(client) })

    await waitFor(() =>
      expect(client.getQueryState(anonymousKey)?.error).toMatchObject({
        message: "Schedule request failed with status 503",
      })
    )
    expect(client.getQueryData(accountKey)).toEqual([accountLesson])
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(apiGet).not.toHaveBeenCalled()
  })
})
