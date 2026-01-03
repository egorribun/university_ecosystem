import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import type { ChangeEvent } from "react"
import CloseIcon from "@mui/icons-material/Close"
import NotificationsActiveIcon from "@mui/icons-material/NotificationsActive"
import NotificationsOffIcon from "@mui/icons-material/NotificationsOff"
import {
  Alert,
  Button,
  Divider,
  FormControl,
  FormControlLabel,
  FormGroup,
  FormHelperText,
  IconButton,
  Link,
  Paper,
  Slide,
  Snackbar,
  Stack,
  Switch,
  Typography,
} from "@mui/material"
import { usePushPreferences, type NotificationToast } from "@/hooks/usePushPreferences"
import { PWA_REFRESH_EVENT, type ServiceWorkerUpdateEventDetail } from "../app/pwaEvents"
import { Trans, useTranslation } from "react-i18next"

interface BeforeInstallPromptEvent extends Event {
  readonly platforms?: string[]
  readonly userChoice: Promise<{ outcome: "accepted" | "dismissed" }>
  prompt: () => Promise<void>
}

type NavigatorStandalone = Navigator & { standalone?: boolean }

const DISMISS_TTL = 1000 * 60 * 60 * 24 * 7
const PWA_DISMISS_STORAGE_KEY = "ecosystem.pwa.install.dismissedAt"
const PUSH_DISMISS_STORAGE_KEY = "ecosystem.push.education.dismissedAt"

const isStandalone = () => {
  if (typeof window === "undefined") return false
  const navigatorWithStandalone = window.navigator as NavigatorStandalone
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    window.matchMedia("(display-mode: minimal-ui)").matches ||
    navigatorWithStandalone.standalone === true
  )
}

const readDismissedAt = (key: string) => {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return 0
    const parsed = Number(raw)
    return Number.isFinite(parsed) ? parsed : 0
  } catch {
    return 0
  }
}

const rememberDismiss = (key: string) => {
  try {
    localStorage.setItem(key, String(Date.now()))
  } catch {
    /* ignore */
  }
}

const clearDismissed = (key: string) => {
  try {
    localStorage.removeItem(key)
  } catch {
    /* ignore */
  }
}

export default function InstallPrompt() {
  const { t } = useTranslation(["system", "navigation", "notifications"])
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null)
  const [installVisible, setInstallVisible] = useState(false)
  const [pushVisible, setPushVisible] = useState(false)
  const [installing, setInstalling] = useState(false)
  const [updateToastOpen, setUpdateToastOpen] = useState(false)
  const [feedback, setFeedback] = useState<NotificationToast | null>(null)
  const installSuppressUntilRef = useRef<number>(0)
  const pushSuppressUntilRef = useRef<number>(0)
  const pendingUpdateRef = useRef<ServiceWorkerUpdateEventDetail["update"] | null>(null)

  const isEligible = useMemo(() => !isStandalone(), [])
  const appName = t("navigation:brandName")

  const {
    topicKeys,
    topicState,
    pushSupported,
    notificationPermission,
    notificationsEnabled,
    pushBusy,
    pushInitializing,
    permissionText,
    selectedTopicsDescription,
    enableNotifications,
    disableNotifications,
    handleTopicToggle,
    safariIOS,
    safariGuideUrl,
  } = usePushPreferences({ onNotify: setFeedback })

  useEffect(() => {
    const handleServiceWorkerUpdate = (event: Event) => {
      const customEvent = event as CustomEvent<ServiceWorkerUpdateEventDetail>
      pendingUpdateRef.current = customEvent.detail.update
      setUpdateToastOpen(true)
    }

    window.addEventListener(PWA_REFRESH_EVENT, handleServiceWorkerUpdate)

    return () => {
      window.removeEventListener(PWA_REFRESH_EVENT, handleServiceWorkerUpdate)
    }
  }, [])

  useEffect(() => {
    if (!isEligible) return

    installSuppressUntilRef.current = readDismissedAt(PWA_DISMISS_STORAGE_KEY) + DISMISS_TTL

    const handleBeforeInstallPrompt = (event: Event) => {
      const now = Date.now()
      if (installSuppressUntilRef.current && now < installSuppressUntilRef.current) {
        return
      }

      event.preventDefault()
      setDeferredPrompt(event as BeforeInstallPromptEvent)
      setInstallVisible(true)
    }

    window.addEventListener("beforeinstallprompt", handleBeforeInstallPrompt)

    return () => {
      window.removeEventListener("beforeinstallprompt", handleBeforeInstallPrompt)
    }
  }, [isEligible])

  useEffect(() => {
    if (!isEligible) return

    const onAppInstalled = () => {
      clearDismissed(PWA_DISMISS_STORAGE_KEY)
      setInstallVisible(false)
      setDeferredPrompt(null)
    }

    window.addEventListener("appinstalled", onAppInstalled)
    return () => window.removeEventListener("appinstalled", onAppInstalled)
  }, [isEligible])

  useEffect(() => {
    if (!pushSuppressUntilRef.current) {
      pushSuppressUntilRef.current = readDismissedAt(PUSH_DISMISS_STORAGE_KEY) + DISMISS_TTL
    }

    if (pushSupported && notificationPermission === "granted") {
      setPushVisible(false)
      return
    }

    const now = Date.now()
    if (pushSuppressUntilRef.current && now < pushSuppressUntilRef.current) return
    setPushVisible(true)
  }, [notificationPermission, pushSupported])

  const handleInstall = useCallback(async () => {
    if (!deferredPrompt) return
    setInstalling(true)
    try {
      await deferredPrompt.prompt()
      const choice = await deferredPrompt.userChoice
      if (choice.outcome === "accepted") {
        clearDismissed(PWA_DISMISS_STORAGE_KEY)
        setInstallVisible(false)
        setDeferredPrompt(null)
      } else {
        installSuppressUntilRef.current = Date.now() + DISMISS_TTL
        rememberDismiss(PWA_DISMISS_STORAGE_KEY)
        setInstallVisible(false)
        setDeferredPrompt(null)
      }
    } catch {
      installSuppressUntilRef.current = Date.now() + DISMISS_TTL
      rememberDismiss(PWA_DISMISS_STORAGE_KEY)
      setInstallVisible(false)
      setDeferredPrompt(null)
    } finally {
      setInstalling(false)
    }
  }, [deferredPrompt])

  const handleNotificationsToggle = useCallback(
    (_: ChangeEvent<HTMLInputElement>, checked: boolean) => {
      if (pushBusy || pushInitializing) return
      if (checked) void enableNotifications()
      else void disableNotifications()
    },
    [disableNotifications, enableNotifications, pushBusy, pushInitializing]
  )

  const handleInstallDismiss = useCallback(() => {
    installSuppressUntilRef.current = Date.now() + DISMISS_TTL
    rememberDismiss(PWA_DISMISS_STORAGE_KEY)
    setInstallVisible(false)
    setDeferredPrompt(null)
  }, [])

  const handlePushDismiss = useCallback(() => {
    pushSuppressUntilRef.current = Date.now() + DISMISS_TTL
    rememberDismiss(PUSH_DISMISS_STORAGE_KEY)
    setPushVisible(false)
  }, [])

  const handleFeedbackClose = useCallback(() => {
    setFeedback(null)
  }, [])

  const handleUpdateReload = useCallback(() => {
    const update = pendingUpdateRef.current
    if (!update) return
    setUpdateToastOpen(false)
    void update()
  }, [])

  const handleCloseUpdateToast = useCallback(() => {
    setUpdateToastOpen(false)
  }, [])

  const showInstallPanel = installVisible && Boolean(deferredPrompt)
  const showPushPanel = pushVisible
  const shouldRenderPrompt = showInstallPanel || showPushPanel

  if (!shouldRenderPrompt && !updateToastOpen && !feedback) return null

  return (
    <>
      <Slide direction="up" in={shouldRenderPrompt} mountOnEnter unmountOnExit>
        <Paper
          elevation={8}
          role="dialog"
          aria-live="polite"
          sx={{
            position: "fixed",
            bottom: { xs: 16, sm: 24 },
            right: { xs: 12, sm: 24 },
            left: { xs: 12, sm: "auto" },
            zIndex: (theme) => theme.zIndex.snackbar,
            maxWidth: 360,
            borderRadius: 3,
            p: 2.5,
            boxShadow: (theme) =>
              theme.palette.mode === "dark"
                ? "0px 18px 45px rgba(11, 15, 22, 0.6)"
                : "0px 18px 45px rgba(11, 99, 244, 0.16)",
          }}
        >
          <Stack spacing={showInstallPanel && showPushPanel ? 2.5 : 1.5} alignItems="flex-start">
            {showInstallPanel && (
              <Stack spacing={2} sx={{ width: "100%" }}>
                <Stack direction="row" spacing={1.5} alignItems="flex-start" sx={{ width: "100%" }}>
                  <Typography component="h2" variant="h6" sx={{ flex: 1, fontWeight: 700 }}>
                    {t("system:installPrompt.installTitle", { appName })}
                  </Typography>
                  <IconButton
                    aria-label={t("system:installPrompt.closeOffer")}
                    onClick={handleInstallDismiss}
                    size="small"
                  >
                    <CloseIcon fontSize="small" />
                  </IconButton>
                </Stack>
                <Typography variant="body2" sx={{ opacity: 0.85 }}>
                  {t("system:installPrompt.description")}
                </Typography>
                <Stack direction="row" spacing={1.5} sx={{ width: "100%" }}>
                  <Button
                    variant="contained"
                    color="primary"
                    onClick={handleInstall}
                    disabled={!deferredPrompt || installing}
                    sx={{ flexGrow: 1 }}
                  >
                    {t("system:installPrompt.install")}
                  </Button>
                  <Button variant="text" color="inherit" onClick={handleInstallDismiss}>
                    {t("system:installPrompt.later")}
                  </Button>
                </Stack>
              </Stack>
            )}
            {showInstallPanel && showPushPanel && <Divider sx={{ width: "100%" }} />}
            {showPushPanel && (
              <Stack spacing={1.2} sx={{ width: "100%" }}>
                <Stack direction="row" spacing={1.5} alignItems="flex-start" sx={{ width: "100%" }}>
                  <Typography component="h2" variant="h6" sx={{ flex: 1, fontWeight: 700 }}>
                    {t("system:installPrompt.notificationsTitle")}
                  </Typography>
                  <IconButton
                    aria-label={t("system:installPrompt.notificationsClose")}
                    onClick={handlePushDismiss}
                    size="small"
                  >
                    <CloseIcon fontSize="small" />
                  </IconButton>
                </Stack>
                <Typography variant="body2" sx={{ opacity: 0.85 }}>
                  {t("system:installPrompt.manageNotifications")}
                </Typography>
                {!pushSupported ? (
                  <Alert severity="warning" variant="outlined">
                    {t("system:installPrompt.unsupported")}
                  </Alert>
                ) : notificationPermission === "denied" ? (
                  <Stack spacing={1}>
                    <Alert severity="error" variant="outlined">
                      {t("system:installPrompt.blocked", { appName })}
                    </Alert>
                    {safariIOS && (
                      <Alert severity="info" variant="outlined">
                        <Trans
                          i18nKey="system:installPrompt.safariGuide"
                          components={{
                            link: (
                              <Link
                                href={safariGuideUrl}
                                target="_blank"
                                rel="noreferrer noopener"
                              />
                            ),
                          }}
                        />
                      </Alert>
                    )}
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Button
                        variant="contained"
                        size="small"
                        onClick={() => void enableNotifications()}
                        disabled={pushBusy}
                      >
                        {t("system:installPrompt.check")}
                      </Button>
                      <Typography variant="caption" sx={{ color: "var(--page-text)" }}>
                        {t("system:installPrompt.status", { status: permissionText })}
                      </Typography>
                    </Stack>
                  </Stack>
                ) : notificationPermission === "default" ? (
                  <Stack spacing={1}>
                    <Typography variant="body2" sx={{ color: "var(--page-text)" }}>
                      {t("system:installPrompt.defaultPermissionDescription")}
                    </Typography>
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Button
                        variant="contained"
                        size="small"
                        onClick={() => void enableNotifications()}
                        disabled={pushBusy || pushInitializing}
                      >
                        {t("system:installPrompt.allow")}
                      </Button>
                      <Typography variant="caption" sx={{ color: "var(--page-text)" }}>
                        {t("system:installPrompt.status", { status: permissionText })}
                      </Typography>
                    </Stack>
                    {safariIOS && (
                      <Alert severity="info" variant="outlined">
                        <Trans
                          i18nKey="system:installPrompt.safariGuide"
                          components={{
                            link: (
                              <Link
                                href={safariGuideUrl}
                                target="_blank"
                                rel="noreferrer noopener"
                              />
                            ),
                          }}
                        />
                      </Alert>
                    )}
                  </Stack>
                ) : (
                  <Stack spacing={1.5}>
                    <FormControl component="fieldset" variant="standard">
                      <FormGroup>
                        <FormControlLabel
                          control={
                            <Switch
                              checked={notificationsEnabled}
                              onChange={handleNotificationsToggle}
                              disabled={pushBusy || pushInitializing}
                            />
                          }
                          label={
                            <Stack
                              direction="row"
                              spacing={1}
                              alignItems="center"
                              sx={{ color: "var(--page-text)" }}
                            >
                              {notificationsEnabled ? (
                                <NotificationsActiveIcon fontSize="small" />
                              ) : (
                                <NotificationsOffIcon fontSize="small" />
                              )}
                              <span>{t("system:installPrompt.toggleLabel")}</span>
                            </Stack>
                          }
                        />
                      </FormGroup>
                      <FormHelperText sx={{ ml: 0, color: "var(--page-text)", mt: 0.5 }}>
                        {t("system:installPrompt.browserPermission", { status: permissionText })}
                      </FormHelperText>
                    </FormControl>
                    <FormControl
                      component="fieldset"
                      variant="standard"
                      disabled={!notificationsEnabled || pushBusy || pushInitializing}
                      sx={{ opacity: notificationsEnabled ? 1 : 0.6 }}
                    >
                      <FormGroup>
                        {topicKeys.map((key) => (
                          <FormControlLabel
                            key={key}
                            control={
                              <Switch
                                checked={topicState[key]}
                                onChange={handleTopicToggle(key)}
                                disabled={!notificationsEnabled || pushBusy || pushInitializing}
                              />
                            }
                            label={
                              <span style={{ color: "var(--page-text)" }}>
                                {t(`notifications:topics.${key}`)}
                              </span>
                            }
                          />
                        ))}
                      </FormGroup>
                      <FormHelperText sx={{ ml: 0, color: "var(--page-text)", mt: 0.5 }}>
                        {t("system:installPrompt.activeTopics", {
                          topics: selectedTopicsDescription,
                        })}
                      </FormHelperText>
                    </FormControl>
                  </Stack>
                )}
              </Stack>
            )}
          </Stack>
        </Paper>
      </Slide>
      <Snackbar
        open={Boolean(feedback)}
        autoHideDuration={4000}
        onClose={handleFeedbackClose}
        anchorOrigin={{ vertical: "top", horizontal: "center" }}
      >
        <Alert
          severity={feedback?.sev ?? "info"}
          variant="filled"
          onClose={handleFeedbackClose}
          sx={{ alignItems: "center" }}
        >
          {feedback?.text}
        </Alert>
      </Snackbar>
      <Snackbar
        open={updateToastOpen}
        onClose={handleCloseUpdateToast}
        autoHideDuration={null}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert
          severity="info"
          variant="filled"
          sx={{ alignItems: "center", gap: 1 }}
          action={
            <Button color="inherit" size="small" onClick={handleUpdateReload}>
              {t("system:installPrompt.reload")}
            </Button>
          }
        >
          {t("system:installPrompt.updateAvailable")}
        </Alert>
      </Snackbar>
    </>
  )
}
