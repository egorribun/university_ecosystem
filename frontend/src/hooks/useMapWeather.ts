import { useQuery } from "@tanstack/react-query"
import { CAMPUS_COORDINATES } from "@/constants/campus"
import { wmoToCondition, type WeatherCondition } from "@/utils/weatherCodes"

export interface MapWeatherData {
  temperature: number
  weatherCode: number
  isDay: boolean
  condition: WeatherCondition
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

const API_URL = `https://api.open-meteo.com/v1/forecast?latitude=${CAMPUS_COORDINATES.lat}&longitude=${CAMPUS_COORDINATES.lon}&current=temperature_2m,weather_code,is_day&timezone=Europe/Moscow`

async function fetchWeather(): Promise<MapWeatherData> {
  const cached = readCache()
  if (cached) return cached

  const res = await fetch(API_URL)
  if (!res.ok) throw new Error(`Weather API ${res.status}`)

  const json = await res.json()
  const current = json.current

  const data: MapWeatherData = {
    temperature: Math.round(current.temperature_2m),
    weatherCode: current.weather_code,
    isDay: current.is_day === 1,
    condition: wmoToCondition(current.weather_code),
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
