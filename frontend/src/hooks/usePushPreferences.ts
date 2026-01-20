import { useCallback, useEffect, useMemo, useState } from "react"
import type { ChangeEvent } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { deleteSubscription } from "@/api/notifications"
import { logError, logWarning } from "@/app/logger"
import {
  ensurePushSubscription,
  getExistingPushSubscription,
  getPersistedTopics,
  hasPushConsent,
  isPushSupported,
  resolveServiceWorkerRegistration,
  setPersistedTopics,
  setPushConsent,
} from "@/push/subscribe"
import { currentUserQueryKey, useAuth } from "@/contexts/AuthContext"
import { isSafariIOS } from "@/utils/browser"
import { useTranslation } from "react-i18next"

export type NotificationTopicKey = "news" | "schedule" | "events" | "system"

export const NOTIFICATION_TOPIC_KEYS: NotificationTopicKey[] = [
  "schedule",
  "news",
  "events",
  "system",
]

export const DEFAULT_NOTIFICATION_TOPICS: Record<NotificationTopicKey, boolean> = {
  schedule: true,
  news: true,
  events: true,
  system: true,
}

export type NotificationToast = {
  text: string
  sev?: "success" | "info" | "warning" | "error"
}

export type UsePushPreferencesOptions = {
  onNotify?: (toast: NotificationToast) => void
}

const SAFARI_IOS_GUIDE_URL = "https://support.apple.com/ru-ru/guide/iphone/iph42ab2f3a7/ios"

export function usePushPreferences(options?: UsePushPreferencesOptions) {
  const { onNotify } = options ?? {}
  const { t } = useTranslation(["notifications"])

  const topicKeys = useMemo(() => NOTIFICATION_TOPIC_KEYS, [])
  const { user } = useAuth()
  const activeUserId = user?.id ?? null
  const [topicState, setTopicState] = useState<Record<NotificationTopicKey, boolean>>(() => {
    const stored = getPersistedTopics({ userId: activeUserId })
    if (stored === undefined) {
      return { ...DEFAULT_NOTIFICATION_TOPICS }
    }
    const initial: Record<NotificationTopicKey, boolean> = {} as Record<
      NotificationTopicKey,
      boolean
    >
    for (const key of NOTIFICATION_TOPIC_KEYS) {
      initial[key] = false
    }
    for (const raw of stored) {
      const normalized = raw.toString().trim().toLowerCase()
      if ((NOTIFICATION_TOPIC_KEYS as string[]).includes(normalized)) {
        initial[normalized as NotificationTopicKey] = true
      }
    }
    return initial
  })
  const [pushSupported, setPushSupported] = useState(() => isPushSupported())
  const [notificationPermission, setNotificationPermission] = useState<NotificationPermission>(
    () => {
      if (typeof window === "undefined" || typeof Notification === "undefined") return "default"
      return Notification.permission
    }
  )
  const [pushSubscription, setPushSubscription] = useState<PushSubscription | null>(null)
  const [pushBusy, setPushBusy] = useState(false)
  const [pushInitializing, setPushInitializing] = useState(true)
  const [safariIOS] = useState(() => isSafariIOS())
  const queryClient = useQueryClient()
  const topicLabels = useMemo(
    () =>
      NOTIFICATION_TOPIC_KEYS.reduce(
        (acc, key) => {
          acc[key] = t(`notifications:topics.${key}`)
          return acc
        },
        {} as Record<NotificationTopicKey, string>
      ),
    [t]
  )

  const invalidatePushQueries = useCallback(() => {
    queryClient.invalidateQueries({
      predicate: (query) => {
        const key = query.queryKey
        if (!Array.isArray(key)) return false
        if (
          key.length === currentUserQueryKey.length &&
          key.every((value, index) => value === currentUserQueryKey[index])
        ) {
          return true
        }
        return key.some((value) => value === "notifications" || value === "users")
      },
    })
  }, [queryClient])

  const notify = useCallback(
    (toast: NotificationToast) => {
      onNotify?.(toast)
    },
    [onNotify]
  )

  const selectedTopics = useMemo(
    () => topicKeys.filter((key) => topicState[key]),
    [topicKeys, topicState]
  )

  const [optimisticEnabled, setOptimisticEnabled] = useState<boolean | null>(null)

  const notificationsEnabled = optimisticEnabled ?? !!pushSubscription

  const permissionText = useMemo(() => {
    const key = notificationPermission === "default" ? "default" : notificationPermission
    return t(`notifications:permission.${key}`)
  }, [notificationPermission, t])

  const selectedTopicsDescription = useMemo(() => {
    if (!selectedTopics.length) return t("notifications:messages.noTopics")
    return selectedTopics
      .map((key) => topicLabels[key])
      .filter(Boolean)
      .join(", ")
  }, [selectedTopics, t, topicLabels])

  const applyServerTopics = useCallback(
    (topics?: string[] | null) => {
      if (topics == null) return
      const next: Record<NotificationTopicKey, boolean> = {} as Record<
        NotificationTopicKey,
        boolean
      >
      for (const key of topicKeys) {
        next[key] = false
      }
      for (const raw of topics) {
        if (!raw) continue
        const normalized = raw.toString().trim().toLowerCase() as NotificationTopicKey
        if ((topicKeys as string[]).includes(normalized)) {
          next[normalized as NotificationTopicKey] = true
        }
      }
      setTopicState(next)
    },
    [topicKeys]
  )

  const enableNotifications = useCallback(async () => {
    if (!isPushSupported()) {
      setPushSupported(false)
      notify({ text: t("notifications:messages.browserUnsupported"), sev: "warning" })
      return
    }
    if (typeof Notification === "undefined") {
      notify({ text: t("notifications:messages.notificationsUnsupported"), sev: "warning" })
      return
    }

    // Optimistic update: instantly show enabled
    setOptimisticEnabled(true)
    setPushBusy(true)

    try {
      const registration = await resolveServiceWorkerRegistration()
      if (!registration) {
        setOptimisticEnabled(null) // Revert optimistic update
        notify({ text: t("notifications:messages.workerNotReady"), sev: "info" })
        return
      }
      const sub = await ensurePushSubscription({
        registration,
        topics: selectedTopics,
        requestPermission: true,
      })
      const permission = Notification.permission
      setNotificationPermission(permission)
      if (!sub) {
        setOptimisticEnabled(null) // Revert optimistic update
        const text =
          permission === "denied"
            ? t("notifications:messages.enableInSettings")
            : permission === "default"
              ? t("notifications:messages.confirmPermission")
              : t("notifications:messages.subscriptionFailed")
        notify({ text, sev: permission === "granted" ? "error" : "info" })
        setPushSubscription(sub)
        return
      }
      if (permission !== "granted") {
        setOptimisticEnabled(null) // Revert optimistic update
        notify({
          text: t("notifications:messages.enableInSettings"),
          sev: "info",
        })
        setPushSubscription(sub)
        return
      }
      const persistedTopics = getPersistedTopics({ userId: activeUserId }) ?? selectedTopics
      applyServerTopics(persistedTopics)
      setPushSubscription(sub)
      setPushConsent(true)
      invalidatePushQueries()
      notify({ text: t("notifications:messages.enabled"), sev: "success" })
    } catch (error) {
      setOptimisticEnabled(null) // Revert on error
      logError("Failed to enable notifications", error)
      notify({ text: t("notifications:messages.enableFailed"), sev: "error" })
    } finally {
      // If successful, setOptimisticEnabled(null) allows falling back to real subscription state
      setOptimisticEnabled(null)
      setPushBusy(false)
      setPushInitializing(false)
    }
  }, [activeUserId, applyServerTopics, invalidatePushQueries, notify, selectedTopics, t])

  const disableNotifications = useCallback(async () => {
    // Optimistic update: instantly show disabled
    setOptimisticEnabled(false)

    if (!isPushSupported()) {
      setPushSubscription(null)
      setPushConsent(false)
      setOptimisticEnabled(null)
      return
    }
    setPushBusy(true)
    try {
      const registration = await resolveServiceWorkerRegistration()
      if (!registration) {
        setOptimisticEnabled(null) // Revert on failure to find SW? Or just proceed?
        // If SW is missing, we probably can't really unsubscribe properly, but local state should be cleared.
        notify({ text: t("notifications:messages.workerUnavailable"), sev: "warning" })
        return
      }
      const sub = await registration.pushManager.getSubscription()
      if (!sub) {
        setPushSubscription(null)
        setPushConsent(false)
        notify({ text: t("notifications:messages.disabled"), sev: "success" })
        invalidatePushQueries()
        return
      }
      const endpoint = sub.endpoint
      let unsubscribed = false
      try {
        unsubscribed = await sub.unsubscribe()
      } catch (error) {
        logError("Failed to unsubscribe push", error)
      }
      if (endpoint) {
        try {
          await deleteSubscription(endpoint)
        } catch (error) {
          logWarning("Failed to delete push subscription on server", error)
        }
      }
      setPushSubscription(null)
      setPushConsent(false)
      if (unsubscribed || !endpoint) {
        notify({ text: t("notifications:messages.disabled"), sev: "success" })
      } else {
        notify({ text: t("notifications:messages.disabledLocal"), sev: "info" })
      }
      invalidatePushQueries()
    } catch (error) {
      // On error, we might want to keep it disabled visually or revert?
      // Typically disabling is safer to assume success for UX.
      logError("Failed to disable notifications", error)
      notify({ text: t("notifications:messages.disableFailed"), sev: "error" })
    } finally {
      setOptimisticEnabled(null)
      setPushBusy(false)
    }
  }, [invalidatePushQueries, notify, t])

  const handleTopicToggle = useCallback(
    (key: NotificationTopicKey) => async (_: ChangeEvent<HTMLInputElement>, checked: boolean) => {
      const previousState = topicState
      const nextState = { ...topicState, [key]: checked }
      setTopicState(nextState)
      setPersistedTopics(
        topicKeys.filter((topic) => nextState[topic]),
        { userId: activeUserId }
      )
      if (!notificationsEnabled || pushBusy) return
      if (!isPushSupported()) {
        setTopicState(previousState)
        return
      }
      setPushBusy(true)
      const topicsToSend = topicKeys.filter((topic) => nextState[topic])
      try {
        const registration = await resolveServiceWorkerRegistration()
        if (!registration) {
          setTopicState(previousState)
          notify({ text: t("notifications:messages.workerUnavailable"), sev: "warning" })
          return
        }
        const sub = await ensurePushSubscription({
          registration,
          topics: topicsToSend,
          requestPermission: false,
        })
        if (!sub) {
          setPushSubscription(null)
          setPushConsent(false)
          notify({
            text: t("notifications:messages.subscriptionPermissionHint"),
            sev: "warning",
          })
          setTopicState(previousState)
          return
        }
        const persisted = getPersistedTopics({ userId: activeUserId }) ?? topicsToSend
        applyServerTopics(persisted)
        setPushSubscription(sub)
        invalidatePushQueries()
        const label = topicLabels[key]
        if (label) {
          notify({
            text: checked
              ? t("notifications:messages.topicEnabled", { label })
              : t("notifications:messages.topicDisabled", { label }),
            sev: "success",
          })
        }
      } catch (error) {
        logError("Failed to update topics", error)
        setTopicState(previousState)
        notify({ text: t("notifications:messages.updateFailed"), sev: "error" })
      } finally {
        setPushBusy(false)
      }
    },
    [
      activeUserId,
      applyServerTopics,
      invalidatePushQueries,
      notificationsEnabled,
      pushBusy,
      topicKeys,
      topicState,
      notify,
      t,
      topicLabels,
    ]
  )

  useEffect(() => {
    setPushSupported(isPushSupported())
  }, [])

  useEffect(() => {
    let cancelled = false
    let removeListener: (() => void) | undefined

    const syncPermission = () => {
      if (typeof Notification === "undefined") {
        setNotificationPermission("default")
        return
      }
      setNotificationPermission(Notification.permission)
    }
    syncPermission()

    if (typeof navigator !== "undefined" && (navigator as any).permissions?.query) {
      ;(navigator as any).permissions
        .query({ name: "notifications" as PermissionName })
        .then((status: PermissionStatus) => {
          if (cancelled) return
          const handler = () => {
            if (cancelled) return
            const state = status.state
            if (state === "prompt") setNotificationPermission("default")
            else setNotificationPermission(state as NotificationPermission)
          }
          handler()
          if (typeof status.addEventListener === "function") {
            status.addEventListener("change", handler)
            removeListener = () => {
              try {
                status.removeEventListener("change", handler)
              } catch {}
            }
          } else {
            const statusWithOnChange = status as PermissionStatus & {
              onchange?: (() => void) | null
            }
            statusWithOnChange.onchange = handler
            removeListener = () => {
              if (statusWithOnChange.onchange === handler) {
                statusWithOnChange.onchange = null
              }
            }
          }
        })
        .catch(() => {})
    }

    return () => {
      cancelled = true
      removeListener?.()
    }
  }, [])

  useEffect(() => {
    let active = true
    const detectSubscription = async () => {
      try {
        const supported = isPushSupported()
        if (!active) return
        setPushSupported(supported)
        if (!supported) {
          setPushSubscription(null)
          return
        }
        setPushInitializing(true)
        const storedTopics = getPersistedTopics({ userId: activeUserId })
        if (storedTopics !== undefined) {
          applyServerTopics(storedTopics)
        }
        const consented = hasPushConsent()
        let sub: PushSubscription | null = null
        if (
          consented &&
          typeof Notification !== "undefined" &&
          Notification.permission === "granted"
        ) {
          sub = await ensurePushSubscription({
            topics: storedTopics,
            requestPermission: false,
          })
        } else {
          sub = await getExistingPushSubscription()
        }
        if (!active) return
        setPushSubscription(sub)
        if (sub) {
          if (consented) {
            setPushConsent(true)
          }
          const persisted = getPersistedTopics({ userId: activeUserId })
          if (persisted !== undefined) {
            applyServerTopics(persisted)
          }
        }
      } catch (error) {
        if (active) {
          logWarning(t("notifications:messages.detectFailed"), error)
        }
      } finally {
        if (active) setPushInitializing(false)
      }
    }
    void detectSubscription()
    return () => {
      active = false
    }
  }, [activeUserId, applyServerTopics])

  return {
    topicKeys,
    topicState,
    setTopicState,
    pushSupported,
    notificationPermission,
    pushSubscription,
    notificationsEnabled,
    pushBusy,
    pushInitializing,
    permissionText,
    selectedTopicsDescription,
    enableNotifications,
    disableNotifications,
    handleTopicToggle,
    safariIOS,
    safariGuideUrl: SAFARI_IOS_GUIDE_URL,
  }
}
