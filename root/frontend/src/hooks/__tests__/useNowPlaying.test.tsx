import { QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor, act } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"
import { createQueryClient } from "@/app/queryClient"
import api from "@/api/client"
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
})

describe("useNowPlaying", () => {
  const wrapper = ({ children }: { children: ReactNode }) => {
    const client = createQueryClient()
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
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
})
