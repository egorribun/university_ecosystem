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
import ExpandMoreIcon from "@mui/icons-material/ExpandMore"
import EmailIcon from "@mui/icons-material/Email"
import TelegramIcon from "@mui/icons-material/Telegram"
import ContentCopyIcon from "@mui/icons-material/ContentCopy"
import { QRCodeSVG } from "qrcode.react"
import { motion, useReducedMotion } from "framer-motion"
import { nowPlayingQueryKey, useNowPlaying } from "@/hooks/useNowPlaying"
import type { NowPlaying } from "@/types/spotify"
import { addVersionParam, resolveMediaUrl } from "@/utils/media"
import { useTranslation } from "react-i18next"

const isTest = typeof import.meta !== "undefined" && import.meta.env.MODE === "test"

// Helper hook to detect dark mode
const useIsDark = () => {
  const [isDark, setIsDark] = useState(false)
  useEffect(() => {
    const checkDark = () => setIsDark(document.body.classList.contains("dark"))
    checkDark()
    const observer = new MutationObserver(checkDark)
    observer.observe(document.body, { attributes: true, attributeFilter: ["class"] })
    return () => observer.disconnect()
  }, [])
  return isDark
}

type SnackKey = "spotifyConnected" | "spotifyError" | "copied" | "profileUpdated" | "error"

type SnackState = {
  key?: SnackKey
  message?: string
  sev?: "success" | "info" | "warning" | "error"
}

export const NowPlayingCard = memo(function NowPlayingCard({ data }: { data: NowPlaying }) {
  const prefersReduce = useMemo(
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    []
  )
  const reduced = useReducedMotion()
  const isDark = useIsDark()
  const duration = data.duration_ms ?? 0
  const { t } = useTranslation(["profile"])

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
      <motion.div
        className="nowplaying--spotify relative w-full grid grid-cols-[auto_1fr] items-center gap-x-8 gap-y-4 px-8 py-7 rounded-3xl overflow-hidden border border-white/14 dark:border-white/14 bg-[#121212] text-white shadow-[0_8px_20px_rgba(0,0,0,0.35)] dark:shadow-[0_8px_20px_rgba(0,0,0,0.35)] backdrop-blur-md"
        initial={isTest || prefersReduce || reduced ? false : { y: 12, opacity: 0.94, scale: 1 }}
        animate={{ y: 0, opacity: 1, scale: 1 }}
        whileHover={prefersReduce || reduced ? {} : { y: -1, scale: 1.002 }}
        whileTap={prefersReduce || reduced ? {} : { scale: 0.997 }}
        transition={
          isTest ? { duration: 0 } : { type: "spring", stiffness: 520, damping: 36, mass: 0.9 }
        }
      >
        <div className="relative w-14 h-14 rounded-xl overflow-hidden shadow-[0_8px_20px_rgba(0,0,0,0.35)] dark:shadow-[0_8px_20px_rgba(0,0,0,0.35)]">
          <img
            src={data.album_image_url ?? ""}
            alt={data.album_name || data.track_name || t("profile:nowPlaying.albumFallback")}
            loading="lazy"
            decoding="async"
            referrerPolicy="no-referrer"
            className={`w-full h-full rounded-xl object-cover ${
              prefersReduce || reduced
                ? ""
                : "transition-transform duration-[900ms] ease-[cubic-bezier(.22,.61,.36,1)] scale-[1.012] hover:scale-[1.02]"
            }`}
          />
        </div>
        <div className="min-w-0 flex flex-col gap-3" aria-live="polite">
          <h3 className="np-title text-base font-extrabold leading-[1.2] tracking-[-0.01em] text-white">
            {data.track_name || "—"}
          </h3>
          <p className="np-art text-sm opacity-90 text-[#b3b3b3]">{data.artists.join(", ")}</p>
          {!data.is_playing && (
            <span
              className="self-start px-4 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-wide bg-white/10 text-white/80 border border-white/20"
              aria-hidden
            >
              {t("profile:nowPlaying.paused")}
            </span>
          )}
          <div className="flex items-center gap-4 w-full">
            <div className="flex-1 h-1.5 rounded-full bg-[#2a2a2a] overflow-hidden">
              <div
                className="h-full bg-[#1db954] rounded-full transition-all duration-300 ease-out"
                style={{ width: `${pct}%` }}
                aria-label={t("profile:nowPlaying.progress")}
                role="progressbar"
                aria-valuenow={pct}
                aria-valuemin={0}
                aria-valuemax={100}
              />
            </div>
            <span className="np-time text-xs whitespace-nowrap text-[#b3b3b3]">
              {fmt(progress)} / {fmt(duration)}
            </span>
          </div>
        </div>
      </motion.div>
    </a>
  )
})

const DetailRow = ({ label, value }: { label: string; value?: React.ReactNode }) => {
  if (value == null || value === "") return null
  return (
    <div className="glass grid grid-cols-[14px_1fr] items-center gap-5 px-5 py-4 min-h-[44px] rounded-xl border border-black/10 dark:border-white/12 bg-glass border-glass-border backdrop-blur-md shadow-glass">
      <div className="w-2 h-2 rounded-full bg-[#1F68C7] dark:bg-[#8ABFEF] shadow-[0_0_0_3px_rgba(31,104,199,0.22)] dark:shadow-[0_0_0_3px_rgba(138,191,239,0.22)] justify-self-center" />
      <p className="leading-[1.25] text-page-foreground">
        <b>{label}:</b> {value}
      </p>
    </div>
  )
}

const SnackbarComponent = ({
  snack,
  snackMessage,
  onClose,
}: {
  snack: SnackState
  snackMessage: string
  onClose: () => void
}) => {
  useEffect(() => {
    const timer = setTimeout(() => {
      onClose()
    }, 2600)
    return () => clearTimeout(timer)
  }, [onClose])

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 20 }}
      className="fixed bottom-8 left-1/2 -translate-x-1/2 z-[3400] max-w-md w-full mx-4"
      data-testid={snack.key === "copied" ? "snackbar-copied" : undefined}
    >
      <div
        className={`rounded-2xl p-4 shadow-[0_10px_26px_rgba(0,0,0,0.18),0_2px_10px_rgba(0,0,0,0.08)] backdrop-blur-md ${
          snack.sev === "success"
            ? "bg-gradient-to-b from-[#2e7d32] to-[#1b5e20] text-[#e9ffef]"
            : snack.sev === "error"
              ? "bg-gradient-to-b from-[#d32f2f] to-[#b71c1c] text-[#fff5f5]"
              : snack.sev === "info"
                ? "bg-gradient-to-b from-[#005ea2] to-[#1a4480] text-[#eaf4ff]"
                : "bg-gradient-to-b from-[#f59e0b] to-[#b45309] text-[#fff8e1]"
        }`}
      >
        <div className="flex items-center justify-between gap-4">
          <p className="flex-1 font-medium">{snackMessage}</p>
          <button
            onClick={onClose}
            className="w-6 h-6 flex items-center justify-center rounded-full hover:bg-white/20 transition-colors duration-200"
            aria-label="Close"
          >
            ×
          </button>
        </div>
      </div>
    </motion.div>
  )
}

const ProfileAccordion = ({
  isDark,
  user,
  t,
  achievementsList,
  setAchOpen,
  isTest,
  reduced,
}: {
  isDark: boolean
  user: User
  t: any
  achievementsList: Array<{
    key: string
    name: string
    issuer?: string
    date?: string
    url?: string
  }>
  setAchOpen: (ach: { name: string; issuer?: string; date?: string; url?: string } | null) => void
  isTest: boolean
  reduced: boolean
}) => {
  const [expanded, setExpanded] = useState(true)

  const rows = [
    { label: t("profile:form.about"), value: user.about },
    { label: t("profile:form.status"), value: user.status },
    { label: t("profile:form.recordBookNumber"), value: user.record_book_number },
    { label: t("profile:form.educationLevel"), value: user.education_level },
    { label: t("profile:form.track"), value: user.track },
    { label: t("profile:form.program"), value: user.program },
    { label: t("profile:form.department"), value: user.department },
    { label: t("profile:form.position"), value: user.position },
  ]

  return (
    <div className="glass rounded-3xl overflow-hidden bg-glass border border-glass-border backdrop-blur-md shadow-glass">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-9 py-6 border-b border-black/8 dark:border-white/10 transition-colors duration-200 hover:bg-surface-accent/50"
      >
        <h3 className="font-extrabold text-page-foreground">
          {t("profile:sections.profileDetails")}
        </h3>
        <ExpandMoreIcon
          className={`text-page-foreground transition-transform duration-300 ${
            expanded ? "rotate-180" : ""
          }`}
        />
      </button>
      {expanded && (
        <div className="px-6 sm:px-9 py-7 sm:py-8">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5 md:gap-6">
            {rows.map((r) => (
              <DetailRow key={r.label} label={r.label} value={r.value} />
            ))}
          </div>
          {achievementsList.length > 0 && (
            <div className="mt-10">
              <h3 className="text-base font-extrabold mb-6 text-page-foreground">
                {t("profile:sections.achievements")}
              </h3>
              <div className="grid grid-cols-[repeat(auto-fit,minmax(140px,1fr))] sm:grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-5">
                {achievementsList.map((ach, idx) => (
                  <motion.button
                    key={ach.key}
                    initial={isTest || reduced ? false : { opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={
                      isTest || reduced
                        ? { duration: 0 }
                        : {
                            duration: 0.5,
                            delay: reduced ? 0 : idx * 0.09,
                            ease: "easeOut",
                          }
                    }
                    onClick={() =>
                      setAchOpen({
                        name: ach.name,
                        issuer: ach.issuer,
                        date: ach.date,
                        url: ach.url,
                      })
                    }
                    className="glass--chip block w-full rounded-xl self-stretch px-6 py-4 font-bold leading-[1.3] whitespace-normal text-left bg-glass border border-glass-border backdrop-blur-md shadow-glass transition-all duration-200 hover:scale-105 focus:outline-none focus:ring-2 focus:ring-nav-link"
                    style={{
                      animation: reduced ? "none" : `chip-highlight 14s ease-in-out infinite`,
                      animationDelay: reduced ? "0ms" : `${idx * 110}ms`,
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
  )
}

export default function Profile() {
  const { user, loading, setUser } = useAuth()
  const isDark = useIsDark()
  const [snack, setSnack] = useState<SnackState | null>(null)
  const [avatarVersion, setAvatarVersion] = useState(Date.now())
  const [coverVersion, setCoverVersion] = useState(Date.now())
  const [reduceMotion, setReduceMotion] = useState(false)
  const [isTwoCol, setIsTwoCol] = useState(false)
  const [isMobile, setIsMobile] = useState(false)
  const reduced = useReducedMotion()
  const { t } = useTranslation(["profile", "common"])
  const [scrollY, setScrollY] = useState(0)

  useEffect(() => {
    const checkReduceMotion = () =>
      setReduceMotion(window.matchMedia("(prefers-reduced-motion: reduce)").matches)
    const checkTwoCol = () => setIsTwoCol(window.matchMedia("(min-width:1400px)").matches)
    const checkMobile = () => setIsMobile(window.matchMedia("(max-width:600px)").matches)

    checkReduceMotion()
    checkTwoCol()
    checkMobile()

    const mqReduce = window.matchMedia("(prefers-reduced-motion: reduce)")
    const mqTwoCol = window.matchMedia("(min-width:1400px)")
    const mqMobile = window.matchMedia("(max-width:600px)")

    const handleReduceChange = () => checkReduceMotion()
    const handleTwoColChange = () => checkTwoCol()
    const handleMobileChange = () => checkMobile()

    if (mqReduce.addEventListener) {
      mqReduce.addEventListener("change", handleReduceChange)
      mqTwoCol.addEventListener("change", handleTwoColChange)
      mqMobile.addEventListener("change", handleMobileChange)
    } else {
      mqReduce.addListener(handleReduceChange)
      mqTwoCol.addListener(handleTwoColChange)
      mqMobile.addListener(handleMobileChange)
    }

    return () => {
      if (mqReduce.removeEventListener) {
        mqReduce.removeEventListener("change", handleReduceChange)
        mqTwoCol.removeEventListener("change", handleTwoColChange)
        mqMobile.removeEventListener("change", handleMobileChange)
      } else {
        mqReduce.removeListener(handleReduceChange)
        mqTwoCol.removeListener(handleTwoColChange)
        mqMobile.removeListener(handleMobileChange)
      }
    }
  }, [])
  const [qrOpen, setQrOpen] = useState(false)
  const [achOpen, setAchOpen] = useState<{
    name: string
    issuer?: string
    date?: string
    url?: string
  } | null>(null)
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
  const coverParallax = reduceMotion ? 0 : Math.min(scrollY * 0.1, 40)
  const coverScale = reduceMotion ? 1 : Math.min(1 + scrollY * 0.00014, 1.04)

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
        <div className="w-12 h-12 border-4 border-glass-border border-t-nav-link rounded-full animate-spin" />
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
      <div
        className="fixed inset-0 -z-[2] bg-cover bg-center bg-fixed"
        style={{ backgroundImage: `url(${profileBg})` }}
      >
        <div className="absolute inset-0 bg-gradient-to-br from-[#123F84]/66 via-[#17406F]/60 to-transparent mix-blend-multiply dark:from-[#2F4F75]/66 dark:via-[#1B3A5D]/60" />
        <div className="absolute inset-0 bg-[radial-gradient(1600px_800px_at_50%_0%,rgba(63,123,223,0.08)_0%,transparent_60%)] opacity-60 dark:bg-[radial-gradient(1600px_800px_at_50%_0%,rgba(157,200,240,0.08)_0%,transparent_60%)]" />
      </div>

      <PageFadeIn>
        <motion.div
          initial={isTest ? false : { opacity: reduceMotion ? 1 : 0.96, y: reduceMotion ? 0 : 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={isTest ? { duration: 0 } : { type: "spring", stiffness: 460, damping: 34 }}
        >
          <main
            id="main"
            className="profile-page relative min-h-[100svh] flex flex-col py-8 sm:py-9 md:py-10 px-6 sm:px-8 md:px-12"
            data-testid="profile-root"
            aria-label={t("profile:aria.page")}
          >
            <div className="max-w-7xl mx-auto relative z-0 w-full px-4 sm:px-6 md:px-8 lg:px-10">
              <motion.div
                ref={containerRef}
                className="glass profile-card relative overflow-hidden rounded-3xl md:rounded-[2rem] px-10 sm:px-14 md:px-[4.5rem] lg:px-[5.5rem] py-14 sm:py-[4.25rem] md:py-20 bg-glass border border-glass-border backdrop-blur-md shadow-glass"
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
                <div className="grid grid-cols-1 md:grid-cols-[minmax(360px,420px)_minmax(0,1fr)] gap-x-12 md:gap-x-24 gap-y-16 md:gap-y-0 items-start">
                  <div className="flex flex-col gap-[3.25rem] md:gap-16 items-stretch">
                    <div
                      className="glass relative rounded-3xl md:rounded-[2rem] overflow-hidden min-h-[300px] sm:min-h-[340px] md:min-h-[360px] lg:min-h-[400px] flex items-end justify-center bg-glass border border-glass-border backdrop-blur-md shadow-[0_28px_70px_-44px_rgba(0,0,0,0.2)] dark:shadow-[0_28px_70px_-44px_rgba(0,0,0,0.58)]"
                      style={{ paddingBottom: heroPaddingBottom }}
                    >
                      <div
                        className="absolute inset-0 bg-cover bg-center"
                        style={{
                          backgroundImage: coverImageUrl ? `url(${coverImageUrl})` : undefined,
                          transform: `translateY(${coverParallax}px) scale(${coverScale})`,
                          transition: reduceMotion
                            ? "none"
                            : "transform 1200ms cubic-bezier(.33,1,.68,1)",
                          filter: "saturate(1) contrast(1.02) brightness(0.98)",
                        }}
                      />
                      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-[rgba(6,9,20,0.9)]" />
                      <div
                        className="absolute left-1/2 top-24 sm:top-28 -translate-x-1/2 flex items-center justify-center p-1 rounded-full"
                        style={{
                          width: avatarSize,
                          height: avatarSize,
                          animation: reduceMotion ? "none" : "aura-pulse 14s ease-in-out infinite",
                        }}
                      >
                        <div className="avatar-ring w-full h-full relative">
                          <img
                            src={avatarImageUrl}
                            alt={user?.full_name ?? undefined}
                            onError={handleAvatarImgError}
                            loading="lazy"
                            decoding="async"
                            referrerPolicy="no-referrer"
                            className="w-full h-full rounded-full object-cover bg-white/12 text-white/92 flex items-center justify-center text-[clamp(28px,6vw,64px)] font-display"
                            style={{
                              fontFamily: "var(--font-display)",
                            }}
                          />
                          {!avatarImageUrl || avatarImageUrl === DEFAULT_AVATAR ? (
                            <span className="absolute inset-0 flex items-center justify-center text-white/92 font-display text-[clamp(28px,6vw,64px)]">
                              {user?.full_name?.[0]}
                            </span>
                          ) : null}
                        </div>

                        {isOnline && (
                          <div
                            className="absolute rounded-full bg-[#22c55e] shadow-[0_0_0_2px_rgba(0,0,0,.18),0_4px_10px_rgba(34,197,94,.45)] z-[3] pointer-events-none"
                            style={{
                              right: `${statusOffset}px`,
                              bottom: `${statusOffset}px`,
                              width: `${statusSize}px`,
                              height: `${statusSize}px`,
                            }}
                          >
                            {!reduced && (
                              <div
                                className="absolute inset-[-6px] rounded-full border-2 border-[#22c55e]/45"
                                style={{ animation: "online-pulse 1.8s ease-in-out infinite" }}
                              />
                            )}
                          </div>
                        )}
                      </div>
                      <div
                        className="relative z-[2] w-full text-center md:text-left px-10 sm:px-12 md:px-14 flex flex-col gap-10"
                        style={{ paddingTop: heroTextPaddingTop }}
                      >
                        <div>
                          <h1
                            className="profile-name text-[clamp(1.7rem,3.2vw,2.9rem)] font-extrabold leading-[1.08] tracking-[-0.01em] font-display"
                            data-testid="profile-name"
                          >
                            {user!.full_name}
                          </h1>
                          {!!user?.position && user?.role === "teacher" && (
                            <p className="profile-subtitle mt-3.5 font-semibold text-secondary dark:text-[#c9d2df] opacity-96">
                              {user.position}
                            </p>
                          )}
                        </div>
                        <div className="flex flex-row flex-wrap gap-5 justify-center md:justify-start items-center">
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
                              transition={
                                isTest || reduced
                                  ? { duration: 0 }
                                  : {
                                      duration: 0.56,
                                      delay: reduced ? 0 : idx * 0.09,
                                      ease: "easeOut",
                                    }
                              }
                              className="glass--chip inline-flex items-center px-6 py-2.5 rounded-full text-xs font-bold tracking-[0.01em] leading-[1.28] bg-glass border border-glass-border backdrop-blur-md shadow-glass"
                              style={{
                                animation: reduced
                                  ? "none"
                                  : `chip-highlight 12s ease-in-out infinite`,
                                animationDelay: reduced ? "0ms" : `${idx * 90}ms`,
                              }}
                            >
                              {chip}
                            </motion.span>
                          ))}
                        </div>
                      </div>
                    </div>

                    <div className="glass profile-card rounded-3xl p-10 sm:p-12 flex flex-col gap-10 md:gap-12 bg-glass border border-glass-border backdrop-blur-md shadow-glass">
                      <div className="flex flex-col gap-5 items-stretch">
                        <button
                          className="glass--btn w-full rounded-xl py-4 font-extrabold tracking-[0.24em] text-base bg-[#17406F] dark:bg-[#1B3A5D] text-white hover:bg-[#1a4a7f] dark:hover:bg-[#224466] transition-all duration-200 ease-out disabled:opacity-50 disabled:cursor-not-allowed"
                          onClick={openQrModal}
                          data-testid="open-qr"
                        >
                          {t("profile:buttons.showQr")}
                        </button>
                      </div>
                      <div className="h-px bg-gradient-to-r from-nav-link via-nav-link/50 to-transparent opacity-90" />
                      <div className="flex flex-col gap-7 contact-links">
                        <div className="flex flex-row items-center justify-between flex-wrap gap-6">
                          <div className="flex flex-row items-center gap-4 min-w-0 flex-1">
                            <EmailIcon
                              className="text-[22px] text-nav-link dark:text-[#7fb6e6]"
                              aria-hidden
                            />
                            <p className="font-extrabold break-words flex-1 text-page-foreground">
                              <a
                                href={`mailto:${user!.email}`}
                                className="text-nav-link dark:text-[#7fb6e6] no-underline hover:underline"
                                data-testid="profile-email-link"
                                title={t("profile:aria.openEmail")}
                              >
                                {user!.email}
                              </a>
                            </p>
                          </div>
                          <button
                            className="glass--btn min-w-[44px] min-h-[44px] flex items-center justify-center rounded-full p-2.5 border border-glass-border bg-glass backdrop-blur-md transition-all duration-200 ease-out hover:-translate-y-0.5 hover:scale-105 focus:outline-none focus:ring-2 focus:ring-nav-link focus:ring-offset-2"
                            onClick={(e) => copy(user!.email, e)}
                            aria-label={t("profile:aria.copyEmail")}
                            title={t("profile:aria.copyEmail")}
                            data-testid="copy-email"
                            style={{
                              transition: reduced
                                ? "color 140ms ease"
                                : "transform 200ms ease, box-shadow 200ms ease, color 200ms ease",
                            }}
                          >
                            <ContentCopyIcon className="text-lg text-page-foreground" />
                          </button>
                        </div>

                        {!!user!.telegram && (
                          <div className="flex flex-row items-center justify-between flex-wrap gap-6">
                            <div className="flex flex-row items-center gap-4 min-w-0 flex-1">
                              <TelegramIcon
                                className="text-[22px] text-nav-link dark:text-[#7fb6e6]"
                                aria-hidden
                              />
                              <p className="font-extrabold break-words flex-1 text-page-foreground">
                                <a
                                  href={telegramHref}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-nav-link dark:text-[#7fb6e6] no-underline hover:underline"
                                  data-testid="profile-telegram-link"
                                  title={t("profile:aria.openTelegram")}
                                >
                                  {user!.telegram}
                                </a>
                              </p>
                            </div>
                            <button
                              className="glass--btn min-w-[44px] min-h-[44px] flex items-center justify-center rounded-full p-2.5 border border-glass-border bg-glass backdrop-blur-md transition-all duration-200 ease-out hover:-translate-y-0.5 hover:scale-105 focus:outline-none focus:ring-2 focus:ring-nav-link focus:ring-offset-2"
                              onClick={(e) => copy(user!.telegram!, e)}
                              aria-label={t("profile:aria.copyTelegram")}
                              title={t("profile:aria.copyTelegram")}
                              data-testid="copy-telegram"
                              style={{
                                transition: reduced
                                  ? "color 140ms ease"
                                  : "transform 200ms ease, box-shadow 200ms ease, color 200ms ease",
                              }}
                            >
                              <ContentCopyIcon className="text-lg text-page-foreground" />
                            </button>
                          </div>
                        )}
                      </div>
                    </div>

                    {showNowPlaying && nowPlaying && (
                      <motion.div
                        initial={isTest || reduced ? false : { opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={isTest || reduced ? { duration: 0 } : { duration: 0.72 }}
                        className="flex flex-col gap-6"
                      >
                        <p className="text-[10px] uppercase tracking-[2.2px] text-secondary dark:text-[#9fb2cc]">
                          {t("profile:sections.nowPlaying")}
                        </p>
                        <NowPlayingCard data={nowPlaying} />
                      </motion.div>
                    )}
                  </div>

                  <div
                    className="w-full relative"
                    style={{ marginTop: isMobile ? `${Math.round(avatarPx * 0.55) + 36}px` : 0 }}
                  >
                    {edit ? (
                      <div className="glass profile-card profile-edit w-full rounded-3xl p-10 sm:p-12 md:p-14 bg-glass border border-glass-border backdrop-blur-md shadow-glass">
                        <div className="flex flex-col gap-9">
                          <div className="flex flex-col gap-1">
                            <label className="text-sm font-semibold text-page-foreground mb-1.5">
                              {t("profile:form.name")}
                            </label>
                            <input
                              type="text"
                              value={fullName}
                              onChange={(e) => setFullName(e.target.value)}
                              maxLength={120}
                              className="w-full px-4 py-3 rounded-xl border border-black/9 dark:border-white/12 bg-card-bg text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-nav-link focus:border-transparent transition-all duration-200"
                            />
                          </div>
                          <div className="flex flex-col gap-1">
                            <label className="text-sm font-semibold text-page-foreground mb-1.5">
                              {t("profile:form.email")}
                            </label>
                            <input
                              type="email"
                              value={email}
                              onChange={(e) => setEmail(e.target.value)}
                              className="w-full px-4 py-3 rounded-xl border border-black/9 dark:border-white/12 bg-card-bg text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-nav-link focus:border-transparent transition-all duration-200"
                            />
                          </div>
                          <div className="flex flex-col gap-1">
                            <label className="text-sm font-semibold text-page-foreground mb-1.5">
                              {t("profile:form.telegram")}
                            </label>
                            <input
                              type="text"
                              value={telegram}
                              onChange={(e) => setTelegram(e.target.value)}
                              className="w-full px-4 py-3 rounded-xl border border-black/9 dark:border-white/12 bg-card-bg text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-nav-link focus:border-transparent transition-all duration-200"
                            />
                            <p className="text-xs text-hint dark:text-hint mt-1">
                              {t("profile:form.telegramHint")}
                            </p>
                          </div>
                          {user!.role === "teacher" && (
                            <>
                              <div className="flex flex-col gap-1">
                                <label className="text-sm font-semibold text-page-foreground mb-1.5">
                                  {t("profile:form.department")}
                                </label>
                                <input
                                  type="text"
                                  value={department}
                                  onChange={(e) => setDepartment(e.target.value)}
                                  className="w-full px-4 py-3 rounded-xl border border-black/9 dark:border-white/12 bg-card-bg text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-nav-link focus:border-transparent transition-all duration-200"
                                />
                              </div>
                              <div className="flex flex-col gap-1">
                                <label className="text-sm font-semibold text-page-foreground mb-1.5">
                                  {t("profile:form.position")}
                                </label>
                                <input
                                  type="text"
                                  value={position}
                                  onChange={(e) => setPosition(e.target.value)}
                                  className="w-full px-4 py-3 rounded-xl border border-black/9 dark:border-white/12 bg-card-bg text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-nav-link focus:border-transparent transition-all duration-200"
                                />
                              </div>
                            </>
                          )}
                          {user!.role === "student" && (
                            <>
                              <div className="flex flex-col gap-1">
                                <label className="text-sm font-semibold text-page-foreground mb-1.5">
                                  {t("profile:form.about")}
                                </label>
                                <textarea
                                  value={about}
                                  onChange={(e) => setAbout(e.target.value)}
                                  rows={3}
                                  className="w-full px-4 py-3 rounded-xl border border-black/9 dark:border-white/12 bg-card-bg text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-nav-link focus:border-transparent transition-all duration-200 resize-y min-h-[80px]"
                                />
                              </div>
                              <div className="flex flex-col gap-1">
                                <label className="text-sm font-semibold text-page-foreground mb-1.5">
                                  {t("profile:form.recordBookNumber")}
                                </label>
                                <input
                                  type="text"
                                  value={recordBookNumber}
                                  onChange={(e) => setRecordBookNumber(e.target.value)}
                                  className="w-full px-4 py-3 rounded-xl border border-black/9 dark:border-white/12 bg-card-bg text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-nav-link focus:border-transparent transition-all duration-200"
                                />
                              </div>
                              <div className="flex flex-col gap-1">
                                <label className="text-sm font-semibold text-page-foreground mb-1.5">
                                  {t("profile:form.status")}
                                </label>
                                <input
                                  type="text"
                                  value={status}
                                  onChange={(e) => setStatus(e.target.value)}
                                  className="w-full px-4 py-3 rounded-xl border border-black/9 dark:border-white/12 bg-card-bg text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-nav-link focus:border-transparent transition-all duration-200"
                                />
                              </div>
                              <div className="flex flex-col gap-1">
                                <label className="text-sm font-semibold text-page-foreground mb-1.5">
                                  {t("profile:form.institute")}
                                </label>
                                <input
                                  type="text"
                                  value={institute}
                                  onChange={(e) => setInstitute(e.target.value)}
                                  className="w-full px-4 py-3 rounded-xl border border-black/9 dark:border-white/12 bg-card-bg text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-nav-link focus:border-transparent transition-all duration-200"
                                />
                              </div>
                              <div className="flex flex-col gap-1">
                                <label className="text-sm font-semibold text-page-foreground mb-1.5">
                                  {t("profile:form.course")}
                                </label>
                                <input
                                  type="text"
                                  value={course}
                                  onChange={(e) => setCourse(e.target.value)}
                                  className="w-full px-4 py-3 rounded-xl border border-black/9 dark:border-white/12 bg-card-bg text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-nav-link focus:border-transparent transition-all duration-200"
                                />
                              </div>
                              <div className="flex flex-col gap-1">
                                <label className="text-sm font-semibold text-page-foreground mb-1.5">
                                  {t("profile:form.educationLevel")}
                                </label>
                                <input
                                  type="text"
                                  value={educationLevel}
                                  onChange={(e) => setEducationLevel(e.target.value)}
                                  className="w-full px-4 py-3 rounded-xl border border-black/9 dark:border-white/12 bg-card-bg text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-nav-link focus:border-transparent transition-all duration-200"
                                />
                              </div>
                              <div className="flex flex-col gap-1">
                                <label className="text-sm font-semibold text-page-foreground mb-1.5">
                                  {t("profile:form.track")}
                                </label>
                                <input
                                  type="text"
                                  value={track}
                                  onChange={(e) => setTrack(e.target.value)}
                                  className="w-full px-4 py-3 rounded-xl border border-black/9 dark:border-white/12 bg-card-bg text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-nav-link focus:border-transparent transition-all duration-200"
                                />
                              </div>
                              <div className="flex flex-col gap-1">
                                <label className="text-sm font-semibold text-page-foreground mb-1.5">
                                  {t("profile:form.program")}
                                </label>
                                <input
                                  type="text"
                                  value={program}
                                  onChange={(e) => setProgram(e.target.value)}
                                  className="w-full px-4 py-3 rounded-xl border border-black/9 dark:border-white/12 bg-card-bg text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-nav-link focus:border-transparent transition-all duration-200"
                                />
                              </div>
                              <div className="flex flex-col gap-1">
                                <label className="text-sm font-semibold text-page-foreground mb-1.5">
                                  {t("profile:form.achievements")}
                                </label>
                                <textarea
                                  value={achievements}
                                  onChange={(e) => setAchievements(e.target.value)}
                                  rows={2}
                                  className="w-full px-4 py-3 rounded-xl border border-black/9 dark:border-white/12 bg-card-bg text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-nav-link focus:border-transparent transition-all duration-200 resize-y min-h-[60px]"
                                />
                              </div>
                            </>
                          )}
                          <div className="flex flex-col sm:flex-row gap-8 items-stretch sm:items-center mt-4">
                            <button
                              onClick={handleSave}
                              disabled={saving}
                              className="glass--btn px-8 py-3 rounded-xl font-extrabold bg-nav-link dark:bg-[#7fb6e6] text-white hover:bg-nav-link-hover dark:hover:bg-[#9DC8F0] disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 w-full sm:w-auto"
                            >
                              {saving ? t("profile:form.saving") : t("profile:form.save")}
                            </button>
                            <button
                              onClick={handleCancel}
                              className="glass--btn px-8 py-3 rounded-xl font-extrabold border-2 border-glass-border bg-glass text-page-foreground hover:bg-surface-accent transition-all duration-200 w-full sm:w-auto"
                            >
                              {t("profile:form.cancel")}
                            </button>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="glass profile-card w-full rounded-3xl p-10 sm:p-12 md:p-14 bg-glass border border-glass-border backdrop-blur-md shadow-glass">
                        <h2 className="text-[clamp(1.3rem,2.3vw,1.8rem)] font-extrabold mb-9 tracking-[-0.01em] font-display text-page-foreground">
                          {t("profile:sections.details")}
                        </h2>
                        <ProfileAccordion
                          isDark={isDark}
                          user={user!}
                          t={t}
                          achievementsList={achievementsList}
                          setAchOpen={setAchOpen}
                          isTest={isTest}
                          reduced={Boolean(reduced)}
                        />
                      </div>
                    )}
                  </div>
                </div>
              </motion.div>
            </div>

            <canvas
              ref={confettiRef}
              className="fixed left-0 top-0 w-screen h-screen pointer-events-none"
              style={{ zIndex: 2147483000 }}
            />
          </main>
        </motion.div>
      </PageFadeIn>

      {qrOpen && (
        <div className="fixed inset-0 z-[2800] flex items-center justify-center p-4 bg-black/50 dark:bg-black/70 backdrop-blur-sm">
          <div className="glass relative max-w-xs w-full rounded-3xl bg-glass border border-glass-border backdrop-blur-md shadow-glass p-6">
            <button
              onClick={closeQrModal}
              className="absolute top-4 right-4 w-8 h-8 flex items-center justify-center rounded-full hover:bg-surface-accent transition-colors duration-200 text-page-foreground"
              aria-label="Close"
            >
              ×
            </button>
            <h2 className="text-center font-extrabold text-xl tracking-[0.4px] mb-6 text-page-foreground">
              {t("profile:dialog.qr.title")}
            </h2>
            <div className="flex flex-col items-center justify-center gap-5 min-h-[320px]">
              <div className="bg-white p-8 rounded-3xl border border-[#0F4FAA]/15 dark:border-[#7fb6e6]/15 shadow-[0_18px_40px_-28px_rgba(0,0,0,0.4)]">
                <QRCodeSVG
                  value={buildVCard()}
                  size={300}
                  level="H"
                  includeMargin
                  bgColor="#ffffff"
                  fgColor={isDark ? "#2F4F75" : "#123F84"}
                  imageSettings={{
                    src: typeof guuLogo === "string" ? guuLogo : String(guuLogo as any),
                    height: 56,
                    width: 56,
                    excavate: true,
                  }}
                />
              </div>
              <p className="text-xs text-secondary dark:text-[#9fb2cc] text-center">
                {t("profile:dialog.qr.hint")}
              </p>
            </div>
            <div className="flex justify-center pt-6">
              <button
                onClick={closeQrModal}
                className="glass--btn px-8 py-3 rounded-xl font-extrabold bg-nav-link dark:bg-[#7fb6e6] text-white hover:bg-nav-link-hover dark:hover:bg-[#9DC8F0] transition-all duration-200"
              >
                {t("common:buttons.done")}
              </button>
            </div>
          </div>
        </div>
      )}

      {achOpen && (
        <div className="fixed inset-0 z-[2800] flex items-center justify-center p-4 bg-black/50 dark:bg-black/70 backdrop-blur-sm">
          <div className="glass relative max-w-xs w-full rounded-3xl bg-glass border border-glass-border backdrop-blur-md shadow-glass p-6">
            <button
              onClick={() => setAchOpen(null)}
              className="absolute top-4 right-4 w-8 h-8 flex items-center justify-center rounded-full hover:bg-surface-accent transition-colors duration-200 text-page-foreground"
              aria-label="Close"
            >
              ×
            </button>
            <h2 className="font-extrabold text-xl mb-6 text-page-foreground">{achOpen.name}</h2>
            <div className="flex flex-col gap-5 mb-6">
              {achOpen.issuer && (
                <p className="text-page-foreground">
                  {t("profile:dialog.achievement.organizer", { issuer: achOpen.issuer })}
                </p>
              )}
              {achOpen.date && (
                <p className="text-page-foreground">
                  {t("profile:dialog.achievement.date", { date: achOpen.date })}
                </p>
              )}
              {achOpen.url && (
                <a
                  href={achOpen.url}
                  target="_blank"
                  rel="noreferrer"
                  className="glass--btn inline-block px-8 py-3 rounded-xl font-extrabold border-2 border-glass-border bg-glass text-page-foreground hover:bg-surface-accent transition-all duration-200 text-center"
                >
                  {t("profile:dialog.achievement.openLink")}
                </a>
              )}
            </div>
            <div className="flex justify-end">
              <button
                onClick={() => setAchOpen(null)}
                className="glass--btn px-8 py-3 rounded-xl font-extrabold bg-nav-link dark:bg-[#7fb6e6] text-white hover:bg-nav-link-hover dark:hover:bg-[#9DC8F0] transition-all duration-200"
              >
                {t("profile:dialog.achievement.close")}
              </button>
            </div>
          </div>
        </div>
      )}

      {snack && (
        <SnackbarComponent
          snack={snack}
          snackMessage={snackMessage}
          onClose={() => setSnack(null)}
        />
      )}
    </>
  )
}
