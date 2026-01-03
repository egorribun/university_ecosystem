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
import { SERVICE_WORKER_MESSAGE_TYPES } from "@/constants/serviceWorkerMessages"

const log = (method: "error" | "warn" | "info", ...args: unknown[]) => {
  const target = typeof console !== "undefined" ? console[method] : undefined
  if (typeof target === "function") {
    target(...(args as unknown[]))
  }
}

const logError = (...args: unknown[]) => log("error", ...args)
const logWarning = (...args: unknown[]) => log("warn", ...args)

declare const self: ServiceWorkerGlobalScope & typeof globalThis

const OFFLINE_URL = "/offline.html"
const APP_SHELL_URL = "/index.html"
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
const NEWS_INTERACTION_STORE = "pending-news-interactions"
const NAVIGATION_SYNC_TAG = "notification-click:navigation"
const REPORT_SYNC_TAG = "notification-click:report"
const NEWS_INTERACTION_SYNC_TAG = "news-interaction:sync"
const PROCESS_QUEUE_MESSAGE = SERVICE_WORKER_MESSAGE_TYPES.PROCESS_NOTIFICATION_CLICK_QUEUE

async function broadcastMessage(message: any): Promise<void> {
  const clients = await self.clients.matchAll({ type: "window" })
  for (const client of clients) {
    client.postMessage(message)
  }
}

const apiStrategies = new Map<string, StaleWhileRevalidate>()
const mediaCacheExpirations = new Map<string, CacheExpiration>()
let sessionCacheHash: string | null = null

const API_CACHE_PLUGIN = new ExpirationPlugin({ maxEntries: 100, maxAgeSeconds: 60 * 60 })

type ApiFallbackKind = "news" | "schedule" | "events"

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

const offlineApiPayload: Record<ApiFallbackKind, unknown> = {
  news: [],
  schedule: [],
  events: { items: [], total: 0, limit: 0, cursor: null, next_cursor: null, has_more: false },
}

const buildOfflineApiResponse = (kind: ApiFallbackKind) =>
  new Response(JSON.stringify(offlineApiPayload[kind]), {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      "X-Offline-Fallback": "1",
      "X-Offline-Resource": kind,
    },
  })

const matchApiCache = async (request: Request) => {
  try {
    const cache = await caches.open(getApiCacheName())
    const cached = await cache.match(request)
    return cached ?? null
  } catch (error) {
    logWarning("SW: failed to read cached API response", error)
    return null
  }
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
    if (response && typeof response.clone === "function") {
      const clone = response.clone()
      void cacheMediaResponse(request, clone, fetchEvent)
    }
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
      if (!db.objectStoreNames.contains(NEWS_INTERACTION_STORE)) {
        db.createObjectStore(NEWS_INTERACTION_STORE, {
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
  await processPendingNewsInteractions()
}

async function processPendingNewsInteractions(): Promise<void> {
  if (!isOnline()) {
    return
  }

  const db = await openDatabase()
  const tx = db.transaction(NEWS_INTERACTION_STORE, "readonly")
  const store = tx.objectStore(NEWS_INTERACTION_STORE)
  const records = (await new Promise<any[]>((resolve, reject) => {
    const req = store.getAll()
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })) as any[]

  let processedCount = 0
  for (const record of records) {
    try {
      const response = await fetch(record.url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(record.payload),
        credentials: "include",
      })

      if (response.ok) {
        await deleteRecord(NEWS_INTERACTION_STORE, record.id)
        processedCount++
      } else if (response.status === 401 || response.status === 403 || response.status === 404) {
        // Drop records that will never succeed
        await deleteRecord(NEWS_INTERACTION_STORE, record.id)
      } else {
        // Transient error, stop and retry later
        break
      }
    } catch (error) {
      logWarning("SW: failed to sync news interaction", error)
      break
    }
  }

  if (processedCount > 0) {
    await broadcastMessage({ type: "SYNC_COMPLETE" })
  }
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

try {
  cleanupOutdatedCaches()
  const wbManifest = self.__WB_MANIFEST
  const manifestEntries = Array.isArray(wbManifest) ? wbManifest : []
  const entriesWithoutRevision = manifestEntries.filter(
    (entry) => !entry || typeof entry !== "object" || !("revision" in entry)
  )
  if (entriesWithoutRevision.length > 0) {
    console.warn(
      "SW: precache entries without revision",
      entriesWithoutRevision.map((entry) => (typeof entry === "object" ? entry.url : entry))
    )
  }
  const shellRevision =
    (import.meta.env.VITE_APP_VERSION as string | undefined) ||
    (import.meta.env.APP_VERSION as string | undefined) ||
    "app-shell"
  // Filter out entries that conflict with our manual shell additions
  const excludedUrls = new Set([APP_SHELL_URL, OFFLINE_URL, "/index.html", "index.html"])
  const filteredManifestEntries = manifestEntries.filter((entry) => {
    const url = typeof entry === "string" ? entry : entry?.url
    return url && !excludedUrls.has(url)
  })
  precacheAndRoute([
    { url: APP_SHELL_URL, revision: shellRevision },
    { url: OFFLINE_URL, revision: shellRevision },
    ...filteredManifestEntries,
  ])
  clientsClaim()
  void self.skipWaiting()
  void processAllQueues()
} catch (error) {
  logError("SW bootstrap failed", error)
  throw error
}

registerRoute(
  new NavigationRoute(
    async (options) => {
      try {
        const cachedResponse = await caches.match(APP_SHELL_URL)
        if (cachedResponse) return cachedResponse
      } catch (e) {
        logError("SW: navigation route fallback failed", e)
      }
      return fetch(options.request)
    },
    { allowlist: [/^\/[^_].*/] }
  )
)

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
  } else if (syncEvent.tag === NEWS_INTERACTION_SYNC_TAG) {
    syncEvent.waitUntil(processPendingNewsInteractions())
  }
})

const offlineNavigationHandler = createHandlerBoundToURL(OFFLINE_URL)
const appShellNavigationHandler = createHandlerBoundToURL(APP_SHELL_URL)

const createApiHandler =
  (kind: ApiFallbackKind) => async (options: RouteHandlerCallbackOptions) => {
    try {
      return await getApiStrategy().handle(options)
    } catch (error) {
      logWarning(`SW: falling back to cached ${kind} response`, error)
      const cached = await matchApiCache(options.request)
      if (cached) {
        return cached
      }
      return buildOfflineApiResponse(kind)
    }
  }

const serveAppShellFromPrecache = async (options: RouteHandlerCallbackOptions) => {
  try {
    return await appShellNavigationHandler(options)
  } catch (error) {
    logWarning("SW: failed to load app shell from precache", error)
    return offlineNavigationHandler(options)
  }
}

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

        const response = await fetch(request)
        if (response.ok) {
          return response
        }

        return serveAppShellFromPrecache(options)
      } catch (error) {
        logWarning("SW: navigation fallback triggered", error)
        return serveAppShellFromPrecache(options)
      }
    },
    { allowlist: [/^\/[^_].*/] }
  )
)

registerRoute(({ url }) => /\/api\/news/.test(url.pathname), createApiHandler("news"))
registerRoute(({ url }) => /\/api\/schedule/.test(url.pathname), createApiHandler("schedule"))
registerRoute(({ url }) => /\/api\/events/.test(url.pathname), createApiHandler("events"))

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
