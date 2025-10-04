import { useQuery } from "@tanstack/react-query"
import api from "@/api/client"
import type { NowPlaying } from "@/types/spotify"

export const nowPlayingQueryKey = ["spotify", "now-playing"] as const

const isTestEnv = typeof process !== "undefined" && process.env.NODE_ENV === "test"

const STORAGE_KEY = "spotify:now-playing:last"

const readCachedNowPlaying = (): NowPlaying | null | undefined => {
  if (typeof window === "undefined") return undefined
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return undefined
    return JSON.parse(raw) as NowPlaying | null
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
  const res = await api.get<NowPlaying>("/spotify/now-playing")
  return res.data
}

const computeInterval = (data?: NowPlaying | null) => {
  if (!data) return 15000
  if (data.is_playing && data.duration_ms && data.progress_ms != null) {
    const remain = Math.max(0, data.duration_ms - data.progress_ms)
    return Math.min(remain + 400, 20000)
  }
  return 15000
}

export const useNowPlaying = (enabled: boolean) =>
  useQuery<NowPlaying | null>({
    queryKey: nowPlayingQueryKey,
    queryFn: fetchNowPlaying,
    enabled,
    placeholderData: (previous: NowPlaying | null | undefined) => {
      if (previous !== undefined) return previous ?? null
      const cached = readCachedNowPlaying()
      return cached ?? null
    },
    staleTime: 60_000,
    gcTime: 5 * 60_000,
    networkMode: "online",
    retry: 1,
    refetchOnWindowFocus: enabled,
    refetchInterval: (query: { state: { data: NowPlaying | null | undefined } }) => {
      if (!enabled || isTestEnv) return false
      const data = query.state.data ?? null
      return computeInterval(data)
    },
    refetchIntervalInBackground: true,
    onSuccess: data => {
      persistNowPlaying(data ?? null)
    },
  })
