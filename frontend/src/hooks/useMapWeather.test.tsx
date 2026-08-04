import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"

import { useMapWeather, type MapWeatherData } from "./useMapWeather"

/**
 * useMapWeather — TanStack Query wrapper over Open-Meteo with a
 * 30-minute localStorage cache. We pin the contract:
 *  - cache hit (fresh) returns synchronously without a network call;
 *  - cache miss → fetch + write back;
 *  - expired cache (> TTL) is evicted and re-fetched;
 *  - localStorage write failure (Safari private mode) is swallowed.
 */

const CACHE_KEY = "map.weather.cache"
const CACHE_TTL = 30 * 60 * 1000

const FIXTURE_API_RESPONSE = {
  current: {
    temperature_2m: 12.4,
    weather_code: 1,
    is_day: 1,
    apparent_temperature: 11,
    wind_speed_10m: 4.2,
    relative_humidity_2m: 71,
    uv_index: 3,
  },
  hourly: {
    time: ["2026-05-15T13:00", "2026-05-15T14:00", "2026-05-15T15:00"],
    temperature_2m: [12, 13, 14],
    weather_code: [1, 2, 3],
  },
}

const FIXTURE_CACHED_DATA: MapWeatherData = {
  temperature: 20,
  weatherCode: 0,
  isDay: true,
  condition: "clear",
  feelsLike: 19,
  windSpeed: 2.5,
  humidity: 50,
  uvIndex: 2,
  hourlyForecast: [],
}

let fetchMock: ReturnType<typeof vi.fn>

function newClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
    },
  })
}

function wrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }
}

beforeEach(() => {
  localStorage.clear()
  fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => FIXTURE_API_RESPONSE,
  } as Response)
  vi.stubGlobal("fetch", fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe("useMapWeather — cache hit", () => {
  it("returns cached data without a network call when cache is fresh", async () => {
    localStorage.setItem(
      CACHE_KEY,
      JSON.stringify({ timestamp: Date.now(), data: FIXTURE_CACHED_DATA })
    )

    const client = newClient()
    const { result } = renderHook(() => useMapWeather(), { wrapper: wrapper(client) })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(FIXTURE_CACHED_DATA)
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe("useMapWeather — cache miss → fetch", () => {
  it("hits the API and writes the result back to localStorage", async () => {
    const client = newClient()
    const { result } = renderHook(() => useMapWeather(), { wrapper: wrapper(client) })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(fetchMock).toHaveBeenCalledOnce()
    const data = result.current.data!
    expect(data.temperature).toBe(12) // rounded from 12.4
    expect(data.feelsLike).toBe(11)
    expect(data.windSpeed).toBe(4.2)
    expect(data.humidity).toBe(71)
    expect(data.uvIndex).toBe(3)
    expect(data.isDay).toBe(true)
    expect(data.hourlyForecast).toHaveLength(3)
    expect(data.hourlyForecast[0]?.temperature).toBe(12)

    // Persistence — next fresh hook would read from cache.
    const cached = JSON.parse(localStorage.getItem(CACHE_KEY) ?? "null")
    expect(cached?.data?.temperature).toBe(12)
  })
})

describe("useMapWeather — expired cache", () => {
  it("evicts the entry and re-fetches when older than TTL", async () => {
    const oldTimestamp = Date.now() - (CACHE_TTL + 60_000)
    localStorage.setItem(
      CACHE_KEY,
      JSON.stringify({ timestamp: oldTimestamp, data: FIXTURE_CACHED_DATA })
    )

    const client = newClient()
    const { result } = renderHook(() => useMapWeather(), { wrapper: wrapper(client) })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(fetchMock).toHaveBeenCalledOnce()
    // After re-fetch the cache key reflects the FRESH server data
    // (rounded 12) — not the stale 20 we pre-seeded.
    const cached = JSON.parse(localStorage.getItem(CACHE_KEY) ?? "null")
    expect(cached?.data?.temperature).toBe(12)
  })
})

describe("useMapWeather — corrupt cache", () => {
  it("treats invalid JSON as a cache miss and fetches fresh", async () => {
    localStorage.setItem(CACHE_KEY, "{not-valid-json")

    const client = newClient()
    const { result } = renderHook(() => useMapWeather(), { wrapper: wrapper(client) })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(fetchMock).toHaveBeenCalledOnce()
  })
})

describe("useMapWeather — apparent_temperature fallback", () => {
  it("falls back to temperature_2m when apparent_temperature is missing", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        ...FIXTURE_API_RESPONSE,
        current: {
          ...FIXTURE_API_RESPONSE.current,
          apparent_temperature: undefined,
        },
      }),
    } as Response)

    const client = newClient()
    const { result } = renderHook(() => useMapWeather(), { wrapper: wrapper(client) })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    // feelsLike falls back to round(temperature_2m=12.4) = 12.
    expect(result.current.data?.feelsLike).toBe(12)
  })
})

describe("useMapWeather — defensive API handling", () => {
  it("surfaces a non-OK API response as a query error", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 503,
    } as Response)

    const client = newClient()
    const { result } = renderHook(() => useMapWeather(), { wrapper: wrapper(client) })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error).toEqual(new Error("Weather API 503"))
  })

  it("uses safe defaults when optional current and hourly collections are absent", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        current: {
          temperature_2m: 5.6,
          weather_code: 99,
          is_day: 0,
          apparent_temperature: undefined,
          wind_speed_10m: undefined,
          relative_humidity_2m: undefined,
          uv_index: undefined,
        },
        hourly: {
          time: undefined,
          temperature_2m: undefined,
          weather_code: undefined,
        },
      }),
    } as Response)

    const client = newClient()
    const { result } = renderHook(() => useMapWeather(), { wrapper: wrapper(client) })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toMatchObject({
      temperature: 6,
      isDay: false,
      feelsLike: 6,
      windSpeed: 0,
      humidity: 0,
      uvIndex: 0,
      hourlyForecast: [],
    })
  })

  it("skips empty hourly timestamps and defaults missing point values", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        current: FIXTURE_API_RESPONSE.current,
        hourly: {
          time: ["", "2026-05-15T14:00"],
          temperature_2m: [],
          weather_code: [],
        },
      }),
    } as Response)

    const client = newClient()
    const { result } = renderHook(() => useMapWeather(), { wrapper: wrapper(client) })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.hourlyForecast).toEqual([
      { hour: 14, temperature: 0, condition: "clear" },
    ])
  })

  it("continues successfully when localStorage cannot persist the response", async () => {
    const setItemSpy = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(() => {
        throw new DOMException("Quota exceeded", "QuotaExceededError")
      })

    const client = newClient()
    const { result } = renderHook(() => useMapWeather(), { wrapper: wrapper(client) })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.temperature).toBe(12)
    expect(setItemSpy).toHaveBeenCalledOnce()
    setItemSpy.mockRestore()
  })
})
