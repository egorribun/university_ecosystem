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
import { cn } from "@/utils/cn"

const isTest = typeof import.meta !== "undefined" && import.meta.env.MODE === "test"

type SnackKey = "spotifyConnected" | "spotifyError" | "copied" | "profileUpdated" | "error"

type SnackState = {
  key?: SnackKey
  message?: string
  sev?: "success" | "info" | "warning" | "error"
}

export const NowPlayingCard = memo(function NowPlayingCard({ data }: { data: NowPlaying }) {
  const reduced = useReducedMotion()
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

  const shouldAnimate = !isTest && data.is_playing && !reduced && duration > 0

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
        initial={isTest || reduced ? false : { y: 12, opacity: 0.94, scale: 1 }}
        animate={{ y: 0, opacity: 1, scale: 1 }}
        whileHover={reduced ? {} : { y: -1, scale: 1.002 }}
        whileTap={reduced ? {} : { scale: 0.997 }}
        transition={
          isTest ? { duration: 0 } : { type: "spring", stiffness: 520, damping: 36, mass: 0.9 }
        }
        className="relative grid w-full grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2 overflow-hidden rounded-3xl border border-[#1db95433] bg-[#121212] px-4 py-4 shadow-[0_8px_20px_rgba(0,0,0,0.35)] transition-all duration-300"
      >
        <div className="relative h-14 w-14 overflow-hidden rounded-2xl shadow-[0_8px_20px_rgba(0,0,0,0.35)]">
          <img
            src={data.album_image_url ?? ""}
            alt={data.album_name || data.track_name || t("profile:nowPlaying.albumFallback")}
            loading="lazy"
            decoding="async"
            referrerPolicy="no-referrer"
            className={cn(
              "h-full w-full rounded-2xl object-cover",
              !reduced &&
                "scale-[1.012] transition-transform duration-[900ms] ease-out hover:scale-[1.02]"
            )}
          />
        </div>
        <div className="flex min-w-0 flex-col gap-2" aria-live="polite">
          <h3 className="text-base font-extrabold leading-tight tracking-tight text-white">
            {data.track_name || "—"}
          </h3>
          <p className="text-sm text-[#b3b3b3] opacity-90">{data.artists.join(", ")}</p>
          {!data.is_playing && (
            <span className="inline-flex w-fit items-center rounded-full border border-gray-600 bg-gray-800 px-3 py-1 text-xs font-bold uppercase text-gray-300">
              {t("profile:nowPlaying.paused")}
            </span>
          )}
          <div className="flex w-full items-center gap-2">
            <div
              className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-[#2a2a2a]"
              role="progressbar"
              aria-label={t("profile:nowPlaying.progress")}
              aria-valuenow={Math.round(pct)}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div
                className="h-full rounded-full bg-[#1db954] transition-all"
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="whitespace-nowrap text-xs text-[#b3b3b3]">
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
    <div className="group flex min-h-[48px] items-center gap-4 rounded-2xl border border-glass-border bg-gradient-to-br from-glass-tint1/50 via-glass-tint2/30 to-transparent px-5 py-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.1)] backdrop-blur-sm transition-all duration-300 hover:-translate-y-0.5 hover:border-nav-link/40 hover:shadow-[0_8px_24px_rgba(0,94,162,0.18)] dark:border-glass-border/60 dark:from-glass-tint1/40 dark:via-glass-tint2/20 dark:hover:border-nav-link-hover/50 dark:hover:shadow-[0_8px_24px_rgba(127,182,230,0.15)]">
      <div className="flex h-2.5 w-2.5 shrink-0 items-center justify-center">
        <div className="h-2.5 w-2.5 rounded-full bg-nav-link shadow-[0_0_0_4px_rgba(15,79,170,0.18)] transition-all duration-300 group-hover:scale-110 group-hover:shadow-[0_0_0_6px_rgba(15,79,170,0.25)] dark:bg-nav-link-hover dark:shadow-[0_0_0_4px_rgba(127,182,230,0.22)] dark:group-hover:shadow-[0_0_0_6px_rgba(127,182,230,0.35)]" />
      </div>
      <p className="flex-1 text-sm leading-relaxed text-page-foreground">
        <span className="font-bold opacity-90">{label}:</span>{" "}
        <span className="font-medium opacity-95">{value}</span>
      </p>
    </div>
  )
}

export default function Profile() {
  const { user, loading, setUser } = useAuth()
  const [snack, setSnack] = useState<SnackState | null>(null)
  const [avatarVersion, setAvatarVersion] = useState(Date.now())
  const [coverVersion, setCoverVersion] = useState(Date.now())
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
      <div className="flex min-h-[70vh] items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-nav-link border-t-transparent" />
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

  const isOnline = ((user as any)?.is_online ?? (user as any)?.online ?? true) as boolean

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
        className="fixed inset-0 -z-10 bg-cover bg-center bg-fixed"
        style={{ backgroundImage: `url(${profileBg})` }}
      >
        <div className="absolute inset-0 bg-gradient-to-br from-[#0f4faa]/20 via-[#1a4480]/25 to-[#005ea2]/30 mix-blend-overlay dark:from-[#0a1524]/90 dark:via-[#0b2b47]/85 dark:to-[#0d2543]/80" />
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-page/60 to-page dark:via-page/70" />
        <div className="absolute inset-0 bg-[radial-gradient(1400px_700px_at_50%_10%,rgba(105,169,220,0.12)_0%,transparent_65%)] opacity-70 dark:opacity-40" />
      </div>

      <PageFadeIn>
        <motion.div
          initial={isTest ? false : { opacity: reduced ? 1 : 0.96, y: reduced ? 0 : 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={isTest ? { duration: 0 } : { type: "spring", stiffness: 460, damping: 34 }}
        >
          <main
            id="main"
            className="profile-page relative flex min-h-screen flex-col px-4 py-16 sm:px-6 sm:py-20 md:px-8 md:py-24 lg:py-28"
            data-testid="profile-root"
            aria-label={t("profile:aria.page")}
          >
            <div className="relative z-0 mx-auto w-full max-w-7xl">
              <motion.div
                ref={containerRef}
                className="glass profile-card relative overflow-hidden rounded-[2rem] px-6 py-10 backdrop-blur-xl sm:px-10 sm:py-12 md:rounded-[2.5rem] md:px-14 md:py-14 lg:px-20 lg:py-16"
                initial={
                  isTest ? false : { opacity: reduced ? 1 : 0.96, y: reduced ? 0 : 12, scale: 0.99 }
                }
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={
                  isTest
                    ? { duration: 0 }
                    : { type: "spring", stiffness: 480, damping: 32, mass: 0.8 }
                }
              >
                <div className="grid grid-cols-1 items-start gap-10 md:grid-cols-[minmax(340px,400px)_minmax(0,1fr)] md:gap-14 lg:gap-20">
                  {/* Left Column */}
                  <div className="flex flex-col gap-8 md:gap-10 lg:gap-12">
                    {/* Hero Card */}
                    <div className="glass relative flex min-h-[340px] flex-col items-center justify-end overflow-hidden rounded-[2rem] pb-20 shadow-[0_20px_60px_-20px_rgba(0,0,0,0.3)] transition-all duration-500 hover:shadow-[0_28px_80px_-20px_rgba(0,0,0,0.4)] sm:min-h-[380px] md:min-h-[400px] md:rounded-[2.5rem] lg:min-h-[440px] dark:shadow-[0_20px_60px_-20px_rgba(0,0,0,0.6)] dark:hover:shadow-[0_28px_80px_-20px_rgba(0,0,0,0.7)]">
                      <div
                        className="absolute inset-0 bg-cover bg-center transition-transform duration-[1400ms] ease-out"
                        style={{
                          backgroundImage: coverImageUrl ? `url(${coverImageUrl})` : undefined,
                          transform: `translateY(${coverParallax}px) scale(${coverScale})`,
                          filter: "saturate(1.05) contrast(1.03) brightness(0.96)",
                        }}
                      />
                      <div className="absolute inset-0 bg-gradient-to-b from-black/5 via-black/40 to-black/90 dark:from-black/10 dark:via-black/50 dark:to-black/95" />

                      {/* Avatar */}
                      <div className="absolute left-1/2 top-10 flex h-36 w-36 -translate-x-1/2 items-center justify-center rounded-full p-1 sm:top-12 sm:h-40 sm:w-40 md:h-44 md:w-44 lg:h-48 lg:w-48">
                        <div className="avatar-ring relative h-full w-full transition-all duration-500 hover:scale-105">
                          <img
                            src={avatarImageUrl}
                            alt={user?.full_name ?? undefined}
                            onError={handleAvatarImgError}
                            loading="lazy"
                            decoding="async"
                            referrerPolicy="no-referrer"
                            className="h-full w-full rounded-full object-cover text-4xl font-medium text-white/90 transition-all duration-300 md:text-5xl lg:text-6xl"
                          />
                          {isOnline && (
                            <div className="absolute bottom-2 right-2 z-10 h-5 w-5 rounded-full bg-[#22c55e] shadow-[0_0_0_3px_rgba(0,0,0,0.2),0_4px_12px_rgba(34,197,94,0.5)] transition-all duration-300 md:h-6 md:w-6">
                              {!reduced && (
                                <div className="absolute -inset-2 animate-[onlinePulse_1.8s_ease-in-out_infinite] rounded-full border-2 border-[#22c55e]/50" />
                              )}
                            </div>
                          )}
                        </div>
                      </div>

                      <div className="relative z-10 w-full px-6 pt-28 text-center sm:px-8 sm:pt-32 md:px-12 md:text-left lg:px-14">
                        <div className="flex flex-col gap-7">
                          <div className="space-y-3">
                            <h1
                              className="profile-name text-[clamp(1.85rem,3.5vw,3.2rem)] font-black leading-[1.1] tracking-tight drop-shadow-[0_2px_8px_rgba(0,0,0,0.4)]"
                              data-testid="profile-name"
                            >
                              {user!.full_name}
                            </h1>
                            {!!user?.position && user?.role === "teacher" && (
                              <p className="profile-subtitle mt-2.5 text-base font-semibold drop-shadow-[0_1px_4px_rgba(0,0,0,0.3)] sm:text-lg">
                                {user.position}
                              </p>
                            )}
                          </div>
                          <div className="flex flex-wrap items-center justify-center gap-3 md:justify-start">
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
                                initial={{ opacity: 0, scale: 0.92, y: 8 }}
                                animate={{ opacity: 1, scale: 1, y: 0 }}
                                transition={
                                  isTest || reduced
                                    ? { duration: 0 }
                                    : {
                                        delay: idx * 0.08,
                                        duration: 0.5,
                                        type: "spring",
                                        stiffness: 400,
                                        damping: 28,
                                      }
                                }
                                className="glass--chip inline-flex items-center rounded-full border border-glass-border/80 bg-glass/90 px-5 py-2.5 text-sm font-extrabold tracking-wide shadow-[0_4px_12px_rgba(0,0,0,0.15)] backdrop-blur-md transition-all duration-300 hover:-translate-y-0.5 hover:scale-105 hover:shadow-[0_8px_20px_rgba(0,0,0,0.2)] dark:border-glass-border/60 dark:bg-glass/80 dark:shadow-[0_4px_12px_rgba(0,0,0,0.3)]"
                              >
                                {chip}
                              </motion.span>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Contact Card */}
                    <div className="glass relative flex flex-col gap-7 overflow-hidden rounded-[2rem] bg-glass/60 p-7 backdrop-blur-xl shadow-[0_8px_24px_rgba(0,0,0,0.12)] transition-all duration-300 hover:shadow-[0_12px_32px_rgba(0,0,0,0.16)] sm:p-9 dark:bg-glass/50 dark:shadow-[0_8px_24px_rgba(0,0,0,0.3)]">
                      <button
                        onClick={openQrModal}
                        data-testid="open-qr"
                        className="glass--btn group relative flex w-full items-center justify-center overflow-hidden rounded-2xl border border-transparent bg-gradient-to-r from-nav-link to-nav-link/90 px-7 py-4 font-extrabold tracking-wide text-white shadow-[0_12px_28px_rgba(0,94,162,0.38)] transition-all duration-300 hover:-translate-y-1 hover:scale-[1.02] hover:shadow-[0_20px_40px_rgba(0,94,162,0.45)] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-nav-link/40 active:translate-y-0 active:scale-[0.98] dark:from-nav-link-hover dark:to-nav-link-hover/90 dark:shadow-[0_12px_28px_rgba(105,169,220,0.3)] dark:hover:shadow-[0_20px_40px_rgba(105,169,220,0.4)]"
                      >
                        <span className="relative z-10">{t("profile:buttons.showQr")}</span>
                        <div className="absolute inset-0 bg-gradient-to-r from-white/0 via-white/10 to-white/0 opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
                      </button>

                      <div className="h-px bg-gradient-to-r from-transparent via-nav-link/30 to-transparent dark:via-nav-link-hover/30" />

                      <div className="contact-links flex flex-col gap-6">
                        {/* Email */}
                        <div className="group flex items-center justify-between gap-5 rounded-2xl border border-glass-border/50 bg-glass/40 p-4 backdrop-blur-sm transition-all duration-300 hover:-translate-y-0.5 hover:border-nav-link/40 hover:bg-glass/60 hover:shadow-[0_8px_20px_rgba(0,94,162,0.15)] dark:border-glass-border/40 dark:bg-glass/30 dark:hover:border-nav-link-hover/40 dark:hover:shadow-[0_8px_20px_rgba(127,182,230,0.12)]">
                          <div className="flex min-w-0 flex-1 items-center gap-4">
                            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-nav-link/10 text-nav-link transition-all duration-300 group-hover:scale-110 group-hover:bg-nav-link/15 dark:bg-nav-link-hover/10 dark:text-nav-link-hover dark:group-hover:bg-nav-link-hover/15">
                              <svg
                                className="h-5 w-5"
                                fill="none"
                                viewBox="0 0 24 24"
                                stroke="currentColor"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth={2.5}
                                  d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
                                />
                              </svg>
                            </div>
                            <a
                              href={`mailto:${user!.email}`}
                              className="flex-1 overflow-hidden text-ellipsis break-words text-sm font-extrabold text-nav-link no-underline transition-all duration-300 hover:text-nav-link-hover sm:text-base dark:text-nav-link-hover"
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
                            className="glass--btn flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-glass-border/60 bg-glass/70 text-nav-link backdrop-blur-sm transition-all duration-300 hover:-translate-y-1 hover:scale-110 hover:border-nav-link/50 hover:shadow-lg focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-nav-link/30 active:translate-y-0 active:scale-100 dark:border-glass-border/50 dark:bg-glass/60 dark:text-nav-link-hover dark:hover:border-nav-link-hover/50"
                          >
                            <svg
                              className="h-5 w-5"
                              fill="none"
                              viewBox="0 0 24 24"
                              stroke="currentColor"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2.5}
                                d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
                              />
                            </svg>
                          </button>
                        </div>

                        {/* Telegram */}
                        {!!user!.telegram && (
                          <div className="group flex items-center justify-between gap-5 rounded-2xl border border-glass-border/50 bg-glass/40 p-4 backdrop-blur-sm transition-all duration-300 hover:-translate-y-0.5 hover:border-nav-link/40 hover:bg-glass/60 hover:shadow-[0_8px_20px_rgba(0,94,162,0.15)] dark:border-glass-border/40 dark:bg-glass/30 dark:hover:border-nav-link-hover/40 dark:hover:shadow-[0_8px_20px_rgba(127,182,230,0.12)]">
                            <div className="flex min-w-0 flex-1 items-center gap-4">
                              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[#0088cc]/10 text-[#0088cc] transition-all duration-300 group-hover:scale-110 group-hover:bg-[#0088cc]/15 dark:bg-[#2aabee]/10 dark:text-[#2aabee] dark:group-hover:bg-[#2aabee]/15">
                                <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24">
                                  <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.562 8.161c-.18 1.897-.962 6.502-1.359 8.627-.168.9-.5 1.201-.82 1.23-.697.064-1.226-.461-1.901-.903-1.056-.692-1.653-1.123-2.678-1.799-1.185-.781-.417-1.21.258-1.911.177-.184 3.247-2.977 3.307-3.23.007-.032.015-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.139-5.062 3.345-.479.329-.913.489-1.302.481-.428-.009-1.252-.241-1.865-.44-.751-.244-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.831-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635.099-.002.321.023.465.141.121.099.155.232.171.326.016.093.036.307.02.473z" />
                                </svg>
                              </div>
                              <a
                                href={telegramHref}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex-1 overflow-hidden text-ellipsis break-words text-sm font-extrabold text-nav-link no-underline transition-all duration-300 hover:text-nav-link-hover sm:text-base dark:text-nav-link-hover"
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
                              className="glass--btn flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-glass-border/60 bg-glass/70 text-nav-link backdrop-blur-sm transition-all duration-300 hover:-translate-y-1 hover:scale-110 hover:border-nav-link/50 hover:shadow-lg focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-nav-link/30 active:translate-y-0 active:scale-100 dark:border-glass-border/50 dark:bg-glass/60 dark:text-nav-link-hover dark:hover:border-nav-link-hover/50"
                            >
                              <svg
                                className="h-5 w-5"
                                fill="none"
                                viewBox="0 0 24 24"
                                stroke="currentColor"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth={2.5}
                                  d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
                                />
                              </svg>
                            </button>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Now Playing */}
                    {showNowPlaying && nowPlaying && (
                      <motion.div
                        initial={{ opacity: 0, y: 24, scale: 0.96 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        transition={
                          isTest || reduced
                            ? { duration: 0 }
                            : { duration: 0.6, type: "spring", stiffness: 400, damping: 28 }
                        }
                        className="flex flex-col gap-5"
                      >
                        <div className="flex items-center gap-3">
                          <div className="h-1 w-1 rounded-full bg-[#1db954]" />
                          <p className="text-xs font-extrabold uppercase tracking-[0.15em] text-secondary/90 dark:text-secondary/80">
                            {t("profile:sections.nowPlaying")}
                          </p>
                        </div>
                        <NowPlayingCard data={nowPlaying} />
                      </motion.div>
                    )}
                  </div>

                  {/* Right Column */}
                  <div className="relative mt-36 w-full md:mt-0">
                    {edit ? (
                      <div className="glass profile-edit relative w-full overflow-hidden rounded-[2rem] bg-glass/60 p-7 backdrop-blur-xl shadow-[0_8px_24px_rgba(0,0,0,0.12)] sm:p-9 md:rounded-[2.5rem] md:p-11 dark:bg-glass/50 dark:shadow-[0_8px_24px_rgba(0,0,0,0.3)]">
                        <div className="flex flex-col gap-6">
                          <input
                            type="text"
                            placeholder={t("profile:form.name")}
                            value={fullName}
                            onChange={(e) => setFullName(e.target.value)}
                            maxLength={120}
                            className="w-full rounded-2xl border border-glass-border/60 bg-surface/80 px-5 py-4 text-page-foreground placeholder-placeholder transition-all duration-300 focus:border-nav-link focus:bg-surface focus:outline-none focus:ring-4 focus:ring-nav-link/20 dark:border-glass-border/50 dark:bg-card-bg/80 dark:focus:border-nav-link-hover dark:focus:bg-card-bg dark:focus:ring-nav-link-hover/20"
                          />
                          <input
                            type="email"
                            placeholder={t("profile:form.email")}
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            className="w-full rounded-2xl border border-glass-border/60 bg-surface/80 px-5 py-4 text-page-foreground placeholder-placeholder transition-all duration-300 focus:border-nav-link focus:bg-surface focus:outline-none focus:ring-4 focus:ring-nav-link/20 dark:border-glass-border/50 dark:bg-card-bg/80 dark:focus:border-nav-link-hover dark:focus:bg-card-bg dark:focus:ring-nav-link-hover/20"
                          />
                          <input
                            type="text"
                            placeholder={t("profile:form.telegram")}
                            value={telegram}
                            onChange={(e) => setTelegram(e.target.value)}
                            className="w-full rounded-2xl border border-glass-border/60 bg-surface/80 px-5 py-4 text-page-foreground placeholder-placeholder transition-all duration-300 focus:border-nav-link focus:bg-surface focus:outline-none focus:ring-4 focus:ring-nav-link/20 dark:border-glass-border/50 dark:bg-card-bg/80 dark:focus:border-nav-link-hover dark:focus:bg-card-bg dark:focus:ring-nav-link-hover/20"
                          />
                          <p className="-mt-2 text-xs font-medium text-hint/80">
                            {t("profile:form.telegramHint")}
                          </p>

                          {user!.role === "teacher" && (
                            <>
                              <input
                                type="text"
                                placeholder={t("profile:form.department")}
                                value={department}
                                onChange={(e) => setDepartment(e.target.value)}
                                className="w-full rounded-2xl border border-glass-border/60 bg-surface/80 px-5 py-4 text-page-foreground placeholder-placeholder transition-all duration-300 focus:border-nav-link focus:bg-surface focus:outline-none focus:ring-4 focus:ring-nav-link/20 dark:border-glass-border/50 dark:bg-card-bg/80 dark:focus:border-nav-link-hover dark:focus:bg-card-bg dark:focus:ring-nav-link-hover/20"
                              />
                              <input
                                type="text"
                                placeholder={t("profile:form.position")}
                                value={position}
                                onChange={(e) => setPosition(e.target.value)}
                                className="w-full rounded-2xl border border-glass-border/60 bg-surface/80 px-5 py-4 text-page-foreground placeholder-placeholder transition-all duration-300 focus:border-nav-link focus:bg-surface focus:outline-none focus:ring-4 focus:ring-nav-link/20 dark:border-glass-border/50 dark:bg-card-bg/80 dark:focus:border-nav-link-hover dark:focus:bg-card-bg dark:focus:ring-nav-link-hover/20"
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
                                className="w-full rounded-2xl border border-glass-border/60 bg-surface/80 px-5 py-4 text-page-foreground placeholder-placeholder transition-all duration-300 focus:border-nav-link focus:bg-surface focus:outline-none focus:ring-4 focus:ring-nav-link/20 dark:border-glass-border/50 dark:bg-card-bg/80 dark:focus:border-nav-link-hover dark:focus:bg-card-bg dark:focus:ring-nav-link-hover/20"
                              />
                              <input
                                type="text"
                                placeholder={t("profile:form.recordBookNumber")}
                                value={recordBookNumber}
                                onChange={(e) => setRecordBookNumber(e.target.value)}
                                className="w-full rounded-2xl border border-glass-border/60 bg-surface/80 px-5 py-4 text-page-foreground placeholder-placeholder transition-all duration-300 focus:border-nav-link focus:bg-surface focus:outline-none focus:ring-4 focus:ring-nav-link/20 dark:border-glass-border/50 dark:bg-card-bg/80 dark:focus:border-nav-link-hover dark:focus:bg-card-bg dark:focus:ring-nav-link-hover/20"
                              />
                              <input
                                type="text"
                                placeholder={t("profile:form.status")}
                                value={status}
                                onChange={(e) => setStatus(e.target.value)}
                                className="w-full rounded-2xl border border-glass-border/60 bg-surface/80 px-5 py-4 text-page-foreground placeholder-placeholder transition-all duration-300 focus:border-nav-link focus:bg-surface focus:outline-none focus:ring-4 focus:ring-nav-link/20 dark:border-glass-border/50 dark:bg-card-bg/80 dark:focus:border-nav-link-hover dark:focus:bg-card-bg dark:focus:ring-nav-link-hover/20"
                              />
                              <input
                                type="text"
                                placeholder={t("profile:form.institute")}
                                value={institute}
                                onChange={(e) => setInstitute(e.target.value)}
                                className="w-full rounded-2xl border border-glass-border/60 bg-surface/80 px-5 py-4 text-page-foreground placeholder-placeholder transition-all duration-300 focus:border-nav-link focus:bg-surface focus:outline-none focus:ring-4 focus:ring-nav-link/20 dark:border-glass-border/50 dark:bg-card-bg/80 dark:focus:border-nav-link-hover dark:focus:bg-card-bg dark:focus:ring-nav-link-hover/20"
                              />
                              <input
                                type="text"
                                placeholder={t("profile:form.course")}
                                value={course}
                                onChange={(e) => setCourse(e.target.value)}
                                className="w-full rounded-2xl border border-glass-border/60 bg-surface/80 px-5 py-4 text-page-foreground placeholder-placeholder transition-all duration-300 focus:border-nav-link focus:bg-surface focus:outline-none focus:ring-4 focus:ring-nav-link/20 dark:border-glass-border/50 dark:bg-card-bg/80 dark:focus:border-nav-link-hover dark:focus:bg-card-bg dark:focus:ring-nav-link-hover/20"
                              />
                              <input
                                type="text"
                                placeholder={t("profile:form.educationLevel")}
                                value={educationLevel}
                                onChange={(e) => setEducationLevel(e.target.value)}
                                className="w-full rounded-2xl border border-glass-border/60 bg-surface/80 px-5 py-4 text-page-foreground placeholder-placeholder transition-all duration-300 focus:border-nav-link focus:bg-surface focus:outline-none focus:ring-4 focus:ring-nav-link/20 dark:border-glass-border/50 dark:bg-card-bg/80 dark:focus:border-nav-link-hover dark:focus:bg-card-bg dark:focus:ring-nav-link-hover/20"
                              />
                              <input
                                type="text"
                                placeholder={t("profile:form.track")}
                                value={track}
                                onChange={(e) => setTrack(e.target.value)}
                                className="w-full rounded-2xl border border-glass-border/60 bg-surface/80 px-5 py-4 text-page-foreground placeholder-placeholder transition-all duration-300 focus:border-nav-link focus:bg-surface focus:outline-none focus:ring-4 focus:ring-nav-link/20 dark:border-glass-border/50 dark:bg-card-bg/80 dark:focus:border-nav-link-hover dark:focus:bg-card-bg dark:focus:ring-nav-link-hover/20"
                              />
                              <input
                                type="text"
                                placeholder={t("profile:form.program")}
                                value={program}
                                onChange={(e) => setProgram(e.target.value)}
                                className="w-full rounded-2xl border border-glass-border/60 bg-surface/80 px-5 py-4 text-page-foreground placeholder-placeholder transition-all duration-300 focus:border-nav-link focus:bg-surface focus:outline-none focus:ring-4 focus:ring-nav-link/20 dark:border-glass-border/50 dark:bg-card-bg/80 dark:focus:border-nav-link-hover dark:focus:bg-card-bg dark:focus:ring-nav-link-hover/20"
                              />
                              <textarea
                                placeholder={t("profile:form.achievements")}
                                value={achievements}
                                onChange={(e) => setAchievements(e.target.value)}
                                rows={2}
                                className="w-full rounded-2xl border border-glass-border/60 bg-surface/80 px-5 py-4 text-page-foreground placeholder-placeholder transition-all duration-300 focus:border-nav-link focus:bg-surface focus:outline-none focus:ring-4 focus:ring-nav-link/20 dark:border-glass-border/50 dark:bg-card-bg/80 dark:focus:border-nav-link-hover dark:focus:bg-card-bg dark:focus:ring-nav-link-hover/20"
                              />
                            </>
                          )}

                          <div className="mt-2 flex flex-col gap-4 sm:flex-row sm:items-center">
                            <button
                              onClick={handleSave}
                              disabled={saving}
                              className="group relative flex w-full items-center justify-center overflow-hidden rounded-2xl border border-transparent bg-gradient-to-r from-nav-link to-nav-link/90 px-8 py-4 font-extrabold text-white shadow-[0_12px_28px_rgba(0,94,162,0.38)] transition-all duration-300 hover:-translate-y-1 hover:scale-[1.02] hover:shadow-[0_20px_40px_rgba(0,94,162,0.45)] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-nav-link/40 disabled:pointer-events-none disabled:opacity-60 active:translate-y-0 active:scale-[0.98] sm:w-auto dark:from-nav-link-hover dark:to-nav-link-hover/90 dark:shadow-[0_12px_28px_rgba(105,169,220,0.3)] dark:hover:shadow-[0_20px_40px_rgba(105,169,220,0.4)]"
                            >
                              <span className="relative z-10">
                                {saving ? t("profile:form.saving") : t("profile:form.save")}
                              </span>
                              <div className="absolute inset-0 bg-gradient-to-r from-white/0 via-white/10 to-white/0 opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
                            </button>
                            <button
                              onClick={handleCancel}
                              className="glass--btn flex w-full items-center justify-center rounded-2xl border border-glass-border/60 bg-glass/60 px-8 py-4 font-extrabold text-page-foreground backdrop-blur-sm transition-all duration-300 hover:-translate-y-1 hover:scale-[1.02] hover:border-glass-border hover:bg-glass/80 hover:shadow-lg focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-nav-link/30 active:translate-y-0 active:scale-[0.98] sm:w-auto dark:border-glass-border/50 dark:bg-glass/50"
                            >
                              {t("profile:form.cancel")}
                            </button>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="glass profile-card relative w-full overflow-hidden rounded-[2rem] bg-glass/60 p-7 backdrop-blur-xl shadow-[0_8px_24px_rgba(0,0,0,0.12)] sm:p-9 md:rounded-[2.5rem] md:p-11 dark:bg-glass/50 dark:shadow-[0_8px_24px_rgba(0,0,0,0.3)]">
                        <h2 className="mb-8 text-[clamp(1.4rem,2.5vw,2rem)] font-black tracking-tight text-page-foreground">
                          {t("profile:sections.details")}
                        </h2>
                        <div className="glass overflow-hidden rounded-[2rem] border border-glass-border/60 bg-glass/50 backdrop-blur-md shadow-[inset_0_1px_0_rgba(255,255,255,0.1)] dark:border-glass-border/50 dark:bg-glass/40">
                          <details open className="group">
                            <summary className="flex cursor-pointer items-center justify-between border-b border-glass-border/50 px-7 py-6 transition-all duration-300 hover:bg-glass/40 dark:border-glass-border/40 dark:hover:bg-glass/30">
                              <h3 className="text-lg font-black tracking-tight text-page-foreground">
                                {t("profile:sections.profileDetails")}
                              </h3>
                              <svg
                                className="h-6 w-6 text-nav-link transition-all duration-300 group-open:rotate-180 dark:text-nav-link-hover"
                                fill="none"
                                viewBox="0 0 24 24"
                                stroke="currentColor"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth={2.5}
                                  d="M19 9l-7 7-7-7"
                                />
                              </svg>
                            </summary>
                            <div className="px-7 py-7">
                              <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
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
                                <div className="mt-10">
                                  <div className="mb-6 flex items-center gap-3">
                                    <div className="h-1 w-1 rounded-full bg-nav-link dark:bg-nav-link-hover" />
                                    <h3 className="text-base font-extrabold uppercase tracking-[0.1em] text-page-foreground/90">
                                      {t("profile:sections.achievements")}
                                    </h3>
                                  </div>
                                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-[repeat(auto-fit,minmax(180px,1fr))]">
                                    {achievementsList.map((ach, idx) => (
                                      <motion.button
                                        key={ach.key}
                                        initial={{ opacity: 0, scale: 0.92, y: 8 }}
                                        animate={{ opacity: 1, scale: 1, y: 0 }}
                                        transition={
                                          isTest || reduced
                                            ? { duration: 0 }
                                            : {
                                                delay: idx * 0.07,
                                                duration: 0.4,
                                                type: "spring",
                                                stiffness: 400,
                                                damping: 26,
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
                                        className="glass--chip group inline-flex w-full items-center justify-center rounded-2xl border border-glass-border/60 bg-gradient-to-br from-glass/70 via-glass/50 to-glass/60 px-5 py-4 text-sm font-extrabold leading-snug text-page-foreground backdrop-blur-md shadow-[0_4px_12px_rgba(0,0,0,0.08)] transition-all duration-300 hover:-translate-y-1 hover:scale-105 hover:border-nav-link/50 hover:shadow-[0_12px_28px_rgba(0,94,162,0.18)] dark:border-glass-border/50 dark:from-glass/60 dark:via-glass/40 dark:to-glass/50 dark:shadow-[0_4px_12px_rgba(0,0,0,0.2)] dark:hover:border-nav-link-hover/50 dark:hover:shadow-[0_12px_28px_rgba(127,182,230,0.15)]"
                                      >
                                        <span className="relative">
                                          {ach.name}
                                          <span className="absolute -right-3 -top-2 h-2 w-2 rounded-full bg-nav-link opacity-0 transition-all duration-300 group-hover:opacity-100 dark:bg-nav-link-hover" />
                                        </span>
                                      </motion.button>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </div>
                          </details>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </motion.div>
            </div>

            <canvas
              ref={confettiRef}
              className="pointer-events-none fixed left-0 top-0 h-screen w-screen"
              style={{ zIndex: 2147483000 }}
            />
          </main>
        </motion.div>
      </PageFadeIn>

      {/* QR Dialog */}
      {qrOpen && (
        <div
          role="button"
          tabIndex={0}
          className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 px-4 backdrop-blur-md transition-all duration-300"
          onClick={closeQrModal}
          onKeyDown={(e) => {
            if (e.key === "Escape" || e.key === "Enter") closeQrModal()
          }}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.92, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{ type: "spring", stiffness: 400, damping: 28 }}
            className="glass relative w-full max-w-md overflow-hidden rounded-[2rem] bg-glass/95 backdrop-blur-2xl shadow-[0_24px_80px_rgba(0,0,0,0.4)] dark:bg-glass/90 dark:shadow-[0_24px_80px_rgba(0,0,0,0.6)]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="border-b border-glass-border/50 px-7 py-7 text-center">
              <h2 className="text-2xl font-black tracking-tight text-page-foreground">
                {t("profile:dialog.qr.title")}
              </h2>
            </div>
            <div className="flex min-h-[340px] flex-col items-center justify-center gap-5 px-7 pb-7 pt-8">
              <div className="rounded-[2rem] border border-nav-link/20 bg-white p-5 shadow-[0_20px_50px_-20px_rgba(0,0,0,0.3)] transition-all duration-300 hover:scale-105 dark:border-nav-link-hover/30 dark:shadow-[0_20px_50px_-20px_rgba(0,0,0,0.5)]">
                <div
                  className="flex h-[280px] w-[280px] items-center justify-center text-sm font-medium text-nav-link sm:h-[300px] sm:w-[300px]"
                  dangerouslySetInnerHTML={{
                    __html: `
                      <svg width="300" height="300" viewBox="0 0 300 300" xmlns="http://www.w3.org/2000/svg">
                        <rect width="300" height="300" fill="white"/>
                        <g transform="translate(150,150)">
                          <circle cx="0" cy="0" r="40" fill="none" stroke="currentColor" stroke-width="2"/>
                          <text x="0" y="0" text-anchor="middle" dominant-baseline="middle" font-size="14" fill="currentColor">
                            ${user?.full_name || "QR Code"}
                          </text>
                          <image href="${guuLogo}" x="-28" y="-80" width="56" height="56"/>
                        </g>
                      </svg>
                    `.trim(),
                  }}
                />
              </div>
              <p className="text-sm font-medium text-secondary/90">{t("profile:dialog.qr.hint")}</p>
            </div>
            <div className="flex justify-center border-t border-glass-border/50 px-7 py-6">
              <button
                onClick={closeQrModal}
                className="group relative flex items-center justify-center overflow-hidden rounded-2xl border border-transparent bg-gradient-to-r from-nav-link to-nav-link/90 px-10 py-4 font-extrabold text-white shadow-[0_12px_28px_rgba(0,94,162,0.38)] transition-all duration-300 hover:-translate-y-1 hover:scale-105 hover:shadow-[0_20px_40px_rgba(0,94,162,0.45)] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-nav-link/40 active:translate-y-0 active:scale-100 dark:from-nav-link-hover dark:to-nav-link-hover/90 dark:shadow-[0_12px_28px_rgba(105,169,220,0.3)]"
              >
                <span className="relative z-10">{t("common:buttons.done")}</span>
                <div className="absolute inset-0 bg-gradient-to-r from-white/0 via-white/10 to-white/0 opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
              </button>
            </div>
          </motion.div>
        </div>
      )}

      {/* Achievement Dialog */}
      {achOpen && (
        <div
          role="button"
          tabIndex={0}
          className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 px-4 backdrop-blur-md transition-all duration-300"
          onClick={() => setAchOpen(null)}
          onKeyDown={(e) => {
            if (e.key === "Escape" || e.key === "Enter") setAchOpen(null)
          }}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.92, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{ type: "spring", stiffness: 400, damping: 28 }}
            className="glass relative w-full max-w-lg overflow-hidden rounded-[2rem] bg-glass/95 backdrop-blur-2xl shadow-[0_24px_80px_rgba(0,0,0,0.4)] dark:bg-glass/90 dark:shadow-[0_24px_80px_rgba(0,0,0,0.6)]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="border-b border-glass-border/50 px-7 py-7">
              <h2 className="text-2xl font-black tracking-tight text-page-foreground">
                {achOpen.name}
              </h2>
            </div>
            <div className="flex flex-col gap-5 px-7 py-7">
              {achOpen.issuer && (
                <div className="flex items-start gap-4 rounded-2xl border border-glass-border/50 bg-glass/40 p-4">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-nav-link/10 text-nav-link dark:bg-nav-link-hover/10 dark:text-nav-link-hover">
                    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2.5}
                        d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"
                      />
                    </svg>
                  </div>
                  <div className="flex-1">
                    <p className="text-sm font-semibold text-secondary/90">
                      {t("profile:dialog.achievement.organizer", { issuer: "" })}
                    </p>
                    <p className="mt-1 font-bold text-page-foreground">{achOpen.issuer}</p>
                  </div>
                </div>
              )}
              {achOpen.date && (
                <div className="flex items-start gap-4 rounded-2xl border border-glass-border/50 bg-glass/40 p-4">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-nav-link/10 text-nav-link dark:bg-nav-link-hover/10 dark:text-nav-link-hover">
                    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2.5}
                        d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
                      />
                    </svg>
                  </div>
                  <div className="flex-1">
                    <p className="text-sm font-semibold text-secondary/90">
                      {t("profile:dialog.achievement.date", { date: "" })}
                    </p>
                    <p className="mt-1 font-bold text-page-foreground">{achOpen.date}</p>
                  </div>
                </div>
              )}
              {achOpen.url && (
                <a
                  href={achOpen.url}
                  target="_blank"
                  rel="noreferrer"
                  className="group relative mt-2 inline-flex items-center justify-center gap-2 overflow-hidden rounded-2xl border border-glass-border/60 bg-glass/60 px-6 py-4 font-extrabold text-page-foreground backdrop-blur-sm transition-all duration-300 hover:-translate-y-1 hover:scale-105 hover:border-nav-link/50 hover:bg-glass/80 hover:shadow-lg dark:border-glass-border/50"
                >
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2.5}
                      d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                    />
                  </svg>
                  <span>{t("profile:dialog.achievement.openLink")}</span>
                </a>
              )}
            </div>
            <div className="flex justify-center border-t border-glass-border/50 px-7 py-6">
              <button
                onClick={() => setAchOpen(null)}
                className="group relative flex items-center justify-center overflow-hidden rounded-2xl border border-transparent bg-gradient-to-r from-nav-link to-nav-link/90 px-10 py-4 font-extrabold text-white shadow-[0_12px_28px_rgba(0,94,162,0.38)] transition-all duration-300 hover:-translate-y-1 hover:scale-105 hover:shadow-[0_20px_40px_rgba(0,94,162,0.45)] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-nav-link/40 active:translate-y-0 active:scale-100 dark:from-nav-link-hover dark:to-nav-link-hover/90 dark:shadow-[0_12px_28px_rgba(105,169,220,0.3)]"
              >
                <span className="relative z-10">{t("profile:dialog.achievement.close")}</span>
                <div className="absolute inset-0 bg-gradient-to-r from-white/0 via-white/10 to-white/0 opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
              </button>
            </div>
          </motion.div>
        </div>
      )}

      {/* Snackbar */}
      {snack && (
        <div
          className="fixed bottom-10 left-1/2 z-[4000] -translate-x-1/2"
          data-testid={snack.key === "copied" ? "snackbar-copied" : undefined}
        >
          <motion.div
            initial={{ opacity: 0, y: 24, scale: 0.92 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 24, scale: 0.92 }}
            transition={{ type: "spring", stiffness: 400, damping: 28 }}
            className={cn(
              "flex min-w-[320px] items-center gap-4 rounded-2xl px-7 py-5 shadow-[0_16px_40px_rgba(0,0,0,0.25),0_4px_12px_rgba(0,0,0,0.15)] backdrop-blur-xl sm:min-w-[380px]",
              snack.sev === "success" &&
                "bg-gradient-to-r from-[#2e7d32] via-[#2e7d32] to-[#1b5e20] text-[#e9ffef]",
              snack.sev === "error" &&
                "bg-gradient-to-r from-[#d32f2f] via-[#d32f2f] to-[#b71c1c] text-[#fff5f5]",
              snack.sev === "info" &&
                "bg-gradient-to-r from-[#005ea2] via-[#005ea2] to-[#1a4480] text-[#eaf4ff]",
              snack.sev === "warning" &&
                "bg-gradient-to-r from-[#f59e0b] via-[#f59e0b] to-[#b45309] text-[#fff8e1]"
            )}
          >
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white/15">
              {snack.sev === "success" && (
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2.5}
                    d="M5 13l4 4L19 7"
                  />
                </svg>
              )}
              {snack.sev === "error" && (
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2.5}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              )}
              {snack.sev === "info" && (
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2.5}
                    d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
              )}
              {snack.sev === "warning" && (
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2.5}
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                  />
                </svg>
              )}
            </div>
            <span className="flex-1 text-sm font-bold leading-relaxed sm:text-base">
              {snackMessage}
            </span>
            <button
              onClick={() => setSnack(null)}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl transition-all duration-300 hover:scale-110 hover:bg-white/20 active:scale-95"
              aria-label="Close"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2.5}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </motion.div>
        </div>
      )}
    </>
  )
}
