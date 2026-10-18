import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { fetchAnonymousNewsItem } from "@/api/news"

const id = "00000000-0000-0000-0000-000000000001"
const fetchMock = vi.fn<typeof fetch>()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal("fetch", fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("anonymous news detail response contract", () => {
  it("preserves the HTTP status failure and does not parse an error body", async () => {
    const json = vi.fn()
    fetchMock.mockResolvedValue({ ok: false, status: 503, json } as unknown as Response)

    await expect(fetchAnonymousNewsItem(id, { language: "en" })).rejects.toThrow(
      "News request failed with status 503"
    )

    expect(json).not.toHaveBeenCalled()
  })

  it("rejects malformed public detail data instead of exposing it as a NewsItem", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          id,
          title: 42,
          content: "Public body",
          created_at: "2026-10-18T00:00:00Z",
          image_url_optimized: null,
        }),
        { status: 200 }
      )
    )

    await expect(fetchAnonymousNewsItem(id, { language: "en" })).rejects.toThrow(
      "Invalid API response for GET /api/v1/news/{id}"
    )
    expect(fetchMock).toHaveBeenCalledOnce()
  })
})
