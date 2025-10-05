/// <reference lib="webworker" />

import { cleanupOutdatedCaches, precacheAndRoute, createHandlerBoundToURL } from "workbox-precaching"
import { clientsClaim } from "workbox-core"
import { registerRoute, NavigationRoute } from "workbox-routing"
import { StaleWhileRevalidate, CacheFirst } from "workbox-strategies"
import { ExpirationPlugin } from "workbox-expiration"
import {
  NotificationData,
  buildNotificationDetails,
  parsePushEventData,
} from "@/push/notification-helpers"

declare const self: ServiceWorkerGlobalScope & typeof globalThis

const OFFLINE_URL = "/offline.html"
const API_CACHE = "api-cache"
const IMG_CACHE = "img-cache"

cleanupOutdatedCaches()
precacheAndRoute(self.__WB_MANIFEST)
clientsClaim()
void self.skipWaiting()

self.addEventListener("message", (event) => {
  if (event.data && typeof event.data === "object" && "type" in event.data) {
    const type = (event.data as { type?: string }).type
    if (type === "SKIP_WAITING") {
      void self.skipWaiting()
    }
  }
})

const navigationHandler = createHandlerBoundToURL(OFFLINE_URL)

registerRoute(
  new NavigationRoute(async (options) => {
    const { event, request, url } = options
    const fetchEvent = event as FetchEvent

    if (!/^\/[^_].*/.test(url.pathname)) {
      return fetch(request)
    }

    try {
      const preload = "preloadResponse" in fetchEvent ? await fetchEvent.preloadResponse : undefined
      if (preload) {
        return preload
      }

      return await fetch(request)
    } catch (error) {
      return navigationHandler(options)
    }
  }, { allowlist: [/^\/[^_].*/] })
)

registerRoute(
  ({ url }) => /\/api\/(news|schedule)/.test(url.pathname),
  new StaleWhileRevalidate({
    cacheName: API_CACHE,
    plugins: [
      new ExpirationPlugin({ maxEntries: 100, maxAgeSeconds: 60 * 60 }),
    ],
  })
)

registerRoute(
  ({ request }) => request.destination === "image",
  new CacheFirst({
    cacheName: IMG_CACHE,
    plugins: [
      new ExpirationPlugin({ maxEntries: 200, maxAgeSeconds: 7 * 24 * 60 * 60 }),
    ],
  })
)

self.addEventListener("push", (event) => {
  const handlePush = async () => {
    const payload = parsePushEventData(event.data)
    const { title, options, data, payloadType } = buildNotificationDetails(payload)

    if (payloadType === "in-app") {
      const windowClients = (await self.clients.matchAll({
        type: "window",
        includeUncontrolled: true,
      })) as WindowClient[]

      const hasVisibleClient = windowClients.some((client) => client.visibilityState === "visible")

      if (hasVisibleClient) {
        const toastMessage = {
          type: "PUSH_NOTIFICATION",
          toast: {
            title,
            body: payload.body,
            url: typeof data.url === "string" ? data.url : undefined,
            icon: options.icon,
            tag: options.tag,
            data,
            timestamp: options.timestamp ?? Date.now(),
          },
        }

        for (const client of windowClients) {
          client.postMessage(toastMessage)
        }

        return
      }
    }

    await self.registration.showNotification(title, options)
  }

  event.waitUntil(handlePush())
})

self.addEventListener("notificationclick", (event) => {
  event.notification.close()

  const data = (event.notification.data || {}) as NotificationData
  const defaultUrl = typeof data.url === "string" && data.url ? data.url : "/"
  const actionUrl =
    event.action && data.actionUrls && typeof data.actionUrls === "object"
      ? data.actionUrls[event.action]
      : undefined
  const targetUrl = typeof actionUrl === "string" && actionUrl ? actionUrl : defaultUrl

  event.waitUntil(
    (async () => {
      const allClients = await self.clients.matchAll({
        type: "window",
        includeUncontrolled: true,
      })

      const absoluteTarget = new URL(targetUrl, self.registration.scope).href

      for (const client of allClients) {
        const clientUrl = new URL(client.url, self.registration.scope).href
        if (clientUrl === absoluteTarget) {
          if ("focus" in client) {
            return client.focus()
          }
          return
        }
        if (clientUrl.startsWith(self.registration.scope) && "navigate" in client) {
          await client.navigate(absoluteTarget)
          if ("focus" in client) {
            return client.focus()
          }
          return
        }
      }

      if (self.clients.openWindow) {
        await self.clients.openWindow(absoluteTarget)
      }
    })()
  )
})
