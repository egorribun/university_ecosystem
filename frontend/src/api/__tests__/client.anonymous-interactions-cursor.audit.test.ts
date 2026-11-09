import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { fetchAnonymousNewsInteractions } from "@/api/client"

const id = "00000000-0000-0000-0000-000000000001"
const fetchMock = vi.fn<typeof fetch>()

// Exercise the runtime boundary with inputs that TypeScript callers cannot
// normally construct, without weakening the production parameter types.
const requestWithUntrustedPagination = (pagination: Record<string, unknown>) =>
  fetchAnonymousNewsInteractions({
    id,
    language: "ru",
    limit: 20,
    ...pagination,
  } as Parameters<typeof fetchAnonymousNewsInteractions>[0])

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal("fetch", fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("anonymous news interaction cursor transport", () => {
  it("round-trips an opaque cursor on the fixed credentialless route", async () => {
    const cursor = `opaque/${crypto.randomUUID()} +&?=🪐`
    const signal = new AbortController().signal
    fetchMock.mockResolvedValue(new Response("{}", { status: 200 }))

    await requestWithUntrustedPagination({ cursor, signal })

    expect(fetchMock).toHaveBeenCalledOnce()
    const [input, init] = fetchMock.mock.calls[0]!
    const url = new URL(String(input), window.location.origin)
    expect(url.origin).toBe(window.location.origin)
    expect(url.pathname).toBe(`/api/v1/news/${id}/interactions`)
    expect(url.searchParams.get("limit")).toBe("20")
    expect(url.searchParams.getAll("cursor")).toEqual([cursor])
    expect(url.searchParams.has("offset")).toBe(false)
    expect(init).toMatchObject({
      method: "GET",
      mode: "same-origin",
      credentials: "omit",
      cache: "no-store",
      signal,
    })
    const headers = new Headers(init?.headers)
    expect(headers.get("Accept-Language")).toBe("ru")
    expect(headers.has("Cookie")).toBe(false)
    expect(headers.has("Authorization")).toBe(false)
  })

  it("accepts a cursor at the 128-character boundary without rewriting it", async () => {
    const cursor = `${"x".repeat(127)}🪐`
    fetchMock.mockResolvedValue(new Response("{}", { status: 200 }))

    await requestWithUntrustedPagination({ cursor })

    expect(fetchMock).toHaveBeenCalledOnce()
    const [input] = fetchMock.mock.calls[0]!
    const url = new URL(String(input), window.location.origin)
    expect(url.searchParams.get("cursor")).toBe(cursor)
    expect(url.searchParams.has("offset")).toBe(false)
  })

  it("rejects missing, mixed, malformed, or oversized pagination before dispatch", async () => {
    fetchMock.mockResolvedValue(new Response("{}", { status: 200 }))
    const invalidInputs: Record<string, unknown>[] = [
      {},
      { cursor: "" },
      { cursor: "x".repeat(129) },
      { cursor: 42 },
      { cursor: String.fromCharCode(0xd800) },
      { cursor: "cursor", offset: 0 },
      { offset: -1 },
      { offset: 0.5 },
      { offset: null },
    ]

    for (const input of invalidInputs) {
      await expect(requestWithUntrustedPagination(input)).rejects.toThrow()
    }
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
