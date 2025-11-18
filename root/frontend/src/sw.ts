/// <reference lib="webworker" />

import {
  cleanupOutdatedCaches,
  precacheAndRoute,
  createHandlerBoundToURL,
} from "workbox-precaching"
import { clientsClaim } from "workbox-core"
import type { RouteHandlerCallbackOptions } from "workbox-core"
import { registerRoute, NavigationRoute } from "workbox-routing"
import { StaleWhileRevalidate, CacheFirst, NetworkFirst } from "workbox-strategies"
import { CacheExpiration, ExpirationPlugin } from "workbox-expiration"
import {
  NotificationData,
  buildNotificationDetails,
  parsePushEventData,
} from "@/push/notification-helpers"
import { logError, logWarning } from "@/app/logger"
import { SERVICE_WORKER_MESSAGE_TYPES } from "@/constants/serviceWorkerMessages"

declare const self: ServiceWorkerGlobalScope & typeof globalThis

const OFFLINE_URL = "/offline.html"
const API_CACHE = "api-cache"
const API_CACHE_SESSION_PREFIX = `${API_CACHE}:`
const MEDIA_PUBLIC_CACHE = "media-public"
const MEDIA_PRIVATE_CACHE_PREFIX = "media-private:"
const MEDIA_CACHE_LIMITS = { maxEntries: 200, maxAgeSeconds: 24 * 60 * 60 }
const IMG_CACHE = "img-cache"
const BACKEND_STATIC_CACHE = "backend-static"
const CLICK_DB_NAME = "notification-interactions"
const CLICK_DB_VERSION = 1
const NAVIGATION_STORE = "pending-navigations"
const REPORT_STORE = "pending-reports"
const NAVIGATION_SYNC_TAG = "notification-click:navigation"
const REPORT_SYNC_TAG = "notification-click:report"
const PROCESS_QUEUE_MESSAGE = SERVICE_WORKER_MESSAGE_TYPES.PROCESS_NOTIFICATION_CLICK_QUEUE

const apiStrategies = new Map<string, StaleWhileRevalidate>()
const mediaCacheExpirations = new Map<string, CacheExpiration>()
let sessionCacheHash: string | null = null

const API_CACHE_PLUGIN = new ExpirationPlugin({ maxEntries: 100, maxAgeSeconds: 60 * 60 })

const getApiCacheName = () =>
  sessionCacheHash && sessionCacheHash.length > 0
    ? `${API_CACHE_SESSION_PREFIX}${sessionCacheHash}`
    : API_CACHE

const getApiStrategy = () => {
  const cacheName = getApiCacheName()
  const existing = apiStrategies.get(cacheName)
  if (existing) {
    return existing
  }

  const strategy = new StaleWhileRevalidate({
    cacheName,
    plugins: [API_CACHE_PLUGIN],
  })
  apiStrategies.set(cacheName, strategy)
  return strategy
}

const purgeSessionCaches = async () => {
  const cacheKeys = await caches.keys()
  const deletions = cacheKeys
    .filter(
      (key) =>
        key === API_CACHE ||
        key.startsWith(API_CACHE_SESSION_PREFIX) ||
        key.startsWith(MEDIA_PRIVATE_CACHE_PREFIX)
    )
    .map(async (key) => {
      const tracker = mediaCacheExpirations.get(key)
      if (tracker) {
        mediaCacheExpirations.delete(key)
        try {
          await tracker.delete()
        } catch {
          /* ignore */
        }
      }
      await caches.delete(key)
    })
  apiStrategies.clear()
  await Promise.all(deletions)
}

const setSessionCacheKey = (hash: unknown) => {
  if (typeof hash === "string" && hash.length > 0) {
    sessionCacheHash = hash
  } else {
    sessionCacheHash = null
  }
  apiStrategies.clear()
}

const getMediaSessionCacheName = () =>
  sessionCacheHash && sessionCacheHash.length > 0
    ? `${MEDIA_PRIVATE_CACHE_PREFIX}${sessionCacheHash}`
    : null

const getMediaCacheExpiration = (cacheName: string) => {
  let expiration = mediaCacheExpirations.get(cacheName)
  if (!expiration) {
    expiration = new CacheExpiration(cacheName, MEDIA_CACHE_LIMITS)
    mediaCacheExpirations.set(cacheName, expiration)
  }
  return expiration
}

const matchMediaCaches = async (request: Request) => {
  const cacheNames: (string | null)[] = [getMediaSessionCacheName(), MEDIA_PUBLIC_CACHE]
  for (const cacheName of cacheNames) {
    if (!cacheName) continue
    const cache = await caches.open(cacheName)
    const match = await cache.match(request)
    if (match) {
      return match
    }
  }
  return null
}

const hasPublicCacheControl = (response: Response) => {
  const cacheControl = response.headers.get("Cache-Control")
  return cacheControl ? /\bpublic\b/i.test(cacheControl) : false
}

const hasSignedUrlFlag = (response: Response) => {
  const signedHeaders = ["x-media-signed-url", "x-signed-url", "x-media-signed"]
  return signedHeaders.some((header) => {
    const value = response.headers.get(header)
    if (!value) return false
    const normalized = value.trim().toLowerCase()
    return normalized !== "0" && normalized !== "false"
  })
}

const shouldTreatAsPublicMedia = (response: Response) =>
  hasPublicCacheControl(response) || hasSignedUrlFlag(response)

const cacheMediaResponse = async (request: Request, response: Response, event?: FetchEvent) => {
  if (!response.ok || request.method !== "GET") {
    return
  }
  const cacheName = shouldTreatAsPublicMedia(response)
    ? MEDIA_PUBLIC_CACHE
    : getMediaSessionCacheName()
  if (!cacheName) {
    return
  }

  try {
    const cache = await caches.open(cacheName)
    await cache.put(request, response)
  } catch (error) {
    logWarning("SW: failed to cache media response", error)
    return
  }

  const expiration = getMediaCacheExpiration(cacheName)
  const maintenance = Promise.all([
    expiration.updateTimestamp(request.url),
    expiration.expireEntries(),
  ]).catch((error) => {
    logWarning("SW: failed to update media cache expiration", error)
  })
  if (event) {
    try {
      event.waitUntil(maintenance)
    } catch {
      void maintenance
    }
  } else {
    void maintenance
  }
}

const mediaRouteHandler = async ({ event }: RouteHandlerCallbackOptions) => {
  const fetchEvent = event as FetchEvent
  const request = fetchEvent.request
  if (request.method !== "GET") {
    return fetch(request)
  }
  try {
    const response = await fetch(request)
    const clone = response.clone()
    void cacheMediaResponse(request, clone, fetchEvent)
    return response
  } catch (error) {
    const cached = await matchMediaCaches(request)
    if (cached) {
      return cached
    }
    throw error
  }
}

type PendingNavigation = {
  id?: number
  url: string
  action?: string | null
  timestamp: number
}

type PendingReport = PendingNavigation & {
  reportUrl: string
  payload?: Record<string, unknown>
}

type SyncManagerLike = {
  register: (tag: string) => Promise<void>
}

type SyncEventLike = Event & {
  tag: string
  waitUntil: (promise: Promise<unknown>) => void
}

const hasIndexedDbSupport = () => "indexedDB" in self

function openDatabase(): Promise<IDBDatabase> {
  if (!hasIndexedDbSupport()) {
    return Promise.reject(new Error("IndexedDB is not available in this environment"))
  }

  return new Promise((resolve, reject) => {
    const request = indexedDB.open(CLICK_DB_NAME, CLICK_DB_VERSION)

    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(NAVIGATION_STORE)) {
        db.createObjectStore(NAVIGATION_STORE, {
          keyPath: "id",
          autoIncrement: true,
        })
      }
      if (!db.objectStoreNames.contains(REPORT_STORE)) {
        db.createObjectStore(REPORT_STORE, {
          keyPath: "id",
          autoIncrement: true,
        })
      }
    }

    request.onsuccess = () => {
      resolve(request.result)
    }

    request.onerror = () => {
      reject(request.error ?? new Error("Failed to open IndexedDB"))
    }
  })
}

function attachTransactionFinalizers(db: IDBDatabase, tx: IDBTransaction) {
  const close = () => {
    try {
      db.close()
    } catch (error) {
      logError("SW: failed to close IndexedDB connection", error)
    }
  }
  tx.addEventListener("complete", close)
  tx.addEventListener("abort", close)
  tx.addEventListener("error", close)
}

async function addRecord<T extends object>(storeName: string, value: T): Promise<number> {
  const db = await openDatabase()
  return await new Promise<number>((resolve, reject) => {
    const tx = db.transaction(storeName, "readwrite")
    attachTransactionFinalizers(db, tx)
    const store = tx.objectStore(storeName)
    const request = store.add(value)
    request.onsuccess = () => {
      resolve(request.result as number)
    }
    request.onerror = () => {
      reject(request.error ?? new Error("Failed to persist record"))
    }
  })
}

async function getAllRecords<T>(storeName: string): Promise<T[]> {
  const db = await openDatabase()
  return await new Promise<T[]>((resolve, reject) => {
    const tx = db.transaction(storeName, "readonly")
    attachTransactionFinalizers(db, tx)
    const store = tx.objectStore(storeName)
    const request = store.getAll()
    request.onsuccess = () => {
      resolve(request.result as T[])
    }
    request.onerror = () => {
      reject(request.error ?? new Error("Failed to read records"))
    }
  })
}

async function deleteRecord(storeName: string, id: number): Promise<void> {
  const db = await openDatabase()
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(storeName, "readwrite")
    attachTransactionFinalizers(db, tx)
    const store = tx.objectStore(storeName)
    const request = store.delete(id)
    request.onsuccess = () => resolve()
    request.onerror = () => {
      reject(request.error ?? new Error("Failed to delete record"))
    }
  })
}

export const queueDbModule = {
  hasIndexedDbSupport,
  openDatabase,
  addRecord,
  getAllRecords,
  deleteRecord,
}

function sanitizeValue(value: unknown, depth = 0): unknown {
  if (value === null || value === undefined) {
    return value
  }

  if (depth > 5) {
    return undefined
  }

  const type = typeof value
  if (type === "string" || type === "number" || type === "boolean") {
    return value
  }

  if (value instanceof Date) {
    return value.toISOString()
  }

  if (Array.isArray(value)) {
    const result = value
      .map((entry) => sanitizeValue(entry, depth + 1))
      .filter((entry) => entry !== undefined)
    return result
  }

  if (type === "object") {
    const result: Record<string, unknown> = {}
    for (const [key, nested] of Object.entries(value as Record<string, unknown>)) {
      if (typeof key !== "string") continue
      const sanitized = sanitizeValue(nested, depth + 1)
      if (sanitized !== undefined) {
        result[key] = sanitized
      }
    }
    return result
  }

  return undefined
}

function sanitizeReportPayload(value: unknown): Record<string, unknown> | undefined {
  const sanitized = sanitizeValue(value)
  if (sanitized && typeof sanitized === "object" && !Array.isArray(sanitized)) {
    return sanitized as Record<string, unknown>
  }
  return undefined
}

export const queueSanitizers = {
  sanitizeValue,
  sanitizeReportPayload,
}

async function storePendingNavigation(record: PendingNavigation): Promise<void> {
  try {
    await addRecord(NAVIGATION_STORE, record)
  } catch (error) {
    logError("SW: failed to queue navigation", error)
  }
}

async function storePendingReport(record: PendingReport): Promise<void> {
  try {
    await addRecord(REPORT_STORE, record)
  } catch (error) {
    logError("SW: failed to queue click report", error)
  }
}

async function readPendingNavigations(): Promise<PendingNavigation[]> {
  try {
    return await getAllRecords<PendingNavigation>(NAVIGATION_STORE)
  } catch (error) {
    logError("SW: failed to read queued navigations", error)
    return []
  }
}

async function readPendingReports(): Promise<PendingReport[]> {
  try {
    return await getAllRecords<PendingReport>(REPORT_STORE)
  } catch (error) {
    logError("SW: failed to read queued click reports", error)
    return []
  }
}

async function removePendingNavigation(id: number): Promise<void> {
  try {
    await deleteRecord(NAVIGATION_STORE, id)
  } catch (error) {
    logError("SW: failed to remove queued navigation", error)
  }
}

async function removePendingReport(id: number): Promise<void> {
  try {
    await deleteRecord(REPORT_STORE, id)
  } catch (error) {
    logError("SW: failed to remove queued click report", error)
  }
}

export const queueStores = {
  storePendingNavigation,
  storePendingReport,
  readPendingNavigations,
  readPendingReports,
  removePendingNavigation,
  removePendingReport,
}

function isOnline(): boolean {
  if (typeof self.navigator === "undefined") return true
  if (typeof self.navigator.onLine === "boolean") {
    return self.navigator.onLine
  }
  return true
}

async function scheduleSync(tag: string): Promise<boolean> {
  const registration = self.registration as ServiceWorkerRegistration & {
    sync?: SyncManagerLike
  }

  const syncManager = registration.sync
  if (!syncManager) {
    return false
  }

  try {
    await syncManager.register(tag)
    return true
  } catch (error) {
    logWarning(`SW: failed to register sync task "${tag}"`, error)
    return false
  }
}

async function focusOrOpenClient(targetUrl: string): Promise<boolean> {
  try {
    const allClients = await self.clients.matchAll({
      type: "window",
      includeUncontrolled: true,
    })

    const absoluteTarget = new URL(targetUrl, self.registration.scope).href

    for (const client of allClients) {
      const windowClient = client as WindowClient
      const clientUrl = new URL(windowClient.url, self.registration.scope).href
      if (clientUrl === absoluteTarget) {
        if ("focus" in windowClient) {
          await windowClient.focus()
        }
        return true
      }
      if (clientUrl.startsWith(self.registration.scope) && "navigate" in windowClient) {
        await windowClient.navigate(absoluteTarget)
        if ("focus" in windowClient) {
          await windowClient.focus()
        }
        return true
      }
    }

    if (self.clients.openWindow) {
      await self.clients.openWindow(absoluteTarget)
      return true
    }
  } catch (error) {
    logError("SW: failed to open client for notification click", error)
  }

  return false
}

async function sendClickReport(record: PendingReport): Promise<boolean> {
  const bodyObject: Record<string, unknown> = {
    action: record.action ?? null,
    url: record.url,
    timestamp: record.timestamp,
  }

  if (record.payload) {
    for (const [key, value] of Object.entries(record.payload)) {
      bodyObject[key] = value
    }
  }

  const body = JSON.stringify(bodyObject)

  const nav = self.navigator as { sendBeacon?: (url: string, data?: BodyInit) => boolean }
  if (typeof nav?.sendBeacon === "function" && isOnline()) {
    try {
      if (nav.sendBeacon(record.reportUrl, body)) {
        return true
      }
    } catch (error) {
      logWarning("SW: sendBeacon failed for click report", error)
    }
  }

  try {
    const response = await fetch(record.reportUrl, {
      method: "POST",
      headers: {
        "content-type": "application/json",
      },
      body,
      credentials: "include",
      keepalive: true,
    })

    return response.ok
  } catch (error) {
    logWarning("SW: click report request failed", error)
    return false
  }
}

async function processPendingNavigations(): Promise<void> {
  if (!isOnline()) {
    return
  }

  const records = await readPendingNavigations()
  for (const record of records) {
    if (typeof record?.id !== "number") continue
    const success = await focusOrOpenClient(record.url)
    if (success) {
      await removePendingNavigation(record.id)
    } else {
      break
    }
  }
}

async function processPendingReports(): Promise<void> {
  if (!isOnline()) {
    return
  }

  const records = await readPendingReports()
  for (const record of records) {
    if (typeof record?.id !== "number") continue
    const delivered = await sendClickReport(record)
    if (delivered) {
      await removePendingReport(record.id)
    } else {
      if (!isOnline()) {
        break
      }
      break
    }
  }
}

async function processAllQueues(): Promise<void> {
  await processPendingNavigations()
  await processPendingReports()
}

export const queueProcessors = {
  processPendingNavigations,
  processPendingReports,
  processAllQueues,
}

export const queueSyncTags = {
  navigation: NAVIGATION_SYNC_TAG,
  report: REPORT_SYNC_TAG,
}

type ServiceWorkerTestingApi = {
  storePendingNavigation: typeof storePendingNavigation
  storePendingReport: typeof storePendingReport
  readPendingNavigations: typeof readPendingNavigations
  readPendingReports: typeof readPendingReports
  processPendingNavigations: typeof processPendingNavigations
  processPendingReports: typeof processPendingReports
  processAllQueues: typeof processAllQueues
  handleMediaRequest: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>
}

declare global {
  interface ServiceWorkerGlobalScope {
    __SW_TESTING__?: ServiceWorkerTestingApi
  }
}

if (import.meta.env.MODE === "test") {
  self.__SW_TESTING__ = {
    storePendingNavigation,
    storePendingReport,
    readPendingNavigations,
    readPendingReports,
    processPendingNavigations,
    processPendingReports,
    processAllQueues,
    handleMediaRequest: (input: RequestInfo | URL, init?: RequestInit) => {
      const request = new Request(input, init)
      const event = Object.assign(Object.create(null), {
        request,
        waitUntil: (promise: Promise<unknown>) => promise,
      }) as FetchEvent
      return mediaRouteHandler({ event, request, url: new URL(request.url) })
    },
  }
}

cleanupOutdatedCaches()
precacheAndRoute(self.__WB_MANIFEST)
clientsClaim()
void self.skipWaiting()
void processAllQueues()

self.addEventListener("message", (event) => {
  if (!event.data || typeof event.data !== "object" || !("type" in event.data)) {
    return
  }

  const message = event.data as { type?: string; sessionHash?: unknown }
  const type = message.type
  if (type === SERVICE_WORKER_MESSAGE_TYPES.SKIP_WAITING) {
    void self.skipWaiting()
  } else if (type === PROCESS_QUEUE_MESSAGE) {
    event.waitUntil(processAllQueues())
  } else if (type === SERVICE_WORKER_MESSAGE_TYPES.CLEAR_API_CACHE) {
    event.waitUntil(purgeSessionCaches())
  } else if (type === SERVICE_WORKER_MESSAGE_TYPES.SET_API_SESSION_CACHE_KEY) {
    setSessionCacheKey(message.sessionHash)
  }
})

self.addEventListener("sync", (event) => {
  const syncEvent = event as SyncEventLike
  if (syncEvent.tag === NAVIGATION_SYNC_TAG) {
    syncEvent.waitUntil(processPendingNavigations())
  } else if (syncEvent.tag === REPORT_SYNC_TAG) {
    syncEvent.waitUntil(processPendingReports())
  }
})

const navigationHandler = createHandlerBoundToURL(OFFLINE_URL)

registerRoute(
  new NavigationRoute(
    async (options) => {
      const { event, request, url } = options
      const fetchEvent = event as FetchEvent

      if (!/^\/[^_].*/.test(url.pathname)) {
        return fetch(request)
      }

      try {
        const preload =
          "preloadResponse" in fetchEvent ? await fetchEvent.preloadResponse : undefined
        if (preload) {
          return preload
        }

        return await fetch(request)
      } catch (error) {
        return navigationHandler(options)
      }
    },
    { allowlist: [/^\/[^_].*/] }
  )
)

registerRoute(
  ({ url }) => /\/api\/(news|schedule)/.test(url.pathname),
  (options) => getApiStrategy().handle(options)
)

registerRoute(
  ({ url }) => url.pathname.startsWith("/static/"),
  new NetworkFirst({
    cacheName: BACKEND_STATIC_CACHE,
    plugins: [new ExpirationPlugin({ maxEntries: 200, maxAgeSeconds: 24 * 60 * 60 })],
  })
)

registerRoute(({ url }) => url.pathname.startsWith("/media/"), mediaRouteHandler, "GET")

registerRoute(
  ({ request }) => request.destination === "image",
  new CacheFirst({
    cacheName: IMG_CACHE,
    plugins: [new ExpirationPlugin({ maxEntries: 200, maxAgeSeconds: 7 * 24 * 60 * 60 })],
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
            body: options.body,
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
      const absoluteTarget = new URL(targetUrl, self.registration.scope).href
      const actionValue = typeof event.action === "string" && event.action ? event.action : null
      const timestamp = Date.now()

      const navigationRecord: PendingNavigation = {
        url: absoluteTarget,
        action: actionValue,
        timestamp,
      }

      const navigationHandled = await focusOrOpenClient(absoluteTarget)
      if (!navigationHandled) {
        await storePendingNavigation(navigationRecord)
        const scheduled = await scheduleSync(NAVIGATION_SYNC_TAG)
        if (!scheduled) {
          await processPendingNavigations()
        }
      }

      const rawReportUrl =
        typeof data.reportUrl === "string" && data.reportUrl ? data.reportUrl : undefined
      let reportUrl: string | undefined
      if (rawReportUrl) {
        try {
          reportUrl = new URL(rawReportUrl, self.registration.scope).href
        } catch (error) {
          logWarning("SW: failed to resolve report URL", error)
          reportUrl = rawReportUrl
        }
      }

      if (reportUrl) {
        const payloadFromData = sanitizeReportPayload(data.reportPayload)
        const additionalPayload: Record<string, unknown> = {}
        const rawId = (data as Record<string, unknown>).notificationId
        if (typeof rawId === "string" || typeof rawId === "number") {
          additionalPayload.notificationId = rawId
        }
        const rawAltId = (data as Record<string, unknown>).notification_id
        if (typeof rawAltId === "string" || typeof rawAltId === "number") {
          additionalPayload.notification_id = rawAltId
        }

        let payload: Record<string, unknown> | undefined
        if (payloadFromData) {
          payload = { ...payloadFromData, ...additionalPayload }
        } else if (Object.keys(additionalPayload).length) {
          payload = additionalPayload
        }

        const reportRecord: PendingReport = {
          ...navigationRecord,
          reportUrl,
          payload,
        }

        if (isOnline()) {
          const delivered = await sendClickReport(reportRecord)
          if (!delivered) {
            await storePendingReport(reportRecord)
            const scheduled = await scheduleSync(REPORT_SYNC_TAG)
            if (!scheduled) {
              await processPendingReports()
            }
          }
        } else {
          await storePendingReport(reportRecord)
          const scheduled = await scheduleSync(REPORT_SYNC_TAG)
          if (!scheduled) {
            await processPendingReports()
          }
        }
      }
    })()
  )
})
