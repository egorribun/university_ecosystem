import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { X, Bell, BellOff, Download, RefreshCw, AlertTriangle, CheckCircle2 } from "lucide-react"
import { usePushPreferences, type NotificationToast } from "@/hooks/usePushPreferences"
import { PWA_REFRESH_EVENT, type ServiceWorkerUpdateEventDetail } from "../app/pwaEvents"
import { Trans, useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"
import { Button, SwitchControl } from "@/components/settings/SettingsUI"

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
  const { t } = useTranslation(["system", "navigation", "notifications", "common"])
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

  return (
    <>
      <AnimatePresence>
        {shouldRenderPrompt && (
          <motion.div
            initial={{ opacity: 0, y: 50, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 50, scale: 0.95 }}
            className="fixed bottom-24 right-4 left-4 sm:left-auto sm:right-6 z-(--z-toast) w-auto max-w-sm"
          >
            <div className="bg-(--bg-surface)/(--opacity-heavy) backdrop-blur-2xl rounded-lg border border-glass-border shadow-2xl overflow-hidden ring-1 ring-black/(--opacity-faint) p-6">
              <div
                className={cn(
                  "flex flex-col",
                  showInstallPanel && showPushPanel ? "gap-6" : "gap-4"
                )}
              >
                {showInstallPanel && (
                  <div className="space-y-4">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex items-center gap-3">
                        <div className="p-2.5 rounded-2xl bg-brand/(--opacity-subtle) text-brand">
                          <Download className="h-5 w-5" />
                        </div>
                        <h3 className="text-lg font-black tracking-tight text-(--text-primary) sf-pro">
                          {t("system:installPrompt.installTitle", { appName })}
                        </h3>
                      </div>
                      <button
                        onClick={handleInstallDismiss}
                        aria-label={t("system:installPrompt.closeOffer")}
                        className="p-1.5 rounded-xl hover:bg-(--bg-surface-hover)/(--opacity-soft) text-(--text-secondary) transition-colors"
                      >
                        <X className="h-5 w-5" />
                      </button>
                    </div>
                    <p className="text-sm font-medium text-(--text-secondary) leading-relaxed opacity-(--opacity-hover)">
                      {t("system:installPrompt.description")}
                    </p>
                    <div className="flex gap-2 pt-2">
                      <Button
                        variant="solid"
                        onClick={handleInstall}
                        disabled={!deferredPrompt || installing}
                        className="flex-1 h-12 rounded-2xl font-black shadow-lg shadow-brand/(--opacity-dim)"
                        loading={installing}
                      >
                        {t("system:installPrompt.install")}
                      </Button>
                      <Button
                        variant="ghost"
                        onClick={handleInstallDismiss}
                        className="h-12 rounded-2xl font-black px-6"
                      >
                        {t("system:installPrompt.later")}
                      </Button>
                    </div>
                  </div>
                )}

                {showInstallPanel && showPushPanel && (
                  <div className="h-px bg-glass-border/(--opacity-subtle)" />
                )}

                {showPushPanel && (
                  <div className="space-y-4">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex items-center gap-3">
                        <div className="p-2.5 rounded-2xl bg-brand/(--opacity-subtle) text-brand">
                          <Bell className="h-5 w-5" />
                        </div>
                        <h3 className="text-lg font-black tracking-tight text-(--text-primary) sf-pro">
                          {t("system:installPrompt.notificationsTitle")}
                        </h3>
                      </div>
                      <button
                        onClick={handlePushDismiss}
                        aria-label={t("system:installPrompt.notificationsClose")}
                        className="p-1.5 rounded-xl hover:bg-(--bg-surface-hover)/(--opacity-soft) text-(--text-secondary) transition-colors"
                      >
                        <X className="h-5 w-5" />
                      </button>
                    </div>

                    <p className="text-sm font-medium text-(--text-secondary) leading-relaxed opacity-(--opacity-hover)">
                      {t("system:installPrompt.manageNotifications")}
                    </p>

                    {!pushSupported ? (
                      <div className="p-4 rounded-2xl bg-warning-bg/(--opacity-dim) border border-warning-border/(--opacity-soft) text-warning-text text-xs font-bold flex gap-3">
                        <AlertTriangle className="h-4 w-4 shrink-0" />
                        {t("system:installPrompt.unsupported")}
                      </div>
                    ) : notificationPermission === "denied" ? (
                      <div className="space-y-3">
                        <div className="p-4 rounded-2xl bg-error-bg/(--opacity-dim) border border-error-border/(--opacity-soft) text-error-text text-xs font-bold flex gap-3">
                          <BellOff className="h-4 w-4 shrink-0" />
                          {t("system:installPrompt.blocked", { appName })}
                        </div>
                        {safariIOS && (
                          <div className="p-4 rounded-2xl bg-info-bg/(--opacity-dim) border border-info-border/(--opacity-soft) text-info-text text-xs font-bold">
                            <Trans
                              i18nKey="system:installPrompt.safariGuide"
                              components={{
                                link: (
                                  <a
                                    href={safariGuideUrl}
                                    target="_blank"
                                    rel="noreferrer noopener"
                                    className="underline font-black"
                                  >
                                    {t("navigation:safariGuide")}
                                  </a>
                                ),
                              }}
                            />
                          </div>
                        )}
                        <div className="flex items-center gap-3">
                          <Button
                            variant="solid"
                            size="sm"
                            onClick={() => void enableNotifications()}
                            disabled={pushBusy}
                            className="rounded-xl font-black h-10 px-4"
                          >
                            {t("system:installPrompt.check")}
                          </Button>
                          <span className="text-label-md font-bold text-(--text-secondary) uppercase tracking-wider opacity-(--opacity-medium)">
                            {t("system:installPrompt.status", { status: permissionText })}
                          </span>
                        </div>
                      </div>
                    ) : notificationPermission === "default" ? (
                      <div className="space-y-4">
                        <p className="text-xs font-bold text-(--text-secondary) opacity-(--opacity-medium) leading-relaxed px-1">
                          {t("system:installPrompt.defaultPermissionDescription")}
                        </p>
                        <div className="flex items-center gap-3">
                          <Button
                            variant="solid"
                            size="sm"
                            onClick={() => void enableNotifications()}
                            disabled={pushBusy || pushInitializing}
                            className="rounded-xl font-black h-10 px-6 shadow-lg shadow-brand/(--opacity-dim)"
                          >
                            {t("system:installPrompt.allow")}
                          </Button>
                          <span className="text-label-md font-bold text-(--text-secondary) uppercase tracking-wider opacity-(--opacity-medium)">
                            {t("system:installPrompt.status", { status: permissionText })}
                          </span>
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-4 pt-2">
                        <div className="rounded-2xl border border-glass-border/(--opacity-subtle) bg-(--bg-surface-raised)/(--opacity-soft) p-4 space-y-4">
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-bold text-(--text-primary)">
                              {t("system:installPrompt.toggleLabel")}
                            </span>
                            <SwitchControl
                              checked={notificationsEnabled}
                              onChange={() =>
                                notificationsEnabled
                                  ? disableNotifications()
                                  : enableNotifications()
                              }
                              disabled={pushBusy || pushInitializing}
                            />
                          </div>
                          <div className="h-px bg-glass-border/(--opacity-subtle)" />
                          {topicKeys.map((key) => (
                            <div key={key} className="flex items-center justify-between">
                              <span className="text-xs font-bold text-(--text-secondary)">
                                {t(`notifications:topics.${key}`)}
                              </span>
                              <SwitchControl
                                checked={topicState[key]}
                                onChange={handleTopicToggle(key)}
                                disabled={!notificationsEnabled || pushBusy || pushInitializing}
                              />
                            </div>
                          ))}
                        </div>
                        <p className="text-label-md font-bold text-(--text-secondary) opacity-(--opacity-dim) uppercase tracking-widest px-1">
                          {t("system:installPrompt.browserPermission", { status: permissionText })}
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {feedback && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: -20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: -20 }}
            className="fixed top-24 left-1/2 -translate-x-1/2 z-(--z-toast) w-full max-w-sm px-6"
          >
            <div
              className={cn(
                "flex items-center gap-3 p-4 rounded-2xl border backdrop-blur-2xl shadow-2xl",
                feedback.severity === "error"
                  ? "bg-error-bg/(--opacity-dim) border-error-border/(--opacity-soft) text-error-text"
                  : feedback.severity === "success"
                    ? "bg-success-bg/(--opacity-dim) border-success-border/(--opacity-soft) text-success-text"
                    : "bg-brand/(--opacity-subtle) border-brand/(--opacity-dim) text-brand"
              )}
            >
              {feedback.severity === "error" ? (
                <AlertTriangle className="h-5 w-5" />
              ) : (
                <CheckCircle2 className="h-5 w-5" />
              )}
              <p className="text-sm font-black tracking-tight flex-1">{feedback.text}</p>
              <button onClick={handleFeedbackClose}>
                <X className="h-4 w-4" />
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {updateToastOpen && (
          <motion.div
            initial={{ opacity: 0, y: 50 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 50 }}
            className="fixed bottom-24 left-1/2 -translate-x-1/2 z-(--z-toast) w-full max-w-md px-6"
          >
            <div className="flex items-center gap-4 p-4 rounded-2xl border border-brand/(--opacity-dim) bg-brand/(--opacity-faint) backdrop-blur-2xl shadow-2xl text-brand">
              <RefreshCw className="h-6 w-6 animate-spin-slow" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-black tracking-tight">
                  {t("system:installPrompt.updateAvailable")}
                </p>
              </div>
              <Button
                variant="solid"
                size="sm"
                onClick={handleUpdateReload}
                className="rounded-xl px-4 h-9 font-black shadow-lg shadow-brand/(--opacity-dim)"
              >
                {t("system:installPrompt.reload")}
              </Button>
              <button
                onClick={handleCloseUpdateToast}
                className="p-1 hover:bg-brand/(--opacity-subtle) rounded-lg transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
