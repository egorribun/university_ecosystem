import { QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor, act } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"
import { renderToString } from "react-dom/server"
import { createQueryClient } from "@/app/queryClient"
import api, { SKIP_UNAUTHORIZED_HEADER } from "@/api/client"
import {
  fetchNowPlaying,
  useNowPlaying,
  __testing as nowPlayingTesting,
} from "@/hooks/useNowPlaying"
import type { NowPlaying } from "@/types/spotify"

const STORAGE_KEY = "spotify:now-playing:last"

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
  vi.useRealTimers()
  nowPlayingTesting.clearRateLimit()
})

beforeEach(() => {
  vi.useRealTimers()
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    get: () => "visible",
  })
})

describe("fetchNowPlaying", () => {
  it("normalizes a playing track", async () => {
    vi.spyOn(api, "get").mockResolvedValue({
      status: 200,
      data: {
        is_playing: true,
        track_id: " 42 ",
        track_name: "Nightcall",
        artists: ["Kavinsky", " "],
        album_name: "Drive",
        album_image_url: "/media/cover.jpg",
        track_url: "https://open.spotify.com/track/42",
        duration_ms: 180000,
        progress_ms: 45000,
      },
    } as any)

    vi.useFakeTimers()
    vi.setSystemTime(new Date("2024-01-01T00:00:00Z"))

    try {
      const result = await fetchNowPlaying()

      expect(result).toMatchObject({
        is_playing: true,
        track_id: "42",
        track_name: "Nightcall",
        artists: ["Kavinsky"],
        album_name: "Drive",
        album_image_url: "/media/cover.jpg",
        track_url: "https://open.spotify.com/track/42",
        duration_ms: 180000,
        progress_ms: 45000,
      })
      expect(typeof result?.fetched_at).toBe("string")
    } finally {
      vi.useRealTimers()
    }
  })

  it("returns null for 204 responses", async () => {
    vi.spyOn(api, "get").mockResolvedValue({ status: 204, data: null } as any)
    const result = await fetchNowPlaying()
    expect(result).toBeNull()
  })

  it("passes the unauthorized-skip header and validates accepted statuses", async () => {
    let requestConfig: any
    vi.spyOn(api, "get").mockImplementation(async (_url, config) => {
      requestConfig = config
      return { status: 200, data: { track_name: "Valid" } } as any
    })

    await fetchNowPlaying()

    expect(requestConfig.headers[SKIP_UNAUTHORIZED_HEADER]).toBe("1")
    expect(requestConfig.validateStatus(204)).toBe(true)
    expect(requestConfig.validateStatus(200)).toBe(true)
    expect(requestConfig.validateStatus(299)).toBe(true)
    expect(requestConfig.validateStatus(199)).toBe(false)
    expect(requestConfig.validateStatus(300)).toBe(false)
  })

  it("normalizes malformed optional fields and empty payloads safely", async () => {
    vi.spyOn(api, "get")
      .mockResolvedValueOnce({
        status: 200,
        data: {
          track_name: " Edge ",
          artists: "not-an-array",
          duration_ms: -50,
          progress_ms: "not-a-number",
          fetched_at: "",
        },
      } as any)
      .mockResolvedValueOnce({ status: 200, data: { artists: [] } } as any)
      .mockResolvedValueOnce({ status: 200, data: null } as any)

    await expect(fetchNowPlaying()).resolves.toMatchObject({
      track_name: "Edge",
      artists: [],
      duration_ms: 0,
      progress_ms: null,
      fetched_at: "",
    })
    await expect(fetchNowPlaying()).resolves.toBeNull()
    await expect(fetchNowPlaying()).resolves.toBeNull()
  })

  it("records rate limit window on 429 errors", async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2024-01-01T00:00:00Z"))

    const error = Object.assign(new Error("Too Many Requests"), {
      isAxiosError: true,
      response: {
        status: 429,
        headers: { "retry-after": "3" },
      },
    })

    vi.spyOn(api, "get").mockRejectedValue(error)

    await expect(fetchNowPlaying()).rejects.toThrow("Too Many Requests")
    const limit = nowPlayingTesting.getRateLimitedUntil()
    expect(limit).toBeGreaterThan(Date.now())
    expect(limit).toBe(Date.now() + 3_250)
  })

  it("uses array and invalid retry-after headers with the safe fallback", async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2024-01-01T00:00:00Z"))
    const get = vi.spyOn(api, "get")
    const first = Object.assign(new Error("array limit"), {
      isAxiosError: true,
      response: { status: 429, headers: { "retry-after": ["2", "3"] } },
    })
    const second = Object.assign(new Error("fallback limit"), {
      isAxiosError: true,
      response: { status: 429, headers: {} },
    })
    get.mockRejectedValueOnce(first).mockRejectedValueOnce(second)

    await expect(fetchNowPlaying()).rejects.toThrow("array limit")
    expect(nowPlayingTesting.getRateLimitedUntil()).toBe(Date.now() + 2_250)
    await expect(fetchNowPlaying()).rejects.toThrow("fallback limit")
    expect(nowPlayingTesting.getRateLimitedUntil()).toBe(Date.now() + 5_250)
  })

  it("dispatches reauth for 401 and rethrows non-Axios failures", async () => {
    const reauth = vi.fn()
    window.addEventListener("spotify:reauth-required", reauth)
    const get = vi.spyOn(api, "get")
    const unauthorized = Object.assign(new Error("expired"), {
      isAxiosError: true,
      response: { status: 401, headers: {} },
    })
    get.mockRejectedValueOnce(unauthorized).mockRejectedValueOnce(new Error("offline"))

    await expect(fetchNowPlaying()).resolves.toBeNull()
    expect(reauth).toHaveBeenCalledOnce()
    await expect(fetchNowPlaying()).rejects.toThrow("offline")
    window.removeEventListener("spotify:reauth-required", reauth)
  })
})

describe("useNowPlaying", () => {
  const wrapper = ({ children }: { children: ReactNode }) => {
    const client = createQueryClient()
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }

  function SsrProbe({ enabled }: { enabled: boolean }) {
    useNowPlaying(enabled)
    return <span data-testid="now-playing-probe" />
  }

  it("exposes paused track data and stores it in cache", async () => {
    const payload: Partial<NowPlaying> = {
      is_playing: false,
      track_id: "xyz",
      track_name: "Lo-fi Study",
      artists: ["Various"],
      album_name: "Lo-fi",
      album_image_url: "https://cdn.example/lofi.jpg",
      track_url: "https://open.spotify.com/track/xyz",
      duration_ms: 210000,
      progress_ms: 120000,
    }

    vi.spyOn(api, "get").mockResolvedValue({ status: 200, data: payload } as any)

    const { result } = renderHook(() => useNowPlaying(true), { wrapper })

    await waitFor(() =>
      expect(result.current.data).toMatchObject({
        is_playing: false,
        track_id: "xyz",
        track_name: "Lo-fi Study",
        artists: ["Various"],
        duration_ms: 210000,
        progress_ms: 120000,
      })
    )

    const stored = localStorage.getItem(STORAGE_KEY)
    expect(stored).toBeTruthy()
  })

  it("falls back to cached value before network resolves", async () => {
    const cached: NowPlaying = {
      is_playing: true,
      track_id: "cached",
      track_name: "Cached Song",
      artists: ["Cache"],
      album_name: null,
      album_image_url: null,
      track_url: null,
      duration_ms: 100000,
      progress_ms: 50000,
      fetched_at: "2024-01-01T00:00:00.000Z",
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(cached))

    vi.spyOn(api, "get").mockImplementation(
      () =>
        new Promise((resolve) => {
          setTimeout(() => {
            resolve({ status: 204, data: null } as any)
          }, 50)
        })
    )

    const { result } = renderHook(() => useNowPlaying(true), { wrapper })

    expect(result.current.data).toMatchObject({ track_id: "cached", track_name: "Cached Song" })

    await act(async () => {
      await result.current.refetch()
    })

    await waitFor(() => expect(result.current.data).toBeNull())
  })

  it("ignores malformed cache and tolerates persistence failures", async () => {
    localStorage.setItem(STORAGE_KEY, "{")
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("storage unavailable")
    })
    vi.spyOn(api, "get").mockResolvedValue({
      status: 200,
      data: { track_id: "fresh", track_name: "Fresh" },
    } as any)

    const { result } = renderHook(() => useNowPlaying(true), { wrapper })
    await waitFor(() => expect(result.current.data?.track_id).toBe("fresh"))
    expect(setItem).toHaveBeenCalled()
  })

  it("refetches when the document becomes visible and stays quiet while hidden", async () => {
    const get = vi.spyOn(api, "get").mockResolvedValue({
      status: 200,
      data: { track_id: "visible", track_name: "Visible" },
    } as any)
    const { result } = renderHook(() => useNowPlaying(true), { wrapper })
    await waitFor(() => expect(result.current.data?.track_id).toBe("visible"))
    expect(get).toHaveBeenCalledOnce()

    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => "hidden",
    })
    document.dispatchEvent(new Event("visibilitychange"))
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(get).toHaveBeenCalledOnce()

    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => "visible",
    })
    document.dispatchEvent(new Event("visibilitychange"))
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2))
  })

  it("does not attach a visibility listener when disabled", () => {
    const addEventListener = vi.spyOn(document, "addEventListener")
    renderHook(() => useNowPlaying(false), { wrapper })

    expect(
      addEventListener.mock.calls.some(([eventName]) => eventName === "visibilitychange")
    ).toBe(false)
  })

  it("reads the cache safely during SSR without a browser window", () => {
    const browserWindow = window
    vi.stubGlobal("window", undefined)
    try {
      const html = renderToString(
        <QueryClientProvider client={createQueryClient()}>
          <SsrProbe enabled={false} />
        </QueryClientProvider>
      )
      expect(html).toContain("now-playing-probe")
    } finally {
      vi.stubGlobal("window", browserWindow)
    }
  })

  it("keeps SSR persistence safe and resolves placeholder branches explicitly", () => {
    const browserWindow = window
    const browserDocument = document
    vi.stubGlobal("window", undefined)
    vi.stubGlobal("document", undefined)
    try {
      expect(nowPlayingTesting.persistNowPlaying(null)).toBeUndefined()
      expect(
        nowPlayingTesting.computeRefetchInterval({
          enabled: true,
          data: null,
          isTestEnvironment: false,
        })
      ).toBe(3_000)

      const cached = { track_id: "cached" } as NowPlaying
      const previous = { track_id: "previous" } as NowPlaying
      expect(nowPlayingTesting.resolvePlaceholderData(previous, cached)).toBe(previous)
      expect(nowPlayingTesting.resolvePlaceholderData(null, cached)).toBeNull()
      expect(nowPlayingTesting.resolvePlaceholderData(undefined, cached)).toBe(cached)
    } finally {
      vi.stubGlobal("window", browserWindow)
      vi.stubGlobal("document", browserDocument)
    }
  })

  it("does not retry rate-limited query responses", async () => {
    const get = vi.spyOn(api, "get").mockRejectedValue(
      Object.assign(new Error("Too Many Requests"), {
        isAxiosError: true,
        response: { status: 429, headers: {} },
      })
    )

    const { result } = renderHook(() => useNowPlaying(true), { wrapper })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(get).toHaveBeenCalledOnce()
  })

  it("retries one time for non-rate-limited query failures", async () => {
    const get = vi.spyOn(api, "get").mockRejectedValue(new Error("offline"))

    const { result } = renderHook(() => useNowPlaying(true), { wrapper })

    await waitFor(() => expect(result.current.isError).toBe(true), { timeout: 5_000 })
    expect(get).toHaveBeenCalledTimes(2)
  })

  it("computes idle, paused, active, hidden, and rate-limited polling intervals", () => {
    expect(nowPlayingTesting.computeInterval(null)).toBe(3_000)
    expect(nowPlayingTesting.computeInterval({ is_playing: false } as NowPlaying)).toBe(2_000)
    expect(nowPlayingTesting.computeInterval({ is_playing: true } as NowPlaying)).toBe(500)

    expect(
      nowPlayingTesting.computeRefetchInterval({
        enabled: false,
        data: null,
        isTestEnvironment: false,
        visibilityState: "visible",
      })
    ).toBe(false)
    expect(
      nowPlayingTesting.computeRefetchInterval({
        enabled: true,
        data: null,
        isTestEnvironment: true,
        visibilityState: "visible",
      })
    ).toBe(false)
    expect(
      nowPlayingTesting.computeRefetchInterval({
        enabled: true,
        data: null,
        isTestEnvironment: false,
        visibilityState: "hidden",
      })
    ).toBe(false)
    expect(
      nowPlayingTesting.computeRefetchInterval({
        enabled: true,
        data: null,
        isTestEnvironment: false,
        visibilityState: "visible",
      })
    ).toBe(3_000)
    expect(
      nowPlayingTesting.computeRefetchInterval({
        enabled: true,
        data: null,
        isTestEnvironment: false,
      })
    ).toBe(3_000)

    vi.useFakeTimers()
    vi.setSystemTime(new Date("2024-01-01T00:00:00Z"))
    nowPlayingTesting.scheduleRateLimit(5_000)
    expect(
      nowPlayingTesting.computeRefetchInterval({
        enabled: true,
        data: { is_playing: true } as NowPlaying,
        isTestEnvironment: false,
        visibilityState: "visible",
      })
    ).toBe(5_000)
  })
})
