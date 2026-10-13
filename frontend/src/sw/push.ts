/// <reference lib="webworker" />
declare const self: ServiceWorkerGlobalScope

import {
  buildNotificationDetails,
  DEFAULT_ICON,
  getDefaultNotificationBody,
  getDefaultNotificationTitle,
  parsePushEventData,
} from "@/push/notification-helpers"
import { resolveNotificationDeepLink, resolveOptionalSameOriginUrl } from "@/notifications/contract"
import { sanitizeReportPayload, storePendingNavigation, storePendingReport } from "./offline"

const USER_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const RECIPIENT_CHECK_TIMEOUT_MS = 2_000

type NativeNotificationDecision = "deliver" | "suppress" | "generic"

async function checkNativeNotificationRecipient(
  recipientUserId: unknown
): Promise<NativeNotificationDecision> {
  if (typeof recipientUserId !== "string" || !USER_ID_PATTERN.test(recipientUserId)) {
    return "suppress"
  }
  if (self.navigator.onLine === false) return "generic"

  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), RECIPIENT_CHECK_TIMEOUT_MS)
  try {
    const response = await fetch(new URL("/api/v1/users/me", self.location.origin), {
      method: "GET",
      credentials: "include",
      cache: "no-store",
      headers: { Accept: "application/json", "Cache-Control": "no-store" },
      signal: controller.signal,
    })
    if (response.status === 401 || response.status === 403) return "suppress"
    if (!response.ok) return "generic"

    let profile: unknown
    try {
      profile = await response.json()
    } catch {
      return "generic"
    }
    if (
      !profile ||
      typeof profile !== "object" ||
      !("id" in profile) ||
      typeof profile.id !== "string" ||
      !USER_ID_PATTERN.test(profile.id)
    ) {
      return "generic"
    }
    return profile.id === recipientUserId ? "deliver" : "suppress"
  } catch {
    return "generic"
  } finally {
    clearTimeout(timeout)
  }
}

function buildGenericNotification() {
  return {
    title: getDefaultNotificationTitle(),
    options: {
      body: getDefaultNotificationBody(),
      icon: DEFAULT_ICON,
      badge: DEFAULT_ICON,
      data: { url: "/" },
    },
  }
}

/**
 * Initialize Push Notification handlers.
 */
export function initPushHandlers() {
  self.addEventListener("push", (event: PushEvent) => {
    const payload = parsePushEventData(event.data)
    const { title, options, data: notificationData } = buildNotificationDetails(payload)

    const handlePush = async () => {
      const clientList = await self.clients.matchAll({ type: "window", includeUncontrolled: true })
      const visibleClients = clientList.filter((c) => c.visibilityState === "visible")
      const hasRecipientBoundMetadata =
        (payload.data?.type !== undefined && payload.data.type !== "default") ||
        "recipientUserId" in notificationData ||
        typeof notificationData.notificationId === "string"

      if (visibleClients.length > 0 && payload.data?.type === "in-app") {
        const notificationId =
          typeof notificationData.notificationId === "string"
            ? notificationData.notificationId
            : undefined
        const topic =
          typeof notificationData.topic === "string" ? notificationData.topic : undefined
        const recipientUserId =
          typeof notificationData.recipientUserId === "string" &&
          notificationData.recipientUserId.length > 0
            ? notificationData.recipientUserId
            : undefined
        const message = {
          type: "PUSH_NOTIFICATION",
          ...(notificationId ? { notificationId } : {}),
          ...(topic ? { topic } : {}),
          ...(recipientUserId ? { recipientUserId } : {}),
          toast: {
            ...(notificationId ? { id: notificationId } : {}),
            title,
            body: options.body,
            url: payload.url || notificationData.url || "/",
            ...(notificationId || topic ? { data: notificationData } : {}),
          },
        }
        for (const client of visibleClients) {
          client.postMessage(message)
        }
      } else if (hasRecipientBoundMetadata) {
        const decision = await checkNativeNotificationRecipient(notificationData.recipientUserId)
        if (decision === "suppress") return
        if (decision === "generic") {
          const fallback = buildGenericNotification()
          await self.registration.showNotification(fallback.title, fallback.options)
          return
        }
        await self.registration.showNotification(title, options)
      } else {
        await self.registration.showNotification(title, options)
      }
    }

    event.waitUntil(handlePush())
  })

  self.addEventListener("notificationclick", (event: NotificationEvent) => {
    event.notification.close()

    const clickData = event.notification.data
    const absoluteUrl = resolveNotificationDeepLink(clickData?.url, self.location.origin)

    const handleNavigationAndReporting = async () => {
      let navigated = false
      try {
        const clientList = await self.clients.matchAll({
          type: "window",
          includeUncontrolled: true,
        })
        for (const client of clientList) {
          if ("url" in client && client.url === absoluteUrl && "focus" in client) {
            await (client as WindowClient).focus()
            navigated = true
            break
          }
        }
        if (!navigated && self.clients.openWindow) {
          const client = await self.clients.openWindow(absoluteUrl)
          if (client) {
            navigated = true
          }
        }
      } catch (_err) {
        // Navigation failed
      }

      if (clickData?.reportUrl) {
        const absoluteReportUrl = resolveOptionalSameOriginUrl(
          clickData.reportUrl,
          self.location.origin
        )
        if (!absoluteReportUrl) {
          if (!navigated) {
            await storePendingNavigation({ url: absoluteUrl, timestamp: Date.now() })
          }
          return
        }
        const rawPayload = clickData.reportPayload || {}
        const sanitized = sanitizeReportPayload(rawPayload)
        const payload =
          typeof sanitized === "object"
            ? { ...sanitized, notificationId: clickData.notificationId }
            : { notificationId: clickData.notificationId }

        const isOnline = self.navigator.onLine !== false

        if (isOnline) {
          try {
            await fetch(absoluteReportUrl, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(payload),
              keepalive: true,
            })
          } catch (_err) {
            if (!navigated) {
              await storePendingNavigation({ url: absoluteUrl, timestamp: Date.now() })
            }
            await storePendingReport({
              url: absoluteUrl,
              reportUrl: absoluteReportUrl,
              timestamp: Date.now(),
              payload,
            })
            return
          }
          if (!navigated) {
            await storePendingNavigation({ url: absoluteUrl, timestamp: Date.now() })
          }
        } else {
          await storePendingNavigation({ url: absoluteUrl, timestamp: Date.now() })
          await storePendingReport({
            url: absoluteUrl,
            reportUrl: absoluteReportUrl,
            timestamp: Date.now(),
            payload,
          })
        }
      } else if (!navigated) {
        await storePendingNavigation({ url: absoluteUrl, timestamp: Date.now() })
      }
    }

    event.waitUntil(handleNavigationAndReporting())
  })
}
