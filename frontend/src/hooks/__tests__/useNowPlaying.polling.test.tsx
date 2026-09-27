import { onlineManager, QueryClientProvider, type QueryClient } from "@tanstack/react-query"
import { act, cleanup, renderHook } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"

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
