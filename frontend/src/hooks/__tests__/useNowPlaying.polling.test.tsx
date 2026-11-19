import { onlineManager, QueryClientProvider, type QueryClient } from "@tanstack/react-query"
import { act, cleanup, renderHook } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import type { UserState } from "@/types/Auth"

/**
 * Polling is disabled in the test build, so these checks load the hook as the
 * production build does.
 */

const clients = new Set<QueryClient>()

beforeEach(() => {
  vi.resetModules()
  vi.stubEnv("MODE", "production")
  vi.useFakeTimers()
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    get: () => "visible",
  })
})

afterEach(() => {
  cleanup()
  clients.forEach((client) => client.clear())
  clients.clear()
  onlineManager.setOnline(true)
  vi.useRealTimers()
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
  localStorage.clear()
})

async function pollingSession(track: Record<string, unknown> | null) {
  const { default: api } = await import("@/api/client")
  const { createQueryClient } = await import("@/app/queryClient")
  const { useNowPlaying } = await import("@/hooks/useNowPlaying")
  const { useAuthStore } = await import("@/stores/useAuthStore")
  const { acceptBrowserSessionGeneration } = await import("@/stores/sessionEpoch")
  acceptBrowserSessionGeneration()
  useAuthStore.setState({ user: { id: "spotify-polling-user" } as UserState, loading: false })
  const get = vi
    .spyOn(api, "get")
    .mockResolvedValue(
      (track === null ? { status: 204, data: "" } : { status: 200, data: track }) as never
    )
  const client = createQueryClient()
  clients.add(client)
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  const hook = renderHook(() => useNowPlaying(true), { wrapper })
  await act(() => vi.advanceTimersByTimeAsync(0))
  return { ...hook, get }
}

it("polls every half second while a track is playing", async () => {
  const { get, unmount } = await pollingSession({ track_id: "live", is_playing: true })
  expect(get).toHaveBeenCalledTimes(1)

  await act(() => vi.advanceTimersByTimeAsync(500))

  expect(get).toHaveBeenCalledTimes(2)
  unmount()
})

it("polls every three seconds while nothing is playing", async () => {
  const { get, unmount } = await pollingSession(null)

  await act(() => vi.advanceTimersByTimeAsync(2_999))
  expect(get).toHaveBeenCalledTimes(1)
  await act(() => vi.advanceTimersByTimeAsync(1))

  expect(get).toHaveBeenCalledTimes(2)
  unmount()
})

it("pauses the first Spotify request while offline and resumes it on reconnect", async () => {
  onlineManager.setOnline(false)
  const { get, result, unmount } = await pollingSession(null)

  try {
    expect(get).not.toHaveBeenCalled()
    expect(result.current.fetchStatus).toBe("paused")

    act(() => onlineManager.setOnline(true))
    await act(() => vi.advanceTimersByTimeAsync(0))

    expect(get).toHaveBeenCalledTimes(1)
    expect(result.current.fetchStatus).toBe("idle")
  } finally {
    unmount()
  }
})

it("pauses a visibility-triggered Spotify refetch while offline", async () => {
  const { get, result, unmount } = await pollingSession({ track_id: "cached", is_playing: true })

  try {
    expect(get).toHaveBeenCalledTimes(1)
    // Read the status before the transition so Query's tracked-property subscription observes it.
    expect(result.current.fetchStatus).toBe("idle")
    act(() => {
      onlineManager.setOnline(false)
      document.dispatchEvent(new Event("visibilitychange"))
    })
    await act(() => vi.advanceTimersByTimeAsync(1))

    expect(get).toHaveBeenCalledTimes(1)
    expect(result.current.fetchStatus).toBe("paused")
    expect(result.current.data?.track_id).toBe("cached")

    act(() => onlineManager.setOnline(true))
    await act(() => vi.advanceTimersByTimeAsync(0))

    expect(get).toHaveBeenCalledTimes(2)
  } finally {
    unmount()
  }
})

it("preserves Retry-After when the document becomes visible during Spotify backoff", async () => {
  const { get, result, unmount } = await pollingSession({ track_id: "cached", is_playing: true })
  const { __testing } = await import("@/hooks/useNowPlaying")

  try {
    get.mockRejectedValueOnce(
      Object.assign(new Error("rate limited"), {
        isAxiosError: true,
        response: { status: 429, headers: { "retry-after": "10" } },
      })
    )
    await act(async () => {
      await result.current.refetch()
    })
    expect(get).toHaveBeenCalledTimes(2)
    const deadline = __testing.getRateLimitedUntil()
    expect(deadline).toBeGreaterThan(Date.now())

    act(() => document.dispatchEvent(new Event("visibilitychange")))
    await act(() => vi.advanceTimersByTimeAsync(0))

    expect(get).toHaveBeenCalledTimes(2)
    expect(__testing.getRateLimitedUntil()).toBe(deadline)

    await act(() => vi.advanceTimersByTimeAsync(deadline - Date.now() - 1))
    expect(get).toHaveBeenCalledTimes(2)
    await act(() => vi.advanceTimersByTimeAsync(1))
    expect(get).toHaveBeenCalledTimes(3)
  } finally {
    unmount()
  }
})

it("resumes polling after Spotify backoff when the 429 arrived while hidden", async () => {
  let visibility: DocumentVisibilityState = "visible"
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    get: () => visibility,
  })
  const { get, result, unmount } = await pollingSession({ track_id: "cached", is_playing: true })
  const { __testing } = await import("@/hooks/useNowPlaying")

  try {
    visibility = "hidden"
    act(() => document.dispatchEvent(new Event("visibilitychange")))
    get.mockRejectedValueOnce(
      Object.assign(new Error("rate limited"), {
        isAxiosError: true,
        response: { status: 429, headers: { "retry-after": "10" } },
      })
    )
    await act(async () => {
      await result.current.refetch()
    })
    expect(get).toHaveBeenCalledTimes(2)
    const deadline = __testing.getRateLimitedUntil()

    visibility = "visible"
    act(() => document.dispatchEvent(new Event("visibilitychange")))
    await act(() => vi.advanceTimersByTimeAsync(deadline - Date.now() - 1))
    expect(get).toHaveBeenCalledTimes(2)
    await act(() => vi.advanceTimersByTimeAsync(1))
    expect(get).toHaveBeenCalledTimes(3)

    // Polling continues on its normal interval after the resumed request.
    await act(() => vi.advanceTimersByTimeAsync(500))
    expect(get).toHaveBeenCalledTimes(4)
  } finally {
    unmount()
  }
})

it("drops a pending backoff resume when the document hides again", async () => {
  let visibility: DocumentVisibilityState = "hidden"
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    get: () => visibility,
  })
  const { get, result, unmount } = await pollingSession({ track_id: "cached", is_playing: true })
  const { __testing } = await import("@/hooks/useNowPlaying")

  try {
    get.mockRejectedValueOnce(
      Object.assign(new Error("rate limited"), {
        isAxiosError: true,
        response: { status: 429, headers: { "retry-after": "10" } },
      })
    )
    await act(async () => {
      await result.current.refetch()
    })
    const calls = get.mock.calls.length
    const deadline = __testing.getRateLimitedUntil()

    visibility = "visible"
    act(() => document.dispatchEvent(new Event("visibilitychange")))
    visibility = "hidden"
    act(() => document.dispatchEvent(new Event("visibilitychange")))
    await act(() => vi.advanceTimersByTimeAsync(deadline - Date.now() + 1_000))

    expect(get).toHaveBeenCalledTimes(calls)
  } finally {
    unmount()
  }
})
