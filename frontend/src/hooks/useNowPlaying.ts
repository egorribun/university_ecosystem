import { useCallback, useEffect, useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import api, { SKIP_UNAUTHORIZED_HEADER } from "@/api/client"
import type { NowPlaying } from "@/types/spotify"
import { getConfirmedUserId } from "@/stores/authIdentity"
import { captureSessionEpoch, getSessionEpoch } from "@/stores/sessionEpoch"
import { useAuthStore } from "@/stores/useAuthStore"

export const nowPlayingQueryKey = ["spotify", "now-playing"] as const
export const SPOTIFY_REAUTH_EVENT = "spotify:reauth-required"

const isTestEnv = import.meta.env.MODE === "test"

const storageKey = (owner: string) =>
  `spotify:now-playing:last:account:${encodeURIComponent(owner)}`
const getCurrentConfirmedUserId = () => getConfirmedUserId(useAuthStore.getState())

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

const readCachedNowPlaying = (owner: string | null): NowPlaying | null | undefined => {
  if (owner === null || getCurrentConfirmedUserId() !== owner) return undefined
  try {
    // Never adopt the legacy ownerless snapshot.
    const raw = window.localStorage.getItem(storageKey(owner))
    if (raw) return normalizeNowPlaying(JSON.parse(raw) as RawNowPlaying)
  } catch {
    // No browser storage (server rendering) or a malformed entry.
  }
  return undefined
}

const persistNowPlaying = (owner: string | null, value: NowPlaying | null) => {
  if (owner === null || getCurrentConfirmedUserId() !== owner) return
  // Without browser storage (server rendering) there is nothing to persist.
  try {
    window.localStorage.setItem(storageKey(owner), JSON.stringify(value))
  } catch {
    /* noop */
  }
}

export const fetchNowPlaying = async () => {
  const owner = getCurrentConfirmedUserId()
  const currentSession = captureSessionEpoch()
  const assertCurrentSession = () => {
    if (
      typeof window !== "undefined" &&
      (owner === null || !currentSession() || getCurrentConfirmedUserId() !== owner)
    ) {
      throw new DOMException("Session changed", "AbortError")
    }
  }
  assertCurrentSession()
  try {
    const res = await api.get<RawNowPlaying>("/spotify/now-playing", {
      validateStatus: (status) => status >= 200 && status < 300,
      headers: { [SKIP_UNAUTHORIZED_HEADER]: "1" },
    })

    assertCurrentSession()
    clearRateLimit()

    // A 204 has an empty body, which normalizes to "nothing playing".
    return normalizeNowPlaying(res.data)
  } catch (error) {
    // An old account's response must not update the query or reauthorize a new account.
    assertCurrentSession()
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
  error.name !== "AbortError" &&
  !(isAxiosError(error) && error.response?.status === 429) &&
  failureCount < 1

export const useNowPlaying = (enabled: boolean) => {
  const owner = useAuthStore(getConfirmedUserId)
  const epoch = getSessionEpoch()
  const isCurrentSession = useMemo(() => {
    const currentSession = captureSessionEpoch()
    return () => epoch === getSessionEpoch() && currentSession()
  }, [epoch])
  const ownsSession = useCallback(
    () =>
      typeof window === "undefined" ||
      (owner !== null && isCurrentSession() && getCurrentConfirmedUserId() === owner),
    [owner, isCurrentSession]
  )
  const active = enabled && (typeof window === "undefined" || owner !== null)
  const cached = useMemo(
    () => (isCurrentSession() ? readCachedNowPlaying(owner) : undefined),
    [owner, isCurrentSession]
  )

  const query = useQuery<NowPlaying | null, Error, NowPlaying | null, typeof nowPlayingQueryKey>({
    queryKey: nowPlayingQueryKey,
    queryFn: () => {
      if (!ownsSession()) throw new DOMException("Session changed", "AbortError")
      return fetchNowPlaying()
    },
    enabled: active,
    initialData: cached,
    // QueryObserver retains previous data after client.clear; only this owner's snapshot is safe.
    placeholderData: () => cached ?? null,
    select: (data) => (ownsSession() ? data : null),
    staleTime: 60_000,
    gcTime: 5 * 60_000,
    // Spotify requires the network; the application's offlineFirst default must not apply.
    networkMode: "online",
    retry: shouldRetryNowPlaying,
    refetchOnWindowFocus: false,
    // A hidden document already stops polling inside computeRefetchInterval.
    refetchInterval: ({ state }) =>
      computeRefetchInterval({ enabled: active, data: state.data ?? null }),
  })

  const { data, refetch } = query

  // The placeholder makes the query successful from the first render; a
  // failed poll keeps the last data, so persisting on every data change
  // stores exactly what was last shown.
  useEffect(() => {
    if (!query.isSuccess || !ownsSession()) return
    persistNowPlaying(owner, data ?? null)
  }, [data, owner, query.isSuccess, ownsSession])

  useEffect(() => {
    // Effects never run during server rendering, so the document exists here.
    if (!active) return
    const listener = () => {
      if (document.visibilityState === "visible" && ownsSession()) {
        void refetch()
      }
    }
    document.addEventListener("visibilitychange", listener)
    return () => document.removeEventListener("visibilitychange", listener)
  }, [active, refetch, ownsSession])

  return query
}

export const __testing = {
  clearRateLimit,
  getRateLimitedUntil: () => rateLimit.until,
  scheduleRateLimit,
  computeInterval,
  computeRefetchInterval,
  persistNowPlaying,
  shouldRetryNowPlaying,
}
