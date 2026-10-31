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

const LEGACY_CACHE_KEY = "map.weather.cache"
const CACHE_KEY = "map.weather.cache.v2"
const CACHE_VERSION = 2
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

function serializedCache(
  data: MapWeatherData,
  timestamp = Date.now(),
  windSpeedUnit = "ms"
): string {
  return JSON.stringify({ version: CACHE_VERSION, windSpeedUnit, timestamp, data })
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
  vi.unstubAllEnvs()
  localStorage.clear()
})

describe("useMapWeather — Lighthouse preview", () => {
  it("uses deterministic local data without cache or network side effects", async () => {
    vi.stubEnv("VITE_LHCI", "true")
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem")

    const client = newClient()
    const { result } = renderHook(() => useMapWeather(), { wrapper: wrapper(client) })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toMatchObject({
      temperature: 20,
      weatherCode: 2,
      condition: "cloudy",
      hourlyForecast: [
        { hour: 12, temperature: 20, condition: "cloudy" },
        { hour: 13, temperature: 21, condition: "clear" },
      ],
    })
    expect(fetchMock).not.toHaveBeenCalled()
    expect(setItemSpy).not.toHaveBeenCalled()
    setItemSpy.mockRestore()
  })
})

describe("useMapWeather — unit-aware cache migration", () => {
  it("evicts the legacy km/h payload without touching unrelated local data", async () => {
    const unrelatedKey = "profile.preferences"
    const unrelatedValue = JSON.stringify({ theme: "dark" })
    localStorage.setItem(
      LEGACY_CACHE_KEY,
      JSON.stringify({
        timestamp: Date.now(),
        data: { ...FIXTURE_CACHED_DATA, windSpeed: 36 },
      })
    )
    localStorage.setItem(unrelatedKey, unrelatedValue)

    const client = newClient()
    const { result } = renderHook(() => useMapWeather(), { wrapper: wrapper(client) })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(result.current.data?.windSpeed).toBe(4.2)
    expect(localStorage.getItem(LEGACY_CACHE_KEY)).toBeNull()
    expect(localStorage.getItem(unrelatedKey)).toBe(unrelatedValue)
    expect(JSON.parse(localStorage.getItem(CACHE_KEY) ?? "null")).toMatchObject({
      version: CACHE_VERSION,
      windSpeedUnit: "ms",
      data: { windSpeed: 4.2 },
    })
  })

  it("rejects and replaces a versioned entry that declares km/h", async () => {
    localStorage.setItem(CACHE_KEY, serializedCache(FIXTURE_CACHED_DATA, Date.now(), "kmh"))

    const client = newClient()
    const { result } = renderHook(() => useMapWeather(), { wrapper: wrapper(client) })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(result.current.data?.windSpeed).toBe(4.2)
    expect(JSON.parse(localStorage.getItem(CACHE_KEY) ?? "null")).toMatchObject({
      version: CACHE_VERSION,
      windSpeedUnit: "ms",
      data: { windSpeed: 4.2 },
    })
  })
})

describe("useMapWeather — cache hit", () => {
  it("returns cached data without a network call when cache is fresh", async () => {
    localStorage.setItem(CACHE_KEY, serializedCache(FIXTURE_CACHED_DATA))

    const client = newClient()
    const { result } = renderHook(() => useMapWeather(), { wrapper: wrapper(client) })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(FIXTURE_CACHED_DATA)
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe("useMapWeather — persisted freshness", () => {
  it("keeps the original storage timestamp when seeding the Query cache", async () => {
    const now = new Date("2026-10-20T12:00:00.000Z")
    const timestamp = now.getTime() - CACHE_TTL + 1_000
    let currentTime = now.getTime()
    const dateNowSpy = vi.spyOn(Date, "now").mockImplementation(() => currentTime)

    try {
      localStorage.setItem(CACHE_KEY, serializedCache(FIXTURE_CACHED_DATA, timestamp))

      const firstMount = renderHook(() => useMapWeather(), { wrapper: wrapper(newClient()) })
      await waitFor(() => expect(firstMount.result.current.isSuccess).toBe(true))
      expect(firstMount.result.current.data).toEqual(FIXTURE_CACHED_DATA)
      expect(firstMount.result.current.dataUpdatedAt).toBe(timestamp)
      expect(firstMount.result.current.isStale).toBe(false)
      expect(fetchMock).not.toHaveBeenCalled()
      firstMount.unmount()

      currentTime = now.getTime() + 1_001
      const remount = renderHook(() => useMapWeather(), { wrapper: wrapper(newClient()) })
      await waitFor(() => expect(remount.result.current.isSuccess).toBe(true))

      expect(fetchMock).toHaveBeenCalledOnce()
      expect(remount.result.current.data?.temperature).toBe(12)
      expect(JSON.parse(localStorage.getItem(CACHE_KEY) ?? "null").timestamp).toBe(Date.now())
      remount.unmount()
    } finally {
      dateNowSpy.mockRestore()
    }
  })

  it("rejects a future-dated cache entry instead of extending its freshness", async () => {
    const futureTimestamp = Date.now() + 60_000
    localStorage.setItem(CACHE_KEY, serializedCache(FIXTURE_CACHED_DATA, futureTimestamp))

    const client = newClient()
    const { result } = renderHook(() => useMapWeather(), { wrapper: wrapper(client) })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(fetchMock).toHaveBeenCalledOnce()
    expect(result.current.data?.temperature).toBe(12)
    expect(JSON.parse(localStorage.getItem(CACHE_KEY) ?? "null").timestamp).not.toBe(
      futureTimestamp
    )
  })

  it("rejects a cache entry with a non-numeric timestamp", async () => {
    localStorage.setItem(
      CACHE_KEY,
      JSON.stringify({
        version: CACHE_VERSION,
        windSpeedUnit: "ms",
        timestamp: "not-a-timestamp",
        data: FIXTURE_CACHED_DATA,
      })
    )

    const client = newClient()
    const { result } = renderHook(() => useMapWeather(), { wrapper: wrapper(client) })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(fetchMock).toHaveBeenCalledOnce()
    expect(result.current.data?.temperature).toBe(12)
  })
})

describe("useMapWeather — provider wall-clock forecast hours", () => {
  it("preserves a valid hour that falls inside the client's DST spring gap", async () => {
    const previousTimezone = process.env.TZ

    try {
      process.env.TZ = "America/New_York"
      expect(new Date("2026-03-08T02:00").getHours()).toBe(3)

      fetchMock.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          ...FIXTURE_API_RESPONSE,
          hourly: {
            time: ["2026-03-08T01:00", "2026-03-08T02:00", "2026-03-08T03:00"],
            temperature_2m: [1, 2, 3],
            weather_code: [0, 1, 2],
          },
        }),
      } as Response)

      const client = newClient()
      const { result } = renderHook(() => useMapWeather(), { wrapper: wrapper(client) })

      await waitFor(() => expect(result.current.isSuccess).toBe(true))
      expect(result.current.data?.hourlyForecast.map((point) => point.hour)).toEqual([1, 2, 3])
    } finally {
      if (previousTimezone === undefined) delete process.env.TZ
      else process.env.TZ = previousTimezone
    }
  })

  it("skips malformed provider wall times without normalizing them through Date", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        ...FIXTURE_API_RESPONSE,
        hourly: {
          time: ["2026-05-15T24:00", "2026-02-30T12:00", "2026-05-15T12:00Z", "2026-05-15T12:00"],
          temperature_2m: [1, 2, 3, 4],
          weather_code: [0, 1, 2, 3],
        },
      }),
    } as Response)

    const client = newClient()
    const { result } = renderHook(() => useMapWeather(), { wrapper: wrapper(client) })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.hourlyForecast).toEqual([
      { hour: 12, temperature: 4, condition: "cloudy" },
    ])
  })

  it("skips non-string and structurally malformed provider timestamps", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        ...FIXTURE_API_RESPONSE,
        hourly: {
          time: [
            null,
            "2026-05-15T12",
            "2026-05T12:00",
            "2026-05-15T12:00:00:00",
            "2026-05-15T14:00",
          ],
          temperature_2m: [1, 2, 3, 4, 14],
          weather_code: [0, 0, 0, 0, 0],
        },
      }),
    } as Response)

    const client = newClient()
    const { result } = renderHook(() => useMapWeather(), { wrapper: wrapper(client) })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.hourlyForecast).toEqual([
      { hour: 14, temperature: 14, condition: "clear" },
    ])
  })

  it("validates leap days using Gregorian century rules", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        ...FIXTURE_API_RESPONSE,
        hourly: {
          time: ["2024-02-29T23:00", "2000-02-29T01:00", "1900-02-29T12:00", "2026-02-28T10:00"],
          temperature_2m: [23, 1, 12, 10],
          weather_code: [0, 0, 0, 0],
        },
      }),
    } as Response)

    const client = newClient()
    const { result } = renderHook(() => useMapWeather(), { wrapper: wrapper(client) })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.hourlyForecast).toEqual([
      { hour: 23, temperature: 23, condition: "clear" },
      { hour: 1, temperature: 1, condition: "clear" },
      { hour: 10, temperature: 10, condition: "clear" },
    ])
  })
})

describe("useMapWeather — cache miss → fetch", () => {
  it("hits the API and writes the result back to localStorage", async () => {
    const client = newClient()
    const { result } = renderHook(() => useMapWeather(), { wrapper: wrapper(client) })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(fetchMock).toHaveBeenCalledOnce()
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("&wind_speed_unit=ms"))
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
    expect(cached).toMatchObject({ version: CACHE_VERSION, windSpeedUnit: "ms" })
  })
})

describe("useMapWeather — expired cache", () => {
  it("evicts the entry and re-fetches when older than TTL", async () => {
    const oldTimestamp = Date.now() - (CACHE_TTL + 60_000)
    localStorage.setItem(CACHE_KEY, serializedCache(FIXTURE_CACHED_DATA, oldTimestamp))

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
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
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

describe("useMapWeather — provider wall-clock seconds", () => {
  it("accepts valid second precision and skips malformed second fields", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        current: FIXTURE_API_RESPONSE.current,
        hourly: {
          time: [
            "2026-05-15T13:45:12.5",
            "2026-05-15T14:45:12",
            "2026-05-15T15:45:12.a",
            "2026-05-15T16:45:12.5.1",
          ],
          temperature_2m: [15, 16, 17, 18],
          weather_code: [1, 2, 3, 4],
        },
      }),
    } as Response)

    const client = newClient()
    const { result } = renderHook(() => useMapWeather(), { wrapper: wrapper(client) })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.hourlyForecast).toEqual([
      { hour: 13, temperature: 15, condition: "clear" },
      { hour: 14, temperature: 16, condition: "cloudy" },
    ])
  })
})
