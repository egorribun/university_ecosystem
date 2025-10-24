import { useEffect, useRef, useState, useCallback, useMemo, ChangeEvent, FocusEvent } from "react"
import { isAxiosError } from "axios"
import { useAuth, currentUserQueryKey, fetchCurrentUser } from "@/contexts/AuthContext"
import { useLanguage, type SupportedLanguage } from "@/contexts/LanguageContext"
import { useNavigate } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { usePushPreferences } from "@/hooks/usePushPreferences"
import { nowPlayingQueryKey } from "@/hooks/useNowPlaying"
import api from "../api/client"
import {
  startTotpEnrollment,
  confirmTotpEnrollment,
  deleteTotpEnrollment,
  startWebAuthnAttestation,
  finishWebAuthnAttestation,
  deleteWebAuthnCredential,
  regenerateRecoveryCodes,
} from "@/api/mfa"
import TotpQrDisplay from "@/components/mfa/TotpQrDisplay"
import OtpEntry from "@/components/mfa/OtpEntry"
import RecoveryCodeList from "@/components/mfa/RecoveryCodeList"
import StepUpDialog from "@/components/mfa/StepUpDialog"
import {
  startRegistration,
  type PublicKeyCredentialCreationOptionsJSON,
  type RegistrationResponseJSON,
} from "@simplewebauthn/browser"
import type { User } from "@/types/User"
import type { ActiveSession } from "@/types/Session"
import type {
  MfaMethod,
  MfaTotpEnrollment,
  MfaWebAuthnCredential,
  TotpEnrollmentStartResponse,
} from "@/types/Mfa"
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
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  CircularProgress,
} from "@mui/material"
import dayjs from "dayjs"
import { useColorScheme, styled, alpha } from "@mui/material/styles"
import type { PaperProps } from "@mui/material/Paper"
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

const isCreationOptions = (
  value: Record<string, unknown> | PublicKeyCredentialCreationOptionsJSON | null | undefined
): value is PublicKeyCredentialCreationOptionsJSON => {
  if (!value || typeof value !== "object") return false
  const candidate = value as {
    challenge?: unknown
    pubKeyCredParams?: unknown
  }
  return typeof candidate.challenge === "string" && Array.isArray(candidate.pubKeyCredParams)
}

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

const SectionCard = styled((props: PaperProps) => <Paper {...props} />)(({ theme }) => ({
  backgroundColor: "var(--card-bg)",
  borderRadius: 20,
  padding: theme.spacing(2.75, 3),
  border: "1px solid var(--glass-border)",
  boxShadow: "none",
  display: "flex",
  flexDirection: "column",
  gap: theme.spacing(1.5),
}))

const SectionTitle = styled(Typography)({
  fontWeight: 600,
  color: "var(--page-text)",
})

const SectionSubtitle = styled(Typography)({
  color: "color-mix(in srgb, var(--page-text) 72%, transparent)",
})

const SessionItem = styled("div")(({ theme }) => ({
  display: "flex",
  alignItems: "stretch",
  justifyContent: "space-between",
  gap: theme.spacing(1.5),
  padding: theme.spacing(1.5),
  borderRadius: 18,
  border: "1px solid var(--glass-border)",
  backgroundColor: theme.palette.mode === "dark" ? alpha("#fff", 0.04) : alpha("#000", 0.03),
  transition: "border-color .2s ease, box-shadow .2s ease, background-color .2s ease",
  [theme.breakpoints.down("sm")]: {
    flexDirection: "column",
    alignItems: "flex-start",
  },
  "&:hover": {
    borderColor: alpha(theme.palette.primary.main, 0.35),
    boxShadow:
      theme.palette.mode === "dark"
        ? "0 12px 28px rgba(0,0,0,.35)"
        : "0 12px 24px rgba(15,23,42,.12)",
    backgroundColor:
      theme.palette.mode === "dark"
        ? alpha(theme.palette.primary.main, 0.18)
        : alpha(theme.palette.primary.main, 0.08),
  },
  '&[data-revoked="true"]': {
    opacity: 0.72,
    borderStyle: "dashed",
    borderColor: alpha(theme.palette.text.primary, 0.18),
    backgroundColor:
      theme.palette.mode === "dark"
        ? alpha(theme.palette.text.primary, 0.06)
        : alpha(theme.palette.text.primary, 0.04),
  },
  '&[data-revoked="true"]:hover': {
    boxShadow: "none",
    borderColor: alpha(theme.palette.text.primary, 0.18),
    backgroundColor:
      theme.palette.mode === "dark"
        ? alpha(theme.palette.text.primary, 0.06)
        : alpha(theme.palette.text.primary, 0.04),
  },
}))

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
    data: sessionsData,
    isFetching: sessionsFetching,
    isError: sessionsIsError,
    error: sessionsError,
  } = useQuery<ActiveSession[], unknown>({
    queryKey: sessionsKey,
    queryFn: fetchSessions,
    enabled: tab === 1 && Boolean(user),
    staleTime: 30_000,
  })

  const sessions = Array.isArray(sessionsData) ? sessionsData : []

  const sortedSessions = useMemo(() => {
    const weight = (session: ActiveSession) => {
      if (session.is_current) return 0
      if (session.revoked_at) return 2
      return 1
    }

    const timeValue = (session: ActiveSession) => {
      const source = session.last_seen_at ?? session.created_at ?? null
      if (!source) return 0
      const parsed = dayjs(source)
      return parsed.isValid() ? parsed.valueOf() : 0
    }

    if (!Array.isArray(sessions)) return []

    return [...sessions].sort((a, b) => {
      const weightDiff = weight(a) - weight(b)
      if (weightDiff !== 0) return weightDiff
      return timeValue(b) - timeValue(a)
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

  const [totpDraft, setTotpDraft] = useState<TotpEnrollmentStartResponse | null>(null)
  const [totpBusy, setTotpBusy] = useState(false)
  const [totpError, setTotpError] = useState<string | null>(null)
  const [webAuthnBusy, setWebAuthnBusy] = useState(false)
  const [webAuthnName, setWebAuthnName] = useState("")
  const [generatedRecoveryCodes, setGeneratedRecoveryCodes] = useState<string[]>([])
  const [recoveryBusy, setRecoveryBusy] = useState(false)
  const [stepUpOpen, setStepUpOpen] = useState(false)
  const stepUpActionRef = useRef<(() => Promise<void>) | null>(null)

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

  const methodLabels = useMemo<Record<MfaMethod, string>>(
    () => ({
      totp: t("settings:security.method.totp"),
      webauthn: t("settings:security.method.webauthn"),
      recovery: t("settings:security.method.recovery"),
    }),
    [t]
  )

  const formatDateTime = useCallback((value: string | null) => {
    if (!value) return null
    const parsed = dayjs(value)
    if (!parsed.isValid()) return null
    return parsed.format("DD MMM YYYY HH:mm")
  }, [])

  const activeTotp = useMemo(
    () => (user?.totp_enrollments ?? []).filter((entry) => entry.is_active),
    [user?.totp_enrollments]
  )

  const activeWebAuthn = useMemo(
    () => (user?.webauthn_credentials ?? []).filter((entry) => entry.is_active),
    [user?.webauthn_credentials]
  )

  const defaultMethodText = useMemo(() => {
    const key = user?.mfa_default_method
    if (!key) return t("settings:security.status.noDefault")
    return t("settings:security.status.defaultMethod", { method: methodLabels[key] })
  }, [methodLabels, t, user?.mfa_default_method])

  const lastVerifiedText = useMemo(() => {
    if (!user?.mfa_last_verified_at) {
      return t("settings:security.status.notVerified")
    }
    const formatted = formatDateTime(user.mfa_last_verified_at)
    return formatted
      ? t("settings:security.status.lastVerified", { value: formatted })
      : t("settings:security.status.notVerified")
  }, [formatDateTime, t, user?.mfa_last_verified_at])

  const recoveryStatusText = useMemo(() => {
    const generatedAt = user?.mfa_recovery_codes_generated_at
    if (!generatedAt) {
      return t("settings:security.recovery.neverGenerated")
    }
    const formatted = formatDateTime(generatedAt)
    return formatted
      ? t("settings:security.recovery.generatedAt", { value: formatted })
      : t("settings:security.recovery.neverGenerated")
  }, [formatDateTime, t, user?.mfa_recovery_codes_generated_at])

  const openStepUpFor = useCallback((action: () => Promise<void>) => {
    stepUpActionRef.current = action
    setStepUpOpen(true)
  }, [])

  const handleStepUpClose = useCallback(() => {
    setStepUpOpen(false)
    stepUpActionRef.current = null
  }, [])

  const handleStepUpCompleted = useCallback(async () => {
    const action = stepUpActionRef.current
    stepUpActionRef.current = null
    setStepUpOpen(false)
    if (action) {
      await action()
    }
  }, [])

  const handleRevokeSession = useCallback(
    async (sessionId: number) => {
      try {
        const result = await revokeSessionMutation.mutateAsync(sessionId)
        setSnack({ text: t("settings:sessions.snackbar.revoked"), sev: "success" })
        queryClient.setQueryData<ActiveSession[] | undefined>(sessionsKey, (prev) => {
          if (!Array.isArray(prev)) return [result]
          return prev.map((session) => (session.id === result.id ? result : session))
        })
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
    [logout, queryClient, resolveDetailMessage, revokeSessionMutation, sessionsKey, t]
  )

  const handleStartTotp = useCallback(async () => {
    if (totpBusy) return
    setTotpBusy(true)
    setTotpError(null)
    try {
      const { data } = await startTotpEnrollment()
      setTotpDraft(data)
    } catch (error) {
      setSnack({
        text: resolveDetailMessage(error, t("settings:security.snackbar.totpStartFailed")),
        sev: "error",
      })
    } finally {
      setTotpBusy(false)
    }
  }, [resolveDetailMessage, setSnack, t, totpBusy])

  const handleConfirmTotp = useCallback(
    async (_method: Extract<MfaMethod, "totp" | "recovery">, code: string) => {
      if (!totpDraft) return
      setTotpBusy(true)
      setTotpError(null)
      try {
        await confirmTotpEnrollment({ enrollment_id: totpDraft.enrollment.id, code })
        setTotpDraft(null)
        setGeneratedRecoveryCodes([])
        await refreshMe()
        setSnack({ text: t("settings:security.snackbar.totpEnabled"), sev: "success" })
      } catch (error) {
        setTotpError(resolveDetailMessage(error, t("settings:security.snackbar.totpConfirmFailed")))
      } finally {
        setTotpBusy(false)
      }
    },
    [refreshMe, resolveDetailMessage, t, totpDraft, setSnack]
  )

  const handleCancelTotp = useCallback(() => {
    setTotpDraft(null)
    setTotpError(null)
  }, [])

  const handleDisableTotp = useCallback(
    (enrollmentId: number) => {
      const action = async () => {
        try {
          await deleteTotpEnrollment(enrollmentId)
          await refreshMe()
          setSnack({ text: t("settings:security.snackbar.totpDisabled"), sev: "success" })
        } catch (error) {
          setSnack({
            text: resolveDetailMessage(error, t("settings:security.snackbar.totpDisableFailed")),
            sev: "error",
          })
        }
      }
      openStepUpFor(action)
    },
    [openStepUpFor, refreshMe, resolveDetailMessage, setSnack, t]
  )

  const handleRegisterWebAuthn = useCallback(async () => {
    if (webAuthnBusy) return
    setWebAuthnBusy(true)
    try {
      const { data } = await startWebAuthnAttestation()
      const rawOptions = data.options ?? null
      if (!isCreationOptions(rawOptions)) {
        throw new Error("Invalid WebAuthn attestation options")
      }
      const credential: RegistrationResponseJSON = await startRegistration({
        optionsJSON: rawOptions,
      })
      await finishWebAuthnAttestation({
        challenge_token: data.challenge_token,
        credential: credential as unknown as Record<string, unknown>,
        device_name: webAuthnName.trim() || undefined,
      })
      setWebAuthnName("")
      await refreshMe()
      setSnack({ text: t("settings:security.snackbar.webauthnAdded"), sev: "success" })
    } catch (error) {
      if (error instanceof DOMException && error.name === "NotAllowedError") {
        setSnack({ text: t("settings:security.snackbar.webauthnCancelled"), sev: "info" })
      } else {
        setSnack({
          text: resolveDetailMessage(error, t("settings:security.snackbar.webauthnAddFailed")),
          sev: "error",
        })
      }
    } finally {
      setWebAuthnBusy(false)
    }
  }, [refreshMe, resolveDetailMessage, setSnack, t, webAuthnBusy, webAuthnName])

  const handleRemoveWebAuthn = useCallback(
    (credentialId: string) => {
      const action = async () => {
        try {
          await deleteWebAuthnCredential(credentialId)
          await refreshMe()
          setSnack({ text: t("settings:security.snackbar.webauthnRemoved"), sev: "success" })
        } catch (error) {
          setSnack({
            text: resolveDetailMessage(error, t("settings:security.snackbar.webauthnRemoveFailed")),
            sev: "error",
          })
        }
      }
      openStepUpFor(action)
    },
    [openStepUpFor, refreshMe, resolveDetailMessage, setSnack, t]
  )

  const handleGenerateRecoveryCodes = useCallback(() => {
    const action = async () => {
      setRecoveryBusy(true)
      try {
        const { data } = await regenerateRecoveryCodes()
        const codes = Array.isArray(data?.codes) ? data.codes.map((code) => String(code)) : []
        setGeneratedRecoveryCodes(codes)
        await refreshMe()
        setSnack({ text: t("settings:security.snackbar.recoveryGenerated"), sev: "success" })
      } catch (error) {
        setSnack({
          text: resolveDetailMessage(error, t("settings:security.snackbar.recoveryFailed")),
          sev: "error",
        })
      } finally {
        setRecoveryBusy(false)
      }
    }
    openStepUpFor(action)
  }, [openStepUpFor, refreshMe, resolveDetailMessage, setSnack, t])

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

  const removeCover = async () => {
    try {
      setCoverBusy(true)
      await api.delete("/users/me/cover")
      await refreshMe()
      setCoverVersion(Date.now())
      setSnack({ text: t("settings:media.cover.deleted"), sev: "success" })
    } catch (error) {
      setSnack({
        text: resolveDetailMessage(error, t("settings:media.cover.deleteFailed")),
        sev: "error",
      })
    } finally {
      setCoverBusy(false)
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
          <Stack
            spacing={2.5}
            sx={{ width: "100%", maxWidth: { xs: "100%", sm: 640, md: 760, lg: 880 } }}
          >
            <SectionCard component="section">
              <Stack
                component="ul"
                spacing={2.5}
                sx={{ width: "100%", listStyle: "none", p: 0, m: 0 }}
              >
                <Stack
                  component="li"
                  direction={{ xs: "column", sm: "row" }}
                  spacing={{ xs: 1.5, sm: 2.5 }}
                  alignItems={{ xs: "flex-start", sm: "center" }}
                  justifyContent="space-between"
                  sx={{ listStyle: "none" }}
                >
                  <Stack
                    direction="row"
                    spacing={{ xs: 1.5, sm: 2.5 }}
                    alignItems="center"
                    sx={{ minWidth: 0, flex: 1 }}
                  >
                    <Avatar
                      src={avatarSrc}
                      alt={user?.full_name || "avatar"}
                      sx={{ width: 72, height: 72 }}
                      imgProps={{
                        onError: handleAvatarError,
                        loading: "lazy",
                        decoding: "async",
                        referrerPolicy: "no-referrer",
                      }}
                    />
                    <Stack spacing={0.5} sx={{ minWidth: 0 }}>
                      <SectionTitle variant="subtitle1">
                        {t("settings:media.avatar.title")}
                      </SectionTitle>
                    </Stack>
                  </Stack>
                  <Stack
                    direction={{ xs: "column", sm: "row" }}
                    spacing={1}
                    alignItems={{ sm: "center" }}
                    justifyContent={{ xs: "flex-start", sm: "flex-end" }}
                    flexWrap="wrap"
                    sx={{ width: { xs: "100%", sm: "auto" } }}
                  >
                    <Button
                      size="small"
                      variant="contained"
                      onClick={triggerAvatarPick}
                      disabled={avatarBusy}
                      sx={{
                        minWidth: { sm: 140 },
                        width: { xs: "100%", sm: "auto" },
                      }}
                    >
                      {t("settings:media.avatar.change")}
                    </Button>
                    <Button
                      size="small"
                      variant="outlined"
                      color="error"
                      onClick={removeAvatar}
                      disabled={avatarBusy}
                      sx={{
                        minWidth: { sm: 140 },
                        width: { xs: "100%", sm: "auto" },
                      }}
                    >
                      {t("settings:media.avatar.delete")}
                    </Button>
                  </Stack>
                </Stack>

                <Divider
                  component="li"
                  flexItem
                  sx={{ borderColor: "var(--glass-border)", listStyle: "none" }}
                />

                <Stack
                  component="li"
                  direction={{ xs: "column", sm: "row" }}
                  spacing={{ xs: 1.5, sm: 2.5 }}
                  alignItems={{ xs: "flex-start", sm: "center" }}
                  justifyContent="space-between"
                  sx={{ listStyle: "none" }}
                >
                  <Stack
                    direction="row"
                    spacing={{ xs: 1.5, sm: 2.5 }}
                    alignItems="center"
                    sx={{ minWidth: 0, flex: 1 }}
                  >
                    <Box
                      data-testid="settings-cover-preview"
                      sx={{
                        width: 160,
                        height: 72,
                        borderRadius: 1.5,
                        border: "1px solid var(--glass-border)",
                        background: coverSrc
                          ? `url(${coverSrc}) center/cover no-repeat`
                          : "color-mix(in srgb, var(--page-text) 6%, transparent)",
                      }}
                    />
                    <SectionTitle variant="subtitle1">
                      {t("settings:media.cover.title")}
                    </SectionTitle>
                  </Stack>
                  <Stack
                    direction={{ xs: "column", sm: "row" }}
                    spacing={1}
                    alignItems={{ sm: "center" }}
                    justifyContent={{ xs: "flex-start", sm: "flex-end" }}
                    flexWrap="wrap"
                    sx={{ width: { xs: "100%", sm: "auto" } }}
                  >
                    <Button
                      size="small"
                      variant="contained"
                      onClick={triggerCoverPick}
                      disabled={coverBusy}
                      sx={{
                        minWidth: { sm: 140 },
                        width: { xs: "100%", sm: "auto" },
                      }}
                    >
                      {t("settings:media.cover.change")}
                    </Button>
                    {coverUrl && (
                      <Button
                        size="small"
                        variant="outlined"
                        color="error"
                        onClick={removeCover}
                        disabled={coverBusy}
                        sx={{
                          minWidth: { sm: 140 },
                          width: { xs: "100%", sm: "auto" },
                        }}
                      >
                        {t("settings:media.cover.remove")}
                      </Button>
                    )}
                  </Stack>
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

            <SectionCard component="section">
              <Stack
                direction={{ xs: "column", sm: "row" }}
                spacing={1.5}
                alignItems={{ sm: "center" }}
                justifyContent="space-between"
              >
                <SectionTitle variant="subtitle1" sx={{ minWidth: 0 }}>
                  {t("settings:account.profile.title")}
                </SectionTitle>
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => navigate({ pathname: "/profile", search: "?edit=1" })}
                >
                  {t("common:buttons.edit")}
                </Button>
              </Stack>
            </SectionCard>

            <SectionCard component="section">
              <Stack spacing={1}>
                <SectionTitle variant="subtitle1">{t("settings:sessions.title")}</SectionTitle>
                <SectionSubtitle variant="body2">{t("settings:sessions.subtitle")}</SectionSubtitle>
              </Stack>

              {sessionsFetching ? (
                <Stack direction="row" spacing={1.25} alignItems="center" sx={{ mt: 1.5 }}>
                  <CircularProgress size={18} />
                  <Typography variant="body2" sx={{ color: "var(--page-text)" }}>
                    {t("settings:sessions.loading")}
                  </Typography>
                </Stack>
              ) : sessionsErrorMessage ? (
                <Alert severity="error" variant="outlined" sx={{ mt: 1.5 }}>
                  {sessionsErrorMessage}
                </Alert>
              ) : sessions.length === 0 ? (
                <Typography variant="body2" sx={{ mt: 1.5, color: "var(--page-text)" }}>
                  {t("settings:sessions.empty")}
                </Typography>
              ) : (
                <Stack spacing={1.5} sx={{ mt: 1.5 }}>
                  {sortedSessions.map((session) => {
                    const isRevoked = Boolean(session.revoked_at)
                    const lastSeen = session.last_seen_at ?? session.created_at
                    const timelineSource = session.revoked_at ?? lastSeen
                    const timeline = t("settings:sessions.lastSeen.value", {
                      value: formatSessionTimestamp(timelineSource),
                    })
                    const ipLabel = session.ip_address
                      ? t("settings:sessions.ipAddress", { ip: session.ip_address })
                      : t("settings:sessions.ipUnknown")
                    const meta = [ipLabel, timeline]
                    if (isRevoked) meta.push(t("settings:sessions.status.revoked"))
                    const details = meta.join(" • ")
                    const statusLabel = session.is_current
                      ? t("settings:sessions.status.current")
                      : isRevoked
                        ? t("settings:sessions.status.revoked")
                        : t("settings:sessions.status.active")
                    const disableRevoke =
                      session.is_current || isRevoked || revokeSessionMutation.isPending

                    return (
                      <SessionItem key={session.id} data-revoked={isRevoked ? "true" : undefined}>
                        <Box sx={{ minWidth: 0 }}>
                          <Typography
                            variant="body2"
                            sx={{
                              color: isRevoked
                                ? "color-mix(in srgb, var(--page-text) 65%, transparent)"
                                : "var(--page-text)",
                              fontWeight: session.is_current ? 600 : 500,
                              wordBreak: "break-word",
                            }}
                          >
                            {session.user_agent || t("settings:sessions.unknownDevice")}
                          </Typography>
                          <Typography
                            variant="caption"
                            sx={{
                              color: isRevoked
                                ? "color-mix(in srgb, var(--page-text) 58%, transparent)"
                                : "color-mix(in srgb, var(--page-text) 68%, transparent)",
                              fontStyle: isRevoked ? "italic" : "normal",
                            }}
                          >
                            {details}
                          </Typography>
                        </Box>
                        <Stack
                          direction="row"
                          spacing={1}
                          alignItems="center"
                          justifyContent={{ xs: "flex-start", sm: "flex-end" }}
                          sx={{ flexWrap: "wrap", rowGap: 0.75, flexShrink: 0 }}
                        >
                          <Chip
                            size="small"
                            label={statusLabel}
                            sx={(theme) => ({
                              borderRadius: 999,
                              fontWeight: 600,
                              color: session.is_current
                                ? "var(--link-color)"
                                : isRevoked
                                  ? "color-mix(in srgb, var(--page-text) 60%, transparent)"
                                  : "color-mix(in srgb, var(--page-text) 72%, transparent)",
                              backgroundColor: session.is_current
                                ? alpha(theme.palette.primary.main, 0.12)
                                : isRevoked
                                  ? "transparent"
                                  : alpha(theme.palette.text.primary, 0.06),
                              border: "1px solid",
                              borderColor: session.is_current
                                ? alpha(theme.palette.primary.main, 0.32)
                                : isRevoked
                                  ? alpha(theme.palette.text.primary, 0.16)
                                  : alpha(theme.palette.text.primary, 0.12),
                            })}
                            variant="outlined"
                          />
                          {!session.is_current && !isRevoked && (
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
                      </SessionItem>
                    )
                  })}
                </Stack>
              )}
            </SectionCard>

            <SectionCard component="section">
              <Stack spacing={1} sx={{ mb: 1.5 }}>
                <SectionTitle variant="subtitle1">{t("settings:security.title")}</SectionTitle>
                <SectionSubtitle variant="body2">{t("settings:security.subtitle")}</SectionSubtitle>
              </Stack>

              <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ mb: 2 }}>
                <Chip size="small" label={defaultMethodText} sx={{ fontWeight: 600 }} />
                <Chip size="small" label={lastVerifiedText} sx={{ fontWeight: 600 }} />
              </Stack>

              <Stack spacing={2.5} sx={{ mt: 1.5 }}>
                <Stack spacing={1}>
                  <SectionTitle variant="subtitle2">
                    {t("settings:security.method.totp")}
                  </SectionTitle>
                  <SectionSubtitle variant="body2">
                    {t("settings:security.totp.description")}
                  </SectionSubtitle>
                </Stack>

                {totpDraft ? (
                  <Stack spacing={2}>
                    <Typography variant="subtitle2" fontWeight={600}>
                      {t("settings:security.totp.pendingTitle")}
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{ color: "color-mix(in srgb, var(--page-text) 70%, transparent)" }}
                    >
                      {t("settings:security.totp.pendingDescription")}
                    </Typography>
                    <TotpQrDisplay
                      otpauthUrl={totpDraft.otpauth_url}
                      secret={totpDraft.secret}
                      label={totpDraft.enrollment.label}
                    />
                    <OtpEntry
                      availableMethods={["totp"]}
                      loading={totpBusy}
                      error={totpError}
                      onSubmit={handleConfirmTotp}
                    />
                    <Button
                      variant="text"
                      color="inherit"
                      disabled={totpBusy}
                      onClick={handleCancelTotp}
                    >
                      {t("settings:security.totp.cancel")}
                    </Button>
                  </Stack>
                ) : (
                  <Stack spacing={1.5}>
                    {activeTotp.length ? (
                      <Stack spacing={1.25}>
                        {activeTotp.map((enrollment: MfaTotpEnrollment, index: number) => (
                          <Stack
                            key={enrollment.id}
                            direction={{ xs: "column", sm: "row" }}
                            spacing={1.25}
                            alignItems={{ sm: "center" }}
                            justifyContent="space-between"
                            sx={{
                              border: "1px solid var(--glass-border)",
                              borderRadius: 2,
                              padding: 1.5,
                            }}
                          >
                            <Stack spacing={0.5} sx={{ minWidth: 0 }}>
                              <Typography fontWeight={600} sx={{ color: "var(--page-text)" }}>
                                {enrollment.label ||
                                  t("settings:security.totp.unnamed", { index: index + 1 })}
                              </Typography>
                              <Typography
                                variant="body2"
                                sx={{
                                  color: "color-mix(in srgb, var(--page-text) 70%, transparent)",
                                }}
                              >
                                {t("settings:security.totp.added", {
                                  value: formatDateTime(enrollment.created_at) ?? "—",
                                })}
                              </Typography>
                            </Stack>
                            <Button
                              variant="outlined"
                              color="error"
                              size="small"
                              onClick={() => handleDisableTotp(enrollment.id)}
                            >
                              {t("settings:security.totp.remove")}
                            </Button>
                          </Stack>
                        ))}
                      </Stack>
                    ) : (
                      <Typography
                        variant="body2"
                        sx={{ color: "color-mix(in srgb, var(--page-text) 70%, transparent)" }}
                      >
                        {t("settings:security.totp.empty")}
                      </Typography>
                    )}
                    <Button
                      variant="contained"
                      onClick={() => void handleStartTotp()}
                      disabled={totpBusy}
                    >
                      {t("settings:security.totp.add")}
                    </Button>
                  </Stack>
                )}

                <Divider sx={{ my: 1 }} />

                <Stack spacing={1}>
                  <SectionTitle variant="subtitle2">
                    {t("settings:security.method.webauthn")}
                  </SectionTitle>
                  <SectionSubtitle variant="body2">
                    {t("settings:security.webauthn.description")}
                  </SectionSubtitle>
                </Stack>

                <Stack
                  direction={{ xs: "column", sm: "row" }}
                  spacing={1.5}
                  alignItems={{ sm: "center" }}
                  sx={{ maxWidth: 420 }}
                >
                  <TextField
                    fullWidth
                    size="small"
                    label={t("settings:security.webauthn.nameLabel")}
                    placeholder={t("settings:security.webauthn.namePlaceholder")}
                    value={webAuthnName}
                    onChange={(event) => setWebAuthnName(event.target.value)}
                  />
                  <Button
                    variant="contained"
                    onClick={() => void handleRegisterWebAuthn()}
                    disabled={webAuthnBusy}
                  >
                    {webAuthnBusy
                      ? t("settings:security.webauthn.registering")
                      : t("settings:security.webauthn.cta")}
                  </Button>
                </Stack>

                {activeWebAuthn.length ? (
                  <Stack spacing={1.25}>
                    {activeWebAuthn.map((credential: MfaWebAuthnCredential, index: number) => {
                      const added = formatDateTime(credential.created_at)
                      const lastUsed = formatDateTime(credential.last_used_at)
                      return (
                        <Stack
                          key={credential.credential_id}
                          direction={{ xs: "column", sm: "row" }}
                          spacing={1.25}
                          alignItems={{ sm: "center" }}
                          justifyContent="space-between"
                          sx={{
                            border: "1px solid var(--glass-border)",
                            borderRadius: 2,
                            padding: 1.5,
                          }}
                        >
                          <Stack spacing={0.5} sx={{ minWidth: 0 }}>
                            <Typography fontWeight={600} sx={{ color: "var(--page-text)" }}>
                              {credential.device_name ||
                                t("settings:security.webauthn.unnamed", { index: index + 1 })}
                            </Typography>
                            <Typography
                              variant="body2"
                              sx={{
                                color: "color-mix(in srgb, var(--page-text) 70%, transparent)",
                              }}
                            >
                              {added
                                ? t("settings:security.webauthn.added", { value: added })
                                : null}
                            </Typography>
                            {lastUsed ? (
                              <Typography
                                variant="body2"
                                sx={{
                                  color: "color-mix(in srgb, var(--page-text) 60%, transparent)",
                                }}
                              >
                                {t("settings:security.webauthn.lastUsed", { value: lastUsed })}
                              </Typography>
                            ) : null}
                          </Stack>
                          <Button
                            variant="outlined"
                            color="error"
                            size="small"
                            onClick={() => handleRemoveWebAuthn(credential.credential_id)}
                          >
                            {t("settings:security.webauthn.remove")}
                          </Button>
                        </Stack>
                      )
                    })}
                  </Stack>
                ) : (
                  <Typography
                    variant="body2"
                    sx={{ color: "color-mix(in srgb, var(--page-text) 70%, transparent)" }}
                  >
                    {t("settings:security.webauthn.empty")}
                  </Typography>
                )}

                <Divider sx={{ my: 1 }} />

                <Stack spacing={1}>
                  <SectionTitle variant="subtitle2">
                    {t("settings:security.method.recovery")}
                  </SectionTitle>
                  <SectionSubtitle variant="body2">
                    {t("settings:security.recovery.description")}
                  </SectionSubtitle>
                </Stack>

                <Stack
                  direction={{ xs: "column", sm: "row" }}
                  spacing={1.5}
                  alignItems={{ sm: "center" }}
                >
                  <Button
                    variant="outlined"
                    onClick={handleGenerateRecoveryCodes}
                    disabled={recoveryBusy}
                  >
                    {recoveryBusy
                      ? t("settings:security.recovery.generating")
                      : t("settings:security.recovery.generate")}
                  </Button>
                  <Typography
                    variant="body2"
                    sx={{ color: "color-mix(in srgb, var(--page-text) 70%, transparent)" }}
                  >
                    {recoveryStatusText}
                  </Typography>
                </Stack>

                {generatedRecoveryCodes.length ? (
                  <RecoveryCodeList
                    codes={generatedRecoveryCodes.map((code) => ({ code }))}
                    allowCopy
                  />
                ) : null}
              </Stack>
            </SectionCard>

            <SectionCard component="section">
              <Stack spacing={1}>
                <SectionTitle variant="subtitle1">
                  {t("settings:account.logout.title")}
                </SectionTitle>
                <SectionSubtitle variant="body2">
                  {t("settings:account.logout.subtitle")}
                </SectionSubtitle>
              </Stack>
              <Button
                size="small"
                variant="outlined"
                color="error"
                onClick={() => setConfirmLogout(true)}
                sx={{ alignSelf: { xs: "flex-start", sm: "flex-end" } }}
              >
                {t("settings:account.logout.button")}
              </Button>
            </SectionCard>
          </Stack>
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

      <StepUpDialog
        open={stepUpOpen}
        onClose={handleStepUpClose}
        onCompleted={handleStepUpCompleted}
        description={t("settings:security.stepUp.description")}
      />

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
