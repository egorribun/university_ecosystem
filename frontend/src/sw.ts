/// <reference lib="webworker" />
declare const self: ServiceWorkerGlobalScope

import { clientsClaim } from "workbox-core"

import { initApiCaching, clearSessionCaches, setSessionHash } from "./sw/api"
import { error, log } from "./sw/logger"
import { initMediaCaching } from "./sw/media"
import { initOfflineQueue, processOfflineQueues } from "./sw/offline"
import { initPrecaching } from "./sw/precaching"
import { initPushHandlers } from "./sw/push"

import * as offline from "./sw/offline"
import { handleMediaRequest } from "./sw/media"

// Re-exports for test compatibility
export const queueStores = {
  storePendingNavigation: offline.storePendingNavigation,
  readPendingNavigations: offline.readPendingNavigations,
  storePendingReport: offline.storePendingReport,
  readPendingReports: offline.readPendingReports,
}

export const queueProcessors = {
  processPendingNavigations: offline.processPendingNavigations,
  processPendingReports: offline.processPendingReports,
  processAllQueues: offline.processOfflineQueues,
}

export const queueSanitizers = {
  sanitizeReportPayload: offline.sanitizeReportPayload,
}

export const queueSyncTags = {
  navigation: "navigation-sync",
  newsInteraction: "news-interaction:sync",
}

/**
 * World-Class Modular Service Worker Entry Point
 */
async function bootstrap() {
  try {
    // 1. Core Workbox setup
    clientsClaim()
    self.skipWaiting()

    // 2. Initialize modules
    initPrecaching()
    initApiCaching()
    initMediaCaching()
    await initOfflineQueue()
    initPushHandlers()

    // 3. Register testing helper
    self.__SW_TESTING__ = {
      storePendingNavigation: offline.storePendingNavigation,
      storePendingReport: offline.storePendingReport,
      readPendingNavigations: offline.readPendingNavigations,
      readPendingReports: offline.readPendingReports,
      processPendingNavigations: offline.processPendingNavigations,
      processPendingReports: offline.processPendingReports,
      processAllQueues: offline.processOfflineQueues,
      handleMediaRequest,
    }

    // 4. Initial sync
    if (import.meta.env.MODE !== "test") {
      await processOfflineQueues()
    }

    if (import.meta.env.DEV) {
      log("Bootstrap complete")
    }
  } catch (err) {
    error("SW bootstrap failed", err)
  }
}

// Start bootstrap
bootstrap()

import { SERVICE_WORKER_MESSAGE_TYPES } from "./constants/serviceWorkerMessages"

// Global Message Listener
self.addEventListener("message", (event) => {
  // Require both data and a traceable source — messages without a source
  // (e.g. from BroadcastChannel or non-Window clients) are rejected to
  // prevent future code paths from accidentally bypassing origin validation.
  if (!event.data || typeof event.data !== "object") return
  if (!event.source || !("url" in event.source)) return

  // RED-03 (audit Wave 11): Use event.origin (browser-enforced per HTML §8.7.3)
  // instead of deriving origin from WindowClient.url.
  // WindowClient.url is a mutable JS property that a compromised page or extension
  // could potentially spoof; event.origin is set by the browser from the sender's
  // Realm and cannot be overridden by JavaScript code.
  const swOrigin = self.location.origin
  if (!event.origin || event.origin !== swOrigin) {
    if (import.meta.env.DEV) {
      console.warn("[SW] Rejected postMessage from foreign origin:", event.origin)
    }
    return
  }

  switch (event.data.type) {
    case SERVICE_WORKER_MESSAGE_TYPES.SKIP_WAITING:
      self.skipWaiting()
      break
    case SERVICE_WORKER_MESSAGE_TYPES.SET_API_SESSION_CACHE_KEY: {
      // Strict type guard — sessionHash must be a non-empty string of reasonable length
      // to prevent null/object/oversized-string injection via postMessage.
      const hash = event.data.sessionHash
      if (typeof hash === "string" && hash.length > 0 && hash.length <= 128) {
        setSessionHash(hash)
      }
      break
    }
    case SERVICE_WORKER_MESSAGE_TYPES.CLEAR_API_CACHE:
      event.waitUntil(clearSessionCaches())
      break
    case SERVICE_WORKER_MESSAGE_TYPES.PROCESS_NOTIFICATION_CLICK_QUEUE:
    case SERVICE_WORKER_MESSAGE_TYPES.PROCESS_OFFLINE_QUEUES:
      event.waitUntil(processOfflineQueues())
      break
  }
})

// Background Sync Listener
self.addEventListener("sync", (event) => {
  const syncEvent = event as ExtendableEvent & { tag: string }
  if (
    syncEvent.tag === queueSyncTags.newsInteraction ||
    syncEvent.tag === queueSyncTags.navigation
  ) {
    syncEvent.waitUntil(processOfflineQueues())
  }
})
