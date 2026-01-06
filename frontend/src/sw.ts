/// <reference lib="webworker" />
declare const self: ServiceWorkerGlobalScope;

import { clientsClaim } from "workbox-core";

import { initApiCaching, clearSessionCaches } from "./sw/api";
import { error } from "./sw/logger";
import { initMediaCaching } from "./sw/media";
import { initOfflineQueue, processOfflineQueues } from "./sw/offline";
import { initPrecaching } from "./sw/precaching";
import { initPushHandlers } from "./sw/push";

/**
 * World-Class Modular Service Worker Entry Point
 */
async function bootstrap() {
  try {
    // 1. Core Workbox setup
    clientsClaim();
    self.skipWaiting();

    // 2. Initialize modules
    initPrecaching();
    initApiCaching();
    initMediaCaching();
    await initOfflineQueue();
    initPushHandlers();

    // 3. Initial sync
    await processOfflineQueues();

    console.log("[SW] Bootstrap complete");
  } catch (err) {
    error("SW bootstrap failed", err);
  }
}

// Start bootstrap
bootstrap();

// Global Message Listener
self.addEventListener("message", (event) => {
  if (!event.data) return;

  switch (event.data.type) {
    case "SKIP_WAITING":
      self.skipWaiting();
      break;
    case "CLEAR_SESSION_CACHES":
      event.waitUntil(clearSessionCaches());
      break;
    case "PROCESS_OFFLINE_QUEUES":
      event.waitUntil(processOfflineQueues());
      break;
  }
});
