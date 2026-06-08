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

  it("throws WeatherFetchError when the payload has no current block", async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse({ unexpected: true }))
    vi.stubGlobal("fetch", fetchMock)

    await expect(fetchWeatherSnapshot({ coordinates: { lat: 3, lon: 4 } })).rejects.toBeInstanceOf(
      WeatherFetchError
    )
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
})

describe("readWeatherCache", () => {
  it("returns null when there is no entry", () => {
    expect(readWeatherCache({ lat: 99, lon: 99 })).toBeNull()
  })

  it("ignores expired entries by default but returns them with allowExpired", () => {
    const key = "weather:snapshot:8.0000,8.0000"
    window.sessionStorage.setItem(key, JSON.stringify({ data: SNAP, expiresAt: Date.now() - 1000 }))

    expect(readWeatherCache({ lat: 8, lon: 8 })).toBeNull()
    expect(readWeatherCache({ lat: 8, lon: 8 }, { allowExpired: true })?.data).toEqual(SNAP)
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
