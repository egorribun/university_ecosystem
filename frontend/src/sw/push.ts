/// <reference lib="webworker" />
declare const self: ServiceWorkerGlobalScope

import { buildNotificationDetails, parsePushEventData } from "@/push/notification-helpers"
import { sanitizeReportPayload, storePendingNavigation, storePendingReport } from "./offline"

/**
 * Initialize Push Notification handlers.
 */
export function initPushHandlers() {
  self.addEventListener("push", (event: PushEvent) => {
    const payload = parsePushEventData(event.data)
    const { title, options } = buildNotificationDetails(payload)

    const handlePush = async () => {
      const clientList = await self.clients.matchAll({ type: "window", includeUncontrolled: true })
      const visibleClients = clientList.filter((c) => c.visibilityState === "visible")

      if (visibleClients.length > 0 && payload.data?.type === "in-app") {
        const message = {
          type: "PUSH_NOTIFICATION",
          toast: {
            title,
            body: options.body || payload.body,
            url: payload.url || options.data?.url || "/",
          },
        }
        for (const client of visibleClients) {
          client.postMessage(message)
        }
      } else {
        await self.registration.showNotification(title, options)
      }
    }

    event.waitUntil(handlePush())
  })

  self.addEventListener("notificationclick", (event: NotificationEvent) => {
    event.notification.close()

    const clickData = event.notification.data
    const urlToOpen = clickData?.url || "/"
    const absoluteUrl = new URL(urlToOpen, self.location.origin).toString()

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
          } else {
            throw new Error("openWindow returned null")
          }
        }
      } catch (_err) {
        // Navigation failed
      }

      if (clickData?.reportUrl) {
        const absoluteReportUrl = new URL(clickData.reportUrl, self.location.origin).toString()
        const rawPayload = clickData.reportPayload || {}
        const sanitized = sanitizeReportPayload(rawPayload)
        const payload =
          typeof sanitized === "object" && sanitized !== null
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
