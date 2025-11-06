import { useAuth, currentUserQueryKey } from "../contexts/AuthContext"
import React, { useEffect, useMemo, useState, useRef, useCallback, memo } from "react"
import { useLocation, useNavigate } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import api from "../api/client"
import type { User } from "@/types/User"
import profileBg from "../assets/background.jpg"
import guuLogo from "../assets/guu_logo.png"
import spotifyLogo from "../assets/spotify_icon.png"
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"
const DEFAULT_AVATAR = AVATAR_PLACEHOLDER_URL
import PageFadeIn from "../components/PageFadeIn"
import {
  CircularProgress,
  Snackbar,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
} from "@mui/material"
import { QRCodeSVG } from "qrcode.react"
import { motion, useReducedMotion } from "framer-motion"
import { nowPlayingQueryKey, useNowPlaying } from "@/hooks/useNowPlaying"
import type { NowPlaying } from "@/types/spotify"
import { addVersionParam, resolveMediaUrl } from "@/utils/media"
import { useTranslation } from "react-i18next"
import EmailIcon from "@mui/icons-material/Email"
import TelegramIcon from "@mui/icons-material/Telegram"
import ContentCopyIcon from "@mui/icons-material/ContentCopy"
import ExpandMoreIcon from "@mui/icons-material/ExpandMore"

const isTest = typeof import.meta !== "undefined" && import.meta.env.MODE === "test"

type SnackKey = "spotifyConnected" | "spotifyError" | "copied" | "profileUpdated" | "error"

type SnackState = {
  key?: SnackKey
  message?: string
  sev?: "success" | "info" | "warning" | "error"
}

export const NowPlayingCard = memo(function NowPlayingCard({ data }: { data: NowPlaying }) {
  const prefersReduce =
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
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
        className="nowplaying--spotify w-full grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2 px-4 py-3.5 rounded-2xl relative overflow-hidden border border-[#1db95433] bg-[#121212] text-white shadow-lg hover:shadow-xl transition-all duration-300 hover:-translate-y-0.5"
        initial={isTest || prefersReduce || reduced ? false : { y: 12, opacity: 0.94, scale: 1 }}
        animate={{ y: 0, opacity: 1, scale: 1 }}
        whileHover={prefersReduce || reduced ? {} : { y: -1, scale: 1.002 }}
        whileTap={prefersReduce || reduced ? {} : { scale: 0.997 }}
        transition={
          isTest ? { duration: 0 } : { type: "spring", stiffness: 520, damping: 36, mass: 0.9 }
        }
      >
        <div className="relative w-14 h-14 rounded-lg overflow-hidden shadow-[0_8px_20px_rgba(0,0,0,0.35)]">
          <img
            src={data.album_image_url ?? ""}
            alt={data.album_name || data.track_name || t("profile:nowPlaying.albumFallback")}
            loading="lazy"
            decoding="async"
            referrerPolicy="no-referrer"
            className={`w-full h-full rounded-lg object-cover ${
              prefersReduce || reduced
                ? ""
                : "scale-[1.012] transition-transform duration-[900ms] cubic-bezier-[0.22,0.61,0.36,1] hover:scale-[1.02]"
            }`}
          />
        </div>
        <div className="min-w-0 flex flex-col gap-1.5" aria-live="polite">
          <h3 className="np-title font-extrabold leading-tight tracking-tight text-white text-base">
            {data.track_name || "—"}
          </h3>
          <p className="np-art text-sm text-[#b3b3b3] opacity-90 truncate">
            {data.artists.join(", ")}
          </p>
          {!data.is_playing && (
            <span
              className="inline-flex self-start px-2 py-0.5 text-xs font-bold uppercase bg-gray-700 text-gray-300 rounded-full"
              aria-hidden
            >
              {t("profile:nowPlaying.paused")}
            </span>
          )}
          <div className="flex items-center gap-2 w-full">
            <div className="flex-1 h-1.5 bg-[#2a2a2a] rounded-full overflow-hidden">
              <div
                role="progressbar"
                aria-valuenow={progress}
                aria-valuemin={0}
                aria-valuemax={duration}
                aria-label={t("profile:nowPlaying.progress")}
                className="h-full bg-[#1db954] rounded-full transition-all duration-200"
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="np-time text-xs text-[#b3b3b3] whitespace-nowrap tabular-nums">
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
    <div className="grid grid-cols-[12px_1fr] items-start gap-2 sm:gap-3 px-3 sm:px-4 py-2.5 sm:py-3 min-h-[44px] sm:min-h-[48px] rounded-lg sm:rounded-xl border border-glass-border bg-surface dark:bg-card-bg transition-all duration-300 hover:shadow-md hover:border-glass-border/80 dark:hover:border-glass-border/80 hover:bg-surface-accent dark:hover:bg-surface-accent">
      <div className="w-1.5 h-1.5 mt-1.5 rounded-full bg-nav-link dark:bg-nav-link shadow-[0_0_0_2px_rgba(15,79,170,0.15)] dark:shadow-[0_0_0_2px_rgba(127,182,230,0.15)] justify-self-center" />
      <div className="text-xs sm:text-sm md:text-base leading-relaxed text-page-foreground">
        <span className="font-extrabold text-nav-link dark:text-nav-link">{label}</span>
        <span className="mx-1 sm:mx-1.5 text-secondary/50">·</span>
        <span className="font-medium break-words">{value}</span>
      </div>
    </div>
  )
}

export default function Profile() {
  const { user, loading, setUser } = useAuth()
  const [snack, setSnack] = useState<SnackState | null>(null)
  const [avatarVersion, setAvatarVersion] = useState(Date.now())
  const [coverVersion, setCoverVersion] = useState(Date.now())
  const reduceMotion =
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  const isTwoCol =
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(min-width: 1400px)").matches
  const isMobile =
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(max-width: 600px)").matches
  const reduced = useReducedMotion()
  const { t } = useTranslation(["profile", "common"])
  const [scrollY, setScrollY] = useState(0)
  const [qrOpen, setQrOpen] = useState(false)
  const [detailsOpen, setDetailsOpen] = useState(true)
  const [achOpen, setAchOpen] = useState<{
    name: string
    issuer?: string
    date?: string
    url?: string
  } | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
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
        <CircularProgress />
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

  const copy = async (text: string, evt?: { clientX: number; clientY: number }) => {
    try {
      await navigator.clipboard?.writeText(text)
    } finally {
      setSnack({ key: "copied", sev: "success" })
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
    if (isMobile) return 120
    if (
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(min-width: 1400px)").matches
    )
      return 188
    return 168
  }, [isMobile])
  const avatarSize = `${avatarPx}px`
  const avatarFloat = Math.round(avatarPx * 0.55)
  const heroPaddingBottom = `${Math.max(avatarFloat - 12, 28)}px`
  const heroTextPaddingTop = isMobile
    ? `${Math.round(40 + avatarPx + 12)}px`
    : `${Math.round(48 + avatarPx + 16)}px`
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
      {/* Background with matte overlay */}
      <div
        className="fixed inset-0 -z-20 bg-cover bg-center bg-fixed"
        style={{ backgroundImage: `url(${profileBg})` }}
      >
        <div className="absolute inset-0 bg-[#1a4480]/75 dark:bg-[#0b121f]/85" />
      </div>

      <PageFadeIn>
        <motion.div
          initial={isTest ? false : { opacity: reduceMotion ? 1 : 0.96, y: reduceMotion ? 0 : 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={isTest ? { duration: 0 } : { type: "spring", stiffness: 460, damping: 34 }}
        >
          <main
            id="main"
            className="profile-page relative min-h-screen flex flex-col py-12 sm:py-16 md:py-20 lg:py-24 px-3 sm:px-4 md:px-6 lg:px-8"
            data-testid="profile-root"
            aria-label={t("profile:aria.page")}
          >
            <div className="max-w-full sm:max-w-[98%] md:max-w-[96%] lg:max-w-[95%] xl:max-w-[1400px] mx-auto w-full relative z-0">
              <motion.div
                ref={containerRef}
                className="profile-card px-4 sm:px-6 md:px-8 lg:px-10 xl:px-12 py-8 sm:py-10 md:py-12 lg:py-14 rounded-xl sm:rounded-2xl md:rounded-3xl relative overflow-hidden border border-glass-border bg-surface dark:bg-card-bg shadow-surface dark:shadow-surface-strong"
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
                <div className="grid grid-cols-1 lg:grid-cols-[minmax(280px,380px)_minmax(0,1fr)] xl:grid-cols-[minmax(320px,420px)_minmax(0,1fr)] 2xl:grid-cols-[minmax(380px,460px)_minmax(0,1fr)] gap-x-4 sm:gap-x-6 md:gap-x-8 lg:gap-x-10 xl:gap-x-12 gap-y-6 sm:gap-y-8 lg:gap-y-0 items-start">
                  <div className="flex flex-col gap-4 sm:gap-5 md:gap-6 lg:gap-8 items-stretch">
                    {/* Hero Card with Cover and Avatar */}
                    <div
                      className="relative rounded-xl sm:rounded-2xl md:rounded-3xl overflow-hidden min-h-[280px] xs:min-h-[300px] sm:min-h-[320px] md:min-h-[340px] lg:min-h-[360px] xl:min-h-[380px] flex items-end justify-center shadow-surface dark:shadow-surface-strong border border-glass-border bg-surface dark:bg-card-bg"
                      style={{ paddingBottom: heroPaddingBottom }}
                    >
                      {/* Cover Image with Parallax */}
                      <div
                        className={`absolute inset-0 bg-center bg-cover ${reduceMotion ? "" : "transition-transform duration-[1200ms] cubic-bezier-[0.33,1,0.68,1]"}`}
                        style={{
                          backgroundImage: coverImageUrl ? `url(${coverImageUrl})` : undefined,
                          transform: `translateY(${coverParallax}px) scale(${coverScale})`,
                          filter: "saturate(1) contrast(1.02) brightness(0.98)",
                        }}
                      />
                      {/* Dark Matte Overlay */}
                      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-[rgba(6,9,20,0.85)] dark:to-[rgba(6,9,20,0.92)] from-35%" />

                      {/* Avatar Container */}
                      <div
                        className="absolute left-1/2 top-8 xs:top-10 sm:top-12 md:top-14 -translate-x-1/2 flex items-center justify-center p-0.5 sm:p-1"
                        style={{ width: avatarSize, height: avatarSize }}
                      >
                        <div className="avatar-ring w-full h-full">
                          <div className="relative w-full h-full rounded-full bg-white/10 overflow-hidden">
                            {avatarImageUrl ? (
                              <img
                                src={avatarImageUrl}
                                alt={user?.full_name ?? undefined}
                                onError={handleAvatarImgError}
                                loading="lazy"
                                decoding="async"
                                referrerPolicy="no-referrer"
                                className="w-full h-full rounded-full object-cover"
                              />
                            ) : (
                              <div className="w-full h-full rounded-full bg-white/10 text-white/90 flex items-center justify-center text-[clamp(28px,6vw,64px)] font-bold">
                                {user?.full_name?.[0]}
                              </div>
                            )}
                          </div>
                        </div>

                        {/* Online Status Indicator */}
                        {isOnline && (
                          <div
                            className="absolute z-[3] rounded-full bg-[#22c55e] shadow-[0_0_0_2px_rgba(0,0,0,0.18),0_4px_10px_rgba(34,197,94,0.45)] pointer-events-none"
                            style={{
                              right: `${statusOffset}px`,
                              bottom: `${statusOffset}px`,
                              width: `${statusSize}px`,
                              height: `${statusSize}px`,
                            }}
                          >
                            {!reduced && (
                              <div className="absolute -inset-1.5 rounded-full border-2 border-[rgba(34,197,94,0.45)] animate-[online-pulse_1.8s_ease-in-out_infinite]" />
                            )}
                          </div>
                        )}
                      </div>

                      {/* Name and Chips Section */}
                      <div
                        className="relative z-[2] w-full text-center md:text-left px-4 sm:px-6 md:px-8 lg:px-10 flex flex-col gap-3 sm:gap-4 md:gap-5"
                        style={{ paddingTop: heroTextPaddingTop }}
                      >
                        <div>
                          <h1
                            className="profile-name text-[clamp(1.5rem,4vw+0.5rem,2.5rem)] sm:text-[clamp(1.7rem,3.5vw+0.5rem,2.7rem)] md:text-[clamp(1.9rem,3.2vw+0.5rem,2.9rem)] font-black leading-[1.08] tracking-tight"
                            data-testid="profile-name"
                          >
                            {user!.full_name}
                          </h1>
                          {!!user?.position && user?.role === "teacher" && (
                            <p className="profile-subtitle mt-1.5 sm:mt-2 font-semibold text-base sm:text-lg text-white/90 dark:text-white/95">
                              {user.position}
                            </p>
                          )}
                        </div>
                        <div className="flex flex-row flex-wrap gap-2 sm:gap-2.5 justify-center md:justify-start">
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
                            <motion.div
                              key={`${chip}-${idx}`}
                              initial={isTest || reduced ? false : { opacity: 0, scale: 0.9 }}
                              animate={{ opacity: 1, scale: 1 }}
                              transition={
                                isTest || reduced
                                  ? { duration: 0 }
                                  : {
                                      delay: idx * 0.09,
                                      duration: 0.56,
                                      ease: [0.22, 0.61, 0.36, 1],
                                    }
                              }
                            >
                              <span className="inline-flex items-center px-3 sm:px-4 py-1 sm:py-1.5 rounded-full border border-white/30 dark:border-white/25 bg-white/20 dark:bg-white/15 text-white text-xs sm:text-sm font-bold tracking-wide transition-all duration-300 hover:scale-105 hover:shadow-md hover:bg-white/28 dark:hover:bg-white/22">
                                {chip}
                              </span>
                            </motion.div>
                          ))}
                        </div>
                      </div>
                    </div>

                    {/* Now Playing Section */}
                    {showNowPlaying && nowPlaying && (
                      <motion.div
                        initial={isTest || reduced ? false : { opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={
                          isTest || reduced
                            ? { duration: 0 }
                            : { duration: 0.72, ease: [0.22, 0.61, 0.36, 1] }
                        }
                        className="flex flex-col gap-3"
                      >
                        <div className="flex items-center gap-2">
                          <img
                            src={spotifyLogo}
                            alt="Spotify"
                            width={16}
                            height={16}
                            style={{ display: "block", borderRadius: "50%" }}
                            loading="lazy"
                            decoding="async"
                            className="flex-shrink-0"
                          />
                          <h3 className="text-[10px] xs:text-xs uppercase tracking-[2.2px] font-bold text-secondary opacity-90">
                            {t("profile:sections.nowPlaying")}
                          </h3>
                        </div>
                        <NowPlayingCard data={nowPlaying} />
                      </motion.div>
                    )}

                    {/* Contact Panel */}
                    <div className="profile-card p-4 sm:p-5 md:p-6 rounded-xl sm:rounded-2xl flex flex-col gap-4 sm:gap-5 border border-glass-border bg-surface dark:bg-card-bg shadow-surface dark:shadow-surface-strong">
                      {/* QR Button */}
                      <div className="flex flex-col gap-3 items-stretch">
                        <button
                          onClick={openQrModal}
                          data-testid="open-qr"
                          className="w-full py-2.5 sm:py-3 px-5 sm:px-6 rounded-lg sm:rounded-xl bg-nav-link dark:bg-nav-link text-white dark:text-[#0b121f] font-extrabold tracking-wide text-sm sm:text-base shadow-surface hover:shadow-surface-strong transition-all duration-300 hover:-translate-y-0.5 hover:scale-[1.01] hover:bg-[#0d4494] dark:hover:bg-[#69a9dc] active:scale-[0.98] border border-nav-link/20 dark:border-nav-link/30"
                        >
                          {t("profile:buttons.showQr")}
                        </button>
                      </div>

                      {/* Divider */}
                      <div className="h-px bg-glass-border dark:bg-glass-border" />

                      {/* Contact Links */}
                      <div className="flex flex-col gap-3 sm:gap-4 contact-links">
                        {/* Email */}
                        <div className="flex flex-row items-center justify-between flex-wrap gap-2 sm:gap-3">
                          <div className="flex flex-row items-center gap-1.5 sm:gap-2 min-w-0 flex-1">
                            <EmailIcon
                              className="w-4 h-4 sm:w-5 sm:h-5 flex-shrink-0 text-nav-link dark:text-[#7fb6e6]"
                              aria-hidden
                            />
                            <p className="font-extrabold break-words flex-1 text-sm sm:text-base text-page-foreground">
                              <a
                                href={`mailto:${user!.email}`}
                                className="text-nav-link dark:text-[#7fb6e6] hover:text-nav-link-hover dark:hover:text-[#c7e1f7] no-underline hover:underline transition-colors duration-200 break-all"
                                data-testid="profile-email-link"
                                title={t("profile:aria.openEmail")}
                              >
                                {user!.email}
                              </a>
                            </p>
                          </div>
                          <button
                            onClick={(e) => copy(user!.email, e)}
                            aria-label={t("profile:aria.copyEmail")}
                            title={t("profile:aria.copyEmail")}
                            data-testid="copy-email"
                            className={`p-2 rounded-lg border border-glass-border bg-surface dark:bg-card-bg hover:bg-surface-accent dark:hover:bg-surface-accent transition-all duration-200 hover:shadow-md ${reduced ? "" : "hover:-translate-y-0.5 hover:scale-105"}`}
                          >
                            <ContentCopyIcon className="w-4 h-4 text-page-foreground" />
                          </button>
                        </div>

                        {/* Telegram */}
                        {!!user!.telegram && (
                          <div className="flex flex-row items-center justify-between flex-wrap gap-2 sm:gap-3">
                            <div className="flex flex-row items-center gap-1.5 sm:gap-2 min-w-0 flex-1">
                              <TelegramIcon
                                className="w-4 h-4 sm:w-5 sm:h-5 flex-shrink-0 text-nav-link dark:text-[#7fb6e6]"
                                aria-hidden
                              />
                              <p className="font-extrabold break-words flex-1 text-sm sm:text-base text-page-foreground">
                                <a
                                  href={telegramHref}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-nav-link dark:text-[#7fb6e6] hover:text-nav-link-hover dark:hover:text-[#c7e1f7] no-underline hover:underline transition-colors duration-200 break-all"
                                  data-testid="profile-telegram-link"
                                  title={t("profile:aria.openTelegram")}
                                >
                                  {user!.telegram}
                                </a>
                              </p>
                            </div>
                            <button
                              onClick={(e) => copy(user!.telegram!, e)}
                              aria-label={t("profile:aria.copyTelegram")}
                              title={t("profile:aria.copyTelegram")}
                              data-testid="copy-telegram"
                              className={`p-2 rounded-lg border border-glass-border bg-surface dark:bg-card-bg hover:bg-surface-accent dark:hover:bg-surface-accent transition-all duration-200 hover:shadow-md ${reduced ? "" : "hover:-translate-y-0.5 hover:scale-105"}`}
                            >
                              <ContentCopyIcon className="w-4 h-4 text-page-foreground" />
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Right Column - Profile Details / Edit Form */}
                  <div
                    className="w-full relative"
                    style={{ marginTop: isMobile ? `${Math.round(avatarPx * 0.55) + 36}px` : "0" }}
                  >
                    {edit ? (
                      <div className="profile-card profile-edit w-full rounded-xl sm:rounded-2xl p-4 sm:p-6 md:p-8 lg:p-10 border border-glass-border bg-surface dark:bg-card-bg shadow-surface dark:shadow-surface-strong">
                        <div className="flex flex-col gap-4 sm:gap-5">
                          {/* Name Field */}
                          <div className="flex flex-col gap-1.5 sm:gap-2">
                            <label className="text-xs sm:text-sm font-bold text-page-foreground">
                              {t("profile:form.name")}
                            </label>
                            <input
                              type="text"
                              value={fullName}
                              onChange={(e) => setFullName(e.target.value)}
                              maxLength={120}
                              className="w-full px-3 sm:px-4 py-2 sm:py-3 text-sm sm:text-base rounded-lg sm:rounded-xl border border-glass-border bg-surface text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-[#0f4faa] dark:focus:ring-[#7fb6e6] focus:border-transparent transition-all duration-200"
                            />
                          </div>

                          {/* Email Field */}
                          <div className="flex flex-col gap-1.5 sm:gap-2">
                            <label className="text-xs sm:text-sm font-bold text-page-foreground">
                              {t("profile:form.email")}
                            </label>
                            <input
                              type="email"
                              value={email}
                              onChange={(e) => setEmail(e.target.value)}
                              className="w-full px-3 sm:px-4 py-2 sm:py-3 text-sm sm:text-base rounded-lg sm:rounded-xl border border-glass-border bg-surface text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-[#0f4faa] dark:focus:ring-[#7fb6e6] focus:border-transparent transition-all duration-200"
                            />
                          </div>

                          {/* Telegram Field */}
                          <div className="flex flex-col gap-1.5 sm:gap-2">
                            <label className="text-xs sm:text-sm font-bold text-page-foreground">
                              {t("profile:form.telegram")}
                            </label>
                            <input
                              type="text"
                              value={telegram}
                              onChange={(e) => setTelegram(e.target.value)}
                              className="w-full px-3 sm:px-4 py-2 sm:py-3 text-sm sm:text-base rounded-lg sm:rounded-xl border border-glass-border bg-surface text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-[#0f4faa] dark:focus:ring-[#7fb6e6] focus:border-transparent transition-all duration-200"
                            />
                            <p className="text-[10px] xs:text-xs text-hint">
                              {t("profile:form.telegramHint")}
                            </p>
                          </div>

                          {/* Teacher Fields */}
                          {user!.role === "teacher" && (
                            <>
                              <div className="flex flex-col gap-1.5 sm:gap-2">
                                <label className="text-xs sm:text-sm font-bold text-page-foreground">
                                  {t("profile:form.department")}
                                </label>
                                <input
                                  type="text"
                                  value={department}
                                  onChange={(e) => setDepartment(e.target.value)}
                                  className="w-full px-3 sm:px-4 py-2 sm:py-3 text-sm sm:text-base rounded-lg sm:rounded-xl border border-glass-border bg-surface text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-[#0f4faa] dark:focus:ring-[#7fb6e6] focus:border-transparent transition-all duration-200"
                                />
                              </div>
                              <div className="flex flex-col gap-1.5 sm:gap-2">
                                <label className="text-xs sm:text-sm font-bold text-page-foreground">
                                  {t("profile:form.position")}
                                </label>
                                <input
                                  type="text"
                                  value={position}
                                  onChange={(e) => setPosition(e.target.value)}
                                  className="w-full px-3 sm:px-4 py-2 sm:py-3 text-sm sm:text-base rounded-lg sm:rounded-xl border border-glass-border bg-surface text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-[#0f4faa] dark:focus:ring-[#7fb6e6] focus:border-transparent transition-all duration-200"
                                />
                              </div>
                            </>
                          )}

                          {/* Student Fields */}
                          {user!.role === "student" && (
                            <>
                              <div className="flex flex-col gap-1.5 sm:gap-2">
                                <label className="text-xs sm:text-sm font-bold text-page-foreground">
                                  {t("profile:form.about")}
                                </label>
                                <textarea
                                  value={about}
                                  onChange={(e) => setAbout(e.target.value)}
                                  rows={3}
                                  className="w-full px-3 sm:px-4 py-2 sm:py-3 text-sm sm:text-base rounded-lg sm:rounded-xl border border-glass-border bg-surface text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-[#0f4faa] dark:focus:ring-[#7fb6e6] focus:border-transparent transition-all duration-200 resize-y min-h-[70px] sm:min-h-[80px]"
                                />
                              </div>
                              <div className="flex flex-col gap-1.5 sm:gap-2">
                                <label className="text-xs sm:text-sm font-bold text-page-foreground">
                                  {t("profile:form.recordBookNumber")}
                                </label>
                                <input
                                  type="text"
                                  value={recordBookNumber}
                                  onChange={(e) => setRecordBookNumber(e.target.value)}
                                  className="w-full px-3 sm:px-4 py-2 sm:py-3 text-sm sm:text-base rounded-lg sm:rounded-xl border border-glass-border bg-surface text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-[#0f4faa] dark:focus:ring-[#7fb6e6] focus:border-transparent transition-all duration-200"
                                />
                              </div>
                              <div className="flex flex-col gap-1.5 sm:gap-2">
                                <label className="text-xs sm:text-sm font-bold text-page-foreground">
                                  {t("profile:form.status")}
                                </label>
                                <input
                                  type="text"
                                  value={status}
                                  onChange={(e) => setStatus(e.target.value)}
                                  className="w-full px-3 sm:px-4 py-2 sm:py-3 text-sm sm:text-base rounded-lg sm:rounded-xl border border-glass-border bg-surface text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-[#0f4faa] dark:focus:ring-[#7fb6e6] focus:border-transparent transition-all duration-200"
                                />
                              </div>
                              <div className="flex flex-col gap-1.5 sm:gap-2">
                                <label className="text-xs sm:text-sm font-bold text-page-foreground">
                                  {t("profile:form.institute")}
                                </label>
                                <input
                                  type="text"
                                  value={institute}
                                  onChange={(e) => setInstitute(e.target.value)}
                                  className="w-full px-3 sm:px-4 py-2 sm:py-3 text-sm sm:text-base rounded-lg sm:rounded-xl border border-glass-border bg-surface text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-[#0f4faa] dark:focus:ring-[#7fb6e6] focus:border-transparent transition-all duration-200"
                                />
                              </div>
                              <div className="flex flex-col gap-1.5 sm:gap-2">
                                <label className="text-xs sm:text-sm font-bold text-page-foreground">
                                  {t("profile:form.course")}
                                </label>
                                <input
                                  type="text"
                                  value={course}
                                  onChange={(e) => setCourse(e.target.value)}
                                  className="w-full px-3 sm:px-4 py-2 sm:py-3 text-sm sm:text-base rounded-lg sm:rounded-xl border border-glass-border bg-surface text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-[#0f4faa] dark:focus:ring-[#7fb6e6] focus:border-transparent transition-all duration-200"
                                />
                              </div>
                              <div className="flex flex-col gap-1.5 sm:gap-2">
                                <label className="text-xs sm:text-sm font-bold text-page-foreground">
                                  {t("profile:form.educationLevel")}
                                </label>
                                <input
                                  type="text"
                                  value={educationLevel}
                                  onChange={(e) => setEducationLevel(e.target.value)}
                                  className="w-full px-3 sm:px-4 py-2 sm:py-3 text-sm sm:text-base rounded-lg sm:rounded-xl border border-glass-border bg-surface text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-[#0f4faa] dark:focus:ring-[#7fb6e6] focus:border-transparent transition-all duration-200"
                                />
                              </div>
                              <div className="flex flex-col gap-1.5 sm:gap-2">
                                <label className="text-xs sm:text-sm font-bold text-page-foreground">
                                  {t("profile:form.track")}
                                </label>
                                <input
                                  type="text"
                                  value={track}
                                  onChange={(e) => setTrack(e.target.value)}
                                  className="w-full px-3 sm:px-4 py-2 sm:py-3 text-sm sm:text-base rounded-lg sm:rounded-xl border border-glass-border bg-surface text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-[#0f4faa] dark:focus:ring-[#7fb6e6] focus:border-transparent transition-all duration-200"
                                />
                              </div>
                              <div className="flex flex-col gap-1.5 sm:gap-2">
                                <label className="text-xs sm:text-sm font-bold text-page-foreground">
                                  {t("profile:form.program")}
                                </label>
                                <input
                                  type="text"
                                  value={program}
                                  onChange={(e) => setProgram(e.target.value)}
                                  className="w-full px-3 sm:px-4 py-2 sm:py-3 text-sm sm:text-base rounded-lg sm:rounded-xl border border-glass-border bg-surface text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-[#0f4faa] dark:focus:ring-[#7fb6e6] focus:border-transparent transition-all duration-200"
                                />
                              </div>
                              <div className="flex flex-col gap-1.5 sm:gap-2">
                                <label className="text-xs sm:text-sm font-bold text-page-foreground">
                                  {t("profile:form.achievements")}
                                </label>
                                <textarea
                                  value={achievements}
                                  onChange={(e) => setAchievements(e.target.value)}
                                  rows={2}
                                  className="w-full px-3 sm:px-4 py-2 sm:py-3 text-sm sm:text-base rounded-lg sm:rounded-xl border border-glass-border bg-surface text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-[#0f4faa] dark:focus:ring-[#7fb6e6] focus:border-transparent transition-all duration-200 resize-y min-h-[50px] sm:min-h-[60px]"
                                />
                              </div>
                            </>
                          )}

                          {/* Action Buttons */}
                          <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 items-stretch sm:items-center pt-2">
                            <button
                              onClick={handleSave}
                              disabled={saving}
                              className="w-full sm:w-auto py-2.5 sm:py-3 px-6 sm:px-8 rounded-lg sm:rounded-xl bg-nav-link dark:bg-nav-link text-white dark:text-[#0b121f] font-extrabold tracking-wide text-sm sm:text-base shadow-surface hover:shadow-surface-strong transition-all duration-300 hover:-translate-y-0.5 hover:scale-[1.01] hover:bg-[#0d4494] dark:hover:bg-[#69a9dc] active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0 disabled:hover:scale-100 disabled:hover:bg-nav-link dark:disabled:hover:bg-nav-link border border-nav-link/20 dark:border-nav-link/30"
                            >
                              {saving ? t("profile:form.saving") : t("profile:form.save")}
                            </button>
                            <button
                              onClick={handleCancel}
                              className="w-full sm:w-auto py-2.5 sm:py-3 px-6 sm:px-8 rounded-lg sm:rounded-xl border-2 border-glass-border bg-transparent hover:bg-surface-accent dark:hover:bg-surface-accent text-page-foreground font-extrabold tracking-wide text-sm sm:text-base transition-all duration-300 hover:-translate-y-0.5 hover:scale-[1.01] active:scale-[0.98]"
                            >
                              {t("profile:form.cancel")}
                            </button>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <>
                        {/* Profile Details View */}
                        <div className="w-full flex flex-col gap-4 sm:gap-5 md:gap-6">
                          {/* Section Header */}
                          <div className="flex items-center justify-between gap-3 sm:gap-4">
                            <h2 className="text-[clamp(1.3rem,3vw+0.5rem,2rem)] sm:text-[clamp(1.5rem,3.2vw+0.5rem,2.2rem)] font-black tracking-tight text-page-foreground">
                              {t("profile:sections.details")}
                            </h2>
                            <button
                              onClick={() => setDetailsOpen(!detailsOpen)}
                              className={`p-2 rounded-lg hover:bg-white/10 dark:hover:bg-white/5 transition-all duration-200 ${reduced ? "" : "hover:scale-105"}`}
                              aria-label={detailsOpen ? "Свернуть" : "Развернуть"}
                            >
                              <ExpandMoreIcon
                                className={`w-6 h-6 text-page-foreground transition-transform duration-300 ${detailsOpen ? "rotate-180" : ""}`}
                              />
                            </button>
                          </div>

                          {/* Collapsible Content */}
                          <motion.div
                            initial={false}
                            animate={{
                              height: detailsOpen ? "auto" : 0,
                              opacity: detailsOpen ? 1 : 0,
                            }}
                            transition={{ duration: 0.3, ease: [0.22, 0.61, 0.36, 1] }}
                            className="overflow-hidden"
                          >
                            <div className="flex flex-col gap-4 sm:gap-5 md:gap-6">
                              {/* Detail Rows Grid */}
                              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
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
                                  {
                                    label: t("profile:form.department"),
                                    value: user!.department,
                                  },
                                  { label: t("profile:form.position"), value: user!.position },
                                ].map((r) => (
                                  <DetailRow key={r.label} label={r.label} value={r.value} />
                                ))}
                              </div>

                              {/* Achievements Section */}
                              {achievementsList.length > 0 && (
                                <div className="pt-2">
                                  <h3 className="font-extrabold mb-3 sm:mb-4 text-lg sm:text-xl text-page-foreground">
                                    {t("profile:sections.achievements")}
                                  </h3>
                                  <div className="grid grid-cols-[repeat(auto-fit,minmax(120px,1fr))] sm:grid-cols-[repeat(auto-fit,minmax(140px,1fr))] md:grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-2.5 sm:gap-3">
                                    {achievementsList.map((ach, idx) => (
                                      <motion.button
                                        key={ach.key}
                                        initial={
                                          isTest || reduced ? false : { opacity: 0, scale: 0.9 }
                                        }
                                        animate={{ opacity: 1, scale: 1 }}
                                        transition={
                                          isTest || reduced
                                            ? { duration: 0 }
                                            : {
                                                delay: idx * 0.09,
                                                duration: 0.5,
                                                ease: [0.22, 0.61, 0.36, 1],
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
                                        className="px-3 sm:px-4 py-2 sm:py-2.5 md:py-3 rounded-lg sm:rounded-xl border border-glass-border bg-surface dark:bg-card-bg hover:bg-surface-accent dark:hover:bg-surface-accent text-page-foreground font-bold text-xs sm:text-sm leading-tight transition-all duration-300 hover:scale-105 hover:shadow-md cursor-pointer text-left"
                                      >
                                        {ach.name}
                                      </motion.button>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </div>
                          </motion.div>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              </motion.div>
            </div>
          </main>
        </motion.div>
      </PageFadeIn>

      {/* QR Code Dialog */}
      <Dialog
        open={qrOpen}
        onClose={closeQrModal}
        maxWidth="xs"
        fullWidth
        PaperProps={{
          className:
            "!rounded-xl sm:!rounded-2xl border border-glass-border bg-surface dark:bg-card-bg shadow-surface dark:shadow-surface-strong",
        }}
      >
        <DialogTitle className="text-center font-black tracking-wide text-page-foreground">
          {t("profile:dialog.qr.title")}
        </DialogTitle>
        <DialogContent className="flex flex-col items-center justify-center gap-3 min-h-[320px] p-6">
          <div className="bg-white p-4 rounded-2xl border border-[#0f4faa]/15 shadow-[0_18px_40px_-28px_rgba(0,0,0,0.4)]">
            <QRCodeSVG
              value={buildVCard()}
              size={300}
              level="H"
              includeMargin
              bgColor="#ffffff"
              fgColor="#1a4480"
              imageSettings={{
                src: typeof guuLogo === "string" ? guuLogo : String(guuLogo as any),
                height: 56,
                width: 56,
                excavate: true,
              }}
            />
          </div>
          <p className="text-xs text-secondary text-center">{t("profile:dialog.qr.hint")}</p>
        </DialogContent>
        <DialogActions className="justify-center pb-4">
          <button
            onClick={closeQrModal}
            className="py-2.5 px-6 rounded-lg sm:rounded-xl bg-nav-link dark:bg-nav-link text-white dark:text-[#0b121f] font-extrabold tracking-wide text-sm sm:text-base shadow-surface hover:shadow-surface-strong transition-all duration-300 hover:-translate-y-0.5 hover:scale-[1.01] hover:bg-[#0d4494] dark:hover:bg-[#69a9dc] active:scale-[0.98] border border-nav-link/20 dark:border-nav-link/30"
          >
            {t("common:buttons.done")}
          </button>
        </DialogActions>
      </Dialog>

      {/* Achievement Dialog */}
      <Dialog
        open={!!achOpen}
        onClose={() => setAchOpen(null)}
        maxWidth="xs"
        fullWidth
        PaperProps={{
          className:
            "!rounded-xl sm:!rounded-2xl border border-glass-border bg-surface dark:bg-card-bg shadow-surface dark:shadow-surface-strong",
        }}
      >
        <DialogTitle className="font-black text-page-foreground">{achOpen?.name}</DialogTitle>
        <DialogContent className="grid gap-3 p-6">
          {achOpen?.issuer && (
            <p className="text-page-foreground">
              {t("profile:dialog.achievement.organizer", { issuer: achOpen.issuer })}
            </p>
          )}
          {achOpen?.date && (
            <p className="text-page-foreground">
              {t("profile:dialog.achievement.date", { date: achOpen.date })}
            </p>
          )}
          {achOpen?.url && (
            <a
              href={achOpen.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex justify-center py-2.5 px-6 rounded-lg sm:rounded-xl border-2 border-glass-border bg-transparent hover:bg-surface-accent dark:hover:bg-surface-accent text-page-foreground font-extrabold tracking-wide text-sm sm:text-base transition-all duration-300 hover:-translate-y-0.5 hover:scale-[1.01] active:scale-[0.98] no-underline"
            >
              {t("profile:dialog.achievement.openLink")}
            </a>
          )}
        </DialogContent>
        <DialogActions className="p-4">
          <button
            onClick={() => setAchOpen(null)}
            className="py-2.5 px-6 rounded-lg sm:rounded-xl bg-nav-link dark:bg-nav-link text-white dark:text-[#0b121f] font-extrabold tracking-wide text-sm sm:text-base shadow-surface hover:shadow-surface-strong transition-all duration-300 hover:-translate-y-0.5 hover:scale-[1.01] hover:bg-[#0d4494] dark:hover:bg-[#69a9dc] active:scale-[0.98] border border-nav-link/20 dark:border-nav-link/30"
          >
            {t("profile:dialog.achievement.close")}
          </button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={!!snack}
        autoHideDuration={2600}
        onClose={() => setSnack(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        data-testid={snack?.key === "copied" ? "snackbar-copied" : undefined}
      >
        <Alert
          onClose={() => setSnack(null)}
          severity={snack?.sev || "info"}
          variant="filled"
          sx={{ width: "100%" }}
        >
          {snackMessage}
        </Alert>
      </Snackbar>
    </>
  )
}
