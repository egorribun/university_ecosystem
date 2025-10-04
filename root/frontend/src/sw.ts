/// <reference lib="webworker" />

import { cleanupOutdatedCaches, precacheAndRoute, createHandlerBoundToURL } from "workbox-precaching"
import { clientsClaim } from "workbox-core"
import { registerRoute, NavigationRoute } from "workbox-routing"
import { StaleWhileRevalidate, CacheFirst } from "workbox-strategies"
import { ExpirationPlugin } from "workbox-expiration"

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

    if (!/^\/[^_].*/.test(url.pathname)) {
      return fetch(request)
    }

    try {
      const preload = await event.preloadResponse
      if (preload) {
        return preload
      }

      return await fetch(request)
    } catch (error) {
      return navigationHandler({ request, event })
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

type NotificationData = {
  url?: string
  [key: string]: unknown
}

type PushPayload = {
  title?: string
  body?: string
  icon?: string
  badge?: string
  tag?: string
  url?: string
  data?: Record<string, unknown>
  renotify?: boolean
  requireInteraction?: boolean
  silent?: boolean
  timestamp?: number
  vibrate?: number[]
  actions?: NotificationAction[]
}

const DEFAULT_TITLE = "Экосистема ГУУ"
const DEFAULT_ICON = "/maskable-icon-192.png"

self.addEventListener("push", (event) => {
  const payload = (() => {
    if (!event.data) {
      return {}
    }
    try {
      return event.data.json() as PushPayload
    } catch (error) {
      return { body: event.data.text() } as PushPayload
    }
  })()

  const title = payload.title || DEFAULT_TITLE
  const data: NotificationData = {
    url: payload.url || "/",
    ...(payload.data ?? {}),
  }

  const options: NotificationOptions = {
    body: payload.body,
    icon: payload.icon || DEFAULT_ICON,
    badge: payload.badge || payload.icon || DEFAULT_ICON,
    tag: payload.tag,
    data,
    renotify: payload.renotify,
    requireInteraction: payload.requireInteraction,
    silent: payload.silent,
    timestamp: payload.timestamp,
    vibrate: payload.vibrate,
    actions: payload.actions,
  }

  event.waitUntil(self.registration.showNotification(title, options))
})

self.addEventListener("notificationclick", (event) => {
  event.notification.close()

  const data = (event.notification.data || {}) as NotificationData
  const targetUrl = typeof data.url === "string" && data.url ? data.url : "/"

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
