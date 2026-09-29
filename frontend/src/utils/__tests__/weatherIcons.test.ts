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

  it("preserves the complete provider mapping and metadata contract", () => {
    const expected = [
      [0, "Clear sky", "clear", "☀️", "glow"],
      [1, "Mostly clear", "mostlyClear", "🌤️", "glow"],
      [2, "Mostly clear", "mostlyClear", "🌤️", "glow"],
      [3, "Overcast", "cloudy", "☁️", "breeze"],
      [45, "Fog", "fog", "🌫️", "none"],
      [48, "Fog", "fog", "🌫️", "none"],
      [51, "Drizzle", "drizzle", "🌦️", "drizzle"],
      [53, "Drizzle", "drizzle", "🌦️", "drizzle"],
      [55, "Drizzle", "drizzle", "🌦️", "drizzle"],
      [56, "Freezing drizzle", "freezingDrizzle", "🌧️", "drizzle"],
      [57, "Freezing drizzle", "freezingDrizzle", "🌧️", "drizzle"],
      [61, "Rain", "rain", "🌧️", "drizzle"],
      [63, "Rain", "rain", "🌧️", "drizzle"],
      [65, "Rain", "rain", "🌧️", "drizzle"],
      [66, "Freezing rain", "freezingRain", "🌧️", "drizzle"],
      [67, "Freezing rain", "freezingRain", "🌧️", "drizzle"],
      [71, "Snowfall", "snow", "🌨️", "snow"],
      [73, "Snowfall", "snow", "🌨️", "snow"],
      [75, "Snowfall", "snow", "🌨️", "snow"],
      [77, "Snow grains", "snowGrains", "❄️", "snow"],
      [80, "Rain showers", "rainShowers", "🌦️", "drizzle"],
      [81, "Rain showers", "rainShowers", "🌦️", "drizzle"],
      [82, "Rain showers", "rainShowers", "🌦️", "drizzle"],
      [85, "Snow showers", "snowShowers", "🌨️", "snow"],
      [86, "Snow showers", "snowShowers", "🌨️", "snow"],
      [95, "Thunderstorm", "thunderstorm", "⛈️", "storm"],
      [96, "Thunderstorm with hail", "thunderstormHail", "⛈️", "storm"],
      [99, "Thunderstorm with hail", "thunderstormHail", "⛈️", "storm"],
    ] as const

    for (const [code, label, translationKeySuffix, icon, animation] of expected) {
      expect(getWeatherIconMeta(code), `weather code ${code}`).toEqual({
        label,
        translationKeySuffix,
        icon,
        animation,
      })
    }
  })

  it("keeps fallback metadata stable and immutable", () => {
    expect(WEATHER_ICON_FALLBACK).toEqual({
      label: "Unknown conditions",
      translationKeySuffix: "unknown",
      icon: "🌡️",
      animation: "none",
    })
    expect(Object.isFrozen(WEATHER_ICON_FALLBACK)).toBe(true)
    expect(getWeatherIconMeta(-1)).toBe(WEATHER_ICON_FALLBACK)
    expect(getWeatherIconMeta(-1.9)).toBe(WEATHER_ICON_FALLBACK)
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
