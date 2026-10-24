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
  vi.useRealTimers()
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
      signal: expect.any(AbortSignal),
    })
    expect(init?.signal).not.toBe(signal)
    expect(init?.signal?.aborted).toBe(false)
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
      fetchAnonymousNewsInteractions({
        id,
        language: "en",
        limit: 101,
        offset: 0,
      })
    ).rejects.toThrow("limit is invalid")
    await expect(
      fetchAnonymousGroupSchedule({ groupId: "group/other", language: "en" })
    ).rejects.toThrow("require a group UUID")
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe("anonymous News transport lifetime", () => {
  const rejectWhenAborted = (init: RequestInit | undefined): Promise<Response> => {
    const requestSignal = init?.signal
    if (!requestSignal) return Promise.reject(new Error("transport signal missing"))
    return new Promise<Response>((_resolve, reject) => {
      const rejectFromAbort = () => reject(requestSignal.reason)
      if (requestSignal.aborted) rejectFromAbort()
      else
        requestSignal.addEventListener("abort", rejectFromAbort, {
          once: true,
        })
    })
  }

  it("aborts a pending native fetch at its own eight-second deadline", async () => {
    vi.useFakeTimers()
    fetchMock.mockImplementation((_input, init) => rejectWhenAborted(init))
    const caller = new AbortController()
    const removeListener = vi.spyOn(caller.signal, "removeEventListener")
    const request = fetchAnonymousNewsPage({
      language: "en",
      limit: 12,
      signal: caller.signal,
    })
    const requestSignal = fetchMock.mock.calls[0]?.[1]?.signal
    expect(requestSignal).toBeInstanceOf(AbortSignal)
    expect(requestSignal).not.toBe(caller.signal)
    expect(vi.getTimerCount()).toBe(1)

    const rejection = expect(request).rejects.toMatchObject({
      name: "TimeoutError",
      message: "Anonymous news request timed out",
    })
    await vi.advanceTimersByTimeAsync(8_000)
    await rejection

    expect(requestSignal?.aborted).toBe(true)
    expect(requestSignal?.reason).toMatchObject({ name: "TimeoutError" })
    expect(caller.signal.aborted).toBe(false)
    expect(removeListener).toHaveBeenCalledWith("abort", expect.any(Function))
    expect(vi.getTimerCount()).toBe(0)
  })

  it("preserves caller cancellation and clears the deadline", async () => {
    vi.useFakeTimers()
    fetchMock.mockImplementation((_input, init) => rejectWhenAborted(init))
    const caller = new AbortController()
    const removeListener = vi.spyOn(caller.signal, "removeEventListener")
    const request = fetchAnonymousNewsPage({
      language: "en",
      limit: 12,
      signal: caller.signal,
    })
    const requestSignal = fetchMock.mock.calls[0]?.[1]?.signal
    const reason = new DOMException("Caller cancelled", "AbortError")
    const rejection = expect(request).rejects.toBe(reason)

    caller.abort(reason)
    await rejection

    expect(requestSignal?.aborted).toBe(true)
    expect(requestSignal?.reason).toBe(reason)
    expect(vi.getTimerCount()).toBe(0)
    expect(removeListener).toHaveBeenCalledWith("abort", expect.any(Function))

    const alreadyAbortedCaller = new AbortController()
    const alreadyAbortedReason = new DOMException("Already cancelled", "AbortError")
    alreadyAbortedCaller.abort(alreadyAbortedReason)
    const addListener = vi.spyOn(alreadyAbortedCaller.signal, "addEventListener")
    const alreadyAbortedRequest = fetchAnonymousNewsPage({
      language: "en",
      limit: 12,
      signal: alreadyAbortedCaller.signal,
    })
    const alreadyAbortedRequestSignal = fetchMock.mock.calls[1]?.[1]?.signal

    await expect(alreadyAbortedRequest).rejects.toBe(alreadyAbortedReason)
    expect(alreadyAbortedRequestSignal?.aborted).toBe(true)
    expect(alreadyAbortedRequestSignal?.reason).toBe(alreadyAbortedReason)
    expect(addListener).not.toHaveBeenCalled()
    expect(vi.getTimerCount()).toBe(0)
  })

  it("cleans up the timer and caller listener after success", async () => {
    vi.useFakeTimers()
    fetchMock.mockResolvedValue(new Response("{}", { status: 200 }))
    const caller = new AbortController()
    const removeListener = vi.spyOn(caller.signal, "removeEventListener")
    const request = fetchAnonymousNewsPage({
      language: "en",
      limit: 12,
      signal: caller.signal,
    })
    const requestSignal = fetchMock.mock.calls[0]?.[1]?.signal

    await expect(request).resolves.toEqual({ ok: true, status: 200, data: {} })
    expect(vi.getTimerCount()).toBe(0)
    expect(removeListener).toHaveBeenCalledWith("abort", expect.any(Function))
    await vi.advanceTimersByTimeAsync(8_000)
    expect(requestSignal?.aborted).toBe(false)
  })

  it("returns an HTTP status without consuming an unsuccessful body", async () => {
    vi.useFakeTimers()
    const response = new Response("{}", { status: 503 })
    const json = vi.spyOn(response, "json")
    fetchMock.mockResolvedValue(response)
    const caller = new AbortController()
    const removeListener = vi.spyOn(caller.signal, "removeEventListener")
    const request = fetchAnonymousNewsPage({
      language: "en",
      limit: 12,
      signal: caller.signal,
    })
    const requestSignal = fetchMock.mock.calls[0]?.[1]?.signal

    await expect(request).resolves.toEqual({ ok: false, status: 503 })
    expect(requestSignal?.aborted).toBe(true)
    expect(requestSignal?.reason).toMatchObject({ name: "AbortError" })
    expect(caller.signal.aborted).toBe(false)
    expect(json).not.toHaveBeenCalled()
    expect(vi.getTimerCount()).toBe(0)
    expect(removeListener).toHaveBeenCalledWith("abort", expect.any(Function))
  })

  it("keeps its deadline active while the response body is pending", async () => {
    vi.useFakeTimers()
    const response = new Response("{}", { status: 200 })
    const json = vi
      .spyOn(response, "json")
      .mockImplementation(() => new Promise<unknown>(() => undefined))
    fetchMock.mockResolvedValue(response)
    const caller = new AbortController()
    const removeListener = vi.spyOn(caller.signal, "removeEventListener")
    const request = fetchAnonymousNewsPage({
      language: "en",
      limit: 12,
      signal: caller.signal,
    })
    const requestSignal = fetchMock.mock.calls[0]?.[1]?.signal
    await vi.waitFor(() => expect(json).toHaveBeenCalledOnce())
    expect(vi.getTimerCount()).toBe(1)

    const rejection = expect(request).rejects.toMatchObject({
      name: "TimeoutError",
      message: "Anonymous news request timed out",
    })
    await vi.advanceTimersByTimeAsync(8_000)
    await rejection

    expect(requestSignal?.aborted).toBe(true)
    expect(requestSignal?.reason).toMatchObject({ name: "TimeoutError" })
    expect(caller.signal.aborted).toBe(false)
    expect(removeListener).toHaveBeenCalledWith("abort", expect.any(Function))
    expect(vi.getTimerCount()).toBe(0)
  })

  it("preserves caller cancellation while the response body is pending", async () => {
    vi.useFakeTimers()
    const response = new Response("{}", { status: 200 })
    const json = vi
      .spyOn(response, "json")
      .mockImplementation(() => new Promise<unknown>(() => undefined))
    fetchMock.mockResolvedValue(response)
    const caller = new AbortController()
    const removeListener = vi.spyOn(caller.signal, "removeEventListener")
    const request = fetchAnonymousNewsPage({
      language: "en",
      limit: 12,
      signal: caller.signal,
    })
    const requestSignal = fetchMock.mock.calls[0]?.[1]?.signal
    await vi.waitFor(() => expect(json).toHaveBeenCalledOnce())
    const reason = new DOMException("Caller cancelled body read", "AbortError")
    const rejection = expect(request).rejects.toBe(reason)

    caller.abort(reason)
    await rejection

    expect(requestSignal?.aborted).toBe(true)
    expect(requestSignal?.reason).toBe(reason)
    expect(vi.getTimerCount()).toBe(0)
    expect(removeListener).toHaveBeenCalledWith("abort", expect.any(Function))
  })

  it("cleans up the deadline and caller listener when body parsing fails", async () => {
    vi.useFakeTimers()
    const response = new Response("{}", { status: 200 })
    vi.spyOn(response, "json").mockRejectedValue(new SyntaxError("invalid JSON"))
    fetchMock.mockResolvedValue(response)
    const caller = new AbortController()
    const removeListener = vi.spyOn(caller.signal, "removeEventListener")

    await expect(
      fetchAnonymousNewsPage({
        language: "en",
        limit: 12,
        signal: caller.signal,
      })
    ).rejects.toThrow("invalid JSON")
    expect(vi.getTimerCount()).toBe(0)
    expect(removeListener).toHaveBeenCalledWith("abort", expect.any(Function))
  })

  it("cleans up the timer and caller listener after a network error", async () => {
    vi.useFakeTimers()
    fetchMock.mockRejectedValue(new TypeError("network unavailable"))
    const caller = new AbortController()
    const removeListener = vi.spyOn(caller.signal, "removeEventListener")
    const request = fetchAnonymousNewsPage({
      language: "en",
      limit: 12,
      signal: caller.signal,
    })

    await expect(request).rejects.toThrow("network unavailable")
    expect(vi.getTimerCount()).toBe(0)
    expect(removeListener).toHaveBeenCalledWith("abort", expect.any(Function))
  })

  it("cleans up when fetch throws synchronously", async () => {
    vi.useFakeTimers()
    fetchMock.mockImplementation(() => {
      throw new TypeError("synchronous fetch failure")
    })
    const caller = new AbortController()
    const removeListener = vi.spyOn(caller.signal, "removeEventListener")

    await expect(
      fetchAnonymousNewsPage({
        language: "en",
        limit: 12,
        signal: caller.signal,
      })
    ).rejects.toThrow("synchronous fetch failure")
    expect(vi.getTimerCount()).toBe(0)
    expect(removeListener).toHaveBeenCalledWith("abort", expect.any(Function))
  })
})
