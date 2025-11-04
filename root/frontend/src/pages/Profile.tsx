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
import { QRCodeSVG } from "qrcode.react"
import { motion, useReducedMotion } from "framer-motion"
import { nowPlayingQueryKey, useNowPlaying } from "@/hooks/useNowPlaying"
import type { NowPlaying } from "@/types/spotify"
import { addVersionParam, resolveMediaUrl } from "@/utils/media"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"

const isTest = typeof import.meta !== "undefined" && import.meta.env.MODE === "test"

type SnackKey = "spotifyConnected" | "spotifyError" | "copied" | "profileUpdated" | "error"

type SnackState = {
  key?: SnackKey
  message?: string
  sev?: "success" | "info" | "warning" | "error"
}

export const NowPlayingCard = memo(function NowPlayingCard({ data }: { data: NowPlaying }) {
  const [prefersReduce, setPrefersReduce] = useState(() =>
    typeof window !== "undefined" ? window.matchMedia("(prefers-reduced-motion: reduce)").matches : false
  )
  const reduced = useReducedMotion()

  useEffect(() => {
    if (typeof window === "undefined") return
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)")
    const handler = (e: MediaQueryListEvent) => setPrefersReduce(e.matches)
    setPrefersReduce(mediaQuery.matches)
    mediaQuery.addEventListener("change", handler)
    return () => mediaQuery.removeEventListener("change", handler)
  }, [])
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
        className="nowplaying--spotify relative grid w-full grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2 overflow-hidden rounded-ue-lg border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[#121212] px-4 py-3.5 text-white dark:border-[color:color-mix(in_srgb,white_8%,var(--nav-link)_92%)]"
        initial={isTest || prefersReduce || reduced ? false : { y: 12, opacity: 0.94, scale: 1 }}
        animate={{ y: 0, opacity: 1, scale: 1 }}
        whileHover={prefersReduce || reduced ? {} : { y: -1, scale: 1.002 }}
        whileTap={prefersReduce || reduced ? {} : { scale: 0.997 }}
        transition={
          isTest ? { duration: 0 } : { type: "spring", stiffness: 520, damping: 36, mass: 0.9 }
        }
      >
        <div className="relative h-14 w-14 overflow-hidden rounded-lg shadow-[0_8px_20px_rgba(0,0,0,0.35)]">
          <img
            src={data.album_image_url ?? ""}
            alt={data.album_name || data.track_name || t("profile:nowPlaying.albumFallback")}
            loading="lazy"
            decoding="async"
            referrerPolicy="no-referrer"
            className={cn(
              "h-full w-full rounded-lg object-cover",
              !prefersReduce && !reduced && "transition-transform duration-[900ms] ease-[cubic-bezier(.22,.61,.36,1)] hover:scale-[1.02]",
              !prefersReduce && !reduced && "scale-[1.012]"
            )}
          />
        </div>
        <div className="flex min-w-0 flex-col gap-1.5" aria-live="polite">
          <h3 className="np-title text-base font-extrabold leading-tight tracking-[-0.01em] text-white">
            {data.track_name || "—"}
          </h3>
          <p className="np-art text-sm opacity-90 text-[#b3b3b3]">
            {data.artists.join(", ")}
          </p>
          {!data.is_playing && (
            <span
              className="w-fit rounded-full border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,white_4%)] px-2.5 py-0.5 text-[0.65rem] font-bold uppercase tracking-wider text-[color:var(--secondary-text)] dark:border-[color:color-mix(in_srgb,white_8%,var(--nav-link)_92%)] dark:bg-[color:color-mix(in_srgb,var(--card-bg)_94%,transparent_6%)]"
              aria-hidden
            >
              {t("profile:nowPlaying.paused")}
            </span>
          )}
          <div className="flex w-full items-center gap-2">
            <div className="flex-1 overflow-hidden rounded-full bg-[#2a2a2a] dark:bg-[#2a2a2a]">
              <div
                className="progress h-1.5 rounded-full bg-[#1db954] transition-[width] duration-600 dark:bg-[#1db954]"
                style={{ width: `${pct}%` }}
                aria-label={t("profile:nowPlaying.progress")}
                role="progressbar"
                aria-valuenow={pct}
                aria-valuemin={0}
                aria-valuemax={100}
              />
            </div>
            <span className="np-time whitespace-nowrap text-xs text-[#b3b3b3]">
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
    <div className="glass grid min-h-[44px] grid-cols-[14px_1fr] items-center gap-3 rounded-lg border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,white_4%)] px-3 py-2.5 dark:border-[color:color-mix(in_srgb,white_8%,var(--nav-link)_92%)] dark:bg-[color:color-mix(in_srgb,var(--card-bg)_94%,transparent_6%)]">
      <div className="h-2 w-2 justify-self-center rounded-full bg-[color:var(--nav-link)] shadow-[0_0_0_3px_color-mix(in_srgb,var(--nav-link)_22%,transparent)]" />
      <p className="leading-tight">
        <strong>{label}:</strong> {value}
      </p>
    </div>
  )
}

const AutoHideSnackbar = ({
  snack,
  onClose,
}: {
  snack: SnackState
  onClose: () => void
}) => {
  useEffect(() => {
    const timer = setTimeout(() => {
      onClose()
    }, 2600)
    return () => clearTimeout(timer)
  }, [snack, onClose])
  return null
}

export default function Profile() {
  const { user, loading, setUser } = useAuth()
  const [snack, setSnack] = useState<SnackState | null>(null)
  const [avatarVersion, setAvatarVersion] = useState(Date.now())
  const [coverVersion, setCoverVersion] = useState(Date.now())
  const [reduceMotion, setReduceMotion] = useState(() =>
    typeof window !== "undefined" ? window.matchMedia("(prefers-reduced-motion: reduce)").matches : false
  )
  const [isTwoCol, setIsTwoCol] = useState(() =>
    typeof window !== "undefined" ? window.matchMedia("(min-width:1400px)").matches : false
  )
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== "undefined" ? window.matchMedia("(max-width:600px)").matches : false
  )
  const reduced = useReducedMotion()

  useEffect(() => {
    if (typeof window === "undefined") return
    const mediaQueries = [
      { query: window.matchMedia("(prefers-reduced-motion: reduce)"), setter: setReduceMotion },
      { query: window.matchMedia("(min-width:1400px)"), setter: setIsTwoCol },
      { query: window.matchMedia("(max-width:600px)"), setter: setIsMobile },
    ]
    const handlers = mediaQueries.map(({ query, setter }) => {
      const handler = (e: MediaQueryListEvent) => setter(e.matches)
      setter(query.matches)
      query.addEventListener("change", handler)
      return () => query.removeEventListener("change", handler)
    })
    return () => handlers.forEach((cleanup) => cleanup())
  }, [])
  const { t } = useTranslation(["profile", "common"])
  const [scrollY, setScrollY] = useState(0)
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
  const [accordionOpen, setAccordionOpen] = useState(true)

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
    if (typeof window === "undefined") return
    const onScroll = () => setScrollY(window.scrollY || 0)
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [])
  const coverParallax = reduceMotion ? 0 : Math.min(scrollY * 0.1, 40)
  const coverScale = reduceMotion ? 1 : Math.min(1 + scrollY * 0.00014, 1.04)

  useEffect(() => {
    if (typeof window === "undefined") return
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

  // Close modals on Escape key
  useEffect(() => {
    if (typeof window === "undefined") return
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (qrOpen) closeQrModal()
        if (achOpen) setAchOpen(null)
      }
    }
    if (qrOpen || achOpen) {
      window.addEventListener("keydown", handleEscape)
      return () => window.removeEventListener("keydown", handleEscape)
    }
  }, [qrOpen, achOpen, closeQrModal])

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
      <div className="flex min-h-[70vh] items-center justify-center">
        <div className="h-12 w-12 animate-spin rounded-full border-4 border-[color:var(--nav-link)] border-t-transparent" />
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
      {/* Background */}
      <div
        className="fixed inset-0 -z-[2] bg-cover bg-center bg-fixed"
        style={{
          backgroundImage: `url(${profileBg})`,
        }}
      >
        <div className="absolute inset-0 bg-gradient-to-br from-[color:color-mix(in_srgb,var(--nav-link)_66%,transparent)] via-[color:color-mix(in_srgb,var(--nav-link-hover)_60%,transparent)] to-transparent mix-blend-multiply dark:from-[color:color-mix(in_srgb,var(--nav-link)_66%,transparent)] dark:via-[color:color-mix(in_srgb,var(--nav-link-hover)_60%,transparent)]" />
        <div className="absolute inset-0 bg-[radial-gradient(1600px_800px_at_50%_0%,color-mix(in_srgb,var(--nav-link)_8%,transparent)_0%,transparent_60%)] opacity-60" />
      </div>

      <PageFadeIn>
        <motion.div
          initial={isTest ? false : { opacity: reduceMotion ? 1 : 0.96, y: reduceMotion ? 0 : 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={isTest ? { duration: 0 } : { type: "spring", stiffness: 460, damping: 34 }}
        >
          <main
            id="main"
            className="profile-page relative z-0 flex min-h-screen flex-col px-3 py-16 sm:px-4 sm:py-20 md:px-6 md:py-24"
            data-testid="profile-root"
            aria-label={t("profile:aria.page")}
          >
            <div className="relative z-0 mx-auto w-full max-w-7xl">
              <motion.div
                ref={containerRef}
                className="glass profile-card relative overflow-hidden rounded-ue-xl px-6 py-10 sm:px-9 sm:py-12 md:px-12 md:py-16 lg:px-14"
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
                <div className="grid grid-cols-1 items-start gap-6 md:grid-cols-[minmax(360px,420px)_minmax(0,1fr)] md:gap-8">
                  {/* Left Column */}
                  <div className="flex flex-col gap-8 md:gap-10">
                    {/* Hero Card */}
                    <div
                      className="glass relative flex min-h-[300px] items-end justify-center overflow-hidden rounded-ue-xl shadow-[0_28px_70px_-44px_rgba(0,0,0,0.2)] dark:shadow-[0_28px_70px_-44px_rgba(0,0,0,0.58)] sm:min-h-[340px] md:min-h-[360px] lg:min-h-[400px]"
                      style={{ paddingBottom: heroPaddingBottom }}
                    >
                      {/* Cover Image */}
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
                      {/* Gradient Overlay */}
                      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-[rgba(6,9,20,0.9)]" />
                      {/* Avatar */}
                      <div
                        className="absolute left-1/2 top-12 flex -translate-x-1/2 items-center justify-center rounded-full p-1 sm:top-14 md:top-16"
                        style={{
                          width: avatarSize,
                          height: avatarSize,
                          animation: reduceMotion
                            ? "none"
                            : "auraPulse 14s ease-in-out infinite",
                        }}
                      >
                        <div className="avatar-ring h-full w-full">
                          <img
                            src={avatarImageUrl}
                            alt={user?.full_name ?? undefined}
                            onError={handleAvatarImgError}
                            loading="lazy"
                            decoding="async"
                            referrerPolicy="no-referrer"
                            className="h-full w-full rounded-full object-cover text-[clamp(28px,6vw,64px)]"
                            style={{
                              backgroundColor: "rgba(255,255,255,0.12)",
                              color: "rgba(255,255,255,0.92)",
                            }}
                          />
                          {!user?.avatar_url && (
                            <div className="flex h-full w-full items-center justify-center rounded-full bg-[rgba(255,255,255,0.12)] text-[clamp(28px,6vw,64px)] text-[rgba(255,255,255,0.92)]">
                              {user?.full_name?.[0]}
                            </div>
                          )}
                        </div>
                        {/* Online Status */}
                        {isOnline && (
                          <div
                            className="absolute rounded-full bg-[#22c55e] shadow-[0_0_0_2px_rgba(0,0,0,0.18),0_4px_10px_rgba(34,197,94,0.45)]"
                            style={{
                              right: `${statusOffset}px`,
                              bottom: `${statusOffset}px`,
                              width: `${statusSize}px`,
                              height: `${statusSize}px`,
                              zIndex: 3,
                            }}
                          >
                            {!reduced && (
                              <div
                                className="absolute inset-[-6px] rounded-full border-2 border-[rgba(34,197,94,0.45)]"
                                style={{
                                  animation: "onlinePulse 1.8s ease-in-out infinite",
                                }}
                              />
                            )}
                          </div>
                        )}
                      </div>
                      {/* Text Content */}
                      <div
                        className="relative z-[2] flex w-full flex-col gap-6 px-6 sm:px-8 md:px-9"
                        style={{ paddingTop: heroTextPaddingTop }}
                      >
                        <div className="text-center md:text-left">
                          <h1
                            className="profile-name text-[clamp(1.7rem,3.2vw,2.9rem)] font-black leading-[1.08]"
                            data-testid="profile-name"
                          >
                            {user!.full_name}
                          </h1>
                          {!!user?.position && user?.role === "teacher" && (
                            <p className="profile-subtitle mt-2 font-semibold text-[color:var(--secondary-text)] dark:text-[#c9d2df]">
                              {user.position}
                            </p>
                          )}
                        </div>
                        <div className="flex flex-wrap justify-center gap-3 md:justify-start">
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
                              className="glass--chip rounded-full border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,white_4%)] px-4 py-1.5 text-xs font-bold uppercase tracking-wide text-[color:var(--nav-text)] backdrop-blur-xl dark:border-[color:color-mix(in_srgb,white_8%,var(--nav-link)_92%)] dark:bg-[color:color-mix(in_srgb,var(--card-bg)_94%,transparent_6%)]"
                              style={{
                                animation: reduced
                                  ? "none"
                                  : "chipHighlight 12s ease-in-out infinite",
                                animationDelay: reduced ? "0ms" : `${idx * 90}ms`,
                              }}
                            >
                              {chip}
                            </motion.span>
                          ))}
                        </div>
                      </div>
                    </div>

                    {/* Contact Card */}
                    <div className="glass profile-card flex flex-col gap-6 rounded-ue-lg p-6 sm:p-8">
                      <div className="flex flex-col gap-3">
                        <button
                          onClick={openQrModal}
                          data-testid="open-qr"
                          className="glass--btn w-full rounded-lg bg-[color:var(--nav-link)] py-3 text-base font-extrabold tracking-wider text-white transition-all duration-200 hover:bg-[color:var(--nav-link-hover)] hover:shadow-lg active:scale-[0.98] dark:bg-[color:var(--nav-link)] dark:hover:bg-[color:var(--nav-link-hover)]"
                        >
                          {t("profile:buttons.showQr")}
                        </button>
                      </div>
                      <div className="h-px bg-gradient-to-r from-[color:var(--nav-link)] to-transparent opacity-90" />
                      <div className="contact-links flex flex-col gap-4">
                        {/* Email */}
                        <div className="flex items-center justify-between gap-4 flex-wrap">
                          <div className="flex min-w-0 flex-1 items-center gap-2">
                            <svg
                              className="h-5 w-5 shrink-0 text-[color:var(--nav-link)]"
                              fill="currentColor"
                              viewBox="0 0 24 24"
                              aria-hidden
                            >
                              <path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z" />
                            </svg>
                            <a
                              href={`mailto:${user!.email}`}
                              className="min-w-0 flex-1 break-words font-extrabold text-[color:inherit] no-underline hover:text-[color:var(--nav-link-hover)]"
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
                            className={cn(
                              "glass--btn flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-all duration-200",
                              !reduced && "hover:-translate-y-0.5 hover:scale-105"
                            )}
                          >
                            <svg
                              className="h-4 w-4"
                              fill="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z" />
                            </svg>
                          </button>
                        </div>

                        {/* Telegram */}
                        {!!user!.telegram && (
                          <div className="flex items-center justify-between gap-4 flex-wrap">
                            <div className="flex min-w-0 flex-1 items-center gap-2">
                              <svg
                                className="h-5 w-5 shrink-0 text-[color:var(--nav-link)]"
                                fill="currentColor"
                                viewBox="0 0 24 24"
                                aria-hidden
                              >
                                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69a.2.2 0 00-.05-.18c-.06-.05-.14-.03-.21-.02-.09.02-1.49.95-4.22 2.79-.4.27-.76.41-1.08.4-.36-.01-1.04-.2-1.55-.37-.63-.2-1.12-.31-1.08-.66.02-.18.27-.36.74-.55 2.92-1.27 4.86-2.11 5.83-2.51 2.78-1.16 3.35-1.36 3.73-1.36.08 0 .27.02.39.12.1.08.13.19.14.27-.01.06.01.24 0 .38z" />
                              </svg>
                              <a
                                href={telegramHref}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="min-w-0 flex-1 break-words font-extrabold text-[color:inherit] no-underline hover:text-[color:var(--nav-link-hover)]"
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
                              className={cn(
                                "glass--btn flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-all duration-200",
                                !reduced && "hover:-translate-y-0.5 hover:scale-105"
                              )}
                            >
                              <svg
                                className="h-4 w-4"
                                fill="currentColor"
                                viewBox="0 0 24 24"
                              >
                                <path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z" />
                              </svg>
                            </button>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Now Playing */}
                    {showNowPlaying && nowPlaying && (
                      <motion.div
                        initial={isTest || reduced ? false : { opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ duration: isTest || reduced ? 0 : 0.72 }}
                        className="flex flex-col gap-3"
                      >
                        <p className="text-[0.65rem] font-semibold uppercase tracking-[2.2px] text-[color:var(--secondary-text)]">
                          {t("profile:sections.nowPlaying")}
                        </p>
                        <NowPlayingCard data={nowPlaying} />
                      </motion.div>
                    )}
                  </div>

                  {/* Right Column */}
                  <div
                    className="relative w-full"
                    style={{
                      marginTop: isMobile ? `${Math.round(avatarPx * 0.55) + 36}px` : 0,
                    }}
                  >
                    {edit ? (
                      <div className="glass profile-card profile-edit w-full rounded-ue-lg p-6 sm:p-8 md:p-10">
                        <div className="flex flex-col gap-5">
                          {/* Name */}
                          <div className="flex flex-col gap-1.5">
                            <label className="text-sm font-semibold text-[color:var(--page-text)]">
                              {t("profile:form.name")}
                            </label>
                            <input
                              type="text"
                              value={fullName}
                              onChange={(e) => setFullName(e.target.value)}
                              maxLength={120}
                              className="glass--btn h-12 rounded-xl border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[color:var(--card-bg)] px-4 text-[color:var(--page-text)] transition-all focus:border-[color:var(--nav-link)] focus:outline-none focus:ring-2 focus:ring-[color:var(--nav-link)] focus:ring-opacity-30 dark:border-[color:color-mix(in_srgb,white_8%,var(--nav-link)_92%)]"
                            />
                          </div>
                          {/* Email */}
                          <div className="flex flex-col gap-1.5">
                            <label className="text-sm font-semibold text-[color:var(--page-text)]">
                              {t("profile:form.email")}
                            </label>
                            <input
                              type="email"
                              value={email}
                              onChange={(e) => setEmail(e.target.value)}
                              className="glass--btn h-12 rounded-xl border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[color:var(--card-bg)] px-4 text-[color:var(--page-text)] transition-all focus:border-[color:var(--nav-link)] focus:outline-none focus:ring-2 focus:ring-[color:var(--nav-link)] focus:ring-opacity-30 dark:border-[color:color-mix(in_srgb,white_8%,var(--nav-link)_92%)]"
                            />
                          </div>
                          {/* Telegram */}
                          <div className="flex flex-col gap-1.5">
                            <label className="text-sm font-semibold text-[color:var(--page-text)]">
                              {t("profile:form.telegram")}
                            </label>
                            <input
                              type="text"
                              value={telegram}
                              onChange={(e) => setTelegram(e.target.value)}
                              className="glass--btn h-12 rounded-xl border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[color:var(--card-bg)] px-4 text-[color:var(--page-text)] transition-all focus:border-[color:var(--nav-link)] focus:outline-none focus:ring-2 focus:ring-[color:var(--nav-link)] focus:ring-opacity-30 dark:border-[color:color-mix(in_srgb,white_8%,var(--nav-link)_92%)]"
                            />
                            <p className="text-xs text-[color:var(--secondary-text)]">
                              {t("profile:form.telegramHint")}
                            </p>
                          </div>
                          {/* Teacher Fields */}
                          {user!.role === "teacher" && (
                            <>
                              <div className="flex flex-col gap-1.5">
                                <label className="text-sm font-semibold text-[color:var(--page-text)]">
                                  {t("profile:form.department")}
                                </label>
                                <input
                                  type="text"
                                  value={department}
                                  onChange={(e) => setDepartment(e.target.value)}
                                  className="glass--btn h-12 rounded-xl border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[color:var(--card-bg)] px-4 text-[color:var(--page-text)] transition-all focus:border-[color:var(--nav-link)] focus:outline-none focus:ring-2 focus:ring-[color:var(--nav-link)] focus:ring-opacity-30 dark:border-[color:color-mix(in_srgb,white_8%,var(--nav-link)_92%)]"
                                />
                              </div>
                              <div className="flex flex-col gap-1.5">
                                <label className="text-sm font-semibold text-[color:var(--page-text)]">
                                  {t("profile:form.position")}
                                </label>
                                <input
                                  type="text"
                                  value={position}
                                  onChange={(e) => setPosition(e.target.value)}
                                  className="glass--btn h-12 rounded-xl border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[color:var(--card-bg)] px-4 text-[color:var(--page-text)] transition-all focus:border-[color:var(--nav-link)] focus:outline-none focus:ring-2 focus:ring-[color:var(--nav-link)] focus:ring-opacity-30 dark:border-[color:color-mix(in_srgb,white_8%,var(--nav-link)_92%)]"
                                />
                              </div>
                            </>
                          )}
                          {/* Student Fields */}
                          {user!.role === "student" && (
                            <>
                              <div className="flex flex-col gap-1.5">
                                <label className="text-sm font-semibold text-[color:var(--page-text)]">
                                  {t("profile:form.about")}
                                </label>
                                <textarea
                                  value={about}
                                  onChange={(e) => setAbout(e.target.value)}
                                  rows={3}
                                  className="glass--btn min-h-[80px] rounded-xl border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[color:var(--card-bg)] px-4 py-3 text-[color:var(--page-text)] transition-all focus:border-[color:var(--nav-link)] focus:outline-none focus:ring-2 focus:ring-[color:var(--nav-link)] focus:ring-opacity-30 dark:border-[color:color-mix(in_srgb,white_8%,var(--nav-link)_92%)]"
                                />
                              </div>
                              <div className="flex flex-col gap-1.5">
                                <label className="text-sm font-semibold text-[color:var(--page-text)]">
                                  {t("profile:form.recordBookNumber")}
                                </label>
                                <input
                                  type="text"
                                  value={recordBookNumber}
                                  onChange={(e) => setRecordBookNumber(e.target.value)}
                                  className="glass--btn h-12 rounded-xl border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[color:var(--card-bg)] px-4 text-[color:var(--page-text)] transition-all focus:border-[color:var(--nav-link)] focus:outline-none focus:ring-2 focus:ring-[color:var(--nav-link)] focus:ring-opacity-30 dark:border-[color:color-mix(in_srgb,white_8%,var(--nav-link)_92%)]"
                                />
                              </div>
                              <div className="flex flex-col gap-1.5">
                                <label className="text-sm font-semibold text-[color:var(--page-text)]">
                                  {t("profile:form.status")}
                                </label>
                                <input
                                  type="text"
                                  value={status}
                                  onChange={(e) => setStatus(e.target.value)}
                                  className="glass--btn h-12 rounded-xl border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[color:var(--card-bg)] px-4 text-[color:var(--page-text)] transition-all focus:border-[color:var(--nav-link)] focus:outline-none focus:ring-2 focus:ring-[color:var(--nav-link)] focus:ring-opacity-30 dark:border-[color:color-mix(in_srgb,white_8%,var(--nav-link)_92%)]"
                                />
                              </div>
                              <div className="flex flex-col gap-1.5">
                                <label className="text-sm font-semibold text-[color:var(--page-text)]">
                                  {t("profile:form.institute")}
                                </label>
                                <input
                                  type="text"
                                  value={institute}
                                  onChange={(e) => setInstitute(e.target.value)}
                                  className="glass--btn h-12 rounded-xl border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[color:var(--card-bg)] px-4 text-[color:var(--page-text)] transition-all focus:border-[color:var(--nav-link)] focus:outline-none focus:ring-2 focus:ring-[color:var(--nav-link)] focus:ring-opacity-30 dark:border-[color:color-mix(in_srgb,white_8%,var(--nav-link)_92%)]"
                                />
                              </div>
                              <div className="flex flex-col gap-1.5">
                                <label className="text-sm font-semibold text-[color:var(--page-text)]">
                                  {t("profile:form.course")}
                                </label>
                                <input
                                  type="text"
                                  value={course}
                                  onChange={(e) => setCourse(e.target.value)}
                                  className="glass--btn h-12 rounded-xl border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[color:var(--card-bg)] px-4 text-[color:var(--page-text)] transition-all focus:border-[color:var(--nav-link)] focus:outline-none focus:ring-2 focus:ring-[color:var(--nav-link)] focus:ring-opacity-30 dark:border-[color:color-mix(in_srgb,white_8%,var(--nav-link)_92%)]"
                                />
                              </div>
                              <div className="flex flex-col gap-1.5">
                                <label className="text-sm font-semibold text-[color:var(--page-text)]">
                                  {t("profile:form.educationLevel")}
                                </label>
                                <input
                                  type="text"
                                  value={educationLevel}
                                  onChange={(e) => setEducationLevel(e.target.value)}
                                  className="glass--btn h-12 rounded-xl border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[color:var(--card-bg)] px-4 text-[color:var(--page-text)] transition-all focus:border-[color:var(--nav-link)] focus:outline-none focus:ring-2 focus:ring-[color:var(--nav-link)] focus:ring-opacity-30 dark:border-[color:color-mix(in_srgb,white_8%,var(--nav-link)_92%)]"
                                />
                              </div>
                              <div className="flex flex-col gap-1.5">
                                <label className="text-sm font-semibold text-[color:var(--page-text)]">
                                  {t("profile:form.track")}
                                </label>
                                <input
                                  type="text"
                                  value={track}
                                  onChange={(e) => setTrack(e.target.value)}
                                  className="glass--btn h-12 rounded-xl border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[color:var(--card-bg)] px-4 text-[color:var(--page-text)] transition-all focus:border-[color:var(--nav-link)] focus:outline-none focus:ring-2 focus:ring-[color:var(--nav-link)] focus:ring-opacity-30 dark:border-[color:color-mix(in_srgb,white_8%,var(--nav-link)_92%)]"
                                />
                              </div>
                              <div className="flex flex-col gap-1.5">
                                <label className="text-sm font-semibold text-[color:var(--page-text)]">
                                  {t("profile:form.program")}
                                </label>
                                <input
                                  type="text"
                                  value={program}
                                  onChange={(e) => setProgram(e.target.value)}
                                  className="glass--btn h-12 rounded-xl border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[color:var(--card-bg)] px-4 text-[color:var(--page-text)] transition-all focus:border-[color:var(--nav-link)] focus:outline-none focus:ring-2 focus:ring-[color:var(--nav-link)] focus:ring-opacity-30 dark:border-[color:color-mix(in_srgb,white_8%,var(--nav-link)_92%)]"
                                />
                              </div>
                              <div className="flex flex-col gap-1.5">
                                <label className="text-sm font-semibold text-[color:var(--page-text)]">
                                  {t("profile:form.achievements")}
                                </label>
                                <textarea
                                  value={achievements}
                                  onChange={(e) => setAchievements(e.target.value)}
                                  rows={2}
                                  className="glass--btn min-h-[60px] rounded-xl border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[color:var(--card-bg)] px-4 py-3 text-[color:var(--page-text)] transition-all focus:border-[color:var(--nav-link)] focus:outline-none focus:ring-2 focus:ring-[color:var(--nav-link)] focus:ring-opacity-30 dark:border-[color:color-mix(in_srgb,white_8%,var(--nav-link)_92%)]"
                                />
                              </div>
                            </>
                          )}
                          {/* Action Buttons */}
                          <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
                            <button
                              onClick={handleSave}
                              disabled={saving}
                              className="glass--btn flex-1 rounded-xl bg-[color:var(--nav-link)] px-6 py-3 text-base font-extrabold text-white transition-all hover:bg-[color:var(--nav-link-hover)] hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98] sm:flex-none dark:bg-[color:var(--nav-link)] dark:hover:bg-[color:var(--nav-link-hover)]"
                            >
                              {saving ? t("profile:form.saving") : t("profile:form.save")}
                            </button>
                            <button
                              onClick={handleCancel}
                              className="glass--btn flex-1 rounded-xl border-2 border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-transparent px-6 py-3 text-base font-extrabold text-[color:var(--page-text)] transition-all hover:bg-[color:color-mix(in_srgb,var(--nav-link)_8%,transparent)] active:scale-[0.98] sm:flex-none dark:border-[color:color-mix(in_srgb,white_8%,var(--nav-link)_92%)]"
                            >
                              {t("profile:form.cancel")}
                            </button>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="glass profile-card w-full rounded-ue-lg p-6 sm:p-8 md:p-10">
                        <h2 className="mb-6 text-[clamp(1.3rem,2.3vw,1.8rem)] font-black tracking-[-0.01em] text-[color:var(--page-text)]">
                          {t("profile:sections.details")}
                        </h2>
                        {/* Accordion */}
                        <div className="glass rounded-ue-lg border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,white_4%)] dark:border-[color:color-mix(in_srgb,white_8%,var(--nav-link)_92%)] dark:bg-[color:color-mix(in_srgb,var(--card-bg)_94%,transparent_6%)]">
                          <button
                            onClick={() => setAccordionOpen(!accordionOpen)}
                            className="flex w-full items-center justify-between border-b border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] px-5 py-4 text-left dark:border-[color:color-mix(in_srgb,white_8%,var(--nav-link)_92%)]"
                          >
                            <h3 className="font-black text-[color:var(--page-text)]">
                              {t("profile:sections.profileDetails")}
                            </h3>
                            <svg
                              className={cn(
                                "h-5 w-5 transition-transform duration-200",
                                accordionOpen && "rotate-180"
                              )}
                              fill="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path d="M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6 1.41-1.41z" />
                            </svg>
                          </button>
                          {accordionOpen && (
                            <div className="px-4 py-5 sm:px-5 sm:py-6">
                              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 md:gap-4">
                                {[
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
                                ].map((r) => (
                                  <DetailRow key={r.label} label={r.label} value={r.value} />
                                ))}
                              </div>
                              {achievementsList.length > 0 && (
                                <div className="mt-6">
                                  <h3 className="mb-4 text-lg font-extrabold text-[color:var(--page-text)]">
                                    {t("profile:sections.achievements")}
                                  </h3>
                                  <div className="grid grid-cols-[repeat(auto-fit,minmax(140px,1fr))] gap-3 sm:grid-cols-[repeat(auto-fit,minmax(160px,1fr))]">
                                    {achievementsList.map((ach, idx) => (
                                      <motion.button
                                        key={ach.key}
                                        initial={isTest || reduced ? false : { opacity: 0, scale: 0.9 }}
                                        animate={{ opacity: 1, scale: 1 }}
                                        transition={{
                                          duration: isTest || reduced ? 0 : 0.5,
                                          delay: reduced ? 0 : idx * 0.09,
                                        }}
                                        onClick={() =>
                                          setAchOpen({
                                            name: ach.name,
                                            issuer: ach.issuer,
                                            date: ach.date,
                                            url: ach.url,
                                          })
                                        }
                                        className="glass--chip block w-full rounded-lg border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,white_4%)] px-4 py-3 text-left text-sm font-bold leading-tight text-[color:var(--page-text)] transition-all hover:scale-[1.02] dark:border-[color:color-mix(in_srgb,white_8%,var(--nav-link)_92%)] dark:bg-[color:color-mix(in_srgb,var(--card-bg)_94%,transparent_6%)]"
                                        style={{
                                          animation: reduced
                                            ? "none"
                                            : "chipHighlight 14s ease-in-out infinite",
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
                      </div>
                    )}
                  </div>
                </div>
              </motion.div>
            </div>

            {/* Confetti Canvas */}
            <canvas
              ref={confettiRef}
              className="pointer-events-none fixed left-0 top-0 z-[2147483000] h-screen w-screen"
            />
          </main>
        </motion.div>
      </PageFadeIn>

      {/* QR Dialog */}
      {qrOpen && (
        <div
          className="fixed inset-0 z-[2500] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
          onClick={closeQrModal}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            onClick={(e) => e.stopPropagation()}
            className="glass w-full max-w-xs rounded-ue-xl p-6"
          >
            <h2 className="mb-6 text-center text-xl font-black tracking-wide text-[color:var(--page-text)]">
              {t("profile:dialog.qr.title")}
            </h2>
            <div className="flex min-h-[320px] flex-col items-center justify-center gap-3">
              <div className="rounded-xl border border-[color:color-mix(in_srgb,var(--nav-link)_15%,transparent)] bg-white p-4 shadow-[0_18px_40px_-28px_rgba(0,0,0,0.4)] dark:border-[color:color-mix(in_srgb,var(--nav-link)_15%,transparent)]">
                <QRCodeSVG
                  value={buildVCard()}
                  size={300}
                  level="H"
                  includeMargin
                  bgColor="#ffffff"
                  fgColor="#0f4faa"
                  imageSettings={{
                    src: typeof guuLogo === "string" ? guuLogo : String(guuLogo as any),
                    height: 56,
                    width: 56,
                    excavate: true,
                  }}
                />
              </div>
              <p className="text-xs text-[color:var(--secondary-text)]">
                {t("profile:dialog.qr.hint")}
              </p>
            </div>
            <div className="mt-6 flex justify-center">
              <button
                onClick={closeQrModal}
                className="glass--btn rounded-xl bg-[color:var(--nav-link)] px-6 py-3 text-base font-extrabold text-white transition-all hover:bg-[color:var(--nav-link-hover)] hover:shadow-lg active:scale-[0.98] dark:bg-[color:var(--nav-link)] dark:hover:bg-[color:var(--nav-link-hover)]"
              >
                {t("common:buttons.done")}
              </button>
            </div>
          </motion.div>
        </div>
      )}

      {/* Achievement Dialog */}
      {achOpen && (
        <div
          className="fixed inset-0 z-[2500] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
          onClick={() => setAchOpen(null)}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            onClick={(e) => e.stopPropagation()}
            className="glass w-full max-w-xs rounded-ue-xl p-6"
          >
            <h2 className="mb-4 text-xl font-black text-[color:var(--page-text)]">
              {achOpen.name}
            </h2>
            <div className="mb-6 flex flex-col gap-3">
              {achOpen.issuer && (
                <p className="text-[color:var(--page-text)]">
                  {t("profile:dialog.achievement.organizer", { issuer: achOpen.issuer })}
                </p>
              )}
              {achOpen.date && (
                <p className="text-[color:var(--page-text)]">
                  {t("profile:dialog.achievement.date", { date: achOpen.date })}
                </p>
              )}
              {achOpen.url && (
                <a
                  href={achOpen.url}
                  target="_blank"
                  rel="noreferrer"
                  className="glass--btn inline-block rounded-xl border-2 border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-transparent px-6 py-3 text-center text-base font-extrabold text-[color:var(--page-text)] transition-all hover:bg-[color:color-mix(in_srgb,var(--nav-link)_8%,transparent)] active:scale-[0.98] dark:border-[color:color-mix(in_srgb,white_8%,var(--nav-link)_92%)]"
                >
                  {t("profile:dialog.achievement.openLink")}
                </a>
              )}
            </div>
            <div className="flex justify-end">
              <button
                onClick={() => setAchOpen(null)}
                className="glass--btn rounded-xl bg-[color:var(--nav-link)] px-6 py-3 text-base font-extrabold text-white transition-all hover:bg-[color:var(--nav-link-hover)] hover:shadow-lg active:scale-[0.98] dark:bg-[color:var(--nav-link)] dark:hover:bg-[color:var(--nav-link-hover)]"
              >
                {t("profile:dialog.achievement.close")}
              </button>
            </div>
          </motion.div>
        </div>
      )}

      {/* Snackbar */}
      {snack && (
        <>
          <AutoHideSnackbar snack={snack} onClose={() => setSnack(null)} />
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className="fixed bottom-6 left-1/2 z-[4000] -translate-x-1/2"
            data-testid={snack.key === "copied" ? "snackbar-copied" : undefined}
          >
            <div
              className={cn(
                "flex items-center rounded-xl px-6 py-4 text-sm font-semibold shadow-lg",
                snack.sev === "success" &&
                  "bg-gradient-to-b from-[#2e7d32] to-[#1b5e20] text-[#e9ffef]",
                snack.sev === "error" &&
                  "bg-gradient-to-b from-[#d32f2f] to-[#b71c1c] text-[#fff5f5]",
                snack.sev === "info" &&
                  "bg-gradient-to-b from-[#005ea2] to-[#1a4480] text-[#eaf4ff]",
                snack.sev === "warning" &&
                  "bg-gradient-to-b from-[#f59e0b] to-[#b45309] text-[#fff8e1]"
              )}
            >
              <span>{snackMessage}</span>
              <button
                onClick={() => setSnack(null)}
                className="ml-4 text-current opacity-80 hover:opacity-100"
                aria-label="Close"
              >
                ×
              </button>
            </div>
          </motion.div>
        </>
      )}
    </>
  )
}
