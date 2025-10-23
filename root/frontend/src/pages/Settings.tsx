import { useEffect, useRef, useState, useCallback, useMemo, ChangeEvent, FocusEvent } from "react"
import { isAxiosError } from "axios"
import { useAuth, currentUserQueryKey, fetchCurrentUser } from "@/contexts/AuthContext"
import { useLanguage, type SupportedLanguage } from "@/contexts/LanguageContext"
import { useNavigate } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { usePushPreferences } from "@/hooks/usePushPreferences"
import { nowPlayingQueryKey } from "@/hooks/useNowPlaying"
import api from "../api/client"
import type { User } from "@/types/User"
import type { ActiveSession } from "@/types/Session"
import { useTranslation } from "react-i18next"
import {
  Box,
  Paper,
  Tabs,
  Tab,
  Stack,
  Typography,
  Button,
  Chip,
  Snackbar,
  Alert,
  RadioGroup,
  FormControlLabel,
  Radio,
  Divider,
  Avatar,
  List,
  ListItem,
  ListItemText,
  ListItemAvatar,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  CircularProgress,
} from "@mui/material"
import dayjs from "dayjs"
import { useColorScheme, styled, alpha, darken } from "@mui/material/styles"
import SettingsIcon from "@mui/icons-material/Settings"
import DarkModeIcon from "@mui/icons-material/DarkMode"
import LightModeIcon from "@mui/icons-material/LightMode"
import DesktopWindowsIcon from "@mui/icons-material/DesktopWindows"
import LogoutIcon from "@mui/icons-material/Logout"
import PhotoCameraIcon from "@mui/icons-material/PhotoCamera"
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline"
import ImageIcon from "@mui/icons-material/Image"
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"
const DEFAULT_AVATAR = AVATAR_PLACEHOLDER_URL
import spotifyLogo from "@/assets/spotify_icon.png"
import { addVersionParam, resolveMediaUrl } from "@/utils/media"
import { sanitizeSpotifyAuthorizeUrl } from "@/utils/spotify"

type ThemeMode = "system" | "light" | "dark"

const DEFAULT_DND_START = "22:00"
const DEFAULT_DND_END = "07:00"

const toInputTime = (value: unknown): string => {
  if (!value) return ""
  const str = String(value)
  const match = str.match(/^(\d{2}:\d{2})/)
  return match ? match[1] : ""
}

const toServerTime = (value: string | null): string | null => {
  if (!value) return null
  const trimmed = value.trim()
  if (!trimmed) return null
  if (/^\d{2}:\d{2}$/.test(trimmed)) return `${trimmed}:00`
  if (/^\d{2}:\d{2}:\d{2}$/.test(trimmed)) return trimmed
  return trimmed
}

const ModernSwitch = styled("span")(({ theme }) => {
  const on = theme.palette.primary.main
  const trackBg = theme.palette.mode === "dark" ? alpha("#fff", 0.12) : alpha("#000", 0.08)
  const trackBorder = theme.palette.mode === "dark" ? alpha("#fff", 0.24) : alpha("#000", 0.12)
  const ring = alpha(on, 0.35)

  return {
    position: "relative",
    display: "inline-flex",
    alignItems: "center",
    width: 52,
    height: 28,
    padding: 2,
    borderRadius: 999,
    cursor: "pointer",
    touchAction: "manipulation",
    WebkitTapHighlightColor: "transparent",
    "& input": {
      opacity: 0,
      width: 0,
      height: 0,
      position: "absolute",
    },
    "& .ms-track": {
      position: "absolute",
      inset: 0,
      borderRadius: 999,
      background: trackBg,
      border: `1px solid ${trackBorder}`,
      transition: "background-color .2s ease, border-color .2s ease",
      boxSizing: "border-box",
    },
    "& .ms-thumb": {
      position: "relative",
      zIndex: 1,
      width: 22,
      height: 22,
      borderRadius: "50%",
      background: theme.palette.common.white,
      boxShadow:
        theme.palette.mode === "dark"
          ? "0 1px 2px rgba(0,0,0,.6), 0 0 0 1px rgba(255,255,255,.08) inset"
          : "0 1px 2px rgba(0,0,0,.25), 0 0 0 1px rgba(0,0,0,.06) inset",
      transform: "translateX(0)",
      transition: "transform .18s cubic-bezier(.2,.9,.22,1), box-shadow .18s ease",
    },
    "&.ms-checked .ms-track": {
      background: alpha(on, theme.palette.mode === "dark" ? 0.55 : 0.2),
      borderColor: alpha(on, 0.6),
    },
    "&.ms-checked .ms-thumb": {
      transform: "translateX(24px)",
      boxShadow:
        theme.palette.mode === "dark"
          ? "0 1px 2px rgba(0,0,0,.6), 0 0 0 1px rgba(255,255,255,.08) inset"
          : "0 1px 2px rgba(0,0,0,.25), 0 0 0 1px rgba(0,0,0,.06) inset",
    },
    "&.ms-hover .ms-track": {
      background: theme.palette.mode === "dark" ? alpha("#fff", 0.16) : alpha("#000", 0.1),
    },
    "&.ms-focus .ms-ring": {
      boxShadow: `0 0 0 3px ${ring}`,
      opacity: 1,
      transform: "scale(1)",
    },
    "& .ms-ring": {
      position: "absolute",
      inset: -2,
      borderRadius: 999,
      boxShadow: "0 0 0 0px transparent",
      transition: "box-shadow .18s ease, transform .18s ease, opacity .18s ease",
      pointerEvents: "none",
      opacity: 0,
      transform: "scale(.98)",
    },
    "&.ms-disabled": {
      cursor: "not-allowed",
      opacity: 0.6,
    },
  }
})

function SwitchControl({
  checked,
  disabled,
  onChange,
  inputId,
  "aria-label": ariaLabel,
}: {
  checked: boolean
  disabled?: boolean
  onChange: (e: ChangeEvent<HTMLInputElement>, checked: boolean) => void
  inputId?: string
  "aria-label"?: string
}) {
  const [hover, setHover] = useState(false)
  const [focus, setFocus] = useState(false)
  return (
    <ModernSwitch
      className={[
        checked ? "ms-checked" : "",
        disabled ? "ms-disabled" : "",
        hover ? "ms-hover" : "",
        focus ? "ms-focus" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <span className="ms-ring" />
      <span className="ms-track" />
      <span className="ms-thumb" />
      <input
        id={inputId}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        aria-label={ariaLabel}
        onChange={(e) => onChange(e, e.target.checked)}
        onFocus={() => setFocus(true)}
        onBlur={() => setFocus(false)}
      />
    </ModernSwitch>
  )
}

export default function Settings() {
  const navigate = useNavigate()
  const { user, setUser, logout } = useAuth()
  const queryClient = useQueryClient()
  const [tab, setTab] = useState(0)
  const [snack, setSnack] = useState<{
    text: string
    sev?: "success" | "info" | "warning" | "error"
  } | null>(null)
  const { language, setLanguage, available: availableLanguages } = useLanguage()
  const { t } = useTranslation(["settings", "common", "notifications", "profile"])

  const { mode: storedMode, setMode } = useColorScheme()
  const theme = (storedMode ?? "system") as ThemeMode

  const timeFieldSx = useMemo(
    () => ({
      maxWidth: { xs: "100%", sm: 200 },
      "& .MuiOutlinedInput-root": {
        borderRadius: 2.5,
        overflow: "hidden",
        backgroundColor: "var(--card-bg)",
        "& fieldset": {
          borderColor: "color-mix(in srgb, var(--page-text) 24%, transparent)",
          borderWidth: 1,
        },
        "&:hover fieldset": {
          borderColor: "color-mix(in srgb, var(--page-text) 32%, transparent)",
        },
        "&.Mui-focused": {
          boxShadow: "0 0 0 3px color-mix(in srgb, var(--link-color) 22%, transparent)",
        },
        "&.Mui-focused fieldset": {
          borderColor: "var(--link-color)",
        },
        "&.Mui-disabled": {
          backgroundColor: "color-mix(in srgb, var(--page-text) 6%, transparent)",
        },
        "&.Mui-disabled fieldset": {
          borderColor: "color-mix(in srgb, var(--page-text) 18%, transparent)",
        },
      },
      "& .MuiInputBase-input": {
        textAlign: "center",
        fontVariantNumeric: "tabular-nums",
      },
      "& .MuiInputLabel-root": {
        px: 0.75,
        backgroundColor: "var(--card-bg)",
        color: "var(--page-text)",
      },
    }),
    []
  )

  const {
    pushSupported,
    notificationPermission,
    notificationsEnabled,
    pushBusy,
    pushInitializing,
    permissionText,
    enableNotifications,
    disableNotifications,
  } = usePushPreferences({ onNotify: setSnack })

  const [dndEnabled, setDndEnabled] = useState(false)
  const [dndStart, setDndStart] = useState("")
  const [dndEnd, setDndEnd] = useState("")
  const [dndSaving, setDndSaving] = useState(false)

  const [avatarVersion, setAvatarVersion] = useState(Date.now())
  const [coverVersion, setCoverVersion] = useState(Date.now())

  const sessionsKey = useMemo(() => ["auth", "sessions", user?.id ?? "me"], [user?.id])

  const fetchSessions = useCallback(async () => {
    const { data } = await api.get<ActiveSession[]>("/auth/sessions")
    return data
  }, [])

  const {
    data: sessions = [],
    isFetching: sessionsFetching,
    isError: sessionsIsError,
    error: sessionsError,
    refetch: refetchSessions,
  } = useQuery<ActiveSession[]>({
    queryKey: sessionsKey,
    queryFn: fetchSessions,
    enabled: tab === 1 && Boolean(user),
    staleTime: 30_000,
  })

  const sessionList = useMemo(() => (Array.isArray(sessions) ? sessions : []), [sessions])

  const revokeSessionMutation = useMutation({
    mutationFn: async (sessionId: number) => {
      const { data } = await api.delete<ActiveSession>(`/auth/sessions/${sessionId}`)
      return data
    },
  })

  const syncDndFromUser = useCallback((value: User | null) => {
    const enabled = Boolean(value?.dnd_enabled)
    const start = toInputTime(value?.dnd_start)
    const end = toInputTime(value?.dnd_end)
    setDndEnabled(enabled)
    setDndStart(start || (enabled ? DEFAULT_DND_START : ""))
    setDndEnd(end || (enabled ? DEFAULT_DND_END : ""))
  }, [])

  const persistDnd = useCallback(
    async (nextEnabled: boolean, nextStart: string | null, nextEnd: string | null) => {
      if (dndSaving) return
      const normalizedStart = nextStart ? nextStart.trim() : null
      const normalizedEnd = nextEnd ? nextEnd.trim() : null
      const prevEnabled = Boolean(user?.dnd_enabled)
      const prevStart = toInputTime(user?.dnd_start)
      const prevEnd = toInputTime(user?.dnd_end)
      if (
        nextEnabled === prevEnabled &&
        (!nextEnabled ||
          (normalizedStart &&
            normalizedEnd &&
            normalizedStart === prevStart &&
            normalizedEnd === prevEnd))
      ) {
        return
      }
      if (nextEnabled && (!normalizedStart || !normalizedEnd)) {
        setSnack({ text: t("settings:dnd.validation.missingRange"), sev: "warning" })
        syncDndFromUser(user)
        return
      }
      setDndSaving(true)
      try {
        const payload: Record<string, unknown> = { dnd_enabled: nextEnabled }
        if (nextEnabled) {
          payload.dnd_start = toServerTime(normalizedStart)
          payload.dnd_end = toServerTime(normalizedEnd)
        } else {
          payload.dnd_start = null
          payload.dnd_end = null
        }
        const res = await api.put<User>("/users/me", payload)
        setUser(res.data)
        syncDndFromUser(res.data)
        const wasEnabled = prevEnabled
        let message: string
        if (nextEnabled && !wasEnabled) message = t("settings:dnd.snackbar.enabled")
        else if (!nextEnabled && wasEnabled) message = t("settings:dnd.snackbar.disabled")
        else message = t("settings:dnd.snackbar.updated")
        setSnack({ text: message, sev: "success" })
      } catch (error: unknown) {
        let message = t("settings:dnd.snackbar.updateFailed")
        if (isAxiosError(error)) {
          const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
          if (typeof detail === "string") message = detail
          else if (Array.isArray(detail)) {
            const collected = detail
              .map((item: unknown) =>
                item && typeof item === "object" && "msg" in item
                  ? String((item as { msg?: unknown }).msg)
                  : ""
              )
              .filter(Boolean)
              .join("; ")
            if (collected) message = collected
          }
        }
        setSnack({ text: message, sev: "error" })
        syncDndFromUser(user)
      } finally {
        setDndSaving(false)
      }
    },
    [dndSaving, setUser, setSnack, syncDndFromUser, t, user]
  )

  const handleDndToggle = useCallback(
    (_: ChangeEvent<HTMLInputElement>, checked: boolean) => {
      if (dndSaving) return
      const nextStart = checked ? dndStart || DEFAULT_DND_START : dndStart
      const nextEnd = checked ? dndEnd || DEFAULT_DND_END : dndEnd
      if (checked) {
        setDndStart(nextStart)
        setDndEnd(nextEnd)
      }
      setDndEnabled(checked)
      void persistDnd(checked, checked ? nextStart : null, checked ? nextEnd : null)
    },
    [dndSaving, dndEnd, dndStart, persistDnd]
  )

  const handleDndStartChange = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    setDndStart(event.target.value)
  }, [])

  const handleDndStartBlur = useCallback(
    (event: FocusEvent<HTMLInputElement>) => {
      if (!dndEnabled || dndSaving) return
      const value = (event.currentTarget.value || "").trim()
      setDndStart(value)
      void persistDnd(true, value || null, dndEnd || null)
    },
    [dndEnabled, dndEnd, dndSaving, persistDnd]
  )

  const handleDndEndChange = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    setDndEnd(event.target.value)
  }, [])

  const handleDndEndBlur = useCallback(
    (event: FocusEvent<HTMLInputElement>) => {
      if (!dndEnabled || dndSaving) return
      const value = (event.currentTarget.value || "").trim()
      setDndEnd(value)
      void persistDnd(true, dndStart || null, value || null)
    },
    [dndEnabled, dndSaving, dndStart, persistDnd]
  )

  useEffect(() => {
    syncDndFromUser(user)
  }, [syncDndFromUser, user])

  useEffect(() => {
    const sp = new URLSearchParams(window.location.search)
    const s = sp.get("spotify")
    if (s) {
      if (s === "connected")
        setSnack({ text: t("settings:integrations.spotify.snackbar.connected"), sev: "success" })
      if (s === "error")
        setSnack({ text: t("settings:integrations.spotify.snackbar.connectFailed"), sev: "error" })
      sp.delete("spotify")
      const next = window.location.pathname + (sp.toString() ? "?" + sp : "")
      window.history.replaceState({}, "", next)
    }
  }, [setSnack, t])

  const handleThemeChange = useCallback(
    (_: ChangeEvent<HTMLInputElement>, value: string) => {
      setMode(value as ThemeMode)
    },
    [setMode]
  )

  const handleNotificationsToggle = useCallback(
    (_: ChangeEvent<HTMLInputElement>, checked: boolean) => {
      if (pushBusy || pushInitializing) return
      if (checked) void enableNotifications()
      else void disableNotifications()
    },
    [disableNotifications, enableNotifications, pushBusy, pushInitializing]
  )

  const spotifyConnected = Boolean(user?.spotify_connected || user?.spotify_is_connected)
  const spotifyName = user?.spotify_display_name ?? ""

  const connectSpotify = async () => {
    try {
      const { data } = await api.get<{ url?: string }>("/spotify/auth-url")
      const safeUrl = sanitizeSpotifyAuthorizeUrl(data?.url)
      if (!safeUrl) throw new Error("Received unsafe Spotify authorization URL")
      window.location.assign(safeUrl)
    } catch (error) {
      setSnack({ text: t("settings:integrations.spotify.snackbar.openFailed"), sev: "error" })
    }
  }

  const disconnectSpotify = async () => {
    try {
      await api.post("/spotify/disconnect")
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: currentUserQueryKey }),
        queryClient.invalidateQueries({ queryKey: nowPlayingQueryKey }),
      ])
      try {
        const profile = await fetchCurrentUser()
        setUser(profile)
      } catch {
        setUser((prev) =>
          prev
            ? {
                ...prev,
                spotify_connected: false,
                spotify_is_connected: false,
                spotify_display_name: null,
              }
            : prev
        )
      }
      setSnack({ text: t("settings:integrations.spotify.snackbar.disconnected"), sev: "success" })
    } catch {
      setSnack({ text: t("settings:integrations.spotify.snackbar.disconnectFailed"), sev: "error" })
    }
  }

  const isImage = (f: File) => /^image\/(png|jpe?g|webp|gif|avif)$/i.test(f.type)
  const withinSize = (f: File, maxMB = 12) => f.size / (1024 * 1024) <= maxMB

  const avatarInputRef = useRef<HTMLInputElement | null>(null)
  const coverInputRef = useRef<HTMLInputElement | null>(null)
  const [avatarBusy, setAvatarBusy] = useState(false)
  const [coverBusy, setCoverBusy] = useState(false)

  const avatarUrl = user?.avatar_url ?? undefined
  const coverUrl = user?.cover_url ?? undefined

  const avatarSrc = useMemo(() => {
    const resolved = resolveMediaUrl(avatarUrl)
    return resolved ? addVersionParam(resolved, avatarVersion) : DEFAULT_AVATAR
  }, [avatarUrl, avatarVersion])

  const coverSrc = useMemo(() => {
    const resolved = resolveMediaUrl(coverUrl)
    return resolved ? addVersionParam(resolved, coverVersion) : ""
  }, [coverUrl, coverVersion])

  const handleAvatarError = useCallback((event: React.SyntheticEvent<HTMLImageElement>) => {
    const img = event.currentTarget
    img.onerror = null
    img.src = DEFAULT_AVATAR
  }, [])

  const triggerAvatarPick = () => avatarInputRef.current?.click()
  const triggerCoverPick = () => coverInputRef.current?.click()

  const refreshMe = useCallback(async () => {
    const fresh = await queryClient.fetchQuery<User>({
      queryKey: currentUserQueryKey,
      queryFn: fetchCurrentUser,
      staleTime: 0,
    })
    setUser(fresh)
    return fresh
  }, [queryClient, setUser])

  const resolveDetailMessage = useCallback((error: unknown, fallback: string) => {
    if (isAxiosError(error)) {
      const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
      if (typeof detail === "string") return detail
      if (Array.isArray(detail)) {
        const combined = detail
          .map((item) =>
            item && typeof item === "object" && "msg" in item
              ? String((item as { msg?: unknown }).msg)
              : ""
          )
          .filter(Boolean)
          .join("; ")
        if (combined) return combined
      }
    }
    return fallback
  }, [])

  const handleRevokeSession = useCallback(
    async (sessionId: number) => {
      try {
        const result = await revokeSessionMutation.mutateAsync(sessionId)
        setSnack({ text: t("settings:sessions.snackbar.revoked"), sev: "success" })
        await refetchSessions()
        if (result?.is_current) {
          await logout()
        }
      } catch (error) {
        setSnack({
          text: resolveDetailMessage(error, t("settings:sessions.snackbar.failed")),
          sev: "error",
        })
      }
    },
    [logout, refetchSessions, resolveDetailMessage, revokeSessionMutation, t]
  )

  const formatSessionTimestamp = useCallback(
    (value: string | null) => {
      if (!value) return t("settings:sessions.lastSeen.never")
      const parsed = dayjs(value)
      if (!parsed.isValid()) return t("settings:sessions.lastSeen.never")
      return parsed.format("DD MMM YYYY HH:mm")
    },
    [t]
  )

  const sessionsErrorMessage = useMemo(
    () =>
      sessionsIsError
        ? resolveDetailMessage(sessionsError, t("settings:sessions.loadFailed"))
        : null,
    [resolveDetailMessage, sessionsError, sessionsIsError, t]
  )

  const uploadAvatar = async (file: File) => {
    if (!isImage(file))
      return setSnack({ text: t("settings:media.validation.supportedFormats"), sev: "warning" })
    if (!withinSize(file))
      return setSnack({ text: t("settings:media.validation.fileTooLarge"), sev: "warning" })
    try {
      setAvatarBusy(true)
      const fd = new FormData()
      fd.append("file", file)
      await api.post("/users/me/avatar", fd, { headers: { "Content-Type": "multipart/form-data" } })
      await refreshMe()
      setAvatarVersion(Date.now())
      setSnack({ text: t("settings:media.avatar.updated"), sev: "success" })
    } catch (error) {
      setSnack({
        text: resolveDetailMessage(error, t("settings:media.avatar.uploadFailed")),
        sev: "error",
      })
    } finally {
      setAvatarBusy(false)
      if (avatarInputRef.current) avatarInputRef.current.value = ""
    }
  }

  const removeAvatar = async () => {
    try {
      setAvatarBusy(true)
      await api.delete("/users/me/avatar")
      await refreshMe()
      setAvatarVersion(Date.now())
      setSnack({ text: t("settings:media.avatar.deleted"), sev: "success" })
    } catch (error) {
      setSnack({
        text: resolveDetailMessage(error, t("settings:media.avatar.deleteFailed")),
        sev: "error",
      })
    } finally {
      setAvatarBusy(false)
    }
  }

  const uploadCover = async (file: File) => {
    if (!isImage(file))
      return setSnack({ text: t("settings:media.validation.supportedFormats"), sev: "warning" })
    if (!withinSize(file))
      return setSnack({ text: t("settings:media.validation.fileTooLarge"), sev: "warning" })
    try {
      setCoverBusy(true)
      const fd = new FormData()
      fd.append("file", file)
      await api.post("/users/me/cover", fd, { headers: { "Content-Type": "multipart/form-data" } })
      await refreshMe()
      setCoverVersion(Date.now())
      setSnack({ text: t("settings:media.cover.updated"), sev: "success" })
    } catch (error) {
      setSnack({
        text: resolveDetailMessage(error, t("settings:media.cover.uploadFailed")),
        sev: "error",
      })
    } finally {
      setCoverBusy(false)
      if (coverInputRef.current) coverInputRef.current.value = ""
    }
  }

  const [confirmLogout, setConfirmLogout] = useState(false)

  return (
    <Box maxWidth="100vw" mx={0} mt={0} width="100vw" minHeight="100svh" px={0}>
      <Paper
        className="glass glass--panel"
        sx={{
          p: { xs: 2, md: 4, lg: 6 },
          borderRadius: 0,
          width: "100%",
          minHeight: "100svh",
          color: "var(--page-text)",
          bgcolor: "var(--card-bg)",
        }}
      >
        <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: { xs: 1.5, md: 2 } }}>
          <SettingsIcon />
          <Typography variant="h4" fontWeight={800} sx={{ color: "var(--page-text)" }}>
            {t("settings:page.title")}
          </Typography>
        </Stack>

        <Paper
          variant="outlined"
          className="glass--segmented"
          sx={{ mb: 3, bgcolor: "var(--card-bg)" }}
        >
          <Tabs
            value={tab}
            onChange={(_, v) => setTab(v)}
            variant="scrollable"
            scrollButtons="auto"
            sx={{
              "& .MuiTab-root": {
                color: "var(--page-text)",
                textTransform: "none",
                fontWeight: 700,
                minHeight: 42,
              },
              "& .Mui-selected": { color: "var(--link-color)" },
            }}
          >
            <Tab label={t("settings:tabs.general")} />
            <Tab label={t("settings:tabs.account")} />
            <Tab label={t("settings:tabs.integrations")} />
          </Tabs>
        </Paper>

        {tab === 0 && (
          <Stack spacing={3}>
            <Box>
              <Typography variant="h6" sx={{ mb: 1.2, color: "var(--page-text)" }}>
                {t("settings:appearance.theme.title")}
              </Typography>
              <RadioGroup row value={theme} onChange={handleThemeChange}>
                <FormControlLabel
                  value="system"
                  control={<Radio />}
                  label={
                    <Stack
                      direction="row"
                      alignItems="center"
                      spacing={1}
                      sx={{ color: "var(--page-text)" }}
                    >
                      <DesktopWindowsIcon />{" "}
                      <span>{t("settings:appearance.theme.options.system")}</span>
                    </Stack>
                  }
                  sx={{ "& .MuiFormControlLabel-label": { color: "var(--page-text)" } }}
                />
                <FormControlLabel
                  value="light"
                  control={<Radio />}
                  label={
                    <Stack
                      direction="row"
                      alignItems="center"
                      spacing={1}
                      sx={{ color: "var(--page-text)" }}
                    >
                      <LightModeIcon /> <span>{t("settings:appearance.theme.options.light")}</span>
                    </Stack>
                  }
                  sx={{ "& .MuiFormControlLabel-label": { color: "var(--page-text)" } }}
                />
                <FormControlLabel
                  value="dark"
                  control={<Radio />}
                  label={
                    <Stack
                      direction="row"
                      alignItems="center"
                      spacing={1}
                      sx={{ color: "var(--page-text)" }}
                    >
                      <DarkModeIcon /> <span>{t("settings:appearance.theme.options.dark")}</span>
                    </Stack>
                  }
                  sx={{ "& .MuiFormControlLabel-label": { color: "var(--page-text)" } }}
                />
              </RadioGroup>
            </Box>

            <Box>
              <Typography variant="h6" sx={{ mb: 1.2, color: "var(--page-text)" }}>
                {t("settings:language.title")}
              </Typography>
              <RadioGroup
                row
                value={language}
                onChange={(_, value) => setLanguage(value as SupportedLanguage)}
                aria-label={t("settings:language.aria")}
              >
                {availableLanguages.map((code) => (
                  <FormControlLabel
                    key={code}
                    value={code}
                    control={<Radio />}
                    label={t(`settings:language.options.${code}`)}
                    sx={{ "& .MuiFormControlLabel-label": { color: "var(--page-text)" } }}
                  />
                ))}
              </RadioGroup>
              <Typography variant="body2" sx={{ mt: 0.5, color: "var(--page-text)" }}>
                {t("settings:language.description")}
              </Typography>
            </Box>

            <Divider />

            <Box>
              <Typography variant="h6" sx={{ mb: 1.2, color: "var(--page-text)" }}>
                {t("settings:notifications.title")}
              </Typography>
              {!pushSupported ? (
                <Alert severity="warning" variant="outlined">
                  {t("settings:notifications.unsupported")}
                </Alert>
              ) : (
                <Stack spacing={1.8}>
                  {notificationPermission === "denied" ? (
                    <Stack spacing={1.5}>
                      <Alert severity="error" variant="outlined">
                        {t("settings:notifications.blocked.description")}
                      </Alert>
                      <Typography variant="body2" sx={{ color: "var(--page-text)" }}>
                        {t("settings:notifications.blocked.hint")}
                      </Typography>
                      <Stack
                        direction={{ xs: "column", sm: "row" }}
                        spacing={1.2}
                        alignItems={{ sm: "center" }}
                      >
                        <Button
                          variant="contained"
                          onClick={() => void enableNotifications()}
                          disabled={pushBusy}
                          startIcon={
                            pushBusy ? <CircularProgress size={18} color="inherit" /> : undefined
                          }
                        >
                          {t("settings:notifications.cta.checkPermission")}
                        </Button>
                        <Typography variant="body2" sx={{ color: "var(--page-text)" }}>
                          {t("settings:notifications.status", { status: permissionText })}
                        </Typography>
                      </Stack>
                    </Stack>
                  ) : notificationPermission === "default" ? (
                    <Stack spacing={1.5}>
                      <Typography variant="body2" sx={{ color: "var(--page-text)" }}>
                        {t("settings:notifications.cta.prompt")}
                      </Typography>
                      <Stack
                        direction={{ xs: "column", sm: "row" }}
                        spacing={1.2}
                        alignItems={{ sm: "center" }}
                      >
                        <Button
                          variant="contained"
                          onClick={() => void enableNotifications()}
                          disabled={pushBusy || pushInitializing}
                          startIcon={
                            pushBusy || pushInitializing ? (
                              <CircularProgress size={18} color="inherit" />
                            ) : undefined
                          }
                        >
                          {t("settings:notifications.cta.allow")}
                        </Button>
                        <Typography variant="body2" sx={{ color: "var(--page-text)" }}>
                          {t("settings:notifications.status", { status: permissionText })}
                        </Typography>
                      </Stack>
                    </Stack>
                  ) : (
                    <>
                      <FormControlLabel
                        sx={{
                          minHeight: 44,
                          alignItems: "center",
                          columnGap: 1.25,
                          m: 0,
                        }}
                        control={
                          <SwitchControl
                            checked={notificationsEnabled}
                            onChange={handleNotificationsToggle}
                            disabled={pushBusy || pushInitializing}
                            aria-label={t("settings:notifications.toggles.notifications.aria")}
                          />
                        }
                        label={
                          <span style={{ color: "var(--page-text)", fontWeight: 700 }}>
                            {t("settings:notifications.toggles.notifications.label")}
                          </span>
                        }
                      />

                      <FormControlLabel
                        sx={{
                          minHeight: 44,
                          alignItems: "center",
                          columnGap: 1.25,
                          m: 0,
                        }}
                        control={
                          <SwitchControl
                            checked={dndEnabled}
                            onChange={handleDndToggle}
                            disabled={dndSaving}
                            aria-label={t("settings:notifications.toggles.dnd.aria")}
                          />
                        }
                        label={
                          <span style={{ color: "var(--page-text)", fontWeight: 700 }}>
                            {t("settings:notifications.toggles.dnd.label")}
                          </span>
                        }
                      />

                      <Stack
                        direction={{ xs: "column", sm: "row" }}
                        spacing={1.5}
                        alignItems={{ sm: "center" }}
                      >
                        <TextField
                          type="time"
                          label={t("settings:dnd.start")}
                          value={dndStart}
                          onChange={handleDndStartChange}
                          onBlur={handleDndStartBlur}
                          disabled={!dndEnabled || dndSaving}
                          size="small"
                          InputLabelProps={{ shrink: true }}
                          sx={timeFieldSx}
                        />
                        <TextField
                          type="time"
                          label={t("settings:dnd.end")}
                          value={dndEnd}
                          onChange={handleDndEndChange}
                          onBlur={handleDndEndBlur}
                          disabled={!dndEnabled || dndSaving}
                          size="small"
                          InputLabelProps={{ shrink: true }}
                          sx={timeFieldSx}
                        />
                      </Stack>
                    </>
                  )}
                </Stack>
              )}
            </Box>
          </Stack>
        )}

        {tab === 1 && (
          <Box sx={{ width: "100%", maxWidth: { xs: "100%", sm: 640, md: 760, lg: 880 } }}>
            <List dense disablePadding>
              <ListItem
                divider
                secondaryAction={
                  <Stack direction="row" spacing={1}>
                    <Button
                      size="small"
                      variant="text"
                      startIcon={<PhotoCameraIcon />}
                      onClick={triggerAvatarPick}
                      disabled={avatarBusy}
                    >
                      {t("settings:media.avatar.change")}
                    </Button>
                    <Button
                      size="small"
                      variant="text"
                      color="error"
                      startIcon={<DeleteOutlineIcon />}
                      onClick={removeAvatar}
                      disabled={avatarBusy}
                    >
                      {t("settings:media.avatar.delete")}
                    </Button>
                  </Stack>
                }
              >
                <ListItemAvatar>
                  <Avatar
                    src={avatarSrc}
                    alt={user?.full_name || "avatar"}
                    sx={{ width: 48, height: 48 }}
                    imgProps={{
                      onError: handleAvatarError,
                      loading: "lazy",
                      decoding: "async",
                      referrerPolicy: "no-referrer",
                    }}
                  />
                </ListItemAvatar>
                <ListItemText
                  primary={t("settings:media.avatar.title")}
                  secondary={t("settings:media.avatar.subtitle")}
                />
                <input
                  ref={avatarInputRef}
                  type="file"
                  accept="image/*"
                  hidden
                  onChange={(e) => {
                    const f = e.currentTarget.files?.[0]
                    if (f) uploadAvatar(f)
                  }}
                />
              </ListItem>

              <ListItem
                divider
                secondaryAction={
                  <Button
                    size="small"
                    variant="text"
                    startIcon={<ImageIcon />}
                    onClick={triggerCoverPick}
                    disabled={coverBusy}
                  >
                    {t("settings:media.cover.change")}
                  </Button>
                }
              >
                <ListItemAvatar sx={{ mr: 1.25 }}>
                  <Box
                    data-testid="settings-cover-preview"
                    sx={{
                      width: 120,
                      height: 52,
                      borderRadius: 1.5,
                      border: "1px solid var(--glass-border)",
                      background: coverSrc
                        ? `url(${coverSrc}) center/cover no-repeat`
                        : "var(--card-bg)",
                    }}
                  />
                </ListItemAvatar>
                <ListItemText
                  primary={t("settings:media.cover.title")}
                  secondary={t("settings:media.cover.recommendation")}
                />
                <input
                  ref={coverInputRef}
                  type="file"
                  accept="image/*"
                  hidden
                  onChange={(e) => {
                    const f = e.currentTarget.files?.[0]
                    if (f) uploadCover(f)
                  }}
                />
              </ListItem>

              <ListItem
                divider
                secondaryAction={
                  <Button
                    size="small"
                    variant="text"
                    onClick={() => navigate({ pathname: "/profile", search: "?edit=1" })}
                  >
                    {t("common:buttons.edit")}
                  </Button>
                }
              >
                <ListItemText
                  primary={t("settings:account.profile.title")}
                  secondary={t("settings:account.profile.subtitle")}
                />
              </ListItem>
            </List>

            <Divider sx={{ my: 2 }} />

            <Box>
              <Typography variant="h6" sx={{ color: "var(--page-text)", mb: 0.5 }}>
                {t("settings:sessions.title")}
              </Typography>
              <Typography
                variant="body2"
                sx={{ color: "color-mix(in srgb, var(--page-text) 72%, transparent)" }}
              >
                {t("settings:sessions.subtitle")}
              </Typography>

              {sessionsFetching ? (
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 2 }}>
                  <CircularProgress size={18} />
                  <Typography variant="body2" sx={{ color: "var(--page-text)" }}>
                    {t("settings:sessions.loading")}
                  </Typography>
                </Stack>
              ) : sessionsErrorMessage ? (
                <Alert severity="error" variant="outlined" sx={{ mt: 2 }}>
                  {sessionsErrorMessage}
                </Alert>
              ) : sessionList.length === 0 ? (
                <Typography variant="body2" sx={{ mt: 2, color: "var(--page-text)" }}>
                  {t("settings:sessions.empty")}
                </Typography>
              ) : (
                <List disablePadding sx={{ mt: 1 }}>
                  {sessionList.map((session) => {
                    const lastSeen = session.last_seen_at ?? session.created_at
                    const lastSeenText = t("settings:sessions.lastSeen.value", {
                      value: formatSessionTimestamp(lastSeen),
                    })
                    const ipLabel = session.ip_address
                      ? t("settings:sessions.ipAddress", { ip: session.ip_address })
                      : t("settings:sessions.ipUnknown")
                    const details = `${ipLabel} • ${lastSeenText}`
                    const revoked = Boolean(session.revoked_at)
                    const statusLabel = revoked
                      ? t("settings:sessions.status.revoked")
                      : session.is_current
                        ? t("settings:sessions.status.current")
                        : t("settings:sessions.status.active")
                    const statusColor: "default" | "primary" | "success" = revoked
                      ? "default"
                      : session.is_current
                        ? "primary"
                        : "success"
                    const disableRevoke =
                      revoked || session.is_current || revokeSessionMutation.isPending
                    return (
                      <ListItem
                        key={session.id}
                        alignItems="flex-start"
                        divider
                        sx={{
                          opacity: revoked ? 0.6 : 1,
                        }}
                        secondaryAction={
                          <Stack direction="row" spacing={1} alignItems="center">
                            <Chip
                              size="small"
                              color={statusColor}
                              label={statusLabel}
                              variant={revoked ? "outlined" : "filled"}
                            />
                            {!revoked && (
                              <Button
                                size="small"
                                variant="text"
                                color="error"
                                disabled={disableRevoke}
                                onClick={() => void handleRevokeSession(session.id)}
                              >
                                {t("settings:sessions.revoke")}
                              </Button>
                            )}
                          </Stack>
                        }
                      >
                        <ListItemText
                          primary={session.user_agent || t("settings:sessions.unknownDevice")}
                          secondary={details}
                          primaryTypographyProps={{
                            sx: {
                              color: "var(--page-text)",
                              fontWeight: session.is_current ? 600 : 500,
                            },
                          }}
                          secondaryTypographyProps={{
                            sx: {
                              color: "color-mix(in srgb, var(--page-text) 68%, transparent)",
                            },
                          }}
                        />
                      </ListItem>
                    )
                  })}
                </List>
              )}
            </Box>

            <Box sx={{ pt: 1.5, mt: 2, borderTop: "1px solid var(--glass-border)" }}>
              <List dense disablePadding>
                <ListItem>
                  <Button
                    size="small"
                    variant="text"
                    color="error"
                    startIcon={<LogoutIcon />}
                    onClick={async () => {
                      setConfirmLogout(false)
                      await logout()
                    }}
                    sx={{ px: 0 }}
                  >
                    {t("settings:account.logout.button")}
                  </Button>
                </ListItem>
              </List>
            </Box>
          </Box>
        )}

        {tab === 2 && (
          <Stack spacing={3}>
            <Stack spacing={2}>
              <Stack direction="row" alignItems="center" spacing={1}>
                <img
                  src={spotifyLogo}
                  alt={t("settings:integrations.spotify.alt")}
                  width={22}
                  height={22}
                  style={{ display: "block", borderRadius: "50%" }}
                  loading="lazy"
                  decoding="async"
                />
                <Typography variant="h6" sx={{ color: "var(--page-text)" }}>
                  {t("settings:integrations.spotify.title")}
                </Typography>
              </Stack>
              <Stack direction="row" alignItems="center" spacing={1.2} flexWrap="wrap">
                <Chip
                  size="small"
                  className="glass--chip"
                  label={
                    spotifyConnected
                      ? t("settings:integrations.spotify.status.connected")
                      : t("settings:integrations.spotify.status.disconnected")
                  }
                  color={spotifyConnected ? "success" : "default"}
                  variant="outlined"
                />
                {spotifyConnected && !!spotifyName && (
                  <Chip size="small" variant="outlined" label={spotifyName} />
                )}
              </Stack>
              {!spotifyConnected ? (
                <Button
                  variant="contained"
                  onClick={connectSpotify}
                  sx={{ alignSelf: "flex-start" }}
                >
                  {t("settings:integrations.spotify.connect")}
                </Button>
              ) : (
                <Button
                  variant="outlined"
                  color="error"
                  onClick={disconnectSpotify}
                  sx={{ alignSelf: "flex-start" }}
                >
                  {t("settings:integrations.spotify.disconnect")}
                </Button>
              )}
            </Stack>
          </Stack>
        )}
      </Paper>

      <Dialog open={confirmLogout} onClose={() => setConfirmLogout(false)} maxWidth="xs" fullWidth>
        <DialogTitle>{t("settings:account.logout.dialogTitle")}</DialogTitle>
        <DialogContent>
          <Typography variant="body2">{t("settings:account.logout.dialogDescription")}</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmLogout(false)}>{t("common:buttons.cancel")}</Button>
          <Button
            color="error"
            onClick={async () => {
              setConfirmLogout(false)
              await logout()
            }}
          >
            {t("settings:account.logout.confirm")}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={!!snack}
        autoHideDuration={2600}
        onClose={() => setSnack(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert
          onClose={() => setSnack(null)}
          severity={snack?.sev || "info"}
          variant="filled"
          sx={{ width: "100%" }}
        >
          {snack?.text}
        </Alert>
      </Snackbar>
    </Box>
  )
}
