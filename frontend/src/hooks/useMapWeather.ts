/**
 * useMapWeather.ts — Campus weather data from Open-Meteo API.
 * Wave 99 — initial; Wave 108 — expanded fields + hourly forecast.
 */

import { useQuery } from "@tanstack/react-query"
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

const CACHE_KEY = "map.weather.cache"
const CACHE_TTL = 30 * 60 * 1000

interface CachedWeather {
  timestamp: number
  data: MapWeatherData
}

function readCache(): MapWeatherData | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    if (!raw) return null
    const cached = JSON.parse(raw) as CachedWeather
    if (Date.now() - cached.timestamp > CACHE_TTL) {
      localStorage.removeItem(CACHE_KEY)
      return null
    }
    return cached.data
  } catch {
    return null
  }
}

function writeCache(data: MapWeatherData): void {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify({ timestamp: Date.now(), data }))
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

  const cached = readCache()
  if (cached) return cached

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
    const timeStr = hourlyTimes[i]
    if (!timeStr) continue
    const dt = new Date(timeStr)
    hourlyForecast.push({
      hour: dt.getHours(),
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

export function useMapWeather() {
  return useQuery<MapWeatherData>({
    queryKey: ["campus-weather"],
    queryFn: fetchWeather,
    staleTime: CACHE_TTL,
    gcTime: 2 * CACHE_TTL,
    retry: 1,
    refetchOnWindowFocus: false,
  })
}
