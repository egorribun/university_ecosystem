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
  Container,
  Paper,
  Box,
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
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  CircularProgress,
  Switch,
} from "@mui/material"
import dayjs from "dayjs"
import { useColorScheme, styled, useTheme } from "@mui/material/styles"
import SettingsIcon from "@mui/icons-material/Settings"
import DarkModeIcon from "@mui/icons-material/DarkMode"
import LightModeIcon from "@mui/icons-material/LightMode"
import DesktopWindowsIcon from "@mui/icons-material/DesktopWindows"
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

const SectionCard = styled(Paper)(({ theme }) => ({
  padding: theme.spacing(3),
  borderRadius: theme.shape.borderRadius * 2,
  border: `1px solid ${theme.palette.divider}`,
  backgroundColor: theme.palette.background.paper,
  boxShadow: "none",
}))

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
  const themeMode = (storedMode ?? "system") as ThemeMode
  const muiTheme = useTheme()
  const mutedTextColor = muiTheme.palette.text.secondary
  const accentColor = muiTheme.palette.primary.main

  const timeFieldSx = useMemo(
    () => ({
      maxWidth: { xs: "100%", sm: 200 },
      "& .MuiOutlinedInput-root": {
        borderRadius: muiTheme.shape.borderRadius,
      },
      "& .MuiInputBase-input": {
        textAlign: "center",
        fontVariantNumeric: "tabular-nums",
      },
    }),
    [muiTheme]
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

  const visibleSessions = useMemo(() => {
    if (!Array.isArray(sessions)) return []
    const cutoff = dayjs().subtract(1, "hour")
    return sessions.filter((session) => {
      if (!session.revoked_at) return true
      return cutoff.isBefore(dayjs(session.revoked_at))
    })
  }, [sessions])

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

  const generalTab = (
    <Stack spacing={3}>
      <SectionCard>
        <Stack spacing={2}>
          <Typography variant="h6">{t("settings:appearance.theme.title")}</Typography>
          <RadioGroup row value={themeMode} onChange={handleThemeChange}>
            <FormControlLabel
              value="system"
              control={<Radio />}
              label={
                <Stack direction="row" alignItems="center" spacing={1}>
                  <DesktopWindowsIcon fontSize="small" />
                  <Typography variant="body2">
                    {t("settings:appearance.theme.options.system")}
                  </Typography>
                </Stack>
              }
            />
            <FormControlLabel
              value="light"
              control={<Radio />}
              label={
                <Stack direction="row" alignItems="center" spacing={1}>
                  <LightModeIcon fontSize="small" />
                  <Typography variant="body2">
                    {t("settings:appearance.theme.options.light")}
                  </Typography>
                </Stack>
              }
            />
            <FormControlLabel
              value="dark"
              control={<Radio />}
              label={
                <Stack direction="row" alignItems="center" spacing={1}>
                  <DarkModeIcon fontSize="small" />
                  <Typography variant="body2">
                    {t("settings:appearance.theme.options.dark")}
                  </Typography>
                </Stack>
              }
            />
          </RadioGroup>
        </Stack>
      </SectionCard>

      <SectionCard>
        <Stack spacing={1.5}>
          <Typography variant="h6">{t("settings:language.title")}</Typography>
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
              />
            ))}
          </RadioGroup>
          <Typography variant="body2" color="text.secondary">
            {t("settings:language.description")}
          </Typography>
        </Stack>
      </SectionCard>

      <SectionCard>
        <Stack spacing={2}>
          <Typography variant="h6">{t("settings:notifications.title")}</Typography>
          {!pushSupported ? (
            <Alert severity="warning" variant="outlined">
              {t("settings:notifications.unsupported")}
            </Alert>
          ) : notificationPermission === "denied" ? (
            <Stack spacing={1.5}>
              <Alert severity="error" variant="outlined">
                {t("settings:notifications.blocked.description")}
              </Alert>
              <Typography variant="body2" color="text.secondary">
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
                  startIcon={pushBusy ? <CircularProgress size={18} color="inherit" /> : undefined}
                >
                  {t("settings:notifications.cta.checkPermission")}
                </Button>
                <Typography variant="body2" color="text.secondary">
                  {t("settings:notifications.status", { status: permissionText })}
                </Typography>
              </Stack>
            </Stack>
          ) : notificationPermission === "default" ? (
            <Stack spacing={1.5}>
              <Typography variant="body2" color="text.secondary">
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
                <Typography variant="body2" color="text.secondary">
                  {t("settings:notifications.status", { status: permissionText })}
                </Typography>
              </Stack>
            </Stack>
          ) : (
            <Stack spacing={1.5}>
              <FormControlLabel
                control={
                  <Switch
                    checked={notificationsEnabled}
                    onChange={handleNotificationsToggle}
                    disabled={pushBusy || pushInitializing}
                    inputProps={{
                      "aria-label": t("settings:notifications.toggles.notifications.aria"),
                    }}
                  />
                }
                label={t("settings:notifications.toggles.notifications.label")}
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={dndEnabled}
                    onChange={handleDndToggle}
                    disabled={dndSaving}
                    inputProps={{ "aria-label": t("settings:notifications.toggles.dnd.aria") }}
                  />
                }
                label={t("settings:notifications.toggles.dnd.label")}
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
            </Stack>
          )}
        </Stack>
      </SectionCard>
    </Stack>
  )

  const accountTab = (
    <Stack spacing={3}>
      <SectionCard>
        <Stack
          component="ul"
          spacing={2.5}
          divider={<Divider />}
          sx={{ listStyle: "none", p: 0, m: 0 }}
        >
          <Stack
            component="li"
            direction={{ xs: "column", sm: "row" }}
            spacing={2}
            alignItems={{ xs: "flex-start", sm: "center" }}
            sx={{ listStyle: "none", width: "100%" }}
          >
            <Avatar
              src={avatarSrc}
              alt={user?.full_name || "avatar"}
              sx={{ width: 56, height: 56 }}
              imgProps={{
                onError: handleAvatarError,
                loading: "lazy",
                decoding: "async",
                referrerPolicy: "no-referrer",
              }}
            />
            <Stack spacing={1} sx={{ width: "100%" }}>
              <Typography variant="subtitle1" fontWeight={600}>
                {t("settings:media.avatar.title")}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t("settings:media.avatar.subtitle")}
              </Typography>
              <Stack direction="row" spacing={1.5} flexWrap="wrap">
                <Button
                  variant="outlined"
                  size="small"
                  onClick={triggerAvatarPick}
                  disabled={avatarBusy}
                >
                  {t("settings:media.avatar.change")}
                </Button>
                {avatarUrl && (
                  <Button
                    variant="text"
                    size="small"
                    color="error"
                    onClick={removeAvatar}
                    disabled={avatarBusy}
                  >
                    {t("settings:media.avatar.delete")}
                  </Button>
                )}
              </Stack>
            </Stack>
          </Stack>

          <Stack
            component="li"
            direction={{ xs: "column", sm: "row" }}
            spacing={2}
            alignItems={{ xs: "flex-start", sm: "center" }}
            sx={{ listStyle: "none", width: "100%" }}
          >
            <Box
              data-testid="settings-cover-preview"
              sx={{
                width: { xs: "100%", sm: 160 },
                maxWidth: 240,
                height: 72,
                borderRadius: 2,
                border: `1px solid ${muiTheme.palette.divider}`,
                backgroundColor: coverSrc ? undefined : muiTheme.palette.action.hover,
                backgroundImage: coverSrc ? `url(${coverSrc})` : undefined,
                backgroundSize: "cover",
                backgroundPosition: "center",
              }}
            />
            <Stack spacing={1} sx={{ width: "100%" }}>
              <Typography variant="subtitle1" fontWeight={600}>
                {t("settings:media.cover.title")}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t("settings:media.cover.recommendation")}
              </Typography>
              <Button
                variant="outlined"
                size="small"
                onClick={triggerCoverPick}
                disabled={coverBusy}
                sx={{ alignSelf: "flex-start" }}
              >
                {t("settings:media.cover.change")}
              </Button>
            </Stack>
          </Stack>

          <Stack
            component="li"
            direction={{ xs: "column", sm: "row" }}
            spacing={1.5}
            alignItems={{ xs: "flex-start", sm: "center" }}
            justifyContent="space-between"
            sx={{ listStyle: "none", width: "100%" }}
          >
            <Stack spacing={0.5} sx={{ flexGrow: 1 }}>
              <Typography variant="subtitle1" fontWeight={600}>
                {t("settings:account.profile.title")}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t("settings:account.profile.subtitle")}
              </Typography>
            </Stack>
            <Button
              variant="outlined"
              size="small"
              onClick={() => navigate({ pathname: "/profile", search: "?edit=1" })}
            >
              {t("common:buttons.edit")}
            </Button>
          </Stack>
        </Stack>
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
      </SectionCard>

      <SectionCard>
        <Stack spacing={2}>
          <Stack spacing={0.75}>
            <Typography variant="h6">{t("settings:sessions.title")}</Typography>
            <Typography variant="body2" color="text.secondary">
              {t("settings:sessions.subtitle")}
            </Typography>
          </Stack>
          {sessionsFetching ? (
            <Stack direction="row" spacing={1} alignItems="center">
              <CircularProgress size={18} />
              <Typography variant="body2" color="text.secondary">
                {t("settings:sessions.loading")}
              </Typography>
            </Stack>
          ) : sessionsErrorMessage ? (
            <Alert severity="error" variant="outlined">
              {sessionsErrorMessage}
            </Alert>
          ) : visibleSessions.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              {t("settings:sessions.empty")}
            </Typography>
          ) : (
            <Stack spacing={1.5} divider={<Divider />}>
              {visibleSessions.map((session) => {
                const isRevoked = Boolean(session.revoked_at)
                const lastRelevantMoment =
                  session.revoked_at ?? session.last_seen_at ?? session.created_at
                const lastSeenText = t("settings:sessions.lastSeen.value", {
                  value: formatSessionTimestamp(lastRelevantMoment),
                })
                const ipLabel = session.ip_address
                  ? t("settings:sessions.ipAddress", { ip: session.ip_address })
                  : t("settings:sessions.ipUnknown")
                const details = `${ipLabel} • ${lastSeenText}`
                const statusLabel = isRevoked
                  ? t("settings:sessions.status.revoked")
                  : session.is_current
                    ? t("settings:sessions.status.current")
                    : t("settings:sessions.status.active")
                const statusColor = isRevoked
                  ? muiTheme.palette.text.disabled
                  : session.is_current
                    ? accentColor
                    : mutedTextColor
                const disableRevoke =
                  session.is_current || isRevoked || revokeSessionMutation.isPending
                return (
                  <Stack key={session.id} spacing={0.75} opacity={isRevoked ? 0.65 : 1}>
                    <Stack direction="row" justifyContent="space-between" alignItems="baseline">
                      <Typography variant="body1" fontWeight={session.is_current ? 600 : 500}>
                        {session.user_agent || t("settings:sessions.unknownDevice")}
                      </Typography>
                      <Typography variant="caption" sx={{ color: statusColor, fontWeight: 600 }}>
                        {statusLabel}
                      </Typography>
                    </Stack>
                    <Typography variant="body2" color="text.secondary">
                      {details}
                    </Typography>
                    {!session.is_current && !isRevoked && (
                      <Button
                        size="small"
                        variant="text"
                        color="error"
                        disabled={disableRevoke}
                        onClick={() => void handleRevokeSession(session.id)}
                        sx={{ alignSelf: { xs: "flex-start", sm: "flex-end" }, px: 0 }}
                      >
                        {t("settings:sessions.revoke")}
                      </Button>
                    )}
                  </Stack>
                )
              })}
            </Stack>
          )}
        </Stack>
      </SectionCard>

      <SectionCard>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={1}
          alignItems={{ xs: "flex-start", sm: "center" }}
          justifyContent="space-between"
        >
          <Stack spacing={0.5} sx={{ maxWidth: { xs: "100%", sm: 360 } }}>
            <Typography variant="subtitle1" fontWeight={600}>
              {t("settings:account.logout.dialogTitle")}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {t("settings:account.logout.dialogDescription")}
            </Typography>
          </Stack>
          <Button
            variant="outlined"
            color="error"
            size="small"
            onClick={() => setConfirmLogout(true)}
          >
            {t("settings:account.logout.button")}
          </Button>
        </Stack>
      </SectionCard>
    </Stack>
  )

  const integrationsTab = (
    <SectionCard>
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
          <Typography variant="h6">{t("settings:integrations.spotify.title")}</Typography>
        </Stack>
        <Stack direction="row" alignItems="center" spacing={1.2} flexWrap="wrap">
          <Chip
            size="small"
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
          <Button variant="contained" onClick={connectSpotify} sx={{ alignSelf: "flex-start" }}>
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
    </SectionCard>
  )

  return (
    <Container component="main" maxWidth="md" sx={{ py: { xs: 3, md: 6 } }}>
      <Stack spacing={3}>
        <Stack direction="row" alignItems="center" spacing={1.5}>
          <SettingsIcon color="primary" />
          <Typography variant="h4" fontWeight={700}>
            {t("settings:page.title")}
          </Typography>
        </Stack>

        <Paper variant="outlined" sx={{ borderRadius: 3, px: { xs: 1, sm: 2 } }}>
          <Tabs
            value={tab}
            onChange={(_, v) => setTab(v)}
            variant="scrollable"
            scrollButtons="auto"
            sx={{ "& .MuiTab-root": { textTransform: "none", fontWeight: 600 } }}
          >
            <Tab label={t("settings:tabs.general")} />
            <Tab label={t("settings:tabs.account")} />
            <Tab label={t("settings:tabs.integrations")} />
          </Tabs>
        </Paper>

        {tab === 0 && generalTab}
        {tab === 1 && accountTab}
        {tab === 2 && integrationsTab}
      </Stack>

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
    </Container>
  )
}
