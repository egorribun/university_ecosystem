import { afterEach, describe, expect, it, vi } from "vitest"

import { fetchCampusTimezone } from "@/api/hooks/campusConfig"

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("fetchCampusTimezone", () => {
  it("reads and validates the one public campus setting", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ campus_timezone: "Europe/Istanbul" }),
    })
    vi.stubGlobal("fetch", fetchMock)

    await expect(fetchCampusTimezone()).resolves.toBe("Europe/Istanbul")
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/campus/config",
      expect.objectContaining({ cache: "no-store", headers: { Accept: "application/json" } })
    )
  })

  it("rejects extra fields and invalid IANA values instead of inventing a zone", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ campus_timezone: "Europe/Istanbul", secret: "must not be accepted" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ campus_timezone: "Not/A_Timezone" }),
      })
    vi.stubGlobal("fetch", fetchMock)

    await expect(fetchCampusTimezone()).resolves.toBeNull()
    await expect(fetchCampusTimezone()).resolves.toBeNull()
  })

  it("aborts at the standard API deadline and stays unavailable on timeout", async () => {
    const timeoutController = new AbortController()
    const timeoutSignal = vi.spyOn(AbortSignal, "timeout").mockReturnValue(timeoutController.signal)
    const fetchMock = vi.fn((_url: RequestInfo | URL, init?: RequestInit) => {
      const signal = init?.signal
      if (!signal) return Promise.reject(new Error("request signal missing"))

      return new Promise<Response>((_resolve, reject) => {
        signal.addEventListener("abort", () => reject(signal.reason), { once: true })
      })
    })
    vi.stubGlobal("fetch", fetchMock)

    const pending = fetchCampusTimezone()

    expect(timeoutSignal).toHaveBeenCalledWith(8_000)
    expect(fetchMock.mock.calls[0]?.[1]?.signal).toBe(timeoutController.signal)
    timeoutController.abort()
    await expect(pending).resolves.toBeNull()
  })
})
