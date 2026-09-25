import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import type { ChangeEvent } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { deleteSubscription, fetchPushTopics, updatePushTopics } from "@/api/notifications"
import { logError, logWarning } from "@/app/logger"
import {
  isPushSupported,
  resolveServiceWorkerRegistration,
  ensurePushSubscription,
  setPushConsent,
  getPersistedTopics,
  getOwnedPushSubscription,
  setPersistedTopics,
} from "@/push/subscribe"
import { currentUserQueryKey } from "@/contexts/AuthContext"
import { getConfirmedUserId } from "@/stores/authIdentity"
import { useAuthStore } from "@/stores/useAuthStore"
import type { PushTopicsResponse } from "@/types/notifications"
import { isSafariIOS } from "@/utils/browser"
import { useTranslation } from "react-i18next"
import {
  CANONICAL_NOTIFICATION_TOPICS,
  NOTIFICATION_TOPIC_LABEL_KEYS,
  normalizeNotificationTopics,
  type NotificationTopic,
} from "@/notifications/contract"

export type NotificationTopicKey = NotificationTopic

export const NOTIFICATION_TOPIC_KEYS: NotificationTopicKey[] = [...CANONICAL_NOTIFICATION_TOPICS]

export const DEFAULT_NOTIFICATION_TOPICS: Record<NotificationTopicKey, boolean> = {
  "news.published": true,
  "schedule.changed": true,
  "events.published": true,
  "chat.message.created": true,
  "system.release": true,
}

export type NotificationToast = {
  text: string
  severity?: "success" | "info" | "warning" | "error"
}

export type UsePushPreferencesOptions = {
  onNotify?: (toast: NotificationToast) => void
}

const SAFARI_IOS_GUIDE_URL = "https://support.apple.com/ru-ru/guide/iphone/iph42ab2f3a7/ios"

function toTopicState(topics: readonly unknown[]): Record<NotificationTopicKey, boolean> {
  const selected = new Set(normalizeNotificationTopics(topics))
  return Object.fromEntries(
    NOTIFICATION_TOPIC_KEYS.map((key) => [key, selected.has(key)])
  ) as Record<NotificationTopicKey, boolean>
}

/** The session answered for another account than the query was keyed by. */
class PushTopicsAccountChangedError extends Error {}

export function usePushPreferences(options?: UsePushPreferencesOptions) {
  const { onNotify } = options ?? {}
  const { t } = useTranslation(["notifications"])

  const topicKeys = useMemo(() => NOTIFICATION_TOPIC_KEYS, [])
  // SSR stubs, cache placeholders and hydrating sessions have no identity.
  const confirmedUserId = useAuthStore(getConfirmedUserId)
  const pushTopicsQuery = useQuery({
    queryKey: ["notifications", "push-topics", confirmedUserId],
    queryFn: async (): Promise<PushTopicsResponse> => {
      const response = await fetchPushTopics()
      // The session answered for whoever is signed in now; never store that
      // answer under the account this query was started for.
      if (getConfirmedUserId(useAuthStore.getState()) !== confirmedUserId) {
        throw new PushTopicsAccountChangedError()
      }
      // The local copy only mirrors the server's canonical preference.
      setPersistedTopics(response.has_preferences ? response.topics : null, {
        userId: confirmedUserId,
      })
      return response
    },
    enabled: confirmedUserId !== null && isPushSupported(),
  })
  const serverTopics = pushTopicsQuery.data
  // Until the canonical preference is known, an explicit toggle would
  // overwrite it (e.g. an opt-out) with a placeholder selection.
  const topicsReady = pushTopicsQuery.isSuccess
  const [topicState, setTopicState] = useState<Record<NotificationTopicKey, boolean>>(() => ({
    ...DEFAULT_NOTIFICATION_TOPICS,
  }))
  // Hydrate during render: server data wins; the cached mirror is only a
  // placeholder for a newly confirmed account until the server responds.
  const topicSource = serverTopics ?? confirmedUserId
  const [appliedTopicSource, setAppliedTopicSource] = useState<typeof topicSource>(null)
  if (topicSource !== appliedTopicSource) {
    setAppliedTopicSource(topicSource)
    setTopicState(
      toTopicState(
        serverTopics
          ? serverTopics.has_preferences
            ? serverTopics.topics
            : topicKeys
          : (getPersistedTopics({ userId: confirmedUserId }) ?? topicKeys)
      )
    )
  }
  // Topics chosen while notifications are off are sent explicitly on enable.
  const pendingExplicitTopicsRef = useRef<string[] | undefined>(undefined)
  const [pushSupported, setPushSupported] = useState(true)
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
          acc[key] = t(`notifications:topics.${NOTIFICATION_TOPIC_LABEL_KEYS[key]}`)
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

  const enableNotifications = useCallback(async () => {
    if (!isPushSupported()) {
      setPushSupported(false)
      notify({ text: t("notifications:messages.browserUnsupported"), severity: "warning" })
      return
    }
    if (typeof Notification === "undefined") {
      notify({ text: t("notifications:messages.notificationsUnsupported"), severity: "warning" })
      return
    }

    // Optimistic update: instantly show enabled
    setOptimisticEnabled(true)
    setPushBusy(true)

    try {
      // Safari requires the native permission request to originate from the
      // button's user activation. Waiting for service-worker readiness first
      // can lose that activation before the browser sees this call.
      const requestedPermission =
        Notification.permission === "default"
          ? await Notification.requestPermission()
          : Notification.permission
      setNotificationPermission(requestedPermission)
      if (requestedPermission !== "granted") {
        setOptimisticEnabled(null)
        notify({
          text:
            requestedPermission === "denied"
              ? t("notifications:messages.enableInSettings")
              : t("notifications:messages.confirmPermission"),
          severity: "info",
        })
        return
      }
      const registration = await resolveServiceWorkerRegistration()
      if (!registration) {
        setOptimisticEnabled(null) // Revert optimistic update
        notify({ text: t("notifications:messages.workerNotReady"), severity: "info" })
        return
      }
      // Never send topics implicitly: the server binds the endpoint to the
      // account's canonical preference, which may be an explicit opt-out.
      const subscription = await ensurePushSubscription({
        registration,
        requestPermission: false,
      })
      const permission = Notification.permission
      setNotificationPermission(permission)
      if (!subscription) {
        setOptimisticEnabled(null) // Revert optimistic update
        const text =
          permission === "denied"
            ? t("notifications:messages.enableInSettings")
            : permission === "default"
              ? t("notifications:messages.confirmPermission")
              : t("notifications:messages.subscriptionFailed")
        notify({ text, severity: permission === "granted" ? "error" : "info" })
        setPushSubscription(subscription)
        return
      }
      if (permission !== "granted") {
        setOptimisticEnabled(null) // Revert optimistic update
        notify({
          text: t("notifications:messages.enableInSettings"),
          severity: "info",
        })
        setPushSubscription(subscription)
        return
      }
      // The endpoint is bound now: reflect that before any topic update.
      setPushSubscription(subscription)
      setPushConsent(true)
      const pendingTopics = pendingExplicitTopicsRef.current
      if (pendingTopics !== undefined) {
        try {
          await updatePushTopics(subscription.endpoint, pendingTopics)
          pendingExplicitTopicsRef.current = undefined
        } catch (error) {
          logError("Failed to update topics", error)
          invalidatePushQueries()
          notify({ text: t("notifications:messages.updateFailed"), severity: "error" })
          return
        }
      }
      invalidatePushQueries()
      notify({ text: t("notifications:messages.enabled"), severity: "success" })
    } catch (error) {
      setOptimisticEnabled(null) // Revert on error
      logError("Failed to enable notifications", error)
      notify({ text: t("notifications:messages.enableFailed"), severity: "error" })
    } finally {
      // If successful, setOptimisticEnabled(null) allows falling back to real subscription state
      setOptimisticEnabled(null)
      setPushBusy(false)
      setPushInitializing(false)
    }
  }, [invalidatePushQueries, notify, t])

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
        notify({ text: t("notifications:messages.workerUnavailable"), severity: "warning" })
        return
      }
      const subscription = await registration.pushManager.getSubscription()
      if (!subscription) {
        setPushSubscription(null)
        setPushConsent(false)
        notify({ text: t("notifications:messages.disabled"), severity: "success" })
        invalidatePushQueries()
        return
      }
      const endpoint = subscription.endpoint
      let unsubscribed = false
      try {
        unsubscribed = await subscription.unsubscribe()
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
        notify({ text: t("notifications:messages.disabled"), severity: "success" })
      } else {
        notify({ text: t("notifications:messages.disabledLocal"), severity: "info" })
      }
      invalidatePushQueries()
    } catch (error) {
      // On error, we might want to keep it disabled visually or revert?
      // Typically disabling is safer to assume success for UX.
      logError("Failed to disable notifications", error)
      notify({ text: t("notifications:messages.disableFailed"), severity: "error" })
    } finally {
      setOptimisticEnabled(null)
      setPushBusy(false)
    }
  }, [invalidatePushQueries, notify, t])

  const handleTopicToggle = useCallback(
    (key: NotificationTopicKey) => async (_: ChangeEvent<HTMLInputElement>, checked: boolean) => {
      if (pushBusy || !topicsReady) return
      const previousState = topicState
      const nextState = { ...topicState, [key]: checked }
      const topicsToSend = topicKeys.filter((topic) => nextState[topic])
      setTopicState(nextState)
      if (!pushSubscription) {
        pendingExplicitTopicsRef.current = topicsToSend
        return
      }
      setPushBusy(true)
      try {
        // PATCH, not POST: an empty list must mean "opt out of everything".
        await updatePushTopics(pushSubscription.endpoint, topicsToSend)
        invalidatePushQueries()
        const label = topicLabels[key]
        notify({
          text: checked
            ? t("notifications:messages.topicEnabled", { label })
            : t("notifications:messages.topicDisabled", { label }),
          severity: "success",
        })
      } catch (error) {
        logError("Failed to update topics", error)
        setTopicState(previousState)
        notify({ text: t("notifications:messages.updateFailed"), severity: "error" })
      } finally {
        setPushBusy(false)
      }
    },
    [
      invalidatePushQueries,
      pushBusy,
      pushSubscription,
      topicKeys,
      topicState,
      topicsReady,
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

    if (typeof navigator !== "undefined" && navigator.permissions?.query) {
      navigator.permissions
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
              } catch {
                // ignore
              }
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
        setPushSupported(supported)
        if (!supported) {
          setPushSubscription(null)
          return
        }
        setPushInitializing(true)
        // A topic choice belongs to the account that made it.
        pendingExplicitTopicsRef.current = undefined
        // Read-only: mounting preferences never writes to the server, and a
        // browser endpoint enabled by another account is not this user's.
        const subscription = await getOwnedPushSubscription(confirmedUserId)
        if (!active) return
        setPushSubscription(subscription)
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
  }, [confirmedUserId, t])

  return {
    topicKeys,
    topicLabels,
    topicState,
    topicsReady,
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
