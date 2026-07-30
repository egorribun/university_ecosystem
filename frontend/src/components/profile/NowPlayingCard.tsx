import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react"
import { m } from "framer-motion"
import { useTranslation } from "react-i18next"
import { motion as motionTokens } from "@/theme/tokens"
import { cn } from "@/utils/cn"
import useMediaQuery from "@/hooks/useMediaQuery"
import type { NowPlaying } from "@/types/spotify"

const isTest = typeof import.meta !== "undefined" && import.meta.env.MODE === "test"

export const NowPlayingCard = memo(function NowPlayingCard({ data }: { data: NowPlaying }) {
  const prefersReduce = useMediaQuery("(prefers-reduced-motion: reduce)")
  const reduced = useMediaQuery("(prefers-reduced-motion: reduce)")
  const duration = data.duration_ms ?? 0
  const { t } = useTranslation(["profile"])
  const [imageLoaded, setImageLoaded] = useState(false)
  const [imageError, setImageError] = useState(false)

  const clampProgress = useCallback(
    (value: number | null | undefined) => {
      if (value == null) return 0
      if (!Number.isFinite(value)) return 0
      if (!duration || duration <= 0) return Math.max(0, value)
      return Math.min(Math.max(0, value), duration)
    },
    [duration]
  )

  const initialProgress = clampProgress(data.progress_ms)
  const [progress, setProgress] = useState<number>(() => initialProgress)
  const startRef = useRef<number>(Date.now() - initialProgress)
  const rafRef = useRef<number | null>(null)
  const prevTrackIdRef = useRef<string | null>(data.track_id ?? null)
  const prevProgressRef = useRef<number>(initialProgress)
  const prevIsPlayingRef = useRef<boolean>(data.is_playing)

  useEffect(() => {
    const next = clampProgress(data.progress_ms)
    const trackChanged = (data.track_id ?? null) !== prevTrackIdRef.current
    const progressChanged = next !== prevProgressRef.current
    const resumed = data.is_playing && !prevIsPlayingRef.current

    if (trackChanged) {
      prevTrackIdRef.current = data.track_id ?? null
      setImageLoaded(false)
      setImageError(false)
    }

    if (progressChanged) {
      prevProgressRef.current = next
    }

    if (trackChanged || progressChanged || resumed) {
      startRef.current = Date.now() - next
      setProgress(next)
    }

    prevIsPlayingRef.current = data.is_playing
  }, [clampProgress, data.is_playing, data.progress_ms, data.track_id])

  useEffect(() => {
    if (data.is_playing) return
    const next = clampProgress(data.progress_ms)
    startRef.current = Date.now() - next
    setProgress((prev) => (prev === next ? prev : next))
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
  }, [clampProgress, data.is_playing, data.progress_ms])

  const shouldAnimate = !isTest && data.is_playing && !prefersReduce && !reduced && duration > 0

  useEffect(() => {
    if (!shouldAnimate) {
      if (rafRef.current != null) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
      return
    }
    const loop = () => {
      const elapsed = Date.now() - startRef.current
      setProgress(clampProgress(elapsed))
      rafRef.current = requestAnimationFrame(loop)
    }
    rafRef.current = requestAnimationFrame(loop)
    return () => {
      if (rafRef.current != null) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
    }
  }, [clampProgress, shouldAnimate])

  const pct = duration > 0 ? Math.max(0, Math.min(100, (progress / duration) * 100)) : 0
  const fmt = (ms: number | null | undefined) => {
    if (ms == null) return "0:00"
    const seconds = Math.max(0, Math.floor(ms / 1000))
    const minutes = Math.floor(seconds / 60)
    const rest = String(seconds % 60).padStart(2, "0")
    return `${minutes}:${rest}`
  }

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
    const fmtTime = (ms: number | null | undefined) => {
      if (ms == null) return "0:00"
      const seconds = Math.max(0, Math.floor(ms / 1000))
      const minutes = Math.floor(seconds / 60)
      const rest = String(seconds % 60).padStart(2, "0")
      return `${minutes}:${rest}`
    }
    const maxTimeStr = fmtTime(duration)
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
    if (shouldAnimate && !prefersReduce && !reduced) {
      return `transform ${motionTokens.durationInstant}s linear`
    }
    return `transform ${motionTokens.durationFast}s ease-out`
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
        initial={
          isTest || prefersReduce || reduced
            ? false
            : { y: motionTokens.slideSm, opacity: 0.8, scale: 1 }
        }
        animate={{ y: 0, opacity: 1, scale: 1 }}
        whileHover={prefersReduce || reduced ? {} : { y: -1, scale: 1.002 }}
        whileTap={prefersReduce || reduced ? {} : { scale: 0.997 }}
        transition={
          isTest ? { duration: 0 } : { type: "spring", stiffness: 520, damping: 36, mass: 0.9 }
        }
      >
        <div className="absolute inset-0 z-base bg-linear-to-t from-black/(--opacity-hover) via-black/(--opacity-dim) to-transparent pointer-events-none" />
        <div className="relative w-14 h-14 rounded-lg overflow-hidden shadow-premium">
          {data.album_image_url && !imageError ? (
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
                imageLoaded ? "opacity-100" : "opacity-0"
              )}
              style={
                prefersReduce || reduced
                  ? undefined
                  : {
                      transform: "scale(1.012)",
                      transition:
                        "transform var(--duration-lazy) cubic-bezier(0.22, 0.61, 0.36, 1)",
                    }
              }
              onMouseEnter={(e) => {
                if (!prefersReduce && !reduced) {
                  e.currentTarget.style.transform = "scale(1.02)"
                }
              }}
              onMouseLeave={(e) => {
                if (!prefersReduce && !reduced) {
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
              imageLoaded || !data.album_image_url || imageError ? "opacity-100" : "opacity-0"
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
