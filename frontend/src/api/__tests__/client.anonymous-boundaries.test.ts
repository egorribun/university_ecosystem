import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  fetchAnonymousGroupSchedule,
  fetchAnonymousNewsDetail,
  fetchAnonymousNewsInteractions,
  fetchAnonymousNewsPage,
  fetchAnonymousScheduleGroups,
} from "@/api/client"

const id = "00000000-0000-0000-0000-000000000001"
const fetchMock = vi.fn<typeof fetch>()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal("fetch", fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("anonymous transport input and server boundaries", () => {
  it("rejects malformed interaction IDs and pagination offsets before dispatch", async () => {
    await expect(
      fetchAnonymousNewsInteractions({ id: "../users", language: "en", limit: 20, offset: 0 })
    ).rejects.toThrow("require a UUID")
    await expect(
      fetchAnonymousNewsInteractions({ id, language: "en", limit: 20, offset: -1 })
    ).rejects.toThrow("offset is invalid")
    await expect(
      fetchAnonymousNewsInteractions({ id, language: "en", limit: 20, offset: 0.5 })
    ).rejects.toThrow("offset is invalid")
    await expect(
      fetchAnonymousNewsInteractions({ id, language: "en", limit: 0, offset: 0 })
    ).rejects.toThrow("limit is invalid")

    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("refuses every public transport when no browser origin exists", async () => {
    vi.stubGlobal("window", undefined)

    const requests = [
      fetchAnonymousNewsPage({ language: "en", limit: 12 }),
      fetchAnonymousNewsDetail({ id, language: "en" }),
      fetchAnonymousNewsInteractions({ id, language: "en", limit: 20, offset: 0 }),
      fetchAnonymousGroupSchedule({ groupId: id, language: "en" }),
      fetchAnonymousScheduleGroups({ language: "en" }),
    ]

    for (const request of requests) {
      await expect(request).rejects.toThrow("browser origin")
    }
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
