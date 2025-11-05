import { useEffect, useMemo, useState, useRef, useCallback, memo, type ReactNode } from "react"
import { Link, useLocation, useNavigate } from "react-router-dom"
import { motion, useReducedMotion } from "framer-motion"
import { useQueryClient } from "@tanstack/react-query"
import { QRCodeSVG } from "qrcode.react"
import { useTranslation } from "react-i18next"

import { useAuth, currentUserQueryKey } from "../contexts/AuthContext"
import useMediaQuery from "@/hooks/useMediaQuery"
import { nowPlayingQueryKey, useNowPlaying } from "@/hooks/useNowPlaying"
import type { NowPlaying } from "@/types/spotify"
import type { User } from "@/types/User"
import api from "../api/client"
import profileBg from "../assets/background.jpg"
import guuLogo from "../assets/guu_logo.png"
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"
import PageFadeIn from "../components/PageFadeIn"
import Dialog from "@/components/Dialog"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { ProgressBar } from "@/components/ui/progress-bar"
import { Chip } from "@/components/ui/badge"
import { cn } from "@/utils/cn"
import { addVersionParam, resolveMediaUrl } from "@/utils/media"

const DEFAULT_AVATAR = AVATAR_PLACEHOLDER_URL
const isTest = typeof import.meta !== "undefined" && import.meta.env.MODE === "test"

type SnackKey = "spotifyConnected" | "spotifyError" | "copied" | "profileUpdated" | "error"

type SnackState = {
  key?: SnackKey
  message?: string
  sev?: "success" | "info" | "warning" | "error"
}

const MailIcon = ({ className }: { className?: string }) => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={1.8}
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden
    className={cn("h-5 w-5 text-nav-link", className)}
  >
    <rect x={3} y={5} width={18} height={14} rx={2.2} ry={2.2} />
    <polyline points="3 7 12 13 21 7" />
  </svg>
)

const TelegramIcon = ({ className }: { className?: string }) => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={1.6}
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden
    className={cn("h-5 w-5 text-nav-link", className)}
  >
    <path d="M21 4.5 3.7 11.8c-.9.36-.88 1.57.03 1.9l4.76 1.72 1.88 5.54c.29.86 1.48.92 1.89.1l2.07-4.18 4.53-9.65c.36-.77-.45-1.56-1.23-1.34Z" />
    <path d="m9.27 14.33 8.28-6.77" />
  </svg>
)

const CopyIcon = ({ className }: { className?: string }) => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={1.6}
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden
    className={cn("h-5 w-5", className)}
  >
    <rect x={9} y={9} width={12} height={12} rx={2} />
    <path d="M5 15V5a2 2 0 0 1 2-2h10" />
  </svg>
)

const ArrowUpRightIcon = ({ className }: { className?: string }) => (
  <svg
    viewBox="0 0 20 20"
    fill="none"
    stroke="currentColor"
    strokeWidth={1.7}
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden
    className={cn("h-4 w-4", className)}
  >
    <path d="M6 6h8v8" />
    <path d="m6 14 8-8" />
  </svg>
)

const severityTone: Record<NonNullable<SnackState["sev"]>, string> = {
  success:
    "border-[color:color-mix(in_srgb,var(--page-text)_16%,transparent)] text-[color:color-mix(in_srgb,#22c55e_82%,white_18%)]",
  info: "border-[color:color-mix(in_srgb,var(--page-text)_16%,transparent)]",
  warning:
    "border-[color:color-mix(in_srgb,var(--page-text)_16%,transparent)] text-[color:color-mix(in_srgb,#f59e0b_84%,white_16%)]",
  error:
    "border-[color:color-mix(in_srgb,var(--page-text)_16%,transparent)] text-[color:color-mix(in_srgb,#f97316_88%,white_12%)]",
}

const prefersReducedMotionQuery = "(prefers-reduced-motion: reduce)"

export const NowPlayingCard = memo(function NowPlayingCard({ data }: { data: NowPlaying }) {
  const prefersReduce = useMediaQuery(prefersReducedMotionQuery)
  const reduced = useReducedMotion()
  const { t } = useTranslation(["profile"])
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
    const tick = () => {
      const elapsed = Date.now() - startRef.current
      setProgress(clampProgress(elapsed))
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
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
      className="group block overflow-hidden rounded-ue-xl border border-[color:color-mix(in_srgb,var(--page-text)_12%,transparent)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,transparent_4%)] p-4 text-page-foreground shadow-surface backdrop-blur-xl transition-[transform,box-shadow,border-color] duration-300 ease-out hover:-translate-y-[2px] hover:border-[color:color-mix(in_srgb,var(--page-text)_26%,transparent)] hover:shadow-surface-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--nav-link)]"
      aria-label={
        data.track_name
          ? t("profile:nowPlaying.openSpotifyWithTrack", { track: data.track_name })
          : t("profile:nowPlaying.openSpotify")
      }
      initial={isTest || prefersReduce || reduced ? undefined : { opacity: 0.94, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={prefersReduce || reduced ? undefined : { scale: 1.006 }}
      whileTap={prefersReduce || reduced ? undefined : { scale: 0.995 }}
      transition={{ type: "spring", stiffness: 420, damping: 32, mass: 0.9 }}
    >
      <div className="grid grid-cols-[auto,1fr] items-center gap-4">
        <div className="relative h-16 w-16 overflow-hidden rounded-ue-lg shadow-surface-strong">
          <img
            src={data.album_image_url ?? ""}
            alt={data.album_name || data.track_name || t("profile:nowPlaying.albumFallback")}
            loading="lazy"
            decoding="async"
            referrerPolicy="no-referrer"
            className={cn(
              "h-full w-full object-cover transition-transform duration-[1200ms] ease-[cubic-bezier(.22,.61,.36,1)]",
              prefersReduce || reduced ? "" : "group-hover:scale-[1.03]"
            )}
          />
        </div>
        <div className="min-w-0 space-y-2" aria-live="polite">
          <p className="truncate font-display text-[clamp(1rem,2.1vw,1.15rem)] font-extrabold tracking-tight">
            {data.track_name || "—"}
          </p>
          <p className="truncate text-sm text-[color:var(--secondary-text)]">
            {data.artists.join(", ")}
          </p>
          {!data.is_playing ? (
            <Chip
              size="xs"
              tone="info"
              variant="outline"
              label={t("profile:nowPlaying.paused")}
              className="uppercase tracking-[0.18em]"
              aria-hidden
            />
          ) : null}
          <div className="flex items-center gap-3">
            <ProgressBar
              value={pct}
              max={100}
              animated={!prefersReduce && !reduced}
              ariaLabel={t("profile:nowPlaying.progress")}
            />
            <p className="shrink-0 text-xs font-semibold text-[color:var(--secondary-text)]">
              {fmt(progress)} / {fmt(duration)}
            </p>
          </div>
        </div>
      </div>
    </motion.a>
  )
})

const DetailRow = ({ label, value }: { label: string; value?: ReactNode }) => {
  if (value == null || value === "") return null
  return (
    <div className="group relative grid grid-cols-[12px,1fr] items-center gap-3 rounded-ue-lg border border-[color:color-mix(in_srgb,var(--page-text)_12%,transparent)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,transparent_4%)] px-4 py-3 text-sm shadow-surface transition-all duration-300 ease-out hover:border-[color:color-mix(in_srgb,var(--page-text)_22%,transparent)] hover:shadow-surface-strong">
      <span className="block h-2 w-2 rounded-full bg-[color:var(--nav-link)] shadow-[0_0_0_6px_color-mix(in_srgb,var(--nav-link)_35%,transparent)]" />
      <p className="min-w-0 text-[0.98rem] leading-relaxed">
        <span className="font-semibold text-page-foreground">{label}:</span> {value}
      </p>
    </div>
  )
}

function Snackbar({
  snack,
  message,
  onClose,
}: {
  snack: SnackState | null
  message: string
  onClose: () => void
}) {
  useEffect(() => {
    if (!snack) return
    const timer = setTimeout(() => onClose(), 2600)
    return () => clearTimeout(timer)
  }, [snack, onClose])

  if (!snack) return null

  const toneClass = snack.sev ? severityTone[snack.sev] : severityTone.info

  return (
    <div className="fixed inset-x-0 bottom-6 z-[var(--ue-z-index-overlay)] flex justify-center px-4">
      <div
        className={cn(
          "animate-in slide-in-from-bottom-4 fade-in rounded-ue-xl border bg-[color:color-mix(in_srgb,var(--card-bg)_92%,transparent_8%)] px-5 py-4 text-sm font-semibold text-page-foreground shadow-[0_18px_46px_rgba(6,11,25,0.32)] backdrop-blur-xl",
          toneClass
        )}
        role="status"
        data-testid={snack.key === "copied" ? "snackbar-copied" : undefined}
      >
        {message}
      </div>
    </div>
  )
}

export default function Profile() {
  const { user, loading, setUser } = useAuth()
  const [snack, setSnack] = useState<SnackState | null>(null)
  const [avatarVersion, setAvatarVersion] = useState(Date.now())
  const [coverVersion, setCoverVersion] = useState(Date.now())
  const reduceMotion = useMediaQuery(prefersReducedMotionQuery)
  const isTwoCol = useMediaQuery("(min-width: 1200px)")
  const isMobile = useMediaQuery("(max-width: 640px)")
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
      const next = window.location.pathname + (sp.toString() ? `?${sp}` : "")
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
        ctx.clearRect(0, 0, canvas.width, canvas.height)
        parts.forEach((p) => {
          p.vy += 0.12 * dpr
          p.x += p.vx * dpr
          p.y += p.vy * dpr
          p.life -= 1
          ctx.fillStyle = p.color
          ctx.beginPath()
          ctx.arc(p.x, p.y, p.size * dpr, 0, Math.PI * 2)
          ctx.fill()
        })
        for (let i = parts.length - 1; i >= 0; i -= 1) if (parts[i].life <= 0) parts.splice(i, 1)
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
    const value = user?.telegram || ""
    if (!value) return ""
    let next = value.trim()
    if (next.startsWith("http")) return next
    if (next.startsWith("@")) next = next.slice(1)
    return `https://t.me/${next}`
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
    if (isMobile) return 124
    return isTwoCol ? 188 : 168
  }, [isMobile, isTwoCol])
  const avatarSize = `${avatarPx}px`
  const avatarFloat = Math.round(avatarPx * 0.55)
  const heroPaddingBottom = `${Math.max(avatarFloat - 20, 32)}px`
  const heroTextPaddingTop = `${Math.round(avatarPx * 0.62)}px`
  const isOnline = ((user as any)?.is_online ?? (user as any)?.online ?? true) as boolean
  const statusSize = useMemo(() => Math.max(12, Math.round(avatarPx * 0.16)), [avatarPx])
  const statusOffset = useMemo(() => Math.max(6, Math.round(avatarPx * 0.08)), [avatarPx])

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

  if (loading) {
    return (
      <div className="flex min-h-[70vh] items-center justify-center">
        <span className="h-9 w-9 animate-spin rounded-full border-2 border-[color:color-mix(in_srgb,var(--page-text)_32%,transparent)] border-t-[color:var(--nav-link)]" />
      </div>
    )
  }

  return (
    <>
      <div className="fixed inset-0 -z-20">
        <img src={profileBg} alt="" aria-hidden className="h-full w-full object-cover" />
        <div className="absolute inset-0 bg-[linear-gradient(118deg,color-mix(in_srgb,var(--nav-link)_64%,transparent),color-mix(in_srgb,var(--btn-bg,_#1f3b84)_38%,transparent))] mix-blend-multiply" />
        <div className="absolute inset-0 bg-[radial-gradient(1200px_760px_at_50%_-10%,color-mix(in_srgb,var(--nav-link)_24%,transparent)_0%,transparent_76%)]" />
      </div>

      <PageFadeIn>
        <motion.div
          initial={isTest ? false : { opacity: reduceMotion ? 1 : 0.96, y: reduceMotion ? 0 : 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={isTest ? { duration: 0 } : { type: "spring", stiffness: 420, damping: 32 }}
        >
          <main
            id="main"
            className="relative z-10 mx-auto flex min-h-[100svh] w-full max-w-[1100px] flex-col gap-10 px-4 py-16 sm:px-6 lg:px-8"
            data-testid="profile-root"
            aria-label={t("profile:aria.page")}
          >
            <motion.div
              initial={
                isTest || reduceMotion
                  ? undefined
                  : { opacity: 0.94, y: 18, scale: 0.99, filter: "blur(6px)" }
              }
              animate={{ opacity: 1, y: 0, scale: 1, filter: "blur(0px)" }}
              transition={{ type: "spring", stiffness: 420, damping: 30, mass: 0.9 }}
              className="relative overflow-hidden rounded-ue-xl border border-[color:color-mix(in_srgb,var(--page-text)_12%,transparent)] bg-[color:color-mix(in_srgb,var(--card-bg)_94%,transparent_6%)] px-6 py-8 text-page-foreground shadow-[0_36px_80px_rgba(6,15,35,0.42)] backdrop-blur-[18px] sm:px-8 sm:py-10"
            >
              <div className="flex flex-col gap-8 lg:[grid-template-columns:minmax(320px,380px)_minmax(0,1fr)] lg:grid lg:gap-10">
                <div className="flex flex-col gap-6">
                  <div
                    className="relative isolate overflow-hidden rounded-ue-xl border border-white/10 bg-[color:color-mix(in_srgb,var(--card-bg)_80%,transparent_20%)] text-white shadow-surface-strong"
                    style={{ paddingBottom: heroPaddingBottom }}
                  >
                    <div className="absolute inset-0">
                      <img
                        src={coverImageUrl}
                        alt=""
                        aria-hidden
                        style={{
                          transform: `translateY(${coverParallax}px) scale(${coverScale})`,
                          transition: reduceMotion
                            ? "none"
                            : "transform 1200ms cubic-bezier(.33,1,.68,1)",
                          filter: "saturate(1.05) contrast(1.04)",
                        }}
                        className="h-full w-full object-cover"
                      />
                      <div className="absolute inset-0 bg-[linear-gradient(190deg,rgba(8,12,28,0.05)_0%,rgba(8,12,28,0.86)_100%)]" />
                    </div>

                    <div
                      className="absolute left-1/2 flex -translate-x-1/2 items-center justify-center rounded-full border border-white/20 bg-white/10 p-1.5 shadow-[0_25px_60px_rgba(8,15,35,0.36)] backdrop-blur-[14px]"
                      style={{
                        top: `clamp(2rem, 8vw, 4.5rem)`,
                        width: avatarSize,
                        height: avatarSize,
                      }}
                    >
                      <div className="relative h-full w-full overflow-hidden rounded-full bg-[color:color-mix(in_srgb,var(--nav-link)_30%,var(--card-bg)_70%)]">
                        <img
                          src={avatarImageUrl}
                          alt={user?.full_name ?? undefined}
                          loading="lazy"
                          decoding="async"
                          referrerPolicy="no-referrer"
                          onError={handleAvatarImgError}
                          className="h-full w-full object-cover"
                        />
                        {!user?.avatar_url ? (
                          <span className="absolute inset-0 flex items-center justify-center font-display text-4xl font-bold text-white/80">
                            {user?.full_name?.[0]}
                          </span>
                        ) : null}
                        {isOnline ? (
                          <span
                            className="absolute rounded-full bg-[#22c55e] shadow-[0_0_0_2px_rgba(6,11,25,0.58),0_6px_14px_rgba(34,197,94,0.45)]"
                            style={{
                              width: `${statusSize}px`,
                              height: `${statusSize}px`,
                              right: `${statusOffset}px`,
                              bottom: `${statusOffset}px`,
                            }}
                          >
                            {reduced ? null : (
                              <span className="absolute inset-0 -z-10 animate-[ping_1.8s_ease-in-out_infinite] rounded-full border-2 border-[#22c55e]/40" />
                            )}
                          </span>
                        ) : null}
                      </div>
                    </div>

                    <div
                      className="relative z-10 mx-auto flex w-full max-w-xl flex-col items-center gap-6 px-6 text-center lg:items-start lg:px-8 lg:text-left"
                      style={{ paddingTop: heroTextPaddingTop }}
                    >
                      <header className="space-y-2">
                        <h1
                          className="font-display text-[clamp(1.9rem,3vw,3rem)] font-extrabold leading-[1.05] tracking-tight"
                          data-testid="profile-name"
                        >
                          {user?.full_name}
                        </h1>
                        {user?.role === "teacher" && user?.position ? (
                          <p className="text-[clamp(1rem,1.5vw,1.2rem)] font-semibold text-white/80">
                            {user.position}
                          </p>
                        ) : null}
                      </header>

                      <div className="flex flex-wrap items-center justify-center gap-2 lg:justify-start">
                        {[
                          user?.role === "teacher"
                            ? t("profile:chips.teacher")
                            : user?.role === "student"
                              ? t("profile:chips.student")
                              : t("profile:chips.admin"),
                          ...(user?.role === "student" && user?.course
                            ? [t("profile:chips.course", { value: user.course })]
                            : []),
                          ...(user?.institute ? [user.institute] : []),
                        ].map((chip, idx) => (
                          <motion.span
                            key={`${chip}-${idx}`}
                            initial={reduced ? undefined : { opacity: 0, y: 12 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: reduced ? 0 : idx * 0.08, duration: 0.4 }}
                          >
                            <Chip
                              size="sm"
                              tone="info"
                              variant="outline"
                              label={chip}
                              className="bg-white/10 text-white"
                            />
                          </motion.span>
                        ))}
                      </div>

                      {!edit ? (
                        <div className="flex flex-wrap items-center justify-center gap-3 lg:justify-start">
                          <Button
                            as={Link}
                            to="/profile/edit"
                            variant="solid"
                            className="w-full rounded-ue-lg px-6 py-3 text-base font-extrabold shadow-surface-strong transition hover:-translate-y-[1px] hover:shadow-surface-strong lg:w-auto"
                          >
                            {t("profile:buttons.edit", { defaultValue: "Редактировать профиль" })}
                          </Button>
                          <Button
                            variant="outline"
                            onClick={openQrModal}
                            className="w-full rounded-ue-lg px-6 py-3 text-base font-semibold lg:w-auto"
                            data-testid="open-qr"
                          >
                            {t("profile:buttons.showQr")}
                          </Button>
                        </div>
                      ) : null}
                    </div>
                  </div>

                  <Card
                    padding="lg"
                    className="gap-6 border-[color:color-mix(in_srgb,var(--page-text)_10%,transparent)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,transparent_4%)] shadow-surface"
                  >
                    {edit ? null : (
                      <div className="flex flex-col gap-4">
                        <h2 className="font-display text-[clamp(1.2rem,2vw,1.4rem)] font-semibold">
                          {t("profile:sections.contacts", { defaultValue: "Контакты" })}
                        </h2>
                        <div className="flex flex-col gap-3">
                          <div className="flex flex-wrap items-center gap-3 rounded-ue-lg border border-[color:color-mix(in_srgb,var(--page-text)_14%,transparent)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,transparent_4%)] px-4 py-3 shadow-surface transition-all duration-200 hover:border-[color:color-mix(in_srgb,var(--page-text)_24%,transparent)]">
                            <MailIcon className="text-[color:var(--nav-link)]" />
                            <a
                              href={`mailto:${user?.email ?? ""}`}
                              className="max-w-full flex-1 truncate text-base font-semibold text-page-foreground no-underline hover:text-nav-link"
                              data-testid="profile-email-link"
                              title={t("profile:aria.openEmail")}
                            >
                              {user?.email}
                            </a>
                            <button
                              type="button"
                              onClick={(event) => {
                                const { clientX, clientY } = event
                                copy(user?.email ?? "", { clientX, clientY })
                              }}
                              className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-[color:color-mix(in_srgb,var(--page-text)_16%,transparent)] bg-white/60 text-[color:var(--nav-link)] shadow-surface transition hover:-translate-y-[1px] hover:border-[color:color-mix(in_srgb,var(--nav-link)_32%,transparent)] hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--nav-link)]"
                              aria-label={t("profile:aria.copyEmail")}
                              data-testid="copy-email"
                            >
                              <CopyIcon />
                            </button>
                          </div>

                          {user?.telegram ? (
                            <div className="flex flex-wrap items-center gap-3 rounded-ue-lg border border-[color:color-mix(in_srgb,var(--page-text)_14%,transparent)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,transparent_4%)] px-4 py-3 shadow-surface transition-all duration-200 hover:border-[color:color-mix(in_srgb,var(--page-text)_24%,transparent)]">
                              <TelegramIcon className="text-[color:var(--nav-link)]" />
                              <a
                                href={telegramHref}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="max-w-full flex-1 truncate text-base font-semibold text-page-foreground no-underline hover:text-nav-link"
                                data-testid="profile-telegram-link"
                                title={t("profile:aria.openTelegram")}
                              >
                                {user.telegram}
                              </a>
                              <button
                                type="button"
                                onClick={(event) => {
                                  const { clientX, clientY } = event
                                  copy(user.telegram ?? "", { clientX, clientY })
                                }}
                                className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-[color:color-mix(in_srgb,var(--page-text)_16%,transparent)] bg-white/60 text-[color:var(--nav-link)] shadow-surface transition hover:-translate-y-[1px] hover:border-[color:color-mix(in_srgb,var(--nav-link)_32%,transparent)] hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--nav-link)]"
                                aria-label={t("profile:aria.copyTelegram")}
                                data-testid="copy-telegram"
                              >
                                <CopyIcon />
                              </button>
                            </div>
                          ) : null}
                        </div>
                      </div>
                    )}

                    {showNowPlaying && nowPlaying ? (
                      <section className="space-y-3">
                        <p className="text-xs font-semibold uppercase tracking-[0.3em] text-[color:var(--secondary-text)]">
                          {t("profile:sections.nowPlaying")}
                        </p>
                        <NowPlayingCard data={nowPlaying} />
                      </section>
                    ) : null}

                    {!edit && achievementsList.length > 0 ? (
                      <section className="space-y-4">
                        <header className="flex items-center justify-between">
                          <h2 className="font-display text-[clamp(1.2rem,2vw,1.4rem)] font-semibold">
                            {t("profile:sections.achievements", { defaultValue: "Достижения" })}
                          </h2>
                          <span className="text-sm font-medium text-[color:var(--secondary-text)]">
                            {t("profile:aria.totalAchievements", {
                              count: achievementsList.length,
                              defaultValue:
                                achievementsList.length === 1
                                  ? "1 достижение"
                                  : `${achievementsList.length} достижений`,
                            })}
                          </span>
                        </header>
                        <div className="grid gap-2.5 sm:grid-cols-2">
                          {achievementsList.map((ach, idx) => (
                            <motion.button
                              key={ach.key}
                              type="button"
                              initial={reduced ? undefined : { opacity: 0, y: 12 }}
                              animate={{ opacity: 1, y: 0 }}
                              transition={{ delay: reduced ? 0 : idx * 0.05, duration: 0.4 }}
                              onClick={() =>
                                setAchOpen({
                                  name: ach.name,
                                  issuer: ach.issuer,
                                  date: ach.date,
                                  url: ach.url,
                                })
                              }
                              className="group flex h-full w-full items-center justify-between gap-3 rounded-ue-lg border border-[color:color-mix(in_srgb,var(--page-text)_14%,transparent)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,transparent_4%)] px-4 py-3 text-left text-sm font-semibold text-page-foreground shadow-surface transition hover:-translate-y-[1px] hover:border-[color:color-mix(in_srgb,var(--nav-link)_32%,transparent)] hover:bg-[color:color-mix(in_srgb,var(--card-bg)_98%,transparent_2%)] hover:shadow-surface-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--nav-link)]"
                            >
                              <span className="truncate font-semibold">{ach.name}</span>
                              <ArrowUpRightIcon className="text-[color:var(--nav-link)] transition group-hover:translate-x-[1px] group-hover:-translate-y-[1px]" />
                            </motion.button>
                          ))}
                        </div>
                      </section>
                    ) : null}

                    {edit ? (
                      <section className="space-y-6">
                        <div className="flex flex-col gap-1">
                          <h2 className="font-display text-[clamp(1.4rem,2.4vw,1.8rem)] font-semibold">
                            {t("profile:sections.editTitle", { defaultValue: "Обновить профиль" })}
                          </h2>
                          <p className="text-sm text-[color:var(--secondary-text)]">
                            {t("profile:sections.editHint", {
                              defaultValue: "Измените публичную информацию о себе.",
                            })}
                          </p>
                        </div>
                        <div className="grid gap-4 md:grid-cols-2 md:gap-5">
                          <div className="flex flex-col gap-2 md:col-span-2">
                            <label
                              className="text-sm font-semibold text-[color:var(--secondary-text)]"
                              htmlFor="profile-full-name"
                            >
                              {t("profile:form.name")}
                            </label>
                            <input
                              id="profile-full-name"
                              value={fullName}
                              onChange={(event) => setFullName(event.target.value)}
                              maxLength={120}
                              className="w-full rounded-ue-lg border border-[color:color-mix(in_srgb,var(--page-text)_18%,transparent)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,transparent_4%)] px-4 py-3 text-base font-medium text-page-foreground shadow-inner transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--nav-link)]"
                              placeholder={t("profile:form.namePlaceholder", "Ваше имя")}
                            />
                          </div>

                          <div className="flex flex-col gap-2">
                            <label
                              className="text-sm font-semibold text-[color:var(--secondary-text)]"
                              htmlFor="profile-email"
                            >
                              {t("profile:form.email")}
                            </label>
                            <input
                              id="profile-email"
                              type="email"
                              value={email}
                              onChange={(event) => setEmail(event.target.value)}
                              className="w-full rounded-ue-lg border border-[color:color-mix(in_srgb,var(--page-text)_18%,transparent)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,transparent_4%)] px-4 py-3 text-base font-medium text-page-foreground shadow-inner transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--nav-link)]"
                              placeholder="example@domain.com"
                            />
                          </div>

                          <div className="flex flex-col gap-2">
                            <label
                              className="text-sm font-semibold text-[color:var(--secondary-text)]"
                              htmlFor="profile-telegram"
                            >
                              {t("profile:form.telegram")}
                            </label>
                            <input
                              id="profile-telegram"
                              value={telegram}
                              onChange={(event) => setTelegram(event.target.value)}
                              className="w-full rounded-ue-lg border border-[color:color-mix(in_srgb,var(--page-text)_18%,transparent)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,transparent_4%)] px-4 py-3 text-base font-medium text-page-foreground shadow-inner transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--nav-link)]"
                              placeholder="@username"
                              aria-describedby="profile-telegram-hint"
                            />
                            <p
                              id="profile-telegram-hint"
                              className="text-xs text-[color:var(--secondary-text)]"
                            >
                              {t("profile:form.telegramHint")}
                            </p>
                          </div>

                          {user?.role === "teacher" ? (
                            <>
                              <div className="flex flex-col gap-2">
                                <label
                                  className="text-sm font-semibold text-[color:var(--secondary-text)]"
                                  htmlFor="profile-department"
                                >
                                  {t("profile:form.department")}
                                </label>
                                <input
                                  id="profile-department"
                                  value={department}
                                  onChange={(event) => setDepartment(event.target.value)}
                                  className="w-full rounded-ue-lg border border-[color:color-mix(in_srgb,var(--page-text)_18%,transparent)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,transparent_4%)] px-4 py-3 text-base font-medium text-page-foreground shadow-inner transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--nav-link)]"
                                />
                              </div>
                              <div className="flex flex-col gap-2">
                                <label
                                  className="text-sm font-semibold text-[color:var(--secondary-text)]"
                                  htmlFor="profile-position"
                                >
                                  {t("profile:form.position")}
                                </label>
                                <input
                                  id="profile-position"
                                  value={position}
                                  onChange={(event) => setPosition(event.target.value)}
                                  className="w-full rounded-ue-lg border border-[color:color-mix(in_srgb,var(--page-text)_18%,transparent)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,transparent_4%)] px-4 py-3 text-base font-medium text-page-foreground shadow-inner transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--nav-link)]"
                                />
                              </div>
                            </>
                          ) : null}

                          {user?.role === "student" ? (
                            <>
                              <div className="md:col-span-2 flex flex-col gap-2">
                                <label
                                  className="text-sm font-semibold text-[color:var(--secondary-text)]"
                                  htmlFor="profile-about"
                                >
                                  {t("profile:form.about")}
                                </label>
                                <textarea
                                  id="profile-about"
                                  value={about}
                                  onChange={(event) => setAbout(event.target.value)}
                                  className="min-h-[120px] w-full rounded-ue-lg border border-[color:color-mix(in_srgb,var(--page-text)_18%,transparent)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,transparent_4%)] px-4 py-3 text-base font-medium text-page-foreground shadow-inner transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--nav-link)]"
                                />
                              </div>

                              <div className="flex flex-col gap-2">
                                <label
                                  className="text-sm font-semibold text-[color:var(--secondary-text)]"
                                  htmlFor="profile-record-book"
                                >
                                  {t("profile:form.recordBookNumber")}
                                </label>
                                <input
                                  id="profile-record-book"
                                  value={recordBookNumber}
                                  onChange={(event) => setRecordBookNumber(event.target.value)}
                                  className="w-full rounded-ue-lg border border-[color:color-mix(in_srgb,var(--page-text)_18%,transparent)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,transparent_4%)] px-4 py-3 text-base font-medium text-page-foreground shadow-inner transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--nav-link)]"
                                />
                              </div>

                              <div className="flex flex-col gap-2">
                                <label
                                  className="text-sm font-semibold text-[color:var(--secondary-text)]"
                                  htmlFor="profile-status"
                                >
                                  {t("profile:form.status")}
                                </label>
                                <input
                                  id="profile-status"
                                  value={status}
                                  onChange={(event) => setStatus(event.target.value)}
                                  className="w-full rounded-ue-lg border border-[color:color-mix(in_srgb,var(--page-text)_18%,transparent)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,transparent_4%)] px-4 py-3 text-base font-medium text-page-foreground shadow-inner transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--nav-link)]"
                                />
                              </div>

                              <div className="flex flex-col gap-2">
                                <label
                                  className="text-sm font-semibold text-[color:var(--secondary-text)]"
                                  htmlFor="profile-institute"
                                >
                                  {t("profile:form.institute")}
                                </label>
                                <input
                                  id="profile-institute"
                                  value={institute}
                                  onChange={(event) => setInstitute(event.target.value)}
                                  className="w-full rounded-ue-lg border border-[color:color-mix(in_srgb,var(--page-text)_18%,transparent)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,transparent_4%)] px-4 py-3 text-base font-medium text-page-foreground shadow-inner transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--nav-link)]"
                                />
                              </div>

                              <div className="flex flex-col gap-2">
                                <label
                                  className="text-sm font-semibold text-[color:var(--secondary-text)]"
                                  htmlFor="profile-course"
                                >
                                  {t("profile:form.course")}
                                </label>
                                <input
                                  id="profile-course"
                                  value={course}
                                  onChange={(event) => setCourse(event.target.value)}
                                  className="w-full rounded-ue-lg border border-[color:color-mix(in_srgb,var(--page-text)_18%,transparent)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,transparent_4%)] px-4 py-3 text-base font-medium text-page-foreground shadow-inner transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--nav-link)]"
                                />
                              </div>

                              <div className="flex flex-col gap-2">
                                <label
                                  className="text-sm font-semibold text-[color:var(--secondary-text)]"
                                  htmlFor="profile-education-level"
                                >
                                  {t("profile:form.educationLevel")}
                                </label>
                                <input
                                  id="profile-education-level"
                                  value={educationLevel}
                                  onChange={(event) => setEducationLevel(event.target.value)}
                                  className="w-full rounded-ue-lg border border-[color:color-mix(in_srgb,var(--page-text)_18%,transparent)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,transparent_4%)] px-4 py-3 text-base font-medium text-page-foreground shadow-inner transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--nav-link)]"
                                />
                              </div>

                              <div className="flex flex-col gap-2">
                                <label
                                  className="text-sm font-semibold text-[color:var(--secondary-text)]"
                                  htmlFor="profile-track"
                                >
                                  {t("profile:form.track")}
                                </label>
                                <input
                                  id="profile-track"
                                  value={track}
                                  onChange={(event) => setTrack(event.target.value)}
                                  className="w-full rounded-ue-lg border border-[color:color-mix(in_srgb,var(--page-text)_18%,transparent)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,transparent_4%)] px-4 py-3 text-base font-medium text-page-foreground shadow-inner transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--nav-link)]"
                                />
                              </div>

                              <div className="flex flex-col gap-2">
                                <label
                                  className="text-sm font-semibold text-[color:var(--secondary-text)]"
                                  htmlFor="profile-program"
                                >
                                  {t("profile:form.program")}
                                </label>
                                <input
                                  id="profile-program"
                                  value={program}
                                  onChange={(event) => setProgram(event.target.value)}
                                  className="w-full rounded-ue-lg border border-[color:color-mix(in_srgb,var(--page-text)_18%,transparent)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,transparent_4%)] px-4 py-3 text-base font-medium text-page-foreground shadow-inner transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--nav-link)]"
                                />
                              </div>

                              <div className="md:col-span-2 flex flex-col gap-2">
                                <label
                                  className="text-sm font-semibold text-[color:var(--secondary-text)]"
                                  htmlFor="profile-achievements"
                                >
                                  {t("profile:form.achievements")}
                                </label>
                                <textarea
                                  id="profile-achievements"
                                  value={achievements}
                                  onChange={(event) => setAchievements(event.target.value)}
                                  className="min-h-[96px] w-full rounded-ue-lg border border-[color:color-mix(in_srgb,var(--page-text)_18%,transparent)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,transparent_4%)] px-4 py-3 text-base font-medium text-page-foreground shadow-inner transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--nav-link)]"
                                />
                              </div>
                            </>
                          ) : null}
                        </div>

                        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-end">
                          <Button
                            onClick={handleSave}
                            variant="solid"
                            loading={saving}
                            className="rounded-ue-lg px-6 py-3 text-base font-extrabold"
                          >
                            {saving ? t("profile:form.saving") : t("profile:form.save")}
                          </Button>
                          <Button
                            onClick={handleCancel}
                            variant="outline"
                            className="rounded-ue-lg px-6 py-3 text-base font-semibold"
                          >
                            {t("profile:form.cancel")}
                          </Button>
                        </div>
                      </section>
                    ) : null}

                    {!edit ? (
                      <section className="space-y-4">
                        <header className="flex flex-col gap-2">
                          <h2 className="font-display text-[clamp(1.25rem,2.2vw,1.6rem)] font-semibold">
                            {t("profile:sections.details", { defaultValue: "Детали" })}
                          </h2>
                          <p className="text-sm text-[color:var(--secondary-text)]">
                            {t("profile:sections.detailsHint", {
                              defaultValue: "Подробности о вашей учебе и работе",
                            })}
                          </p>
                        </header>
                        <div className="grid gap-3 md:grid-cols-2">
                          <DetailRow label={t("profile:form.about") ?? ""} value={user?.about} />
                          <DetailRow label={t("profile:form.status") ?? ""} value={user?.status} />
                          <DetailRow
                            label={t("profile:form.recordBookNumber") ?? ""}
                            value={user?.record_book_number}
                          />
                          <DetailRow
                            label={t("profile:form.educationLevel") ?? ""}
                            value={user?.education_level}
                          />
                          <DetailRow label={t("profile:form.track") ?? ""} value={user?.track} />
                          <DetailRow
                            label={t("profile:form.program") ?? ""}
                            value={user?.program}
                          />
                          <DetailRow
                            label={t("profile:form.department") ?? ""}
                            value={user?.department}
                          />
                          <DetailRow
                            label={t("profile:form.position") ?? ""}
                            value={user?.position}
                          />
                          <DetailRow
                            label={t("profile:form.institute") ?? ""}
                            value={user?.institute}
                          />
                        </div>
                      </section>
                    ) : null}
                  </Card>
                </div>
              </div>
            </motion.div>

            <canvas
              ref={confettiRef}
              className="pointer-events-none fixed left-0 top-0 z-[2147483000] h-screen w-screen"
            />
          </main>
        </motion.div>
      </PageFadeIn>

      <Dialog
        open={qrOpen}
        onClose={closeQrModal}
        title={t("profile:dialog.qr.title")}
        size="sm"
        footer={
          <Button onClick={closeQrModal} variant="solid" className="rounded-ue-lg">
            {t("common:buttons.done")}
          </Button>
        }
      >
        <div className="flex flex-col items-center gap-4">
          <div className="rounded-ue-xl border border-[color:color-mix(in_srgb,var(--nav-link)_28%,transparent)] bg-white p-3 shadow-[0_16px_40px_rgba(6,11,25,0.24)]">
            <QRCodeSVG
              value={buildVCard()}
              size={260}
              level="H"
              includeMargin
              bgColor="#ffffff"
              fgColor="#0f172a"
              imageSettings={{
                src: typeof guuLogo === "string" ? guuLogo : String(guuLogo as any),
                height: 48,
                width: 48,
                excavate: true,
              }}
            />
          </div>
          <p className="text-center text-sm text-[color:var(--secondary-text)]">
            {t("profile:dialog.qr.hint")}
          </p>
        </div>
      </Dialog>

      <Dialog
        open={Boolean(achOpen)}
        onClose={() => setAchOpen(null)}
        title={achOpen?.name ?? ""}
        size="sm"
        footer={
          <Button onClick={() => setAchOpen(null)} variant="solid" className="rounded-ue-lg">
            {t("profile:dialog.achievement.close")}
          </Button>
        }
      >
        <div className="space-y-3 text-sm">
          {achOpen?.issuer ? (
            <p>{t("profile:dialog.achievement.organizer", { issuer: achOpen.issuer })}</p>
          ) : null}
          {achOpen?.date ? (
            <p>{t("profile:dialog.achievement.date", { date: achOpen.date })}</p>
          ) : null}
          {achOpen?.url ? (
            <Button
              as="a"
              href={achOpen.url}
              target="_blank"
              rel="noreferrer"
              variant="outline"
              className="rounded-ue-lg"
            >
              {t("profile:dialog.achievement.openLink")}
            </Button>
          ) : null}
        </div>
      </Dialog>

      <Snackbar snack={snack} message={snackMessage} onClose={() => setSnack(null)} />
    </>
  )
}
