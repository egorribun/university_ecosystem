/// <reference lib="webworker" />
declare const self: ServiceWorkerGlobalScope

import { clientsClaim } from "workbox-core"

import { initApiCaching, clearSessionCaches, setSessionHash } from "./sw/api"
import { error } from "./sw/logger"
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
    ;(self as any).__SW_TESTING__ = {
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
    await processOfflineQueues()

    console.log("[SW] Bootstrap complete")
  } catch (err) {
    error("SW bootstrap failed", err)
  }
}

// Start bootstrap
bootstrap()

import { SERVICE_WORKER_MESSAGE_TYPES } from "./constants/serviceWorkerMessages"

// Global Message Listener
self.addEventListener("message", (event) => {
  if (!event.data) return

  switch (event.data.type) {
    case SERVICE_WORKER_MESSAGE_TYPES.SKIP_WAITING:
      self.skipWaiting()
      break
    case SERVICE_WORKER_MESSAGE_TYPES.SET_API_SESSION_CACHE_KEY:
      if (event.data.sessionHash !== undefined) {
        setSessionHash(event.data.sessionHash)
      }
      break
    case SERVICE_WORKER_MESSAGE_TYPES.CLEAR_API_CACHE:
      event.waitUntil(clearSessionCaches())
      break
    case SERVICE_WORKER_MESSAGE_TYPES.PROCESS_NOTIFICATION_CLICK_QUEUE:
    case "PROCESS_OFFLINE_QUEUES":
      event.waitUntil(processOfflineQueues())
      break
  }
})
