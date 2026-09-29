import { useEffect, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import api, { SKIP_UNAUTHORIZED_HEADER } from "@/api/client"
import type { NowPlaying } from "@/types/spotify"

export const nowPlayingQueryKey = ["spotify", "now-playing"] as const
export const SPOTIFY_REAUTH_EVENT = "spotify:reauth-required"

const isTestEnv = import.meta.env.MODE === "test"

const STORAGE_KEY = "spotify:now-playing:last"

const RATE_LIMIT_FALLBACK_MS = 5_000
const RATE_LIMIT_BUFFER_MS = 250

/** Polling intervals for NowPlaying status */
const POLLING_IDLE_MS = 3_000
const POLLING_PAUSED_MS = 2_000
const POLLING_ACTIVE_MS = 500

// RZ-43-03: Module-level rate limit state wrapped in object to avoid
// race conditions with concurrent React Strict Mode double-invocations.
// Object reference is stable; mutations are intentional (shared singleton).
const rateLimit = { until: 0 }

const clearRateLimit = () => {
  rateLimit.until = 0
}

const scheduleRateLimit = (ms: number) => {
  const wait = Math.max(0, ms)
  rateLimit.until = Date.now() + wait
}

const rateLimitDelay = () => {
  return Math.max(0, rateLimit.until - Date.now())
}

type RawNowPlaying = Partial<NowPlaying> | null | undefined

const toNullableString = (value: unknown) => {
  if (value == null) return null
  const str = String(value).trim()
  return str.length > 0 ? str : null
}

const toNullableNumber = (value: unknown) => {
  if (value == null) return null
  const num = Number(value)
  if (!Number.isFinite(num)) return null
  return Math.max(0, num)
}

const normalizeNowPlaying = (input: RawNowPlaying): NowPlaying | null => {
  if (!input) return null

  const artists = Array.isArray(input.artists)
    ? input.artists
        .map((artist) => toNullableString(artist))
        .filter((artist): artist is string => Boolean(artist))
    : []

  const durationMs = toNullableNumber(input.duration_ms)
  const progressMs = toNullableNumber(input.progress_ms)

  const payload: NowPlaying = {
    is_playing: Boolean(input.is_playing),
    track_id: toNullableString(input.track_id),
    track_name: toNullableString(input.track_name),
    artists,
    album_name: toNullableString(input.album_name),
    album_image_url: toNullableString(input.album_image_url),
    track_url: toNullableString(input.track_url),
    duration_ms: durationMs,
    progress_ms:
      durationMs != null && progressMs != null
        ? Math.min(Math.max(0, progressMs), durationMs)
        : progressMs,
    fetched_at: input.fetched_at ?? new Date().toISOString(),
  }

  const hasContent = payload.track_id || payload.track_name || payload.artists.length > 0
  if (!hasContent) return null

  return payload
}

const readCachedNowPlaying = (): NowPlaying | null | undefined => {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (raw) return normalizeNowPlaying(JSON.parse(raw) as RawNowPlaying)
  } catch {
    // No browser storage (server rendering) or a malformed entry.
  }
  return undefined
}

const persistNowPlaying = (value: NowPlaying | null) => {
  // Without browser storage (server rendering) there is nothing to persist.
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
  } catch {
    /* noop */
  }
}

const resolvePlaceholderData = (
  previous: NowPlaying | null | undefined,
  cached: NowPlaying | null | undefined
): NowPlaying | null => {
  if (previous !== undefined) return previous ?? null
  return cached ?? null
}

export const fetchNowPlaying = async () => {
  try {
    const res = await api.get<RawNowPlaying>("/spotify/now-playing", {
      validateStatus: (status) => status >= 200 && status < 300,
      headers: { [SKIP_UNAUTHORIZED_HEADER]: "1" },
    })

    clearRateLimit()

    // A 204 has an empty body, which normalizes to "nothing playing".
    return normalizeNowPlaying(res.data)
  } catch (error) {
    if (isAxiosError(error)) {
      if (error.response?.status === 401) {
        clearRateLimit()
        if (typeof window !== "undefined") {
          window.dispatchEvent(new CustomEvent(SPOTIFY_REAUTH_EVENT))
        }
        return null
      }
      if (error.response?.status === 429) {
        const header = error.response.headers?.["retry-after"]
        const raw = Array.isArray(header) ? header[0] : header
        // A missing header parses as NaN and uses the fallback below.
        const parsed = Number.parseFloat(String(raw))
        const waitMs =
          Number.isFinite(parsed) && parsed > 0 ? parsed * 1000 : RATE_LIMIT_FALLBACK_MS
        scheduleRateLimit(waitMs + RATE_LIMIT_BUFFER_MS)
      }
    }
    throw error
  }
}

const computeInterval = (data: NowPlaying | null) => {
  if (!data) return POLLING_IDLE_MS
  if (!data.is_playing) return POLLING_PAUSED_MS
  // Lightning-fast polling - check frequently for maximum responsiveness
  return POLLING_ACTIVE_MS
}

type RefetchIntervalOptions = {
  enabled: boolean
  data: NowPlaying | null
  isTestEnvironment?: boolean
  visibilityState?: DocumentVisibilityState
}

const computeRefetchInterval = ({
  enabled,
  data,
  isTestEnvironment = isTestEnv,
  visibilityState = typeof document === "undefined" ? undefined : document.visibilityState,
}: RefetchIntervalOptions): number | false => {
  if (!enabled || isTestEnvironment) return false
  if (visibilityState === "hidden") return false
  return Math.max(computeInterval(data), rateLimitDelay())
}

/** Retry a failed poll once, except when the server asked us to back off. */
const shouldRetryNowPlaying = (failureCount: number, error: Error): boolean =>
  !(isAxiosError(error) && error.response?.status === 429) && failureCount < 1

export const useNowPlaying = (enabled: boolean) => {
  const [cached] = useState(readCachedNowPlaying)

  const query = useQuery<NowPlaying | null, Error, NowPlaying | null, typeof nowPlayingQueryKey>({
    queryKey: nowPlayingQueryKey,
    queryFn: fetchNowPlaying,
    enabled,
    initialData: cached,
    placeholderData: (previous) => resolvePlaceholderData(previous, cached),
    staleTime: 60_000,
    gcTime: 5 * 60_000,
    // Spotify requires the network; the application's offlineFirst default must not apply.
    networkMode: "online",
    retry: shouldRetryNowPlaying,
    refetchOnWindowFocus: false,
    // A hidden document already stops polling inside computeRefetchInterval.
    refetchInterval: ({ state }) => computeRefetchInterval({ enabled, data: state.data ?? null }),
  })

  const { data, refetch } = query

  // The placeholder makes the query successful from the first render; a
  // failed poll keeps the last data, so persisting on every data change
  // stores exactly what was last shown.
  useEffect(() => {
    persistNowPlaying(data ?? null)
  }, [data])

  useEffect(() => {
    // Effects never run during server rendering, so the document exists here.
    if (!enabled) return
    const listener = () => {
      if (document.visibilityState === "visible") {
        void refetch()
      }
    }
    document.addEventListener("visibilitychange", listener)
    return () => document.removeEventListener("visibilitychange", listener)
  }, [enabled, refetch])

  return query
}

export const __testing = {
  clearRateLimit,
  getRateLimitedUntil: () => rateLimit.until,
  scheduleRateLimit,
  computeInterval,
  computeRefetchInterval,
  persistNowPlaying,
  resolvePlaceholderData,
  shouldRetryNowPlaying,
}
