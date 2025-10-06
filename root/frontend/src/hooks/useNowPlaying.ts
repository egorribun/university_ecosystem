import { useEffect, useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import api from "@/api/client"
import type { NowPlaying } from "@/types/spotify"

export const nowPlayingQueryKey = ["spotify", "now-playing"] as const

const isTestEnv = typeof import.meta !== "undefined" && import.meta.env.MODE === "test"

const STORAGE_KEY = "spotify:now-playing:last"

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
  if (typeof window === "undefined") return undefined
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return undefined
    return normalizeNowPlaying(JSON.parse(raw) as RawNowPlaying)
  } catch {
    return undefined
  }
}

const persistNowPlaying = (value: NowPlaying | null) => {
  if (typeof window === "undefined") return
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
  } catch {
    /* noop */
  }
}

export const fetchNowPlaying = async () => {
  const res = await api.get<RawNowPlaying>("/spotify/now-playing", {
    validateStatus: (status) => status === 204 || (status >= 200 && status < 300),
  })

  if (res.status === 204) return null
  return normalizeNowPlaying(res.data)
}

const computeInterval = (data: NowPlaying | null) => {
  if (!data || !data.is_playing) return 75_000
  if (data.duration_ms != null && data.progress_ms != null) {
    const remaining = Math.max(0, data.duration_ms - data.progress_ms)
    const padded = remaining + 5_000
    return Math.min(Math.max(padded, 15_000), 20_000)
  }
  return 18_000
}

export const useNowPlaying = (enabled: boolean) => {
  const cached = useMemo(() => readCachedNowPlaying(), [])

  const query = useQuery<NowPlaying | null, Error, NowPlaying | null, typeof nowPlayingQueryKey>({
    queryKey: nowPlayingQueryKey,
    queryFn: fetchNowPlaying,
    enabled,
    initialData: cached,
    placeholderData: (previous) => {
      if (previous !== undefined) return previous ?? null
      return cached ?? null
    },
    staleTime: 60_000,
    gcTime: 5 * 60_000,
    networkMode: "online",
    retry: 1,
    refetchOnWindowFocus: false,
    refetchInterval: ({ state }) => {
      if (!enabled || isTestEnv) return false
      if (typeof document !== "undefined" && document.visibilityState === "hidden") return false
      return computeInterval(state.data ?? null)
    },
    refetchIntervalInBackground: true,
  })

  const { data, isSuccess, refetch } = query

  useEffect(() => {
    if (!isSuccess) return
    persistNowPlaying(data ?? null)
  }, [data, isSuccess])

  useEffect(() => {
    if (!enabled || typeof document === "undefined") return
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
