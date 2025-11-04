import { useAuth, currentUserQueryKey } from "../contexts/AuthContext"
import React, { useEffect, useMemo, useState, useRef, useCallback, memo } from "react"
import { useLocation, useNavigate } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import api from "../api/client"
import type { User } from "@/types/User"
import profileBg from "../assets/background.jpg"
import guuLogo from "../assets/guu_logo.png"
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"
const DEFAULT_AVATAR = AVATAR_PLACEHOLDER_URL
import PageFadeIn from "../components/PageFadeIn"
import { motion, useReducedMotion } from "framer-motion"
import { nowPlayingQueryKey, useNowPlaying } from "@/hooks/useNowPlaying"
import type { NowPlaying } from "@/types/spotify"
import { addVersionParam, resolveMediaUrl } from "@/utils/media"
import { useTranslation } from "react-i18next"
import { QRCodeSVG } from "qrcode.react"

const isTest = typeof import.meta !== "undefined" && import.meta.env.MODE === "test"

type SnackKey = "spotifyConnected" | "spotifyError" | "copied" | "profileUpdated" | "error"

type SnackState = {
  key?: SnackKey
  message?: string
  sev?: "success" | "info" | "warning" | "error"
}

// Icon Components (inline SVG)
const EmailIcon = ({ className = "w-5 h-5" }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
    />
  </svg>
)

const TelegramIcon = ({ className = "w-5 h-5" }: { className?: string }) => (
  <svg className={className} fill="currentColor" viewBox="0 0 24 24">
    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69a.2.2 0 00-.05-.18c-.06-.05-.14-.03-.21-.02-.09.02-1.49.95-4.22 2.79-.4.27-.76.41-1.08.4-.36-.01-1.04-.2-1.55-.37-.63-.2-1.12-.31-1.08-.66.02-.18.27-.36.74-.55 2.92-1.27 4.86-2.11 5.83-2.51 2.78-1.16 3.35-1.36 3.73-1.36.08 0 .27.02.39.12.1.08.13.19.14.27-.01.06.01.24 0 .38z" />
  </svg>
)

const ContentCopyIcon = ({ className = "w-5 h-5" }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
    />
  </svg>
)

const ExpandMoreIcon = ({ className = "w-6 h-6" }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
  </svg>
)

const CloseIcon = ({ className = "w-6 h-6" }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
  </svg>
)

const CheckIcon = ({ className = "w-6 h-6" }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
  </svg>
)

const AlertCircleIcon = ({ className = "w-6 h-6" }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
    />
  </svg>
)

const InfoIcon = ({ className = "w-6 h-6" }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
    />
  </svg>
)

export const NowPlayingCard = memo(function NowPlayingCard({ data }: { data: NowPlaying }) {
  const { t } = useTranslation(["profile"])
  const prefersReduce =
    typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches
  const reduced = useReducedMotion()
  const duration = data.duration_ms ?? 0

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

  const href = data.track_url || "https://open.spotify.com"

  return (
    <motion.a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={
        data.track_name
          ? t("profile:nowPlaying.openSpotifyWithTrack", { track: data.track_name })
          : t("profile:nowPlaying.openSpotify")
      }
      className="block w-full no-underline group"
      initial={isTest || prefersReduce || reduced ? false : { y: 12, opacity: 0.94, scale: 1 }}
      animate={{ y: 0, opacity: 1, scale: 1 }}
      whileHover={prefersReduce || reduced ? {} : { y: -1, scale: 1.002 }}
      whileTap={prefersReduce || reduced ? {} : { scale: 0.997 }}
      transition={
        isTest ? { duration: 0 } : { type: "spring", stiffness: 520, damping: 36, mass: 0.9 }
      }
    >
      <div className="relative w-full grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2 px-4 py-4 rounded-3xl overflow-hidden border border-white/10 dark:border-white/[0.14] backdrop-blur-xl bg-gradient-to-br from-white/[0.08] via-white/[0.04] to-white/[0.02] dark:from-white/[0.06] dark:via-white/[0.03] dark:to-white/[0.01] shadow-[0_8px_32px_rgba(0,0,0,0.12)] dark:shadow-[0_8px_32px_rgba(0,0,0,0.3)] transition-all duration-300 hover:shadow-[0_12px_40px_rgba(0,0,0,0.16)] dark:hover:shadow-[0_12px_40px_rgba(0,0,0,0.4)]">
        {/* Album Art */}
        <div className="relative w-14 h-14 rounded-2xl overflow-hidden shadow-[0_8px_20px_rgba(0,0,0,0.25)] dark:shadow-[0_8px_20px_rgba(0,0,0,0.45)]">
          <img
            src={data.album_image_url ?? ""}
            alt={data.album_name || data.track_name || t("profile:nowPlaying.albumFallback")}
            loading="lazy"
            decoding="async"
            referrerPolicy="no-referrer"
            className="w-full h-full object-cover rounded-2xl transform scale-[1.012] transition-transform duration-700 ease-out group-hover:scale-[1.02]"
          />
        </div>

        {/* Track Info */}
        <div className="min-w-0 flex flex-col gap-2" aria-live="polite">
          <h3 className="text-base font-extrabold leading-tight tracking-tight text-white dark:text-white line-clamp-1">
            {data.track_name || "—"}
          </h3>
          <p className="text-sm opacity-90 text-white dark:text-white/90 line-clamp-1">
            {data.artists.join(", ")}
          </p>
          {!data.is_playing && (
            <span className="self-start px-3 py-1 text-xs font-bold uppercase rounded-full bg-white/20 dark:bg-white/10 text-white dark:text-white/90 backdrop-blur-sm">
              {t("profile:nowPlaying.paused")}
            </span>
          )}

          {/* Progress Bar */}
          <div className="flex items-center gap-2 w-full">
            <div className="flex-1 h-1.5 bg-white/20 dark:bg-white/10 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-green-400 to-green-300 dark:from-green-500 dark:to-green-400 rounded-full transition-all duration-200"
                style={{ width: `${pct}%` }}
                aria-label={t("profile:nowPlaying.progress")}
              />
            </div>
            <span className="text-xs text-white/70 dark:text-white/60 whitespace-nowrap tabular-nums">
              {fmt(progress)} / {fmt(duration)}
            </span>
          </div>
        </div>
      </div>
    </motion.a>
  )
})

const DetailRow = ({ label, value }: { label: string; value?: React.ReactNode }) => {
  if (value == null || value === "") return null
  return (
    <div className="relative grid grid-cols-[14px_1fr] items-center gap-3 px-3 py-3 min-h-[44px] rounded-2xl border border-white/10 dark:border-white/[0.12] backdrop-blur-md bg-gradient-to-br from-white/[0.06] via-white/[0.03] to-white/[0.02] dark:from-white/[0.04] dark:via-white/[0.02] dark:to-white/[0.01]">
      {/* Dot Indicator */}
      <div className="w-2 h-2 rounded-full bg-blue-400 dark:bg-blue-500 shadow-[0_0_0_3px_rgba(59,130,246,0.22)] justify-self-center" />

      {/* Content */}
      <p className="text-sm leading-tight text-gray-900 dark:text-gray-100">
        <span className="font-bold">{label}:</span> {value}
      </p>
    </div>
  )
}

export default function Profile() {
  const { user, loading, setUser } = useAuth()
  const [snack, setSnack] = useState<SnackState | null>(null)
  const [avatarVersion, setAvatarVersion] = useState(Date.now())
  const [coverVersion, setCoverVersion] = useState(Date.now())
  const isMobile = typeof window !== "undefined" && window.innerWidth <= 640
  const isTwoCol = typeof window !== "undefined" && window.innerWidth >= 1400
  const reduced = useReducedMotion()
  const { t } = useTranslation(["profile", "common"])
  const [scrollY, setScrollY] = useState(0)
  const [qrOpen, setQrOpen] = useState(false)
  const [achOpen, setAchOpen] = useState<{
    name: string
    issuer?: string
    date?: string
    url?: string
  } | null>(null)
  const [accordionOpen, setAccordionOpen] = useState(true)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const confettiRef = useRef<HTMLCanvasElement | null>(null)
  const ldJsonRef = useRef<HTMLScriptElement | null>(null)
  const queryClient = useQueryClient()
  const spotifyConnected = Boolean(user?.spotify_connected || user?.spotify_is_connected)
  const nowPlayingQuery = useNowPlaying(spotifyConnected)
  const { refetch: refetchNowPlaying } = nowPlayingQuery
  const nowPlaying = nowPlayingQuery.data ?? null
  const prevSpotifyConnectedRef = useRef(spotifyConnected)
  const showNowPlaying = Boolean(
    spotifyConnected &&
      nowPlaying &&
      (nowPlaying.track_id || nowPlaying.track_name || nowPlaying.artists.length > 0)
  )
  const location = useLocation()
  const navigate = useNavigate()

  const [edit, setEdit] = useState(false)
  const [fullName, setFullName] = useState(user?.full_name || "")
  const [email, setEmail] = useState(user?.email || "")
  const [about, setAbout] = useState(user?.about || "")
  const [recordBookNumber, setRecordBookNumber] = useState(user?.record_book_number || "")
  const [status, setStatus] = useState(user?.status || "")
  const [institute, setInstitute] = useState(user?.institute || "")
  const [course, setCourse] = useState(user?.course || "")
  const [educationLevel, setEducationLevel] = useState(user?.education_level || "")
  const [track, setTrack] = useState(user?.track || "")
  const [program, setProgram] = useState(user?.program || "")
  const [telegram, setTelegram] = useState(user?.telegram || "")
  const [achievements, setAchievements] = useState(user?.achievements || "")
  const [department, setDepartment] = useState(user?.department || "")
  const [position, setPosition] = useState(user?.position || "")
  const [saving, setSaving] = useState(false)

  const initEditFields = useCallback(() => {
    setFullName(user?.full_name || "")
    setEmail(user?.email || "")
    setAbout(user?.about || "")
    setRecordBookNumber(user?.record_book_number || "")
    setStatus(user?.status || "")
    setInstitute(user?.institute || "")
    setCourse(user?.course || "")
    setEducationLevel(user?.education_level || "")
    setTrack(user?.track || "")
    setProgram(user?.program || "")
    setTelegram(user?.telegram || "")
    setAchievements(user?.achievements || "")
    setDepartment(user?.department || "")
    setPosition(user?.position || "")
  }, [user])

  useEffect(() => {
    const sp = new URLSearchParams(location.search)
    const wantsEdit = sp.get("edit") === "1" || location.pathname.endsWith("/edit")
    if (wantsEdit && !edit) {
      initEditFields()
      setEdit(true)
    }
    if (!wantsEdit && edit) setEdit(false)
  }, [location.pathname, location.search, edit, initEditFields])

  useEffect(() => {
    const onScroll = () => setScrollY(window.scrollY || 0)
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [])

  const coverParallax = reduced ? 0 : Math.min(scrollY * 0.1, 40)
  const coverScale = reduced ? 1 : Math.min(1 + scrollY * 0.00014, 1.04)

  useEffect(() => {
    const sp = new URLSearchParams(window.location.search)
    const s = sp.get("spotify")
    if (s !== null) {
      if (s !== "error") {
        void queryClient.invalidateQueries({ queryKey: currentUserQueryKey })
        void queryClient.invalidateQueries({ queryKey: nowPlayingQueryKey })
        void refetchNowPlaying({ throwOnError: false })
        setSnack({ key: "spotifyConnected", sev: "success" })
      } else {
        setSnack({ key: "spotifyError", sev: "error" })
      }
      sp.delete("spotify")
      const next = window.location.pathname + (sp.toString() ? "?" + sp : "")
      window.history.replaceState({}, "", next)
    }
  }, [queryClient, refetchNowPlaying])

  useEffect(() => {
    if (spotifyConnected && !prevSpotifyConnectedRef.current) {
      void refetchNowPlaying({ throwOnError: false })
    }
    prevSpotifyConnectedRef.current = spotifyConnected
  }, [spotifyConnected, refetchNowPlaying])

  useEffect(() => {
    if (!user) return
    const elPrev = ldJsonRef.current
    if (elPrev && elPrev.parentNode) elPrev.parentNode.removeChild(elPrev)
    const el = document.createElement("script")
    el.type = "application/ld+json"
    el.setAttribute("data-profile-ldjson", "1")
    el.text = JSON.stringify({
      "@context": "https://schema.org",
      "@type": "Person",
      name: user.full_name || "",
      email: user.email || "",
      jobTitle:
        user.role === "teacher"
          ? user.position || ""
          : user.role === "student"
            ? "Student"
            : "Administrator",
      affiliation: user.institute || user.department || "",
      url: typeof window !== "undefined" ? window.location.href : "",
      image: (() => {
        const media = resolveMediaUrl(user.avatar_url ?? undefined)
        return media ? addVersionParam(media, avatarVersion) : ""
      })(),
    })
    document.head.appendChild(el)
    ldJsonRef.current = el
    return () => {
      const node = ldJsonRef.current
      if (node && node.parentNode) node.parentNode.removeChild(node)
      ldJsonRef.current = null
    }
  }, [user, avatarVersion])

  if (loading)
    return (
      <div className="min-h-[70vh] flex items-center justify-center">
        <div className="w-12 h-12 border-4 border-blue-500/30 border-t-blue-500 rounded-full animate-spin" />
      </div>
    )

  const avatarImageUrl = useMemo(() => {
    const media = resolveMediaUrl(user?.avatar_url ?? undefined)
    return media ? addVersionParam(media, avatarVersion) : DEFAULT_AVATAR
  }, [user?.avatar_url, avatarVersion])

  const coverImageUrl = useMemo(() => {
    const media = resolveMediaUrl(user?.cover_url ?? undefined)
    return media ? addVersionParam(media, coverVersion) : profileBg
  }, [user?.cover_url, coverVersion])

  const handleAvatarImgError = useCallback((event: React.SyntheticEvent<HTMLImageElement>) => {
    const img = event.currentTarget
    img.onerror = null
    img.src = DEFAULT_AVATAR
  }, [])

  const ensureConfettiSize = useCallback(() => {
    const canvas = confettiRef.current
    if (!canvas) return { dpr: 1, w: window.innerWidth, h: window.innerHeight }
    const dpr = Math.max(1, window.devicePixelRatio || 1)
    const w = Math.max(1, window.innerWidth)
    const h = Math.max(1, window.innerHeight)
    canvas.style.width = `${w}px`
    canvas.style.height = `${h}px`
    canvas.width = Math.floor(w * dpr)
    canvas.height = Math.floor(h * dpr)
    return { dpr, w, h }
  }, [])

  useEffect(() => {
    const onResize = () => ensureConfettiSize()
    ensureConfettiSize()
    window.addEventListener("resize", onResize)
    window.addEventListener("orientationchange", onResize)
    return () => {
      window.removeEventListener("resize", onResize)
      window.removeEventListener("orientationchange", onResize)
    }
  }, [ensureConfettiSize])

  const burstConfetti = useCallback(
    (x?: number, y?: number) => {
      const canvas = confettiRef.current
      if (!canvas) return
      const ctx = canvas.getContext("2d")
      if (!ctx) return
      const { dpr, w, h } = ensureConfettiSize()
      const cx = x != null ? x * dpr : (w * dpr) / 2
      const cy = y != null ? y * dpr : (h * dpr) / 5
      const count = 120
      const parts = Array.from({ length: count }).map((_, i) => {
        const angle = Math.random() * Math.PI - Math.PI / 2
        const speed = 3 + Math.random() * 6
        const hue = Math.floor((i / count) * 360)
        return {
          x: cx,
          y: cy,
          vx: Math.cos(angle) * speed,
          vy: Math.sin(angle) * speed - 2,
          life: 56 + Math.random() * 36,
          size: 2 + Math.random() * 3,
          color: `hsl(${hue} 90% 55%)`,
        }
      })
      let raf = 0
      const step = () => {
        const context = ctx
        context.clearRect(0, 0, canvas.width, canvas.height)
        parts.forEach((p) => {
          p.vy += 0.12 * dpr
          p.x += p.vx * dpr
          p.y += p.vy * dpr
          p.life -= 1
          context.fillStyle = p.color
          context.beginPath()
          context.arc(p.x, p.y, p.size * dpr, 0, Math.PI * 2)
          context.fill()
        })
        for (let i = parts.length - 1; i >= 0; i--) if (parts[i].life <= 0) parts.splice(i, 1)
        if (parts.length > 0) raf = requestAnimationFrame(step)
        else cancelAnimationFrame(raf)
      }
      step()
    },
    [ensureConfettiSize]
  )

  useEffect(() => {
    if (snack && snack.sev === "success" && snack.key !== "copied") burstConfetti()
  }, [snack, burstConfetti])

  const copy = async (text: string, evt?: { clientX: number; clientY: number }) => {
    try {
      await navigator.clipboard?.writeText(text)
    } finally {
      setSnack({ key: "copied", sev: "success" })
      if (evt) burstConfetti(evt.clientX, evt.clientY)
    }
  }

  const buildVCard = useCallback(() => {
    const u = user!
    const lines = [
      "BEGIN:VCARD",
      "VERSION:4.0",
      `FN:${u.full_name || ""}`,
      u.email ? `EMAIL:${u.email}` : "",
      u.institute || u.department ? `ORG:${u.institute || u.department}` : "",
      u.position || u.status ? `TITLE:${u.position || u.status}` : "",
      typeof window !== "undefined" ? `URL:${window.location.href}` : "",
    ].filter(Boolean)
    lines.push("END:VCARD")
    return lines.join("\r\n")
  }, [user])

  const openQrModal = useCallback(() => setQrOpen(true), [])
  const closeQrModal = useCallback(() => setQrOpen(false), [])

  const telegramHref = useMemo(() => {
    const t = user?.telegram || ""
    if (!t) return ""
    let v = String(t).trim()
    if (v.startsWith("http")) return v
    if (v.startsWith("@")) v = v.slice(1)
    return `https://t.me/${v}`
  }, [user?.telegram])

  const achievementsList = useMemo(
    () =>
      String(user?.achievements || "")
        .split(/[,;\n]/)
        .map((str) => String(str || "").trim())
        .filter(Boolean)
        .map((raw, index) => {
          const [name, issuer, date, url] = raw.split("|").map((s) => s.trim())
          return { key: `${raw}-${index}`, name, issuer, date, url }
        }),
    [user?.achievements]
  )

  const avatarPx = useMemo(() => {
    if (isMobile) return 132
    return isTwoCol ? 188 : 168
  }, [isMobile, isTwoCol])

  const avatarSize = `${avatarPx}px`
  const avatarFloat = Math.round(avatarPx * 0.55)
  const heroPaddingBottom = `${Math.max(avatarFloat - 12, 28)}px`
  const heroTextPaddingTop = `${Math.round(avatarPx * 0.65)}px`
  const isOnline = ((user as any)?.is_online ?? (user as any)?.online ?? true) as boolean
  const statusSize = useMemo(() => Math.max(12, Math.round(avatarPx * 0.16)), [avatarPx])
  const statusOffset = useMemo(() => Math.max(6, Math.round(avatarPx * 0.08)), [avatarPx])

  const handleSave = async () => {
    setSaving(true)
    try {
      const res = await api.put<User>("/users/me", {
        full_name: fullName,
        email,
        about,
        record_book_number: recordBookNumber,
        status,
        institute,
        course,
        education_level: educationLevel,
        track,
        program,
        telegram,
        achievements,
        department,
        position,
      })
      setUser(res.data)
      setEdit(false)
      navigate("/profile", { replace: true })
      setSnack({ key: "profileUpdated", sev: "success" })
      setAvatarVersion(Date.now())
      setCoverVersion(Date.now())
    } catch (e: any) {
      let messageKey: SnackKey | undefined = "error"
      let messageText: string | undefined
      if (e?.response?.data?.detail) {
        if (typeof e.response.data.detail === "string") {
          messageKey = undefined
          messageText = e.response.data.detail
        } else if (Array.isArray(e.response.data.detail)) {
          messageKey = undefined
          messageText = e.response.data.detail.map((err: any) => err.msg).join("; ")
        }
      }
      setSnack({ key: messageKey, message: messageText, sev: "error" })
    } finally {
      setSaving(false)
    }
  }

  const handleCancel = () => {
    setEdit(false)
    navigate("/profile", { replace: true })
  }

  const snackMessage = snack?.key ? t(`profile:snackbar.${snack.key}`) : snack?.message || ""

  return (
    <>
      {/* Fixed Background */}
      <div
        className="fixed inset-0 -z-10 bg-cover bg-center bg-fixed"
        style={{ backgroundImage: `url(${profileBg})` }}
      >
        <div className="absolute inset-0 bg-gradient-to-br from-blue-900/70 via-purple-900/60 to-blue-800/70 mix-blend-multiply" />
        <div className="absolute inset-0 bg-radial-gradient opacity-60" />
      </div>

      <PageFadeIn>
        <motion.div
          initial={isTest ? false : { opacity: reduced ? 1 : 0.96, y: reduced ? 0 : 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={isTest ? { duration: 0 } : { type: "spring", stiffness: 460, damping: 34 }}
        >
          <main
            id="main"
            className="profile-page relative min-h-screen flex flex-col py-8 sm:py-9 md:py-10 px-3 sm:px-4 md:px-6"
            data-testid="profile-root"
            aria-label={t("profile:aria.page")}
          >
            <div className="container mx-auto max-w-7xl relative z-0">
              <motion.div
                ref={containerRef}
                className="relative overflow-hidden rounded-3xl md:rounded-[2rem] px-5 sm:px-7 md:px-9 lg:px-11 py-7 sm:py-8 md:py-10 backdrop-blur-xl bg-gradient-to-br from-white/[0.08] via-white/[0.05] to-white/[0.03] dark:from-white/[0.06] dark:via-white/[0.04] dark:to-white/[0.02] border border-white/10 dark:border-white/[0.12] shadow-[0_24px_80px_rgba(0,0,0,0.25)] dark:shadow-[0_24px_80px_rgba(0,0,0,0.5)]"
                initial={
                  isTest ? false : { opacity: reduced ? 1 : 0.98, y: reduced ? 0 : 10, scale: 1 }
                }
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={
                  isTest
                    ? { duration: 0 }
                    : { type: "spring", stiffness: 520, damping: 34, mass: 0.9 }
                }
              >
                {/* Main Grid Layout */}
                <div className="grid grid-cols-1 md:grid-cols-[minmax(360px,420px)_minmax(0,1fr)] gap-8 md:gap-10 lg:gap-12 items-start">
                  {/* Left Column - Hero + Contacts + NowPlaying */}
                  <div className="flex flex-col gap-6 md:gap-8">
                    {/* Hero Card with Avatar & Cover */}
                    <div
                      className="relative rounded-3xl md:rounded-[2rem] overflow-hidden min-h-[300px] sm:min-h-[340px] md:min-h-[360px] lg:min-h-[400px] flex items-end justify-center backdrop-blur-md bg-gradient-to-br from-white/[0.06] via-white/[0.03] to-white/[0.02] dark:from-white/[0.04] dark:via-white/[0.02] dark:to-white/[0.01] shadow-[0_28px_70px_rgba(0,0,0,0.3)] dark:shadow-[0_28px_70px_rgba(0,0,0,0.58)] border border-white/10 dark:border-white/[0.12]"
                      style={{ paddingBottom: heroPaddingBottom }}
                    >
                      {/* Cover Image with Parallax */}
                      <div
                        className="absolute inset-0 bg-cover bg-center transition-transform duration-1000 ease-out"
                        style={{
                          backgroundImage: coverImageUrl ? `url(${coverImageUrl})` : undefined,
                          transform: `translateY(${coverParallax}px) scale(${coverScale})`,
                          filter: "saturate(1) contrast(1.02) brightness(0.98)",
                        }}
                      />

                      {/* Cover Gradient Overlay */}
                      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent via-40% to-black/90" />

                      {/* Avatar Container */}
                      <div
                        className="absolute left-1/2 top-6 sm:top-7 -translate-x-1/2 flex items-center justify-center p-1 rounded-full"
                        style={{
                          width: avatarSize,
                          height: avatarSize,
                          animation: reduced ? "none" : "pulse-ring 14s ease-in-out infinite",
                        }}
                      >
                        {/* Avatar with Gradient Ring */}
                        <div className="relative w-full h-full rounded-full overflow-hidden bg-gradient-to-br from-blue-400 via-purple-500 to-blue-600 p-1.5 shadow-[0_10px_28px_rgba(0,0,0,0.3),0_0_0_2px_rgba(255,255,255,0.6)]">
                          <div className="w-full h-full rounded-full overflow-hidden bg-gray-800">
                            <img
                              src={avatarImageUrl}
                              alt={user?.full_name ?? undefined}
                              onError={handleAvatarImgError}
                              loading="lazy"
                              decoding="async"
                              referrerPolicy="no-referrer"
                              className="w-full h-full object-cover"
                            />
                          </div>

                          {/* Inner Ring Shine */}
                          <div className="absolute inset-0 rounded-full shadow-[inset_0_1px_0_rgba(255,255,255,0.6),inset_0_0_0_1px_rgba(255,255,255,0.3)] pointer-events-none" />
                        </div>

                        {/* Online Status Indicator */}
                        {isOnline && (
                          <div
                            className="absolute rounded-full bg-green-500 shadow-[0_0_0_2px_rgba(0,0,0,0.18),0_4px_10px_rgba(34,197,94,0.45)] z-10"
                            style={{
                              right: `${statusOffset}px`,
                              bottom: `${statusOffset}px`,
                              width: `${statusSize}px`,
                              height: `${statusSize}px`,
                            }}
                          >
                            {!reduced && (
                              <div
                                className="absolute -inset-1.5 rounded-full border-2 border-green-500/45 animate-ping"
                                style={{ animationDuration: "1.8s" }}
                              />
                            )}
                          </div>
                        )}
                      </div>

                      {/* Name & Info Section */}
                      <div
                        className="relative z-10 w-full text-center md:text-left px-5 sm:px-6 md:px-7 flex flex-col gap-5"
                        style={{ paddingTop: heroTextPaddingTop }}
                      >
                        <div>
                          <h1
                            className="text-3xl sm:text-4xl lg:text-5xl font-black leading-tight text-white dark:text-white"
                            data-testid="profile-name"
                            style={{ fontSize: "clamp(1.7rem, 3.2vw, 2.9rem)" }}
                          >
                            {user!.full_name}
                          </h1>
                          {!!user?.position && user?.role === "teacher" && (
                            <p className="mt-2 text-lg font-semibold text-white/95 dark:text-white/90">
                              {user.position}
                            </p>
                          )}
                        </div>

                        {/* Role Chips */}
                        <div className="flex flex-row flex-wrap gap-2 justify-center md:justify-start">
                          {[
                            user!.role === "teacher"
                              ? t("profile:chips.teacher")
                              : user!.role === "student"
                                ? t("profile:chips.student")
                                : t("profile:chips.admin"),
                            ...(user!.role === "student" && user!.course
                              ? [t("profile:chips.course", { value: user!.course })]
                              : []),
                            ...(user!.institute ? [user!.institute] : []),
                          ].map((chip, idx) => (
                            <motion.span
                              key={`${chip}-${idx}`}
                              initial={isTest || reduced ? false : { opacity: 0, scale: 0.9 }}
                              animate={{ opacity: 1, scale: 1 }}
                              transition={{
                                duration: isTest || reduced ? 0 : 0.56,
                                delay: reduced ? 0 : idx * 0.09,
                              }}
                              className="inline-flex px-4 py-2 text-xs font-bold uppercase tracking-wide rounded-full bg-white/20 dark:bg-white/10 text-white dark:text-white/90 backdrop-blur-md border border-white/20 dark:border-white/10"
                              style={{
                                animation: reduced
                                  ? "none"
                                  : `border-pulse 12s ease-in-out infinite ${idx * 90}ms`,
                              }}
                            >
                              {chip}
                            </motion.span>
                          ))}
                        </div>
                      </div>
                    </div>

                    {/* Contact Card */}
                    <div className="rounded-3xl p-5 sm:p-6 flex flex-col gap-5 backdrop-blur-xl bg-gradient-to-br from-white/[0.08] via-white/[0.04] to-white/[0.02] dark:from-white/[0.06] dark:via-white/[0.03] dark:to-white/[0.01] border border-white/10 dark:border-white/[0.12] shadow-lg">
                      {/* QR Button */}
                      <button
                        onClick={openQrModal}
                        data-testid="open-qr"
                        className="w-full py-3 px-6 rounded-2xl font-extrabold tracking-wide text-white bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700 shadow-lg hover:shadow-xl transition-all duration-200 transform hover:-translate-y-0.5 active:scale-95"
                      >
                        {t("profile:buttons.showQr")}
                      </button>

                      {/* Divider */}
                      <div className="h-px bg-gradient-to-r from-transparent via-white/20 to-transparent" />

                      {/* Email */}
                      <div className="flex items-center justify-between gap-3 flex-wrap">
                        <div className="flex items-center gap-2 min-w-0 flex-1">
                          <EmailIcon className="w-5 h-5 text-gray-700 dark:text-gray-300 flex-shrink-0" />
                          <a
                            href={`mailto:${user!.email}`}
                            className="font-extrabold text-gray-900 dark:text-gray-100 hover:text-blue-600 dark:hover:text-blue-400 transition-colors break-words flex-1 no-underline"
                            data-testid="profile-email-link"
                            title={t("profile:aria.openEmail")}
                          >
                            {user!.email}
                          </a>
                        </div>
                        <button
                          onClick={(e) => copy(user!.email, e)}
                          aria-label={t("profile:aria.copyEmail")}
                          title={t("profile:aria.copyEmail")}
                          data-testid="copy-email"
                          className="p-2 rounded-xl backdrop-blur-md bg-white/10 dark:bg-white/5 hover:bg-white/20 dark:hover:bg-white/10 border border-white/20 dark:border-white/10 transition-all duration-200 transform hover:-translate-y-0.5 hover:scale-105 active:scale-95"
                        >
                          <ContentCopyIcon className="w-4 h-4 text-gray-700 dark:text-gray-300" />
                        </button>
                      </div>

                      {/* Telegram */}
                      {!!user!.telegram && (
                        <div className="flex items-center justify-between gap-3 flex-wrap">
                          <div className="flex items-center gap-2 min-w-0 flex-1">
                            <TelegramIcon className="w-5 h-5 text-gray-700 dark:text-gray-300 flex-shrink-0" />
                            <a
                              href={telegramHref}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="font-extrabold text-gray-900 dark:text-gray-100 hover:text-blue-600 dark:hover:text-blue-400 transition-colors break-words flex-1 no-underline"
                              data-testid="profile-telegram-link"
                              title={t("profile:aria.openTelegram")}
                            >
                              {user!.telegram}
                            </a>
                          </div>
                          <button
                            onClick={(e) => copy(user!.telegram!, e)}
                            aria-label={t("profile:aria.copyTelegram")}
                            title={t("profile:aria.copyTelegram")}
                            data-testid="copy-telegram"
                            className="p-2 rounded-xl backdrop-blur-md bg-white/10 dark:bg-white/5 hover:bg-white/20 dark:hover:bg-white/10 border border-white/20 dark:border-white/10 transition-all duration-200 transform hover:-translate-y-0.5 hover:scale-105 active:scale-95"
                          >
                            <ContentCopyIcon className="w-4 h-4 text-gray-700 dark:text-gray-300" />
                          </button>
                        </div>
                      )}
                    </div>

                    {/* Now Playing Card */}
                    {showNowPlaying && nowPlaying && (
                      <motion.div
                        initial={isTest || reduced ? false : { opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: isTest || reduced ? 0 : 0.72 }}
                        className="flex flex-col gap-3"
                      >
                        <h2 className="text-xs font-bold uppercase tracking-widest text-gray-600 dark:text-gray-400">
                          {t("profile:sections.nowPlaying")}
                        </h2>
                        <NowPlayingCard data={nowPlaying} />
                      </motion.div>
                    )}
                  </div>

                  {/* Right Column - Details / Edit Form */}
                  <div
                    className="w-full relative"
                    style={{ marginTop: `${Math.round(avatarPx * 0.55) + 36}px` }}
                  >
                    {edit ? (
                      /* Edit Form */
                      <div className="w-full rounded-3xl p-5 sm:p-6 md:p-7 backdrop-blur-xl bg-gradient-to-br from-white/[0.08] via-white/[0.04] to-white/[0.02] dark:from-white/[0.06] dark:via-white/[0.03] dark:to-white/[0.01] border border-white/10 dark:border-white/[0.12] shadow-lg">
                        <div className="flex flex-col gap-4">
                          <input
                            type="text"
                            placeholder={t("profile:form.name")}
                            value={fullName}
                            onChange={(e) => setFullName(e.target.value)}
                            maxLength={120}
                            className="w-full px-4 py-3 rounded-2xl bg-white/10 dark:bg-white/5 border border-white/20 dark:border-white/10 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 backdrop-blur-sm transition-all"
                          />
                          <input
                            type="email"
                            placeholder={t("profile:form.email")}
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            className="w-full px-4 py-3 rounded-2xl bg-white/10 dark:bg-white/5 border border-white/20 dark:border-white/10 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 backdrop-blur-sm transition-all"
                          />
                          <input
                            type="text"
                            placeholder={t("profile:form.telegram")}
                            value={telegram}
                            onChange={(e) => setTelegram(e.target.value)}
                            className="w-full px-4 py-3 rounded-2xl bg-white/10 dark:bg-white/5 border border-white/20 dark:border-white/10 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 backdrop-blur-sm transition-all"
                          />
                          <p className="text-xs text-gray-600 dark:text-gray-400 -mt-2">
                            {t("profile:form.telegramHint")}
                          </p>

                          {user!.role === "teacher" && (
                            <>
                              <input
                                type="text"
                                placeholder={t("profile:form.department")}
                                value={department}
                                onChange={(e) => setDepartment(e.target.value)}
                                className="w-full px-4 py-3 rounded-2xl bg-white/10 dark:bg-white/5 border border-white/20 dark:border-white/10 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 backdrop-blur-sm transition-all"
                              />
                              <input
                                type="text"
                                placeholder={t("profile:form.position")}
                                value={position}
                                onChange={(e) => setPosition(e.target.value)}
                                className="w-full px-4 py-3 rounded-2xl bg-white/10 dark:bg-white/5 border border-white/20 dark:border-white/10 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 backdrop-blur-sm transition-all"
                              />
                            </>
                          )}

                          {user!.role === "student" && (
                            <>
                              <textarea
                                placeholder={t("profile:form.about")}
                                value={about}
                                onChange={(e) => setAbout(e.target.value)}
                                rows={3}
                                className="w-full px-4 py-3 rounded-2xl bg-white/10 dark:bg-white/5 border border-white/20 dark:border-white/10 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 backdrop-blur-sm transition-all resize-none"
                              />
                              <input
                                type="text"
                                placeholder={t("profile:form.recordBookNumber")}
                                value={recordBookNumber}
                                onChange={(e) => setRecordBookNumber(e.target.value)}
                                className="w-full px-4 py-3 rounded-2xl bg-white/10 dark:bg-white/5 border border-white/20 dark:border-white/10 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 backdrop-blur-sm transition-all"
                              />
                              <input
                                type="text"
                                placeholder={t("profile:form.status")}
                                value={status}
                                onChange={(e) => setStatus(e.target.value)}
                                className="w-full px-4 py-3 rounded-2xl bg-white/10 dark:bg-white/5 border border-white/20 dark:border-white/10 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 backdrop-blur-sm transition-all"
                              />
                              <input
                                type="text"
                                placeholder={t("profile:form.institute")}
                                value={institute}
                                onChange={(e) => setInstitute(e.target.value)}
                                className="w-full px-4 py-3 rounded-2xl bg-white/10 dark:bg-white/5 border border-white/20 dark:border-white/10 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 backdrop-blur-sm transition-all"
                              />
                              <input
                                type="text"
                                placeholder={t("profile:form.course")}
                                value={course}
                                onChange={(e) => setCourse(e.target.value)}
                                className="w-full px-4 py-3 rounded-2xl bg-white/10 dark:bg-white/5 border border-white/20 dark:border-white/10 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 backdrop-blur-sm transition-all"
                              />
                              <input
                                type="text"
                                placeholder={t("profile:form.educationLevel")}
                                value={educationLevel}
                                onChange={(e) => setEducationLevel(e.target.value)}
                                className="w-full px-4 py-3 rounded-2xl bg-white/10 dark:bg-white/5 border border-white/20 dark:border-white/10 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 backdrop-blur-sm transition-all"
                              />
                              <input
                                type="text"
                                placeholder={t("profile:form.track")}
                                value={track}
                                onChange={(e) => setTrack(e.target.value)}
                                className="w-full px-4 py-3 rounded-2xl bg-white/10 dark:bg-white/5 border border-white/20 dark:border-white/10 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 backdrop-blur-sm transition-all"
                              />
                              <input
                                type="text"
                                placeholder={t("profile:form.program")}
                                value={program}
                                onChange={(e) => setProgram(e.target.value)}
                                className="w-full px-4 py-3 rounded-2xl bg-white/10 dark:bg-white/5 border border-white/20 dark:border-white/10 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 backdrop-blur-sm transition-all"
                              />
                              <textarea
                                placeholder={t("profile:form.achievements")}
                                value={achievements}
                                onChange={(e) => setAchievements(e.target.value)}
                                rows={2}
                                className="w-full px-4 py-3 rounded-2xl bg-white/10 dark:bg-white/5 border border-white/20 dark:border-white/10 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 backdrop-blur-sm transition-all resize-none"
                              />
                            </>
                          )}

                          {/* Action Buttons */}
                          <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center pt-2">
                            <button
                              onClick={handleSave}
                              disabled={saving}
                              className="w-full sm:w-auto px-6 py-3 rounded-2xl font-extrabold text-white bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 disabled:opacity-50 disabled:cursor-not-allowed shadow-lg hover:shadow-xl transition-all duration-200 transform hover:-translate-y-0.5 active:scale-95"
                            >
                              {saving ? t("profile:form.saving") : t("profile:form.save")}
                            </button>
                            <button
                              onClick={handleCancel}
                              className="w-full sm:w-auto px-6 py-3 rounded-2xl font-extrabold text-gray-900 dark:text-gray-100 bg-white/10 dark:bg-white/5 hover:bg-white/20 dark:hover:bg-white/10 border border-white/20 dark:border-white/10 transition-all duration-200 transform hover:-translate-y-0.5 active:scale-95"
                            >
                              {t("profile:form.cancel")}
                            </button>
                          </div>
                        </div>
                      </div>
                    ) : (
                      /* Details View */
                      <div className="w-full rounded-3xl p-5 sm:p-6 md:p-7 backdrop-blur-xl bg-gradient-to-br from-white/[0.08] via-white/[0.04] to-white/[0.02] dark:from-white/[0.06] dark:via-white/[0.03] dark:to-white/[0.01] border border-white/10 dark:border-white/[0.12] shadow-lg">
                        <h2 className="text-2xl md:text-3xl font-black mb-5 text-gray-900 dark:text-gray-100 tracking-tight">
                          {t("profile:sections.details")}
                        </h2>

                        {/* Accordion */}
                        <div className="rounded-3xl overflow-hidden backdrop-blur-md bg-gradient-to-br from-white/[0.06] via-white/[0.03] to-white/[0.02] dark:from-white/[0.04] dark:via-white/[0.02] dark:to-white/[0.01] border border-white/10 dark:border-white/[0.12]">
                          {/* Accordion Header */}
                          <button
                            onClick={() => setAccordionOpen(!accordionOpen)}
                            className="w-full px-4 sm:px-5 py-4 flex items-center justify-between border-b border-white/10 dark:border-white/10 hover:bg-white/5 dark:hover:bg-white/5 transition-colors"
                          >
                            <h3 className="font-black text-gray-900 dark:text-gray-100">
                              {t("profile:sections.profileDetails")}
                            </h3>
                            <ExpandMoreIcon
                              className={`w-6 h-6 text-gray-700 dark:text-gray-300 transition-transform duration-200 ${
                                accordionOpen ? "rotate-180" : ""
                              }`}
                            />
                          </button>

                          {/* Accordion Content */}
                          {accordionOpen && (
                            <div className="px-3 sm:px-4 py-4 sm:py-5">
                              {(() => {
                                const rows = [
                                  { label: t("profile:form.about"), value: user!.about },
                                  { label: t("profile:form.status"), value: user!.status },
                                  {
                                    label: t("profile:form.recordBookNumber"),
                                    value: user!.record_book_number,
                                  },
                                  {
                                    label: t("profile:form.educationLevel"),
                                    value: user!.education_level,
                                  },
                                  { label: t("profile:form.track"), value: user!.track },
                                  { label: t("profile:form.program"), value: user!.program },
                                  { label: t("profile:form.department"), value: user!.department },
                                  { label: t("profile:form.position"), value: user!.position },
                                ]
                                return (
                                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 md:gap-4">
                                    {rows.map((r) => (
                                      <DetailRow key={r.label} label={r.label} value={r.value} />
                                    ))}
                                  </div>
                                )
                              })()}

                              {/* Achievements */}
                              {achievementsList.length > 0 && (
                                <div className="mt-6">
                                  <h3 className="text-lg font-extrabold mb-3 text-gray-900 dark:text-gray-100">
                                    {t("profile:sections.achievements")}
                                  </h3>
                                  <div className="grid grid-cols-[repeat(auto-fit,minmax(140px,1fr))] sm:grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-3">
                                    {achievementsList.map((ach, idx) => (
                                      <motion.button
                                        key={ach.key}
                                        onClick={() =>
                                          setAchOpen({
                                            name: ach.name,
                                            issuer: ach.issuer,
                                            date: ach.date,
                                            url: ach.url,
                                          })
                                        }
                                        initial={
                                          isTest || reduced ? false : { opacity: 0, scale: 0.9 }
                                        }
                                        animate={{ opacity: 1, scale: 1 }}
                                        transition={{
                                          duration: isTest || reduced ? 0 : 0.5,
                                          delay: reduced ? 0 : idx * 0.09,
                                        }}
                                        className="px-4 py-3 rounded-2xl text-sm font-bold leading-tight text-gray-900 dark:text-gray-100 backdrop-blur-md bg-gradient-to-br from-white/10 via-white/5 to-white/5 dark:from-white/8 dark:via-white/4 dark:to-white/4 border border-white/20 dark:border-white/10 hover:bg-white/20 dark:hover:bg-white/10 transition-all duration-200 transform hover:-translate-y-0.5 hover:scale-105 active:scale-95 text-left"
                                        style={{
                                          animation: reduced
                                            ? "none"
                                            : `border-pulse 14s ease-in-out infinite ${idx * 110}ms`,
                                        }}
                                      >
                                        {ach.name}
                                      </motion.button>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </motion.div>
            </div>

            {/* Confetti Canvas */}
            <canvas
              ref={confettiRef}
              className="fixed left-0 top-0 w-screen h-screen pointer-events-none"
              style={{ zIndex: 2147483000 }}
            />
          </main>
        </motion.div>
      </PageFadeIn>

      {/* QR Code Modal */}
      {qrOpen && (
        <div
          role="button"
          tabIndex={0}
          className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm cursor-pointer"
          onClick={closeQrModal}
          onKeyDown={(e) => {
            if (e.key === "Escape" || e.key === "Enter" || e.key === " ") {
              e.preventDefault()
              closeQrModal()
            }
          }}
          aria-label="Close modal"
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 20 }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            onClick={(e) => e.stopPropagation()}
            className="relative w-full max-w-md rounded-3xl overflow-hidden backdrop-blur-xl bg-gradient-to-br from-white/95 via-white/90 to-white/85 dark:from-gray-900/95 dark:via-gray-900/90 dark:to-gray-900/85 border border-white/20 dark:border-white/10 shadow-2xl"
          >
            {/* Close Button */}
            <button
              onClick={closeQrModal}
              className="absolute top-4 right-4 p-2 rounded-xl bg-white/10 dark:bg-white/5 hover:bg-white/20 dark:hover:bg-white/10 transition-colors z-10"
              aria-label="Close"
            >
              <CloseIcon className="w-5 h-5 text-gray-900 dark:text-gray-100" />
            </button>

            {/* Modal Content */}
            <div className="p-6 sm:p-8">
              <h2 className="text-2xl font-black text-center mb-6 text-gray-900 dark:text-gray-100 tracking-tight">
                {t("profile:dialog.qr.title")}
              </h2>

              <div className="flex flex-col items-center justify-center gap-3 min-h-[320px]">
                <div className="bg-white p-4 rounded-3xl border border-blue-500/15 shadow-xl">
                  <QRCodeSVG
                    value={buildVCard()}
                    size={300}
                    level="H"
                    includeMargin
                    bgColor="#ffffff"
                    fgColor="#1e3a8a"
                    imageSettings={{
                      src: typeof guuLogo === "string" ? guuLogo : String(guuLogo as any),
                      height: 56,
                      width: 56,
                      excavate: true,
                    }}
                  />
                </div>
                <p className="text-xs text-gray-600 dark:text-gray-400 text-center">
                  {t("profile:dialog.qr.hint")}
                </p>
              </div>

              <div className="flex justify-center pt-4">
                <button
                  onClick={closeQrModal}
                  className="px-8 py-3 rounded-2xl font-extrabold text-white bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 shadow-lg hover:shadow-xl transition-all duration-200 transform hover:-translate-y-0.5 active:scale-95"
                >
                  {t("common:buttons.done")}
                </button>
              </div>
            </div>
          </motion.div>
        </div>
      )}

      {/* Achievement Modal */}
      {achOpen && (
        <div
          role="button"
          tabIndex={0}
          className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm cursor-pointer"
          onClick={() => setAchOpen(null)}
          onKeyDown={(e) => {
            if (e.key === "Escape" || e.key === "Enter" || e.key === " ") {
              e.preventDefault()
              setAchOpen(null)
            }
          }}
          aria-label="Close modal"
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 20 }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            onClick={(e) => e.stopPropagation()}
            className="relative w-full max-w-md rounded-3xl overflow-hidden backdrop-blur-xl bg-gradient-to-br from-white/95 via-white/90 to-white/85 dark:from-gray-900/95 dark:via-gray-900/90 dark:to-gray-900/85 border border-white/20 dark:border-white/10 shadow-2xl"
          >
            {/* Close Button */}
            <button
              onClick={() => setAchOpen(null)}
              className="absolute top-4 right-4 p-2 rounded-xl bg-white/10 dark:bg-white/5 hover:bg-white/20 dark:hover:bg-white/10 transition-colors z-10"
              aria-label="Close"
            >
              <CloseIcon className="w-5 h-5 text-gray-900 dark:text-gray-100" />
            </button>

            {/* Modal Content */}
            <div className="p-6 sm:p-8">
              <h2 className="text-2xl font-black mb-4 text-gray-900 dark:text-gray-100 pr-8">
                {achOpen.name}
              </h2>

              <div className="flex flex-col gap-3">
                {achOpen.issuer && (
                  <p className="text-gray-800 dark:text-gray-200">
                    {t("profile:dialog.achievement.organizer", { issuer: achOpen.issuer })}
                  </p>
                )}
                {achOpen.date && (
                  <p className="text-gray-800 dark:text-gray-200">
                    {t("profile:dialog.achievement.date", { date: achOpen.date })}
                  </p>
                )}
                {achOpen.url && (
                  <a
                    href={achOpen.url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center justify-center px-6 py-3 rounded-2xl font-extrabold text-white bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 shadow-lg hover:shadow-xl transition-all duration-200 transform hover:-translate-y-0.5 active:scale-95 no-underline"
                  >
                    {t("profile:dialog.achievement.openLink")}
                  </a>
                )}
              </div>

              <div className="flex justify-end pt-6">
                <button
                  onClick={() => setAchOpen(null)}
                  className="px-8 py-3 rounded-2xl font-extrabold text-gray-900 dark:text-gray-100 bg-white/10 dark:bg-white/5 hover:bg-white/20 dark:hover:bg-white/10 border border-white/20 dark:border-white/10 transition-all duration-200 transform hover:-translate-y-0.5 active:scale-95"
                >
                  {t("profile:dialog.achievement.close")}
                </button>
              </div>
            </div>
          </motion.div>
        </div>
      )}

      {/* Snackbar Notification */}
      {snack && (
        <motion.div
          initial={{ opacity: 0, y: 50, scale: 0.9 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 50, scale: 0.9 }}
          transition={{ type: "spring", stiffness: 300, damping: 25 }}
          className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[10000] w-full max-w-md px-4"
          data-testid={snack.key === "copied" ? "snackbar-copied" : undefined}
        >
          <div
            className={`relative flex items-center gap-3 px-5 py-4 rounded-2xl backdrop-blur-xl shadow-2xl ${
              snack.sev === "success"
                ? "bg-green-500/95 text-white"
                : snack.sev === "error"
                  ? "bg-red-500/95 text-white"
                  : snack.sev === "warning"
                    ? "bg-yellow-500/95 text-white"
                    : "bg-blue-500/95 text-white"
            }`}
          >
            {snack.sev === "success" && <CheckIcon className="w-6 h-6 flex-shrink-0" />}
            {snack.sev === "error" && <AlertCircleIcon className="w-6 h-6 flex-shrink-0" />}
            {snack.sev === "info" && <InfoIcon className="w-6 h-6 flex-shrink-0" />}
            {snack.sev === "warning" && <AlertCircleIcon className="w-6 h-6 flex-shrink-0" />}
            <p className="flex-1 font-bold">{snackMessage}</p>
            <button
              onClick={() => setSnack(null)}
              className="p-1 rounded-lg hover:bg-white/10 transition-colors flex-shrink-0"
              aria-label="Close"
            >
              <CloseIcon className="w-5 h-5" />
            </button>
          </div>
        </motion.div>
      )}

      {/* Auto-hide Snackbar */}
      {snack && setTimeout(() => setSnack(null), 2600)}

      <style>{`
        @keyframes pulse-ring {
          0% { box-shadow: 0 0 0 0 rgba(255,255,255,.18); }
          50% { box-shadow: 0 0 0 14px rgba(255,255,255,.03); }
          100% { box-shadow: 0 0 0 0 rgba(255,255,255,.02); }
        }
        
        @keyframes border-pulse {
          0% { border-color: rgba(255,255,255,.18); }
          50% { border-color: rgba(255,255,255,.34); }
          100% { border-color: rgba(255,255,255,.18); }
        }
      `}</style>
    </>
  )
}
