export type NowPlaying = {
  is_playing: boolean
  track_id: string | null
  track_name: string | null
  artists: string[]
  album_name: string | null
  album_image_url: string | null
  track_url: string | null
  duration_ms: number | null
  progress_ms: number | null
  fetched_at?: string | number | Date | null
}
