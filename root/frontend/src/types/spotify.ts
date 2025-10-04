export type NowPlaying = {
  is_playing: boolean
  progress_ms?: number
  duration_ms?: number
  track_id?: string
  track_name?: string
  artists?: string[]
  album_name?: string
  album_image_url?: string
  track_url?: string
  preview_url?: string
  fetched_at: string | number | Date
}
