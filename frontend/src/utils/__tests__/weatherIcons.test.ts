import { describe, it, expect } from "vitest"

import { getWeatherIconMeta, getWeatherLabel, WEATHER_ICON_FALLBACK } from "../weatherIcons"

describe("getWeatherIconMeta", () => {
  it("returns the matching meta for a known code", () => {
    const meta = getWeatherIconMeta(0)
    expect(meta.label).toBe("Clear sky")
    expect(meta.animation).toBe("glow")
    expect(meta.translationKeySuffix).toBe("clear")
  })

  it("truncates fractional codes before lookup", () => {
    // 75.9 → trunc 75 → Snowfall
    expect(getWeatherIconMeta(75.9).label).toBe("Snowfall")
  })

  it("returns the fallback for null/undefined/non-finite codes", () => {
    expect(getWeatherIconMeta(null)).toBe(WEATHER_ICON_FALLBACK)
    expect(getWeatherIconMeta(undefined)).toBe(WEATHER_ICON_FALLBACK)
    expect(getWeatherIconMeta(Number.NaN)).toBe(WEATHER_ICON_FALLBACK)
    expect(getWeatherIconMeta(Number.POSITIVE_INFINITY)).toBe(WEATHER_ICON_FALLBACK)
  })

  it("returns the fallback for an unmapped finite code", () => {
    expect(getWeatherIconMeta(200)).toBe(WEATHER_ICON_FALLBACK)
  })
})

describe("getWeatherLabel", () => {
  it("returns the label for a known code", () => {
    expect(getWeatherLabel(95)).toBe("Thunderstorm")
  })

  it("returns the fallback label for an unknown code", () => {
    expect(getWeatherLabel(null)).toBe(WEATHER_ICON_FALLBACK.label)
  })
})
