import { useCallback, useMemo, useRef } from "react"
import { useQuery } from "@tanstack/react-query"

import { weatherQueryOptions } from "@/api/hooks/weather"
import { CAMPUS_COORDINATES } from "@/constants/campus"
import { WEATHER_CACHE_TTL_MS, fetchWeatherSnapshot } from "@/api/weather"
import type { WeatherCoordinates, WeatherSnapshot } from "@/api/weather"
import { getWeatherIconMeta } from "@/utils/weatherIcons"
import type { WeatherAnimationVariant } from "@/utils/weatherIcons"
import useMediaQuery from "./useMediaQuery"

const WEATHER_TRANSLATION_BASE = "dashboard:weather.conditions"

// Lighthouse audits run without the transactional backend and must not make
// an external Open-Meteo request in the critical navigation window. Keep a
// deterministic, representative snapshot in the audit-only bundle; Vite
// replaces the flag at build time and removes this branch from production.
const LHCI_WEATHER_SNAPSHOT: WeatherSnapshot = {
  conditionCode: 2,
  conditionLabel: "Partly cloudy",
  temperatureC: 20,
  observedAt: "2026-01-01T12:00:00.000Z",
}

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

/**
 * Wave 130 SW3 — migrated from bespoke fetch + sessionStorage +
 * AbortController + 4 useState/useEffect calls to standard
 * TanStack Query (matches project convention per useDashboardSchedule,
 * useNewsListQuery, useEventsListQuery).
 *
 * Public API preserved: same `UseWeatherResult` shape so
 * `Dashboard.tsx`, `WeatherWidget.tsx`, and existing mocks in
 * `pageTranslations.test.tsx` + `WeatherWidget.test.tsx` keep working
 * unchanged.
 *
 * Cache layer: TanStack Query in-memory + sessionStorage cold-mount
 * placeholderData (handled by weatherQueryOptions factory). The
 * underlying `fetchWeatherSnapshot` helper continues to write to
 * sessionStorage on success so a fresh tab on subsequent visits gets
 * an instant paint via placeholderData read.
 *
 * `WeatherFetchError` thrown by queryFn surfaces via `query.error`
 * preserving the prior fallback semantics.
 *
 * Wave 130 polish — `refresh()` honours forceRefresh semantics
 * (closes W130 §Honesty probe #6). User-initiated refresh sets
 * `forceRefreshRef.current = true`; the local queryFn override
 * reads + clears the ref + propagates `forceRefresh: true` to
 * `fetchWeatherSnapshot`, which then bypasses the sessionStorage
 * cache check at api/weather.ts:155-159 and forces a network
 * round-trip. SSR loaders + factory consumers use the unmodified
 * factory queryFn (no forceRefresh) — only the dashboard hook
 * exercises the refresh-button flow.
 */
export const useWeather = (options: UseWeatherOptions = {}): UseWeatherResult => {
  const { coordinates: overrideCoordinates, cacheTtlMs = WEATHER_CACHE_TTL_MS } = options
  const coordinates = useMemo<WeatherCoordinates>(
    () =>
      overrideCoordinates
        ? Object.freeze({ lat: overrideCoordinates.lat, lon: overrideCoordinates.lon })
        : CAMPUS_COORDINATES,
    [overrideCoordinates]
  )
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
  const forceRefreshRef = useRef(false)

  const query = useQuery({
    ...weatherQueryOptions(coordinates, cacheTtlMs),
    queryFn: async ({ signal }: { signal?: AbortSignal }): Promise<WeatherSnapshot> => {
      if (import.meta.env.VITE_LHCI === "true") return LHCI_WEATHER_SNAPSHOT
      const force = forceRefreshRef.current
      forceRefreshRef.current = false
      return fetchWeatherSnapshot({ coordinates, cacheTtlMs, forceRefresh: force, signal })
    },
  })

  const data = useMemo<WeatherData | null>(() => {
    const snapshot = query.data
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
  }, [query.data, prefersReducedMotion])

  const refresh = useCallback(async () => {
    forceRefreshRef.current = true
    await query.refetch()
  }, [query])

  return {
    data,
    isLoading: query.isPending,
    error: (query.error as Error | null) ?? null,
    refresh,
  }
}
