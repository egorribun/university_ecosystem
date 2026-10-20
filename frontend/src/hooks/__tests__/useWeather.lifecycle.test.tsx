import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, renderHook, waitFor } from "@testing-library/react"
import type { PropsWithChildren } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { weatherQueryKey } from "@/api/hooks/weather"
import { WeatherFetchError, type WeatherSnapshot } from "@/api/weather"
import { CAMPUS_COORDINATES } from "@/constants/campus"
import { useWeather } from "../useWeather"

const CACHED_WEATHER: WeatherSnapshot = {
  conditionCode: 3,
  conditionLabel: "Overcast",
  temperatureC: 12,
  observedAt: "2026-10-20T09:00:00.000Z",
}

const FRESH_WEATHER: WeatherSnapshot = {
  conditionCode: 1,
  conditionLabel: "Mainly clear",
  temperatureC: 18,
  observedAt: "2026-10-20T10:00:00.000Z",
}

const makeQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        gcTime: 30 * 60_000,
        retry: false,
      },
    },
  })

const makeWrapper = (queryClient: QueryClient) => {
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return Wrapper
}

const makeWeatherResponse = (snapshot: WeatherSnapshot) =>
  new Response(
    JSON.stringify({
      current: {
        weather_code: snapshot.conditionCode,
        temperature_2m: snapshot.temperatureC,
        time: snapshot.observedAt,
      },
    }),
    { status: 200, headers: { "content-type": "application/json" } }
  )

const sessionCacheKey = (): string => {
  const [, , latitude, longitude] = weatherQueryKey(CAMPUS_COORDINATES)
  return `weather:snapshot:${latitude},${longitude}`
}

describe("useWeather lifecycle against a real QueryClient", () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = makeQueryClient()
    window.sessionStorage.clear()
  })

  afterEach(async () => {
    cleanup()
    await queryClient.cancelQueries()
    queryClient.clear()
    vi.useRealTimers()
    vi.unstubAllGlobals()
    window.sessionStorage.clear()
  })

  it("keeps fresh cached weather on mount, then refetches after a stale remount", async () => {
    vi.useFakeTimers({ toFake: ["Date"] })
    const firstUpdatedAt = new Date("2026-10-20T10:00:00.000Z").getTime()
    const cacheTtlMs = 1_000
    vi.setSystemTime(firstUpdatedAt)
    queryClient.setQueryData(weatherQueryKey(CAMPUS_COORDINATES), CACHED_WEATHER, {
      updatedAt: firstUpdatedAt,
    })

    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(makeWeatherResponse(FRESH_WEATHER))
    vi.stubGlobal("fetch", fetchMock)

    const firstMount = renderHook(() => useWeather({ cacheTtlMs }), {
      wrapper: makeWrapper(queryClient),
    })
    expect(firstMount.result.current.data?.temperatureC).toBe(CACHED_WEATHER.temperatureC)
    expect(fetchMock).not.toHaveBeenCalled()
    firstMount.unmount()

    vi.setSystemTime(firstUpdatedAt + cacheTtlMs + 1)
    const remount = renderHook(() => useWeather({ cacheTtlMs }), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    await waitFor(() =>
      expect(remount.result.current.data?.temperatureC).toBe(FRESH_WEATHER.temperatureC)
    )
    expect(queryClient.getQueryData(weatherQueryKey(CAMPUS_COORDINATES))).toMatchObject({
      temperatureC: FRESH_WEATHER.temperatureC,
    })
  })

  it.each([
    ["numeric", 7],
    ["unavailable", null],
  ] as const)(
    "retains the expired session fallback after HTTP failure without caching it as fresh data (%s temperature)",
    async (_label, temperatureC) => {
      const staleFallback = {
        ...CACHED_WEATHER,
        temperatureC,
        observedAt: "2026-10-20T08:00:00.000Z",
      }
      const cachedEntry = JSON.stringify({ data: staleFallback, expiresAt: Date.now() - 1_000 })
      window.sessionStorage.setItem(sessionCacheKey(), cachedEntry)

      const fetchMock = vi
        .fn<typeof fetch>()
        .mockResolvedValue(new Response("unavailable", { status: 503 }))
      vi.stubGlobal("fetch", fetchMock)

      const { result } = renderHook(() => useWeather(), { wrapper: makeWrapper(queryClient) })

      await waitFor(() => expect(result.current.error).toBeInstanceOf(WeatherFetchError))

      expect(result.current.data).toMatchObject({
        conditionCode: staleFallback.conditionCode,
        conditionLabel: staleFallback.conditionLabel,
        temperatureC,
        observedAt: staleFallback.observedAt,
      })
      expect(result.current.isLoading).toBe(false)
      expect(queryClient.getQueryState(weatherQueryKey(CAMPUS_COORDINATES))?.status).toBe("error")
      expect(queryClient.getQueryData(weatherQueryKey(CAMPUS_COORDINATES))).toBeUndefined()
      expect(fetchMock).toHaveBeenCalledTimes(2)
      expect(fetchMock.mock.calls[0]?.[0]).toContain("https://api.open-meteo.com/v1/forecast")
      expect(fetchMock.mock.calls[0]?.[1]?.signal).toBeInstanceOf(AbortSignal)
      expect(window.sessionStorage.getItem(sessionCacheKey())).toBe(cachedEntry)
    }
  )

  it("deduplicates a pending request for concurrent observers", async () => {
    let resolveResponse: ((response: Response) => void) | undefined
    const pendingResponse = new Promise<Response>((resolve) => {
      resolveResponse = resolve
    })
    const fetchMock = vi.fn<typeof fetch>().mockReturnValue(pendingResponse)
    vi.stubGlobal("fetch", fetchMock)

    const wrapper = makeWrapper(queryClient)
    const first = renderHook(() => useWeather(), { wrapper })
    const second = renderHook(() => useWeather(), { wrapper })

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect(fetchMock.mock.calls[0]?.[1]?.signal).toBeInstanceOf(AbortSignal)

    await act(async () => {
      resolveResponse?.(makeWeatherResponse(FRESH_WEATHER))
      await pendingResponse
    })
    await waitFor(() =>
      expect(first.result.current.data?.temperatureC).toBe(FRESH_WEATHER.temperatureC)
    )
    expect(second.result.current.data?.temperatureC).toBe(FRESH_WEATHER.temperatureC)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it("aborts the provider request when the final observer unmounts", async () => {
    const fetchMock = vi.fn<typeof fetch>(
      (_input, init) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener(
            "abort",
            () => reject(new DOMException("request cancelled", "AbortError")),
            { once: true }
          )
        })
    )
    vi.stubGlobal("fetch", fetchMock)

    const { unmount } = renderHook(() => useWeather(), { wrapper: makeWrapper(queryClient) })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const signal = fetchMock.mock.calls[0]?.[1]?.signal
    expect(signal).toBeInstanceOf(AbortSignal)

    unmount()
    await waitFor(() => expect(signal?.aborted).toBe(true))
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
