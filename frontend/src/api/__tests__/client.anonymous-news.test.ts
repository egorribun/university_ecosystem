import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  fetchAnonymousGroupSchedule,
  fetchAnonymousNewsDetail,
  fetchAnonymousNewsInteractions,
  fetchAnonymousNewsPage,
  fetchAnonymousScheduleGroups,
} from "@/api/client"

const fetchMock = vi.fn<typeof fetch>()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal("fetch", fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("fetchAnonymousNewsPage", () => {
  it("uses the fixed same-origin news route without ambient credentials", async () => {
    const signal = new AbortController().signal
    fetchMock.mockResolvedValue(new Response("{}", { status: 200 }))

    await fetchAnonymousNewsPage({
      language: "tr-TR",
      limit: 7,
      cursor: "cursor/with spaces",
      signal,
    })

    const call = fetchMock.mock.calls[0]
    expect(call).toBeDefined()
    if (!call) throw new Error("fetch was not called")
    const [input, init] = call
    const url = input instanceof URL ? input : new URL(String(input), window.location.origin)

    expect(url.origin).toBe(window.location.origin)
    expect(url.pathname).toBe("/api/v1/news")
    expect(url.searchParams.get("limit")).toBe("7")
    expect(url.searchParams.get("cursor")).toBe("cursor/with spaces")
    expect(init).toMatchObject({
      method: "GET",
      mode: "same-origin",
      credentials: "omit",
      cache: "no-store",
      signal,
    })
    const headers = new Headers(init?.headers)
    expect(headers.get("Accept")).toBe("application/json")
    expect(headers.get("Accept-Language")).toBe("tr-TR")
    expect(headers.has("Cookie")).toBe(false)
    expect(headers.has("Authorization")).toBe(false)
  })
})

describe("anonymous public detail transports", () => {
  const id = "00000000-0000-0000-0000-000000000001"

  it("uses only fixed same-origin detail, interactions, and schedule routes without credentials", async () => {
    const signal = new AbortController().signal
    fetchMock.mockResolvedValue(new Response("{}", { status: 200 }))

    await fetchAnonymousNewsDetail({ id, language: "en", signal })
    await fetchAnonymousNewsInteractions({
      id,
      language: "en",
      limit: 20,
      offset: 40,
      signal,
    })
    await fetchAnonymousGroupSchedule({ groupId: id, language: "ru", signal })
    await fetchAnonymousScheduleGroups({ language: "en", signal })

    expect(fetchMock).toHaveBeenCalledTimes(4)
    const calls = fetchMock.mock.calls
    const detail = calls[0]
    const interactions = calls[1]
    const schedule = calls[2]
    const groups = calls[3]
    if (!detail || !interactions || !schedule || !groups) {
      throw new Error("anonymous fetch calls missing")
    }

    const detailUrl = new URL(String(detail[0]), window.location.origin)
    expect(detailUrl.origin).toBe(window.location.origin)
    expect(detailUrl.pathname).toBe(`/api/v1/news/${id}`)
    const interactionsUrl = new URL(String(interactions[0]), window.location.origin)
    expect(interactionsUrl.origin).toBe(window.location.origin)
    expect(interactionsUrl.pathname).toBe(`/api/v1/news/${id}/interactions`)
    expect(interactionsUrl.searchParams.get("limit")).toBe("20")
    expect(interactionsUrl.searchParams.get("offset")).toBe("40")
    const scheduleUrl = new URL(String(schedule[0]), window.location.origin)
    expect(scheduleUrl.origin).toBe(window.location.origin)
    expect(scheduleUrl.pathname).toBe(`/api/v1/schedule/${id}`)
    const groupsUrl = new URL(String(groups[0]), window.location.origin)
    expect(groupsUrl.origin).toBe(window.location.origin)
    expect(groupsUrl.pathname).toBe("/api/v1/groups")

    for (const [input, init] of calls) {
      const url = new URL(String(input), window.location.origin)
      expect(url.origin).toBe(window.location.origin)
      expect(init).toMatchObject({
        method: "GET",
        mode: "same-origin",
        credentials: "omit",
        cache: "no-store",
        signal,
      })
      const headers = new Headers(init?.headers)
      expect(headers.get("Accept")).toBe("application/json")
      expect(headers.has("Cookie")).toBe(false)
      expect(headers.has("Authorization")).toBe(false)
    }
    expect(new Headers(detail[1]?.headers).get("Accept-Language")).toBe("en")
    expect(new Headers(schedule[1]?.headers).get("Accept-Language")).toBe("ru")
    expect(new Headers(groups[1]?.headers).get("Accept-Language")).toBe("en")
  })

  it("rejects non-UUID resource IDs before dispatch", async () => {
    await expect(fetchAnonymousNewsDetail({ id: "../../users", language: "en" })).rejects.toThrow(
      "requires a UUID"
    )
    await expect(
      fetchAnonymousNewsInteractions({ id, language: "en", limit: 101, offset: 0 })
    ).rejects.toThrow("limit is invalid")
    await expect(
      fetchAnonymousGroupSchedule({ groupId: "group/other", language: "en" })
    ).rejects.toThrow("require a group UUID")
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
