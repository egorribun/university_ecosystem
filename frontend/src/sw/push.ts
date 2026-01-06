/// <reference lib="webworker" />
declare const self: ServiceWorkerGlobalScope

import { buildNotificationDetails, parsePushEventData } from "@/push/notification-helpers"
import { log } from "./logger"

/**
 * Initialize Push Notification handlers.
 */
export function initPushHandlers() {
  self.addEventListener("push", (event: PushEvent) => {
    const payload = parsePushEventData(event.data)
    const { title, options } = buildNotificationDetails(payload)

    event.waitUntil(self.registration.showNotification(title, options))
  })

  self.addEventListener("notificationclick", (event: NotificationEvent) => {
    event.notification.close()

    const clickData = event.notification.data
    const urlToOpen = clickData?.url || "/"

    // Handle action buttons if any
    if (event.action && clickData?.actionUrls?.[event.action]) {
      // Handle specific action click
    }

    event.waitUntil(
      self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
        for (const client of clientList) {
          if ("url" in client && client.url === urlToOpen && "focus" in client) {
            return (client as WindowClient).focus()
          }
        }
        if (self.clients.openWindow) {
          return self.clients.openWindow(urlToOpen)
        }
      })
    )
  })
}
