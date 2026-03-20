import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import { CAMPUS_COORDINATES } from "@/constants/campus"
import {
  WEATHER_CACHE_TTL_MS,
  WeatherFetchError,
  fetchWeatherSnapshot,
  readWeatherCache,
} from "@/api/weather"
import type { WeatherCoordinates, WeatherSnapshot } from "@/api/weather"
import { getWeatherIconMeta } from "@/utils/weatherIcons"
import type { WeatherAnimationVariant } from "@/utils/weatherIcons"
import useMediaQuery from "./useMediaQuery"

const WEATHER_TRANSLATION_BASE = "dashboard:weather.conditions"

export interface UseWeatherOptions {
  coordinates?: WeatherCoordinates
  cacheTtlMs?: number
}

export interface WeatherData extends WeatherSnapshot {
  icon: string
  translationKey: string
  translationKeySuffix: string
  animation: WeatherAnimationVariant
}

export interface UseWeatherResult {
  data: WeatherData | null
  isLoading: boolean
  error: Error | null
  refresh: () => Promise<void>
}

const toSignature = (coordinates: WeatherCoordinates): string => {
  const lat = Number(coordinates.lat).toFixed(4)
  const lon = Number(coordinates.lon).toFixed(4)
  return `${lat},${lon}`
}

const normalizeError = (error: unknown, coordinates: WeatherCoordinates): WeatherFetchError => {
  if (error instanceof WeatherFetchError) return error
  const fallback = readWeatherCache(coordinates, { allowExpired: true })?.data ?? null
  return new WeatherFetchError("Failed to fetch weather", { fallback, cause: error })
}

export const useWeather = (options: UseWeatherOptions = {}): UseWeatherResult => {
  const { coordinates: overrideCoordinates, cacheTtlMs = WEATHER_CACHE_TTL_MS } = options
  const coordinates = useMemo<WeatherCoordinates>(
    () =>
      overrideCoordinates
        ? Object.freeze({ lat: overrideCoordinates.lat, lon: overrideCoordinates.lon })
        : CAMPUS_COORDINATES,
    [overrideCoordinates]
  )
  const signature = useMemo(() => toSignature(coordinates), [coordinates])
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
  const abortRef = useRef<AbortController | null>(null)

  const initialCached = useMemo(
    () => readWeatherCache(coordinates, { allowExpired: true }),
    [coordinates]
  )
  const hasFreshCache = Boolean(initialCached && initialCached.expiresAt > Date.now())

  const [snapshot, setSnapshot] = useState<WeatherSnapshot | null>(initialCached?.data ?? null)
  const [isLoading, setIsLoading] = useState(!hasFreshCache)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    return () => {
      abortRef.current?.abort()
      abortRef.current = null
    }
  }, [])

  useEffect(() => {
    const cached = readWeatherCache(coordinates, { allowExpired: true })
    setSnapshot(cached?.data ?? null)
    const fresh = Boolean(cached && cached.expiresAt > Date.now())
    if (fresh) {
      setIsLoading(false)
      setError(null)
      return
    }
    setIsLoading(true)
    setError(null)

    const controller = new AbortController()
    abortRef.current?.abort()
    abortRef.current = controller

    void fetchWeatherSnapshot({
      coordinates,
      cacheTtlMs,
      signal: controller.signal,
    })
      .then((next) => {
        if (controller.signal.aborted) return
        setSnapshot(next)
        setError(null)
        setIsLoading(false)
      })
      .catch((err) => {
        if (controller.signal.aborted) return
        const normalized = normalizeError(err, coordinates)
        if (!normalized.aborted && normalized.fallback) {
          setSnapshot(normalized.fallback)
        }
        if (!normalized.aborted) {
          setError(normalized)
        }
        setIsLoading(false)
      })
  }, [cacheTtlMs, coordinates, signature])

  const load = useCallback(
    async (force: boolean) => {
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller
      try {
        const next = await fetchWeatherSnapshot({
          coordinates,
          cacheTtlMs,
          forceRefresh: force,
          signal: controller.signal,
        })
        if (controller.signal.aborted) return
        setSnapshot(next)
        setError(null)
        setIsLoading(false)
      } catch (err) {
        if (controller.signal.aborted) return
        const normalized = normalizeError(err, coordinates)
        if (normalized.aborted) {
          setIsLoading(false)
          return
        }
        if (normalized.fallback) {
          setSnapshot(normalized.fallback)
        }
        setError(normalized)
        setIsLoading(false)
      } finally {
        if (abortRef.current === controller) {
          abortRef.current = null
        }
      }
    },
    [cacheTtlMs, coordinates]
  )

  const refresh = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    await load(true)
  }, [load])

  const data = useMemo<WeatherData | null>(() => {
    if (!snapshot) return null
    const meta = getWeatherIconMeta(snapshot.conditionCode)
    const animation: WeatherAnimationVariant = prefersReducedMotion ? "none" : meta.animation
    return {
      ...snapshot,
      icon: meta.icon,
      translationKeySuffix: meta.translationKeySuffix,
      translationKey: `${WEATHER_TRANSLATION_BASE}.${meta.translationKeySuffix}`,
      animation,
    }
  }, [snapshot, prefersReducedMotion])

  return { data, isLoading, error, refresh }
}
