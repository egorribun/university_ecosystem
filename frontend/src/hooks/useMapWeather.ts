/**
 * useMapWeather.ts — Campus weather data from Open-Meteo API.
 * Wave 99 — initial; Wave 108 — expanded fields + hourly forecast.
 */

import { useQuery } from "@tanstack/react-query"
import { useEffect, useMemo } from "react"
import { CAMPUS_COORDINATES } from "@/constants/campus"
import { wmoToCondition, type WeatherCondition } from "@/utils/weatherCodes"

export interface HourlyPoint {
  /** Hour (0-23) */
  hour: number
  /** Temperature in Celsius, rounded */
  temperature: number
  /** Mapped weather condition */
  condition: WeatherCondition
}

export interface MapWeatherData {
  temperature: number
  weatherCode: number
  isDay: boolean
  condition: WeatherCondition
  /** Feels-like temperature (°C) */
  feelsLike: number
  /** Wind speed (m/s) */
  windSpeed: number
  /** Relative humidity (%) */
  humidity: number
  /** UV index (0-11+) */
  uvIndex: number
  /** Next 12 hours forecast */
  hourlyForecast: HourlyPoint[]
}

const LEGACY_CACHE_KEY = "map.weather.cache"
const CACHE_KEY = "map.weather.cache.v2"
const CACHE_VERSION = 2
const CACHE_WIND_SPEED_UNIT = "ms" as const
const CACHE_TTL = 30 * 60 * 1000

interface CachedWeather {
  version: number
  windSpeedUnit: typeof CACHE_WIND_SPEED_UNIT
  timestamp: number
  data: MapWeatherData
}

function readCache(): CachedWeather | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    if (!raw) return null
    const cached = JSON.parse(raw) as Partial<CachedWeather>
    const timestamp = cached?.timestamp
    const now = Date.now()
    if (
      !cached ||
      cached.version !== CACHE_VERSION ||
      cached.windSpeedUnit !== CACHE_WIND_SPEED_UNIT ||
      typeof timestamp !== "number" ||
      !Number.isFinite(timestamp) ||
      timestamp > now ||
      !cached.data
    ) {
      return null
    }
    if (now - timestamp >= CACHE_TTL) {
      return null
    }
    return cached as CachedWeather
  } catch {
    return null
  }
}

function writeCache(data: MapWeatherData): void {
  try {
    localStorage.setItem(
      CACHE_KEY,
      JSON.stringify({
        version: CACHE_VERSION,
        windSpeedUnit: CACHE_WIND_SPEED_UNIT,
        timestamp: Date.now(),
        data,
      })
    )
  } catch {
    // Safari private browsing — localStorage may throw (RZ-31-03)
  }
}

const API_URL = [
  `https://api.open-meteo.com/v1/forecast`,
  `?latitude=${CAMPUS_COORDINATES.lat}`,
  `&longitude=${CAMPUS_COORDINATES.lon}`,
  `&current=temperature_2m,weather_code,is_day,apparent_temperature,wind_speed_10m,relative_humidity_2m,uv_index`,
  `&hourly=temperature_2m,weather_code`,
  `&forecast_hours=12`,
  `&wind_speed_unit=ms`,
  `&timezone=Europe/Moscow`,
].join("")

/**
 * Lighthouse runs without the campus API dependencies. Keep the map route's
 * weather card deterministic in that isolated preview so performance checks
 * measure our UI rather than an external Open-Meteo request.
 */
const LHCI_MAP_WEATHER_DATA: MapWeatherData = {
  temperature: 20,
  weatherCode: 2,
  isDay: true,
  condition: wmoToCondition(2),
  feelsLike: 19,
  windSpeed: 2.5,
  humidity: 50,
  uvIndex: 2,
  hourlyForecast: [
    { hour: 12, temperature: 20, condition: wmoToCondition(2) },
    { hour: 13, temperature: 21, condition: wmoToCondition(1) },
  ],
}

async function fetchWeather(): Promise<MapWeatherData> {
  if (import.meta.env.VITE_LHCI === "true") return LHCI_MAP_WEATHER_DATA

  const res = await fetch(API_URL)
  if (!res.ok) throw new Error(`Weather API ${res.status}`)

  const json = await res.json()
  const current = json.current

  // Parse hourly forecast (12 points)
  const hourlyForecast: HourlyPoint[] = []
  const hourlyTimes: string[] = json.hourly?.time ?? []
  const hourlyTemps: number[] = json.hourly?.temperature_2m ?? []
  const hourlyCodes: number[] = json.hourly?.weather_code ?? []

  for (let i = 0; i < Math.min(hourlyTimes.length, 12); i++) {
    const hour = parseProviderWallHour(hourlyTimes[i])
    if (hour === null) continue
    hourlyForecast.push({
      hour,
      temperature: Math.round(hourlyTemps[i] ?? 0),
      condition: wmoToCondition(hourlyCodes[i] ?? 0),
    })
  }

  const data: MapWeatherData = {
    temperature: Math.round(current.temperature_2m),
    weatherCode: current.weather_code,
    isDay: current.is_day === 1,
    condition: wmoToCondition(current.weather_code),
    feelsLike: Math.round(current.apparent_temperature ?? current.temperature_2m),
    windSpeed: Math.round((current.wind_speed_10m ?? 0) * 10) / 10,
    humidity: Math.round(current.relative_humidity_2m ?? 0),
    uvIndex: Math.round(current.uv_index ?? 0),
    hourlyForecast,
  }

  writeCache(data)
  return data
}

/**
 * Open-Meteo returns local wall-clock timestamps for the requested timezone
 * without an offset. Read the provider hour directly rather than letting the
 * browser's local timezone normalize gaps or folds around DST transitions.
 */
function parseProviderWallHour(value: unknown): number | null {
  if (typeof value !== "string") return null

  const dateTime = value.split("T")
  if (dateTime.length !== 2) return null
  const dateParts = dateTime[0]?.split("-") ?? []
  const timeParts = dateTime[1]?.split(":") ?? []
  if (dateParts.length !== 3 || timeParts.length < 2 || timeParts.length > 3) return null

  const yearText = dateParts[0]
  const monthText = dateParts[1]
  const dayText = dateParts[2]
  const hourText = timeParts[0]
  const minuteText = timeParts[1]
  const secondText = timeParts[2]
  if (
    yearText === undefined ||
    monthText === undefined ||
    dayText === undefined ||
    hourText === undefined ||
    minuteText === undefined ||
    !/^\d{4}$/u.test(yearText) ||
    !/^\d{2}$/u.test(monthText) ||
    !/^\d{2}$/u.test(dayText) ||
    !/^\d{2}$/u.test(hourText) ||
    !/^\d{2}$/u.test(minuteText)
  ) {
    return null
  }

  const year = Number(yearText)
  const month = Number(monthText)
  const day = Number(dayText)
  const hour = Number(hourText)
  const minute = Number(minuteText)
  let second = 0
  if (secondText !== undefined) {
    const secondParts = secondText.split(".")
    const secondValue = secondParts[0]
    const fractionalSeconds = secondParts[1]
    if (
      secondParts.length > 2 ||
      secondValue === undefined ||
      !/^\d{2}$/u.test(secondValue) ||
      (fractionalSeconds !== undefined && !/^\d+$/u.test(fractionalSeconds))
    ) {
      return null
    }
    second = Number(secondValue)
  }

  const isLeapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0)
  const daysInMonth = [31, isLeapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
  const maxDay = daysInMonth[month - 1]

  if (
    month < 1 ||
    month > 12 ||
    day < 1 ||
    maxDay === undefined ||
    day > maxDay ||
    hour > 23 ||
    minute > 59 ||
    second > 59
  ) {
    return null
  }

  return hour
}

export function useMapWeather() {
  const cached = useMemo(() => (import.meta.env.VITE_LHCI === "true" ? null : readCache()), [])

  useEffect(() => {
    if (import.meta.env.VITE_LHCI === "true") return
    try {
      localStorage.removeItem(LEGACY_CACHE_KEY)
      if (!readCache()) localStorage.removeItem(CACHE_KEY)
    } catch {
      // Storage can be unavailable in private browsing or during SSR.
    }
  }, [])

  return useQuery<MapWeatherData>({
    queryKey: ["campus-weather"],
    queryFn: fetchWeather,
    initialData: cached?.data,
    initialDataUpdatedAt: cached?.timestamp,
    staleTime: CACHE_TTL,
    gcTime: 2 * CACHE_TTL,
    retry: 1,
    refetchOnWindowFocus: false,
  })
}
