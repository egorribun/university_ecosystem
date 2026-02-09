import React, {
  useState,
  useCallback,
  useMemo,
  useRef,
  useEffect,
  type CSSProperties,
  type ChangeEvent,
  type FocusEvent,
} from "react"
import { useNavigate } from "react-router-dom"
import { useQueryClient, useQuery, useMutation } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import dayjs from "dayjs"
import { isAxiosError } from "axios"

import {
  Settings as SettingsIcon,
  Bell,
  Lock,
  User as UserIcon,
  Globe,
  Palette,
  Monitor,
  Sun,
  Moon,
  Shield,
  Smartphone,
  CreditCard,
  LogOut,
  ChevronRight,
  Fingerprint,
  RefreshCcw,
  Trash2,
  AlertTriangle,
  Mail,
  MoreVertical,
  Key,
  Smartphone as DeviceIcon,
} from "lucide-react"

import { startRegistration, browserSupportsWebAuthn } from "@simplewebauthn/browser"

import api from "../api/client"
import { useAuth } from "../contexts/AuthContext"
import { useLanguage } from "../contexts/LanguageContext"
import { useTheme } from "../contexts/ThemeContext"
import { usePushPreferences } from "../hooks/usePushPreferences"
import { useNowPlaying, nowPlayingQueryKey } from "../hooks/useNowPlaying"
import { currentUserQueryKey, fetchCurrentUser } from "../hooks/auth/useProfileSync"
import { type SupportedLanguage } from "../i18n/metadata"

import Layout from "../components/Layout"
import PageFadeIn from "../components/PageFadeIn"

import {
  Button,
  TextField,
  SwitchControl,
  RadioGroup,
  Radio,
  FormControlLabel,
  Avatar,
  Chip,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Snackbar,
  CircularProgress,
  Tabs,
  Tab,
  SectionCard,
  SectionTitle,
  SectionSubtitle,
  AccordionSection,
  Divider,
  SessionItem,
  securityStatusChipClassName,
  type ThemeMode,
} from "../components/settings"

import { TotpQrDisplay } from "../components/mfa/TotpQrDisplay"
import { OtpEntry } from "../components/mfa/OtpEntry"
import { StepUpDialog } from "../components/mfa/StepUpDialog"

import {
  startTotpEnrollment,
  confirmTotpEnrollment,
  deleteTotpEnrollment,
  deletePendingTotpEnrollment,
  startWebAuthnRegistration,
  confirmWebAuthnRegistration,
  listWebAuthnCredentials,
  deleteWebAuthnCredential,
} from "../api/mfa"

import type {
  MfaTotpEnrollment,
  TotpEnrollmentStartResponse,
  TotpEnrollmentStartPayload,
} from "../types/Mfa"
import type { User } from "../types/User"
import type { ActiveSession } from "../types/Session"

import { cn } from "../utils/cn"
import { resolveMediaUrl, addVersionParam } from "../utils/media"
import { sanitizeSpotifyAuthorizeUrl } from "../utils/spotify"

const DEFAULT_AVATAR = "https://www.gravatar.com/avatar/00000000000000000000000000000000?d=mp&f=y"
const AVATAR_PLACEHOLDER_URL = DEFAULT_AVATAR

const SpotifyLogo = ({ className }: { className?: string }) => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" className={className}>
    <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.508 17.302c-.216.354-.675.464-1.03.248-2.863-1.748-6.463-2.144-10.707-1.177-.404.092-.814-.16-.906-.565-.092-.404.16-.814.565-.906 4.646-1.063 8.625-.613 11.83 1.342.354.215.465.674.248 1.058zm1.467-3.258c-.272.443-.847.584-1.29.312-3.277-2.015-8.272-2.597-12.146-1.422-.497.151-1.025-.13-1.176-.627-.151-.497.13-1.025.627-1.176 4.43-1.344 9.932-.693 13.673 1.606.443.272.584.847.312 1.307zm.126-3.395C15.222 8.243 8.818 8.03 5.072 9.168c-.596.18-1.23-.153-1.41-.749-.18-.596.153-1.23.749-1.41 4.29-1.302 11.37-1.055 15.86 1.61.536.318.713 1.008.395 1.543-.318.536-1.008.713-1.543.395z" />
  </svg>
)

const fadeDelayStyle = (value: string): CSSProperties =>
  ({ "--fade-delay": value }) as CSSProperties

const resolveDetailMessage = (error: unknown, fallback: string): string => {
  if (isAxiosError(error) && error.response?.data?.detail) {
    return String(error.response.data.detail)
  }
  return error instanceof Error ? error.message : fallback
}

const isCreationOptions = (value: unknown): value is PublicKeyCredentialCreationOptionsJSON => {
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

// Types duplicated or extended locally as needed
interface PublicKeyCredentialCreationOptionsJSON {
  challenge: string
  pubKeyCredParams: { type: "public-key"; alg: number }[]
  rp: { id: string; name: string }
  user: { id: string; name: string; displayName: string }
  timeout: number
  attestation: AttestationConveyancePreference
  excludeCredentials: { id: string; type: "public-key" }[]
  authenticatorSelection?: AuthenticatorSelectionCriteria
  extensions?: AuthenticationExtensionsClientInputs
}

// Tailwind CSS components

export default function Settings() {
  const navigate = useNavigate()
  const { user, setUser, logout } = useAuth()
  const queryClient = useQueryClient()
  const [tab, setTab] = useState(0)
  const [snackbar, setSnackbar] = useState<{
    text: string
    severity?: "success" | "info" | "warning" | "error"
  } | null>(null)
  const { language, setLanguage, available: availableLanguages } = useLanguage()
  const { t } = useTranslation(["settings", "common", "notifications", "profile"])

  // Theme management using custom useTheme hook
  const { theme, setTheme, resolvedTheme: resolvedColorScheme } = useTheme()

  const setMode = useCallback(
    (value: ThemeMode) => {
      setTheme(value)
    },
    [setTheme]
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
  } = usePushPreferences({ onNotify: setSnackbar })

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
    mutationFn: async (sessionId: string) => {
      console.log(`[settings] mutationFn: deleting session ${sessionId}`)
      const { data } = await api.delete<ActiveSession>(`/auth/sessions/${sessionId}`)
      console.log(`[settings] mutationFn: session ${sessionId} deleted, returning data`, data)
      return data
    },
  })

  const revokeAllSessionsMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<{ revoked: number }>("/auth/sessions/revoke-others")
      return data
    },
  })

  const syncDndFromUser = useCallback((value: User | null) => {
    const enabled = Boolean(value?.dnd_enabled)
    const start = toInputTime(value?.dnd_start)
    const end = toInputTime(value?.dnd_end)
    setDndEnabled((prev) => (prev === enabled ? prev : enabled))
    setDndStart((prev) => {
      const next = start || (enabled ? DEFAULT_DND_START : "")
      return prev === next ? prev : next
    })
    setDndEnd((prev) => {
      const next = end || (enabled ? DEFAULT_DND_END : "")
      return prev === next ? prev : next
    })
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
        setSnackbar({ text: t("settings:dnd.validation.missingRange"), severity: "warning" })
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
        setSnackbar({ text: message, severity: "success" })
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
        setSnackbar({ text: message, severity: "error" })
        syncDndFromUser(user)
      } finally {
        setDndSaving(false)
      }
    },
    [dndSaving, setUser, setSnackbar, syncDndFromUser, t, user]
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
        setSnackbar({
          text: t("settings:integrations.spotify.snackbar.connected"),
          severity: "success",
        })
      if (s === "error")
        setSnackbar({
          text: t("settings:integrations.spotify.snackbar.connectFailed"),
          severity: "error",
        })
      sp.delete("spotify")
      const next = window.location.pathname + (sp.toString() ? "?" + sp : "")
      window.history.replaceState({}, "", next)
    }
  }, [setSnackbar, t])

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
      setSnackbar({
        text: t("settings:integrations.spotify.snackbar.openFailed"),
        severity: "error",
      })
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
      setSnackbar({
        text: t("settings:integrations.spotify.snackbar.disconnected"),
        severity: "success",
      })
    } catch {
      setSnackbar({
        text: t("settings:integrations.spotify.snackbar.disconnectFailed"),
        severity: "error",
      })
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
  const [pendingEmail, setPendingEmail] = useState<string | null>(user?.pending_email ?? null)
  const [emailValue, setEmailValue] = useState(user?.email ?? "")
  const [emailPassword, setEmailPassword] = useState("")
  const [emailBusy, setEmailBusy] = useState(false)
  const [emailError, setEmailError] = useState<string | null>(null)
  const [emailPasswordError, setEmailPasswordError] = useState<string | null>(null)
  const [currentPasswordValue, setCurrentPasswordValue] = useState("")
  const [newPasswordValue, setNewPasswordValue] = useState("")
  const [confirmPasswordValue, setConfirmPasswordValue] = useState("")
  const [passwordBusy, setPasswordBusy] = useState(false)
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [currentPasswordError, setCurrentPasswordError] = useState<string | null>(null)
  const [stepUpOpen, setStepUpOpen] = useState(false)
  const stepUpActionRef = useRef<(() => Promise<void>) | null>(null)

  useEffect(() => {
    setEmailValue(user?.email ?? "")
  }, [user?.email])

  useEffect(() => {
    setPendingEmail(user?.pending_email ?? null)
  }, [user?.pending_email])

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

  const isStepUpError = useCallback(
    (error: unknown) => isAxiosError(error) && error.response?.status === 428,
    []
  )

  const formatDateTime = useCallback((value: string | null) => {
    if (!value) return null
    const parsed = dayjs(value)
    if (!parsed.isValid()) return null
    return parsed.format("DD MMM YYYY HH:mm")
  }, [])

  const activeTotp = useMemo(
    () =>
      (user?.totp_enrollments ?? []).filter(
        (entry) => Boolean(entry.confirmed_at) && !entry.revoked_at
      ),
    [user?.totp_enrollments]
  )

  const pendingTotpEnrollment = useMemo(
    () =>
      (user?.totp_enrollments ?? []).find((entry) => !entry.confirmed_at && !entry.revoked_at) ??
      null,
    [user?.totp_enrollments]
  )
  const pendingTotpId = pendingTotpEnrollment?.id ?? null

  const hasInteractiveMfa = activeTotp.length > 0
  const totpLimitReached = hasInteractiveMfa

  const mfaDisabledMessage = useMemo(() => {
    if (hasInteractiveMfa) {
      return null
    }
    if (user?.mfa_required) {
      return t("settings:security.status.mfaDisabledWasRequired")
    }
    return t("settings:security.status.mfaDisabled")
  }, [hasInteractiveMfa, t, user?.mfa_required])

  const defaultMethodText = useMemo(() => {
    if (!user?.mfa_default_method) {
      return t("settings:security.status.noDefault")
    }
    return t("settings:security.status.defaultTotp")
  }, [t, user?.mfa_default_method])

  const lastVerifiedText = useMemo(() => {
    if (!user?.mfa_last_verified_at) {
      return t("settings:security.status.notVerified")
    }
    const formatted = formatDateTime(user.mfa_last_verified_at)
    return formatted
      ? t("settings:security.status.lastVerified", { value: formatted })
      : t("settings:security.status.notVerified")
  }, [formatDateTime, t, user?.mfa_last_verified_at])

  const isNewPasswordError = useMemo(() => {
    if (!passwordError) return false
    return [
      t("settings:security.password.errors.newRequired"),
      t("settings:security.password.errors.same"),
    ].includes(passwordError)
  }, [passwordError, t])

  const confirmPasswordMessage = useMemo(() => {
    if (!passwordError) return null
    if (
      [
        t("settings:security.password.errors.newRequired"),
        t("settings:security.password.errors.same"),
      ].includes(passwordError)
    ) {
      return null
    }
    return passwordError
  }, [passwordError, t])

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

  const handleChallengeResetNotice = useCallback(() => {
    setSnackbar({ text: t("settings:security.snackbar.challengeReset"), severity: "info" })
  }, [t])

  const handleRevokeSession = useCallback(
    async (sessionId: string, options?: { skipStepUp?: boolean }) => {
      try {
        const result = await revokeSessionMutation.mutateAsync(sessionId)
        setSnackbar({ text: t("settings:sessions.snackbar.revoked"), severity: "success" })

        // Update cache immediately and then invalidate to be safe
        queryClient.setQueryData<ActiveSession[] | undefined>(sessionsKey, (prev) => {
          if (!Array.isArray(prev)) return prev
          return prev.map((s) => (s.id === result.id ? result : s))
        })
        await queryClient.invalidateQueries({ queryKey: sessionsKey })
        if (result?.is_current) {
          await logout()
        }
      } catch (error) {
        if (!options?.skipStepUp && isStepUpError(error)) {
          openStepUpFor(async () => {
            await handleRevokeSession(sessionId, { skipStepUp: true })
          })
          return
        }
        setSnackbar({
          text: resolveDetailMessage(error, t("settings:sessions.snackbar.failed")),
          severity: "error",
        })
      }
    },
    [
      isStepUpError,
      logout,
      openStepUpFor,
      queryClient,
      resolveDetailMessage,
      revokeSessionMutation,
      sessionsKey,
      t,
    ]
  )

  const handleRevokeAllSessions = useCallback(
    async (options?: { skipStepUp?: boolean }) => {
      try {
        const result = await revokeAllSessionsMutation.mutateAsync()
        await queryClient.invalidateQueries({ queryKey: sessionsKey })
        setSnackbar({
          text: t("settings:sessions.snackbar.revokedAll", {
            count: result?.revoked ?? 0,
          }),
          severity: "success",
        })
      } catch (error) {
        if (!options?.skipStepUp && isStepUpError(error)) {
          openStepUpFor(async () => {
            await handleRevokeAllSessions({ skipStepUp: true })
          })
          return
        }
        setSnackbar({
          text: resolveDetailMessage(error, t("settings:sessions.snackbar.revokeAllFailed")),
          severity: "error",
        })
      }
    },
    [
      isStepUpError,
      openStepUpFor,
      queryClient,
      resolveDetailMessage,
      revokeAllSessionsMutation,
      sessionsKey,
      t,
    ]
  )

  const handleEmailSubmit = useCallback(
    async (options?: { skipStepUp?: boolean }) => {
      if (emailBusy) return
      let hasError = false
      const trimmedEmail = emailValue.trim()
      setEmailError(null)
      setEmailPasswordError(null)
      if (!trimmedEmail) {
        setEmailError(t("settings:security.email.errors.required"))
        hasError = true
      } else if (user?.email && trimmedEmail.toLowerCase() === user.email.toLowerCase()) {
        setEmailError(t("settings:security.email.noChange"))
        hasError = true
      } else if (pendingEmail && trimmedEmail.toLowerCase() === pendingEmail.toLowerCase()) {
        setEmailError(t("settings:security.email.pendingSame", { email: pendingEmail }))
        hasError = true
      }
      if (!emailPassword) {
        setEmailPasswordError(t("settings:security.email.errors.passwordRequired"))
        hasError = true
      }
      if (hasError) return

      setEmailBusy(true)
      try {
        await api.post<User>("/users/me/email", {
          email: trimmedEmail,
          password: emailPassword,
        })
        setPendingEmail(trimmedEmail.toLowerCase())
        await refreshMe()
        setEmailPassword("")
        setSnackbar({
          text: t("settings:security.email.confirmationSent", { email: trimmedEmail }),
          severity: "success",
        })
      } catch (error) {
        if (!options?.skipStepUp && isStepUpError(error)) {
          openStepUpFor(async () => {
            await handleEmailSubmit({ skipStepUp: true })
          })
          return
        }
        let handled = false
        if (isAxiosError(error)) {
          const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
          if (typeof detail === "string") {
            if (detail === t("settings:security.email.errors.invalidPassword")) {
              setEmailPasswordError(detail)
              handled = true
            } else {
              setEmailError(detail)
              handled = true
            }
          }
        }
        if (!handled) {
          const message = resolveDetailMessage(error, t("settings:security.email.failed"))
          setEmailError(message)
          setSnackbar({ text: message, severity: "error" })
        }
      } finally {
        setEmailBusy(false)
      }
    },
    [
      emailBusy,
      emailPassword,
      emailValue,
      isStepUpError,
      openStepUpFor,
      refreshMe,
      resolveDetailMessage,
      pendingEmail,
      setSnackbar,
      t,
      user?.email,
    ]
  )

  const handlePasswordSubmit = useCallback(
    async (options?: { skipStepUp?: boolean }) => {
      if (passwordBusy) return
      setCurrentPasswordError(null)
      setPasswordError(null)
      let hasError = false
      if (!currentPasswordValue) {
        setCurrentPasswordError(t("settings:security.password.errors.currentRequired"))
        hasError = true
      }
      let derivedError: string | null = null
      if (!newPasswordValue) {
        derivedError = t("settings:security.password.errors.newRequired")
      } else if (!confirmPasswordValue) {
        derivedError = t("settings:security.password.errors.confirmRequired")
      } else if (newPasswordValue !== confirmPasswordValue) {
        derivedError = t("settings:security.password.errors.mismatch")
      }
      if (derivedError) {
        setPasswordError(derivedError)
        hasError = true
      }
      if (hasError) return

      setPasswordBusy(true)
      try {
        const { data } = await api.post<{
          ok: boolean
          revoked_sessions: number
        }>("/users/me/password", {
          current_password: currentPasswordValue,
          new_password: newPasswordValue,
        })
        if (data?.ok) {
          setSnackbar({
            text: t("settings:security.password.updated", {
              count: data.revoked_sessions ?? 0,
            }),
            severity: "success",
          })
        }
        setCurrentPasswordValue("")
        setNewPasswordValue("")
        setConfirmPasswordValue("")
        await queryClient.invalidateQueries({ queryKey: sessionsKey })
      } catch (error) {
        if (!options?.skipStepUp && isStepUpError(error)) {
          openStepUpFor(async () => {
            await handlePasswordSubmit({ skipStepUp: true })
          })
          return
        }
        const message = resolveDetailMessage(error, t("settings:security.password.failed"))
        let handled = false
        if (isAxiosError(error)) {
          const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
          if (typeof detail === "string") {
            if (detail === t("settings:security.password.errors.currentInvalid")) {
              setCurrentPasswordError(detail)
              handled = true
            } else if (detail === t("settings:security.password.errors.same")) {
              setPasswordError(detail)
              handled = true
            } else {
              setPasswordError(detail)
              handled = true
            }
          }
        }
        if (!handled) {
          setPasswordError(message)
          setSnackbar({ text: message, severity: "error" })
        }
      } finally {
        setPasswordBusy(false)
      }
    },
    [
      confirmPasswordValue,
      currentPasswordValue,
      isStepUpError,
      newPasswordValue,
      openStepUpFor,
      passwordBusy,
      queryClient,
      resolveDetailMessage,
      sessionsKey,
      setSnackbar,
      t,
    ]
  )

  const handleStartTotp = useCallback(
    async (options?: { skipStepUp?: boolean; payload?: TotpEnrollmentStartPayload }) => {
      if (totpBusy || totpLimitReached) return
      setTotpBusy(true)
      setTotpError(null)
      try {
        const { data } = await startTotpEnrollment(options?.payload)
        setTotpDraft(data)
      } catch (error) {
        if (!options?.skipStepUp && isStepUpError(error)) {
          openStepUpFor(async () => {
            await handleStartTotp({ skipStepUp: true, payload: options?.payload })
          })
          return
        }
        const message = resolveDetailMessage(error, t("settings:security.snackbar.totpStartFailed"))
        setTotpError(message)
        setSnackbar({
          text: message,
          severity: "error",
        })
      } finally {
        setTotpBusy(false)
      }
    },
    [
      isStepUpError,
      openStepUpFor,
      resolveDetailMessage,
      setSnackbar,
      setTotpError,
      t,
      totpBusy,
      totpLimitReached,
    ]
  )

  useEffect(() => {
    if (!pendingTotpEnrollment || totpDraft) {
      return
    }
    void handleStartTotp({ payload: { reuse_existing: true } })
  }, [handleStartTotp, pendingTotpEnrollment, totpDraft])

  const handleConfirmTotp = useCallback(
    async (code: string) => {
      const enrollmentId = totpDraft?.enrollment.id ?? pendingTotpId
      if (!enrollmentId) return
      setTotpBusy(true)
      setTotpError(null)
      try {
        await confirmTotpEnrollment({ enrollment_id: enrollmentId, code })
        setTotpDraft(null)
        await refreshMe()
        setSnackbar({ text: t("settings:security.snackbar.totpEnabled"), severity: "success" })
      } catch (error) {
        setTotpError(resolveDetailMessage(error, t("settings:security.snackbar.totpConfirmFailed")))
      } finally {
        setTotpBusy(false)
      }
    },
    [pendingTotpId, refreshMe, resolveDetailMessage, t, totpDraft, setSnackbar]
  )

  const handleCancelTotp = useCallback(async () => {
    const enrollmentId = totpDraft?.enrollment.id ?? pendingTotpId
    if (!enrollmentId || totpBusy) return
    setTotpBusy(true)
    setTotpError(null)
    try {
      await deletePendingTotpEnrollment(enrollmentId)
      setTotpDraft(null)
      await refreshMe()
    } catch (error) {
      const message = resolveDetailMessage(error, t("settings:security.snackbar.totpCancelFailed"))
      setTotpError(message)
      setSnackbar({ text: message, severity: "error" })
    } finally {
      setTotpBusy(false)
    }
  }, [pendingTotpId, refreshMe, resolveDetailMessage, setSnackbar, t, totpBusy, totpDraft])

  const handleDisableTotp = useCallback(
    (enrollmentId: string) => {
      const action = async () => {
        try {
          const { data } = await deleteTotpEnrollment(enrollmentId)
          if (data) {
            setUser((prev) =>
              prev
                ? {
                    ...prev,
                    mfa_default_method: data.mfa_default_method,
                    mfa_required: data.mfa_required,
                  }
                : prev
            )
          }
          await refreshMe()
          setSnackbar({ text: t("settings:security.snackbar.totpDisabled"), severity: "success" })
        } catch (error) {
          setSnackbar({
            text: resolveDetailMessage(error, t("settings:security.snackbar.totpDisableFailed")),
            severity: "error",
          })
        }
      }
      openStepUpFor(action)
    },
    [openStepUpFor, refreshMe, resolveDetailMessage, setSnackbar, setUser, t]
  )

  const {
    data: webauthnCredentialsData,
    isFetching: webauthnFetching,
    refetch: refetchWebAuthn,
  } = useQuery({
    queryKey: ["auth", "webauthn", user?.id ?? "me"],
    queryFn: async () => {
      const { data } = await listWebAuthnCredentials()
      return data
    },
    enabled: tab === 1 && Boolean(user),
  })

  const webauthnCredentials = Array.isArray(webauthnCredentialsData) ? webauthnCredentialsData : []

  const [webauthnBusy, setWebauthnBusy] = useState(false)
  const [webauthnLabel, setWebauthnLabel] = useState("")
  const [isAddingWebAuthn, setIsAddingWebAuthn] = useState(false)

  // Check if browser supports WebAuthn (requires secure context: HTTPS or localhost)
  const webauthnSupported = useMemo(() => browserSupportsWebAuthn(), [])

  const handleRegisterWebAuthn = useCallback(
    async (options?: { skipStepUp?: boolean; label?: string }) => {
      if (webauthnBusy) return
      setWebauthnBusy(true)
      setIsAddingWebAuthn(true)
      try {
        const { data: startData } = await startWebAuthnRegistration()

        if (!isCreationOptions(startData.publicKey)) {
          throw new Error("Invalid WebAuthn creation options received from server")
        }

        const attestationResponse = await startRegistration({
          optionsJSON: startData.publicKey,
        })

        await confirmWebAuthnRegistration({
          challenge: startData.challenge_token,
          response: attestationResponse,
          label: options?.label?.trim() || webauthnLabel.trim() || undefined,
        })

        await Promise.all([refetchWebAuthn(), refreshMe()])
        setSnackbar({ text: t("settings:security.snackbar.webauthnEnabled"), severity: "success" })
        setIsAddingWebAuthn(false)
        setWebauthnLabel("")
      } catch (error) {
        if (!options?.skipStepUp && isStepUpError(error)) {
          openStepUpFor(async () => {
            await handleRegisterWebAuthn({
              skipStepUp: true,
              label: options?.label || webauthnLabel,
            })
          })
          return
        }
        let message = resolveDetailMessage(error, t("settings:security.snackbar.webauthnFailed"))
        if (error instanceof Error && error.name === "NotAllowedError") {
          message = t("settings:security.webauthn.errors.cancelled")
        }
        setSnackbar({ text: message, severity: "error" })
      } finally {
        setWebauthnBusy(false)
      }
    },
    [
      isStepUpError,
      openStepUpFor,
      refetchWebAuthn,
      refreshMe,
      resolveDetailMessage,
      setSnackbar,
      t,
      webauthnBusy,
      webauthnLabel,
    ]
  )

  const handleDeleteWebAuthn = useCallback(
    (credentialId: string) => {
      const action = async () => {
        try {
          await deleteWebAuthnCredential(credentialId)
          await Promise.all([refetchWebAuthn(), refreshMe()])
          setSnackbar({
            text: t("settings:security.snackbar.webauthnDeleted"),
            severity: "success",
          })
        } catch (error) {
          setSnackbar({
            text: resolveDetailMessage(error, t("settings:security.snackbar.webauthnDeleteFailed")),
            severity: "error",
          })
        }
      }
      openStepUpFor(action)
    },
    [openStepUpFor, refetchWebAuthn, refreshMe, resolveDetailMessage, setSnackbar, t]
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
      return setSnackbar({
        text: t("settings:media.validation.supportedFormats"),
        severity: "warning",
      })
    if (!withinSize(file))
      return setSnackbar({ text: t("settings:media.validation.fileTooLarge"), severity: "warning" })
    try {
      setAvatarBusy(true)
      const fd = new FormData()
      fd.append("file", file)
      await api.post("/users/me/avatar", fd, { headers: { "Content-Type": "multipart/form-data" } })
      await refreshMe()
      setAvatarVersion(Date.now())
      setSnackbar({ text: t("settings:media.avatar.updated"), severity: "success" })
    } catch (error) {
      setSnackbar({
        text: resolveDetailMessage(error, t("settings:media.avatar.uploadFailed")),
        severity: "error",
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
      setSnackbar({ text: t("settings:media.avatar.deleted"), severity: "success" })
    } catch (error) {
      setSnackbar({
        text: resolveDetailMessage(error, t("settings:media.avatar.deleteFailed")),
        severity: "error",
      })
    } finally {
      setAvatarBusy(false)
    }
  }

  const uploadCover = async (file: File) => {
    if (!isImage(file))
      return setSnackbar({
        text: t("settings:media.validation.supportedFormats"),
        severity: "warning",
      })
    if (!withinSize(file))
      return setSnackbar({ text: t("settings:media.validation.fileTooLarge"), severity: "warning" })
    try {
      setCoverBusy(true)
      const fd = new FormData()
      fd.append("file", file)
      await api.post("/users/me/cover", fd, { headers: { "Content-Type": "multipart/form-data" } })
      await refreshMe()
      setCoverVersion(Date.now())
      setSnackbar({ text: t("settings:media.cover.updated"), severity: "success" })
    } catch (error) {
      setSnackbar({
        text: resolveDetailMessage(error, t("settings:media.cover.uploadFailed")),
        severity: "error",
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
      setSnackbar({ text: t("settings:media.cover.deleted"), severity: "success" })
    } catch (error) {
      setSnackbar({
        text: resolveDetailMessage(error, t("settings:media.cover.deleteFailed")),
        severity: "error",
      })
    } finally {
      setCoverBusy(false)
    }
  }

  const [confirmLogout, setConfirmLogout] = useState(false)

  return (
    <Layout>
      <PageFadeIn>
        <div className="flex h-full w-full flex-col bg-page text-primary-text sm:h-[640px] sm:max-h-[85vh] sm:flex-row">
          <div className="px-2 md:px-4">
            <div
              data-fade
              style={fadeDelayStyle("80ms")}
              className="mb-8 flex flex-wrap items-center gap-4 sm:gap-5"
            >
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-brand-subtle-bg text-brand shadow-premium transition-transform duration-200 hover:scale-105 backdrop-blur-sm [-webkit-backdrop-filter:blur(12px)]">
                <SettingsIcon className="h-6 w-6" />
              </div>
              <h1 className="text-[clamp(1.6rem,5vw,2.75rem)] font-bold tracking-tight text-primary-text">
                {t("settings:page.title")}
              </h1>
            </div>

            <div data-fade style={fadeDelayStyle("140ms")} className="mb-8">
              <Tabs
                value={tab}
                onChange={(_, value) => setTab(value)}
                variant="scrollable"
                scrollButtons="auto"
              >
                <Tab label={t("settings:tabs.general")} />
                <Tab label={t("settings:tabs.account")} />
                <Tab label={t("settings:tabs.integrations")} />
              </Tabs>
            </div>

            <div data-fade style={fadeDelayStyle("200ms")}>
              {tab === 0 && (
                <div className="flex w-full flex-col gap-8 sm:gap-10 xl:max-w-[min(100%,1100px)] 2xl:gap-12">
                  <div className="flex flex-col gap-3">
                    <SectionTitle variant="h6">{t("settings:appearance.theme.title")}</SectionTitle>
                    <RadioGroup
                      row
                      value={theme}
                      onChange={(
                        _event: React.ChangeEvent<HTMLInputElement> | null,
                        value: string
                      ) => handleThemeChange(_event as React.ChangeEvent<HTMLInputElement>, value)}
                    >
                      <FormControlLabel
                        value="system"
                        control={<Radio data-testid="theme-option-system" />}
                        label={
                          <span className="flex items-center gap-2 text-[color-mix(in_srgb,var(--page-text)_82%,var(--secondary-text)_18%)]">
                            <Monitor className="h-5 w-5" />
                            <span>{t("settings:appearance.theme.options.system")}</span>
                          </span>
                        }
                      />
                      <FormControlLabel
                        value="light"
                        control={<Radio data-testid="theme-option-light" />}
                        label={
                          <span className="flex items-center gap-2 text-[color-mix(in_srgb,var(--page-text)_82%,var(--secondary-text)_18%)]">
                            <Sun className="h-5 w-5" />
                            <span>{t("settings:appearance.theme.options.light")}</span>
                          </span>
                        }
                      />
                      <FormControlLabel
                        value="dark"
                        control={<Radio data-testid="theme-option-dark" />}
                        label={
                          <span className="flex items-center gap-2 text-[color-mix(in_srgb,var(--page-text)_82%,var(--secondary-text)_18%)]">
                            <Moon className="h-5 w-5" />
                            <span>{t("settings:appearance.theme.options.dark")}</span>
                          </span>
                        }
                      />
                    </RadioGroup>
                  </div>

                  <div className="flex flex-col gap-3">
                    <SectionTitle variant="h6">{t("settings:language.title")}</SectionTitle>
                    <RadioGroup
                      row
                      value={language}
                      onChange={(
                        _event: React.ChangeEvent<HTMLInputElement> | null,
                        value: string
                      ) => setLanguage(value as SupportedLanguage)}
                      aria-label={t("settings:language.aria")}
                    >
                      {availableLanguages.map((code) => (
                        <FormControlLabel
                          key={code}
                          value={code}
                          control={<Radio />}
                          label={
                            <span className="text-[color-mix(in_srgb,var(--page-text)_84%,var(--secondary-text)_16%)]">
                              {t(`settings:language.options.${code}`)}
                            </span>
                          }
                        />
                      ))}
                    </RadioGroup>
                    <SectionSubtitle className="mt-1">
                      {t("settings:language.description")}
                    </SectionSubtitle>
                  </div>

                  <Divider />
                  <div className="flex flex-col gap-4">
                    <SectionTitle variant="h6">{t("settings:notifications.title")}</SectionTitle>
                    {!pushSupported ? (
                      <Alert severity="warning" variant="outlined">
                        {t("settings:notifications.unsupported")}
                      </Alert>
                    ) : (
                      <div className="flex flex-col gap-4">
                        {notificationPermission === "denied" ? (
                          <div className="flex flex-col gap-3">
                            <Alert severity="error" variant="outlined">
                              {t("settings:notifications.blocked.description")}
                            </Alert>
                            <SectionSubtitle>
                              {t("settings:notifications.blocked.hint")}
                            </SectionSubtitle>
                            <div className="flex flex-col gap-2.5 sm:flex-row sm:items-center">
                              <Button
                                variant="contained"
                                onClick={() => void enableNotifications()}
                                disabled={pushBusy}
                              >
                                {t("settings:notifications.cta.checkPermission")}
                              </Button>
                              <p className="text-sm font-semibold text-text-muted-more">
                                {t("settings:notifications.status", { status: permissionText })}
                              </p>
                            </div>
                          </div>
                        ) : notificationPermission === "default" ? (
                          <div className="flex flex-col gap-3">
                            <SectionSubtitle>
                              {t("settings:notifications.cta.prompt")}
                            </SectionSubtitle>
                            <div className="flex flex-col gap-2.5 sm:flex-row sm:items-center">
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
                              <p className="text-sm font-semibold text-text-muted-more">
                                {t("settings:notifications.status", { status: permissionText })}
                              </p>
                            </div>
                          </div>
                        ) : (
                          <>
                            <label className="m-0 flex h-11 items-center gap-2.5 cursor-pointer">
                              <SwitchControl
                                checked={notificationsEnabled}
                                onChange={handleNotificationsToggle}
                                disabled={pushBusy || pushInitializing}
                                aria-label={t("settings:notifications.toggles.notifications.aria")}
                              />
                              <span className="font-semibold text-text-soft">
                                {t("settings:notifications.toggles.notifications.label")}
                              </span>
                            </label>

                            <label className="m-0 flex min-h-[44px] items-center gap-2.5 cursor-pointer">
                              <SwitchControl
                                checked={dndEnabled}
                                onChange={handleDndToggle}
                                disabled={dndSaving}
                                aria-label={t("settings:notifications.toggles.dnd.aria")}
                              />
                              <span className="font-semibold text-text-soft">
                                {t("settings:notifications.toggles.dnd.label")}
                              </span>
                            </label>

                            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                              <TextField
                                type="time"
                                label={t("settings:dnd.start")}
                                value={dndStart}
                                onChange={handleDndStartChange}
                                onBlur={handleDndStartBlur}
                                disabled={!dndEnabled || dndSaving}
                                size="small"
                              />
                              <TextField
                                type="time"
                                label={t("settings:dnd.end")}
                                value={dndEnd}
                                onChange={handleDndEndChange}
                                onBlur={handleDndEndBlur}
                                disabled={!dndEnabled || dndSaving}
                                size="small"
                              />
                            </div>
                          </>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {tab === 1 && (
                <div className="flex w-full flex-col gap-5 sm:gap-6 xl:max-w-[min(100%,1080px)] 2xl:max-w-[min(100%,1240px)]">
                  <SectionCard component="section">
                    <div className="flex flex-col gap-2 mb-4">
                      <SectionTitle variant="subtitle1">
                        {t("settings:account.profile.title")}
                      </SectionTitle>
                      <SectionSubtitle variant="body2">
                        Управление вашим профилем и медиа контентом
                      </SectionSubtitle>
                    </div>

                    <ul className="flex flex-col gap-3 list-none m-0 p-0">
                      <li className="list-none">
                        <AccordionSection
                          title={t("settings:media.avatar.title")}
                          subtitle="Загрузите или измените фото профиля"
                        >
                          <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center">
                            <Avatar
                              src={avatarSrc}
                              alt={user?.full_name || "avatar"}
                              className="w-20 h-20"
                              imgProps={{
                                onError: handleAvatarError,
                                loading: "lazy",
                                decoding: "async",
                                referrerPolicy: "no-referrer",
                              }}
                            />
                            <div className="flex flex-col sm:flex-row gap-2 flex-1">
                              <Button
                                size="small"
                                variant="contained"
                                onClick={triggerAvatarPick}
                                disabled={avatarBusy}
                                className="w-full sm:w-auto"
                              >
                                {t("settings:media.avatar.change")}
                              </Button>
                              <Button
                                size="small"
                                variant="outlined"
                                color="error"
                                onClick={removeAvatar}
                                disabled={avatarBusy}
                                className="w-full sm:w-auto"
                              >
                                {t("settings:media.avatar.delete")}
                              </Button>
                            </div>
                          </div>
                        </AccordionSection>
                      </li>

                      <li className="list-none">
                        <AccordionSection
                          title={t("settings:media.cover.title")}
                          subtitle="Установите обложку для вашего профиля"
                        >
                          <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center">
                            <div
                              data-testid="settings-cover-preview"
                              className="h-20 w-32 rounded-xl border shrink-0"
                              style={{
                                background: coverSrc
                                  ? `url(${coverSrc}) center/cover no-repeat`
                                  : "var(--surface-hover)",
                                borderColor: "var(--glass-border-subtle)",
                              }}
                            />
                            <div className="flex flex-col sm:flex-row gap-2 flex-1">
                              <Button
                                size="small"
                                variant="contained"
                                onClick={triggerCoverPick}
                                disabled={coverBusy}
                                className="w-full sm:w-auto"
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
                                  className="w-full sm:w-auto"
                                >
                                  {t("settings:media.cover.remove")}
                                </Button>
                              )}
                            </div>
                          </div>
                        </AccordionSection>
                      </li>

                      <li className="list-none">
                        <AccordionSection
                          title="Информация о пользователе"
                          subtitle="Имя, биография и другие данные профиля"
                        >
                          <div className="flex flex-col gap-3">
                            <SectionSubtitle className="text-sm">
                              Редактируйте информацию о себе на странице профиля
                            </SectionSubtitle>
                            <Button
                              size="small"
                              variant="outlined"
                              onClick={() => navigate({ pathname: "/profile", search: "?edit=1" })}
                              className="self-start"
                            >
                              {t("common:buttons.edit")}
                            </Button>
                          </div>
                        </AccordionSection>
                      </li>
                    </ul>
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
                    <div className="flex flex-col gap-2">
                      <SectionTitle variant="subtitle1">
                        {t("settings:account.logout.title")}
                      </SectionTitle>
                      <SectionSubtitle variant="body2">
                        {t("settings:account.logout.subtitle")}
                      </SectionSubtitle>
                    </div>
                    <Button
                      size="small"
                      variant="outlined"
                      color="error"
                      onClick={() => setConfirmLogout(true)}
                      className="self-start sm:self-end mt-2"
                    >
                      {t("settings:account.logout.button")}
                    </Button>
                  </SectionCard>

                  <SectionCard component="section">
                    <div className="flex flex-col gap-2 mb-4">
                      <SectionTitle variant="subtitle1">
                        {t("settings:security.account.title")}
                      </SectionTitle>
                      <SectionSubtitle variant="body2">
                        {t("settings:security.account.subtitle")}
                      </SectionSubtitle>
                    </div>

                    <div className="flex flex-col gap-3">
                      <AccordionSection
                        title={t("settings:security.email.title")}
                        subtitle={t("settings:security.email.subtitle")}
                      >
                        <form
                          className="flex flex-col gap-3"
                          onSubmit={(event) => {
                            event.preventDefault()
                            void handleEmailSubmit()
                          }}
                        >
                          {pendingEmail ? (
                            <Alert severity="info" variant="outlined">
                              {t("settings:security.email.pendingNotice", { email: pendingEmail })}
                            </Alert>
                          ) : null}
                          <div className="flex flex-col sm:flex-row gap-2.5 items-start sm:items-end">
                            <TextField
                              fullWidth
                              type="email"
                              size="small"
                              label={t("settings:security.email.label")}
                              value={emailValue}
                              onChange={(event) => {
                                setEmailValue(event.target.value)
                                setEmailError(null)
                              }}
                              error={Boolean(emailError)}
                              helperText={emailError ?? undefined}
                              autoComplete="email"
                            />
                            <TextField
                              fullWidth
                              type="password"
                              size="small"
                              label={t("settings:security.email.passwordLabel")}
                              value={emailPassword}
                              onChange={(event) => {
                                setEmailPassword(event.target.value)
                                setEmailPasswordError(null)
                              }}
                              error={Boolean(emailPasswordError)}
                              helperText={emailPasswordError ?? undefined}
                              autoComplete="current-password"
                            />
                          </div>
                          <div className="flex flex-col items-start gap-2.5 sm:flex-row sm:items-center">
                            <Button
                              type="submit"
                              variant="contained"
                              disabled={emailBusy}
                              startIcon={
                                emailBusy ? (
                                  <CircularProgress size={18} color="inherit" />
                                ) : undefined
                              }
                            >
                              {t("settings:security.email.updateButton")}
                            </Button>
                            <SectionSubtitle className="text-sm">
                              {t("settings:security.email.helper")}
                            </SectionSubtitle>
                          </div>
                        </form>
                      </AccordionSection>

                      <AccordionSection
                        title={t("settings:security.password.title")}
                        subtitle={t("settings:security.password.subtitle")}
                      >
                        <form
                          className="flex flex-col gap-3"
                          onSubmit={(event) => {
                            event.preventDefault()
                            void handlePasswordSubmit()
                          }}
                        >
                          <div className="flex flex-col sm:flex-row gap-2.5">
                            <TextField
                              fullWidth
                              type="password"
                              size="small"
                              label={t("settings:security.password.currentLabel")}
                              value={currentPasswordValue}
                              onChange={(event) => {
                                setCurrentPasswordValue(event.target.value)
                                setCurrentPasswordError(null)
                              }}
                              error={Boolean(currentPasswordError)}
                              helperText={currentPasswordError ?? undefined}
                              autoComplete="current-password"
                            />
                            <TextField
                              fullWidth
                              type="password"
                              size="small"
                              label={t("settings:security.password.newLabel")}
                              value={newPasswordValue}
                              onChange={(event) => {
                                setNewPasswordValue(event.target.value)
                                if (passwordError) setPasswordError(null)
                              }}
                              error={isNewPasswordError}
                              helperText={
                                isNewPasswordError ? (passwordError ?? undefined) : undefined
                              }
                              autoComplete="new-password"
                            />
                          </div>
                          <div className="flex flex-col sm:flex-row gap-2.5 items-start sm:items-center">
                            <TextField
                              fullWidth
                              type="password"
                              size="small"
                              label={t("settings:security.password.confirmLabel")}
                              value={confirmPasswordValue}
                              onChange={(event) => {
                                setConfirmPasswordValue(event.target.value)
                                if (passwordError) setPasswordError(null)
                              }}
                              error={Boolean(confirmPasswordMessage)}
                              helperText={confirmPasswordMessage ?? undefined}
                              autoComplete="new-password"
                            />
                            <Button
                              type="submit"
                              variant="contained"
                              disabled={passwordBusy}
                              startIcon={
                                passwordBusy ? (
                                  <CircularProgress size={18} color="inherit" />
                                ) : undefined
                              }
                            >
                              {passwordBusy
                                ? t("settings:security.password.updating")
                                : t("settings:security.password.updateButton")}
                            </Button>
                          </div>
                        </form>
                      </AccordionSection>

                      <AccordionSection
                        title={t("settings:sessions.title")}
                        subtitle={t("settings:sessions.subtitle")}
                      >
                        <div className="flex flex-col gap-3">
                          <div className="flex flex-col items-start gap-2.5 sm:flex-row sm:items-center sm:justify-between">
                            <Button
                              variant="outlined"
                              color="error"
                              disabled={revokeAllSessionsMutation.isPending}
                              onClick={() => void handleRevokeAllSessions()}
                              startIcon={
                                revokeAllSessionsMutation.isPending ? (
                                  <CircularProgress size={18} color="inherit" />
                                ) : undefined
                              }
                            >
                              {t("settings:sessions.revokeAll")}
                            </Button>
                            <SectionSubtitle className="text-sm">
                              {t("settings:sessions.revokeAllHint")}
                            </SectionSubtitle>
                          </div>

                          {sessions.length === 0 && sessionsFetching ? (
                            <div className="mt-3 flex flex-row items-center gap-2.5">
                              <CircularProgress size={18} />
                              <p className="text-sm font-semibold text-[color-mix(in_srgb,var(--page-text)_84%,var(--secondary-text)_16%)]">
                                {t("settings:sessions.loading")}
                              </p>
                            </div>
                          ) : sessionsErrorMessage ? (
                            <Alert severity="error" variant="outlined" className="mt-3">
                              {sessionsErrorMessage}
                            </Alert>
                          ) : sessions.length === 0 ? (
                            <SectionSubtitle className="mt-3 text-sm">
                              {t("settings:sessions.empty")}
                            </SectionSubtitle>
                          ) : (
                            <div className="flex flex-col gap-3 mt-3">
                              {sortedSessions.map((session, idx) => {
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
                                  <SessionItem
                                    key={session.id}
                                    data-revoked={isRevoked ? "true" : undefined}
                                  >
                                    <div className="min-w-0">
                                      <p
                                        className={cn(
                                          "text-sm wrap-break-word transition-colors",
                                          session.is_current ? "font-semibold" : "font-medium",
                                          isRevoked
                                            ? "text-[color-mix(in_srgb,var(--page-text)_68%,white_32%)]"
                                            : "text-[color-mix(in_srgb,var(--page-text)_90%,var(--secondary-text)_10%)]"
                                        )}
                                      >
                                        {session.user_agent || t("settings:sessions.unknownDevice")}
                                      </p>
                                      <p
                                        className={cn(
                                          "text-xs transition-colors",
                                          isRevoked
                                            ? "italic text-[color-mix(in_srgb,var(--page-text)_64%,white_36%)]"
                                            : "text-[color-mix(in_srgb,var(--page-text)_78%,var(--secondary-text)_22%)]"
                                        )}
                                      >
                                        {details}
                                      </p>
                                    </div>
                                    <div className="flex flex-row flex-wrap items-center justify-start gap-2 gap-y-1.5 sm:justify-end">
                                      <Chip
                                        key={isRevoked ? "revoked" : "active"}
                                        data-testid={`session-status-${session.id}`}
                                        size="small"
                                        label={statusLabel}
                                        variant="outlined"
                                        color={session.is_current ? "primary" : "default"}
                                        className={cn("font-semibold", isRevoked && "opacity-80")}
                                      />
                                      {!session.is_current && !isRevoked && (
                                        <Button
                                          data-testid={`session-revoke-${session.id}`}
                                          size="small"
                                          variant="text"
                                          color="error"
                                          disabled={disableRevoke}
                                          onClick={() => {
                                            console.log(
                                              `[settings] Clicked revoke for session ${session.id}`
                                            )
                                            void handleRevokeSession(session.id)
                                          }}
                                        >
                                          {t("settings:sessions.revoke")}
                                        </Button>
                                      )}
                                    </div>
                                  </SessionItem>
                                )
                              })}
                            </div>
                          )}
                        </div>
                      </AccordionSection>
                    </div>
                  </SectionCard>

                  <SectionCard component="section">
                    <div className="flex flex-col gap-2 mb-3">
                      <SectionTitle variant="subtitle1">
                        {t("settings:security.title")}
                      </SectionTitle>
                      <SectionSubtitle variant="body2">
                        {t("settings:security.subtitle")}
                      </SectionSubtitle>
                    </div>

                    {mfaDisabledMessage ? (
                      <Alert severity="warning" variant="outlined" className="mb-3">
                        {mfaDisabledMessage}
                      </Alert>
                    ) : null}

                    <div className="flex flex-col sm:flex-row gap-2 mb-4">
                      <Chip
                        size="small"
                        label={defaultMethodText}
                        className={securityStatusChipClassName}
                      />
                      <Chip
                        size="small"
                        label={lastVerifiedText}
                        className={securityStatusChipClassName}
                      />
                    </div>

                    <div className="flex flex-col gap-3 mt-3">
                      <AccordionSection
                        title={t("settings:security.method.totp")}
                        subtitle={t("settings:security.totp.description")}
                      >
                        {pendingTotpEnrollment || totpDraft ? (
                          <div className="flex flex-col gap-4">
                            <div className="text-xs font-bold text-(--secondary-text) uppercase tracking-widest opacity-60">
                              {t("settings:security.totp.pendingTitle")}
                            </div>
                            <SectionSubtitle className="text-sm">
                              {t("settings:security.totp.pendingDescription")}
                            </SectionSubtitle>
                            {totpDraft ? (
                              <TotpQrDisplay
                                otpauthUrl={totpDraft.otpauth_url}
                                secret={totpDraft.secret}
                                label={totpDraft.enrollment.label}
                              />
                            ) : null}
                            {totpError ? (
                              <Alert severity="error" variant="outlined">
                                {totpError}
                              </Alert>
                            ) : null}
                            <OtpEntry
                              loading={totpBusy}
                              error={totpError}
                              helperText={t("settings:security.totp.pendingHelper")}
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
                          </div>
                        ) : (
                          <div className="flex flex-col gap-3">
                            {activeTotp.length ? (
                              <div className="flex flex-col gap-2.5">
                                {activeTotp.map((enrollment: MfaTotpEnrollment, index: number) => (
                                  <div
                                    key={enrollment.id}
                                    className={cn(
                                      "flex flex-col gap-2.5 rounded-2xl border p-3 transition-colors sm:flex-row sm:items-center sm:justify-between",
                                      "border-[color-mix(in_srgb,var(--glass-border)_88%,transparent)]",
                                      "bg-[color-mix(in_srgb,var(--card-bg)_96%,var(--primary-main)_4%)]",
                                      "dark:border-white/10",
                                      "dark:bg-[color-mix(in_srgb,var(--card-bg)_90%,var(--bg-page)_10%)]"
                                    )}
                                  >
                                    <div className="flex min-w-0 flex-col gap-1">
                                      <p className="font-semibold text-[color-mix(in_srgb,var(--page-text)_90%,var(--nav-link)_10%)]">
                                        {enrollment.label ||
                                          t("settings:security.totp.unnamed", { index: index + 1 })}
                                      </p>
                                      <SectionSubtitle className="text-xs">
                                        {t("settings:security.totp.added", {
                                          value: formatDateTime(enrollment.created_at) ?? "—",
                                        })}
                                      </SectionSubtitle>
                                    </div>
                                    <Button
                                      variant="outlined"
                                      color="error"
                                      size="small"
                                      onClick={() => handleDisableTotp(enrollment.id)}
                                    >
                                      {t("settings:security.totp.remove")}
                                    </Button>
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <SectionSubtitle className="text-sm">
                                {t("settings:security.totp.empty")}
                              </SectionSubtitle>
                            )}
                            {totpError ? (
                              <Alert severity="error" variant="outlined">
                                {totpError}
                              </Alert>
                            ) : null}
                            {totpLimitReached ? (
                              <Alert severity="info" variant="outlined">
                                {t("settings:security.totp.limitReached")}
                              </Alert>
                            ) : (
                              <Button
                                variant="contained"
                                onClick={() => void handleStartTotp()}
                                disabled={totpBusy}
                              >
                                {t("settings:security.totp.add")}
                              </Button>
                            )}
                          </div>
                        )}
                      </AccordionSection>

                      <AccordionSection
                        title={t("settings:security.method.webauthn")}
                        subtitle={t("settings:security.webauthn.description")}
                      >
                        <div className="flex flex-col gap-3">
                          {webauthnCredentials.length ? (
                            <div className="flex flex-col gap-2.5">
                              {webauthnCredentials.map((credential: any) => (
                                <div
                                  key={credential.id}
                                  className={cn(
                                    "flex flex-col gap-2.5 rounded-[18px] border p-3 transition-colors sm:flex-row sm:items-center sm:justify-between",
                                    "border-[color-mix(in_srgb,var(--glass-border)_88%,transparent)]",
                                    "bg-[color-mix(in_srgb,var(--card-bg)_96%,var(--primary-main)_4%)]",
                                    "dark:border-white/10",
                                    "dark:bg-[color-mix(in_srgb,var(--card-bg)_90%,var(--bg-page)_10%)]"
                                  )}
                                >
                                  <div className="flex min-w-0 items-center gap-3">
                                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[color-mix(in_srgb,var(--nav-link)_10%,transparent)] text-(--nav-link)">
                                      <Fingerprint className="h-5 w-5" />
                                    </div>
                                    <div className="flex min-w-0 flex-col gap-0.5">
                                      <p className="font-semibold text-[color-mix(in_srgb,var(--page-text)_90%,var(--nav-link)_10%)]">
                                        {credential.label ||
                                          t("settings:security.webauthn.defaultLabel")}
                                      </p>
                                      <SectionSubtitle className="text-xs whitespace-nowrap overflow-hidden text-ellipsis">
                                        {t("settings:security.webauthn.added", {
                                          value: formatDateTime(credential.created_at) ?? "—",
                                        })}
                                        {credential.last_used_at &&
                                          ` • ${t("settings:security.webauthn.lastUsed", {
                                            value: formatDateTime(credential.last_used_at),
                                          })}`}
                                      </SectionSubtitle>
                                    </div>
                                  </div>
                                  <Button
                                    variant="outlined"
                                    color="error"
                                    size="small"
                                    onClick={() => handleDeleteWebAuthn(credential.id)}
                                  >
                                    {t("common:buttons.delete")}
                                  </Button>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <SectionSubtitle className="text-sm">
                              {t("settings:security.webauthn.empty")}
                            </SectionSubtitle>
                          )}

                          <Button
                            variant="contained"
                            onClick={() => setIsAddingWebAuthn(true)}
                            disabled={webauthnBusy}
                            startIcon={
                              webauthnBusy ? (
                                <CircularProgress size={18} color="inherit" />
                              ) : (
                                <Fingerprint className="h-4 w-4" />
                              )
                            }
                          >
                            {t("settings:security.webauthn.add")}
                          </Button>

                          <Dialog
                            open={isAddingWebAuthn}
                            onClose={() => setIsAddingWebAuthn(false)}
                            maxWidth="xs"
                            fullWidth
                          >
                            <DialogTitle>
                              {t("settings:security.webauthn.dialog.title")}
                            </DialogTitle>
                            <DialogContent>
                              <div className="flex flex-col gap-4 py-2">
                                {!webauthnSupported ? (
                                  <Alert severity="warning" variant="outlined">
                                    {t("settings:security.webauthn.notSupported", {
                                      defaultValue:
                                        "WebAuthn недоступен. Для регистрации отпечатка пальца требуется HTTPS или localhost.",
                                    })}
                                  </Alert>
                                ) : (
                                  <>
                                    <p className="text-sm">
                                      {t("settings:security.webauthn.dialog.description")}
                                    </p>
                                    <TextField
                                      fullWidth
                                      label={t("settings:security.webauthn.labelField")}
                                      placeholder={t("settings:security.webauthn.labelPlaceholder")}
                                      value={webauthnLabel}
                                      onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                                        setWebauthnLabel(e.target.value)
                                      }
                                      disabled={webauthnBusy}
                                      autoFocus
                                    />
                                  </>
                                )}
                              </div>
                            </DialogContent>
                            <DialogActions>
                              <Button
                                variant="text"
                                color="inherit"
                                onClick={() => setIsAddingWebAuthn(false)}
                                disabled={webauthnBusy}
                                className="px-(--btn-padding-x) py-(--btn-padding-y)"
                              >
                                {t("common:buttons.cancel")}
                              </Button>
                              {webauthnSupported && (
                                <Button
                                  variant="contained"
                                  onClick={() => void handleRegisterWebAuthn()}
                                  disabled={webauthnBusy || !webauthnLabel.trim()}
                                  className="px-(--btn-padding-x) py-(--btn-padding-y) flex-1"
                                  startIcon={
                                    webauthnBusy ? (
                                      <CircularProgress size={18} color="inherit" />
                                    ) : undefined
                                  }
                                >
                                  {t("common:buttons.add")}
                                </Button>
                              )}
                            </DialogActions>
                          </Dialog>
                        </div>
                      </AccordionSection>
                    </div>
                  </SectionCard>
                </div>
              )}

              {tab === 2 && (
                <div className="flex w-full flex-col gap-6 sm:gap-7 xl:max-w-[min(100%,820px)]">
                  <div className="flex flex-col gap-4">
                    <div className="flex items-center gap-2">
                      <SpotifyLogo className="rounded-full" />
                      <SectionTitle variant="subtitle1" className="text-lg">
                        {t("settings:integrations.spotify.title")}
                      </SectionTitle>
                    </div>
                    <div className="flex flex-wrap items-center gap-2.5">
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
                    </div>
                    {!spotifyConnected ? (
                      <Button variant="contained" onClick={connectSpotify} className="self-start">
                        {t("settings:integrations.spotify.connect")}
                      </Button>
                    ) : (
                      <Button
                        variant="outlined"
                        color="error"
                        onClick={disconnectSpotify}
                        className="self-start"
                      >
                        {t("settings:integrations.spotify.disconnect")}
                      </Button>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>

          <Dialog
            open={confirmLogout}
            onClose={() => setConfirmLogout(false)}
            maxWidth="xs"
            fullWidth
          >
            <DialogTitle>{t("settings:account.logout.dialogTitle")}</DialogTitle>
            <DialogContent>
              <p className="text-sm">{t("settings:account.logout.dialogDescription")}</p>
            </DialogContent>
            <DialogActions>
              <Button
                onClick={() => setConfirmLogout(false)}
                className="px-(--btn-padding-x) py-(--btn-padding-y)"
              >
                {t("common:buttons.cancel")}
              </Button>
              <Button
                color="error"
                onClick={async () => {
                  setConfirmLogout(false)
                  await logout()
                }}
                className="px-(--btn-padding-x) py-(--btn-padding-y)"
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
            onChallengeReset={handleChallengeResetNotice}
          />
          <Snackbar
            open={!!snackbar}
            autoHideDuration={2600}
            onClose={() => setSnackbar(null)}
            anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
          >
            <Alert
              onClose={() => setSnackbar(null)}
              severity={snackbar?.severity || "info"}
              variant="filled"
              className="w-full"
            >
              {snackbar?.text}
            </Alert>
          </Snackbar>
        </div>
      </PageFadeIn>
    </Layout>
  )
}
