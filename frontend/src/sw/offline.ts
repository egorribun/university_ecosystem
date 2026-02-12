/// <reference lib="webworker" />
declare const self: ServiceWorkerGlobalScope

import { openDB, type IDBPDatabase } from "idb"
import { log, warn } from "./logger"

const CLICK_DB_NAME = "notification-interactions"
const DB_VERSION = 3

export const STORES = {
  NAVIGATION: "pending-navigations",
  REPORT: "pending-reports",
  NEWS_INTERACTION: "pending-news-interactions",
} as const

/**
 * Get the database with proper upgrade handler.
 * All functions should use this instead of openDB directly.
 */
async function getDatabase() {
  return openDB(CLICK_DB_NAME, DB_VERSION, {
    upgrade(db) {
      if (!db.objectStoreNames.contains(STORES.NAVIGATION)) {
        db.createObjectStore(STORES.NAVIGATION, { keyPath: "id", autoIncrement: true })
      }
      if (!db.objectStoreNames.contains(STORES.REPORT)) {
        db.createObjectStore(STORES.REPORT, { keyPath: "id", autoIncrement: true })
      }
      if (!db.objectStoreNames.contains(STORES.NEWS_INTERACTION)) {
        db.createObjectStore(STORES.NEWS_INTERACTION, { keyPath: "id", autoIncrement: true })
      }
    },
  })
}

/**
 * Initialize IndexedDB for offline interaction queue.
 */
export async function initOfflineQueue() {
  await getDatabase()
}

function isOnline(): boolean {
  return self.navigator.onLine !== false
}

export async function addRecord<T extends object>(storeName: string, value: T) {
  const db = await getDatabase()
  return db.add(storeName, value)
}

export async function storePendingNavigation(record: { url: string; timestamp: number }) {
  return addRecord(STORES.NAVIGATION, record)
}

export async function readPendingNavigations() {
  const db = await getDatabase()
  return db.getAll(STORES.NAVIGATION)
}

export async function storePendingReport(record: {
  url: string
  reportUrl: string
  timestamp: number
  payload?: any
}) {
  return addRecord(STORES.REPORT, record)
}

export async function readPendingReports() {
  const db = await getDatabase()
  return db.getAll(STORES.REPORT)
}

export function sanitizeReportPayload(payload: any): any {
  if (!payload || typeof payload !== "object") return payload
  const result: any = Array.isArray(payload) ? [] : {}
  for (const key in payload) {
    const val = payload[key]
    if (typeof val === "function") continue
    if (val && typeof val === "object") {
      result[key] = sanitizeReportPayload(val)
    } else {
      result[key] = val
    }
  }
  return result
}

export async function processOfflineQueues() {
  if (!isOnline()) return

  log("Processing offline queues...")
  const db = await getDatabase()

  await Promise.all([
    processPendingNavigations(),
    processPendingReports(),
    processNewsInteractionQueue(db),
  ])
}

export async function processPendingNavigations() {
  if (!isOnline()) return
  const db = await getDatabase()
  const records = await db.getAll(STORES.NAVIGATION)
  for (const record of records) {
    log("Processing navigation", record)
    // In a real SW, this might involve clients.openWindow
    await db.delete(STORES.NAVIGATION, record.id)
  }
}

export async function processPendingReports() {
  if (!isOnline()) return
  const db = await getDatabase()
  const records = await db.getAll(STORES.REPORT)
  for (const record of records) {
    try {
      const response = await fetch(record.reportUrl, {
        method: "POST",
        body: JSON.stringify(record.payload),
        headers: { "Content-Type": "application/json" },
        keepalive: true,
      })
      if (response.ok) {
        await db.delete(STORES.REPORT, record.id)
      }
    } catch (err) {
      warn("Failed to sync report", err)
      break
    }
  }
}

async function processNewsInteractionQueue(db: IDBPDatabase) {
  const records = await db.getAll(STORES.NEWS_INTERACTION)
  for (const record of records) {
    try {
      const { url, method = "POST", payload } = record
      const options: RequestInit = {
        method,
        headers: { "Content-Type": "application/json" },
      }
      if (method !== "GET" && method !== "HEAD") {
        options.body = JSON.stringify(payload)
      }

      const response = await fetch(url, options)
      if (response.ok) {
        await db.delete(STORES.NEWS_INTERACTION, record.id)
      } else if (response.status === 400 || response.status === 404) {
        // Drop invalid requests that will never succeed
        await db.delete(STORES.NEWS_INTERACTION, record.id)
      }
    } catch (err) {
      warn("Failed to sync news interaction", err)
      break
    }
  }
}
