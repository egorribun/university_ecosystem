import { useQuery } from "@tanstack/react-query"
import api from "@/api/client"
import type { NowPlaying } from "@/types/spotify"

export const nowPlayingQueryKey = ["spotify", "now-playing"] as const

const isTestEnv = typeof process !== "undefined" && process.env.NODE_ENV === "test"

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
    placeholderData: (previous: NowPlaying | null | undefined) => previous ?? null,
    staleTime: 15000,
    gcTime: 5 * 60 * 1000,
    refetchOnWindowFocus: enabled,
    refetchInterval: (query: { state: { data: NowPlaying | null | undefined } }) => {
      if (!enabled || isTestEnv) return false
      const data = query.state.data ?? null
      return computeInterval(data)
    },
    refetchIntervalInBackground: true,
  })
