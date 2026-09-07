import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react"
import { m } from "framer-motion"
import { useTranslation } from "react-i18next"
import { motion as motionTokens } from "@/theme/tokens"
import { cn } from "@/utils/cn"
import useMediaQuery from "@/hooks/useMediaQuery"
import type { NowPlaying } from "@/types/spotify"

const isTest = typeof import.meta !== "undefined" && import.meta.env.MODE === "test"

export const clampNowPlayingProgress = (
  value: number | null | undefined,
  duration: number
): number => {
  if (value == null) return 0
  if (!Number.isFinite(value)) return 0
  if (!duration || duration <= 0) return Math.max(0, value)
  return Math.min(Math.max(0, value), duration)
}

export const getNowPlayingTrackKey = (trackId: string | null | undefined): string | null =>
  trackId ?? null

export const isNowPlayingResumed = (isPlaying: boolean, wasPlaying: boolean): boolean =>
  isPlaying && !wasPlaying

export const shouldSyncNowPlayingState = (
  trackChanged: boolean,
  progressChanged: boolean,
  resumed: boolean
): boolean => trackChanged || progressChanged || resumed

export const shouldAnimateNowPlaying = (
  testEnvironment: boolean,
  isPlaying: boolean,
  prefersReduce: boolean,
  reduced: boolean,
  duration: number
): boolean => !testEnvironment && isPlaying && !prefersReduce && !reduced && duration > 0

export const getNowPlayingProgressTransition = (
  shouldAnimate: boolean,
  prefersReduce: boolean,
  reduced: boolean
): string =>
  shouldAnimate && !prefersReduce && !reduced
    ? `transform ${motionTokens.durationInstant}s linear`
    : `transform ${motionTokens.durationFast}s ease-out`

export const getNowPlayingInitial = (
  testEnvironment: boolean,
  prefersReduce: boolean,
  reduced: boolean
): false | { y: number; opacity: number; scale: number } =>
  testEnvironment || prefersReduce || reduced
    ? false
    : { y: motionTokens.slideSm, opacity: 0.8, scale: 1 }

export const getNowPlayingTransition = (
  testEnvironment: boolean
): { duration: number } | { type: "spring"; stiffness: number; damping: number; mass: number } =>
  testEnvironment ? { duration: 0 } : { type: "spring", stiffness: 520, damping: 36, mass: 0.9 }

export const shouldUseNowPlayingImage = (imageUrl: string | null, imageError: boolean): boolean =>
  Boolean(imageUrl) && !imageError

export const shouldUseNowPlayingImageHover = (prefersReduce: boolean, reduced: boolean): boolean =>
  !prefersReduce && !reduced

export const isNowPlayingImageVisible = (
  imageLoaded: boolean,
  imageUrl: string | null,
  imageError: boolean
): boolean => imageLoaded || !imageUrl || imageError

export const getNowPlayingTrackTime = (ms: number): string => {
  const seconds = Math.max(0, Math.floor(ms / 1000))
  const minutes = Math.floor(seconds / 60)
  const rest = String(seconds % 60).padStart(2, "0")
  return `${minutes}:${rest}`
}

export const NowPlayingCard = memo(function NowPlayingCard({ data }: { data: NowPlaying }) {
  const prefersReduce = useMediaQuery("(prefers-reduced-motion: reduce)")
  const reduced = useMediaQuery("(prefers-reduced-motion: reduce)")
  const duration = data.duration_ms ?? 0
  const { t } = useTranslation(["profile"])
  const [imageLoaded, setImageLoaded] = useState(false)
  const [imageError, setImageError] = useState(false)

  const clampProgress = useCallback(
    (value: number | null | undefined) => clampNowPlayingProgress(value, duration),
    [duration]
  )

  const initialProgress = clampProgress(data.progress_ms)
  const [progress, setProgress] = useState<number>(() => initialProgress)
  const startRef = useRef<number>(Date.now() - initialProgress)
  const rafRef = useRef<number | null>(null)
  const prevTrackIdRef = useRef<string | null>(getNowPlayingTrackKey(data.track_id))
  const prevProgressRef = useRef<number>(initialProgress)
  const prevIsPlayingRef = useRef<boolean>(data.is_playing)

  useEffect(() => {
    const next = clampProgress(data.progress_ms)
    const trackChanged = getNowPlayingTrackKey(data.track_id) !== prevTrackIdRef.current
    const progressChanged = next !== prevProgressRef.current
    const resumed = isNowPlayingResumed(data.is_playing, prevIsPlayingRef.current)

    if (trackChanged) {
      prevTrackIdRef.current = getNowPlayingTrackKey(data.track_id)
      setImageLoaded(false)
      setImageError(false)
    }

    if (progressChanged) {
      prevProgressRef.current = next
    }

    if (shouldSyncNowPlayingState(trackChanged, progressChanged, resumed)) {
      startRef.current = Date.now() - next
      setProgress(next)
    }

    prevIsPlayingRef.current = data.is_playing
  }, [clampProgress, data.is_playing, data.progress_ms, data.track_id])

  useEffect(() => {
    if (data.is_playing) return
    const next = clampProgress(data.progress_ms)
    startRef.current = Date.now() - next
    setProgress(next)
  }, [clampProgress, data.is_playing, data.progress_ms])

  const shouldAnimate = shouldAnimateNowPlaying(
    isTest,
    data.is_playing,
    prefersReduce,
    reduced,
    duration
  )

  useEffect(() => {
    if (!shouldAnimate) {
      return
    }
    const loop = () => {
      const elapsed = Date.now() - startRef.current
      setProgress(clampProgress(elapsed))
      rafRef.current = requestAnimationFrame(loop)
    }
    rafRef.current = requestAnimationFrame(loop)
    return () => {
      cancelAnimationFrame(rafRef.current!)
      rafRef.current = null
    }
  }, [clampProgress, shouldAnimate])

  const pct = duration > 0 ? Math.max(0, Math.min(100, (progress / duration) * 100)) : 0
  const fmt = getNowPlayingTrackTime

  const handleImageLoad = useCallback(() => {
    setImageLoaded(true)
    setImageError(false)
  }, [])

  const handleImageError = useCallback(() => {
    setImageError(true)
    setImageLoaded(true)
  }, [])

  const href = data.track_url || "https://open.spotify.com"

  const maxTimeWidth = useMemo(() => {
    const maxTimeStr = getNowPlayingTrackTime(duration)
    const fullFormat = `${maxTimeStr} / ${maxTimeStr}`
    return `${fullFormat.length * 0.6}ch`
  }, [duration])

  useEffect(() => {
    if (!data.album_image_url) {
      setImageLoaded(true)
      return
    }

    const img = new Image()
    img.src = data.album_image_url

    if (img.complete) {
      setImageLoaded(true)
      setImageError(false)
    }
  }, [data.album_image_url])

  const progressBarTransition = useMemo(() => {
    return getNowPlayingProgressTransition(shouldAnimate, prefersReduce, reduced)
  }, [shouldAnimate, prefersReduce, reduced])

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={
        data.track_name
          ? t("profile:nowPlaying.openSpotifyWithTrack", { track: data.track_name })
          : t("profile:nowPlaying.openSpotify")
      }
      className="block w-full no-underline"
    >
      <m.div
        className={cn(
          "nowplaying--spotify card-glass card-glass-interactive w-full grid items-center gap-x-4 gap-y-2 px-4 py-3.5 rounded-2xl relative overflow-hidden"
        )}
        style={{ gridTemplateColumns: "auto 1fr" }}
        initial={getNowPlayingInitial(isTest, prefersReduce, reduced)}
        animate={{ y: 0, opacity: 1, scale: 1 }}
        whileHover={prefersReduce || reduced ? {} : { y: -1, scale: 1.002 }}
        whileTap={prefersReduce || reduced ? {} : { scale: 0.997 }}
        transition={getNowPlayingTransition(isTest)}
      >
        <div className="absolute inset-0 z-base bg-linear-to-t from-black/(--opacity-hover) via-black/(--opacity-dim) to-transparent pointer-events-none" />
        <div className="relative w-14 h-14 rounded-lg overflow-hidden shadow-premium">
          {shouldUseNowPlayingImage(data.album_image_url, imageError) ? (
            <img
              src={data.album_image_url}
              alt={data.album_name || data.track_name || t("profile:nowPlaying.albumFallback")}
              loading="eager"
              decoding="async"
              referrerPolicy="no-referrer"
              onLoad={handleImageLoad}
              onError={handleImageError}
              className={cn(
                "w-full h-full rounded-lg object-cover transition-opacity duration-base",
                isNowPlayingImageVisible(imageLoaded, data.album_image_url, imageError)
                  ? "opacity-100"
                  : "opacity-0"
              )}
              style={
                shouldUseNowPlayingImageHover(prefersReduce, reduced)
                  ? {
                      transform: "scale(1.012)",
                      transition:
                        "transform var(--motion-duration-lazy) cubic-bezier(0.22, 0.61, 0.36, 1)",
                    }
                  : undefined
              }
              onMouseEnter={(e) => {
                if (shouldUseNowPlayingImageHover(prefersReduce, reduced)) {
                  e.currentTarget.style.transform = "scale(1.02)"
                }
              }}
              onMouseLeave={(e) => {
                if (shouldUseNowPlayingImageHover(prefersReduce, reduced)) {
                  e.currentTarget.style.transform = "scale(1.012)"
                }
              }}
            />
          ) : (
            <div className="w-full h-full rounded-lg bg-(--bg-surface-hover)/(--opacity-medium) flex items-center justify-center">
              <span className="text-text-tertiary text-xs">♪</span>
            </div>
          )}
        </div>
        <div className="min-w-0 flex flex-col gap-1.5 relative z-deep" aria-live="polite">
          <h3
            className={`np-title font-bold leading-tight tracking-tight text-text-primary text-base transition-opacity duration-fast ${
              isNowPlayingImageVisible(imageLoaded, data.album_image_url, imageError)
                ? "opacity-100"
                : "opacity-0"
            }`}
          >
            {data.track_name || "—"}
          </h3>
          <p className="np-art text-sm text-(--text-secondary) opacity-strong truncate">
            {data.artists.join(", ")}
          </p>
          {!data.is_playing && (
            <span
              className="inline-flex self-start px-2 py-0.5 text-label-xs font-bold uppercase bg-(--bg-surface-hover)/(--opacity-hover) text-(--text-secondary) rounded-full border border-glass-border"
              aria-hidden
            >
              {t("profile:nowPlaying.paused")}
            </span>
          )}
          <div className="flex items-center gap-2 w-full mt-0.5">
            <div className="flex-1 min-w-0 h-1.5 bg-(--bg-surface-hover)/(--opacity-hover) rounded-full overflow-hidden relative">
              <div
                role="progressbar"
                aria-valuenow={progress}
                aria-valuemin={0}
                aria-valuemax={duration}
                aria-label={t("profile:nowPlaying.progress")}
                className="h-full bg-brand rounded-full origin-left will-change-transform shadow-glow-primary"
                style={{
                  transform: `scaleX(${pct / 100})`,
                  transition: progressBarTransition,
                }}
              />
            </div>
            <span
              className="np-time text-xs text-text-tertiary whitespace-nowrap tabular-nums shrink-0"
              style={{ width: maxTimeWidth }}
            >
              {fmt(progress)} / {fmt(duration)}
            </span>
          </div>
        </div>
      </m.div>
    </a>
  )
})

export default NowPlayingCard
