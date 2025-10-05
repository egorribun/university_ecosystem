import { useCallback, useEffect, useMemo, useState } from "react"
import type { ChangeEvent } from "react"
import {
  getExistingPushSubscription,
  isPushSupported,
  setPushConsent,
  urlBase64ToUint8Array,
} from "@/push/subscribe"
import {
  deleteSubscription,
  getVapidKey,
  saveSubscription,
  updateSubscriptionTopics,
} from "@/api/notifications"
import { isSafariIOS } from "@/utils/browser"

export type NotificationTopicKey = "news" | "schedule" | "system"

export const NOTIFICATION_TOPIC_LABELS: Record<NotificationTopicKey, string> = {
  news: "Новости",
  schedule: "Расписание",
  system: "Системные",
}

export const DEFAULT_NOTIFICATION_TOPICS: Record<NotificationTopicKey, boolean> = {
  news: true,
  schedule: true,
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

  const topicKeys = useMemo(
    () => Object.keys(NOTIFICATION_TOPIC_LABELS) as NotificationTopicKey[],
    [],
  )
  const [topicState, setTopicState] = useState<Record<NotificationTopicKey, boolean>>(
    DEFAULT_NOTIFICATION_TOPICS,
  )
  const [pushSupported, setPushSupported] = useState(() => isPushSupported())
  const [notificationPermission, setNotificationPermission] = useState<NotificationPermission>(() => {
    if (typeof window === "undefined" || typeof Notification === "undefined") return "default"
    return Notification.permission
  })
  const [pushSubscription, setPushSubscription] = useState<PushSubscription | null>(null)
  const [pushBusy, setPushBusy] = useState(false)
  const [pushInitializing, setPushInitializing] = useState(true)
  const [safariIOS] = useState(() => isSafariIOS())

  const notify = useCallback(
    (toast: NotificationToast) => {
      onNotify?.(toast)
    },
    [onNotify],
  )

  const selectedTopics = useMemo(() => topicKeys.filter(key => topicState[key]), [topicKeys, topicState])

  const notificationsEnabled = !!pushSubscription

  const permissionText = useMemo(() => {
    switch (notificationPermission) {
      case "granted":
        return "разрешено"
      case "denied":
        return "запрещено"
      default:
        return "не запрошено"
    }
  }, [notificationPermission])

  const selectedTopicsDescription = useMemo(() => {
    if (!selectedTopics.length) return "Темы не выбраны"
    return selectedTopics.map(key => NOTIFICATION_TOPIC_LABELS[key]).join(", ")
  }, [selectedTopics])

  const applyServerTopics = useCallback(
    (topics?: string[] | null) => {
      if (topics == null) return
      const next: Record<NotificationTopicKey, boolean> = {} as Record<NotificationTopicKey, boolean>
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
    [topicKeys],
  )

  const enableNotifications = useCallback(async () => {
    if (!isPushSupported()) {
      setPushSupported(false)
      notify({ text: "Ваш браузер не поддерживает push-уведомления", sev: "warning" })
      return
    }
    if (typeof Notification === "undefined") {
      notify({ text: "Браузер не поддерживает уведомления", sev: "warning" })
      return
    }
    setPushBusy(true)
    try {
      const permission = await Notification.requestPermission()
      setNotificationPermission(permission)
      if (permission !== "granted") {
        notify({ text: "Разрешите уведомления в настройках браузера", sev: "info" })
        return
      }

      if (!("serviceWorker" in navigator)) {
        notify({ text: "Сервис-воркеры недоступны", sev: "error" })
        return
      }

      const registration = await navigator.serviceWorker.ready
      let sub = await registration.pushManager.getSubscription()

      if (!sub) {
        let vapidKey = ""
        try {
          vapidKey = (await getVapidKey())?.trim() || ""
        } catch (error) {
          console.error("Failed to load VAPID key", error)
        }
        if (!vapidKey) {
          notify({ text: "Не удалось получить ключ уведомлений", sev: "error" })
          return
        }
        const applicationServerKey = urlBase64ToUint8Array(vapidKey)
        sub = await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey,
        })
      }

      if (!sub) {
        notify({ text: "Не удалось активировать подписку", sev: "error" })
        return
      }

      type Payload = Parameters<typeof saveSubscription>[0]
      const saved = await saveSubscription(sub.toJSON() as Payload, selectedTopics)
      applyServerTopics(saved?.topics ?? selectedTopics)
      setPushSubscription(sub)
      setPushConsent(true)
      notify({ text: "Уведомления включены", sev: "success" })
    } catch (error) {
      console.error("Failed to enable notifications", error)
      notify({ text: "Не удалось включить уведомления", sev: "error" })
    } finally {
      setPushBusy(false)
      setPushInitializing(false)
    }
  }, [applyServerTopics, notify, selectedTopics])

  const disableNotifications = useCallback(async () => {
    if (!isPushSupported()) {
      setPushSubscription(null)
      setPushConsent(false)
      return
    }
    setPushBusy(true)
    try {
      const registration = await navigator.serviceWorker.ready
      const sub = await registration.pushManager.getSubscription()
      if (!sub) {
        setPushSubscription(null)
        setPushConsent(false)
        notify({ text: "Уведомления выключены", sev: "success" })
        return
      }
      const endpoint = sub.endpoint
      let unsubscribed = false
      try {
        unsubscribed = await sub.unsubscribe()
      } catch (error) {
        console.error("Failed to unsubscribe push", error)
      }
      if (endpoint) {
        try {
          await deleteSubscription(endpoint)
        } catch (error) {
          console.warn("Не удалось удалить подписку на сервере", error)
        }
      }
      setPushSubscription(null)
      setPushConsent(false)
      if (unsubscribed || !endpoint) {
        notify({ text: "Уведомления выключены", sev: "success" })
      } else {
        notify({ text: "Уведомления отключены локально", sev: "info" })
      }
    } catch (error) {
      console.error("Failed to disable notifications", error)
      notify({ text: "Не удалось выключить уведомления", sev: "error" })
    } finally {
      setPushBusy(false)
    }
  }, [notify])

  const handleTopicToggle = useCallback(
    (key: NotificationTopicKey) =>
      async (_: ChangeEvent<HTMLInputElement>, checked: boolean) => {
        const nextState = { ...topicState, [key]: checked }
        setTopicState(nextState)
        if (!notificationsEnabled || pushBusy) return
        if (!isPushSupported()) return
        setPushBusy(true)
        const topicsToSend = topicKeys.filter(topic => nextState[topic])
        try {
          const registration = await navigator.serviceWorker.ready
          const sub = await registration.pushManager.getSubscription()
          if (!sub) {
            setPushSubscription(null)
            setPushConsent(false)
            return
          }
          const endpoint = (sub.endpoint || "").trim()
          type Payload = Parameters<typeof saveSubscription>[0]
          const saved = endpoint
            ? await updateSubscriptionTopics(endpoint, topicsToSend)
            : await saveSubscription(sub.toJSON() as Payload, topicsToSend)
          applyServerTopics(saved?.topics ?? topicsToSend)
          setPushSubscription(sub)
        } catch (error) {
          console.error("Failed to update topics", error)
          notify({ text: "Не удалось обновить настройки уведомлений", sev: "error" })
        } finally {
          setPushBusy(false)
        }
      },
    [applyServerTopics, notificationsEnabled, pushBusy, topicKeys, topicState, notify],
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
      ;(navigator as any)
        .permissions.query({ name: "notifications" as PermissionName })
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
            const statusWithOnChange = status as PermissionStatus & { onchange?: (() => void) | null }
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
        const sub = await getExistingPushSubscription()
        if (!active) return
        setPushSubscription(sub)
        if (sub) {
          setPushConsent(true)
          type Payload = Parameters<typeof saveSubscription>[0]
          try {
            const saved = await saveSubscription(sub.toJSON() as Payload)
            if (!active) return
            applyServerTopics(saved?.topics ?? [])
          } catch (error) {
            console.warn("Не удалось получить настройки подписки", error)
          }
        }
      } catch (error) {
        if (active) {
          console.warn("Не удалось определить подписку на push", error)
        }
      } finally {
        if (active) setPushInitializing(false)
      }
    }
    void detectSubscription()
    return () => {
      active = false
    }
  }, [applyServerTopics])

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
