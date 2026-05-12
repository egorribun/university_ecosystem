/**
 * @fileoverview SSR-safe queryOptions factory for the dashboard
 * `useWeather` hook.
 *
 * Wave 130 SW3 — extracted from `useWeather()` (frontend/src/hooks/
 * useWeather.ts) so the cache participates in the per-request
 * QueryClient + the hook gains React Query DevTools visibility.
 *
 * NOT used by `useMapWeather` (frontend/src/hooks/useMapWeather.ts)
 * which has its own state machine + Open-Meteo enrichment per
 * Wave 106 design (see CLAUDE.md gotcha "Map weather: useMapWeather()
 * hook (NOT useWeather - that's dashboard)").
 *
 * `placeholderData` reads sessionStorage so the widget paints with
 * cached data on cold mount even before queryFn resolves. The
 * underlying `readWeatherCache` helper has a `typeof window`
 * guard so SSR returns null rather than crashing.
 *
 * Usage:
 *
 * ```ts
 * useQuery(weatherQueryOptions(CAMPUS_COORDINATES))
 * ```
 */
import {
  WEATHER_CACHE_TTL_MS,
  type WeatherCoordinates,
  type WeatherSnapshot,
  fetchWeatherSnapshot,
  readWeatherCache,
} from "@/api/weather"

export type WeatherQueryKey = readonly ["weather", "snapshot", string, string]

export const weatherQueryKey = (coordinates: WeatherCoordinates): WeatherQueryKey =>
  [
    "weather",
    "snapshot",
    Number(coordinates.lat).toFixed(4),
    Number(coordinates.lon).toFixed(4),
  ] as const

export const weatherQueryOptions = (
  coordinates: WeatherCoordinates,
  cacheTtlMs: number = WEATHER_CACHE_TTL_MS
) => ({
  queryKey: weatherQueryKey(coordinates),
  queryFn: async ({ signal }: { signal?: AbortSignal }): Promise<WeatherSnapshot> => {
    return fetchWeatherSnapshot({ coordinates, cacheTtlMs, signal })
  },
  // Cold-mount fast paint via sessionStorage (typeof window guard
  // inside readWeatherCache returns null on SSR — placeholderData
  // simply absent there, query starts in loading state).
  placeholderData: (): WeatherSnapshot | undefined => {
    const cached = readWeatherCache(coordinates, { allowExpired: true })
    return cached?.data ?? undefined
  },
  staleTime: cacheTtlMs,
  gcTime: 30 * 60_000,
  retry: 1,
  refetchOnWindowFocus: false,
  refetchOnMount: false,
})
