import type { SpotifyNowPlayingOut } from "@/api/generated"

export type NowPlaying = Omit<SpotifyNowPlayingOut, "artists" | "fetched_at"> & {
  artists: SpotifyNowPlayingOut["artists"] extends (infer T)[] | undefined ? T[] : string[]
  fetched_at?: string | number | Date | null
}
