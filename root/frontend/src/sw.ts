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

type NotificationData = {
  url?: string
  actionUrls?: Record<string, string>
  [key: string]: unknown
}

type NotificationActionPayload = {
  action: string
  title: string
  icon?: string
  url?: string
}

type NotificationActionOption = {
  action: string
  title: string
  icon?: string
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
  actions?: NotificationActionPayload[]
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
    requireInteraction: payload.requireInteraction,
    silent: payload.silent,
  }

  const extendedOptions = options as NotificationOptions & {
    renotify?: boolean
    timestamp?: number
    vibrate?: number[]
    actions?: NotificationActionOption[]
  }

  if (payload.renotify !== undefined) {
    extendedOptions.renotify = payload.renotify
  }

  if (payload.timestamp !== undefined) {
    extendedOptions.timestamp = payload.timestamp
  }

  if (payload.vibrate) {
    extendedOptions.vibrate = payload.vibrate
  }

  if (payload.actions?.length) {
    const actionUrls: Record<string, string> = {}
    const validActions: NotificationActionOption[] = []
    for (const action of payload.actions) {
      if (!action || typeof action !== "object") continue
      const key = typeof action.action === "string" ? action.action.trim() : ""
      const title = typeof action.title === "string" ? action.title.trim() : ""
      if (!key || !title) continue
      const entry: NotificationActionOption = { action: key, title }
      if (action.icon && typeof action.icon === "string") {
        entry.icon = action.icon
      }
      validActions.push(entry)
      if (action.url && typeof action.url === "string" && action.url.trim()) {
        actionUrls[key] = action.url
      }
    }
    if (validActions.length) {
      extendedOptions.actions = validActions
      if (Object.keys(actionUrls).length) {
        data.actionUrls = actionUrls
      }
    }
  }

  event.waitUntil(self.registration.showNotification(title, options))
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
