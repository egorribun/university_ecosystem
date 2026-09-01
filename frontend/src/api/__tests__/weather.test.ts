import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"

import {
  fetchWeatherSnapshot,
  readWeatherCache,
  WEATHER_CACHE_TTL_MS,
  WeatherFetchError,
  type WeatherSnapshot,
} from "../weather"

const COORDS = { lat: 55.0, lon: 37.0 }
const KEY = "weather:snapshot:55.0000,37.0000"

const SNAP: WeatherSnapshot = {
  conditionCode: 0,
  conditionLabel: "Clear sky",
  temperatureC: 5,
  observedAt: "2026-01-01T00:00:00.000Z",
}

it("keeps the canonical weather cache contract constants stable", () => {
  expect(WEATHER_CACHE_TTL_MS).toBe(600_000)
})

const okResponse = (body: unknown) => ({
  ok: true,
  status: 200,
  json: async () => body,
})

beforeEach(() => {
  window.sessionStorage.clear()
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  window.sessionStorage.clear()
})

describe("fetchWeatherSnapshot", () => {
  it("returns no cache during SSR and tolerates an unavailable session store", async () => {
    vi.stubGlobal("window", undefined)
    expect(readWeatherCache({ lat: 0, lon: 0 })).toBeNull()
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        okResponse({
          current: { weather_code: 0, temperature_2m: 5, time: "2026-06-05T10:00:00Z" },
        })
      )
    )

    await expect(fetchWeatherSnapshot({ coordinates: COORDS })).resolves.toMatchObject({
      conditionCode: 0,
      temperatureC: 5,
    })
  })

  it("handles whitespace timestamps and a missing sessionStorage object", async () => {
    const sessionStorage = vi
      .spyOn(window, "sessionStorage", "get")
      .mockReturnValue(undefined as unknown as Storage)
    expect(readWeatherCache(COORDS)).toBeNull()
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        okResponse({
          current: { weather_code: 1, temperature_2m: 6, time: "   " },
        })
      )
    )

    const result = await fetchWeatherSnapshot({ coordinates: COORDS })
    expect(result.conditionCode).toBe(1)
    expect(Number.isNaN(Date.parse(result.observedAt))).toBe(false)
    expect(sessionStorage).toHaveBeenCalled()
  })

  it("fetches without touching browser storage during SSR", async () => {
    vi.stubGlobal("window", undefined)
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        okResponse({
          current: { weather_code: 0, temperature_2m: 5, time: "2026-06-05T10:00:00Z" },
        })
      )
    )

    await expect(fetchWeatherSnapshot({ coordinates: COORDS })).resolves.toMatchObject({
      conditionCode: 0,
      temperatureC: 5,
    })
  })

  it("returns the cached snapshot without fetching when fresh", async () => {
    window.sessionStorage.setItem(
      KEY,
      JSON.stringify({ data: SNAP, expiresAt: Date.now() + 60_000 })
    )
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)

    const result = await fetchWeatherSnapshot({ coordinates: COORDS })
    expect(result).toEqual(SNAP)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("fetches, normalizes, and caches when there is no fresh entry", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      okResponse({
        current: { weather_code: 0, temperature_2m: 5, time: "2026-06-05T10:00:00Z" },
      })
    )
    vi.stubGlobal("fetch", fetchMock)

    const result = await fetchWeatherSnapshot({ coordinates: { lat: 10, lon: 20 } })
    expect(result.conditionCode).toBe(0)
    expect(result.conditionLabel).toBe("Clear sky")
    expect(result.temperatureC).toBe(5)
    expect(fetchMock).toHaveBeenCalledOnce()

    const cached = readWeatherCache({ lat: 10, lon: 20 }, { allowExpired: true })
    expect(cached?.data.conditionCode).toBe(0)
  })

  it("builds the canonical provider request and enforces the cache lifetime floor", async () => {
    vi.useFakeTimers()
    try {
      const now = new Date("2026-06-05T10:00:00.000Z")
      vi.setSystemTime(now)
      const fetchMock = vi.fn().mockResolvedValue(
        okResponse({
          current: { weather_code: 2, temperature_2m: 7, time: now.toISOString() },
        })
      )
      vi.stubGlobal("fetch", fetchMock)

      await fetchWeatherSnapshot({
        coordinates: { lat: 1.234567, lon: -2.345678 },
        cacheTtlMs: 120_000,
      })

      const [requestUrl, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit]
      const parsed = new URL(requestUrl)
      expect(parsed.origin + parsed.pathname).toBe("https://api.open-meteo.com/v1/forecast")
      expect(Object.fromEntries(parsed.searchParams)).toEqual({
        latitude: "1.23457",
        longitude: "-2.34568",
        current: "temperature_2m,weather_code",
        timeformat: "iso8601",
        forecast_days: "1",
        timezone: "auto",
      })
      expect(requestInit.signal).toBeInstanceOf(AbortSignal)
      expect(
        readWeatherCache({ lat: 1.234567, lon: -2.345678 }, { allowExpired: true })
      ).toMatchObject({ expiresAt: now.getTime() + 120_000 })

      await fetchWeatherSnapshot({
        coordinates: { lat: 1.234567, lon: -2.345678 },
        cacheTtlMs: 1_000,
        forceRefresh: true,
      })
      expect(
        readWeatherCache({ lat: 1.234567, lon: -2.345678 }, { allowExpired: true })
      ).toMatchObject({ expiresAt: now.getTime() + 30_000 })
    } finally {
      vi.useRealTimers()
    }
  })

  it("understands the legacy current_weather block shape", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      okResponse({
        current_weather: { weathercode: 95, temperature: -3, time: "2026-06-05T10:00:00Z" },
      })
    )
    vi.stubGlobal("fetch", fetchMock)

    const result = await fetchWeatherSnapshot({ coordinates: { lat: 1, lon: 2 } })
    expect(result.conditionCode).toBe(95)
    expect(result.conditionLabel).toBe("Thunderstorm")
    expect(result.temperatureC).toBe(-3)
  })

  it("prefers the modern current block when both provider shapes are present", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      okResponse({
        current: { weather_code: 1, temperature_2m: 11, time: "2026-06-05T10:00:00Z" },
        current_weather: { weathercode: 95, temperature: -3, time: "2026-06-05T11:00:00Z" },
      })
    )
    vi.stubGlobal("fetch", fetchMock)

    const result = await fetchWeatherSnapshot({ coordinates: { lat: 1, lon: 2 } })

    expect(result.conditionCode).toBe(1)
    expect(result.temperatureC).toBe(11)
    expect(result.observedAt).toBe("2026-06-05T10:00:00.000Z")
  })

  it("uses legacy field names when the modern current block fields are absent", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      okResponse({
        current: { weathercode: 3, temperature: 2, time: "2026-06-05T10:00:00Z" },
      })
    )
    vi.stubGlobal("fetch", fetchMock)

    const result = await fetchWeatherSnapshot({ coordinates: { lat: 11, lon: 12 } })

    expect(result.conditionCode).toBe(3)
    expect(result.temperatureC).toBe(2)
  })

  it("normalizes non-numeric codes and temperatures to defensive fallbacks", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        okResponse({
          current: { weather_code: "unknown", temperature_2m: "unknown", time: "invalid" },
        })
      )
    )

    const result = await fetchWeatherSnapshot({ coordinates: { lat: 19, lon: 20 } })

    expect(result.conditionCode).toBe(-1)
    expect(result.temperatureC).toBeNull()
    expect(Number.isNaN(Date.parse(result.observedAt))).toBe(false)
  })

  it("preserves valid timestamps and rejects non-string timestamp values", async () => {
    const fixedNow = new Date("2026-06-05T11:00:00.000Z")
    vi.useFakeTimers()
    vi.setSystemTime(fixedNow)
    try {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
          okResponse({
            current: { weather_code: 1, temperature_2m: 6, time: "2026-06-05T10:00:00Z" },
          })
        )
      )
      await expect(
        fetchWeatherSnapshot({ coordinates: { lat: 19, lon: 20 } })
      ).resolves.toMatchObject({ observedAt: "2026-06-05T10:00:00.000Z" })

      vi.stubGlobal(
        "fetch",
        vi
          .fn()
          .mockResolvedValue(
            okResponse({ current: { weather_code: 1, temperature_2m: 6, time: 0 } })
          )
      )
      await expect(
        fetchWeatherSnapshot({ coordinates: { lat: 19, lon: 21 } })
      ).resolves.toMatchObject({ observedAt: fixedNow.toISOString() })
    } finally {
      vi.useRealTimers()
    }
  })

  it("normalizes null current values and a missing current block", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          okResponse({ current: { weather_code: null, temperature_2m: null, time: null } })
        )
    )

    const result = await fetchWeatherSnapshot({ coordinates: { lat: 23, lon: 24 } })
    expect(result.conditionCode).toBe(-1)
    expect(result.temperatureC).toBeNull()

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        okResponse({
          current: null,
          current_weather: { weathercode: 2, temperature: 4, time: "2026-06-05T10:00:00Z" },
        })
      )
    )
    await expect(
      fetchWeatherSnapshot({ coordinates: { lat: 25, lon: 26 } })
    ).resolves.toMatchObject({
      conditionCode: 2,
      temperatureC: 4,
    })
  })

  it("throws WeatherFetchError when the payload has no current block", async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse({ unexpected: true }))
    vi.stubGlobal("fetch", fetchMock)

    await expect(fetchWeatherSnapshot({ coordinates: { lat: 3, lon: 4 } })).rejects.toMatchObject({
      name: "WeatherFetchError",
      message: "Failed to fetch weather",
      cause: expect.objectContaining({ message: "Missing current weather data" }),
    })
  })

  it("rejects primitive weather payloads", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okResponse(null)))

    await expect(fetchWeatherSnapshot({ coordinates: { lat: 4, lon: 5 } })).rejects.toMatchObject({
      name: "WeatherFetchError",
      cause: expect.objectContaining({ message: "Missing current weather data" }),
    })

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okResponse("invalid")))
    await expect(fetchWeatherSnapshot({ coordinates: { lat: 40, lon: 41 } })).rejects.toMatchObject(
      {
        name: "WeatherFetchError",
        cause: expect.objectContaining({ message: "Missing current weather data" }),
      }
    )
  })

  it("rejects primitive current and legacy blocks instead of normalizing them", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okResponse({ current: "invalid" })))
    await expect(fetchWeatherSnapshot({ coordinates: { lat: 6, lon: 7 } })).rejects.toMatchObject({
      name: "WeatherFetchError",
      cause: expect.objectContaining({ message: "Missing current weather data" }),
    })

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okResponse({ current_weather: "invalid" })))
    await expect(fetchWeatherSnapshot({ coordinates: { lat: 8, lon: 9 } })).rejects.toMatchObject({
      name: "WeatherFetchError",
      cause: expect.objectContaining({ message: "Missing current weather data" }),
    })

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okResponse({ current_weather: null })))
    await expect(fetchWeatherSnapshot({ coordinates: { lat: 10, lon: 11 } })).rejects.toMatchObject(
      {
        name: "WeatherFetchError",
        cause: expect.objectContaining({ message: "Missing current weather data" }),
      }
    )
  })

  it("does not trust a payload that hides its weather blocks from membership checks", async () => {
    const hiddenPayload = new Proxy(
      {},
      {
        get(target, property, receiver) {
          if (property === "current") {
            return { weather_code: 1, temperature_2m: 6, time: "2026-06-05T10:00:00Z" }
          }
          return Reflect.get(target, property, receiver)
        },
        has: () => false,
      }
    )
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okResponse(hiddenPayload)))

    await expect(fetchWeatherSnapshot({ coordinates: { lat: 12, lon: 13 } })).rejects.toMatchObject(
      {
        name: "WeatherFetchError",
        cause: expect.objectContaining({ message: "Missing current weather data" }),
      }
    )
  })

  it("uses campus coordinates when no fetch options are supplied", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      okResponse({
        current: { weather_code: 1, temperature_2m: 7, time: "2026-06-05T10:00:00Z" },
      })
    )
    vi.stubGlobal("fetch", fetchMock)

    await fetchWeatherSnapshot()
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("latitude="), expect.anything())
  })

  it("throws WeatherFetchError on a non-ok response", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({}) })
    vi.stubGlobal("fetch", fetchMock)

    await expect(fetchWeatherSnapshot({ coordinates: { lat: 5, lon: 6 } })).rejects.toMatchObject({
      name: "WeatherFetchError",
      cause: expect.objectContaining({ message: "Weather request failed with status 503" }),
    })
  })

  it("attaches the stale cache as a fallback when the fetch fails", async () => {
    window.sessionStorage.setItem(
      "weather:snapshot:7.0000,8.0000",
      JSON.stringify({ data: SNAP, expiresAt: Date.now() - 1000 }) // expired → triggers fetch
    )
    const fetchMock = vi.fn().mockRejectedValue(new Error("network down"))
    vi.stubGlobal("fetch", fetchMock)

    let caught: unknown
    try {
      await fetchWeatherSnapshot({ coordinates: { lat: 7, lon: 8 } })
    } catch (error) {
      caught = error
    }
    expect(caught).toBeInstanceOf(WeatherFetchError)
    expect((caught as WeatherFetchError).fallback).toEqual(SNAP)
  })

  it("reports an internally aborted request distinctly", async () => {
    class AlreadyAbortedController {
      signal = { aborted: true } as AbortSignal
      abort() {}
    }
    vi.stubGlobal("AbortController", AlreadyAbortedController as unknown as typeof AbortController)
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("aborted by browser")))

    const caught = await fetchWeatherSnapshot({ coordinates: { lat: 13, lon: 14 } }).catch(
      (error: unknown) => error
    )

    expect(caught).toBeInstanceOf(WeatherFetchError)
    expect((caught as WeatherFetchError).aborted).toBe(true)
    expect((caught as WeatherFetchError).message).toBe("Weather request aborted")
    expect((caught as WeatherFetchError).fallback).toBeNull()
  })

  it("preserves a stale cached snapshot for an internally aborted request", async () => {
    class AlreadyAbortedController {
      signal = { aborted: true } as AbortSignal
      abort() {}
    }
    const staleKey = "weather:snapshot:17.0000,18.0000"
    window.sessionStorage.setItem(
      staleKey,
      JSON.stringify({ data: SNAP, expiresAt: Date.now() - 1000 })
    )
    vi.stubGlobal("AbortController", AlreadyAbortedController as unknown as typeof AbortController)
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("aborted by browser")))

    const caught = await fetchWeatherSnapshot({ coordinates: { lat: 17, lon: 18 } }).catch(
      (error: unknown) => error
    )

    expect(caught).toBeInstanceOf(WeatherFetchError)
    expect((caught as WeatherFetchError).aborted).toBe(true)
    expect((caught as WeatherFetchError).fallback).toEqual(SNAP)
  })

  it("continues when sessionStorage refuses to persist a fresh snapshot", async () => {
    const setItem = vi.fn(() => {
      throw new Error("storage unavailable")
    })
    vi.spyOn(window, "sessionStorage", "get").mockReturnValue({
      getItem: vi.fn(() => null),
      setItem,
      removeItem: vi.fn(),
      clear: vi.fn(),
      key: vi.fn(),
      length: 0,
    } as unknown as Storage)
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        okResponse({
          current: { weather_code: 1, temperature_2m: 8, time: "2026-06-05T10:00:00Z" },
        })
      )
    )

    const result = await fetchWeatherSnapshot({ coordinates: { lat: 15, lon: 16 } })

    expect(result.temperatureC).toBe(8)
    expect(setItem).toHaveBeenCalled()
  })

  it("honors an external abort signal and force-refreshes a fresh cache", async () => {
    const controller = new AbortController()
    window.sessionStorage.setItem(
      "weather:snapshot:21.0000,22.0000",
      JSON.stringify({ data: SNAP, expiresAt: Date.now() + 60_000 })
    )
    const fetchMock = vi.fn().mockResolvedValue(
      okResponse({
        current: { weather_code: 2, temperature_2m: 9, time: "2026-06-05T10:00:00Z" },
      })
    )
    vi.stubGlobal("fetch", fetchMock)

    const result = await fetchWeatherSnapshot({
      coordinates: { lat: 21, lon: 22 },
      forceRefresh: true,
      signal: controller.signal,
    })

    expect(result.temperatureC).toBe(9)
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("latitude=21.00000"), {
      signal: controller.signal,
    })
  })

  it("fetches when a cached entry expires exactly now", async () => {
    vi.useFakeTimers()
    try {
      const now = new Date("2026-06-05T10:00:00.000Z")
      vi.setSystemTime(now)
      const staleAtBoundary = { ...SNAP, temperatureC: 1 }
      window.sessionStorage.setItem(
        "weather:snapshot:45.0000,46.0000",
        JSON.stringify({ data: staleAtBoundary, expiresAt: now.getTime() })
      )
      const fetchMock = vi.fn().mockResolvedValue(
        okResponse({
          current: { weather_code: 3, temperature_2m: 9, time: now.toISOString() },
        })
      )
      vi.stubGlobal("fetch", fetchMock)

      const result = await fetchWeatherSnapshot({ coordinates: { lat: 45, lon: 46 } })
      expect(result.temperatureC).toBe(9)
      expect(fetchMock).toHaveBeenCalledOnce()
    } finally {
      vi.useRealTimers()
    }
  })

  it("keeps external abort failures distinct from internally aborted requests", async () => {
    const controller = new AbortController()
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("caller cancelled")))

    const caught = await fetchWeatherSnapshot({
      coordinates: { lat: 41, lon: 42 },
      signal: controller.signal,
    }).catch((error: unknown) => error)

    expect(caught).toBeInstanceOf(WeatherFetchError)
    expect(caught).toMatchObject({
      name: "WeatherFetchError",
      message: "Failed to fetch weather",
      aborted: false,
      cause: expect.objectContaining({ message: "caller cancelled" }),
    })
  })
})

describe("readWeatherCache", () => {
  it("returns null when there is no entry", () => {
    expect(readWeatherCache({ lat: 99, lon: 99 })).toBeNull()
  })

  it("ignores empty and structurally invalid persisted entries", () => {
    window.sessionStorage.setItem("weather:snapshot:27.0000,28.0000", "")
    expect(readWeatherCache({ lat: 27, lon: 28 })).toBeNull()

    window.sessionStorage.setItem("weather:snapshot:29.0000,30.0000", JSON.stringify({}))
    expect(readWeatherCache({ lat: 29, lon: 30 })).toBeNull()
    window.sessionStorage.setItem("weather:snapshot:30.0000,31.0000", "null")
    expect(readWeatherCache({ lat: 30, lon: 31 })).toBeNull()
    window.sessionStorage.setItem("weather:snapshot:30.0000,32.0000", "[]")
    expect(readWeatherCache({ lat: 30, lon: 32 })).toBeNull()
    window.sessionStorage.setItem(
      "weather:snapshot:31.0000,32.0000",
      JSON.stringify({ expiresAt: Date.now() + 60_000 })
    )
    expect(readWeatherCache({ lat: 31, lon: 32 })).toBeNull()

    window.sessionStorage.setItem(
      "weather:snapshot:32.0000,33.0000",
      JSON.stringify({ expiresAt: "later", data: SNAP })
    )
    expect(readWeatherCache({ lat: 32, lon: 33 })).toBeNull()
  })

  it("rejects array-shaped entries even when they expose cache fields", () => {
    const parseSpy = vi
      .spyOn(JSON, "parse")
      .mockReturnValue(Object.assign([], { data: SNAP, expiresAt: Date.now() + 60_000 }))

    try {
      expect(readWeatherCache({ lat: 35, lon: 36 })).toBeNull()
    } finally {
      parseSpy.mockRestore()
    }
  })

  it("returns a fresh entry when expiration is in the future", () => {
    window.sessionStorage.setItem(
      "weather:snapshot:34.0000,35.0000",
      JSON.stringify({ data: SNAP, expiresAt: Date.now() + 60_000 })
    )

    expect(readWeatherCache({ lat: 34, lon: 35 })).toEqual({
      data: SNAP,
      expiresAt: expect.any(Number),
    })
  })

  it("ignores expired entries by default but returns them with allowExpired", () => {
    const key = "weather:snapshot:8.0000,8.0000"
    window.sessionStorage.setItem(key, JSON.stringify({ data: SNAP, expiresAt: Date.now() - 1000 }))

    expect(readWeatherCache({ lat: 8, lon: 8 })).toBeNull()
    expect(readWeatherCache({ lat: 8, lon: 8 }, { allowExpired: true })?.data).toEqual(SNAP)
  })

  it("treats an entry expiring at the current instant as expired", () => {
    vi.useFakeTimers()
    try {
      const now = new Date("2026-06-05T10:00:00.000Z")
      vi.setSystemTime(now)
      window.sessionStorage.setItem(
        "weather:snapshot:43.0000,44.0000",
        JSON.stringify({ data: SNAP, expiresAt: now.getTime() })
      )

      expect(readWeatherCache({ lat: 43, lon: 44 })).toBeNull()
      expect(readWeatherCache({ lat: 43, lon: 44 }, { allowExpired: true })?.data).toEqual(SNAP)
    } finally {
      vi.useRealTimers()
    }
  })

  it("returns null when a persisted cache entry is malformed JSON", () => {
    window.sessionStorage.setItem("weather:snapshot:17.0000,18.0000", "not-json")

    expect(readWeatherCache({ lat: 17, lon: 18 })).toBeNull()
  })

  it("fails closed when a storage adapter returns a non-string value", () => {
    const hostileValue = {
      toString: () => {
        throw new Error("unexpected coercion")
      },
    }
    vi.spyOn(window, "sessionStorage", "get").mockReturnValue({
      getItem: vi.fn(() => hostileValue),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
      key: vi.fn(),
      length: 1,
    } as unknown as Storage)

    expect(readWeatherCache({ lat: 18, lon: 19 })).toBeNull()
  })
})

describe("WeatherFetchError", () => {
  it("captures fallback, aborted, and cause options", () => {
    const cause = new Error("root")
    const err = new WeatherFetchError("boom", { fallback: SNAP, aborted: true, cause })
    expect(err.name).toBe("WeatherFetchError")
    expect(err.fallback).toEqual(SNAP)
    expect(err.aborted).toBe(true)
    expect(err.cause).toBe(cause)
  })

  it("defaults fallback to null and aborted to false", () => {
    const err = new WeatherFetchError("plain")
    expect(err.fallback).toBeNull()
    expect(err.aborted).toBe(false)
    expect(Object.prototype.hasOwnProperty.call(err, "cause")).toBe(false)
  })
})
