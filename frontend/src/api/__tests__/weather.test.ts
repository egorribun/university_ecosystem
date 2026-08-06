import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"

import {
  fetchWeatherSnapshot,
  readWeatherCache,
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

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okResponse({ current: null })))
    await expect(
      fetchWeatherSnapshot({ coordinates: { lat: 25, lon: 26 } })
    ).rejects.toBeInstanceOf(WeatherFetchError)
  })

  it("throws WeatherFetchError when the payload has no current block", async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse({ unexpected: true }))
    vi.stubGlobal("fetch", fetchMock)

    await expect(fetchWeatherSnapshot({ coordinates: { lat: 3, lon: 4 } })).rejects.toBeInstanceOf(
      WeatherFetchError
    )
  })

  it("rejects primitive weather payloads", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okResponse(null)))

    await expect(fetchWeatherSnapshot({ coordinates: { lat: 4, lon: 5 } })).rejects.toBeInstanceOf(
      WeatherFetchError
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

    await expect(fetchWeatherSnapshot({ coordinates: { lat: 5, lon: 6 } })).rejects.toBeInstanceOf(
      WeatherFetchError
    )
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
  })

  it("ignores expired entries by default but returns them with allowExpired", () => {
    const key = "weather:snapshot:8.0000,8.0000"
    window.sessionStorage.setItem(key, JSON.stringify({ data: SNAP, expiresAt: Date.now() - 1000 }))

    expect(readWeatherCache({ lat: 8, lon: 8 })).toBeNull()
    expect(readWeatherCache({ lat: 8, lon: 8 }, { allowExpired: true })?.data).toEqual(SNAP)
  })

  it("returns null when a persisted cache entry is malformed JSON", () => {
    window.sessionStorage.setItem("weather:snapshot:17.0000,18.0000", "not-json")

    expect(readWeatherCache({ lat: 17, lon: 18 })).toBeNull()
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
  })
})
