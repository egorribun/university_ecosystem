/**
 * useOverpassPOI.ts — TanStack Query hook for lazy Overpass API POI fetching.
 *
 * Not fetched automatically — only on user "load more" action.
 * Results cached in localStorage with 24h TTL.
 *
 * Wave 99 — campus map Leaflet integration.
 */

import { useQuery } from "@tanstack/react-query"
import { fetchOverpassPOIs } from "@/utils/overpassQuery"
import { CAMPUS_COORDINATES } from "@/constants/campus"
import type { CampusPOI } from "@/data/campusPOI"

const CACHE_KEY = "map.overpass.cache"
const CACHE_TTL = 24 * 60 * 60 * 1000 // 24 hours

interface CachedData {
  timestamp: number
  pois: CampusPOI[]
}

function readCache(): CampusPOI[] | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    if (!raw) return null
    const cached = JSON.parse(raw) as CachedData
    if (Date.now() - cached.timestamp > CACHE_TTL) {
      localStorage.removeItem(CACHE_KEY)
      return null
    }
    return cached.pois
  } catch {
    return null
  }
}

function writeCache(pois: CampusPOI[]): void {
  try {
    const data: CachedData = { timestamp: Date.now(), pois }
    localStorage.setItem(CACHE_KEY, JSON.stringify(data))
  } catch {
    // Safari private browsing — localStorage may throw (RZ-31-03)
  }
}

async function fetchWithCache(): Promise<CampusPOI[]> {
  const cached = readCache()
  if (cached) return cached

  const center: [number, number] = [CAMPUS_COORDINATES.lat, CAMPUS_COORDINATES.lon]
  const pois = await fetchOverpassPOIs(center, 500)
  writeCache(pois)
  return pois
}

/**
 * Lazy Overpass POI hook — only fetches when manually triggered via refetch().
 * Results are cached in localStorage for 24h.
 */
export function useOverpassPOI() {
  const query = useQuery<CampusPOI[]>({
    queryKey: ["overpass-poi"],
    queryFn: fetchWithCache,
    enabled: false,
    staleTime: CACHE_TTL,
    gcTime: 2 * CACHE_TTL,
    retry: 1,
  })

  return {
    pois: query.data ?? [],
    isLoading: query.isFetching,
    isError: query.isError,
    error: query.error,
    /** Call to trigger Overpass API fetch (or load from cache) */
    loadMore: query.refetch,
    hasLoaded: query.isSuccess,
    // query.isSuccess is true when fetchWithCache resolves (including cached path)
    isCached: query.isSuccess,
  }
}
