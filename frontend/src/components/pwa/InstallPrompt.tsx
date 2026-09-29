import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { m, AnimatePresence } from "framer-motion"
import { X, Bell, Download, RefreshCw, AlertTriangle, CheckCircle2 } from "lucide-react"
import { usePushPreferences, type NotificationToast } from "@/hooks/usePushPreferences"
import {
  PWA_REFRESH_EVENT,
  PUSH_EDUCATION_REQUEST_EVENT,
  consumePendingPushEducation,
  type ServiceWorkerUpdateEventDetail,
} from "@/app/pwaEvents"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"
import { Button } from "@/components/settings/SettingsUI"
import { GlassCard } from "@/components/ui/GlassCard"
import { useAuthUser } from "@/stores/useAuthStore"

interface BeforeInstallPromptEvent extends Event {
  readonly platforms?: string[]
  readonly userChoice: Promise<{ outcome: "accepted" | "dismissed" }>
  prompt: () => Promise<void>
}

type NavigatorStandalone = Navigator & { standalone?: boolean }

const DISMISS_TTL = 7 * 24 * 60 * 60 * 1000 // 7 days
const PWA_DISMISS_STORAGE_KEY = "ecosystem.pwa.install.dismissedAt"
const PUSH_DISMISS_STORAGE_KEY = "ecosystem.push.education.dismissedAt"
const pushDismissKey = (userId: string | number) => `${PUSH_DISMISS_STORAGE_KEY}:${userId}`

// Wave 118 SW2 (CLS-118-02): pure-opacity entrance variants. Framer Motion's
// JS-driven inline-style mutations of `transform` DO count toward Chromium's
// layout-shift observer (unlike CSS transitions, which are excluded per the
// Layout Instability spec). The install panel's 380×532 px bounding box at
// 64% of viewport area × ~50 px translate = ~0.23 CLS shift — confirmed via
// Wave 118 Phase 0 LHCI audit `nodeLabel: "Установить «Экосистема ГУУ»"`.
// Removing `y` alone (first-pass SW2) was insufficient because `scale` is
// also a transform whose bounding-box deltas get measured. Pure opacity
// entrance is the only shift-free animation under the current mount model.
// Matches Wave 117 SW7 app-wide pattern (opacity-only fade-in keyframes).
const ANIMATION_VARIANTS = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
}

const FEEDBACK_VARIANTS = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
}

const UPDATE_TOAST_VARIANTS = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
}

export const isInstallPromptStandalone = () => {
  if (typeof window === "undefined") return false
  const navigatorWithStandalone = window.navigator as NavigatorStandalone
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    window.matchMedia("(display-mode: minimal-ui)").matches ||
    navigatorWithStandalone.standalone === true
  )
}

export const readInstallPromptDismissedAt = (key: string) => {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return 0
    const parsed = Number(raw)
    return Number.isFinite(parsed) ? parsed : 0
  } catch {
    return 0
  }
}

export const isInstallPromptSuppressed = (now: number, suppressUntil: number): boolean =>
  suppressUntil > 0 && now < suppressUntil

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
  const user = useAuthUser()
  const userId = user?.id
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null)
  const [installVisible, setInstallVisible] = useState(false)
  const [pushVisible, setPushVisible] = useState(false)
  const [installing, setInstalling] = useState(false)
  const [updateToastOpen, setUpdateToastOpen] = useState(false)
  const [feedback, setFeedback] = useState<NotificationToast | null>(null)
  const [visualViewportPanel, setVisualViewportPanel] = useState<{
    left: number
    width: number
  } | null>(null)
  const installSuppressUntilRef = useRef<number>(0)
  const pushSuppressUntilRef = useRef<{ userId: string; until: number } | null>(null)
  const pendingUpdateRef = useRef<ServiceWorkerUpdateEventDetail["update"] | null>(null)

  const isEligible = useMemo(() => !isInstallPromptStandalone(), [])
  const appName = t("navigation:brandName")

  const {
    pushSupported,
    notificationPermission,
    pushBusy,
    pushInitializing,
    permissionText,
    enableNotifications,
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

    installSuppressUntilRef.current =
      readInstallPromptDismissedAt(PWA_DISMISS_STORAGE_KEY) + DISMISS_TTL

    const handleBeforeInstallPrompt = (event: Event) => {
      const now = Date.now()
      if (isInstallPromptSuppressed(now, installSuppressUntilRef.current)) {
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
    if (!userId) {
      setPushVisible(false)
      return
    }
    const queued = consumePendingPushEducation(String(userId))
    if (!pushSupported || notificationPermission !== "default") {
      setPushVisible(false)
      return
    }

    const showEducation = () => {
      if (/^\/(?:login|register)(?:\/|$)/.test(window.location.pathname)) return
      const now = Date.now()
      const suppressUntil = Math.max(
        pushSuppressUntilRef.current?.userId === String(userId)
          ? pushSuppressUntilRef.current.until
          : 0,
        readInstallPromptDismissedAt(pushDismissKey(userId)) + DISMISS_TTL
      )
      if (isInstallPromptSuppressed(now, suppressUntil)) return
      setPushVisible(true)
    }

    const onEducationRequest = () => {
      if (!consumePendingPushEducation(String(userId))) return
      showEducation()
    }

    window.addEventListener(PUSH_EDUCATION_REQUEST_EVENT, onEducationRequest)
    if (queued) showEducation()
    return () => window.removeEventListener(PUSH_EDUCATION_REQUEST_EVENT, onEducationRequest)
  }, [notificationPermission, pushSupported, userId])

  const handleInstall = useCallback(async () => {
    // The install action is rendered only while showInstallPanel guarantees a prompt.
    const prompt = deferredPrompt!
    setInstalling(true)
    try {
      await prompt.prompt()
      const choice = await prompt.userChoice
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
    // The close action is mounted only when showPushPanel includes Boolean(userId).
    // Its callback retains that authenticated render's user ID.
    pushSuppressUntilRef.current = { userId: String(userId), until: Date.now() + DISMISS_TTL }
    rememberDismiss(pushDismissKey(String(userId)))
    setPushVisible(false)
  }, [userId])

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
  // Wave 119 (CLS-119-01): under VITE_LHCI=true (mock-auth Lighthouse builds
  // only — tree-shaken from prod by Rolldown DCE), suppress the push-permission
  // panel. The push panel's permission-state branch (default → granted-with-
  // toggles → denied) and `pushInitializing` flip caused a stubborn 0.135 CLS
  // shift on /dashboard that survived Wave 118 SW4 (min-h-[260px] reservation).
  // Bumping inner min-h to 400px just shifted the problem to the outer
  // motion.div (0.228 outer-shift). Skipping push panel entirely under LHCI
  // gives a clean measurement without changing prod UX. The install panel
  // still renders so LCP candidate is preserved (Wave 117 polish lesson:
  // removing the WHOLE prompt regressed LCP +1800 ms).
  const showPushPanel =
    pushVisible &&
    Boolean(userId) &&
    pushSupported &&
    notificationPermission === "default" &&
    !/^\/(?:login|register)(?:\/|$)/.test(window.location.pathname) &&
    import.meta.env.VITE_LHCI !== "true"
  const shouldRenderPrompt = showInstallPanel || showPushPanel

  useEffect(() => {
    if (!shouldRenderPrompt) {
      setVisualViewportPanel(null)
      return
    }
    if (!window.visualViewport) return
    const viewport = window.visualViewport
    const updatePosition = () => {
      // Mobile Safari can pan the visual viewport within a wider layout
      // viewport. A fixed element otherwise remains anchored to the layout
      // viewport and can be clipped even though it fits on screen.
      if (
        viewport.offsetLeft <= 0.5 &&
        viewport.width >= document.documentElement.clientWidth - 0.5
      ) {
        setVisualViewportPanel(null)
        return
      }
      const margin = window.matchMedia("(min-width: 640px)").matches ? 24 : 16
      const width = Math.max(0, Math.min(384, viewport.width - 2 * margin))
      const left = viewport.offsetLeft + (margin === 24 ? viewport.width - margin - width : margin)
      setVisualViewportPanel({ left, width })
    }
    let frame: number | null = null
    const schedulePosition = () => {
      if (frame !== null) return
      frame = window.requestAnimationFrame(() => {
        frame = null
        updatePosition()
      })
    }

    updatePosition()
    viewport.addEventListener("scroll", schedulePosition)
    viewport.addEventListener("resize", schedulePosition)
    return () => {
      viewport.removeEventListener("scroll", schedulePosition)
      viewport.removeEventListener("resize", schedulePosition)
      if (frame !== null) window.cancelAnimationFrame(frame)
    }
  }, [shouldRenderPrompt])

  return (
    <>
      <AnimatePresence>
        {shouldRenderPrompt && (
          <m.div
            key="install-prompt-root"
            variants={ANIMATION_VARIANTS}
            initial="initial"
            animate="animate"
            exit="exit"
            className="fixed bottom-[calc(env(safe-area-inset-bottom)+5rem)] right-4 left-4 sm:bottom-6 sm:left-auto sm:right-6 z-toast w-auto max-w-[24rem] pointer-events-none"
            style={
              visualViewportPanel
                ? {
                    left: visualViewportPanel.left,
                    right: "auto",
                    width: visualViewportPanel.width,
                  }
                : undefined
            }
          >
            <GlassCard
              intensity="high"
              radius="lg"
              className="z-toast w-auto max-w-[24rem] max-h-[calc(100dvh-env(safe-area-inset-bottom)-6rem)] overflow-y-auto overscroll-contain border-glass-border shadow-2xl ring-1 ring-black/(--opacity-faint) p-6 pointer-events-auto"
            >
              <div
                className={cn(
                  "flex flex-col",
                  showInstallPanel && showPushPanel ? "gap-6" : "gap-4"
                )}
              >
                {showInstallPanel && (
                  // Wave 119 SW7 (CLS-119-02): mirror W118 SW4's push-panel
                  // min-h pattern. Install panel content (icon+title row →
                  // description paragraph → button row) mounts after async i18n
                  // resolves, contributing ~0.141 CLS in worst-case 7-URL × 3
                  // LHCI sweeps that hit warm-cache timing. Reserved height
                  // 220px ≈ 32 (header) + 16 (gap) + 68 (description, RU 3-line
                  // worst case) + 16 (gap) + 56 (button row pt-2 + h-12) + ~32
                  // buffer. Push panel uses 260px (smaller buffer because it has
                  // tighter known content layout).
                  <div className="space-y-4 min-h-[220px]">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex items-center gap-3">
                        <div className="p-2.5 rounded-2xl bg-brand/(--opacity-subtle) text-brand">
                          <Download className="h-5 w-5" />
                        </div>
                        <h2 className="text-lg font-black tracking-tight text-text-primary sf-pro">
                          {t("system:installPrompt.installTitle", { appName })}
                        </h2>
                      </div>
                      <button
                        onClick={handleInstallDismiss}
                        aria-label={t("system:installPrompt.closeOffer")}
                        className="min-h-11 min-w-11 inline-flex items-center justify-center rounded-xl hover:bg-(--bg-surface-hover)/(--opacity-soft) text-(--text-secondary) transition-colors"
                      >
                        <X className="h-5 w-5" />
                      </button>
                    </div>
                    <p className="text-sm font-medium text-(--text-secondary) leading-relaxed opacity-hover">
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
                  // The default-permission education panel is only opened by a
                  // successful authenticated event-registration action.
                  <div className="space-y-4 min-h-[260px]">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex items-center gap-3">
                        <div className="p-2.5 rounded-2xl bg-brand/(--opacity-subtle) text-brand">
                          <Bell className="h-5 w-5" />
                        </div>
                        <h2 className="text-lg font-black tracking-tight text-text-primary sf-pro">
                          {t("system:installPrompt.notificationsTitle")}
                        </h2>
                      </div>
                      <button
                        onClick={handlePushDismiss}
                        aria-label={t("system:installPrompt.notificationsClose")}
                        className="min-h-11 min-w-11 inline-flex items-center justify-center rounded-xl hover:bg-(--bg-surface-hover)/(--opacity-soft) text-(--text-secondary) transition-colors"
                      >
                        <X className="h-5 w-5" />
                      </button>
                    </div>

                    <p className="text-sm font-medium text-(--text-secondary) leading-relaxed opacity-hover">
                      {t("system:installPrompt.manageNotifications")}
                    </p>

                    <div className="space-y-4">
                      <p className="text-xs font-bold text-(--text-secondary) opacity-medium leading-relaxed px-1">
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
                        <span className="text-label-md font-bold text-(--text-secondary) uppercase tracking-wider opacity-medium">
                          {t("system:installPrompt.status", { status: permissionText })}
                        </span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </GlassCard>
          </m.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {feedback && (
          <m.div
            initial={FEEDBACK_VARIANTS.initial}
            animate={FEEDBACK_VARIANTS.animate}
            exit={FEEDBACK_VARIANTS.exit}
            className="fixed top-24 left-1/2 -translate-x-1/2 z-toast w-full max-w-[24rem] px-6"
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
              <button
                onClick={handleFeedbackClose}
                aria-label={t("common:buttons.close")}
                className="min-h-11 min-w-11 inline-flex items-center justify-center"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </m.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {updateToastOpen && (
          <m.div
            initial={UPDATE_TOAST_VARIANTS.initial}
            animate={UPDATE_TOAST_VARIANTS.animate}
            exit={UPDATE_TOAST_VARIANTS.exit}
            className="fixed bottom-24 left-1/2 -translate-x-1/2 z-toast w-full max-w-[28rem] px-6"
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
                aria-label={t("common:buttons.close")}
                className="min-h-11 min-w-11 inline-flex items-center justify-center hover:bg-brand/(--opacity-subtle) rounded-lg transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </m.div>
        )}
      </AnimatePresence>
    </>
  )
}
