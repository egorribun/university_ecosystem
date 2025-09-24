/// <reference lib="webworker" />

import { precacheAndRoute, cleanupOutdatedCaches } from "workbox-precaching"
import { registerRoute } from "workbox-routing"
import { CacheFirst, NetworkFirst, StaleWhileRevalidate } from "workbox-strategies"
import { warmStrategyCache } from "workbox-recipes"

declare let self: ServiceWorkerGlobalScope & { __WB_MANIFEST: Array<any> }

type NotificationAction = { action: string; title: string; icon?: string }

interface ExtendedNotificationOptions extends NotificationOptions {
  renotify?: boolean
  timestamp?: number
  actions?: NotificationAction[]
}

const PAGE_CACHE = "pages"
const API_CACHE = "api"
const ASSET_CACHE = "assets"
const MEDIA_CACHE = "media"

precacheAndRoute(self.__WB_MANIFEST)
cleanupOutdatedCaches()

self.addEventListener("install", (event) => {
  self.skipWaiting()
  event.waitUntil(
    caches.open(PAGE_CACHE).then((cache) => cache.addAll(["/dashboard", "/news", "/schedule", "/events", "/profile"]))
  )
})

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim())
})

self.addEventListener("message", (event) => {
  const msg = event.data
  if (msg && msg.type === "SKIP_WAITING") {
    self.skipWaiting()
  }
})

const pageStrategy = new NetworkFirst({
  cacheName: PAGE_CACHE,
  networkTimeoutSeconds: 4,
})

warmStrategyCache({
  urls: ["/", "/dashboard", "/news", "/schedule", "/events", "/profile"],
  strategy: pageStrategy,
})

registerRoute(
  ({ request }: { request: Request }) => request.mode === "navigate",
  async ({ event, request }: { event: ExtendableEvent; request: Request }) => {
    try {
      if (typeof pageStrategy.handle === "function") {
        return await pageStrategy.handle({ event, request })
      }
      return await fetch(request)
    } catch (error) {
      const cache = await caches.open(PAGE_CACHE)
      const cached = await cache.match("/dashboard")
      return cached || Response.redirect("/dashboard")
    }
  }
)

registerRoute(
  ({ request }: { request: Request }) => ["style", "script", "worker"].includes(request.destination),
  new StaleWhileRevalidate({ cacheName: ASSET_CACHE })
)

registerRoute(
  ({ url, request }: { url: URL; request: Request }) =>
    url.origin === self.location.origin && request.destination === "image",
  new CacheFirst({ cacheName: MEDIA_CACHE, matchOptions: { ignoreVary: true } })
)

registerRoute(
  ({ url }: { url: URL }) => url.pathname.startsWith("/api"),
  new NetworkFirst({ cacheName: API_CACHE, networkTimeoutSeconds: 6 })
)

self.addEventListener("push", (event) => {
  let data: any = {}
  try {
    data = event.data ? event.data.json() : {}
  } catch (err) {
    try {
      data = { title: "Уведомление", body: event.data ? event.data.text() : "" }
    } catch (error) {
      data = { title: "Уведомление" }
    }
  }

  const idTag = data.id != null ? `app:id:${data.id}` : undefined
  const typeTag = data.type ? `app:${data.type}` : undefined
  const title = data.title || "Уведомление"
  const options: ExtendedNotificationOptions = {
    body: data.body || "",
    tag: data.tag || idTag || typeTag,
    renotify: Boolean(data.renotify),
    requireInteraction: Boolean(data.requireInteraction),
    icon: data.icon || "/guu_logo.png",
    badge: data.badge || "/guu_logo.png",
    timestamp: data.timestamp || Date.now(),
    data: { url: data.url || data.click_action || "/", id: data.id ?? null, type: data.type ?? null, raw: data },
    actions: Array.isArray(data.actions) ? data.actions.slice(0, 2) : [],
  }

  event.waitUntil(
    (async () => {
      if (self.navigator && (self.navigator as any).setAppBadge && typeof data.unreadCount === "number") {
        try {
          if (data.unreadCount > 0) await (self.navigator as any).setAppBadge(data.unreadCount)
          else await (self.navigator as any).clearAppBadge?.()
        } catch (err) {}
      }

      await self.registration.showNotification(title, options)
      try {
        const clients = await self.clients.matchAll({ type: "window", includeUncontrolled: true })
        for (const client of clients) client.postMessage({ type: "PUSH_NOTIFICATION", payload: { title, ...options } })
      } catch (err) {}
    })()
  )
})

self.addEventListener("notificationclick", (event) => {
  const notification = event.notification
  const targetUrl = notification?.data?.url || notification?.data?.raw?.url || "/"
  notification.close()

  event.waitUntil(
    (async () => {
      const absolute = new URL(targetUrl, self.location.origin).href
      const clientList = await self.clients.matchAll({ type: "window", includeUncontrolled: true })
      for (const client of clientList) {
        try {
          const href = new URL(client.url, self.location.origin).href
          if (href.startsWith(self.location.origin)) {
            if ("navigate" in client) await (client as WindowClient).navigate(absolute)
            if ("focus" in client) return client.focus()
          }
        } catch (error) {}
      }
      return self.clients.openWindow(absolute)
    })()
  )
})

self.addEventListener("notificationclose", (event) => {
  const notification = event.notification
  event.waitUntil(
    (async () => {
      try {
        const clients = await self.clients.matchAll({ type: "window", includeUncontrolled: true })
        for (const client of clients) client.postMessage({ type: "NOTIFICATION_CLOSED", id: notification?.data?.id ?? null })
      } catch (error) {}
    })()
  )
})

export {}
