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
import type { MfaTotpEnrollment } from "../types/Mfa"

import {
  useAvatarUpload,
  useCoverUpload,
  useWebAuthn,
  useDndSettings,
  useSessionManagement,
  useEmailChange,
  usePasswordChange,
  useTotpEnrollment,
} from "./settings/hooks"
import type { User } from "../types/User"
import type { SetSnackbar } from "./settings/types"

import { cn } from "../utils/cn"
import { resolveMediaUrl, addVersionParam } from "../utils/media"
import { sanitizeSpotifyAuthorizeUrl } from "../utils/spotify"

import { SpotifySection } from "./settings/sections"

const DEFAULT_AVATAR = "https://www.gravatar.com/avatar/00000000000000000000000000000000?d=mp&f=y"
const AVATAR_PLACEHOLDER_URL = DEFAULT_AVATAR

const fadeDelayStyle = (value: string): CSSProperties =>
  ({ "--fade-delay": value }) as CSSProperties

// Types moved to settings/types.ts or hook files where appropriate

// Tailwind CSS components

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

  const [stepUpOpen, setStepUpOpen] = useState(false)
  const stepUpActionRef = useRef<(() => Promise<void>) | null>(null)

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

  const {
    inputRef: avatarInputRef,
    busy: avatarBusy,
    avatarSrc,
    triggerPick: triggerAvatarPick,
    upload: uploadAvatar,
    remove: removeAvatar,
    handleError: handleAvatarError,
  } = useAvatarUpload(setSnackbar)

  const {
    inputRef: coverInputRef,
    busy: coverBusy,
    coverSrc,
    triggerPick: triggerCoverPick,
    upload: uploadCover,
    remove: removeCover,
  } = useCoverUpload(setSnackbar)

  const {
    dndEnabled,
    dndStart,
    dndEnd,
    dndSaving,
    handleDndToggle,
    handleDndStartChange,
    handleDndStartBlur,
    handleDndEndChange,
    handleDndEndBlur,
  } = useDndSettings(setSnackbar)

  const {
    sessions,
    sortedSessions,
    sessionsFetching,
    sessionsIsError,
    sessionsError,
    handleRevokeSession,
    handleRevokeAllSessions,
    revokeSessionBusy,
    revokeAllSessionsBusy,
    formatSessionTimestamp,
  } = useSessionManagement({
    setSnackbar,
    tabActive: tab === 1,
    openStepUpFor,
  })

  const sessionsErrorMessage = useMemo(() => {
    if (!sessionsIsError) return null
    if (isAxiosError(sessionsError) && sessionsError.response?.data?.detail) {
      return String(sessionsError.response.data.detail)
    }
    return sessionsError instanceof Error
      ? sessionsError.message
      : t("settings:sessions.error")
  }, [sessionsIsError, sessionsError, t])

  const {
    emailValue,
    emailPassword,
    emailBusy,
    emailError,
    emailPasswordError,
    pendingEmail,
    setEmailValue,
    setEmailPassword,
    handleEmailSubmit,
  } = useEmailChange({
    setSnackbar,
    openStepUpFor,
  })

  const {
    currentPasswordValue,
    newPasswordValue,
    confirmPasswordValue,
    passwordBusy,
    passwordError,
    currentPasswordError,
    isNewPasswordError,
    confirmPasswordMessage,
    setCurrentPasswordValue,
    setNewPasswordValue,
    setConfirmPasswordValue,
    handlePasswordSubmit,
  } = usePasswordChange({
    setSnackbar,
    sessionsQueryKey: ["auth", "sessions", user?.id ?? "me"],
    openStepUpFor,
  })

  const {
    totpDraft,
    totpBusy,
    totpError,
    activeTotp,
    pendingTotpEnrollment,
    hasInteractiveMfa,
    totpLimitReached,
    mfaDisabledMessage,
    defaultMethodText,
    lastVerifiedText,
    handleStartTotp,
    handleConfirmTotp,
    handleCancelTotp,
    handleDisableTotp,
    formatDateTime,
  } = useTotpEnrollment({
    setSnackbar,
    openStepUpFor,
  })

  const {
    credentials: webauthnCredentials,
    credentialsLoading: webauthnFetching,
    busy: webauthnBusy,
    label: webauthnLabel,
    isAdding: isAddingWebAuthn,
    setIsAdding: setIsAddingWebAuthn,
    supported: webauthnSupported,
    setLabel: setWebauthnLabel,
    handleRegister: handleRegisterWebAuthn,
    handleDelete: handleDeleteWebAuthn,
  } = useWebAuthn({
    setSnackbar,
    tabActive: tab === 1,
    openStepUpFor,
  })

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

  const avatarUrl = user?.avatar_url ?? undefined
  const coverUrl = user?.cover_url ?? undefined



  const handleChallengeResetNotice = useCallback(() => {
    setSnackbar({ text: t("settings:security.snackbar.challengeReset"), severity: "info" })
  }, [setSnackbar, t])

  const [confirmLogout, setConfirmLogout] = useState(false)

  return (
    <Layout>
      <PageFadeIn>
        <div className="flex h-full w-full flex-col bg-(--bg-page) text-(--text-primary) sm:h-[640px] sm:max-h-[85vh] sm:flex-row">
          <div className="px-2 md:px-4">
            <div
              data-fade
              style={fadeDelayStyle("80ms")}
              className="mb-8 flex flex-wrap items-center gap-4 sm:gap-5"
            >
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-brand-subtle-bg text-brand shadow-premium transition-transform duration-200 hover:scale-105 backdrop-blur-sm [-webkit-backdrop-filter:blur(12px)]">
                <SettingsIcon className="h-6 w-6" />
              </div>
              <h1 className="text-[clamp(1.6rem,5vw,2.75rem)] font-bold tracking-tight text-(--text-primary)">
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
                          <span className="flex items-center gap-2 text-[color-mix(in_srgb,var(--text-primary)_82%,var(--text-secondary)_18%)]">
                            <Monitor className="h-5 w-5" />
                            <span>{t("settings:appearance.theme.options.system")}</span>
                          </span>
                        }
                      />
                      <FormControlLabel
                        value="light"
                        control={<Radio data-testid="theme-option-light" />}
                        label={
                          <span className="flex items-center gap-2 text-[color-mix(in_srgb,var(--text-primary)_82%,var(--text-secondary)_18%)]">
                            <Sun className="h-5 w-5" />
                            <span>{t("settings:appearance.theme.options.light")}</span>
                          </span>
                        }
                      />
                      <FormControlLabel
                        value="dark"
                        control={<Radio data-testid="theme-option-dark" />}
                        label={
                          <span className="flex items-center gap-2 text-[color-mix(in_srgb,var(--text-primary)_82%,var(--text-secondary)_18%)]">
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
                            <span className="text-[color-mix(in_srgb,var(--text-primary)_84%,var(--text-secondary)_16%)]">
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
                                  : "var(--bg-surface-hover)",
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
                              disabled={revokeAllSessionsBusy}
                              onClick={() => void handleRevokeAllSessions()}
                              startIcon={
                                revokeAllSessionsBusy ? (
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
                              <p className="text-sm font-semibold text-[color-mix(in_srgb,var(--text-primary)_84%,var(--text-secondary)_16%)]">
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
                                  session.is_current || isRevoked || revokeSessionBusy

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
                                            ? "text-[color-mix(in_srgb,var(--text-primary)_68%,white_32%)]"
                                            : "text-[color-mix(in_srgb,var(--text-primary)_90%,var(--text-secondary)_10%)]"
                                        )}
                                      >
                                        {session.user_agent || t("settings:sessions.unknownDevice")}
                                      </p>
                                      <p
                                        className={cn(
                                          "text-xs transition-colors",
                                          isRevoked
                                            ? "italic text-[color-mix(in_srgb,var(--text-primary)_64%,white_36%)]"
                                            : "text-[color-mix(in_srgb,var(--text-primary)_78%,var(--text-secondary)_22%)]"
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
                                          disabled={revokeSessionBusy}
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
                            <div className="text-xs font-bold text-(--text-secondary) uppercase tracking-widest opacity-60">
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
                                      "bg-[color-mix(in_srgb,var(--bg-surface)_96%,var(--primary-main)_4%)]",
                                      "dark:border-white/10",
                                      "dark:bg-[color-mix(in_srgb,var(--bg-surface)_90%,var(--bg-page)_10%)]"
                                    )}
                                  >
                                    <div className="flex min-w-0 flex-col gap-1">
                                      <p className="font-semibold text-[color-mix(in_srgb,var(--text-primary)_90%,var(--primary-main)_10%)]">
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
                                    "bg-[color-mix(in_srgb,var(--bg-surface)_96%,var(--primary-main)_4%)]",
                                    "dark:border-white/10",
                                    "dark:bg-[color-mix(in_srgb,var(--bg-surface)_90%,var(--bg-page)_10%)]"
                                  )}
                                >
                                  <div className="flex min-w-0 items-center gap-3">
                                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[color-mix(in_srgb,var(--primary-main)_10%,transparent)] text-(--primary-main)">
                                      <Fingerprint className="h-5 w-5" />
                                    </div>
                                    <div className="flex min-w-0 flex-col gap-0.5">
                                      <p className="font-semibold text-[color-mix(in_srgb,var(--text-primary)_90%,var(--primary-main)_10%)]">
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
                  <SpotifySection
                    setSnackbar={setSnackbar}
                    connected={spotifyConnected}
                    displayName={spotifyName}
                    onConnect={connectSpotify}
                    onDisconnect={disconnectSpotify}
                  />
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






