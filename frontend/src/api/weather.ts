import { CAMPUS_COORDINATES } from "@/constants/campus"
import type { CampusCoordinates } from "@/constants/campus"
import { getWeatherIconMeta } from "@/utils/weatherIcons"

export interface WeatherSnapshot {
  conditionCode: number
  conditionLabel: string
  /** Temperature in degrees Celsius. Null when unavailable. */
  temperatureC: number | null
  /** ISO timestamp reported by the provider. */
  observedAt: string
}

export type WeatherCoordinates = CampusCoordinates

export interface WeatherCacheEntry {
  data: WeatherSnapshot
  expiresAt: number
}

export const WEATHER_CACHE_TTL_MS = 10 * 60_000

const WEATHER_CACHE_PREFIX = "weather:snapshot"

const toNumber = (value: unknown): number | null => {
  if (value == null) return null
  const num = Number(value)
  return Number.isFinite(num) ? num : null
}

const toIsoString = (value: unknown): string | null => {
  if (typeof value !== "string" || value.trim().length === 0) return null
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return null
  return parsed.toISOString()
}

const toCacheKey = ({ lat, lon }: WeatherCoordinates) => {
  const latKey = Number(lat).toFixed(4)
  const lonKey = Number(lon).toFixed(4)
  return `${WEATHER_CACHE_PREFIX}:${latKey},${lonKey}`
}

const readCacheEntry = (
  key: string,
  { allowExpired = false }: { allowExpired?: boolean } = {}
): WeatherCacheEntry | null => {
  if (typeof window === "undefined") return null
  try {
    const raw = window.sessionStorage?.getItem(key)
    if (!raw) return null
    const parsed = JSON.parse(raw) as WeatherCacheEntry
    if (!parsed || typeof parsed !== "object") return null
    if (typeof parsed.expiresAt !== "number" || !parsed.data) return null
    if (!allowExpired && parsed.expiresAt <= Date.now()) return null
    return parsed
  } catch {
    return null
  }
}

const writeCacheEntry = (key: string, entry: WeatherCacheEntry) => {
  if (typeof window === "undefined") return
  try {
    window.sessionStorage?.setItem(key, JSON.stringify(entry))
  } catch {
    /* ignore persistence failures */
  }
}

const pickCurrentBlock = (input: unknown) => {
  if (!input || typeof input !== "object") return null
  const current = (input as { current?: unknown }).current
  if (current && typeof current === "object") return current
  const legacy = (input as { current_weather?: unknown }).current_weather
  if (legacy && typeof legacy === "object") {
    const block = legacy as { time?: unknown; temperature?: unknown; weathercode?: unknown }
    return {
      time: block.time,
      temperature_2m: block.temperature,
      weather_code: block.weathercode,
    }
  }
  return null
}

const normalizeSnapshot = (payload: unknown): WeatherSnapshot => {
  const current = pickCurrentBlock(payload)
  if (!current || typeof current !== "object") {
    throw new Error("Missing current weather data")
  }

  const codeValue =
    (current as { weather_code?: unknown }).weather_code ??
    (current as { weathercode?: unknown }).weathercode
  const tempValue =
    (current as { temperature_2m?: unknown }).temperature_2m ??
    (current as { temperature?: unknown }).temperature
  const timeValue = (current as { time?: unknown }).time

  const parsedCode = toNumber(codeValue)
  const conditionCode = Number.isFinite(parsedCode ?? NaN) ? Math.trunc(parsedCode as number) : -1
  const meta = getWeatherIconMeta(conditionCode)
  const observedAt = toIsoString(timeValue) ?? new Date().toISOString()
  const temperature = toNumber(tempValue)

  return {
    conditionCode,
    conditionLabel: meta.label,
    temperatureC: temperature,
    observedAt,
  }
}

export class WeatherFetchError extends Error {
  fallback: WeatherSnapshot | null
  aborted: boolean
  cause?: unknown

  constructor(
    message: string,
    options: { fallback?: WeatherSnapshot | null; cause?: unknown; aborted?: boolean } = {}
  ) {
    super(message)
    this.name = "WeatherFetchError"
    this.fallback = options.fallback ?? null
    this.aborted = Boolean(options.aborted)
    if (options.cause !== undefined) {
      this.cause = options.cause
    }
  }
}

export const readWeatherCache = (
  coordinates: WeatherCoordinates = CAMPUS_COORDINATES,
  options?: { allowExpired?: boolean }
): WeatherCacheEntry | null => {
  const key = toCacheKey(coordinates)
  return readCacheEntry(key, options)
}

export interface FetchWeatherOptions {
  coordinates?: WeatherCoordinates
  cacheTtlMs?: number
  forceRefresh?: boolean
  signal?: AbortSignal
}

export const fetchWeatherSnapshot = async (
  options: FetchWeatherOptions = {}
): Promise<WeatherSnapshot> => {
  const coordinates = options.coordinates ?? CAMPUS_COORDINATES
  const ttl = Math.max(30_000, options.cacheTtlMs ?? WEATHER_CACHE_TTL_MS)
  const key = toCacheKey(coordinates)
  const cached = readCacheEntry(key, { allowExpired: true })

  if (!options.forceRefresh && cached && cached.expiresAt > Date.now()) {
    return cached.data
  }

  const controller = options.signal ? null : new AbortController()
  const signal = options.signal ?? controller!.signal

  const url = new URL("https://api.open-meteo.com/v1/forecast")
  url.searchParams.set("latitude", Number(coordinates.lat).toFixed(5))
  url.searchParams.set("longitude", Number(coordinates.lon).toFixed(5))
  url.searchParams.set("current", "temperature_2m,weather_code")
  url.searchParams.set("timeformat", "iso8601")
  url.searchParams.set("forecast_days", "1")
  url.searchParams.set("timezone", "auto")

  try {
    const response = await fetch(url.toString(), { signal })
    if (!response.ok) {
      throw new Error(`Weather request failed with status ${response.status}`)
    }
    const payload = await response.json()
    const snapshot = normalizeSnapshot(payload)
    writeCacheEntry(key, { data: snapshot, expiresAt: Date.now() + ttl })
    return snapshot
  } catch (error) {
    if (controller && controller.signal.aborted) {
      throw new WeatherFetchError("Weather request aborted", {
        fallback: cached?.data ?? null,
        cause: error,
        aborted: true,
      })
    }
    throw new WeatherFetchError("Failed to fetch weather", {
      fallback: cached?.data ?? null,
      cause: error,
    })
  }
}




